"""
pipeline.py — end-to-end run:
  deterministic matcher  ->  LLM/heuristic handler on the escalated residue
  ->  before/after pairing report  +  audit log.

This is the demo entry point. It shows the measurable value the handler adds on
the ambiguous tail the deterministic rules refused to guess.

Run:  py src/pipeline.py            (heuristic fallback, no key needed)
      set ANTHROPIC_API_KEY in .env to run the real LLM path.
"""
import csv
import os
import sys
import time

import matcher
import llm_handler
import audit


def _true_ghosts():
    notes = {}
    with open(os.path.join(matcher.D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    return notes


def _pairing_stats(results, truth_ghosts):
    mis = [r for r in results if r.entity_id in truth_ghosts]
    resolved = [r for r in mis if r.matched_entity]
    correct = sum(1 for r in resolved if r.matched_entity == truth_ghosts[r.entity_id])
    escalated = sum(1 for r in mis if not r.matched_entity)
    return len(mis), correct, escalated


def run(dry_run=True) -> dict:
    """End-to-end run returning EVERYTHING the CLI and the Streamlit UI need — one
    source of truth. Side effect: rewrites data/generated/audit_log.jsonl (a fresh,
    verifiable chain per run). Does not print; callers render."""
    ledger, recon = matcher._load()
    truth = matcher._load_truth()
    truth_ghosts = _true_ghosts()

    t0 = time.perf_counter()
    results = matcher.reconcile(ledger, recon)
    elapsed = time.perf_counter() - t0
    n_records = len(ledger) + len(recon)
    throughput = n_records / elapsed if elapsed > 0 else 0.0

    metrics_before = matcher.compute_metrics(results, truth)
    _, corr_before, esc_before = _pairing_stats(results, truth_ghosts)

    records = llm_handler.resolve_escalations(results, ledger, recon)
    engine = records[0]["engine"] if records else "n/a"
    n_mis, corr_after, esc_after = _pairing_stats(results, truth_ghosts)

    # Post-handler, credits the handler paired to an order are no longer "unexplained
    # money": recompute EXTRA_CREDIT precision excluding them (closes the Day-7 loose end).
    resolved_credits = {r.matched_entity for r in results
                        if r.entity_id in truth_ghosts and r.matched_entity}
    ec_after, ec_tp_after, ec_pred_after = matcher.extra_credit_precision(
        results, truth, resolved_credits)
    ec_reclassified = metrics_before["extra_credit_predicted"] - ec_pred_after

    # ---- GUARDRAILS: gate every decision, then write a tamper-evident audit entry ----
    # BOUNDED/GATED: only high-confidence AUTO_RESOLVE may be auto-applied, and only
    # when --execute is passed. FLAG/ESCALATE always wait for a human. Dry-run is default.
    mode = "EXECUTE" if not dry_run else "DRY-RUN"
    path = os.path.join(matcher.D, "audit_log.jsonl")
    if os.path.exists(path):
        os.remove(path)                       # fresh, verifiable chain per demo run
    applied = 0
    audit_rows = []
    for rec in records:
        can_apply = (not dry_run) and rec["route"] == "AUTO_RESOLVE"
        action = "APPLIED" if can_apply else "PROPOSED"
        applied += can_apply
        entry = {**rec, "action": action, "mode": mode}
        audit.append(path, entry)
        audit_rows.append(entry)
    ok, count = audit.verify(path)

    return {
        "results": results,
        "records": records,
        "engine": engine,
        "metrics": metrics_before,
        "pairing": {"total": n_mis, "before": corr_before, "after": corr_after,
                    "escalated_before": esc_before, "escalated_after": esc_after},
        "extra_credit_after": {"precision": ec_after, "tp": ec_tp_after,
                               "predicted": ec_pred_after,
                               "reclassified": ec_reclassified},
        "throughput": throughput,
        "n_records": n_records,
        "elapsed": elapsed,
        "mode": mode,
        "applied": applied,
        "held": len(records) - applied,
        "audit": {"path": path, "ok": ok, "count": count, "rows": audit_rows},
    }


def main(dry_run=True):
    r = run(dry_run=dry_run)
    p = r["pairing"]
    print(f"BEFORE handler (deterministic): {p['before']}/{p['total']} misattributions "
          f"paired correctly, {p['escalated_before']} escalated")
    print(f"AFTER  handler ({r['engine']}): {p['after']}/{p['total']} paired correctly, "
          f"{p['escalated_after']} still escalated")
    print(f"throughput: {r['throughput']:.0f} records/s ({r['n_records']} records "
          f"in {r['elapsed']*1000:.0f} ms)")

    print(f"\n[{r['mode']}] {r['applied']} applied, {r['held']} held for human review")
    print(f"audit chain: {r['audit']['count']} entries, "
          f"integrity {'OK' if r['audit']['ok'] else 'BROKEN'} "
          f"(data/generated/audit_log.jsonl)")
    for rec in r["records"]:
        print(f"   {rec['entity_id']}: {rec['route']} (conf {rec['confidence']}) "
              f"via {rec['engine']} -- {rec['reason']}")


if __name__ == "__main__":
    main(dry_run="--execute" not in sys.argv)
