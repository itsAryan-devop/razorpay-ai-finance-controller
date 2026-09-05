# Research 01 — Razorpay-Specific Intelligence

*Research completed 2026-08-24. Full findings with sources.*

---

## ⚠️ CRITICAL: DEADLINE IS 5 SEPTEMBER 2026

Today is 24 Aug 2026. **~12 days.** This is the single most important constraint on every decision.
Sources: https://x.com/ajay_2512x/status/2090393869473165453 · https://velonx.in/blog/razorpay-ai-buildathon-2026-tracks-eligibility-stipend-selection-process
Program starts September, **in-person Bengaluru**, ₹75k/mo, 6 or 12 months (candidate's choice, same stipend).

---

## 1. Prior editions? NO — this is edition one

High confidence, convergent negative evidence: no edition number/past-winners/alumni on the landing page; ~10 differently-phrased searches returned zero prior-cohort results; no YouTube demos, no "I won" LinkedIn posts, no Devfolio archive.

**Implication:** no reference submissions to calibrate against → **over-index on Razorpay's engineering blog as the calibration source** (see §3).

**Do not confuse with:** the *OpenCode Buildathon* — organised by **GrowthX**, Razorpay was only venue partner. 8-hour sprint, 100 builders, no winners published. Different event.

## 2. Razorpay's hackathon history (culture signals)

- **FTX Hackathon 2020/2021** (external, closest precedent) — judging panel was **Shashank Kumar (Co-Founder), Raju Shetty (Head of Engineering)**, plus Kailash Nadh (Zerodha CTO), Matrix & Sequoia partners. 2021 winner: Team KeyboardCavalry. Projects gallery is empty — nothing recoverable about *what* was built. Note: FTX **banned solo entries**; this Buildathon does not.
- **HACK:O(n)** — internal employee hackathon, 9 editions by 2024. 800+ employees, 215 teams. Deliberately cross-functional. Winner names unpublished.
- **Razorpay Ray** (their AI assistant product) **originated as an internal hackathon project.** Culturally load-bearing: at Razorpay, hackathon projects are expected to become products.
- **Razorpay won RBI's HaRBInger 2023** with **DrishtiPay** (payments for the visually impaired) — https://razorpay.com/newsroom/razorpay-pos-awarded-first-prize-at-rbis-global-hackathon-harbinger-for-drishtipay-a-solution-which-facilitates-ease-to-use-digital-payments-for-visually-impaired/ → **accessibility/underserved framing has documented cultural resonance.**

## 3. ⭐ THEIR ENGINEERING BLOG IS THE RUBRIC

Medium 403s to bots; DEV mirror works: https://dev.to/razorpaytech

### 3a. Bumblebee — multi-agent merchant fraud detection ← **THE TEMPLATE**
https://dev.to/razorpaytech/meet-bumblebee-agentic-ai-flagging-risky-merchants-in-under-90-seconds-2nlf

Narrative structure of the post = **naive prototype → why it broke → rebuild → why that broke → production architecture → measured deltas.**

- *Phase 1, n8n prototype:* died of branch explosion, poor observability, platform instability.
- *Phase 2, Python + ReAct single agent:* got observability, but token bloat (50KB+ context), sequential latency, **temperature conflicts between planning and scoring**.
- *Phase 3, multi-agent (production):* **Planner Agent** (execution plan with priorities + **token budgets**, enforces business rules e.g. skip GST validation for non-Indian merchants) → **parallel Data Fetcher Agents** (one per source: website, WHOIS, fraud DBs, social; each **prunes locally**, returns compact JSON not raw payloads) → **Analyzer Agent** (**deterministic rules first** — hard thresholds, blacklists — LLM only for interpretive summarisation).

Stated principles: "Token budgets are real constraints… prune early, prune often" (60% token reduction); **temperature tuned per agent role** (medium planning, very low deterministic scoring); many small parallel agents > one big sequential agent; **graceful degradation** — fetcher fails → Analyzer proceeds on partial data and flags what's missing rather than blocking. Every agent logs **trace ID, tokens, latency, confidence score, reasoning** → replayable audit trails for regulatory/dispute purposes.

Metrics: latency 35s → 8–12s · success 88% → 99%+ · 700–800 manual hours/month eliminated · cost per evaluation *down* despite added sophistication.

**Thesis: production AI success depends less on model capability than on engineering discipline.**

### 3b. Project Viveka / Oncall Agent — multi-agent RCA
https://engineering.razorpay.com/project-viveka-from-30-minute-investigations-to-90-second-ai-analysis-e49ec9db2638 · https://www.zenml.io/llmops-database/ai-powered-incident-investigation-for-payment-infrastructure

Built on **LangGraph**. Supervisor → **parallel domain specialists** (Kubernetes, Coralogix, PromQL, AWS). **Dual RAG**: one store for service architecture/dependencies, another for alert-specific runbooks — grounding on institutional knowledge, not generic LLM output. Outputs **structured evidence with confidence scores, not free text**. Multi-hypothesis scoring with temporal correlation.

MTTI 30min → 90s · MTTR −50-60% · **accuracy target 80%+, and as of Apr 2026 STILL IN SHADOW MODE running parallel to humans.** Lessons: augmentation over replacement, **specialisation over generalisation**, continuous learning into the RAG store.

### 3c. Slash — autonomous engineering agent platform
https://razorpay.com/blog/razorpay-engineers-built-slash-slash-builds-the-rest/ — **Prabu Ram, SVP Engineering**, 18 May 2026.

Writes code, opens PRs, reviews them, talks to 15+ internal systems. Sub-agents for bugs, security, code quality, design-system compliance, i18n, pre-mortems. **MCP + CLI Gateway with scoped permissions.** Knowledge graph over GitHub/Slack/Drive/AWS/ticketing.

PRs 100/wk → ~1,000/wk in one month; zero-human PRs 10/wk → 100/wk; **over a third of merged PRs have no human in the loop.**

Quotes: **"Code got cheap. Everything else didn't."** · **"Slash is the platform. Repos decide the output."**
They score repos for **"Agent Readiness" on three pillars — Context, Testing, CI/CD — with an 80% threshold.**

### 3d. Other posts
"LinkedPayments: Payment Chains in Microservices" · "Gateway Integration Agent" (LangGraph, weeks→days) · "Delta Lake Health Analyzer" (DuckDB + Delta Lake). Auth revamp where an extra monolith hop was **60% of total latency**.

## 4. GitHub & stack signals

https://github.com/razorpay — 177 public repos. **Go is the systems language**, PHP legacy monolith, TypeScript frontend.

| Repo | Lang | ★ |
|---|---|---|
| `blade` (design system) | TS | 647 |
| `ifsc` | HTML/Ruby | 392 |
| `go-financial` | Go | 317 |
| **`razorpay-mcp-server`** | **Go** | **229** |
| `razorpay-php` | PHP | 206 |
| `devstack` | Go | 133 |

## 5. Hiring bar / what they screen for

**⭐ The page nobody links: https://razorpay.com/ai-builders/** — their own definition of an "AI Builder": people who "turn ambiguous business and product problems into working AI systems," who **"view workflows as agent loops,"** fluent in prompts, comfortable with GitHub-based work, and **have shipped or seriously prototyped projects to show.** Process: form → **project/GitHub portfolio review** → callback within 48h.

AI/ML screening (https://faceprep.in/article/razorpay-2026-ai-engineer-roles-for-freshers/): feature engineering, model serving, **drift detection**, agentic-AI portfolios. They prioritise engineers who can **"walk through a system you built end to end."** Explicitly notes familiarity with **Razorpay's own agentic implementations (Bumblebee, ACS Risk Engine, Agent Studio) strengthens candidacy.**

Intern stipend benchmark ₹60–80k → **₹75k is top-of-band. This is a genuine senior-intern bar.**

Traditional funnel (now replaced) drilled **deep project interrogation with follow-ups on every detail** — that part survives and is now the *whole* evaluation.

## 6. Evaluation signals NOT on the landing page

From secondary coverage — treat as directional, landing page wins on conflict:
1. **"Explain what broke during development and how you recovered from it."** (placement-officer.com) ← same instruction as Bumblebee's narrative
2. **"How you identified system failures and engineered fallbacks"** + whether AI/LLMs/agents were applied **appropriately** (coursejoiner, offcampusjobs4u)
3. Judging criteria (Velonx): code quality & architecture decisions · ability to **defend** technical choices · completeness of working implementation · clarity of problem statement · demonstration of AI-native components

Razorpay's framing: **"no resume screening, no aptitude test, no group discussion"** · "rather than shortlisting on CGPA or college tier" · **"your GitHub repo becomes your resume."**

## 7. Test-mode API surface

Same base URL `https://api.razorpay.com/v1/` for both modes — **mode = which key you use.** Test and live keys cannot be used simultaneously.
Docs: https://razorpay.com/docs/api/sandbox-setup/ · Postman: https://www.postman.com/razorpaydev/razorpay-public-workspace/collection/mfu7vaw/razorpay-apis
SDKs: .NET, Java, Node.js, PHP, Python, Ruby, **Go**.

| Product | Track fit |
|---|---|
| Orders, Payments | Core |
| **Payment Links** | **Best agentic-commerce primitive** — agent mints a link and sends it |
| Refunds | Revenue Recovery |
| **Disputes** | Risk |
| Settlements + Instant | Finance Controller |
| **Subscriptions** | **Revenue Recovery** |
| Invoices | Finance Controller |
| **Route** | Marketplace split/vendor payouts |
| **Smart Collect** | Reconciliation |
| **Downtime** | **UNDEREXPLOITED** — routing/risk agent |
| RazorpayX Payouts/Contacts/Fund Accounts | Finance ops |

**Verified test-mode capabilities:**
- **Subscriptions** — dashboard **"Charge this now"** simulates a due charge and fires all events → Revenue Recovery fully simulatable end-to-end. https://razorpay.com/docs/payments/subscriptions/test/
- **Smart Collect** — **"Make a Test Payment"** via NEFT/RTGS/IMPS, **fires the same webhooks as a live bank transfer.** https://razorpay.com/docs/smart-collect/testing/
- **RazorpayX** — own dummy balance, top up any amount; create contacts/fund accounts/payouts. ⚠️ **payouts do not auto-progress (manual state advance from dashboard)**; **Approval Workflow unavailable in test mode.** https://razorpay.com/docs/razorpayx/test-mode
- **Magic Checkout** — test keys + mock payment page, end-to-end funds-flow simulation.

### ⭐⭐ The single most exploitable asset: official MCP server
**https://github.com/razorpay/razorpay-mcp-server** (Go, MIT, 229★) · https://razorpay.com/docs/mcp-server/

**35+ tools.** MCP auth is just your Razorpay key → **works with test-mode keys.** Categories: Payments (`capture_payment`, `initiate_payment`, `submit_otp`…), Payment Links (`create_payment_link`, `create_payment_link_upi`, `send_payment_link`…), Orders, Refunds, QR codes, **Settlements/Payouts** (`fetch_settlement_recon_details`, `create_instant_settlement`…), Tokens, and integration helpers (`detect_stack`, `integrate_razorpay_checkout`).

**Local server = all tools unrestricted. Remote hosted = restricted. → run local.**
Razorpay also ships **400+ documented endpoints and an `llms.txt`** in dev docs specifically for AI coding agents.

## 8. ⚠️ COMPETITIVE BASELINE — what Razorpay ALREADY BUILT

**Agent Studio**, launched 12 Mar 2026, **built on Anthropic's Claude Agent SDK** — https://razorpay.com/agent-studio/ · https://razorpay.com/blog/agent-studio-ai-agents-by-razorpay/

Eight launch agents — **these are the obvious ideas, already taken:**
1. Dispute Responder
2. Subscription Recovery (w/ ElevenLabs)
3. Abandoned Cart Conversion ×2 (SuperU; Nugget by Zomato)
4. **Cashflow Forecaster** (cash position 3–7 days out, payroll/payout risk alerts)
5. **RTO Shield** (high-risk COD detection pre-dispatch, address validation)
6. RTO Insights
7. Settlement Insights (daily WhatsApp summaries)

Roadmap: No-Code Agent Builder (beta), third-party agent marketplace.

**Agentic Payments** — https://razorpay.com/agentic-payments/ — In-App Commerce (beta), LLM integration (**explicitly names Claude**), Voice AI. **UPI Reserve Pay (live)** for consent-based pre-auth, **UPI Circle (soon)** for delegated authorisation. "40+ composable tools & APIs", "AI-Ready MCP & APIs". Partners: NPCI, Vi, bigbasket; flows extending to Zomato, Swiggy, PVR Inox.

**Sprint 2026 — "The Age of AI-Native Payments"** — https://razorpay.com/sprint/26 — 100+ launches incl. **Razorpay MCP 1.0**, Remote MCP for cash position prediction, intelligent retry engine, smart AML risk screening, biometric card auth, CardSync.

---

## 🎯 WHAT THIS TELLS US — actionable inferences

1. **It's a disguised senior-engineer design interview, not a demo contest.** The winning artifact is the **architecture document and your defence of it**, not the UI. Budget ~40% of time on writing up *why*, not *what*.

2. **Copy Bumblebee's narrative structure literally.** Their blog: v1 fails → diagnosis → v2 fails → diagnosis → production + measured deltas. The Buildathon asks "explain what broke and how you recovered." **Same instruction.** → **Ship the failed branches in git history. Do NOT squash.**

3. **House architecture pattern (appears in Bumblebee AND Viveka independently):** planner/supervisor → **parallel** specialist sub-agents (one per data source) → **deterministic-rules-first** analyzer with LLM confined to interpretation. Plus: explicit token budgets + local pruning; per-agent temperature tuning; graceful degradation with explicit "missing" flags; **structured output with confidence scores, never free text**; per-agent trace IDs logging tokens/latency/confidence/reasoning.

4. **Report deltas as before→after pairs.** Every Razorpay AI post leads with numbers (35s→8-12s, 88%→99%, 30min→90s). **Build a small labelled eval set, run a baseline, report the improvement.** 30 labelled cases at an honest 76% beats a slicker project with no measurement.

5. **Shadow mode and honest limits are REWARDED.** Viveka shipped at an 80% *target*, still shadow-mode, and they published that proudly. Include a **"what this doesn't do"** section. Do not oversell autonomy.

6. **⚠️ Don't rebuild Agent Studio.** Dispute response, subscription recovery, abandoned cart, cashflow forecasting, RTO shielding are ALL already shipped — the panel maintains the real versions. Either go adjacent (**Downtime API is conspicuously unexploited**; **Route** for multi-party settlement; **Smart Collect** reconciliation) or explicitly acknowledge Agent Studio and argue what you do differently. Name-checking their production systems demonstrates the homework their hiring guidance rewards.

7. **Sanctioned stacks: Claude Agent SDK (Agent Studio) and LangGraph (Viveka, Gateway Agent). Go where you touch infra.** **Building on `razorpay-mcp-server` as your tool layer is the highest-signal, lowest-effort credibility move available.**

8. **Your repo is graded as an agent-ready repo** by the people who wrote the Agent Readiness rubric: **Context, Testing, CI/CD at 80%.** → real README with architecture diagram, a `CLAUDE.md`/`AGENTS.md` context file, actual tests, green CI badge. Cheap, disproportionately weighted.

9. **Solo is fine, no incumbent to beat, but no calibration reference either** → the blog posts ARE the calibration.

10. **Accessibility/underserved framing is a known soft spot** (DrishtiPay/HaRBInger).

---

## GAPS — explicitly not found (do not fabricate around these)

1. No prior edition exists. No past winners, alumni, or archived submissions.
2. **No Razorpay newsroom/press release for the Buildathon** — aggregator blogs are *paraphrasing*. Where they conflict with https://razorpay.com/buildathon/, **trust the landing page.**
3. **No post by any identifiable Razorpay employee** adding detail beyond the landing page.
4. **No per-track deliverables or "performance bars" published.** Landing page says they exist; content is nowhere public. Velonx's track table is *interpretation*, not Razorpay wording.
5. **Team size rules, project-window length, IP ownership, round dates: all unpublished.** Round dates communicated only to shortlisted candidates post-deadline.
6. FTX 2020 + all 9 HACK:O(n) winning project names never published; Devfolio gallery empty.
7. **403-blocked:** both TipRanks articles, Medium blog root + Viveka on Medium, Medianama Agent Studio critique, hackORtech listing. (Substance recovered via DEV mirror + ZenML.)
8. **Unverified:** a "Razorpay AI for Good Hackathon 2026" appeared once on an aggregator that 403'd. Not on any Razorpay property. Probably an artifact.
9. **MCP server docs never explicitly state test-mode support.** Test-key compatibility is strong inference (shared base URL, key-based auth), **not documented — verify empirically before designing around it.**
10. **Test-mode feature-parity table didn't render.** **Verify Route and Magic Checkout test-mode availability on your own dashboard** — some products need per-account activation even in test mode.
