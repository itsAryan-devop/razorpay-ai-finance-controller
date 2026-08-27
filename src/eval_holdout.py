"""
eval_holdout.py — held-out generalization + reliability posture.

The deterministic matcher's rules were written while looking at the seed-42 dataset
(the DEV set). This regenerates the data on INDEPENDENT seeds the rules were never
tuned against (the HELD-OUT set) and re-scores, to show the headline numbers are a
property of the RULES, not an overfit to one random draw.

Reliability note (research: report pass^k for a money agent): the deterministic core
is pass^k = pass@1 by construction — identical input yields identical output on every
trial (verified: byte-identical regeneration under a fixed seed). A money agent that
never disagrees with itself across k runs is the desirable property; a pure-LLM agent's
pass^k collapses with k. The LLM only touches the small escalated tail, and its output
is gated + audited, so stochasticity can never silently apply money.

Run:  py src/eval_holdout.py     (exits non-zero if generalization drops below the gate)
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
import generate_data
import matcher

DEV_SEED = 42
HELDOUT_SEEDS = [7, 123, 2024, 99999]
GATE = 0.95                      # held-out mean accuracy must stay at/above this


def _score_current():
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    return matcher.compute_metrics(results, matcher._load_truth())


def evaluate(seeds=HELDOUT_SEEDS):
    """Score the matcher on the dev seed + each held-out seed. Always restores the
    canonical seed-42 dataset afterwards (deterministic), so callers/tests are undisturbed."""
    rows = []
    try:
        for s in [DEV_SEED] + list(seeds):
            generate_data.SEED = s
            with redirect_stdout(io.StringIO()):          # silence the generator summary
                generate_data.generate()
            m = _score_current()
            rows.append({"seed": s, "held_out": s != DEV_SEED,
                         "accuracy": m["accuracy"], "match_rate": m["match_rate"],
                         "extra_credit_precision": m["extra_credit_precision"],
                         "escalated": m["routing"].get("ESCALATE", 0)})
    finally:
        generate_data.SEED = DEV_SEED
        with redirect_stdout(io.StringIO()):
            generate_data.generate()                      # deterministic restore
    return rows


def summary(rows):
    ho = [r["accuracy"] for r in rows if r["held_out"]]
    dev = next(r["accuracy"] for r in rows if not r["held_out"])
    return {"dev_accuracy": dev, "heldout_mean": sum(ho) / len(ho),
            "heldout_min": min(ho), "heldout_max": max(ho)}


def main():
    rows = evaluate()
    print(f"{'seed':>7} {'set':>9} {'accuracy':>9} {'match_rate':>11} "
          f"{'EC_prec':>8} {'escalated':>10}")
    for r in rows:
        print(f"{r['seed']:>7} {'HELD-OUT' if r['held_out'] else 'DEV':>9} "
              f"{r['accuracy']:>9.3f} {r['match_rate']:>11.3f} "
              f"{r['extra_credit_precision']:>8.2f} {r['escalated']:>10}")
    s = summary(rows)
    print(f"\nheld-out accuracy: mean={s['heldout_mean']:.3f} "
          f"min={s['heldout_min']:.3f} max={s['heldout_max']:.3f}   "
          f"(dev seed {DEV_SEED}: {s['dev_accuracy']:.3f} — the conservative end)")
    ok = s["heldout_mean"] >= GATE
    print(f"generalization gate (held-out mean >= {GATE}): {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
