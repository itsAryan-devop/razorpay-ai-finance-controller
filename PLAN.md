# Build Plan — T4 Finance Controller (Reconciliation Agent)

> The executable roadmap + architecture "mindmap". NOTES.md = research/context; this = what we're building and when.
> Deadline: **5 Sep 2026**. Budget: ~3-5 hrs/day × 11 days ≈ 40 hrs. **Freeze code ~Aug 30-31**, rest on README/video/form.

---

## What we're building (one sentence)
An AI Finance Controller that reconciles Razorpay settlement data against a merchant's own sales ledger, reports an honest **match rate + typed exception queue**, uses an LLM only to explain/resolve the leftover exceptions (never to do arithmetic), and audits every action — closing a real finance-ops loop across 50+ records with provable correctness.

## Why this wins (maps to Razorpay's verbatim rubric)
- "match rate and the exceptions it could not resolve" → our core output *is* exactly this.
- "throughput plus measured accuracy" → we generate both sides of the data, so ground truth is known → accuracy is provable, not estimated.
- "every money action explainable, bounded, gated" → audit log + confidence-gated routed actions + dry-run default.
- Deterministic-matcher-first, LLM-on-exception-tail = the single best "AI Judgment" signal research found for this track.

---

## Architecture (the mindmap)

```
                 ┌─────────────────────────────────────────────┐
                 │  DATA LAYER (we generate both sides)          │
                 │  • Merchant ledger  (their "books")           │
                 │  • Razorpay settlement recon report (truth    │
                 │    from test-mode API, or synthetic fallback) │
                 │  • Ground-truth map (we KNOW the answer)      │
                 └───────────────────┬─────────────────────────┘
                                     │
                 ┌───────────────────▼─────────────────────────┐
                 │  DETERMINISTIC MATCHER  (NO LLM — code only)  │
                 │  Pass 1: exact  (payment_id/order_id+amount)  │
                 │  Pass 2: fuzzy  (amount±fee, date±T+2 window) │
                 │  Pass 3: net-settlement decomposition         │
                 │    gross − MDR − GST − refunds ± adj = net,   │
                 │    tie to UTR to the paisa                    │
                 └───────────────────┬─────────────────────────┘
                          matched ◄──┤──► remainder
                                     │
                 ┌───────────────────▼─────────────────────────┐
                 │  TYPED EXCEPTION QUEUE                        │
                 │  MISSING_CREDIT · TIMING_VARIANCE ·          │
                 │  FEE_MISMATCH · PARTIAL_SETTLEMENT ·         │
                 │  REFUND_IN_LATER_CYCLE · DUPLICATE · FX_DIFF │
                 └───────────────────┬─────────────────────────┘
                                     │  (only the residue)
                 ┌───────────────────▼─────────────────────────┐
                 │  LLM EXCEPTION HANDLER                        │
                 │  • proposes resolution + human-readable why   │
                 │  • confidence score, evidence cited           │
                 │  • routed action:                             │
                 │      AUTO-RESOLVE / FLAG / ESCALATE           │
                 │  • LLM explains, CODE computes — never math   │
                 └───────────────────┬─────────────────────────┘
                                     │
                 ┌───────────────────▼─────────────────────────┐
                 │  GUARDRAILS + AUDIT                           │
                 │  append-only hash-chained log · dry-run       │
                 │  default (--execute opt-in) · confidence gate │
                 │  · idempotency · human override always avail  │
                 └──────────────────────────────────────────────┘

   EVAL HARNESS (built alongside, not after): match rate, exception-
   classification precision/recall on held-out split, throughput
   (records/min), pass@k & pass^k on LLM resolutions, exceptions.csv.

   THIN UI (Streamlit): recon dashboard · exception queue w/ explanations
   · audit-log viewer.
```

## Stack
Python · Razorpay test-mode API via `razorpay-mcp-server` (auto-detects test key) and/or the official `razorpay` Python SDK · pandas for matching · Claude (Agent SDK or direct API) for the exception handler · Streamlit for UI · pytest + GitHub Actions CI.

## Key principle stolen from competitor's path
**Causal / as-of matching**: never let a later settlement cycle retroactively "fix" a current-period match. A refund that settles in a later cycle is a REFUND_IN_LATER_CYCLE exception at period close, not a silent match. This is the finance-ops equivalent of "no future data leak" and it's an honesty signal.

---

## 11-Day Schedule

| Day | Date | Goal |
|---|---|---|
| 1 | Aug 25-26 | **⚠️ SETTLEMENT SPIKE = GO/NO-GO.** Repo scaffold, git init, LOG.md started. |
| 2 | Aug 26-27 | Data generation: merchant-ledger generator + pull real test-mode settlement recon (or synthetic fallback). Ground-truth labeling. |
| 3-4 | Aug 27-29 | Deterministic matcher (passes 1-3) + typed exception queue. |
| 5 | Aug 29-30 | Eval harness: match rate, throughput, held-out split. First honest metrics in RESULTS.md. |
| 6 | Aug 30 | LLM exception handler + routed actions + append-only audit log. |
| 7 | Aug 31 | Guardrails: dry-run/execute, idempotency, confidence gate. **← soft freeze target.** |
| 8 | Sep 1 | Streamlit UI (dashboard + exception queue + audit viewer). |
| 9 | Sep 2 | **FREEZE.** README (problem → money → build → metrics+cost table → limitations → how-to-run), architecture doc. |
| 10 | Sep 3 | 5-min video (lead with metrics, then show where it breaks). RBI FREE-AI section. |
| 11 | Sep 4 | Buffer + submit form. Deadline Sep 5. |

Rule: **rough complete v1 first, then improve the weakest part.** README + honest-metrics section outweigh the last 5% of accuracy.

## Running failure log
Keep `LOG.md` from day 1 — every bug, every "my first matcher gave X% false matches, here's the fix." Razorpay explicitly asks "what broke and how you recovered." A real log beats a clean narrative.

---

## Day-1 GO/NO-GO gate
Run the settlement spike (see `spike/check_settlements.py`). 
- **Settlements populate in test mode** → proceed with T4 as designed.
- **They don't / return empty** → two options, decide then: (a) synthetic settlement generator calibrated to the real recon schema (still fully valid — the track literally says "synthetic records"), or (b) pivot to T3 Revenue Recovery (pre-agreed fallback, research already done in NOTES.md §7 + research/04).
