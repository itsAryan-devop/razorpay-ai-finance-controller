# Competitive refresh (2026-08-28) — Razorpay architecture, comparable submissions, gap analysis

Three parallel research passes, run after the core engineering was done, specifically to
answer: "is anything here weaker than what other students will submit, and what would make
a judge trust this more?" Every claim below is sourced; unverifiable claims are flagged as
such rather than asserted. Where this refresh **corrects** something in the earlier
research files (01-04), the correction is called out explicitly.

## 1. Razorpay's own agent architecture — verified/updated

**Bumblebee** (fraud detection) — [engineering.razorpay.com](https://engineering.razorpay.com/meet-bumblebee-the-multi-agent-ai-architecture-that-changed-fraud-detection-at-razorpay-c2b6d5704f51),
mirrored on [dev.to/razorpaytech](https://dev.to/razorpaytech/meet-bumblebee-agentic-ai-flagging-risky-merchants-in-under-90-seconds-2nlf).
Orchestration is **Celery** (a job queue), not LangGraph or Claude Agent SDK. Planner →
parallel Data Fetcher agents (each returns a compact JSON payload with structured snippets,
confidence scores, and provenance links) → Analyzer running **deterministic rules first**,
LLM confined to interpretation. Per-agent temperature tuning (Planner=medium, Analyzer=very
low). Metrics: latency 35s→8-12s, 60% token reduction, success rate 88%→99%+, 700-800 human
hours/month reclaimed. This is the closest published analog to our own
"deterministic-first, LLM-on-the-tail" design.

**Project Viveka** — **CORRECTION to 01-razorpay-intel.md**: it is specifically an
oncall/incident root-cause-analysis agent (not a generic "shadow mode" agent), and is built
on **LangGraph** ("Supervisor Agent is built on LangGraph, a framework for creating stateful
multi-agent workflows"), not Claude Agent SDK as our stack-decision note in NOTES.md §5
loosely implied. Source: [engineering.razorpay.com](https://engineering.razorpay.com/project-viveka-from-30-minute-investigations-to-90-second-ai-analysis-e49ec9db2638).
Metrics: MTTI 30min→90s, MTTR −50-60%. **The "~80% accuracy target, still in shadow mode as
of Apr 2026" claim in 01-razorpay-intel.md (sourced there from a ZenML LLMOps-database
mirror, not the primary blog) could NOT be confirmed by re-reading the primary
engineering.razorpay.com article.** Treat that specific figure as unverified pending a
primary-source re-check; it is not repeated in our public-facing README (checked — it only
appears in internal notes/research files).

**Agent Studio** — [razorpay.com/blog](https://razorpay.com/blog/agent-studio-ai-agents-by-razorpay/),
launched FTX'26, **March 12, 2026**, built on **Claude Agent SDK** (confirmed). Includes a
**Settlement Insights** agent — sends a daily settlement summary via WhatsApp. This is
Razorpay's own finance-ops-adjacent shipped product. It reads/summarizes; it does not
reconcile against a merchant ledger or resolve exceptions — so our submission is
complementary to it, not a duplicate of already-shipped Razorpay functionality (the research
brief in 01-razorpay-intel.md flagged "don't rebuild Agent Studio" as a risk; this confirms
we haven't).

**razorpay-mcp-server** — verified via `gh api` (not scraping): MIT license, **230 stars, 35
forks**, last tagged release **v1.2.1 (Sept 2025)**; default-branch history tops out at
2026-03-26. **45 tools** now (README table), including `fetch_settlement_recon_details` and
`fetch_all_settlements` — useful reference for making `src/sources.py`'s
`RazorpaySettlementsSource` stub name real field/tool names. Could **not** confirm the
"auto-detects test/live mode from key prefix" claim in the MCP server's own README (our
earlier belief in this was based on our own day-1 empirical spike test against the live API,
not the MCP server's docs — that empirical finding stands on its own evidence, independent
of this repo).

**Track 04 rubric — exact quote, high-value finding.** From
[razorpay.com/buildathon](https://razorpay.com/buildathon/): *"Run the books and the cash
position. Build an agent that closes one finance-ops loop across a 50+ record batch of
synthetic data, reporting its match rate and the exceptions it could not resolve."*
Evaluation bar, quoted verbatim: **"Throughput plus measured accuracy plus an honest
exception list. One cherry-picked match proves nothing."** This is now quoted directly in
README.md as the validation frame for our held-out 5-seed eval + typed exception queue. No
FAQ, exact deadline time, or team-size rule was found anywhere on or off the page.

**RBI FREE-AI (13 Aug 2025)** — 7 sutras: Trust, People First, Innovation (over Restraint),
Fairness (and Equity), Accountability, Explainability ("Understandable by Design"),
Safety/Resilience/Sustainability. 6 pillars, 26 recommendations. Sources:
[Outlook Money](https://www.outlookmoney.com/banking/free-ai-rbi-releases-framework-for-ai-use-in-financial-sector-learn-about-its-seven-sutras),
[KPMG](https://kpmg.com/in/en/insights/2025/09/rbis-free-ai-committee-report-in-the-financial-sector.html)
— wording is a paraphrase of secondary sources; the primary RBI PDF itself was not located.
Our existing README citation ("Accountability and Understandable-by-Design") matches this.

## 2. Comparable submissions / competitors

**No public Track 04 (reconciliation/finance-controller) submission was found** despite
targeted GitHub/Devpost/LinkedIn/X searches. Two real public submissions to this *same*
buildathon were found, both other tracks:

- **RiskPulse — Transaction Risk Manager** ([GitHub](https://github.com/SamarthKapdi/RiskPulse---transaction-risk-manager)),
  Track 02 (AI Risk Manager). ML risk scorer (HistGradientBoosting) + Gemini LLM for
  explanations + a deterministic policy engine (ALLOW/MONITOR/REVIEW/HOLD) + PostgreSQL
  audit trail. Explicit stated principle: **"The LLM does not control financial
  decisions."** Metrics: PR-AUC 0.9699, ROC-AUC 0.9972, precision 97.4%, recall 90.2%, 29
  tests. This is a strong sibling submission at the *same event* — same guardrail
  philosophy as ours (LLM explains, deterministic code decides), and its rigor (held-out
  metrics, real audit trail, graceful LLM fallback) is a useful bar for "what good looks
  like" in this buildathon's judging culture, even though it targets a different track.
- **"Recovery Agent"** ([recovery-agent-eight.vercel.app](https://recovery-agent-eight.vercel.app/)),
  apparently Track 03 (Revenue Recovery) by title match. Page was too thin (JS-rendered, no
  README found) to extract architecture or metrics — nothing more can be honestly reported.

General fintech/AI-agent hackathon judging patterns found: task completion rate, tool-use
accuracy, **cost per run**, latency, hallucination rate are a commonly cited rubric
([AngelHack AI Agent Hackathon Playbook](https://angelhack.com/blog/ai-agent-hackathon/)).
The Great Agent Hack 2025 (Holistic AI × UCL) judged explicitly on performance,
**transparency/observability**, and safety for financial-services agents, and its
observability-track winner built full execution-trace + human-interpretable reasoning
chains ([holisticai.com](https://www.holisticai.com/blog/what-we-learned-from-the-great-agent-hack-2025)).
No evidence was found tying a specific observability tool (LangSmith/Langfuse/etc.) to an
actual finance-agent hackathon win — reporting that gap honestly rather than inventing a link.

Bottom line: as of this research, **no visible direct track-mate rival exists with a public
repo.** This is good news but not something to get complacent about — it could still exist
privately, or appear before the deadline. It does NOT reduce the value of doing the
engineering right.

Two general-purpose (non-hackathon) reconciliation reference implementations were found for
architectural comparison, not as competitors: [verity-invoice-agent](https://github.com/nikhil5342/verity-invoice-agent)
(LLM extraction + deterministic validation — philosophically close, but 0 stars, unconfirmed
as a hackathon entry, thin README) and LlamaIndex's official
[invoice-reconciliation templates](https://github.com/run-llama/template-workflow-extract-reconcile-invoice)
(LLM-FIRST — an LLM compares and produces the match+rationale directly — the *opposite*
guardrail philosophy from ours; useful as a documented counter-example of what NOT to do
for a money-moving decision).

## 3. Brutal technical gap analysis vs. 2025-2026 best practice

Full sourced report below; net verdict up front: **the architecture (deterministic
matcher + narrow LLM escalation + verify-guard) is not a weakness to disguise as
"agentic" — it matches the emerging 2026 consensus for finance specifically.** The real
gaps are in observability and adversarial testing, not architecture.

1. **No LLM observability/tracing tool** (LangSmith/Langfuse/Arize/Braintrust). "89% of
   respondents have implemented observability for their agents" per LangChain's 2026
   state-of-agent-engineering survey vs. 52% for evals
   ([langchain.com](https://www.langchain.com/state-of-agent-engineering)). Our structured
   JSON logging (`src/obs.py`) is a partial substitute. **Recommendation: document as a
   known limitation; add only if time remains** — not worth the retrofit risk this close to
   deadline.
2. **No formal eval framework (DeepEval/RAGAS/promptfoo).** DeepEval is "pytest-based...
   built explicitly to function as a CI/CD quality gate"
   ([deepeval.com](https://deepeval.com/blog/top-5-llm-evaluation-frameworks)) — close to
   what `eval_holdout.py` already does by hand. **Recommendation: skip.** LLM-as-judge tooling
   is built for open-ended generation; our held-out 5-seed CI gate (mean accuracy 0.992,
   gate ≥0.95) is arguably more rigorous for a deterministic matcher than a bolted-on judge
   metric would be.
3. **No adversarial/prompt-injection test suite for the verify-guard** — flagged as the
   **highest-value cheap fix**, and the one item from this whole research sprint we
   actually implemented (`tests/test_adversarial.py`, 7 tests): sanitize-strips-injection,
   length-bomb bounding, JSON-breakout resistance, the guard rejecting a mocked
   "compromised" model's confident wrong pick end-to-end (a direct reproduction of the live
   qwen3:4b bug), a tied-narration-collision-escalates-not-guesses property test, and one
   test that HONESTLY documents a real remaining limitation: the guard checks textual
   grounding, not narration *authenticity* — a forged narration (if the field were
   attacker-writable, which the real settlement `description` field is not) would still
   fool it. Financial-agent red-teaming context: "Authentication Bypass – Financial Damage"
   is 48% of policy-violation test cases in one agent-benchmark breakdown
   ([arxiv.org/2506.09600](https://arxiv.org/pdf/2506.09600)).
4. **"Is single-shot structured-output classification defensible, or should this be a
   'real' multi-step agent?"** Yes, defensible — cite it as a feature, not a limitation.
   Anthropic's own guide: "most production LLM systems are workflows, not agents"
   ([anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)).
   A cited 2026 finance-AI framework: full autonomous decision-making is right for only
   "~2%" of finance use cases
   ([kognitos.com](https://www.kognitos.com/blog/ai-agents-finance-autonomous-finance-what-it-means-2026/)).
   Multi-agent LangGraph/CrewAI orchestration is common in vendor marketing but not shown to
   outperform a hybrid deterministic/LLM design on grounding or audit correctness for this
   use case — the reconciliation-pattern write-up in
   [chatfin.ai](https://chatfin.ai/blog/build-ai-reconciliation-agents-complete-development-guide-2026/)
   independently converges on the same hybrid pattern we already built. **Recommendation:
   state this explicitly in the pitch — don't apologize for the bounded design.**

Priority order actually executed this session: adversarial test suite (done), rubric-quote
citation in README (done), Settlement-Insights differentiation note (done), Viveka
correction logged (done, this file). Observability tooling and a formal eval framework are
explicitly left as documented, deliberate non-priorities — see ARCHITECTURE.md §8 for the
existing "what we deliberately did NOT build and why" framing, which this extends.
