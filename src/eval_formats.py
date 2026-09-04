"""
eval_formats.py — FORMAT-level held-out generalization.

eval_holdout.py varies the RNG SEED (a different random draw, same schema) to prove the
matcher isn't overfit to one dataset. This varies something different and harder: the
bank-narration FORMAT the exception handler reads.

The handler pairs a misattributed credit to its order by finding the customer code inside
the credit's free-text narration. That reader was written against exactly ONE narration
style — "NEFT/{code}". Real banks emit many. If the reader only works on the one format it
was tuned on, it is overfit to a format, and its match rate on a live merchant's real
statements would collapse. This measures exactly that, on the SAME pairing task rendered in
several formats (one seen, several unseen), so any gap is caused purely by the format.

Three readers, run through the REAL pipeline (matcher.reconcile -> resolve_escalations) so
the guard and routing are exactly as shipped:
  strict      the reader AS ORIGINALLY TUNED — case-sensitive substring. Brittle.
  normalized  the SHIPPED reader — casefold + strip separators (_norm). Generalizes.
  llm         the LLM handler, when a provider (Ollama/Anthropic) is available; else n/a.

Honest expectation, stated up front: for narration formats that still CONTAIN the code,
the normalized deterministic reader generalizes on its own — this is a feature, not a gap
(rules-first, auditable, no model needed). The strict->normalized lift on unseen formats is
the real, CI-reproducible result. Formats that carry NO code (only a name) are beyond any
code-only reader and correctly ESCALATE — noted as costed future work, never mis-paired.

Run:  py src/eval_formats.py   (exits non-zero if a gate fails)
"""
import io
import os
import sys
import re
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
import csv
import generate_data
import matcher
import llm_handler

D = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
RESOLVED_ROUTES = ("AUTO_RESOLVE", "FLAG")


def _strict_similarity(code: str, desc: str) -> float:
    """The narration reader AS ORIGINALLY TUNED, before the format-level held-out forced
    the _norm fix: a case-sensitive, separator-sensitive substring check. Frozen here so the
    eval can show, side by side, how the untuned rule degrades on unseen formats."""
    if not code or not desc:
        return 0.0
    if code in desc:
        return 1.0
    if code[:2] and code[:2] in desc:
        return 0.5
    return 0.0


def _load_format(fmt):
    def rd(name):
        with open(os.path.join(D, name), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return rd(f"ledger_{fmt}.csv"), rd(f"settlements_{fmt}.csv")


def _load_format_truth():
    with open(os.path.join(D, "ground_truth_formats.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_fmt = {}
    for r in rows:
        by_fmt.setdefault(r["format"], {})[r["payment_id"]] = r["true_settlement"]
    return by_fmt


def _score_format(fmt, provider, sim_fn):
    """Run the real pipeline on one format's fixture with a chosen narration reader, and
    grade the misattribution pairing against the answer key. Returns (recall, correct,
    wrong, escalated, n)."""
    ledger, recon = _load_format(fmt)
    truth = _load_format_truth()[fmt]

    results = matcher.reconcile(ledger, recon)
    saved = llm_handler._similarity
    llm_handler._similarity = sim_fn                      # swap the reader (guard + heuristic)
    try:
        with redirect_stdout(io.StringIO()):
            llm_handler.resolve_escalations(results, ledger, recon, provider=provider)
    finally:
        llm_handler._similarity = saved

    by_pid = {r.entity_id: r for r in results}
    correct = wrong = escalated = 0
    for pid, want in truth.items():
        r = by_pid.get(pid)
        if r is None or r.route not in RESOLVED_ROUTES:
            escalated += 1
        elif r.matched_entity == want:
            correct += 1
        else:
            wrong += 1
    n = len(truth)
    return correct / n if n else 1.0, correct, wrong, escalated, n


def evaluate():
    formats = generate_data.NARRATION_FORMATS
    llm_active = llm_handler._active_provider("auto")
    llm_available = llm_active in ("ollama", "anthropic")

    rows = []
    for fmt, (_render, seen) in formats.items():
        strict = _score_format(fmt, "heuristic", _strict_similarity)
        norm = _score_format(fmt, "heuristic", llm_handler._similarity)
        llm = _score_format(fmt, "auto", llm_handler._similarity) if llm_available else None
        rows.append({"format": fmt, "seen": seen, "strict": strict,
                     "normalized": norm, "llm": llm})
    return rows, llm_active


def main():
    rows, llm_active = evaluate()

    def cell(s):
        return "   n/a  " if s is None else f"{s[0]:>5.2f}  "

    print(f"format-level held-out — misattribution pairing recall by narration format")
    print(f"(LLM provider resolved to: {llm_active})\n")
    print(f"{'narration format':<14}{'seen?':>6}{'strict':>9}{'normalized':>12}"
          f"{'llm':>9}{'wrong':>7}")
    strict_seen = norm_seen = None
    wrong_total = 0
    strict_unseen, norm_unseen = [], []
    for r in rows:
        s, nm, lm = r["strict"], r["normalized"], r["llm"]
        wrong_here = s[2] + nm[2] + (lm[2] if lm else 0)
        wrong_total += wrong_here
        print(f"{r['format']:<14}{('yes' if r['seen'] else 'no'):>6}"
              f"{cell(s)}{cell(nm):>12}{cell(lm)}{wrong_here:>7}")
        if r["seen"]:
            strict_seen, norm_seen = s[0], nm[0]
        else:
            strict_unseen.append(s[0])
            norm_unseen.append(nm[0])

    su = sum(strict_unseen) / len(strict_unseen) if strict_unseen else 1.0
    nu = sum(norm_unseen) / len(norm_unseen) if norm_unseen else 1.0
    print(f"\nseen format   : strict {strict_seen:.2f}  normalized {norm_seen:.2f}")
    print(f"unseen formats: strict {su:.2f}  normalized {nu:.2f}   "
          f"(normalized recovers +{nu - su:.2f} on unseen — generalizes across format)")
    print(f"wrong pairings (all readers, all formats): {wrong_total}  (must be 0 — "
          f"deterministic escalates instead of mis-pairing)")

    # gates: the shipped reader must be perfect on the seen format (regression) and nothing
    # may ever be mis-paired. The strict<normalized gap on unseen formats is the finding.
    ok = (norm_seen == 1.0) and (wrong_total == 0)
    print(f"\nformat-generalization gate (normalized seen==1.0, 0 wrong): "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
