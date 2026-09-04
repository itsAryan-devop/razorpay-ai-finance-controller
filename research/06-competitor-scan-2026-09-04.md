# GitHub competitor scan (2026-09-04) — Track 04 reconciliation submissions

Direct `gh search` + repo/README inspection. **This overturns the earlier "no public
Track 04 rival found" conclusion (research/05).** With the deadline ~1 day out, the space
is now crowded: many public Razorpay-Buildathon reconciliation repos exist. Everything
below was read from the actual repos, cited by name.

## The landscape (real repos found, Track 04 reconciliation)
Salil360-cyber/razorpay-reconciliation · adithyaathreya2264/payment-reconciliation-agent ·
deepthi1884-sys/settlement-reconciliation-agent · IshwarRajChauhan/settlement-reconciliation-agent ·
sanskruti26052/…-agent · simrankaurgill1820-hash/-razorpay-reconciliation-agent ·
Hansika-A, piyushrajclr-sys (copilot), mddakhole-spec, kirthii07, Varshatolani14,
DHRUMIL932/ReaconAI, TAYAB-HUB/RazorpayBuildathon, Kridha24, Adwika-95/LedgerLens,
PriyaPandey27/Auditra, Manu-47/Finanzor, monishvp2008 (NIVI) … (dozens more).
Framing is often near-identical to ours ("honest match rate", "exceptions it could not
resolve", deterministic-first + LLM-on-ambiguous, answer key).

## Two competitors that are genuinely strong (read in depth)

### adithyaathreya2264/payment-reconciliation-agent (Python, ~200KB)
- **Three-way** reconciliation: bank statement + gateway settlement + invoices (we do
  two-way: ledger vs settlement).
- **Tiered matcher**: exact → tolerance-window → **subset-sum DP (many-to-one: one
  lump settlement credit ↦ a batch of invoices)** → zero-candidate rule → LLM escalation
  → agent controller records a `DecisionTrace` per record.
- **Confidence-calibration table** — empirical accuracy per confidence band
  (auto_match ≥0.7 → 100% over n=102; needs_review; exception), checked against ground
  truth, not asserted.
- Real LLM validated: Groq `gpt-oss-120b`, **$0.0109 total**, only 9/153 records reached
  the LLM (8 right, 1 honest `insufficient_evidence` defer). 94.1% resolved with zero AI.
- Scale: 2,000 invoices / 153 bank records, seed 42. `FINAL_REPORT.md` artifact.

### deepthi1884-sys/settlement-reconciliation-agent (Python, ~185KB)
- **Three-way** (bank + settlement + order ledger), full `tests/` suite, `web.py` UI,
  `audit.py`, `ARCHITECTURE.md`.
- **Held-out is by NARRATION FORMAT, not seed** — reports every metric twice: on formats
  built-against vs **bank formats never seen**. Killer framing: deterministic rules
  84.1% default → **32.4% on unseen formats**; + hypothesis search 85%; + model 100%.
  **"The model is worth +15.0 pts on unseen formats, +0.0 on known formats" — measured.**
  That asymmetry IS their argument for using AI. (Ours: 8/11→11/11, less rigorous.)
- **Wrong matches reported as an absolute count in its own column, never averaged into
  accuracy.** ₹-attribution: "unexplained rupees: 0", "orders never settled: 8, worth
  ₹14,792", "140/140 discrepancies attributed to a named cause".

### IshwarRajChauhan/settlement-reconciliation-agent
- deterministic + fuzzy matcher, **LangGraph agent** (graph/schemas/tools), **a
  `settlement_qa_chain` — natural-language Q&A over the results**, `app.py` UI.
  (Settlement Q&A is one of Razorpay's own suggested Track-04 directions; several
  competitors + the track brief have it; we don't.)

## Honest head-to-head — where we stand

**We LEAD on production/engineering discipline (the 60%-weighted axis):**
- Dockerfile + docker-compose, **image build gated in CI** (none of the above mention Docker/CI at this depth).
- **Real `razorpay-mcp-server` wired** over MCP, live-verified (none mention MCP).
- **50 tests**; SHA-256 **hash-chained persistent audit log** + tamper test; dry-run/execute
  gate; **idempotency**; adversarial/injection suite; guard-safety CI gate; RBI FREE-AI mapping.
- Held-out generalization gate; homegrown decision-trace UI; cost tracking; free local Ollama.

**They LEAD us on reconciliation sophistication:**
- **Many-to-one / subset-sum** (batched settlements: one credit ↦ many orders) — REAL
  Razorpay behaviour, and we do 1:1 only. Biggest genuine capability gap.
- **Three-way** (bank + settlement + ledger) vs our two-way.
- **Format-level held-out** (unseen narration formats) — stronger than our seed-level.
- **Confidence-calibration-by-band table**; explicit **₹-impact aggregation**.
- **NL Settlement Q&A** (a named track direction).

## Prioritised recommendations (given ~1 day to deadline + video/push/form still to do)

**Cheap, high-signal, LOW risk — worth doing if we touch code at all:**
1. **Confidence-calibration table** — we already log confidence + have ground truth; bucket
   decisions by band and print empirical accuracy per band. Strong honesty artifact.
2. **₹-impact aggregation in the report/README** — "total reconciled ₹X, unexplained ₹0,
   N orders never settled worth ₹Y". We have paise amounts already; just aggregate + surface.
   (Matches research/02's "every finding needs a ₹ number".)
3. **Headline reframe** — show dev + held-out numbers side by side, and a crisp
   **"wrong matches: 0"** absolute-count line. Pure framing of rigor we already have.

**Genuinely valuable but HIGHER effort / risk — do NOT start with ~1 day left; note as
"future work" in ARCHITECTURE.md so we own the gap honestly:**
4. Many-to-one / subset-sum matching (the standout capability we lack).
5. Three-way reconciliation (add a bank-statement leg).
6. Format-level held-out (vary narration format, not just seed).
7. NL Settlement Q&A layer.

**Do NOT adopt:** LangGraph agent refactor (we deliberately chose bounded single-shot;
still defensible per Anthropic's own guidance — and it's our differentiation, not a gap).

## Net
We are **not clearly #1** — 2+ competitors beat us on reconciliation depth, we beat most on
production discipline. Best ROI now is the 3 cheap framing/artifact wins + honestly
documenting the deeper capabilities as costed future work, rather than half-building a
subset-sum matcher the day before the deadline.
