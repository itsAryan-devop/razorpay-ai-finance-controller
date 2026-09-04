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
import datetime as dt
import os
import sys
import time
import uuid

# Load .env BEFORE importing llm_handler (it reads OLLAMA_MODEL/HOST at import time).
# override=False so real shell env vars and the CI-forced defaults always win.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass

import matcher
import llm_handler
import audit
import obs
import report_metrics
import threeway

AUDIT_PATH = os.path.join(matcher.D, "audit_log.jsonl")
log = obs.get_logger("recon.pipeline")


def _true_ghosts():
    notes = {}
    with open(os.path.join(matcher.D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    return notes


def _pairing_stats(results, truth_ghosts):
    """Returns (total, correct, escalated, wrong).

    `wrong` is reported as an ABSOLUTE COUNT, never folded into an accuracy average:
    for a money system a confidently wrong pairing is a different kind of failure from
    an honest escalation, and averaging the two hides exactly the number that matters.
    """
    mis = [r for r in results if r.entity_id in truth_ghosts]
    resolved = [r for r in mis if r.matched_entity]
    correct = sum(1 for r in resolved if r.matched_entity == truth_ghosts[r.entity_id])
    escalated = sum(1 for r in mis if not r.matched_entity)
    return len(mis), correct, escalated, len(resolved) - correct


def run(dry_run=True, cycle="adhoc", commit=True, reset_audit=False,
        source=None, audit_path=AUDIT_PATH, provider=None) -> dict:
    """End-to-end reconciliation. PURE compute + an OPTIONAL commit to the audit log.

    dry_run : only high-confidence AUTO_RESOLVE may apply, and only when False (execute).
    commit  : when True, append this run's gated decisions to the persistent, append-only
              hash-chained audit log. When False, compute the same decisions but write
              nothing (the UI uses this on every render so the log reflects deliberate
              runs, not re-renders).
    reset_audit : truncate the chain first (a clean demo slate; off by default).
    source  : a sources.ReconciliationSource. Defaults to the CSV generator output.

    Idempotency: a decision whose entity was already committed as APPLIED in a prior run
    is recorded as SKIPPED_IDEMPOTENT and NOT applied again — re-running a cycle is safe.
    """
    if source is None:
        ledger, recon = matcher._load()
    else:
        ledger, recon = source.load_ledger(), source.load_settlements()
    truth = matcher._load_truth()
    truth_ghosts = _true_ghosts()

    t0 = time.perf_counter()
    results = matcher.reconcile(ledger, recon)
    elapsed = time.perf_counter() - t0
    n_records = len(ledger) + len(recon)
    throughput = n_records / elapsed if elapsed > 0 else 0.0

    metrics_before = matcher.compute_metrics(results, truth)
    _, corr_before, esc_before, wrong_before = _pairing_stats(results, truth_ghosts)

    handler_records = llm_handler.resolve_escalations(results, ledger, recon,
                                                      provider=provider)
    engine = handler_records[0]["engine"] if handler_records else "n/a"
    n_mis, corr_after, esc_after, wrong_after = _pairing_stats(results, truth_ghosts)

    # Post-handler, credits the handler paired to an order are no longer "unexplained
    # money": recompute EXTRA_CREDIT precision excluding them (closes the Day-7 loose end).
    resolved_credits = {r.matched_entity for r in results
                        if r.entity_id in truth_ghosts and r.matched_entity}
    ec_after, ec_tp_after, ec_pred_after = matcher.extra_credit_precision(
        results, truth, resolved_credits)
    ec_reclassified = metrics_before["extra_credit_predicted"] - ec_pred_after

    # Is a stated confidence worth anything? Grade each band against the answer key.
    calibration = report_metrics.confidence_calibration(handler_records, truth_ghosts)
    # The rupee view: reconciliation is about money, not row counts.
    money = report_metrics.money_impact(results, ledger, recon, resolved_credits)

    # Many-to-one leg: lump settlement credits that each pay out a batch of orders.
    # Separate fixture, separate metric — never disturbs the 1:1 numbers above. Empty
    # (all zeros) if the batch fixture isn't present, so this is always safe.
    batch_ledger, batch_recon = matcher._load_batch()
    if batch_recon:
        batch_records = matcher.match_batch_settlements(batch_ledger, batch_recon)
        batch = matcher.score_batches(batch_records, matcher._load_batch_truth())
    else:
        batch = {"total": 0, "correct": 0, "wrong": 0, "escalated": 0, "unmatched": 0}

    # Three-way leg: ledger expected vs Razorpay reported vs bank received, joined by UTR.
    # Separate *_3way.csv fixture, separate metric — never disturbs the 1:1 numbers. None if
    # the fixture isn't present, so this is always safe.
    threeway_out = threeway.run_threeway()

    # ---- GUARDRAILS: gate every decision, then (optionally) commit a tamper-evident entry.
    # BOUNDED/GATED: only high-confidence AUTO_RESOLVE may auto-apply, and only in EXECUTE.
    # FLAG/ESCALATE always wait for a human. Dry-run is the default.
    mode = "EXECUTE" if not dry_run else "DRY-RUN"
    if reset_audit and os.path.exists(audit_path):
        os.remove(audit_path)
    already_applied = audit.applied_entities(audit_path)   # from prior committed runs
    run_id = uuid.uuid4().hex[:8]
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    applied = skipped = 0
    audit_rows = []
    for rec in handler_records:
        want_apply = (not dry_run) and rec["route"] == "AUTO_RESOLVE"
        if want_apply and rec["entity_id"] in already_applied:
            action, skipped = "SKIPPED_IDEMPOTENT", skipped + 1   # already applied earlier
        elif want_apply:
            action, applied = "APPLIED", applied + 1
        else:
            action = "PROPOSED"                                    # held for a human
        entry = {**rec, "action": action, "mode": mode,
                 "cycle": cycle, "run_id": run_id, "ts": stamp}
        audit_rows.append(entry)
        if commit:
            audit.append(audit_path, entry)

    ok, count = audit.verify(audit_path)   # whole persisted chain (0 if none committed yet)

    return {
        "results": results,
        "records": handler_records,
        "engine": engine,
        "metrics": metrics_before,
        "pairing": {"total": n_mis, "before": corr_before, "after": corr_after,
                    "escalated_before": esc_before, "escalated_after": esc_after,
                    "wrong_before": wrong_before, "wrong_after": wrong_after},
        "calibration": calibration,
        "money": money,
        "batch": batch,
        "threeway": threeway_out,
        "extra_credit_after": {"precision": ec_after, "tp": ec_tp_after,
                               "predicted": ec_pred_after,
                               "reclassified": ec_reclassified},
        "throughput": throughput,
        "n_records": n_records,
        "elapsed": elapsed,
        "mode": mode,
        "cycle": cycle,
        "run_id": run_id,
        "committed": commit,
        "applied": applied,
        "skipped": skipped,
        "held": len(handler_records) - applied - skipped,
        "audit": {"path": audit_path, "ok": ok, "count": count, "rows": audit_rows},
    }


def _ensure_data():
    """Generate the deterministic dataset if it's missing, so the batch entrypoint is
    self-sufficient (e.g. in a container whose data volume mounts empty over the copy
    baked at build time)."""
    if not os.path.exists(os.path.join(matcher.D, "ledger.csv")):
        import generate_data
        generate_data.generate()


def main(dry_run=True, cycle="adhoc", reset_audit=False):
    obs.configure(os.getenv("LOG_LEVEL", "INFO"))
    obs.enable_utf8_stdout()          # so ₹ prints on a Windows cp1252 console (root fix)
    _ensure_data()
    r = run(dry_run=dry_run, cycle=cycle, commit=True, reset_audit=reset_audit)
    log.info("reconciliation run complete", extra={"fields": {
        "cycle": r["cycle"], "run_id": r["run_id"], "mode": r["mode"],
        "n_records": r["n_records"], "accuracy": round(r["metrics"]["accuracy"], 3),
        "match_rate": round(r["metrics"]["match_rate"], 3),
        "applied": r["applied"], "skipped": r["skipped"], "held": r["held"],
        "audit_entries": r["audit"]["count"], "audit_ok": r["audit"]["ok"]}})
    p = r["pairing"]
    print(f"BEFORE handler (deterministic): {p['before']}/{p['total']} misattributions "
          f"paired correctly, {p['escalated_before']} escalated, "
          f"{p['wrong_before']} WRONG")
    print(f"AFTER  handler ({r['engine']}): {p['after']}/{p['total']} paired correctly, "
          f"{p['escalated_after']} still escalated, {p['wrong_after']} WRONG")
    print(f"throughput: {r['throughput']:.0f} records/s ({r['n_records']} records "
          f"in {r['elapsed']*1000:.0f} ms)")

    print("\n-- confidence calibration (is a stated confidence worth anything?) --")
    print(report_metrics.format_calibration(r["calibration"]))
    print("\n-- money impact --")
    print(report_metrics.format_money(r["money"]))

    b = r["batch"]
    if b["total"]:
        print(f"\n-- batch settlement (many-to-one) --\n"
              f"{b['correct']}/{b['total']} lump credits resolved to the correct order-set"
              f" | {b['escalated']} ambiguous escalated | {b['wrong']} WRONG")

    tw = r.get("threeway")
    if tw:
        s, m = tw["score"], tw["money"]
        print(f"\n-- three-way (ledger vs Razorpay vs bank, joined by UTR) --\n"
              f"{s['total'] - s['escalated']}/{s['total']} records classified"
              f" | {s['escalated']} escalated (UTR mismatch) | {s['wrong']} WRONG | "
              f"of {report_metrics.rupees(m['reported_total'])} reported: "
              f"{report_metrics.rupees(m['in_transit'])} in transit, "
              f"{report_metrics.rupees(m['bank_short_lost'])} short-credited, "
              f"residual {report_metrics.rupees(m['residual'])}")

    extra = f", {r['skipped']} skipped (idempotent)" if r["skipped"] else ""
    print(f"\n[{r['mode']}] cycle={r['cycle']} run={r['run_id']} — "
          f"{r['applied']} applied, {r['held']} held for human review{extra}")
    print(f"audit chain: {r['audit']['count']} entries (persistent), "
          f"integrity {'OK' if r['audit']['ok'] else 'BROKEN'} "
          f"(data/generated/audit_log.jsonl)")
    for rec in r["records"]:
        print(f"   {rec['entity_id']}: {rec['route']} (conf {rec['confidence']}) "
              f"via {rec['engine']} -- {rec['reason']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    cycle_arg = "adhoc"
    if "--cycle" in args:
        cycle_arg = args[args.index("--cycle") + 1]
    main(dry_run="--execute" not in args,
         cycle=cycle_arg,
         reset_audit="--reset-audit" in args)
