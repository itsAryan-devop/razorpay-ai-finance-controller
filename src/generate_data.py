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
    "CLEAN":                 0.43,
    "TIMING_VARIANCE":       0.12,
    "FEE_MISMATCH":          0.07,
    "REFUND_IN_LATER_CYCLE": 0.10,
    "DUPLICATE":             0.04,
    "MISSING_CREDIT":        0.08,
    "EXTRA_CREDIT":          0.07,   # recon rows with no ledger order (truly unexpected money)
    "MISATTRIBUTED_CREDIT":  0.09,   # money in under a WRONG payment id -> needs fuzzy pairing
}

# Misattributed credits draw amounts from a small pool ON PURPOSE, so several share
# the same amount. That makes amount+date pairing genuinely AMBIGUOUS for a rules-only
# matcher (it can detect the misattribution but not always resolve which credit is whose)
# -> honest sub-100 numbers, and a real job for the LLM exception handler (Day 6).
COLLISION_AMOUNTS = [99900, 149900, 249900, 349900]   # paise


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


NAMES = ["Rhea Nair", "Arjun Rao", "Kavya Iyer", "Dev Mehta", "Sara Khan",
         "Vikram Bose", "Ira Shah", "Neel Gupta", "Tara Menon", "Om Verma",
         "Zoya Ali", "Kabir Jain", "Meera Das", "Rohan Sethi", "Anaya Roy"]


def make_customer(rng: random.Random) -> tuple[str, str]:
    """Returns (display_name, short_code). Code = initials + 3 digits, e.g. 'RN482'."""
    name = rng.choice(NAMES)
    code = "".join(w[0] for w in name.split()) + str(rng.randint(100, 999))
    return name, code


def noisy_hint(code: str, rng: random.Random) -> str:
    """A bank narration hint for a misattributed credit: usually the full code,
    sometimes just the initials — a fuzzy signal rules can't safely use but an
    LLM (or a text heuristic) can weigh. This is what makes the LLM handler earn
    its place on the escalated residue."""
    return code if rng.random() < 0.7 else code[:2]


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
                  settled_date, order_id="", method="netbanking", description=""):
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
            "description": description,          # free-text bank narration (noisy signal)
        })

    for i, label in enumerate(labels):
        if label == "MISATTRIBUTED_CREDIT":
            amount = rng.choice(COLLISION_AMOUNTS)     # forced collisions -> pairing ambiguity
        else:
            amount = rng.randint(100, 5000) * 100      # Rs 100..5000, in paise
        captured = START + dt.timedelta(days=rng.randint(0, SPAN_DAYS))
        pid = _uid("pay_", rng)
        oid = _uid("order_", rng)
        cust_name, code = make_customer(rng)
        fee_base, gst = razorpay_fee_paise(amount)
        net = amount - fee_base - gst

        # every real order goes in the merchant ledger (their books)
        ledger_rows.append({
            "order_id": oid, "payment_id": pid, "amount": amount,
            "method": "netbanking", "captured_at": captured.isoformat(),
            "status": "captured", "customer": f"{cust_name} ({code})",
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

        elif label == "MISATTRIBUTED_CREDIT":
            # money DID arrive, but the settlement attributes it to a ghost payment id.
            # real order stays in the ledger; the matching credit hides under `ghost`.
            # its bank narration carries a NOISY hint of the true customer code.
            ghost = _uid("pay_", rng)
            add_recon(ghost, "payment", amount, fee_base, gst, net, 0,
                      _settled_date(captured, rng.choice([0, 1])), "",
                      description=f"NEFT/{noisy_hint(code, rng)}")
            note = f"true_match={ghost}"                   # answer key for the pairing task

        truth_rows.append({
            "payment_id": truth_pid, "order_id": truth_oid, "amount": amount,
            "label": label, "note": note,
        })

    _write(OUT_DIR, ledger_rows, recon_rows, truth_rows)
    _summary(labels, ledger_rows, recon_rows)
    generate_batches(OUT_DIR)
    generate_formats(OUT_DIR)


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


BATCH_SEED = 4242            # independent RNG: batch fixture is purely ADDITIVE — it does
                             # NOT touch the seed-42 core dataset or any of its numbers.


def _net(amount_paise: int) -> int:
    base, gst = razorpay_fee_paise(amount_paise)
    return amount_paise - base - gst


def generate_batches(out_dir):
    """Many-to-one fixture: lump settlement credits that each pay out a BATCH of orders
    (no per-order recon row). Written to *_batch.csv, separate from the 1:1 core so it
    never disturbs existing metrics. Includes one DELIBERATELY AMBIGUOUS batch where two
    different order-subsets sum to the same credit — the matcher must escalate it, not
    guess. Deterministic (BATCH_SEED)."""
    rng = random.Random(BATCH_SEED)
    ledger, recon, truth = [], [], []
    base_day = dt.date(2026, 7, 10)
    _batch_no = [0]              # spaces batches 15 days apart so the date window never
                                # pools orders across two different settlements

    def add_batch(order_amounts, ambiguous_extra=None):
        """order_amounts: gross paise for the TRUE member orders. ambiguous_extra: gross
        paise for decoy orders that create a second subset summing to the same credit."""
        sid = _uid("setl_", rng)
        utr = str(rng.randint(10**11, 10**12 - 1)) + rng.choice("abcdefgh")
        captured = base_day + dt.timedelta(days=15 * _batch_no[0])
        _batch_no[0] += 1
        settled = _settled_date(captured, rng.choice([0, 1]))
        member_pids = []
        for amt in order_amounts:
            name, code = make_customer(rng)
            pid, oid = _uid("pay_", rng), _uid("order_", rng)
            ledger.append({"order_id": oid, "payment_id": pid, "amount": amt,
                           "method": "netbanking", "captured_at": captured.isoformat(),
                           "status": "captured", "customer": f"{name} ({code})"})
            member_pids.append(pid)
            truth.append({"payment_id": pid, "settlement_id": sid, "amount": amt})
        for amt in (ambiguous_extra or []):        # decoys: real orders, NOT in this credit
            name, code = make_customer(rng)
            pid, oid = _uid("pay_", rng), _uid("order_", rng)
            ledger.append({"order_id": oid, "payment_id": pid, "amount": amt,
                           "method": "netbanking", "captured_at": captured.isoformat(),
                           "status": "captured", "customer": f"{name} ({code})"})
            # decoys have no true settlement here — truth maps them to '' (unsettled)
            truth.append({"payment_id": pid, "settlement_id": "", "amount": amt})
        credit = sum(_net(a) for a in order_amounts)
        recon.append({"entity_id": sid, "type": "settlement", "credit": credit,
                      "settlement_id": sid, "settlement_utr": utr,
                      "settled_at": settled.isoformat(),
                      "n_orders": len(order_amounts)})

    # 4 clean batches of varying size (net sums are unique -> unique subset)
    add_batch([120000, 250000, 90000])
    add_batch([340000, 175000])
    add_batch([80000, 80000, 80000, 80000])        # equal amounts, still one subset = all four
    add_batch([210000, 330000, 145000, 260000])
    # 1 ambiguous batch: credit = net(300000). Decoys net(120000)+net(180000) also sum to it
    # (net is linear here: net(a)+net(b) != net(a+b) exactly, so pick amounts whose NETS add
    # up — use amounts where the fee rounding lines up). Simplest robust ambiguity: two TRUE
    # members whose nets equal a third decoy's net individually is hard; instead give two
    # equal-net decoys that reproduce the members' combined net.
    a = 200000
    b = 200000
    add_batch([a, b], ambiguous_extra=[a, b])      # {oA,oB} and {decoyA,decoyB} both sum equal

    _write_batch(out_dir, ledger, recon, truth)
    print(f"Batch fixture: {len(ledger)} orders across {len(recon)} lump settlements "
          f"(incl. 1 ambiguous) | output in data/generated/*_batch.csv")


def _write_batch(out_dir, ledger, recon, truth):
    def dump(name, rows):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    dump("ledger_batch.csv", ledger)
    dump("settlements_batch.csv", recon)
    dump("ground_truth_batch.csv", truth)


# =========================================================================================
# Format-level held-out fixture — vary the bank-narration FORMAT, not the RNG seed.
#
# The seed-based held-out (eval_holdout.py) proves the rules aren't overfit to one random
# DRAW. But the narration-reading rule (_similarity: does the customer code appear in the
# credit's description?) was written against exactly ONE narration style: "NEFT/{code}".
# Real banks emit dozens of narration formats. This fixture renders the SAME misattribution
# pairing task under several formats — one the rule was tuned on ("seen") and several it was
# never tuned on ("held-out") — so we can measure how the deterministic reader degrades on
# unseen formats and where the normalized reader / LLM recover it.
#
# Purely ADDITIVE: independent seed, own *_formats.csv files. The seed-42 core is untouched.
# Every case is a MISATTRIBUTED_CREDIT with a COLLIDING amount (so the matcher must escalate
# to the narration reader rather than pairing by amount alone) — narration is the ONLY signal.
# =========================================================================================
FORMAT_SEED = 20260904
FORMAT_N = 12               # misattribution cases per format
FORMAT_GROUP = 3           # cases per colliding-amount group (>=2 forces escalation)
FORMAT_AMOUNTS = [119900, 189900, 279900, 359900]   # paise; grouped to force collisions


def _spread_code(code: str) -> str:
    return " ".join(code)                              # "RN482" -> "R N 4 8 2"


# name -> (renderer(code, name) -> narration, is_seen). "seen" = the format the strict
# code-in-description rule was written against. All others are held-out (never tuned on).
NARRATION_FORMATS = {
    "dev_neft":   (lambda code, name: f"NEFT/{code}",                     True),
    "lower_imps": (lambda code, name: f"imps/{code.lower()} settlement",  False),  # casing
    "spaced":     (lambda code, name: f"NEFT CR {_spread_code(code)}",    False),  # separators
    "hyphen_upi": (lambda code, name: f"UPI-{code[:2]}-{code[2:]}-CR",    False),  # delimiters
    "name_only":  (lambda code, name: f"NEFT CR {name.upper()}",          False),  # no code at all
}


def generate_formats(out_dir=OUT_DIR):
    """One fixture per narration format. Each is a self-contained ledger + settlements +
    ground-truth trio (ledger_{fmt}.csv, settlements_{fmt}.csv) plus a shared
    ground_truth_formats.csv keyed (format, payment_id) -> true settlement credit id.
    Deterministic (FORMAT_SEED). The pairing task is identical across formats; only the
    narration rendering differs, so any accuracy gap between formats is caused purely by
    the narration format, not by a harder underlying problem."""
    rng = random.Random(FORMAT_SEED)
    truth_rows = []
    base_day = dt.date(2026, 7, 5)

    for fmt, (render, _seen) in NARRATION_FORMATS.items():
        ledger, recon = [], []
        # Cases are built in colliding GROUPS: every member of a group shares BOTH the amount
        # AND the capture date, so all their ghost credits fall inside each order's pairing
        # window at once. That forces the deterministic matcher to ESCALATE the whole group
        # (amount+date alone can't disambiguate) and hand it to the narration reader — which
        # is the only signal that differs. Without shared dates the matcher would auto-pair
        # each by amount+date and the narration format would never be exercised.
        for g in range(FORMAT_N // FORMAT_GROUP):
            amount = FORMAT_AMOUNTS[g % len(FORMAT_AMOUNTS)]
            captured = base_day + dt.timedelta(days=rng.randint(0, 20))
            fee_base, gst = razorpay_fee_paise(amount)
            net = amount - fee_base - gst
            for _k in range(FORMAT_GROUP):
                pid, oid = _uid("pay_", rng), _uid("order_", rng)
                name, code = make_customer(rng)
                ledger.append({"order_id": oid, "payment_id": pid, "amount": amount,
                               "method": "netbanking", "captured_at": captured.isoformat(),
                               "status": "captured", "customer": f"{name} ({code})"})
                # its money settled under a GHOST id; narration carries the signal in THIS format
                ghost = _uid("pay_", rng)
                sid = _uid("setl_", rng)
                utr = str(rng.randint(10**11, 10**12 - 1)) + rng.choice("abcdefgh")
                settled = _settled_date(captured, rng.choice([0, 1]))
                recon.append({
                    "entity_id": ghost, "type": "payment", "amount": amount,
                    "fee": fee_base + gst, "tax": gst, "credit": net, "debit": 0,
                    "settlement_id": sid, "settlement_utr": utr,
                    "settled_at": settled.isoformat(), "order_id": "",
                    "method": "netbanking", "description": render(code, name),
                })
                truth_rows.append({"format": fmt, "payment_id": pid,
                                   "true_settlement": ghost, "amount": amount, "code": code})
        _write_format(out_dir, fmt, ledger, recon)

    _write_format_truth(out_dir, truth_rows)
    print(f"Format held-out fixture: {len(NARRATION_FORMATS)} narration formats x "
          f"{FORMAT_N} misattribution cases | output in data/generated/*_formats.csv")


def _write_format(out_dir, fmt, ledger, recon):
    def dump(name, rows):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    dump(f"ledger_{fmt}.csv", ledger)
    dump(f"settlements_{fmt}.csv", recon)


def _write_format_truth(out_dir, truth_rows):
    with open(os.path.join(out_dir, "ground_truth_formats.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(truth_rows[0].keys()))
        w.writeheader()
        w.writerows(truth_rows)


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
