# AI Finance Controller — Settlement Reconciliation Agent

> Razorpay AI Buildathon 2026 · Track 04 (AI Finance Controller) · solo submission

**Status: 🚧 in development.** This README is a skeleton — the metrics table, architecture diagram, and demo link land as phases complete. See `PLAN.md` for the roadmap and `LOG.md` for the build history.

## The problem
_(1 paragraph — settlement opacity: one bank credit hides hundreds of transactions, fees, refunds, and timing skew; manual reconciliation match rates sit near ~51% vs ~88%+ with proper tooling.)_

## What it does
Reconciles Razorpay settlement data against a merchant's own sales ledger, reports an honest **match rate + typed exception queue**, and uses an LLM only to explain and resolve the leftover exceptions — never to do arithmetic. Deterministic matcher first; LLM on the exception tail.

## Headline metrics
_(Goes here, near the top — reviewers skim. match rate · throughput (records/min) · exception-classification precision/recall on held-out split · pass@k / pass^k on LLM resolutions.)_

## Architecture
_(Diagram + the deterministic-matcher → typed-exception-queue → LLM-handler → audit flow. Draft is in PLAN.md.)_

## How to run
```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in TEST-mode Razorpay keys
python spike/check_settlements.py setup   # day-1 data spike
```

## What broke and how we recovered
_(Pulled from LOG.md — this is a scored part of the pitch.)_

## Guardrails (explainable · bounded · gated)
_(Audit log · dry-run default · confidence gate · human override. Mapped to RBI FREE-AI's 7 sutras.)_

## What this does NOT do
_(Honest limitations section — shadow-mode framing, known failure modes.)_
