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


def main(dry_run=True):
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    truth_ghosts = _true_ghosts()

    n, corr, esc = _pairing_stats(results, truth_ghosts)
    print(f"BEFORE handler (deterministic): {corr}/{n} misattributions paired correctly, "
          f"{esc} escalated")

    records = llm_handler.resolve_escalations(results, ledger, recon)
    engine = records[0]["engine"] if records else "n/a"
    n, corr, esc = _pairing_stats(results, truth_ghosts)
    print(f"AFTER  handler ({engine}): {corr}/{n} paired correctly, {esc} still escalated")

    # ---- GUARDRAILS: gate every decision, then write a tamper-evident audit entry ----
    # BOUNDED/GATED: only high-confidence AUTO_RESOLVE may be auto-applied, and only
    # when --execute is passed. FLAG/ESCALATE always wait for a human. Dry-run is default.
    mode = "EXECUTE" if not dry_run else "DRY-RUN"
    path = os.path.join(matcher.D, "audit_log.jsonl")
    if os.path.exists(path):
        os.remove(path)                       # fresh, verifiable chain per demo run
    applied = 0
    for rec in records:
        can_apply = (not dry_run) and rec["route"] == "AUTO_RESOLVE"
        action = "APPLIED" if can_apply else "PROPOSED"
        applied += can_apply
        audit.append(path, {**rec, "action": action, "mode": mode})

    ok, count = audit.verify(path)
    print(f"\n[{mode}] {applied} applied, {len(records) - applied} held for human review")
    print(f"audit chain: {count} entries, integrity {'OK' if ok else 'BROKEN'} "
          f"(data/generated/audit_log.jsonl)")
    for rec in records:
        print(f"   {rec['entity_id']}: {rec['route']} (conf {rec['confidence']}) "
              f"via {rec['engine']} -- {rec['reason']}")


if __name__ == "__main__":
    main(dry_run="--execute" not in sys.argv)
