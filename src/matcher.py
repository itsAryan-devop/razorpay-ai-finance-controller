"""
matcher.py — deterministic reconciliation matcher (Track 04 core engine).

Reconciles the merchant ledger against Razorpay settlement recon rows using
DETERMINISTIC passes only. No LLM here by design — the LLM handles only the
residual exception tail later (Day 6). Every money number is computed by code.

Passes:
  1. exact       payment recon row whose entity_id == ledger payment_id
  2. fuzzy       fee within tolerance (real fees round +/-1 paise) and
                 settlement within the expected T+2 window
  3. decompose   money-conservation guard: credit == amount - fee

Classification precedence per ledger order (mutually exclusive by construction):
  MISSING_CREDIT > DUPLICATE > REFUND_IN_LATER_CYCLE > FEE_MISMATCH
  > TIMING_VARIANCE > CLEAN
Recon payment rows that match no ledger order  ->  EXTRA_CREDIT.

Output: a list of Result records (one per reconciled entity) with evidence, and
- when run directly - a scoring report vs ground_truth.csv plus exceptions.csv.

Run:  py src/matcher.py
"""
import csv
import os
import datetime as dt
from dataclasses import dataclass, field

D = os.path.join(os.path.dirname(__file__), "..", "data", "generated")

FEE_TOLERANCE_PAISE = 2      # real test-mode fees rounded +/-1 paise vs formula (LOG.md)
ONTIME_MAX_DAYS = 2          # T+2. NOTE: synthetic data ignores weekends; a real
                             # deployment must use working-day math, not calendar days.

EXCEPTION_LABELS = [
    "CLEAN", "TIMING_VARIANCE", "FEE_MISMATCH", "REFUND_IN_LATER_CYCLE",
    "DUPLICATE", "MISSING_CREDIT", "EXTRA_CREDIT", "MISATTRIBUTED_CREDIT",
]

PAIR_WINDOW_DAYS = 4         # an orphan credit can pair with an order settled within this window


def expected_total_fee(amount_paise: int) -> int:
    """Razorpay total fee (MDR 2.2% + 18% GST), calibrated to real test payments."""
    base = round(amount_paise * 0.022)
    return base + round(base * 0.18)


@dataclass
class Result:
    entity_id: str
    label: str
    matched_settlement_id: str = ""
    reason: str = ""
    route: str = "AUTO"            # AUTO (resolved) | ESCALATE (needs human/LLM) | FLAG
    matched_entity: str = ""       # the paired counterpart id, when applicable
    evidence: dict = field(default_factory=dict)


def _load():
    def rd(name):
        with open(os.path.join(D, name), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return rd("ledger.csv"), rd("settlements.csv")


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def reconcile(ledger, recon) -> list[Result]:
    # index recon rows
    pay_by_pid: dict[str, list[dict]] = {}
    refunds_by_oid: dict[str, list[dict]] = {}
    for r in recon:
        if r["type"] == "payment":
            pay_by_pid.setdefault(r["entity_id"], []).append(r)
        elif r["type"] == "refund":
            refunds_by_oid.setdefault(r["order_id"], []).append(r)

    ledger_pids = {l["payment_id"] for l in ledger}
    results: list[Result] = []
    unmatched: list[dict] = []       # deferred: could be MISSING_CREDIT or MISATTRIBUTED

    for l in ledger:
        pid, oid = l["payment_id"], l["order_id"]
        amount = int(l["amount"])
        captured = _date(l["captured_at"])
        matches = pay_by_pid.get(pid, [])
        refunds = refunds_by_oid.get(oid, [])

        if not matches:
            unmatched.append(l)                       # decide after the pairing pass
            continue

        if len(matches) > 1:
            results.append(Result(pid, "DUPLICATE", matches[0]["settlement_id"],
                reason=f"payment id appears {len(matches)}x in settlements",
                evidence={"count": len(matches)}))
            continue

        row = matches[0]
        sid = row["settlement_id"]

        # pass 3: money-conservation guard (should always hold; flags data corruption)
        if int(row["credit"]) != amount - int(row["fee"]):
            results.append(Result(pid, "FEE_MISMATCH", sid,
                reason="credit != amount - fee (money not conserved)",
                evidence={"amount": amount, "fee": int(row["fee"]),
                          "credit": int(row["credit"])}))
            continue

        if refunds:
            tot = sum(int(r["debit"]) for r in refunds)
            results.append(Result(pid, "REFUND_IN_LATER_CYCLE", sid,
                reason=f"{len(refunds)} refund(s) totalling {tot} in a later cycle",
                evidence={"refund_total": tot,
                          "refund_settlements": [r["settlement_id"] for r in refunds]}))
            continue

        exp = expected_total_fee(amount)
        if abs(int(row["fee"]) - exp) > FEE_TOLERANCE_PAISE:
            results.append(Result(pid, "FEE_MISMATCH", sid,
                reason=f"fee {row['fee']} vs expected {exp} (> {FEE_TOLERANCE_PAISE}p tol)",
                evidence={"fee": int(row["fee"]), "expected_fee": exp}))
            continue

        delta = (_date(row["settled_at"]) - captured).days
        if delta > ONTIME_MAX_DAYS:
            results.append(Result(pid, "TIMING_VARIANCE", sid,
                reason=f"settled T+{delta} (expected <= T+{ONTIME_MAX_DAYS})",
                evidence={"settled_days": delta}))
            continue

        results.append(Result(pid, "CLEAN", sid,
            reason="exact match, fee and timing within tolerance",
            evidence={"amount": amount, "settled_days": delta}))

    # ---- fuzzy pairing pass: explain unmatched orders with orphan credits ----
    # An orphan is a settlement credit whose payment id is not in the ledger. An
    # unmatched order may be MISATTRIBUTED (its money arrived under an orphan id) or
    # genuinely MISSING. We pair by amount + settlement window. On collisions we do
    # NOT guess -> we ESCALATE, which is the honest deterministic answer and the exact
    # residue the LLM handler works on (Day 6).
    orphans = [r for opid, rows in pay_by_pid.items() if opid not in ledger_pids
               for r in rows]
    consumed: set[int] = set()

    for l in unmatched:
        pid = l["payment_id"]
        amount = int(l["amount"])
        captured = _date(l["captured_at"])
        cands = [r for r in orphans if id(r) not in consumed
                 and int(r["amount"]) == amount
                 and 0 <= (_date(r["settled_at"]) - captured).days <= PAIR_WINDOW_DAYS]
        if len(cands) == 1:
            r = cands[0]
            consumed.add(id(r))
            results.append(Result(pid, "MISATTRIBUTED_CREDIT", r["settlement_id"],
                route="AUTO", matched_entity=r["entity_id"],
                reason=f"paired to orphan credit {r['entity_id']} by amount+date",
                evidence={"amount": amount}))
        elif len(cands) > 1:
            results.append(Result(pid, "MISATTRIBUTED_CREDIT", "",
                route="ESCALATE",
                reason=f"ambiguous: {len(cands)} orphan credits match amount+window",
                evidence={"amount": amount, "candidates": [c["entity_id"] for c in cands]}))
        else:
            results.append(Result(pid, "MISSING_CREDIT", "",
                reason="captured in ledger but no settlement credit found",
                evidence={"amount": amount}))

    # orphan credits never paired -> genuinely unexpected money
    for r in orphans:
        if id(r) not in consumed:
            results.append(Result(r["entity_id"], "EXTRA_CREDIT", r["settlement_id"],
                reason="settlement credit with no matching ledger order",
                evidence={"amount": int(r["amount"]), "order_id": r["order_id"]}))

    return results


# --------------------------------------------------------------------------- scoring
def _load_truth():
    with open(os.path.join(D, "ground_truth.csv"), encoding="utf-8") as f:
        return {t["payment_id"]: t["label"] for t in csv.DictReader(f)}


def score(results: list[Result], truth: dict[str, str]):
    pred = {r.entity_id: r.label for r in results}
    keys = set(truth) | set(pred)

    # per-class precision/recall
    print(f"{'label':<22}{'prec':>7}{'recall':>8}{'support':>9}")
    macro_p = macro_r = 0.0
    for L in EXCEPTION_LABELS:
        tp = sum(1 for k in keys if truth.get(k) == L and pred.get(k) == L)
        fp = sum(1 for k in keys if pred.get(k) == L and truth.get(k) != L)
        fn = sum(1 for k in keys if truth.get(k) == L and pred.get(k) != L)
        support = tp + fn
        p = tp / (tp + fp) if (tp + fp) else 1.0
        r = tp / (tp + fn) if (tp + fn) else 1.0
        macro_p += p
        macro_r += r
        print(f"{L:<22}{p:>7.2f}{r:>8.2f}{support:>9}")
    n = len(EXCEPTION_LABELS)
    print(f"{'MACRO AVG':<22}{macro_p/n:>7.2f}{macro_r/n:>8.2f}")

    correct = sum(1 for k in keys if truth.get(k) == pred.get(k))
    acc = correct / len(keys)
    # reconciliation match rate: ledger orders tied to a settlement (not missing)
    ledger_keys = [k for k in truth if truth[k] != "EXTRA_CREDIT"]
    matched = sum(1 for k in ledger_keys if pred.get(k) not in (None, "MISSING_CREDIT"))
    print(f"\nclassification accuracy : {acc:.3f}  ({correct}/{len(keys)})")
    print(f"reconciliation match rate: {matched/len(ledger_keys):.3f}  "
          f"({matched}/{len(ledger_keys)} ledger orders tied to a settlement)")

    from collections import Counter
    routes = Counter(r.route for r in results)
    print("routing: " + "  ".join(f"{k}={v}" for k, v in sorted(routes.items())))

    # confusion (only mismatches)
    mism = [(k, truth.get(k), pred.get(k)) for k in keys if truth.get(k) != pred.get(k)]
    print(f"misclassified: {len(mism)}")
    for k, t, p in mism[:12]:
        print(f"   {k}: truth={t} pred={p}")


def write_exceptions(results: list[Result]):
    path = os.path.join(D, "exceptions.csv")
    rows = [r for r in results if r.label != "CLEAN"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "exception_type", "settlement_id", "reason"])
        for r in rows:
            w.writerow([r.entity_id, r.label, r.matched_settlement_id, r.reason])
    print(f"\nwrote {len(rows)} exceptions to data/generated/exceptions.csv")


def pairing_report(results: list[Result]):
    """Did we pair each misattributed order to the RIGHT orphan credit?"""
    notes = {}
    with open(os.path.join(D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    mis = [r for r in results if r.entity_id in notes]
    resolved = [r for r in mis if r.route == "AUTO"]
    correct = sum(1 for r in resolved if r.matched_entity == notes[r.entity_id])
    escalated = sum(1 for r in mis if r.route == "ESCALATE")
    print(f"\nmisattribution pairing: {len(mis)} cases | {len(resolved)} auto-paired "
          f"({correct} to the correct credit) | {escalated} escalated as ambiguous")
    print("  -> the escalated cases are exactly the residue the LLM handler (Day 6) works on.")


if __name__ == "__main__":
    ledger, recon = _load()
    results = reconcile(ledger, recon)
    print(f"reconciled {len(ledger)} ledger orders + {len(recon)} recon rows "
          f"-> {len(results)} results\n")
    score(results, _load_truth())
    pairing_report(results)
    write_exceptions(results)
