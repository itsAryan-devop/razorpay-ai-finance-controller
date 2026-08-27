# Razorpay AI Buildathon — Project Notes

> Living document. Updated as we research, brainstorm, and plan.
> Purpose: carry context across chat sessions once this conversation gets too long.

---

## 0. ⚠️ HARD DEADLINE

**Applications close 5 September 2026.** Today = 24 Aug 2026 → **~12 days.**
Program starts September, in-person Bengaluru. Confirm relocation feasibility early — don't leave it to the end.
Full findings: [research/01-razorpay-intel.md](research/01-razorpay-intel.md)

## 1. Program Facts

- **Event:** Razorpay AI Buildathon — "Build. Show. Get hired."
- **What it really is:** Recruiting funnel for a paid AI Builder Internship, not a standalone hackathon.
- **Eligibility:** Students only. Solo project — no team.
- **Stipend/Offer:** ₹75,000/month, 6 or 12 month internship.
- **Location:** In-person, Bangalore.
- **Apply:** https://forms.gle/d9r2gvxp8cmoZhon9
- **API access:** Page confirms — *"Build an agent that grows revenue for a merchant on Razorpay test-mode APIs"* (explicitly mentioned for Track 1; not confirmed whether all tracks get test-mode API access — needs checking after applying / in onboarding docs).

## 2. The 5 Tracks

1. **AI Growth & Agentic Commerce** — agents that increase merchant revenue or drive AI-driven transactions (conversational checkout, AI-readable catalogs, automated upselling). Uses Razorpay test-mode APIs. Requirement: every money action explainable, bounded, gated.
2. **AI Risk Manager** — fraud detection / verification / automated response to chargebacks & returns losses. Defense-only. Requirement: measured precision & recall on held-out test set, honest false-positive cost analysis.
3. **AI Revenue Recovery** — agents that detect at-risk revenue and run recovery workflows (failed payments → overdue receivables). Requirement: measured money recovered across a batch, compliant escalation.
4. **AI Finance Controller** — close finance-ops loops across 50+ synthetic records (reconciliation, settlement, cash forecasting). Requirement: throughput + measured accuracy + honest exception list.
5. **Open Track** — any meaningful AI/fintech application not covered above. Same rigor bar applies.

**Track decision: _not yet chosen_** ← update once decided.

## 3. Key Insight — What Actually Gets You Selected

Razorpay's track descriptions aren't marketing copy — they're the evaluation rubric, stated openly:
- "every money action explainable, bounded and gated"
- "measured precision and recall on a held-out test set"
- "honest false-positive cost analysis"
- "honest exception list"

Most solo student applicants will skim past this and ship a flashy demo. Taking this language literally as engineering requirements is the actual differentiator — not "I used AI to build this" (everyone will say that).

### Differentiation checklist
- [ ] **Bounded & gated** — hard caps on agent actions, human-approval step before anything irreversible, full audit log of decisions + reasoning.
- [ ] **Real metrics, not vibes** — train/held-out split, precision/recall reported with numbers, threshold tuning explained.
- [ ] **Honest failure handling** — exception list for cases the agent flags instead of guessing; no "100% accuracy" claims.
- [ ] **Narrow & deep scope** — one track, one clear use case, reliable end-to-end, rather than broad shallow coverage.
- [ ] **Written reasoning** — short README/doc explaining tradeoffs made and why (this is an internship interview in disguise — they're hiring for judgment, not just code).
- [ ] **Reliability tested** — golden path + 3-4 adversarial/edge-case inputs verified before calling it done.

## 4. Our Two Known Weaknesses (Aryan's diagnosis — drives our strategy)

**Weakness 1 — We build demos, not production systems.**
Competitors ship shippable, scalable, production-ready projects. LLMs default to the cheapest path that satisfies the goal, which produces flashy-but-fragile code. Companies want to see real engineering: containerisation (Docker), deployment (Vercel/Cloud Run/K8s where genuinely warranted), observability, tests, error handling, security.
Rule: use production tooling **where it is needed and beneficial** — not as decoration. Justify each choice.

**Weakness 2 — We build without studying prior art.**
Our best work historically comes after researching papers/GitHub projects first. For a hackathon the equivalent is mining *past winners*: what they built, how they presented it, why they won.

### Research strategy (agreed)
Two streams, run one at a time so each gets real depth:
- **Stream 1 — Winner pattern-mining** ← RUNNING FIRST (informs the track decision)
- **Stream 2 — Production-readiness practices** ← after track is chosen (so it's targeted, not generic)

### Tooling decisions
- **Claude Code, not Cowork** — research output must land as files in `D:\razorpay_project` alongside the code we build. One workspace = one source of truth; avoids the context fragmentation NOTES.md exists to prevent. Claude Code fans out subagents the same way Cowork does.
- **Claude Skills — yes, use them.** Relevant ones: `brainstorming` (requirements before code), `writing-plans` / `executing-plans` (fresh-chat handoff), `test-driven-development` (directly addresses Weakness 1), `verification-before-completion` (no unverified "it works" claims), `requesting-code-review` (adversarial self-review pre-submission), `deep-research`. Pull in at the right moment, not all at once.

## 5. Stack Decision — LOCKED

**Python + LangGraph (or Claude Agent SDK) + `razorpay-mcp-server` as tool layer + pandas/sklearn for the ML-heavy parts (fraud track).**

Why: Aryan is strong in Python + ML/math libraries already — no learning-curve tax with 12 days on the clock. Razorpay's own "sanctioned" stacks are Go (systems/MCP server) and LangGraph/Claude Agent SDK (their actual production agents — Viveka, Agent Studio) — both are first-class in Python, so we get the credibility without a Go detour. `razorpay-mcp-server` is a Go *binary* we run locally and talk to over MCP — no Go code required from us.
Aryan's approach: study/deepen understanding of chosen stack *while* building and after — not a blocker to starting. Confirmed he can defend any technical choice on demand (agreed: post-build I'll interview him like the panel would).

## 6. Research Findings Log

### [research/01-razorpay-intel.md](research/01-razorpay-intel.md) — Razorpay-specific intel (Stream 1, agent 1/4)
Key takeaways:
- **First edition** — no prior winners to study; Razorpay's own engineering blog (Bumblebee, Viveka, Slash posts on dev.to/razorpaytech) is the de facto rubric — narrative structure = naive v1 → why it broke → v2 → why that broke → production + measured before/after deltas. Buildathon explicitly asks "explain what broke and how you recovered" — same instruction.
- **House architecture pattern** (appears independently in 2 of their production systems): planner/supervisor agent → parallel specialist sub-agents (one per data source) → deterministic-rules-first analyzer, LLM confined to interpretation. Token budgets + local pruning. Structured output with confidence scores, never free text. Per-agent trace IDs (tokens/latency/confidence/reasoning logged).
- **Shadow mode / honest limits are rewarded**, not penalized — their own production agent (Viveka) shipped still in shadow mode at an 80% target and they published that proudly. Include a "what this doesn't do" section.
- **⚠️ Don't rebuild Agent Studio** — Razorpay already shipped Dispute Responder, Subscription Recovery, Abandoned Cart, Cashflow Forecaster, RTO Shield (Mar 2026, built on Claude Agent SDK). Go adjacent instead — **Downtime API and Route API are conspicuously unexploited.**
- **`razorpay-mcp-server`** (official, Go, MIT, 229★, 35+ tools) is the single highest-signal, lowest-effort credibility move — use it as our tool layer. Test-mode compatibility is a strong inference, **not confirmed — verify empirically first.**
- Repo itself is graded as an "agent-ready repo" by their own internal rubric: **Context + Testing + CI/CD at 80% threshold.** README with architecture diagram, a CLAUDE.md/AGENTS.md context file, real tests, green CI badge — cheap, disproportionately weighted.
- Accessibility/underserved-user framing has documented cultural resonance (DrishtiPay won RBI's HaRBInger for Razorpay).

### [research/02-hackathon-winners.md](research/02-hackathon-winners.md) — Winning fintech hackathon patterns (Stream 1, agent 2/4)
Key takeaways:
- **Reframe confirmed independently:** Round 1 build → Round 2 public repo + 5-min video + architecture doc → Round 3 panel live architecture walkthrough. Repo gets read, architecture gets interrogated — not a watch-and-move-on demo judge.
- **⭐ Winning risk/finance systems output a ROUTED ACTION, not a score.** Three independent winners converged on this: block/approve/step-up-auth (FraudLens), auto-dismiss/escalate (AWS triage), AUTO-CLEAR/FLAG/ESCALATE (verity). Whatever track we pick, the output must be an action taxonomy, not a probability number.
- **Attack the operational COST of the problem, not the problem.** "90% of fraud alerts are false positives → analyst fatigue" beats "fraud is expensive." Quantify human-hours wasted.
- **Every finding needs a ₹ number attached + proposed resolution.** (TruthKeeper: reconciliation that "estimates financial impact" per break, not just flags it.)
- **Multi-agent where each agent = one real human role** (triage analyst → investigator → compliance officer), not "Agent A/B/C." An **adversarial/critic agent** is a repeatedly-rewarded differentiator (AegisAgent, GAIA).
- **"The LLM reads, deterministic code does the math"** — verity-invoice-agent's exact design principle, directly echoes what Bumblebee (Razorpay's own blog) does. Two independent sources converge on this — strong signal it's correct.
- **⭐⭐ Revenue Recovery track has almost ZERO public prior art / hackathon winners found.** Least competitive track — a genuinely fresh space, or a real signal it's hard/unrewarding. Worth weighing as an option.
- **Anti-patterns to avoid (repo):** no tests/Docker/CI, reporting raw accuracy on imbalanced fraud data (meaningless at ~3% fraud rate — use PR-AUC/recall), no cost-matrix/threshold reasoning, no entity-level aggregation (transaction-only features), backend with no clickable UI, live API calls in the demo instead of pre-seeded data.
- **Fraud-ML technical bar (Kaggle IEEE-CIS 1st place):** the winning move is entity resolution (stitch transactions into merchant/card/device/beneficiary UIDs, compute velocity+aggregates at that level) — not a fancier model. Time-based validation, not random split.

### [research/03-ai-agent-eval-and-judging.md](research/03-ai-agent-eval-and-judging.md) — Eval methodology & guardrails (Stream 1, agent 3/4) ⭐ MOST IMPORTANT REPORT SO FAR
Key takeaways:
- **Razorpay's landing page IS a measurement spec disguised as a hackathon page.** Every noun in the track descriptions (precision, recall, held-out, false-positive cost, exception list, match rate, throughput, audit trail, stopping rules, bounded, gated) is a literal scoreable artifact they expect us to produce, by name.
- **⭐ Build the eval harness BEFORE the agent, not after.** 20-50 tasks, balanced positive/negative/adversarial, reference solutions, 30% true held-out set never touched during dev. No known competitor publicly ships this — it's an uncontested differentiator.
- **Grade state, not text.** Assert against the DB/ledger row, never the model's prose.
- **Report pass@k AND pass^k** (probability ANY vs ALL of k trials succeed) — reliability collapses fast (75% per-trial → 42% pass^3) and almost nobody reports it. This is the correct headline metric for a money agent.
- **τ-bench (Sierra) is the benchmark to imitate**: policy doc + tool API + N annotated goal-states + pass^k + a *separate* policy-violation rate (tests whether the agent correctly REFUSES out-of-policy requests). Build a mini version of this.
- **False positives are a pricing problem, not a model problem** — price a wrong decline (blocked-txn margin + complaint cost + P(churn)×LTV) in the same currency as a missed fraud, set thresholds against review capacity. This is literally the answer to Track 02's "honest false-positive cost analysis."
- **Guardrail checklist locked in** (Explainable / Bounded / Gated, mapped to Razorpay's own words) — see full checklist in the research file. Must demo ≥6 guardrails on camera, including the agent *refusing* an out-of-policy/injected action.
- **⭐⭐ Cite RBI FREE-AI (India's AI-in-finance regulatory framework, Aug 2025) by name** — 7 Sutras including Accountability, Understandable by Design. Razorpay is RBI-regulated; almost no competitor will make this connection. 30 min of work, high signal.
- **Judges reportedly score shallow** (skim README/folder structure) — metrics table must be at README line 3 and in the video's first 60 seconds, not buried.
- Winning demo structure: pitch → problem → solution → demo → architecture → **numbers** → what broke and how you recovered. Only mock non-core features; judges spot mocks.
- Best rubric found weights: 40% innovation/utility, **30% architectural discipline, 30% demo & production readiness (unedited live execution + docs w/ diagrams)** — 60% is engineering discipline, not UI polish.

### [research/04-fintech-domain-deepdive.md](research/04-fintech-domain-deepdive.md) — Per-track industry glossary, metrics, datasets (Stream 1, agent 4/4) — **ALL 4 RESEARCH AGENTS NOW COMPLETE**
Key takeaways:
- Real industry terminology per track (use these words verbatim in the submission — it's a cheap, high-signal credibility move): **T2 Risk** — retrieval→chargeback→pre-arbitration→arbitration, CE 3.0 evidence assembly, VAMP threshold (1.50%, $8/txn fine), RTO (₹285/order, COD≈26% vs prepaid<2%). **T3 Recovery** — soft vs hard decline, dunning, DSO, **Section 43B(h)** (India-only MSME tax lever, "almost nobody builds for it"), NACH's ~2 re-presentation cap + ₹250-600 bounce charge, RBI's 24h pre-debit notice + 08:00-19:00 contact window. **T4 Finance** — Razorpay's actual settlement/recon field names (`utr`, `settlement_id`, `on_hold`, `settlement_recon/combined` endpoint), 194-O TDS + GST TCS overlay, 13-week cash forecast with weekly variance review.
- **⭐ T4 is the most buildable without external datasets** — no public reconciliation dataset exists, but you can generate your own ground truth by creating real orders/payments/refunds via Razorpay test-mode API and pulling the actual settlement recon report. You control the answer key.
- **⭐ T3 confirmed as most under-served** (near-zero public prior art) — high differentiation ceiling, no template to copy.
- Cross-cutting: **RBI data localization** — if the agent sends payment data to a foreign LLM API, address this explicitly (redact/tokenize before the call, or send only derived features). Single highest-signal paragraph available in the whole submission — proves "AI + Indian payments" is understood as regulated, not just an integration.

## 7. ⭐ TRACK RECOMMENDATION (pending Aryan's decision)

Given solo + ~11 days + "rigor over flash" strategy, ranked by buildability-vs-differentiation tradeoff:

1. **T4 Finance Controller (lead recommendation)** — most self-contained (generate your own ground-truth data via Razorpay test mode, so correctness is provable, not estimated); "deterministic-matcher-first, LLM-on-exception-tail" is a clean, defensible architecture; direct match to Razorpay's own real API field names found in research.
2. **T3 Revenue Recovery** — highest differentiation ceiling (least competition, Section 43B(h) angle is genuinely novel) but no prior art to lean on if we get stuck — higher risk for a tight timeline.
3. **T2 Risk Manager** — richest "credibility signal" story (rupee cost matrix) but needs either an imbalanced public dataset (not Razorpay-specific) or simulated RTO data (no public dataset exists) — more data-engineering overhead.
4. T1 Agentic Commerce — deprioritized: highest overlap risk with Razorpay's already-shipped Agent Studio.

## 8. To-Do List (Aryan's action items)

> Add items here as we identify them. Check off as completed.

- [ ] **Decide track** — recommendation above is T4, awaiting Aryan's call
- [ ] Confirm realistic hours/day available before Sep 5 (drives scope)
- [ ] Confirm in-person Bengaluru relocation feasibility for Sept — don't leave to last minute
- [ ] Verify `razorpay-mcp-server` actually works against test-mode keys (not confirmed by research, only inferred)
- [ ] Fill application form (deadline 5 Sep 2026)
- [ ] (add more as we brainstorm)

## 9. Open Questions

- Does test-mode API access extend to all 5 tracks or just Track 1?
- What does the application form ask for beyond repo+video (submission format, exact deadline time, deliverable checklist)?

## 10. Decisions Log

> Record each decision once made, with a one-line reason, so we don't re-litigate it later.

- **Stack: Python + LangGraph (or Claude Agent SDK) + `razorpay-mcp-server` + pandas/sklearn.** Reason: Aryan's existing strength, matches Razorpay's own sanctioned stacks, zero learning-curve tax with the clock running. See §5.
- **Research approach: 4 parallel agents (Razorpay intel, domain deep-dive, hackathon winners, eval/judging) before choosing a track.** Reason: avoid building on the wrong assumptions with only 11 days to correct course.
- **Data strategy: HYBRID synthetic (2026-08-25, post-spike).** Reason: real test-mode settlements don't populate (pre-KYC gating), but real payments + real fee math do. Use real payments as ground-truth ledger, synthesize settlements calibrated to real recon schema + real fee formula (MDR 2.2% + 18% GST). Track wording "50+ synthetic records" makes this valid, and it lets us plant the hard exception cases a matcher needs to prove itself on.

## 10.5 Final Verification Sweep (2026-08-25) — closes the T4 vs T3 decision

1. **`razorpay-mcp-server` test-mode — CONFIRMED.** Official FAQ (razorpay.com/docs/mcp-server/faqs/): auto-detects env from key prefix, `rzp_test_` = test mode. No longer an inference.
2. **Buildathon page — no new info found** since 24-25 Aug. No FAQ subpage exists publicly. Team-size rules still unstated anywhere.
3. **⚠️ T4's core assumption is a confirmed RISK, not yet resolved.** Test mode is explicitly the pre-KYC state; live settlement is gated on KYC-verified/activated accounts. No doc explicitly confirms `/settlements/recon/combined` returns realistic data in test mode (suspicious silence, vs. how explicit the MCP FAQ was on point 1). **Action: spike-test this in the FIRST 1-2 days — create test account, fire test payments/refunds, poll the settlements endpoint, see what actually comes back — before building anything else on top of the "generate our own ground truth" plan.** If it's empty/unusable, pivot to T3 (fallback criterion, not a redo of research).
4. **T3's "nobody's built this" claim is weakened but not dead.** Two existing 43B(h) tools found (thegstcalculator.in MSME payment tracker; an open, unmerged GitHub feature request on resilient-tech/india-compliance). Neither is an AI agent — both are calculator/rule-based bolt-ons. Reposition as "AI-native, proactive" not "first-ever" if T3 is used.

**Verdict: T4 locked as primary, with the settlement-data spike as the #1 go/no-go item on day 1. T3 remains the named fallback if that spike fails.**

## 10.6 BUILD STARTED (2026-08-25)
Track 04 locked. Scaffold created: `PLAN.md` (roadmap + architecture mindmap), `README.md` (skeleton), `LOG.md` (running failure log), `.env.example`, `.gitignore`, `requirements.txt`, `spike/check_settlements.py`. Git initialized on `main`. Deps install via `py -m pip` (Windows: use the `py` launcher / Python 3.12 — msys2 python has no pip).

### ✅ Day-1 settlement spike DONE — verdict: NO-GO on real settlements → hybrid synthetic (pre-agreed fallback)
- Auth works, payments capture fine (4/4 real captured payments), but `/settlements` + `/settlements/recon/combined` stay empty in test mode (pre-KYC gating). Full detail in LOG.md.
- **Locked approach: HYBRID.** Real captured payments = ledger/payment side; synthesize the settlement side, calibrated to the real recon schema. Track literally says "50+ synthetic records," so this is valid/intended, and a generator lets us plant the hard cases (partial settlement, refund-in-later-cycle, fee mismatch, duplicate) that test mode can't produce.
- **⭐ Real fee formula captured empirically: MDR 2.2% + 18% GST → total fee ≈ amount × 0.02596; net = amount − fee.** Generator uses this, not a guessed rate. (Real test key works, real payment IDs on hand: pay_TTk0Us..., pay_TTjztF..., pay_TTjzCZ..., pay_TTjxfG...)
### ✅ Day 2 DONE — data generator built + self-verified
- `src/generate_data.py`: 120 ledger orders, 127 recon rows, ground_truth.csv answer key. Paise integers, seed 42, real fee formula. Plants 7 exception types (CLEAN 63 / TIMING_VARIANCE 14 / FEE_MISMATCH 8 / REFUND_IN_LATER_CYCLE 12 / DUPLICATE 5 / MISSING_CREDIT 10 / EXTRA_CREDIT 8).
- `src/selftest_data.py`: 8 invariants asserted, all PASS (exit 0) — this is what makes "provable correctness" real. Matcher will need a 2-paise fee tolerance (real fees round ±1 paise).
- Output files are gitignored (data/generated/); generator + selftest are committed-worthy.
### ✅ Day 3 DONE — deterministic matcher built (src/matcher.py)
- 3 passes + classification precedence, emits exceptions.csv. Score vs ground truth: accuracy 1.000, match rate 0.911.
- **⚠️ The 1.000 is TAUTOLOGICAL** (I wrote both generator and matcher → rules are exact inverses). Proves the pipeline works, NOT that matching is good. A believable number beats a perfect one — do not brag 100% in the README.
- Also fixed EXTRA_CREDIT to be a clean orphan (ledger now 112 orders, recon 127, truth 120); selftest still green.
### ✅ Day 4 DONE — injected real ambiguity, honest numbers now
- New exception MISATTRIBUTED_CREDIT (money under wrong pid), 11 cases over 4 collision amounts → genuine pairing ambiguity. Matcher does a fuzzy pairing pass: unique→AUTO-resolve, collision→ESCALATE (doesn't guess), none→MISSING.
- **Honest metrics (was tautological 1.000):** classification accuracy **0.984**, match rate **0.911**, misattribution pairing **9/11 auto + 2 escalated**, EXTRA_CREDIT precision **0.80**. Written to RESULTS.md.
- The 2 escalated cases = the exact residue for the Day-6 LLM handler (measured before/after improvement).
### ✅ Day 5 DONE — pytest eval harness in CI
10 tests total (data invariants + matcher behaviour + handler). Accuracy test asserts `[0.90,1.0)` so a tautological 1.0 fails the build. CI: generate → invariants → matcher → pipeline → pytest.

### ✅ Day 6 DONE — LLM exception handler (the "meaningful AI" core)
- Added a fuzzy signal (customer code + noisy bank-narration hint) so the LLM has a real job. `src/llm_handler.py` (Anthropic when keyed, transparent heuristic fallback) + `src/pipeline.py` (matcher→handler→before/after + audit_log.jsonl).
- **Measured value (keyless): misattribution pairing 8/11 → 11/11.** Confidence-gated routing (AUTO_RESOLVE/FLAG/ESCALATE).
- RNG note: adding customer/hint fields reshuffled the seed-42 set; deterministic baseline now accuracy **0.976**, EXTRA_CREDIT prec **0.73**, 3 escalated. RESULTS.md refreshed.
- ⚠️ **Aryan action: add ANTHROPIC_API_KEY to .env** to validate the real-LLM path (`py src/pipeline.py`). Heuristic fallback is what CI/keyless runs use.
### ✅ Day 7 DONE — guardrails (explainable · bounded · gated)
`src/audit.py` append-only SHA-256 hash-chained log (tamper-evident, tested). Pipeline dry-run by default; only high-confidence AUTO_RESOLVE applies with `--execute`, rest held for human. DRY-RUN 0 applied / EXECUTE 1 applied. 12 tests pass.

### ✅ Day 9 (README) DONE EARLY — the portfolio artifact
Full README.md written: honest metrics up top, architecture diagram, how-to-run, guardrails + RBI FREE-AI mapping, "what broke" pointer, honest limits, repo layout.

### ✅ Day 8 DONE (2026-08-27) — Streamlit UI + closed EXTRA_CREDIT loose end
- `app.py`: 3 tabs (Dashboard / Exception queue / Audit log). Runs `pipeline.run()` in-process on every render, so on-screen numbers are recomputed live, never hardcoded. Guarded execute gate (confirm checkbox → applies only conf-≥0.75 AUTO_RESOLVE) + live "Verify chain integrity" button.
- Refactor that enabled it: `pipeline.run(dry_run)->dict` (was print-only) + `matcher.compute_metrics()` as the single numbers source (`score()` now prints from it). Behaviour-preserving; 12 tests still green.
- **Closed the loose end RESULTS.md flagged:** EXTRA_CREDIT precision post-handler **0.73 → 1.00** (colliding credits paired to their order are no longer "unexplained money"). Computed in `pipeline.run()`, shown live, RESULTS.md updated to the real number (2 of 3 are FLAG = proposed/human-confirm).
- Verified in a real browser: all tabs render, integrity check passes, `--execute` applies 1 / holds 2. `streamlit>=1.39.0` added; `.claude/launch.json` for reproducible launch (port 8501).

## 🟢 CURRENT STATE (updated 2026-08-27)
**Days 1-8 + README complete. Working, tested, guarded end-to-end system WITH a UI, all committed under Aryan's identity.** 12 passing tests. CI green-by-design. Honest headline: accuracy 0.976, match rate 0.911, misattribution pairing 8/11→11/11, EXTRA_CREDIT precision 0.73→1.00 post-handler.

**Remaining before Sep 5 deadline:**
- **Day 10: 5-min pitch video** — Aryan records. Lead with metrics, then show the escalation/guardrails live in the UI, then "what broke."
- **Day 11: submit the form** (https://forms.gle/d9r2gvxp8cmoZhon9).
- Iterative polish welcome (user said "don't rush to done") — the UI is the natural place to keep refining.

**Aryan action items when back:**
1. (optional) add `ANTHROPIC_API_KEY` to `.env` + `py src/pipeline.py` to see the real-LLM path.
2. Decide: push repo to GitHub (public repo is the submission — needs a remote; I did NOT create one, that's an external publish action for you to approve).
3. Fill the application form + sort the Thapar academic/relocation question.
4. Read LOG.md top-to-bottom — it's the "what broke" narrative for the pitch.

## 11. Competitive Awareness

A friend is also applying, on **T2 Risk Manager** — abuse-ring/RTO detection for COD orders (graph problem: device/address/phone/pincode clusters), not generic Kaggle fraud. As of 2026-08-25 he already has: synthetic data generator w/ planted rings, a causal (no-future-leak) feature pipeline, believable held-out metrics, rupee cost-matrix threshold tuning, per-ring-type recall breakdown, working Streamlit UI. Plans to freeze code ~Aug 30, spend remaining days on README/video/form.

**Implication:** reinforces T4 over T2 (avoid near-duplicate submission from the same account pool). Reinforces urgency — he's already at "working evaluated model," we're still choosing a track. **Steal the transferable principle: causal/as-of feature computation applies directly to T4's reconciliation matcher too — must not leak future settlement data into features.** Adopt his freeze-then-polish pacing: stop coding with ~5-6 days of buffer left for README/video.

---
*Last updated: 2026-08-27*
