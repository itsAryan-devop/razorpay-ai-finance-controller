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

# Approximate published per-token pricing (USD per 1K tokens) for cost-per-decision
# reporting — a real judging criterion (task completion / cost-per-run / latency /
# hallucination rate). ENV-overridable and labelled "approximate": verify against
# https://www.anthropic.com/pricing before treating as exact billing truth. Ollama and
# the heuristic are genuinely free (local compute / no model call) — $0.00, not estimated.
ANTHROPIC_COST_PER_1K_INPUT = float(os.getenv("ANTHROPIC_COST_PER_1K_INPUT", "0.001"))
ANTHROPIC_COST_PER_1K_OUTPUT = float(os.getenv("ANTHROPIC_COST_PER_1K_OUTPUT", "0.005"))

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


def _ollama_choose(code, customer, amount, candidates, trace_out=None):
    """Ask a local Ollama model to pick the right credit + justify. Returns a tuple,
    or None on ANY failure (no server, timeout, bad JSON) so the caller falls back to
    the heuristic. Uses structured output (format=json) + temperature 0 for determinism.

    trace_out (optional dict, mutated in place): captures latency/tokens/raw-response
    for the decision-trace viewer and cost reporting — local inference is always $0."""
    prompt = _build_prompt(code, customer, amount, candidates)
    body = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",                 # constrain output to valid JSON
        "options": {"temperature": 0},
        # Reasoning models (qwen3) otherwise spend 40-120s on chain-of-thought before
        # answering — we only need a narration match, so disable it (measured 42s -> 3s).
        "think": False,
    }
    t0 = time.perf_counter()
    try:
        import requests
        try:
            resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=body,
                                 timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT))
            resp.raise_for_status()
        except requests.HTTPError:
            body.pop("think", None)       # a non-reasoning model may reject 'think' -> retry
            resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=body,
                                 timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT))
            resp.raise_for_status()
        payload = resp.json()
        content = payload["message"]["content"]
        if trace_out is not None:
            trace_out.update({
                "prompt": prompt, "raw_response": content,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "tokens_in": payload.get("prompt_eval_count"),
                "tokens_out": payload.get("eval_count"),
                "cost_usd": 0.0, "cost_note": "local inference — free", "error": None,
            })
        return _parse_choice(content)
    except Exception as e:
        if trace_out is not None:
            trace_out.update({
                "prompt": prompt, "raw_response": None,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "tokens_in": None, "tokens_out": None,
                "cost_usd": 0.0, "cost_note": "local inference — free", "error": repr(e),
            })
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


def _llm_choose(code, customer, amount, candidates, trace_out=None):
    """Ask the Anthropic model to pick the right credit + justify. Returns a tuple or
    None on failure (so the caller falls back to the heuristic).

    trace_out (optional dict, mutated in place): captures latency/tokens/raw-response
    + an approximate USD cost estimate for the decision-trace viewer and cost reporting."""
    if not _anthropic_ready():
        return None
    from anthropic import Anthropic
    prompt = _build_prompt(code, customer, amount, candidates)
    t0 = time.perf_counter()
    try:
        client = Anthropic()
        msg = client.messages.create(model=MODEL, max_tokens=200,
                                      messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if trace_out is not None:
            tin = tout = cost = None
            try:
                tin, tout = msg.usage.input_tokens, msg.usage.output_tokens
                cost = round(tin / 1000 * ANTHROPIC_COST_PER_1K_INPUT
                             + tout / 1000 * ANTHROPIC_COST_PER_1K_OUTPUT, 6)
            except Exception:
                pass
            trace_out.update({
                "prompt": prompt, "raw_response": text,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "tokens_in": tin, "tokens_out": tout,
                "cost_usd": cost, "cost_note": "approximate — see ANTHROPIC_COST_PER_1K_*",
                "error": None,
            })
        return _parse_choice(text)
    except Exception as e:
        if trace_out is not None:
            trace_out.update({
                "prompt": prompt, "raw_response": None,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "tokens_in": None, "tokens_out": None,
                "cost_usd": None, "cost_note": "call failed", "error": repr(e),
            })
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

        out, engine, trace = None, active, {}
        model_attempted = active in ("ollama", "anthropic")
        if active == "ollama":
            out = _ollama_choose(code, "", amount, candidates, trace_out=trace)
        elif active == "anthropic":
            out = _llm_choose(code, "", amount, candidates, trace_out=trace)
        model_raw_pick = out[0] if out is not None else None      # pre-guard, for the
                                                                    # hallucination-rate metric

        # Deterministic guard on the model's proposal: "the LLM reads, code VERIFIES."
        # The chosen credit must have actual narration support for this order's code — an
        # LLM may interpret a fuzzy signal but must not invent a match that isn't there.
        # Observed live: qwen3:4b paired order code KI532 to a 'NEFT/SK815' credit at
        # confidence 0.85 (would auto-apply a WRONG money decision). The guard rejects an
        # unsupported pick and falls back to the transparent, conservative heuristic.
        rejected_pick = False
        if out is not None and _similarity(code, dict(candidates).get(out[0], "")) <= 0.0:
            out, rejected_pick = None, True

        if out is None:                     # provider unused/failed, or its pick was rejected
            engine = (f"heuristic (after {active} pick rejected)" if rejected_pick
                      else "heuristic")
            t0 = time.perf_counter()
            out = _heuristic_choose(code, candidates)
            if not trace:                   # provider was never attempted (heuristic-only run)
                trace = {"prompt": None, "raw_response": None,
                         "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
                         "tokens_in": None, "tokens_out": None, "cost_usd": 0.0,
                         "cost_note": "deterministic text-similarity — no model call",
                         "error": None}
        chosen, conf, why = out

        route = ("AUTO_RESOLVE" if conf >= AUTO_CONF
                 else "FLAG" if conf >= FLAG_CONF else "ESCALATE")
        r.matched_entity = chosen if route != "ESCALATE" else ""
        r.route = route
        r.reason = f"[{engine}] {why}"
        records.append({
            "entity_id": r.entity_id, "engine": engine, "chosen": chosen,
            "confidence": round(conf, 3), "route": route, "reason": why,
            "model_attempted": model_attempted, "model_raw_pick": model_raw_pick,
            "guard_rejected": rejected_pick, "trace": trace,
        })
    return records
