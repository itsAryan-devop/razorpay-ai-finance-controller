# Build Log — what broke and how we recovered

> Razorpay explicitly asks in the pitch: "explain what broke during development and how you recovered."
> Log every real bug, dead end, and course-correction here from day 1. A believable failure story beats a clean narrative.
> Format: `## YYYY-MM-DD — short title` then what happened / why / fix.

## 2026-08-25 — Project kickoff
- Locked Track 04 (Finance Controller / reconciliation agent) after 4-stream research + a targeted verification sweep. Full reasoning in NOTES.md, roadmap in PLAN.md.
- Known open risk carried into day 1: test-mode settlements may not populate (test mode is the pre-KYC state; live settlement is KYC-gated). Spike script written to resolve this as the first GO/NO-GO. Fallback = synthetic settlement generator or pivot to T3, both pre-agreed.

## 2026-08-25 — Bug #1: UnicodeEncodeError on Windows console
- `check_settlements.py` printed emoji (✅/⚠️/❌) in the verdict; Windows default console codec is cp1252, which can't encode U+274C → `UnicodeEncodeError`, crashing the script *after* it had already printed the useful output.
- Fix: replaced emoji with ASCII tags `[GO]/[PARTIAL]/[NO-GO]`. Lesson noted for the whole project — this is a Windows dev box, keep stdout ASCII-safe (or set PYTHONIOENCODING=utf-8) rather than assuming UTF-8 terminals.

## 2026-08-25 — Spike baseline (pre-payment)
- Auth OK with test key. `/payments`, `/settlements`, `/settlements/recon/combined` all return HTTP 200 but empty (nothing paid yet). Endpoints reachable — good. 4 payment links created via API for the settlement test.
- Next: pay the 4 links with test card, wait for settlement, re-run `check` for the real GO/NO-GO.

## 2026-08-25 — Bug #2 / finding: generic Visa test card rejected as "international"
- Paying the link with `4111 1111 1111 1111` returned "International cards are not supported" on this Indian test account. Worked around via **Netbanking** test flow (pick any bank → demo bank page → Success), which is the most reliable test-mode capture path. Note for later if we need card-specific data: use Razorpay's documented *domestic* test cards, not the generic 4111.

## 2026-08-25 — ⚠️ SPIKE VERDICT: NO-GO on real test-mode settlements (this is the pre-agreed fallback, not a setback)
- Paid all 4 links (Netbanking → Success). Result: **4/4 payments captured, but `/settlements` and `/settlements/recon/combined` both stay empty (HTTP 200, 0 rows).**
- Confirms the research risk: test mode is pre-KYC; settlement is a live-money construct gated on KYC-verified accounts. Payments sit captured/on-hold but never settle in test mode.
- **Decision: hybrid synthetic approach.** Use REAL captured payments (real IDs, amounts, fees) as the ledger/payment side; SYNTHESIZE the settlement side calibrated to the real recon schema + real fee math. Fully valid — Track 4 wording is literally "50+ synthetic records." Bonus: a generator lets us plant the hard cases (partial settlement, refund-in-later-cycle, fee mismatch, duplicate) that test mode could never produce reliably anyway.

## 2026-08-25 — ⭐ Captured Razorpay's REAL test-mode fee formula (calibration constant)
- From the 4 real captured netbanking payments: **MDR = 2.2% of amount, GST = 18% on MDR**, so total fee = `amount × 0.022 × 1.18 ≈ amount × 0.02596`; net settlement = `amount − total_fee`.
- Verified exact on all 4: 600→15.58, 450→11.68, 300→7.78, 150→3.90.
- The synthetic settlement generator MUST use this real formula, not a guessed rate. This is a cheap, high-signal "we grounded it in real Razorpay economics" point for the README.

## 2026-08-25 — Day 2: data generator built + self-verified
- `src/generate_data.py` produces ledger.csv (120 merchant orders), settlements.csv (127 recon rows), ground_truth.csv (the answer key). All money in PAISE integers (never floats — a reconciler must be exact). Seed 42, reproducible.
- Plants 7 exception types on purpose: CLEAN(63), TIMING_VARIANCE(14), FEE_MISMATCH(8), REFUND_IN_LATER_CYCLE(12), DUPLICATE(5), MISSING_CREDIT(10), EXTRA_CREDIT(8). Uses the real fee formula above for clean cases.
- **Design finding:** real fees showed ±1 paise rounding vs the formula → the matcher needs a small fee tolerance (2 paise) even for "clean" matches; exact-equal fee matching would false-flag legit rows. This is itself a real reconciliation insight worth putting in the README.
- `src/selftest_data.py` asserts 8 invariants (missing-credit truly absent, duplicates truly 2x, fee formula holds, money conserved, refunds are debits, fee-mismatch really deviates, extra-credit has no ledger order, truth covers all orders). All PASS, exit 0. This is the guarantee that our "provable correctness" claim is real, not asserted.
- **Next (Day 3-4): the deterministic matcher** — pass 1 exact (payment_id+amount), pass 2 fuzzy (amount±fee-tolerance, date±window), pass 3 net-settlement decomposition; then classify the remainder into the typed exception queue and score against ground_truth.csv.
