"""
report_metrics.py — reporting aggregations over an already-computed reconciliation run.

Three artifacts, all derived from data the pipeline already produces (no new guesses,
no new model calls):

  1. confidence_calibration()  — is a stated confidence WORTH anything? Buckets every
     handler decision by its confidence band and reports the EMPIRICAL accuracy of each
     band against ground truth. A confidence number nobody checks is decoration; this
     checks it.

  2. money_impact()            — the ₹ view. Reconciliation is about money, not row
     counts, so report value settled / never settled / unexplained, and prove every
     rupee of the ledger is attributed to exactly one bucket.

  3. wrong-match counting      — see pipeline._pairing_stats. A WRONG match is reported
     as an absolute count, never averaged into an accuracy figure that hides it: for a
     money system, one confident wrong pairing is worse than ten honest escalations.

All money is paise (int) end to end — a reconciler must never float money.
"""

import llm_handler


def rupees(paise: int, symbol: str = "₹") -> str:
    """Format paise for display. Display only — never used in math.

    Uses the ₹ sign by default now that the CLI entrypoint forces UTF-8 stdout
    (obs.enable_utf8_stdout) — the root-cause fix for the day-1 cp1252 crash, so CLI and
    the Streamlit UI show identical figures. `symbol` is still overridable for any surface
    that genuinely can't render it.
    """
    return f"{symbol}{int(paise) / 100:,.2f}"


# --------------------------------------------------------------- 1. calibration
def confidence_calibration(records, truth_pairings) -> list[dict]:
    """Bucket handler decisions by confidence band, and score each band against the
    answer key.

    records        : handler records ({entity_id, chosen, confidence, route, ...})
    truth_pairings : {order payment_id -> the credit id that TRULY belongs to it}

    Returns one row per band (highest first) with n / correct / empirical accuracy.
    A band with n=0 is still returned (accuracy None) so the table shape is stable and
    an empty band is visible rather than silently dropped.
    """
    bands = [
        ("AUTO_RESOLVE", f">= {llm_handler.AUTO_CONF}", llm_handler.AUTO_CONF, 1.01),
        ("FLAG", f"{llm_handler.FLAG_CONF} - {llm_handler.AUTO_CONF}",
         llm_handler.FLAG_CONF, llm_handler.AUTO_CONF),
        ("ESCALATE", f"< {llm_handler.FLAG_CONF}", -0.01, llm_handler.FLAG_CONF),
    ]
    out = []
    for name, label, lo, hi in bands:
        in_band = [r for r in records if lo <= r.get("confidence", 0.0) < hi]
        # Only decisions we can actually grade (the entity is in the answer key) count
        # toward accuracy — an ungradeable row must not be silently scored as correct.
        gradeable = [r for r in in_band if r["entity_id"] in truth_pairings]
        correct = sum(1 for r in gradeable
                      if r.get("chosen") == truth_pairings[r["entity_id"]])
        out.append({
            "band": name,
            "range": label,
            "n": len(in_band),
            "gradeable": len(gradeable),
            "correct": correct,
            "accuracy": (correct / len(gradeable)) if gradeable else None,
        })
    return out


# -------------------------------------------------------------- 2. money impact
def _amount_index(ledger, recon) -> dict:
    """entity_id -> amount in paise. Ledger wins for real payment ids; recon supplies
    the ghost/orphan credit ids that never existed in the merchant's books."""
    amt = {l["payment_id"]: int(l["amount"]) for l in ledger}
    for r in recon:
        amt.setdefault(r["entity_id"], int(r["amount"]))
    return amt


def money_impact(results, ledger, recon, resolved_credits=None) -> dict:
    """The ₹ view of a reconciliation run.

    Every rupee in the merchant's ledger lands in exactly one bucket: tied to a
    settlement, or never settled. `unattributed` is the residual and MUST be 0 — it is
    reported rather than asserted away, so a future bug shows up as a number instead of
    hiding. `unexplained` is the other direction: money that arrived with no ledger
    order behind it (orphan credits the handler could not pair).
    """
    resolved_credits = resolved_credits or set()
    amt = _amount_index(ledger, recon)
    ledger_pids = {l["payment_id"] for l in ledger}

    total_ledger = sum(int(l["amount"]) for l in ledger)

    never_settled = [r for r in results
                     if r.entity_id in ledger_pids and r.label == "MISSING_CREDIT"]
    never_settled_value = sum(amt.get(r.entity_id, 0) for r in never_settled)

    settled = [r for r in results
               if r.entity_id in ledger_pids and r.label != "MISSING_CREDIT"]
    settled_value = sum(amt.get(r.entity_id, 0) for r in settled)

    # Orphan credits still unexplained after the handler had its chance to pair them.
    unexplained = [r for r in results
                   if r.label == "EXTRA_CREDIT" and r.entity_id not in resolved_credits]
    unexplained_value = sum(amt.get(r.entity_id, 0) for r in unexplained)

    return {
        "total_ledger": total_ledger,
        "settled_value": settled_value,
        "settled_orders": len(settled),
        "never_settled_value": never_settled_value,
        "never_settled_orders": len(never_settled),
        "unexplained_value": unexplained_value,
        "unexplained_credits": len(unexplained),
        # residual: must be 0 if every ledger order was classified into exactly one bucket
        "unattributed_value": total_ledger - settled_value - never_settled_value,
    }


# ------------------------------------------------------------------- rendering
def format_calibration(rows) -> str:
    """Plain-ASCII table (Windows consoles choke on fancy glyphs — see LOG.md day 1)."""
    lines = [f"{'band':<14}{'range':>14}{'n':>5}{'gradeable':>11}{'correct':>9}{'accuracy':>10}"]
    for r in rows:
        acc = "n/a" if r["accuracy"] is None else f"{r['accuracy']:.2f}"
        lines.append(f"{r['band']:<14}{r['range']:>14}{r['n']:>5}"
                     f"{r['gradeable']:>11}{r['correct']:>9}{acc:>10}")
    return "\n".join(lines)


def format_money(m) -> str:
    return (
        f"ledger value        : {rupees(m['total_ledger'])}\n"
        f"  tied to settlement: {rupees(m['settled_value'])}  ({m['settled_orders']} orders)\n"
        f"  never settled     : {rupees(m['never_settled_value'])}  "
        f"({m['never_settled_orders']} orders)\n"
        f"unexplained credits : {rupees(m['unexplained_value'])}  "
        f"({m['unexplained_credits']} orphan credits, no ledger order)\n"
        f"unattributed        : {rupees(m['unattributed_value'])}   <- must be 0"
    )
