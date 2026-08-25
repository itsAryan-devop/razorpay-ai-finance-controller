"""
generate_data.py — Hybrid data generator for the reconciliation agent (Track 04).

Produces three files in data/generated/:
  ledger.csv        the merchant's own books  (what they THINK happened)
  settlements.csv   Razorpay settlement recon rows (what Razorpay says settled)
  ground_truth.csv  the answer key (we planted every exception, so we KNOW)

WHY hybrid/synthetic: real Razorpay test-mode settlements never populate
(pre-KYC gating — confirmed by the day-1 spike, see LOG.md). Track 04 asks for
"50+ synthetic records", so we synthesize the settlement side, calibrated to the
REAL recon schema and the REAL fee economics measured on 2026-08-25:
    MDR 2.2% + 18% GST.

All money is in PAISE (integers). A reconciler must never use floats for money.

Exception taxonomy we plant (each row's true label lives in ground_truth.csv):
  CLEAN                 settles normally (matches within fee tolerance)
  TIMING_VARIANCE       settles outside the naive T+2 window -> needs date tolerance
  FEE_MISMATCH          recon fee differs from expected by > tolerance (data quality)
  REFUND_IN_LATER_CYCLE order refunded; refund debit lands in a later batch than sale
  DUPLICATE             same payment_id appears twice in recon (one real, one error)
  MISSING_CREDIT        captured in ledger but NEVER in any settlement (money not received)
  EXTRA_CREDIT          recon credit with no matching ledger order (unexplained money in)

Run:  py src/generate_data.py
"""
import csv
import os
import random
import datetime as dt

# ----------------------------------------------------------------------------- config
SEED = 42
N_ORDERS = 120                      # > 50 required; gives room for a held-out split later
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
START = dt.date(2026, 7, 1)         # orders spread across ~6 weeks
SPAN_DAYS = 42
FEE_TOLERANCE_PAISE = 2             # real fees showed +/-1 paise rounding vs formula (see LOG.md)

# exception mix (must sum to ~1.0). CLEAN dominates, like real life.
MIX = {
    "CLEAN":                 0.52,
    "TIMING_VARIANCE":       0.12,
    "FEE_MISMATCH":          0.07,
    "REFUND_IN_LATER_CYCLE": 0.10,
    "DUPLICATE":             0.04,
    "MISSING_CREDIT":        0.08,
    "EXTRA_CREDIT":          0.07,   # injected as recon rows with no ledger order
}


# ------------------------------------------------------------------- real fee economics
def razorpay_fee_paise(amount_paise: int) -> tuple[int, int]:
    """Returns (fee_base_paise, gst_paise). Calibrated to real test-mode netbanking:
    MDR 2.2%, GST 18% on MDR. Verified exact on 4 real payments (see LOG.md)."""
    fee_base = round(amount_paise * 0.022)
    gst = round(fee_base * 0.18)
    return fee_base, gst


def _uid(prefix: str, rng: random.Random, n: int = 14) -> str:
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return prefix + "".join(rng.choice(alpha) for _ in range(n))


def _settled_date(captured: dt.date, extra_days: int = 0) -> dt.date:
    """T+2 working-day settlement (naive: +2 calendar days here + optional skew)."""
    return captured + dt.timedelta(days=2 + extra_days)


def assign_labels(rng: random.Random) -> list[str]:
    labels = []
    for name, frac in MIX.items():
        labels += [name] * round(frac * N_ORDERS)
    # pad/trim to exactly N_ORDERS
    while len(labels) < N_ORDERS:
        labels.append("CLEAN")
    labels = labels[:N_ORDERS]
    rng.shuffle(labels)
    return labels


def generate():
    rng = random.Random(SEED)
    labels = assign_labels(rng)

    ledger_rows = []       # merchant books
    recon_rows = []        # razorpay settlement recon
    truth_rows = []        # answer key

    # settlement batches keyed by settled date -> (settlement_id, utr)
    batches: dict[dt.date, tuple[str, str]] = {}

    def batch_for(d: dt.date):
        if d not in batches:
            sid = _uid("setl_", rng)
            utr = str(rng.randint(10**11, 10**12 - 1)) + rng.choice("abcdefgh")
            batches[d] = (sid, utr)
        return batches[d]

    def add_recon(entity_id, rtype, amount, fee_base, gst, credit, debit,
                  settled_date, order_id="", method="netbanking"):
        sid, utr = batch_for(settled_date)
        recon_rows.append({
            "entity_id": entity_id,
            "type": rtype,                       # payment | refund | adjustment
            "amount": amount,
            "fee": fee_base + gst,
            "tax": gst,
            "credit": credit,
            "debit": debit,
            "settlement_id": sid,
            "settlement_utr": utr,
            "settled_at": settled_date.isoformat(),
            "order_id": order_id,
            "method": method,
        })

    for i, label in enumerate(labels):
        amount = rng.randint(100, 5000) * 100          # Rs 100..5000, in paise
        captured = START + dt.timedelta(days=rng.randint(0, SPAN_DAYS))
        pid = _uid("pay_", rng)
        oid = _uid("order_", rng)
        fee_base, gst = razorpay_fee_paise(amount)
        net = amount - fee_base - gst

        # every real order goes in the merchant ledger (their books)
        ledger_rows.append({
            "order_id": oid, "payment_id": pid, "amount": amount,
            "method": "netbanking", "captured_at": captured.isoformat(),
            "status": "captured",
        })

        note = ""
        truth_pid, truth_oid = pid, oid
        if label == "CLEAN":
            add_recon(pid, "payment", amount, fee_base, gst, net, 0,
                      _settled_date(captured), oid)

        elif label == "TIMING_VARIANCE":
            skew = rng.choice([2, 3, 4])               # settles late, beyond naive T+2
            add_recon(pid, "payment", amount, fee_base, gst, net, 0,
                      _settled_date(captured, skew), oid)
            note = f"settled T+{2+skew} instead of T+2"

        elif label == "FEE_MISMATCH":
            bad_fee = fee_base + rng.choice([-15, -10, 12, 20])   # data-quality fee error
            add_recon(pid, "payment", amount, bad_fee, gst, amount - bad_fee - gst, 0,
                      _settled_date(captured), oid)
            note = f"recon fee_base {bad_fee} vs expected {fee_base}"

        elif label == "REFUND_IN_LATER_CYCLE":
            # sale settles normally...
            add_recon(pid, "payment", amount, fee_base, gst, net, 0,
                      _settled_date(captured), oid)
            # ...then a refund debit lands in a LATER batch
            refund_amt = amount if rng.random() < 0.5 else amount // 2  # full or partial
            rid = _uid("rfnd_", rng)
            refund_date = _settled_date(captured, rng.randint(3, 8))
            add_recon(rid, "refund", refund_amt, 0, 0, 0, refund_amt, refund_date, oid)
            ledger_rows[-1]["status"] = "refunded"
            note = f"refund {refund_amt} in later cycle {refund_date.isoformat()}"

        elif label == "DUPLICATE":
            sd = _settled_date(captured)
            add_recon(pid, "payment", amount, fee_base, gst, net, 0, sd, oid)
            add_recon(pid, "payment", amount, fee_base, gst, net, 0, sd, oid)  # erroneous dup
            note = "same payment_id appears twice in recon"

        elif label == "MISSING_CREDIT":
            # in ledger, captured, but NO recon row at all -> money never received
            note = "captured in ledger but absent from all settlements"

        elif label == "EXTRA_CREDIT":
            # money arrives under an UNKNOWN payment id with no ledger order at all
            ledger_rows.pop()                              # this order never existed in the books
            ghost = _uid("pay_", rng)
            add_recon(ghost, "payment", amount, fee_base, gst, net, 0,
                      _settled_date(captured), "")         # no order_id -> unexplained
            truth_pid, truth_oid = ghost, ""
            note = "orphan recon credit, no ledger order (money in under unknown id)"

        truth_rows.append({
            "payment_id": truth_pid, "order_id": truth_oid, "amount": amount,
            "label": label, "note": note,
        })

    _write(OUT_DIR, ledger_rows, recon_rows, truth_rows)
    _summary(labels, ledger_rows, recon_rows)


def _write(out_dir, ledger_rows, recon_rows, truth_rows):
    os.makedirs(out_dir, exist_ok=True)
    def dump(name, rows):
        path = os.path.join(out_dir, name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return path
    dump("ledger.csv", ledger_rows)
    dump("settlements.csv", recon_rows)
    dump("ground_truth.csv", truth_rows)


def _summary(labels, ledger_rows, recon_rows):
    from collections import Counter
    c = Counter(labels)
    print(f"Generated {len(ledger_rows)} ledger orders, {len(recon_rows)} recon rows.")
    print(f"Seed {SEED} | fee tolerance {FEE_TOLERANCE_PAISE} paise | output in data/generated/")
    print("Exception mix (ground truth):")
    for k in MIX:
        print(f"  {k:<22} {c.get(k,0):>3}")


if __name__ == "__main__":
    generate()
