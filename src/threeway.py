"""
threeway.py — three-way reconciliation: ledger expected vs Razorpay settlement reported
vs bank statement received, joined by UTR.

The 1:1 core (matcher.py) ties the merchant ledger to the Razorpay settlement report. But
"Razorpay reported a payout" is not "the money is in my bank": a settlement UTR can be
short-credited, delayed in transit, arrive under a corrected UTR, or never show up. Finance
teams close the loop with a THREE-way tie-out:

    expected (books)  ==  reported (Razorpay)  ==  received (bank)      to the paise, by UTR

This is a SEPARATE leg on its own *_3way.csv fixture, so it never perturbs the 1:1 numbers.
Deterministic: the UTR join and every rupee comparison are done in code; genuine ambiguity
(a bank credit that matches by amount+date but under a DIFFERENT UTR) is ESCALATED, not
guessed — the same "defer, don't fake" rule as the other legs.

Typed exceptions:
  RECONCILED        expected == reported == received (benign next-day bank posting tolerated)
  SETTLEMENT_SHORT  Razorpay reported less than the books expected (funds on_hold/withheld)
  BANK_SHORT        the bank credited less than Razorpay reported (a bank-side deduction)
  BANK_MISSING      Razorpay reported a payout but nothing credited the bank (money in transit)
  UTR_MISMATCH      a bank credit matches by amount+date but a different UTR -> ESCALATE
  BANK_EXTRA        a bank credit with no settlement behind it (unexplained money in)

Run:  py src/threeway.py
"""
import csv
import os
import datetime as dt

D = os.path.join(os.path.dirname(__file__), "..", "data", "generated")

BANK_POST_LAG_OK = 1          # a bank credit posting up to T+1 vs the settlement date is benign
UTR_MATCH_WINDOW = 3          # amount+date fallback search window when the UTR isn't found
AUTO_LABELS = {"RECONCILED", "SETTLEMENT_SHORT", "BANK_SHORT", "BANK_MISSING", "BANK_EXTRA"}


def _date(s):
    return dt.date.fromisoformat(s)


def reconcile_threeway(settlements, bank):
    """Join each settlement to a bank credit by UTR, classify the three-way outcome, and
    account for every bank credit. Returns one record per settlement plus one per orphan
    bank credit (BANK_EXTRA). Amount+date is only a FALLBACK when the exact UTR is absent,
    and a fallback hit under a different UTR ESCALATES rather than auto-matching."""
    bank_by_utr = {}
    for b in bank:
        bank_by_utr.setdefault(b["utr"], []).append(b)
    claimed = set()                                     # id(bank_row) already accounted for
    records = []

    for s in settlements:
        sid, utr = s["settlement_id"], s["settlement_utr"]
        expected, reported = int(s["expected_net"]), int(s["reported_net"])
        settled = _date(s["settled_at"])
        exact = [b for b in bank_by_utr.get(utr, []) if id(b) not in claimed]

        if exact:
            b = exact[0]
            claimed.add(id(b))
            received = int(b["amount"])
            lag = (_date(b["value_date"]) - settled).days
            if received == reported == expected:
                label, route = "RECONCILED", "AUTO"
                reason = (f"expected==reported==received ({received}) via UTR {utr}"
                          + (f", benign T+{lag} bank posting" if lag else ""))
            elif reported < expected and received == reported:
                label, route = "SETTLEMENT_SHORT", "AUTO"
                reason = (f"Razorpay reported {reported} vs books {expected} "
                          f"(withheld {expected - reported}); bank matched the report")
            elif received < reported:
                label, route = "BANK_SHORT", "AUTO"
                reason = f"bank credited {received} vs reported {reported} (short {reported - received})"
            else:
                label, route = "UTR_MISMATCH", "ESCALATE"
                reason = f"amounts disagree (exp {expected}/rep {reported}/recv {received})"
            records.append({"settlement_id": sid, "label": label, "route": route,
                            "expected": expected, "reported": reported, "received": received,
                            "matched_utr": utr, "reason": reason})
            continue

        # no exact UTR — fall back to amount+date, but do NOT auto-accept a different UTR
        cands = [b for b in bank if id(b) not in claimed and int(b["amount"]) == reported
                 and 0 <= (_date(b["value_date"]) - settled).days <= UTR_MATCH_WINDOW]
        if len(cands) == 1:
            claimed.add(id(cands[0]))
            records.append({"settlement_id": sid, "label": "UTR_MISMATCH", "route": "ESCALATE",
                            "expected": expected, "reported": reported,
                            "received": int(cands[0]["amount"]), "matched_utr": cands[0]["utr"],
                            "reason": f"bank credit {cands[0]['amount']} matches amount+date but "
                                      f"under UTR {cands[0]['utr']} != settlement UTR {utr}"})
        elif len(cands) > 1:
            records.append({"settlement_id": sid, "label": "UTR_MISMATCH", "route": "ESCALATE",
                            "expected": expected, "reported": reported, "received": 0,
                            "matched_utr": "", "reason": f"{len(cands)} bank credits match "
                                                         f"amount+date, none by UTR — ambiguous"})
        else:
            records.append({"settlement_id": sid, "label": "BANK_MISSING", "route": "AUTO",
                            "expected": expected, "reported": reported, "received": 0,
                            "matched_utr": "", "reason": f"reported {reported} but no bank credit "
                                                         f"(money in transit / owed)"})

    for b in bank:                                      # bank credits nothing claimed -> orphan
        if id(b) not in claimed:
            records.append({"settlement_id": f"BANK_EXTRA:{b['utr']}", "label": "BANK_EXTRA",
                            "route": "AUTO", "expected": 0, "reported": 0,
                            "received": int(b["amount"]), "matched_utr": b["utr"],
                            "reason": "bank credit with no settlement behind it (unexplained)"})
    return records


def _load_threeway():
    def rd(name):
        path = os.path.join(D, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return rd("settlements_3way.csv"), rd("bank_3way.csv")


def _load_threeway_truth():
    path = os.path.join(D, "ground_truth_3way.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {t["settlement_id"]: t["label"] for t in csv.DictReader(f)}


def score_threeway(records, truth):
    """Grade the classification against the answer key. wrong = an AUTO record whose label
    disagrees with truth (a confidently-wrong tie-out — reported, never hidden); escalated =
    honestly deferred (UTR mismatches). Accuracy excludes escalations from the numerator the
    same way the 1:1 leg keeps wrong-matches out of its accuracy average."""
    total = correct = wrong = escalated = 0
    for r in records:
        total += 1
        want = truth.get(r["settlement_id"])
        if r["route"] == "ESCALATE":
            escalated += 1
        elif want == r["label"]:
            correct += 1
        else:
            wrong += 1
    gradeable = total - escalated
    return {"total": total, "correct": correct, "wrong": wrong, "escalated": escalated,
            "accuracy": correct / gradeable if gradeable else 1.0}


def threeway_money(records):
    """Attribute every REPORTED settlement rupee to exactly one bucket, plus the books gap
    and unexplained bank credits. Integer paise throughout; the residual must be zero."""
    reported_total = sum(r["reported"] for r in records)
    reconciled = sum(r["received"] for r in records if r["label"] == "RECONCILED")
    short_settled_landed = sum(r["received"] for r in records if r["label"] == "SETTLEMENT_SHORT")
    bank_short_landed = sum(r["received"] for r in records if r["label"] == "BANK_SHORT")
    bank_short_lost = sum(r["reported"] - r["received"] for r in records if r["label"] == "BANK_SHORT")
    in_transit = sum(r["reported"] for r in records if r["label"] == "BANK_MISSING")
    under_wrong_utr = sum(r["reported"] for r in records if r["label"] == "UTR_MISMATCH")
    landed = reconciled + short_settled_landed + bank_short_landed
    accounted = landed + bank_short_lost + in_transit + under_wrong_utr
    gateway_withheld = sum(r["expected"] - r["reported"] for r in records
                           if r["label"] == "SETTLEMENT_SHORT")
    bank_extra = sum(r["received"] for r in records if r["label"] == "BANK_EXTRA")
    return {"reported_total": reported_total, "landed_reconciled_or_short": landed,
            "bank_short_lost": bank_short_lost, "in_transit": in_transit,
            "under_wrong_utr": under_wrong_utr, "gateway_withheld": gateway_withheld,
            "bank_extra": bank_extra, "residual": reported_total - accounted}


def run_threeway():
    settlements, bank = _load_threeway()
    if not settlements:
        return None
    records = reconcile_threeway(settlements, bank)
    return {"records": records, "score": score_threeway(records, _load_threeway_truth()),
            "money": threeway_money(records)}


if __name__ == "__main__":
    import obs
    obs.enable_utf8_stdout()
    from report_metrics import rupees
    out = run_threeway()
    if not out:
        print("no three-way fixture found (run: py src/generate_data.py)")
        raise SystemExit(0)
    s, m, recs = out["score"], out["money"], out["records"]
    from collections import Counter
    print("three-way reconciliation (ledger expected vs Razorpay reported vs bank received)\n")
    print("exception mix:", dict(Counter(r["label"] for r in recs)))
    print(f"\nclassification accuracy: {s['accuracy']:.3f}  ({s['correct']}/"
          f"{s['total'] - s['escalated']} gradeable) | {s['escalated']} escalated "
          f"(UTR mismatch) | {s['wrong']} WRONG")
    print("\n-- money tie-out (of what Razorpay REPORTED as settled) --")
    print(f"reported settled     : {rupees(m['reported_total'])}")
    print(f"  landed & tied      : {rupees(m['landed_reconciled_or_short'])}")
    print(f"  bank short-credited: {rupees(m['bank_short_lost'])}")
    print(f"  in transit (unpaid): {rupees(m['in_transit'])}")
    print(f"  under a wrong UTR  : {rupees(m['under_wrong_utr'])}  (escalated for confirm)")
    print(f"  residual           : {rupees(m['residual'])}   <- must be 0")
    print(f"gateway withheld vs books: {rupees(m['gateway_withheld'])}  (settlement short of expected)")
    print(f"unexplained bank credits : {rupees(m['bank_extra'])}  (money in with no settlement)")

    # gate: never a confidently-wrong tie-out, and every reported rupee must be attributed.
    ok = (s["wrong"] == 0) and (m["residual"] == 0)
    print(f"\nthree-way gate (0 wrong, residual 0): {'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)
