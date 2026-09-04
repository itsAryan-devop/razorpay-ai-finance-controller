"""
Three-way reconciliation tests — ledger expected vs Razorpay reported vs bank received.

Lock in: every planted three-way exception is classified from the UTR join; a bank credit
under a DIFFERENT UTR escalates rather than being auto-accepted; nothing is mis-classified;
and the money tie-out attributes every reported rupee with a zero residual, in integer paise.
"""
import threeway
import generate_data


def _run():
    settlements, bank = threeway._load_threeway()
    records = threeway.reconcile_threeway(settlements, bank)
    truth = threeway._load_threeway_truth()
    return records, truth, {r["settlement_id"]: r for r in records}


def test_threeway_fixture_integrity():
    settlements, bank = threeway._load_threeway()
    assert settlements and bank
    for s in settlements:
        for k in ("expected_net", "reported_net"):
            assert int(s[k]) == float(s[k])                 # integer paise, never float
    for b in bank:
        assert int(b["amount"]) == float(b["amount"])
    truth = threeway._load_threeway_truth()
    # every planted exception kind is present, so the test actually exercises each branch
    assert {"RECONCILED", "SETTLEMENT_SHORT", "BANK_SHORT", "BANK_MISSING",
            "UTR_MISMATCH", "BANK_EXTRA"} <= set(truth.values())


def test_every_settlement_classified_correctly():
    records, truth, _by = _run()
    s = threeway.score_threeway(records, truth)
    assert s["wrong"] == 0                                   # never a confidently-wrong tie-out
    # each gradeable (non-escalated) record matches the answer key
    for r in records:
        if r["route"] != "ESCALATE":
            assert r["label"] == truth[r["settlement_id"]]


def test_utr_mismatch_escalates_not_auto_matched():
    """A bank credit that matches by amount+date but under a DIFFERENT UTR must ESCALATE for
    human confirmation — the honest 'defer, don't fake' rule, same as the 1:1 and batch legs."""
    records, truth, by = _run()
    mismatched = [sid for sid, lbl in truth.items() if lbl == "UTR_MISMATCH"]
    assert mismatched
    for sid in mismatched:
        assert by[sid]["route"] == "ESCALATE"
        assert by[sid]["label"] == "UTR_MISMATCH"


def test_money_tie_out_residual_is_zero_and_integer():
    records, _t, _b = _run()
    m = threeway.threeway_money(records)
    assert m["residual"] == 0                                # every reported rupee attributed
    assert all(isinstance(v, int) for v in m.values())      # integer paise, never float


def test_benign_next_day_bank_posting_still_reconciles():
    """A bank credit posting T+1 vs the settlement date is normal, not an exception."""
    settlements = [{"settlement_id": "s1", "settlement_utr": "UTR1",
                    "expected_net": 100000, "reported_net": 100000, "settled_at": "2026-07-08"}]
    bank = [{"utr": "UTR1", "amount": 100000, "value_date": "2026-07-09", "ref": "NEFT CR"}]
    rec = threeway.reconcile_threeway(settlements, bank)[0]
    assert rec["label"] == "RECONCILED" and rec["route"] == "AUTO"


def test_bank_missing_vs_utr_mismatch():
    """No bank credit at all -> BANK_MISSING (money in transit). A credit of the right amount
    under the wrong UTR -> UTR_MISMATCH (escalate). The two must not be confused."""
    settlements = [{"settlement_id": "s1", "settlement_utr": "UTR1",
                    "expected_net": 50000, "reported_net": 50000, "settled_at": "2026-07-08"}]
    # nothing in the bank -> BANK_MISSING
    r_missing = threeway.reconcile_threeway(settlements, [])[0]
    assert r_missing["label"] == "BANK_MISSING" and r_missing["route"] == "AUTO"
    # right amount+date, wrong UTR -> UTR_MISMATCH escalation
    bank = [{"utr": "OTHER", "amount": 50000, "value_date": "2026-07-08", "ref": "NEFT CR"}]
    r_mis = threeway.reconcile_threeway(settlements, bank)[0]
    assert r_mis["label"] == "UTR_MISMATCH" and r_mis["route"] == "ESCALATE"


def test_orphan_bank_credit_is_bank_extra():
    settlements = []
    bank = [{"utr": "Z9", "amount": 4200, "value_date": "2026-07-10", "ref": "NEFT CR MANUAL"}]
    rec = threeway.reconcile_threeway(settlements, bank)
    assert len(rec) == 1 and rec[0]["label"] == "BANK_EXTRA" and rec[0]["received"] == 4200
