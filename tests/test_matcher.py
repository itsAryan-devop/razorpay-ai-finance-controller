"""Matcher regression + behaviour tests.

These lock in the honest behaviour we care about:
  - high (but not perfect) classification accuracy
  - structural exceptions resolved exactly
  - genuine ambiguity is ESCALATED, never guessed
  - money is conserved on every clean match
"""
import matcher


def _run():
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    truth = matcher._load_truth()
    return results, truth


def test_classification_accuracy_high_but_honest():
    results, truth = _run()
    pred = {r.entity_id: r.label for r in results}
    keys = set(truth) | set(pred)
    acc = sum(1 for k in keys if truth.get(k) == pred.get(k)) / len(keys)
    # believable, not tautological: rules resolve structure, ambiguity is escalated
    assert 0.90 <= acc < 1.0


def test_missing_credits_all_detected():
    results, truth = _run()
    pred = {r.entity_id: r.label for r in results}
    missing = [k for k, v in truth.items() if v == "MISSING_CREDIT"]
    assert missing and all(pred.get(k) == "MISSING_CREDIT" for k in missing)


def test_structural_exceptions_exact():
    results, truth = _run()
    pred = {r.entity_id: r.label for r in results}
    for label in ("CLEAN", "DUPLICATE", "FEE_MISMATCH",
                  "TIMING_VARIANCE", "REFUND_IN_LATER_CYCLE"):
        keys = [k for k, v in truth.items() if v == label]
        assert keys, f"no {label} cases in fixture"
        assert all(pred.get(k) == label for k in keys), f"{label} misclassified"


def test_ambiguous_pairings_escalate_not_guess():
    results, _ = _run()
    escalated = [r for r in results if r.route == "ESCALATE"]
    assert escalated, "expected at least one escalated ambiguous case"
    # we only escalate genuine ambiguity (more than one candidate credit)
    for r in escalated:
        assert len(r.evidence.get("candidates", [])) > 1


def test_auto_paired_misattributions_are_correct():
    # every AUTO-resolved misattribution must point at the true counterpart credit
    results, _ = _run()
    import csv
    import os
    notes = {}
    with open(os.path.join(matcher.D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    auto = [r for r in results if r.entity_id in notes and r.route == "AUTO"]
    assert auto, "expected some auto-paired misattributions"
    for r in auto:
        assert r.matched_entity == notes[r.entity_id]


def test_money_conserved_on_clean():
    ledger, recon = matcher._load()
    truth = matcher._load_truth()
    by_pid = {r["entity_id"]: r for r in recon if r["type"] == "payment"}
    for l in ledger:
        if truth.get(l["payment_id"]) == "CLEAN":
            row = by_pid[l["payment_id"]]
            assert int(row["credit"]) == int(l["amount"]) - int(row["fee"])
