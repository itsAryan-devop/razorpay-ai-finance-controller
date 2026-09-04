# AI Finance Controller — Settlement Reconciliation Agent

> Razorpay AI Buildathon 2026 · **Track 04 (AI Finance Controller)** · solo submission

An agent that reconciles Razorpay settlement data against a merchant's own sales ledger,
reports an **honest match rate and a typed exception queue**, and uses an LLM *only* to
resolve the ambiguous residue the rules refuse to guess — never to do arithmetic.
Every money-affecting decision is **explainable, bounded, and gated**.

> Track 04's own evaluation bar, quoted verbatim from [razorpay.com/buildathon](https://razorpay.com/buildathon/):
> **"Throughput plus measured accuracy plus an honest exception list. One cherry-picked
> match proves nothing."** This submission is built to that exact bar — see the throughput
> figure and the [held-out, 5-seed generalization table](RESULTS.md#held-out-generalization-the-rules-arent-overfit-to-seed-42)
> below, not a single cherry-picked run.

## Headline results (deterministic baseline + handler)
*Reproduce: `py src/generate_data.py && py src/matcher.py && py src/pipeline.py`*

| metric | dev seed (42) | held-out (4 unseen seeds) |
|---|---|---|
| classification accuracy | **0.976** (120/123) | **0.992** mean (0.984 min) |
| reconciliation match rate | **0.911** (102/112 orders tied to a settlement) | 0.911 (structural) |
| misattribution pairing (rules → +handler) | **8/11 → 11/11** | — |
| **wrong matches** | **0** | **0** |
| batch settlement (many-to-one) | **4/5 resolved · 1 escalated · 0 wrong** | — |
| three-way tie-out (ledger·Razorpay·bank) | **15/16 classified · 1 escalated · 0 wrong · residual ₹0** | — |
| routing | deterministic escalates ambiguity; handler auto-applies only high-confidence | |

**The dev seed is the *hardest* of the five** — most colliding credits, most escalations —
so the headline is the conservative number, not a cherry-picked one. `wrong matches` is an
**absolute count, never averaged into an accuracy figure**: a confidently wrong pairing is
a different kind of failure from an honest escalation, and averaging the two hides exactly
the number that matters for money. Reproduce the held-out column: `py src/eval_holdout.py`.

**Every rupee is attributed.** Of **₹281,973.00** in the ledger: **₹251,431.00** tied to a
settlement (102 orders), **₹30,542.00** never settled (10 orders — money the merchant is
owed), **unattributed residual ₹0.00**. Plus **₹15,692.00** across 8 orphan credits that
arrived with no ledger order behind them. The residual is *reported, not asserted away*, so
a future bug surfaces as a number instead of hiding — and a test enforces it stays zero.

**Confidence is graded, not asserted** — every handler decision is bucketed by confidence
band and scored against the answer key, so the routing thresholds are justified by measured
accuracy. Ungradeable rows are excluded rather than counted as wins (an empty band reads
`n/a`, never a fabricated `1.00`).

**Held out two ways.** The rules aren't overfit to the seed-42 *draw* (5-seed table above)
and the narration reader isn't overfit to one bank *format*: the same pairing task rendered
in unseen narration formats collapses the as-tuned reader from 1.00 to **0.25**, while the
shipped normalized reader recovers to **0.75** deterministically — 0 wrong, formats it can't
read escalate rather than guess. See [format-level held-out](RESULTS.md#format-level-held-out-the-reader-isnt-overfit-to-one-bank-narration-format).

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
Plus a **many-to-one leg**: real settlements pay out a batch of orders in one lump credit,
reconciled by a bounded **subset-sum search** (ambiguous batches escalate, never guess).

And a **three-way leg**: "Razorpay reported a payout" is not "the money is in my bank." A
bank-statement leg ties **ledger expected == Razorpay reported == bank received**, joined by
**UTR**, surfacing money in transit, short bank credits, gateway-withheld funds, and credits
under a mismatched UTR (escalated). Every reported rupee is attributed with a zero residual.

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
py src/eval_guard.py         # reproducible guard-safety metric vs a worst-case adversarial model
py src/eval_holdout.py       # seed-level held-out: rules aren't overfit to the seed-42 draw
py src/eval_formats.py       # format-level held-out: narration reader generalizes across bank formats
py src/threeway.py           # three-way tie-out: ledger vs Razorpay vs bank statement (by UTR)
py src/demo_refusals.py      # scripted demo: 4 out-of-policy actions, all refused
pytest -q                    # 79 tests (adversarial guard, refusals, money attr., batch + format + three-way)
streamlit run app.py         # dashboard + exception queue + audit viewer + LLM trace
```
The LLM path activates when a provider is available; otherwise a transparent
text-similarity heuristic runs so the pipeline and CI work with no key and no server.

### Local LLM via Ollama — free, no key
The "real LLM" path runs at **zero cost on a local model** — no API key, no quota, no
rate limits. On a 4GB-VRAM GPU (e.g. RTX 3050), `qwen3:4b` fits fully on-GPU and is strong
at structured JSON.
```bash
# 1. install Ollama (https://ollama.com/download), then:
ollama pull qwen3:4b            # ~2.5 GB
ollama serve                    # or just run the Ollama app; serves on 127.0.0.1:11434
# 2. run the pipeline — it auto-detects the local server:
py src/pipeline.py              # audit log shows engine=ollama on the resolved cases
```
Provider is chosen by `LLM_PROVIDER` (`auto` default → Ollama if running, else Anthropic if
keyed, else heuristic). Alternatives for a 4GB card: `OLLAMA_MODEL=phi4-mini` or `qwen3.5:2b`.
**Any failure — no server, timeout, bad JSON — falls back to the heuristic**, so a keyless,
server-less run (including CI) never breaks. The UI renders on the fast heuristic for
responsiveness; the local-LLM path is shown via the CLI and appears in the persisted audit
chain.

## UI (Streamlit)
`app.py` is a thin, honest read-layer over the same engine — it runs `pipeline.run()`
**in-process on every render**, so every number on screen is recomputed live, never
hardcoded. Four views:
- **Dashboard** — headline metrics (accuracy, match rate, misattribution pairing before→after,
  **wrong matches as an absolute count**, throughput), the **money-impact panel** (ledger value
  split into settled / never-settled with an unattributed residual of ₹0.00), the
  **confidence-calibration table** (empirical accuracy per band, graded against the answer
  key), the exception mix, per-class precision/recall, and the EXTRA_CREDIT queue
  precision lift (0.73 → 1.00 after the handler pairs the colliding credits), and the
  **batch settlement (many-to-one) panel** (lump credits resolved to their order-set, ambiguous ones escalated).
- **Exception queue** — the typed queue, filterable by type and route, plus the
  escalated→handler decisions with their confidence and justification.
- **Audit log** — the hash-chained entries with a live **"Verify chain integrity"** button
  that recomputes the SHA-256 chain, and the dry-run/execute gate exposed as a guarded button
  (only high-confidence AUTO_RESOLVE applies, behind an explicit confirm).
- **LLM Decision Trace** — homegrown observability (no Langfuse/LangSmith dependency): a
  deliberate sidebar action calls the real configured provider once and shows, per decision,
  the full prompt, the model's raw response, latency, token counts, an approximate cost
  (**$0.00** for local Ollama), and whether the verify-guard rejected the pick. The dashboard/
  queue/audit tabs always render on the fast heuristic so the UI never blocks on a model call.

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

## Production readiness
Full engineering assessment — components, current-vs-target, scaling numbers, failure
modes, RBI data-localization — in **[ARCHITECTURE.md](ARCHITECTURE.md)**. Honest headline:
this is a **production-grade reconciliation core with a costed path to full production**,
not a finished distributed system. What's real today:
- **Ingestion seam** (`sources.py`) — a `ReconciliationSource` interface with CSV + a real
  SQLite adapter, and documented stubs showing exactly where the live merchant DB + Razorpay
  settlement API plug in. The matcher is source-agnostic.
- **Persistent, append-only audit log** with **idempotency** — re-running a settlement cycle
  never double-applies a decision (`SKIPPED_IDEMPOTENT`).
- **Ops:** JSON structured logging (`obs.py`), bounded-backoff retries for the API path
  (`net.py`), a **Dockerfile + docker-compose** (CI builds the image on every push).
- **Untrusted-input hardening:** bank narration fed to the LLM is sanitized + JSON-encoded
  (prompt-injection posture); the heuristic path is injection-immune by construction.

```bash
docker compose up                                   # the reconciliation UI on :8501
docker run --rm recon-controller \
  python src/pipeline.py --execute --cycle 2026-07-15   # the batch job
```

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
- The reported **headline numbers are the keyless heuristic** (so CI stays deterministic).
  The real-LLM path **is validated live** on a local model (qwen3:4b via Ollama) — and that
  run surfaced a real failure mode: the model auto-resolved clear cases but made one
  over-confident *wrong* pairing, which a deterministic verify-guard now rejects (falls back
  to the heuristic → human review). See [RESULTS.md](RESULTS.md).
- The verify-guard rejects LLM picks with **no** narration support; it is a safety net
  against unsupported hallucinations, not a proof of correctness — genuinely ambiguous cases
  still escalate to a human by design. It also does **not** detect a *forged* narration (an
  attacker who can write the narration field itself, not just influence the LLM's reading of
  it) — the integrity assumption is that narration is bank-generated, matching Razorpay's real
  settlement recon `description` field, which is server-generated, not merchant-editable. A
  test (`test_KNOWN_LIMITATION_guard_does_not_detect_narration_forgery`) documents this
  honestly rather than overclaiming the guard is injection-proof end to end.
- It reconciles and proposes; it does not move money. This is Razorpay's own stated framing
  for the track too — Agent Studio's adjacent **Settlement Insights** agent (launched Mar
  2026) reads and *summarizes* settlements over WhatsApp; it does not reconcile against a
  merchant ledger or resolve exceptions, so this submission is complementary, not a duplicate.

## Repo layout
```
src/generate_data.py   synthetic data + ground-truth answer key (seed 42)
src/selftest_data.py   9 data-integrity invariants
src/matcher.py         deterministic 3-pass matcher + typed exception queue
src/llm_handler.py     LLM/heuristic resolver for the escalated residue
src/pipeline.py        end-to-end run (run()/main) + guardrails + audit log
src/audit.py           persistent append-only hash-chained audit log
src/sources.py         ingestion seam: CSV/SQLite adapters + production stubs
src/obs.py  src/net.py JSON structured logging · bounded-backoff retries
app.py                 Streamlit UI: dashboard · exception queue · audit viewer
Dockerfile  docker-compose.yml   reproducible image (CI builds it every push)
src/eval_guard.py      reproducible guard-safety metric vs a worst-case adversarial model
src/report_metrics.py  confidence calibration - rupee attribution - wrong-match count
src/matcher.py         [also] subset-sum many-to-one batch settlement matching
src/threeway.py        three-way tie-out: ledger vs Razorpay settlement vs bank statement (by UTR)
src/demo_refusals.py   scripted on-camera demo: 4 out-of-policy actions, all refused
src/eval_holdout.py    seed-level held-out gate · src/eval_formats.py format-level held-out gate
tests/                 79 pytest cases (adversarial guard, refusals, money attr., batch, format, three-way) in CI
ARCHITECTURE.md        components · current-vs-target · scaling · failure modes
NOTES.md PLAN.md LOG.md RESULTS.md   context, roadmap, failure trail, metrics
research/              the research reports the design is grounded in (incl. Razorpay's
                       own architecture + competitive landscape, refreshed 2026-08-28)
```
