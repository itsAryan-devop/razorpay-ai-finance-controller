"""
selftest_data.py — invariant checks on the generated data vs its ground truth.

The whole Track-04 thesis is "correctness is provable because we own the answer
key." That only holds if the generator actually produces what ground_truth.csv
claims. This asserts that. Run it after every generate_data.py change.

Run:  py src/selftest_data.py     (exit 0 = all pass, 1 = something drifted)
"""
import csv
import collections
import os
import sys

D = os.path.join(os.path.dirname(__file__), "..", "data", "generated")


def _load():
    def rd(name):
        with open(os.path.join(D, name), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return rd("ledger.csv"), rd("settlements.csv"), rd("ground_truth.csv")


def expected_fee(amount_paise: int) -> int:
    base = round(amount_paise * 0.022)
    return base + round(base * 0.18)


def main() -> int:
    led, rec, tru = _load()
    truth = {t["payment_id"]: t["label"] for t in tru}
    ledger_pids = {l["payment_id"] for l in led}
    pay_count = collections.Counter(r["entity_id"] for r in rec if r["type"] == "payment")

    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    miss = [t["payment_id"] for t in tru if t["label"] == "MISSING_CREDIT"]
    check("MISSING_CREDIT absent from recon", all(pay_count[p] == 0 for p in miss))

    dup = [t["payment_id"] for t in tru if t["label"] == "DUPLICATE"]
    check("DUPLICATE appears exactly twice", all(pay_count[p] == 2 for p in dup))

    clean = [r for r in rec if r["type"] == "payment" and truth.get(r["entity_id"]) == "CLEAN"]
    check("CLEAN fee matches real Razorpay formula",
          all(int(r["fee"]) == expected_fee(int(r["amount"])) for r in clean))
    check("CLEAN net credit = amount - fee (money conserved)",
          all(int(r["credit"]) == int(r["amount"]) - int(r["fee"]) for r in clean))

    ref = [r for r in rec if r["type"] == "refund"]
    check("refunds recorded as debits, not credits",
          all(int(r["debit"]) > 0 and int(r["credit"]) == 0 for r in ref))

    fee_mm = [r for r in rec if r["type"] == "payment" and truth.get(r["entity_id"]) == "FEE_MISMATCH"]
    check("FEE_MISMATCH fees actually deviate from formula",
          all(int(r["fee"]) != expected_fee(int(r["amount"])) for r in fee_mm))

    extra = [r for r in rec if r["type"] == "payment" and r["order_id"] == ""]
    check("EXTRA_CREDIT recon rows have no ledger order",
          all(r["entity_id"] not in ledger_pids for r in extra))

    check("every ledger order has a ground-truth label",
          {l["payment_id"] for l in led} <= {t["payment_id"] for t in tru})

    ok = all(passed for _, passed in checks)
    for name, passed in checks:
        print(("PASS" if passed else "FAIL"), name)
    print("---", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
