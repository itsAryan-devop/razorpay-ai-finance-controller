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
pytest -q                    # 26 tests
streamlit run app.py         # dashboard + exception queue + audit viewer
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
hardcoded. Three views:
- **Dashboard** — headline metrics (accuracy, match rate, misattribution pairing before→after,
  throughput), the exception mix, per-class precision/recall, and the EXTRA_CREDIT queue
  precision lift (0.73 → 1.00 after the handler pairs the colliding credits).
- **Exception queue** — the typed queue, filterable by type and route, plus the
  escalated→handler decisions with their confidence and justification.
- **Audit log** — the hash-chained entries with a live **"Verify chain integrity"** button
  that recomputes the SHA-256 chain, and the dry-run/execute gate exposed as a guarded button
  (only high-confidence AUTO_RESOLVE applies, behind an explicit confirm).

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
- The real-LLM path is wired and fallback-tested but **not yet validated live** (pending an
  API key); the reported numbers are the keyless heuristic.
- It reconciles and proposes; it does not move money.

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
tests/                 26 pytest cases (run in CI on every push)
ARCHITECTURE.md        components · current-vs-target · scaling · failure modes
NOTES.md PLAN.md LOG.md RESULTS.md   context, roadmap, failure trail, metrics
research/              the 4 research reports the design is grounded in
```
