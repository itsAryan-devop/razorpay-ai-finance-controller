# Research 02 — Winning Fintech Hackathon Projects, Reverse-Engineered

*Research completed 2026-08-24.*

---

## 0. Reframe: this is a hiring funnel, not a hackathon

Per Velonx's breakdown of the process:
- **Round 1** — pick a track, build a working project
- **Round 2** — public GitHub repo + ~5-min pitch video + architecture documentation
- **Round 3** — panel review, **live architecture walkthrough**

Stated signals: code quality & architecture decisions · ability to **explain technical choices live** · complete-and-working beats ambitious-and-half-finished · genuine understanding of AI-native primitives · **professional repo presentation** (README, commit history, docs).

This is materially different from Devpost judging (watch 3-min video, move on). **Razorpay judges read the repo and interrogate the architecture.** Design for that.

## 1. Table of winning projects found

| Project | Hackathon / Award | What it did |
|---|---|---|
| AI-Driven Multi-Agent Fraud Alert Triage System | AWS AI Agent Global Hackathon — Best Bedrock AgentCore | 3-agent fraud alert triage → investigation → SAR drafting |
| AegisAgent | AWS — 2nd overall | Insurance claims via adversarial multi-agent debate, pause/resume |
| Province | AWS — 3rd overall | Conversational tax filing, multi-agent |
| TruthKeeper | Google Cloud Rapid Agent Hackathon — 2nd (1,430 submissions) | Reconciles CRM/billing/support data, **explains + estimates $ impact** |
| "How Did I?" | same — 3rd | Surfaces ecommerce **revenue leaks**, recommends fixes |
| SalesShortcut | Google ADK Hackathon — Grand Prize (477 projects) | Full multi-agent SDR: lead gen → research → proposal → outreach |
| AgentZero | TreeHacks 2025 — Winner | "Autonomous and verifiable" trading agent, safety rails |
| FraudLens | RBI HaRBInger 2025 — Winner | Real-time risk scoring → block/approve/step-up auth |
| CrawlerPal / Codebusters | PayPal Dev Days 2025 — 1st/2nd | AI paywall agent on PayPal APIs / a *correct SDK migration* (no AI!) |
| FraudSquad | Kaggle IEEE-CIS Fraud Detection — 1st of 6,381 | Canonical fraud feature-engineering solution |
| MCP.STORE | Solo.io MCP Hackathon 2026 — runner-up | E-commerce demonstrating MCP **authn/authz** |

## 2. The most instructive examples

### 2.1 AI Fraud Alert Triage (Best Bedrock AgentCore) — ⭐ template for Risk track
https://devpost.com/software/ai-driven-multi-agent-fraud-alert-triage-system

**Framing move:** doesn't say "detect fraud" — says **>90% of fraud alerts are false positives, causing analyst fatigue.** Attacks the *ops cost*, not the abstract problem.

**3 agents, each a one-sentence job mapping to a real role:**
1. Alert-Triage Agent — pulls from Athena, enriches, risk-scores, auto-dismiss vs escalate
2. Investigation Agent — cross-account linkage, velocity, fraud typology
3. Report Agent — structured SAR summaries → S3

Stack: Claude 3.5 Sonnet/Bedrock, AgentCore, LangGraph, Athena, S3, Lambda, React analyst UI.
**Result: false positives down 60% in pilot.**

**Why it won:** attacks cost side (analyst hours) nobody else targets · 3 agents map to a real job ladder judges instantly recognize · ships an analyst UI, not a notebook · SAR output is a real regulatory artifact · one clean headline number.
**Weakness — beatable:** no public repo, no visible demo video. Razorpay scores the repo — you can beat this on presentation alone.

### 2.2 AegisAgent — adversarial critic agent as differentiator
https://devpost.com/software/aegisagent-an-insurance-claim-app-fully-developed-by-kiro

Evidence Curator → Policy Interpreter → **Compliance Reviewer that adversarially challenges the other two agents' assumptions.** Debate rounds with **pause-and-resume** — stops and asks the user for missing evidence.
Why it won: adversarial reviewer gives judges something to probe · pause-and-resume proves they designed for incomplete inputs (most demos assume perfect data) · used LLM vision to replace CV object detection — a defensible, explainable tradeoff · shipped a live URL.
**Pattern repeats** in GAIA (adversarial debate for ESG-claim verification). **Adversarial/critic agents are a repeatedly-rewarded pattern.**

### 2.3 TruthKeeper — closest public analogue to Finance Controller track
https://www.fivetran.com/blog/meet-the-ai-agents-that-won-the-google-cloud-rapid-agent-hackathon

Reconciles CRM/billing/support, **explains discrepancies AND estimates financial impact of each.**
**The bar this sets: every unmatched line must carry a ₹ number and a proposed resolution.** Anyone can build a diff; winners build a diff that ranks by rupees at stake.

### 2.4 verity-invoice-agent — best public architecture for LLM finance-ops (not a winner, a design reference)
https://github.com/nikhil5342/verity-invoice-agent

**Design principle, verbatim: "The LLM reads. Deterministic code does the math."**
5 layers: Extraction (LLM reads fields **with per-field confidence**) → Context (direct lookups, **explicitly no RAG**) → Orchestration (Python does matching/arithmetic/anomaly detection) → Governance (confidence+findings → decision, logged) → Human Gate.

**3 decision outputs — distinction matters, they route to different human workflows:**
`AUTO-CLEAR` (confident, fine) / `FLAG` (problem found, with evidence) / `ESCALATE` (model unsure it even read the fields right).

**Eval framing — copy this verbatim:**
1. Perception accuracy (did extraction work?) — 100%
2. Routing correctness (decisions match ground truth?) — 94%
3. **Trustworthiness — escaped-error rate on auto-cleared invoices — 2.8%** ← they prioritize THIS, reasoning that high automation is worthless if auto-cleared invoices hide undetected errors.

**Honest-failure reporting, copy this too:** all invoices self-reported 100% confidence, so ESCALATE never fired; 3 errors came from degraded scans read confidently anyway. Their #1 roadmap item: an *independent* image-quality gate, because self-reported confidence isn't trustworthy.

Repo layout: `extract.py / validate.py / decide.py / audit.py` (append-only JSONL) `/ run_eval.py / selftest.py`. Gap to close if we use this as a model: **no Docker/CI.**

### 2.5 FraudSquad — Kaggle IEEE-CIS 1st place — the fraud-ML technical bar
https://www.kaggle.com/competitions/ieee-fraud-detection/writeups/fraudsquad-1st-place-solution-part-2 · https://developer.nvidia.com/blog/leveraging-machine-learning-to-detect-fraud-tips-to-developing-a-winning-kaggle-solution/

**Core insight: classify the CLIENT, not the transaction.** Synthesized UID from `card1+addr1+D1n`, then 40+ group-aggregate features (mean/std/count) over that UID; final step replaces per-transaction predictions with client-level averages.

Other separators: **time-based validation** (GroupKFold on ordered months, not random split) · aggressive feature selection (dropped 19/242) · splitting compound values (amount → dollars+cents) · CatBoost+LGBM+XGBoost ensemble, heavy regularization · **AUC not accuracy** (3.5% fraud rate).

**Translated to Risk track: the winning move isn't a better model, it's entity resolution** — stitch transactions into merchant/card/device/beneficiary UIDs and compute velocity+aggregates at THAT level. This is literally how mule networks and card-testing work.

### 2.6 CrawlerPal / Codebusters — the anti-flashy lesson
2nd place at an AI-era hackathon was a **correct SDK version migration, zero AI.** It placed because it did something the sponsor deeply cares about, completely and correctly.
**Lesson: deep, correct, COMPLETE use of the sponsor's own primitives beats novelty.** Build on Razorpay's actual APIs/webhooks, not a generic simulated payment model.

### 2.7 SalesShortcut — Grand Prize, 477 projects
Automates lead-gen → research → proposal → outreach **end-to-end**, not a step. Beat "analysis-only, human still decides" entries.
**Translated: "an agent that does X" loses to "an agent that runs the entire [named role]'s loop and closes it."**

### 2.8 FraudLens — RBI HaRBInger 2025 winner
Real-time scoring → **block / approve / step-up auth** (three-way action, not a probability).
Same shape as verity's AUTO-CLEAR/FLAG/ESCALATE and AWS triage's auto-dismiss/escalate. **Three winners independently converged: a risk system's output is a routed action, not a score.**

## 3. COMMON PATTERNS IN WINNERS

1. **Output is a routed decision, not a score.** Block/approve/step-up. Auto-clear/flag/escalate. Define an action taxonomy.
2. **Attack the operational COST of the problem**, not the problem itself. "90% false positives → analyst fatigue" beats "fraud is expensive."
3. **One headline number, quantified.** 60% fewer false positives. Never a metrics dump.
4. **Every finding carries a ₹ number and a proposed resolution.** Ranking by money turns a detector into a product.
5. **Multi-agent where each agent maps to a real human role.** Not "Agent A, B, C" — triage analyst → investigator → compliance officer.
6. **Adversarial/critic agent = repeatedly rewarded differentiator.** Gives judges something to probe; real hallucination defence.
7. **Human-in-the-loop is a designed surface, not an apology.** Review UI, pause-resume for missing evidence, append-only audit log.
8. **LLM for perception, deterministic code for arithmetic.** Nobody who wins lets an LLM add up money.
9. **They ship something you can click.** Judges explicitly penalize "backend-heavy, minimal UI."
10. **Deep correct use of the sponsor's own primitives** beats generic novelty.
11. **The repo is a portfolio artifact** — CI badges, docker-compose, /tests, /docs, quick-start, architecture+security docs linked from README.

## 4. WHAT LOSERS DO — anti-patterns

**Presentation:**
- Skipping the problem statement — "a strong project with a confusing demo loses to a simpler project judges understand"
- Demo takes too long to show something working (rule of thumb: **within ~90 seconds**)
- Five half-broken features instead of one polished one
- Live API calls in the demo (winners mock/pre-seed to remove stall points)
- Backend-heavy, no UI
- Bragging about invisible infrastructure
- Recycling a previous submission (visible in the wild — one repo submitted to 60+ hackathons, mismatched to track theme each time)

**Fraud/ML specifically:**
- **Reporting accuracy on imbalanced data** — at ~3% fraud, "always predict not-fraud" scores 97%. Use **PR-AUC and recall**, ROC-AUC secondary only.
- **Random train/test split on temporal data** — leaks the future. Use time-ordered splits.
- **No cost matrix** — a missed fraud and a blocked good customer cost wildly different amounts. Define expected-loss over the confusion matrix, don't default to 0.5 threshold.
- **Transaction-level features only, no entity aggregation** — the single biggest gap between average and winning fraud work.
- **SMOTE as the entire imbalance story**, no discussion of distortion. (1st place Kaggle solution didn't resample at all.)
- **No SHAP / no explanation of why flagged** — in payments this is a compliance requirement, not a nice-to-have.
- **No threshold discussion, hardcoded 0.5.**

**Repo:** compared an "above-average" public fraud repo (FastAPI+React, 8 rule patterns, XGBoost, 0.98 ROC-AUC, deployed) against what's still missing even there: **no tests, no Docker, no CI; imbalance handling undocumented; reports raw accuracy (94.7%) prominently on a fraud problem; no architecture diagram, no eval harness, no error analysis.** Closing exactly these four gaps is cheap and is most of the delta to a winning repo.

## 5. Concrete techniques by track

**Risk Manager** — entity-resolve into merchant/card/device/beneficiary UIDs · velocity+aggregate features on those UIDs · time-based validation · cost matrix + tuned threshold, expected-loss reported · SHAP per-decision · three-way routing (approve/step-up/block) · analyst review UI with feedback loop · **measure analyst-hours saved, not just AUC.**

**Finance Controller** — copy verity's layering exactly (LLM-reads-with-confidence → deterministic-matches-and-computes → confidence-routed-decision → audit log → human gate) · multi-pass matching (exact → fuzzy → many-to-one → residual) · every break annotated with ₹ at stake + proposed journal entry. Also see run-llama/invoice-reconciler and erp-mafia/accounted (has real CI — good repo-structure reference).

**Revenue Recovery** — ⭐ **no hackathon winner found in this space at all — least competitive track, almost no public prior art to be compared against.** Industry baseline: naive retries recover 15-25%; ML-driven retry-time/gateway/channel selection reaches 55-80%. Model on decline code, issuer behavior, customer value, timing.

**Growth/Agentic Commerce** — build on the actual protocol layer: Stripe's Agentic Commerce Protocol, MCP servers for payments. MCP.STORE won specifically for handling **agent authn/authz** (JWT+CEL policy) — the unsexy trust layer is where judge attention goes because it's the unsolved part.

## GAPS — not found

1. No Razorpay Buildathon winners exist yet (future deadline).
2. **No hackathon winner found for failed-payment recovery/dunning/smart retries** — confirms Revenue Recovery is the least-charted track.
3. No public repos for top fintech Devpost winners (AWS triage, AegisAgent) — analysis is writeup-based only.
4. Devpost's own search is JS-rendered, not fetchable by agent — coverage skewed toward hackathons with a separate winners blog post.
5. Kaggle writeup pages didn't render directly; IEEE-CIS details sourced via NVIDIA's secondary account.
6. RBI HaRBInger primary source blocked (Cloudflare) — FraudLens stack/repo/architecture unknown, only product description public.
7. **Bank-run hackathons (HSBC, StanChart, DBS, JPMorgan, Goldman, Capital One, HDFC, ICICI, CRED, Setu, Juspay, Cashfree, Zerodha) publish essentially no winner detail publicly.** Real, confirmed gap.
8. No verifiable winner demo video found — have judge/organizer demo-craft advice instead.
9. OpenAI Build Week 2026 winners (~40k registrants, $100k, announced ~12 Aug 2026) not yet indexed anywhere reachable — worth checking openai.devpost.com directly if time allows.
10. No public Stripe developer hackathon winners list found.
