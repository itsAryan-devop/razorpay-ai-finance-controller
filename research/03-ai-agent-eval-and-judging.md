# Research 03 — AI Agent Winners, Judging Criteria & Eval Methodology

*Research completed 2026-08-24. This is the single most decision-relevant report of the four.*

---

## 0. ⭐⭐⭐ THE MOST IMPORTANT FINDING

Razorpay's landing page is **a measurement spec disguised as a hackathon page.** Verbatim per-track bars:

| Track | Verbatim bar |
|---|---|
| 01 Growth/Commerce | "Every money action explainable, bounded and gated." Audit trail + graceful failure handling. |
| 02 Risk Manager | "Measured precision and recall on a held-out test set"; "honest metrics including false-positive cost"; "strictly defense-only." |
| 03 Revenue Recovery | "Measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail." |
| 04 Finance Controller | "Match rate and the exceptions it could not resolve"; "throughput plus measured accuracy." |
| 05 Open | "Real problem, working product, meaningful use of AI." |

**Every noun — precision, recall, held-out, false-positive cost, exception list, match rate, throughput, audit trail, stopping rules, bounded, gated — is a scoreable artifact.** The winning move: produce every one of these literally, by name. Most submissions won't, because most people build a demo, not an evaluation.

Format: track + working solution + public repo + **5-min pitch video with architecture explanation.** Secondary coverage: "explain what broke and how you recovered" + "defend design decisions" in a panel.

---

## 1. What actually won, across agent hackathons

### Anthropic "Built with Opus" Claude Code hackathons — most relevant signal
https://claude.com/blog/meet-the-winners-of-built-with-opus-4-7-claude-code-hackathon

Common patterns Anthropic itself calls out:
- **1-2 days on spec BEFORE code**, framed as accelerating not delaying execution
- **Domain expertise embedded**, not left to the model
- **Structured evaluation**: MaestrIA built a **9-dimension eval against 12 real cases**, used the data to set dev priorities — explicitly named a winning pattern
- Assistive not generative — winners made the architecture/domain calls themselves

Opus 4.6 edition: **domain experts with near-zero coding beat professional engineers** (13,000 applicants, 500 selected) — differentiator was problem selection and domain depth, not code volume.

### AWS AI Agent Global Hackathon
2nd (AegisAgent) and 3rd (Province) both won on **explainability of the decision**, not autonomy — "shows its work." Same axis as Razorpay Track 01.

### Microsoft AI Agents Hackathon 2025 (18k registrants, 570 submissions)
**ModelProof: Sentinel AI Chat** won its category with **dual-LLM consistency checking to detect hallucinations/bias/intent misalignment** — an evaluation/guardrail system won outright.

⚠️ **Could not find:** a public winning-agent repo that ships a full eval harness with reported numbers. **This is a genuinely uncontested differentiator.**

## 2. Real published judging rubrics (with weights)

### All Things Agentic Hackathon (Google Cloud) — most agent-specific
- 40% Innovation & Operational Utility ("does it eliminate real friction, autonomous execution beyond chat")
- 30% **Architectural Discipline & Tech Stack** (decoupling, state mgmt, failure tolerance, routing resilience)
- 30% **Demo & Production Readiness** (**unedited live execution**, clean docs **with architecture diagrams**)

**60% of the score is engineering discipline + provable execution. Nothing about UI polish.**

### Agents for Humans (AWS Strands) — 5×20%
Technical Implementation (non-trivial) · Design (complete product, not just PoC) · Potential Impact (credible+specific, based on what's demonstrated) · Creativity (non-obvious) · Presentation (end-to-end demo)

### Cross-rubric synthesis
Every rubric found contains: real problem · works end-to-end · non-trivial engineering · judge can understand and reproduce it. **Razorpay substitutes "measured" for "works."**

## 3. What judges/organizers actually say

- **Jono Bacon:** "You have to be able to show something working within about 90 seconds."
- **Avi Press:** be transparent about what works vs doesn't — "judges can tell when you're talking around a feature that doesn't exist."
- **Colin Lowenberg:** most common failure = five features instead of one perfected.
- **⭐ AngelHack playbook** — the 5 metrics enterprise AI teams actually use to judge agents in production, recommended AS the hackathon rubric: **task completion rate, tool-use accuracy, cost per run, latency, hallucination rate.** Killer line: judges should score **trace logs, not demo quality**, otherwise "whoever made the slickest demo wins regardless of whether their agent actually worked." → **Shipping a trace log + metrics table is itself a scoring artifact.**
- **Money Forward judge writeup:** an AI judge skipped most tech and focused only on the visible folder structure → **assume shallow reading; put metrics at README line 3 and video's first 60s.**
- **Why agent demos fail (production lit):** most demo agents are "a UI, a prompt, and a foundation model — enough to win a hackathon, but nowhere near enough to run a business process." **Name this problem on camera, then show you solved it.**

## 4. ⭐ Agent Evaluation Methodology — the core of the submission

### Anthropic, "Demystifying evals for AI agents" — canonical source
https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

**Vocabulary to use verbatim in the README** (Razorpay engineers will recognize it): Task, Trial, Transcript/trace/trajectory, Outcome, Grader, Agent harness vs Eval harness, Eval suite.

Load-bearing recommendations:
1. **Grade state, not text.** "Your flight is reserved" means nothing if the DB has no row.
2. **Grade what the agent produced, not the path it took** (trajectory is a separate diagnostic layer).
3. **Start with 20-50 tasks from real failures.** Don't wait for hundreds.
4. **Task quality bar:** "two domain experts would independently reach the same pass/fail verdict." Ship a reference solution.
5. **Balanced problem sets** — test where behavior should AND should not fire. Directly relevant to false positives.
6. **Three grader types:** code-based (fast, brittle) / model-based (flexible, needs calibration against human judgment) / human (gold standard).
7. **Isolate every trial** — clean state each run.
8. **Separate capability evals (informative, start low) from regression evals (near 100%, release blockers).**
9. **Read the transcripts** — that's how you find your grader is wrong.
10. **Run evals in CI** on every change.

**Metrics — the differentiator:**
- **pass@k** — probability ≥1 of k trials succeeds
- **pass^k** — probability ALL k trials succeed
- Worked example: **at 75% per-trial success, pass^3 = 42%.** Single-run numbers hide reliability collapse.

> **For a money agent, pass^k is the correct headline metric and almost nobody will report it.**

### Anthropic, "Building Effective Agents"
Six patterns: prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, autonomous agent. **Choose deliberately, say why in the video.**
- "Start with simple prompts, optimize with evaluation, add multi-step agentic systems only when simpler solutions fall short."
- Three principles: simplicity, transparency (show planning steps explicitly), carefully-crafted agent-computer interface.
- Anthropic spent **more time optimizing tools than prompts** for SWE-bench.

### Langfuse — most implementable methodology
Four eval dimensions: **Trajectory** (sensible path?) · **Tool use** (right tool, right args?) · **Task completion** (did the user get what they asked?) · **Multi-turn quality**.
Golden-dataset loop: collect failing production traces → add to dataset with expected outputs → write code evaluators → gate CI on thresholds.
Stat: **agents evaluated only on final-output quality pass 20-40% more test cases than trajectory-level eval reveals** — the failure surface is at the step level.

### ⭐ τ-bench (Sierra) — THE benchmark to imitate for a payments agent
Domains with **domain-specific API tools + a policy document**. **Grading compares end-state DB against an annotated goal state** — "grade state not text," made concrete. Introduced **pass^k**. **First benchmark to treat policy adherence as a first-class metric separate from task success** — tests the agent's ability to **refuse requests that violate policy and propose alternatives.**

> **Direct steal: build a mini-τ-bench.** Policy doc + tool API + N annotated goal-states + pass^k + a separate policy-violation rate. This alone puts you in a different tier.

### Fraud-specific metrics
Use **PR-AUC not ROC-AUC** for imbalanced data. **"False positives are a pricing problem, not a model problem"** — price a wrong decline (blocked-txn margin + complaint servicing cost + P(churn)×LTV) in the same currency as a missed fraud, then set thresholds against **review capacity**, not a target recall figure. Multiple thresholds per risk tier, driven by a cost matrix.

> Razorpay literally asked for "honest false-positive cost analysis." This IS the answer — turn it into a rupee table with a stated review-capacity constraint.

## 5. ⭐ Guardrail patterns for money-touching agents

### OWASP Top 10 for Agentic Applications v1.0 (Dec 2025)
| ID | Risk | Mitigation | Relevance |
|---|---|---|---|
| ASI01 | Goal Hijack | Treat external data untrusted; human-in-loop for goal changes | HIGH |
| ASI02 | Tool Misuse | Strict permissions; **validate args before execution** | CRITICAL |
| ASI03 | Identity/Privilege Abuse | **Short-lived, task-scoped JIT credentials** | CRITICAL |
| ASI08 | Cascading Failures | **Circuit breakers, fan-out caps** — "financial DoS" | CRITICAL |
| ASI09 | Human-Agent Trust Exploitation | **Show confidence scores**; step-up auth outside chat | CRITICAL |
| ASI10 | Rogue Agents | Baseline behavior; **automated kill switches** | CRITICAL |

Core doctrine: **you cannot filter prompt injection away — contain the agent.** Least privilege, human approval for risky actions, sandboxed tools.

### Spend control patterns (concrete, copyable)
Six standard controls: **spending limits, velocity caps, allowlists, approval workflows, policy-engine enforcement, virtual-card scoping.** Tiered ladder: auto below X, notify at Y, **require human approval above Z.**

### Human-in-the-loop implementation
**LangGraph `interrupt()` + `Command`** — pauses mid-execution, surfaces decision, resumes from checkpoint. Four resolutions: **approve / edit / reject(w/ feedback) / respond.**
**OpenAI Agents SDK guardrails** — input guardrails (small classifier agent), output guardrails, **tool guardrails right before the real-world action**, tripwires that halt the run.

### ⭐ Audit & explainability (Track 01's literal wording)
FINOS MI-21 fields to log per decision: trigger+context, all inputs with sources/timestamps, **tool selection rationale AND rejected alternatives**, final decision+downstream effects, applicable rules/policies, risk assessment + confidence, **decision-chain linkages across multi-agent flows**, human approval records.
Mechanism: natural-language summary (business/regulator) + technical detail (engineers); **cryptographic hashing / append-only tamper-evident logs.**

### ⭐⭐ India-specific hook: RBI FREE-AI (13 Aug 2025)
7 Sutras: Trust is the Foundation · People First · Innovation over Restraint · Fairness and Equity · **Accountability** · **Understandable by Design** · Safety, Resilience and Sustainability.
Requires: customers know when AI is involved; **individuals retain final authority to override AI determinations**; log exact inputs, model versions, config, human-readable rationales, replayable audit trails.

> **Cite RBI FREE-AI by name in the README and video.** Razorpay is RBI-regulated. Mapping guardrails to the regulator's own seven sutras speaks the language of the people scoring you. Essentially no competitor will do this.

### Agentic-payments standards (Track 01 context)
- **AP2** (Google) — three signed **Mandates: Intent, Cart, Payment**, as W3C Verifiable Credentials
- **ACP** (OpenAI+Stripe) — **Shared Payment Token**: bound to merchant + dollar amount, time-bounded, single-use

> The **mandate → scoped, single-use, amount-bound, merchant-bound, time-bound token** pattern is the industry-standard answer to "bounded and gated." Implement it in miniature.

## 6. Demo craft

- Judges see 30-100 demos, form an opinion in **first 30 seconds.**
- **Razorpay format: 5 minutes with architecture walkthrough.**
- Structure: one-sentence pitch → problem → solution → demo → architecture → **numbers** → what broke and how you recovered.
- **Only mock non-core features** — judges spot mocks, it costs credibility.
- **Unedited live execution** is an explicit scoring line in the best rubric found.
- Be openly transparent about what doesn't work — Razorpay asks for this directly, it's a **scored honesty test.**
- Assume shallow reading: metrics table in README line 3 and video's first 60 seconds.

---

## 🎯 THE WINNING FORMULA (synthesized)

1. **Pick the narrowest possible loop and close it completely.** "One class of loss" beats a platform.
2. **Spend day 1 on a spec, not code.** Policy doc, tool contracts, eval task list — before the agent.
3. **Build the eval harness BEFORE the agent.** 20-50 tasks, balanced positive/negative, reference solutions. Most defensible differentiator; Razorpay asked for it four separate times.
4. **Grade state, not text.**
5. **Report reliability, not just capability.** pass@k AND pass^k, explicitly.
6. **Make every money action explainable, bounded, gated — demo each word separately on camera.**
7. **Be aggressively honest.** Exception list, false-positive cost table in ₹, failure-modes section, "what broke" narrative.
8. **Show the agent refusing.** A 20-second clip of it declining an injected instruction / hitting a spend ceiling / escalating to a human beats any happy-path clip.
9. **Prove architectural discipline.** Diagram, clean boundaries, retries/timeouts/idempotency keys, deterministic replay. Name which Anthropic pattern you chose and why not a more complex one.
10. **Optimize the artifact, not the moment** — repo/README outlive the pitch.
11. **Map to RBI FREE-AI** — one README section, seven bullets. 30 minutes of work, high signal.

## 📐 EVAL HARNESS BLUEPRINT — concrete repo layout

```
/agent            # tools, policy, orchestration
/policy           # policy.md — rules the agent must obey (τ-bench style)
/evals
  /tasks
    positive/     # ~20 — action should fire
    negative/     # ~15 — action should NOT fire (false-positive control)
    adversarial/  # ~5  — injection, out-of-policy, over-limit, ambiguous
  /graders
    outcome.py    # state assertions — DB rows, ledger, refund records
    trajectory.py # required tool present, no loops, step budget
    judge.py      # LLM-as-judge, explanation quality ONLY, calibrated
  run_eval.py     # k trials/task, isolated state, writes traces
  report.py       # emits RESULTS.md + confusion matrix + cost table
/traces           # every transcript, committed — this is your evidence
RESULTS.md        # auto-generated, linked from README line 3
```

Task rules: 40 tasks min · two-domain-experts-agree test · reference solution required · balanced classes (~50% should-not-fire) · **30% true held-out set, never touched during dev, seeded split committed.**

### README metrics table template
```
Held-out test set: 12 tasks × 5 trials = 60 runs · seed 42 · run 2026-08-xx

OUTCOME
  Task success (pass@1)            0.83
  Reliability   (pass^5)           0.58
  Precision / Recall               0.91 / 0.79
  PR-AUC                           0.88
  Policy-violation rate            0.00   ← must be zero

TRAJECTORY
  Tool-call accuracy               0.94
  Mean steps / run                 6.2 (budget 12, 0 breaches)

COST & THROUGHPUT
  Cost / successful task           ₹X.XX
  P50/P95 latency                  Xs/Ys

SAFETY
  Injection attempts blocked       5/5
  Actions gated to human           14
  Actions refused (out of policy)  5
```

## ✅ GUARDRAIL CHECKLIST — implement, demo ≥6 on camera

**EXPLAINABLE:** decision receipt (inputs+sources, rule/model version, confidence, alternatives rejected, action, effects) · dual-format output · full trace persisted · deterministic replay · hash-chained audit log · model/policy version stamped · confidence surfaced to human, never hidden

**BOUNDED:** per-action cap · rolling caps (daily/weekly) · velocity cap · allowlists · step budget · **stopping rules** (Razorpay names these for Track 03 explicitly) · circuit breaker · idempotency keys (no double refunds on retry) · dry-run default, `--execute` opt-in · kill switch · least-privilege short-lived scoped credentials

**GATED:** tiered approval ladder (config not code) · HITL interrupt w/ approve/edit/reject/respond · arg validation before execution · pre-execution tool guardrail (allowlist/amount/rate check) · input injection classifier · plan-then-execute (form plan before ingesting untrusted text) · irreversible actions always need human approval, no exceptions · step-up auth outside chat for large actions · human override always available · sandboxed tools (fixture ledger, no prod access) · escalation path with SLA

**Test them:** adversarial eval subset that fires each guardrail (injection in a note, over-limit refund, out-of-policy request, loop-inducing input) and **asserts the guardrail trips.** A guardrail with no test is a claim, not a control.

---

## GAPS

1. No published weighted rubric from Razorpay — track *standards* quoted in §0 are unusually specific though; treat as the rubric.
2. **No winning agent-hackathon repo publicly ships an eval harness with reported numbers** — searched Devpost/Anthropic/AWS/Microsoft/Google Cloud/LangChain/Agno. Unclaimed territory.
3. No judge writeup dedicated specifically to AI-agent submission failures (found production/enterprise-framed literature instead, labeled as inference not direct testimony).
4. AI Engineer World's Fair hackathon has an "evals & reliability" track but no published winners list — corroborates the thesis regardless.
5. Razorpay's panel-round format (what they probe, how) — only secondhand aggregator coverage, no first-party source.
