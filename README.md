# AI Finance Controller — Settlement Reconciliation Agent

> Razorpay AI Buildathon 2026 · **Track 04 (AI Finance Controller)** · solo submission

An agent that reconciles Razorpay settlement data against a merchant's own sales ledger,
reports an **honest match rate and a typed exception queue**, and uses an LLM *only* to
resolve the ambiguous residue the rules refuse to guess — never to do arithmetic.
Every money-affecting decision is **explainable, bounded, and gated**.

## Headline results (deterministic baseline + handler)
*Reproduce: `py src/generate_data.py && py src/matcher.py && py src/pipeline.py`*

| metric | value |
|---|---|
| classification accuracy | **0.976** (120/123) |
| reconciliation match rate | **0.911** (102/112 orders tied to a settlement) |
| misattribution pairing (rules → +handler) | **8/11 → 11/11** |
| routing | deterministic escalates ambiguity; handler auto-applies only high-confidence |

The accuracy is deliberately **not** 100%. On self-generated data a perfect score would
just prove the matcher inverts the generator — a tell, not an achievement. The honest
difficulty lives in **misattributed credits** (money that settled under the wrong payment
id) whose amounts collide; the matcher escalates those rather than guessing, and the
handler resolves them with a confidence-gated, audited decision. Full numbers: [RESULTS.md](RESULTS.md).

## The problem
A single bank settlement credit hides dozens of transactions, fees, refunds, and timing
skew. Payment date, capture date, settlement date, and bank-posting date are four different
dates; refunds land in later cycles; fees carry GST that must be separable for input-tax
credit. Manual reconciliation is slow and error-prone — this closes the loop with measured
accuracy and an honest exception list.

## How it works
```
 ledger (merchant books) + Razorpay settlement recon rows
                         │
        ┌────────────────▼─────────────────┐
        │ DETERMINISTIC MATCHER (no LLM)     │  exact id match → money-conservation
        │                                    │  guard → fuzzy fee/timing → pairing
        └────────────────┬─────────────────┘
             matched ◄───┤───► typed exception queue
                         │     MISSING · DUPLICATE · FEE_MISMATCH · TIMING ·
                         │     REFUND_IN_LATER_CYCLE · EXTRA · MISATTRIBUTED
                         │  (ambiguous collisions → ESCALATE, not a guess)
        ┌────────────────▼─────────────────┐
        │ EXCEPTION HANDLER (LLM or heuristic)│  reads a fuzzy narration signal,
        │                                    │  proposes a pairing + confidence +
        │                                    │  justification. Code does the math.
        └────────────────┬─────────────────┘
        ┌────────────────▼─────────────────┐
        │ GUARDRAILS: dry-run default ·      │  only high-confidence AUTO_RESOLVE
        │ confidence-gated · hash-chained    │  applies with --execute; the rest
        │ append-only audit log              │  waits for a human.
        └────────────────────────────────────┘
```
Design principle (from Razorpay's own engineering blog and the reconciliation literature):
**the LLM reads; deterministic code does the math.** An LLM must never arithmetic a ledger.

## Run it
```bash
pip install -r requirements.txt
py src/generate_data.py      # deterministic synthetic data (seed 42), calibrated to
                             # real Razorpay test-mode fees (MDR 2.2% + 18% GST)
py src/selftest_data.py      # 9 ground-truth invariants
py src/matcher.py            # deterministic baseline + per-class metrics + exceptions.csv
py src/pipeline.py           # end-to-end: matcher → handler → before/after + audit log
py src/pipeline.py --execute # apply high-confidence auto-resolutions (gated)
pytest -q                    # 12 tests
```
The LLM path activates when `ANTHROPIC_API_KEY` is set in `.env`; otherwise a transparent
text-similarity heuristic runs so the pipeline and CI work with no key.

Data is synthetic because **real Razorpay test-mode settlements never populate** (test mode
is the pre-KYC state — verified by a day-1 spike, see [LOG.md](LOG.md)). The generator is
calibrated to real economics measured from real test payments, and the track brief itself
asks for "50+ synthetic records."

## Guardrails — every money action explainable, bounded, gated
- **Explainable** — every decision carries a human-readable justification, confidence, and
  the evidence it used; all written to a **tamper-evident, SHA-256 hash-chained** audit log
  (`src/audit.py`; editing history breaks the chain — there's a test that proves it).
- **Bounded** — the deterministic matcher escalates genuine ambiguity instead of guessing;
  the handler applies a confidence gate (AUTO_RESOLVE ≥ 0.75, FLAG ≥ 0.45, else escalate).
- **Gated** — **dry-run by default**; only high-confidence auto-resolutions apply, and only
  with `--execute`. Everything else waits for a human.

This maps directly onto **RBI FREE-AI** (the RBI framework for AI in finance): Accountability
and Understandable-by-Design (the audit trail + justifications), and humans retaining final
authority (the gate). Razorpay is an RBI-regulated payment aggregator; these are not optional.

## What broke, and how we recovered
Kept honestly in [LOG.md](LOG.md) from day one — e.g. the day-1 spike proving test-mode
settlements don't populate (→ pivot to calibrated synthetic), a Windows console encoding
crash, and the moment the matcher scored a tautological 100% and we redesigned the data to
inject real ambiguity. The test suite now asserts accuracy `< 1.0` so the tautology can't
silently return.

## What this does NOT do (honest limits)
- Synthetic data (real test-mode settlements are KYC-gated); calibrated to real fees, but not
  real settlement volume or real bank narrations.
- Timing uses calendar days, not working-day/holiday calculation — noted in the matcher.
- The real-LLM path is wired and fallback-tested but **not yet validated live** (pending an
  API key); the reported numbers are the keyless heuristic.
- It reconciles and proposes; it does not move money.

## Repo layout
```
src/generate_data.py   synthetic data + ground-truth answer key (seed 42)
src/selftest_data.py   9 data-integrity invariants
src/matcher.py         deterministic 3-pass matcher + typed exception queue
src/llm_handler.py     LLM/heuristic resolver for the escalated residue
src/pipeline.py        end-to-end run + guardrails + audit log
src/audit.py           append-only hash-chained audit log
tests/                 12 pytest cases (run in CI on every push)
NOTES.md PLAN.md LOG.md RESULTS.md   context, roadmap, failure trail, metrics
research/              the 4 research reports the design is grounded in
```
