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

Runs against the Anthropic API when ANTHROPIC_API_KEY is set; otherwise falls back
to a transparent text-similarity heuristic so the pipeline and CI run keyless.
The LLM's specific value over the heuristic is the audit-ready natural-language
justification and a calibrated confidence — not merely picking the winner.
"""
import os
import re

AUTO_CONF = 0.75      # >= -> AUTO_RESOLVE
FLAG_CONF = 0.45      # >= -> FLAG, else stay ESCALATE
MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")


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


def _llm_choose(code, customer, amount, candidates):
    """Ask the model to pick the right credit + justify. Returns tuple or None on failure."""
    try:
        from anthropic import Anthropic
    except Exception:
        return None
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    import json
    # Untrusted narration is JSON-encoded (quotes/specials escaped) and pre-sanitized,
    # so it cannot break out of its field to be read as an instruction.
    lines = "\n".join(f"  - id={cid}  narration={json.dumps(sanitize_narration(d))}"
                      for cid, d in candidates)
    prompt = (
        "You reconcile payments. An order's money settled under the WRONG payment id. "
        "Pick which settlement credit truly belongs to this order, using the bank "
        "narration text as a fuzzy hint. Do not do arithmetic; the amounts already match.\n\n"
        f"Order customer: {customer}  (code {code}), amount {amount} paise.\n"
        f"Candidate credits (same amount):\n{lines}\n\n"
        'Reply ONLY as JSON: {"chosen":"<id>","confidence":<0..1>,"reason":"<short>"}'
    )
    try:
        import json
        client = Anthropic()
        msg = client.messages.create(model=MODEL, max_tokens=200,
                                      messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        return data["chosen"], float(data["confidence"]), data.get("reason", "")
    except Exception:
        return None                                       # any failure -> heuristic fallback


def resolve_escalations(results, ledger, recon, use_llm=None):
    """Mutates ESCALATE results in place; returns a list of resolution records."""
    if use_llm is None:
        use_llm = bool(os.getenv("ANTHROPIC_API_KEY"))
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

        engine = "llm"
        out = _llm_choose(code, "", amount, candidates) if use_llm else None
        if out is None:
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
