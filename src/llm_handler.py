"""
llm_handler.py — resolves the ESCALATED residue the deterministic matcher refused
to guess (ambiguous misattributed credits with colliding amounts).

Principle (from research): the LLM READS, deterministic code does the MATH.
The handler weighs a fuzzy free-text bank-narration signal to decide which orphan
credit belongs to an order, and returns:
  - matched_entity   (the chosen credit; code verifies the amount separately)
  - confidence       (0..1)
  - justification    (human-readable, for the audit trail)
  - route            AUTO_RESOLVE (confident) | FLAG (weak) | ESCALATE (still human)

Provider is selected via LLM_PROVIDER (default "auto"):
  auto       -> local Ollama if its server responds, else Anthropic if a key is set,
                else the transparent heuristic
  ollama     -> local Ollama (free, no key)  [OLLAMA_HOST, OLLAMA_MODEL]
  anthropic  -> Anthropic API                [ANTHROPIC_API_KEY, LLM_MODEL]
  heuristic  -> deterministic text-similarity (the zero-config CI default & fallback)

Every provider degrades gracefully to the heuristic on ANY failure (no server, no key,
timeout, bad JSON), so a keyless / server-less run — CI included — always works.
The audit "engine" field records the provider that actually decided each case.
"""
import os
import re
import time

AUTO_CONF = 0.75      # >= -> AUTO_RESOLVE
FLAG_CONF = 0.45      # >= -> FLAG, else stay ESCALATE

# Anthropic (optional, paid)
MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

# Ollama (optional, FREE + LOCAL). Default qwen3:4b — at ~2.5GB it fits FULLY on a
# 4GB-VRAM RTX 3050 (no CPU offload) and Qwen is strong at structured JSON. Do NOT
# default to a 7B (spills to CPU on a 4GB card) or llama3.2:3b (weak JSON reliability).
# Default host is 127.0.0.1 (NOT "localhost") on purpose: Ollama listens on 127.0.0.1,
# and "localhost" resolves to ::1 first on Windows, so an absent server costs ~5x longer
# to fail (measured 1958ms vs 403ms). Override with OLLAMA_HOST if your server differs.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
# Short PROBE timeout: a dead port on Windows DROPS the SYN (no fast refusal), so we cap
# the wait. 0.4s bounds an absent-server probe while staying ample for a real local connect.
OLLAMA_PROBE_TIMEOUT = float(os.getenv("OLLAMA_PROBE_TIMEOUT", "0.4"))
OLLAMA_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "2"))  # chat connect
OLLAMA_READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", "60"))  # 4B first-gen warmup
_PROBE_CACHE: dict = {}          # host -> (ok, expiry_monotonic); avoids re-probing per case
_PROBE_TTL = 15.0

MAX_NARRATION = 120       # bank narrations are short; anything longer is suspect


def sanitize_narration(text: str, max_len: int = MAX_NARRATION) -> str:
    """Bank narration is attacker-influenceable free text that we feed to an LLM, so
    it is untrusted input. Strip control chars / newlines (which is how injection
    payloads smuggle 'ignore previous instructions'), collapse whitespace, and bound
    the length. The deterministic heuristic path is injection-immune anyway (it only
    substring-matches a customer code); this hardens the LLM path, where we ALSO pass
    the value as JSON-encoded data, never as instructions."""
    if not text:
        return ""
    cleaned = "".join(c if (c.isprintable() and c not in "\r\n\t") else " " for c in text)
    cleaned = " ".join(cleaned.split())               # collapse runs of whitespace
    return cleaned[:max_len]


def customer_code(customer: str) -> str:
    m = re.search(r"\(([^)]+)\)", customer or "")
    return m.group(1) if m else ""


def _similarity(code: str, desc: str) -> float:
    """Transparent fuzzy score between an order's code and a credit's narration."""
    if not code or not desc:
        return 0.0
    if code in desc:
        return 1.0
    if code[:2] and code[:2] in desc:
        return 0.5
    return 0.0


def _heuristic_choose(code, candidates):
    """candidates: list of (entity_id, description). Returns (entity, conf, why)."""
    scored = sorted(((cid, _similarity(code, d), d) for cid, d in candidates),
                    key=lambda x: x[1], reverse=True)
    top_id, top, top_desc = scored[0]
    runner = scored[1][1] if len(scored) > 1 else 0.0
    conf = max(0.0, top - runner) if top > 0 else 0.0     # margin-based confidence
    why = (f"narration '{top_desc}' best matches customer code {code} "
           f"(score {top:.2f} vs next {runner:.2f})")
    return top_id, conf, why


# --------------------------------------------------------------- shared LLM plumbing
def _build_prompt(code, customer, amount, candidates) -> str:
    """One prompt for every model provider. Untrusted narration is sanitized AND
    JSON-encoded (quotes/specials escaped), so it is passed as DATA and cannot break
    out of its field to be read as an instruction."""
    import json
    lines = "\n".join(f"  - id={cid}  narration={json.dumps(sanitize_narration(d))}"
                      for cid, d in candidates)
    return (
        "You reconcile payments. An order's money settled under the WRONG payment id. "
        "Pick which settlement credit truly belongs to this order, using the bank "
        "narration text as a fuzzy hint. Do not do arithmetic; the amounts already match.\n\n"
        f"Order customer: {customer}  (code {code}), amount {amount} paise.\n"
        f"Candidate credits (same amount):\n{lines}\n\n"
        'Reply ONLY as JSON: {"chosen":"<id>","confidence":<0..1>,"reason":"<short>"}'
    )


def _parse_choice(text: str):
    """Extract {chosen, confidence, reason} from model text. Tolerates surrounding
    prose by grabbing the first JSON object. Returns a tuple or raises."""
    import json
    data = json.loads(text) if text.strip().startswith("{") \
        else json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    return data["chosen"], float(data["confidence"]), data.get("reason", "")


# ------------------------------------------------------------------- Ollama (free/local)
def _ollama_available(host: str = None) -> bool:
    """One cheap, cached reachability probe. Bounded by the short probe timeout so an
    absent/firewalled server can never stall the run; cached briefly so we probe once
    per run, not once per escalated case. Any failure -> False."""
    host = host or OLLAMA_HOST
    now = time.monotonic()
    cached = _PROBE_CACHE.get(host)
    if cached and cached[1] > now:
        return cached[0]
    ok = False
    try:
        import requests
        r = requests.get(f"{host}/api/tags",
                         timeout=(OLLAMA_PROBE_TIMEOUT, OLLAMA_PROBE_TIMEOUT))
        ok = (r.status_code == 200)
    except Exception:
        ok = False
    _PROBE_CACHE[host] = (ok, now + _PROBE_TTL)
    return ok


def _ollama_choose(code, customer, amount, candidates):
    """Ask a local Ollama model to pick the right credit + justify. Returns a tuple,
    or None on ANY failure (no server, timeout, bad JSON) so the caller falls back to
    the heuristic. Uses structured output (format=json) + temperature 0 for determinism."""
    prompt = _build_prompt(code, customer, amount, candidates)
    try:
        import requests
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT),  # connect instant once probed
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",                 # constrain output to valid JSON
                "options": {"temperature": 0},
            },
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return _parse_choice(content)
    except Exception:
        return None                                # any failure -> heuristic fallback


# ------------------------------------------------------------------- Anthropic (paid API)
def _anthropic_ready() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def _llm_choose(code, customer, amount, candidates):
    """Ask the Anthropic model to pick the right credit + justify. Returns a tuple or
    None on failure (so the caller falls back to the heuristic)."""
    if not _anthropic_ready():
        return None
    from anthropic import Anthropic
    prompt = _build_prompt(code, customer, amount, candidates)
    try:
        client = Anthropic()
        msg = client.messages.create(model=MODEL, max_tokens=200,
                                      messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return _parse_choice(text)
    except Exception:
        return None


# ------------------------------------------------------------------- provider selection
def _active_provider(provider: str) -> str:
    """Resolve the requested provider to one that is actually usable right now. Anything
    unavailable degrades to 'heuristic', which always works (no key, no server)."""
    provider = (provider or "auto").lower()
    if provider == "heuristic":
        return "heuristic"
    if provider == "anthropic":
        return "anthropic" if _anthropic_ready() else "heuristic"
    if provider == "ollama":
        return "ollama" if _ollama_available() else "heuristic"
    # auto: prefer the free local model, then the paid API, then the heuristic
    if _ollama_available():
        return "ollama"
    if _anthropic_ready():
        return "anthropic"
    return "heuristic"


def resolve_escalations(results, ledger, recon, use_llm=None, provider=None):
    """Mutates ESCALATE results in place; returns a list of resolution records.

    Provider precedence: explicit `provider` arg > LLM_PROVIDER env > 'auto'.
    `use_llm=False` forces the heuristic (kept for existing callers/tests). The chosen
    provider is probed ONCE here, not per-case."""
    provider = provider or os.getenv("LLM_PROVIDER", "auto")
    if use_llm is False:
        provider = "heuristic"
    active = _active_provider(provider)

    code_by_pid = {l["payment_id"]: customer_code(l.get("customer", "")) for l in ledger}
    desc_by_eid = {r["entity_id"]: r.get("description", "")
                   for r in recon if r["type"] == "payment"}

    records = []
    for r in results:
        if r.route != "ESCALATE":
            continue
        code = code_by_pid.get(r.entity_id, "")
        cand_ids = r.evidence.get("candidates", [])
        candidates = [(cid, sanitize_narration(desc_by_eid.get(cid, "")))
                      for cid in cand_ids]
        amount = r.evidence.get("amount", 0)

        out, engine = None, active
        if active == "ollama":
            out = _ollama_choose(code, "", amount, candidates)
        elif active == "anthropic":
            out = _llm_choose(code, "", amount, candidates)
        if out is None:                     # provider unused, or it failed on this case
            engine = "heuristic"
            out = _heuristic_choose(code, candidates)
        chosen, conf, why = out

        route = ("AUTO_RESOLVE" if conf >= AUTO_CONF
                 else "FLAG" if conf >= FLAG_CONF else "ESCALATE")
        r.matched_entity = chosen if route != "ESCALATE" else ""
        r.route = route
        r.reason = f"[{engine}] {why}"
        records.append({"entity_id": r.entity_id, "engine": engine, "chosen": chosen,
                        "confidence": round(conf, 3), "route": route, "reason": why})
    return records
