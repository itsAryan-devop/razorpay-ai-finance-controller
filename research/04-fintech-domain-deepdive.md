# Research 02 — Fintech Domain Deep-Dive (per track)

*Research completed 2026-08-24. Full findings with sources.*

Evaluation parameters per public write-ups: **Problem Taste, Build Quality, AI Judgment, Failure Recovery.** Round 2 = public repo + 5-min pitch + architecture doc, explicitly explaining what broke and how you fixed it. "Problem Taste" = domain understanding, which is what this doc is for. "Failure Recovery" = they want the messy paths (declines, disputes, exceptions, partial settlements), not the happy path.
Sources: https://velonx.in/blog/razorpay-ai-buildathon-2026-tracks-eligibility-stipend-selection-process · https://www.placement-officer.com/2026/08/razorpay-ai-buildathon-2026-build-ai.html

---

# TRACK 1 — AI Growth & Agentic Commerce

## State of the art (Aug 2026) — a standards war, 4 live stacks

| Layer | Standard | Owner | Status |
|---|---|---|---|
| Checkout/catalog | **ACP** (Agentic Commerce Protocol) | OpenAI + Stripe (+Meta) | Apache-2.0, live, latest `2026-04-17` adds cart/feed/orders/auth/MCP |
| Checkout/catalog | **UCP** (Universal Commerce Protocol) | Google | Live for eligible US merchants, global rollout through 2026 |
| Authorization/consent | **AP2** (Agent Payments Protocol) | Google + 60 partners | v0.2.0, April 2026 |
| Card rails | **Visa Intelligent Commerce / TAP**, **Mastercard Agent Pay** | Visa, Mastercard | Converging on AP2 compat by mid-2026 |
| Agent identity | **Web Bot Auth** | Cloudflare/IETF | Auth foundation for Visa TAP & Mastercard Agent Pay |
| Micropayments | **x402** | Coinbase/Cloudflare, now Linux Foundation | 119M+ txns on Base, ~$600M annualized (Mar 2026) |
| India | **UAP** (Unified Agent Protocol) | NPCI | In development, needs RBI approval |

Key sources: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol · https://docs.stripe.com/agentic-commerce/acp · https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol · https://ucp.dev/ · https://blog.cloudflare.com/secure-agentic-commerce/

## Glossary (say these words)

- **Agentic checkout** — create/update/complete a checkout session (ACP)
- **Merchant of record (MoR)** — stays with the business, not the agent. **Most demos get this wrong.**
- **Delegate payment / delegate authentication** — agent uses a shared payment token via a payment handler; OAuth2 lets the agent act on the buyer's behalf
- **Capability negotiation** — merchant declares supported ACP features
- **`/.well-known/ucp` manifest** — standardized JSON discovery doc; merchant declares services/capabilities/endpoints/payment config
- **Bindings** — same capability exposed over REST, A2A, or **MCP**
- **Mandate (AP2)** — tamper-proof signed contract, a **W3C Verifiable Credential**. Three kinds: Intent Mandate, Cart Mandate, Payment Mandate. Answers: *how does a merchant prove a human authorized this agent purchase?*
- **Agentic Token (Mastercard)** — binds a tokenized card to a specific agent + merchant scope + consent policy; agent never holds the PAN
- **Visa TAP** — three signed headers per request: `Signature-Agent`, `Signature-Input`, `Signature` (Ed25519 over canonical request)
- **Web Bot Auth key insight**: legit agent traffic looks bot-like → replace heuristic bot detection with signatures
- **x402** — revives HTTP 402; server returns payment requirements, client pays USDC, retries with proof, a facilitator verifies/settles

## AI-readable product catalog — 3 stackable layers (do 2+)

1. **Structured feed file** — OpenAI Product Feed Spec: https://developers.openai.com/commerce/specs
2. **On-page structured data** — schema.org `Product` + nested `Offer` (same substrate as Google Merchant Center)
3. **Live machine endpoints** — `/.well-known/ucp` manifest, MCP catalog server, `llms.txt` (Cloudflare template: https://github.com/cloudflare/templates/tree/main/commerce-llms-txt-template)

**Insight to state out loud:** a static feed goes stale; agents need real-time price/inventory/promo APIs or the agent quotes a price the merchant can't honour → agent-caused dispute.

## India / Razorpay specifics

- **Razorpay MCP Server** — first Indian PG to ship one. https://razorpay.com/newsroom/razorpay-becomes-indias-first-payment-gateway-to-launch-mcp-server-for-instant-ai-payment-integration/
- **Razorpay Agentic Payments** — In-App Commerce (live beta), LLM integration, Voice AI. 40+ tools/APIs, PCI DSS L1.
  - **UPI Reserve Pay (live)** — consent-based pre-authorized payments within a spending limit = India's analogue of an AP2 Intent Mandate
  - **UPI Circle (coming)** — delegated/shared authorization
- **Agent Studio / Agentic Experience Platform** — built on **Claude Agent SDK**
- **NPCI UAP** — registers/verifies/authorizes agents before they transact; needs RBI approval. UPI scale: June 2026 = 22.71bn txns, ₹28.92T, 63.5% P2M.
- **Magic Checkout** — 1-click, prefills from 100M+ user network, ~5x faster. **COD Intelligence** disables COD for high-RTO shoppers using cross-brand RTO history.

## Pain points

- Catalog freshness / hallucinated offers → agent quotes stale price, merchant eats the delta or order fails
- Attribution collapse when Gemini/ChatGPT is the surface — merchant loses session/cookie/analytics
- MoR & liability ambiguity when an agent buys wrong
- Bot vs agent — WAF/bot rules block the very agents merchants want (why TAP/Web Bot Auth exists)
- **India: agentic + COD is an RTO bomb** → Reserve Pay / prepaid-only for agent orders is the credible answer

## Metrics
- ~70% of Indian cart abandonment attributed to payment failures
- Feed coverage %, feed freshness lag, offer-mismatch rate
- Agent-attributed GMV/AOV vs human sessions
- COD ≈ 65% of India orders; prepaid vs COD share
- Auth success rate: agent-initiated vs human-initiated

## Datasets (no public "agentic commerce" txn dataset exists)
- Google Merchant Center feed schema: https://support.google.com/merchants/answer/7052112
- OpenAI feed spec: https://developers.openai.com/commerce/specs/spec
- Amazon Reviews/Product Metadata (UCSD): https://amazon-reviews-2023.github.io/
- Fake Store API, Shopify sample data, schema.org/Product

## ⭐ CREDIBILITY SIGNALS — do 3-4 of these
1. Serve a real `/.well-known/ucp` manifest with declared capabilities/bindings
2. Implement ACP-shaped checkout session lifecycle (create→update→complete) on Razorpay test orders; **state explicitly the merchant remains MoR**
3. Sign agent requests with TAP-style `Signature-Agent`/`Signature-Input`/`Signature` headers (toy Ed25519 is fine) + show merchant-side verification
4. Emit an AP2-style signed Cart Mandate JSON at confirmation, store as dispute evidence, close the loop in your Track-2 dispute flow
5. Show a stale-price guard: agent quotes ₹X, merchant recomputes at session-complete, handle mismatch (re-confirm vs abort) instead of crashing
6. Gate agent orders to prepaid/UPI Reserve Pay, explain why (RTO); note UAP needs RBI approval so today's compliant pattern is a pre-authorized consent envelope with a cap, not unattended debits
7. Use the **Razorpay MCP server**, not raw REST — explain why MCP is the right binding for an LLM surface
8. Report feed coverage % and freshness lag as first-class product metrics

---

# TRACK 2 — AI Risk Manager

## Glossary (Razorpay's own dispute vocabulary — use exactly)

**Retrieval → Chargeback → Pre-Arbitration → Arbitration.** Retrieval = no money moved yet, cheapest to win. Razorpay explicitly advises: act at Retrieval/Chargeback, avoid pre-arb/arbitration. Dispute representment verdict typically 15–30 days. https://razorpay.com/docs/payments/disputes/

**Fraud typology**
- **Friendly fraud** — cardholder got goods, disputes anyway. **~75% of all disputes (Visa).**
- **Card testing / carding / BIN attack** — bot iterates PANs in a BIN range. Signature: hundreds of attempts/session, sequential PANs in one BIN, **decline:approve ratio >90%**, one device fingerprint across many cards, zero behavioural entropy. **1,000–5,000 txns in <60 min. Visa: +134% enumeration attacks 2022→2024.**
- **Velocity checks** — caps per IP/device/BIN/card per window. **BIN-range velocity catches 60–70% of card testing pre-auth.**
- **AFA** (Additional Factor of Authentication) — India's term, not "SCA"
- **TC40/TC15** — Visa fraud report / dispute record; **VAMP** = combined ratio
- **CE 3.0 (Compelling Evidence 3.0)** — merchant proves "historical footprint": 2 prior undisputed txns from same cardholder matching device/IP/address/account ID → fraud claim invalidated. **Expanded 18 Apr 2026 to non-disputed fraud.** The only compliant way to remove TC40 reports from the VAMP numerator after the fact.

**India: RTO (Return to Origin)** — COD refused/undeliverable. **COD Intelligence** suppresses COD for high-RTO shoppers.
**UPI disputes**: URCS/UDIR/TCC/RET. **Since 15 Feb 2025, URCS auto-accepts/rejects chargebacks based on TCC/RET the beneficiary bank raises next settlement cycle** (bulk uploads + UDIR only).

## Metrics (real 2026 numbers)

| Metric | Benchmark |
|---|---|
| Approval rate | General CNP 85–92%, optimized 91–96%, tokenized wallets 92–97%; India 85–90%, top performers 95%+ |
| Fraud rate | in **bps**, never % |
| Chargeback ratio | keep <0.5% (processors flag ~0.9%) |
| **VAMP threshold** | dropped 2.20%→**1.50%** on 1 Apr 2026 (US/CA/EU/APAC); floor 1,500 combined events/mo; **$8/txn fine, no warning tier** |
| Mastercard ECM | triggers at 1.5% + >100 chargebacks/mo |
| Manual review rate | Q2 2026: 2.1% |
| **RTO rate India** | D2C national avg 20–30%, fashion up to 40%, global benchmark 8–12%. **COD RTO ≈26%, prepaid <2%** |
| RTO cost/order | ₹150–300 (GoKwik 2026: ₹285 = ₹200 direct + ₹85 reverse logistics) |

## ⭐ The core idea: cost asymmetry

**False declines cost ~13x more than actual fraud** (Javelin 2021 study, cite as directional). Global false-decline losses **>$231bn in 2026**. **47% of merchants say false declines cost them sales.**

**→ Build the confusion matrix in RUPEES, not accuracy/F1:**
- Block a good COD order = lost margin + LTV
- Allow an RTO order = ₹285
- Allow fraud = txn value + chargeback fee + VAMP damage

## Datasets — Amazon Fraud Dataset Benchmark (best entry point)
https://github.com/amazon-science/fraud-dataset-benchmark

| Key | Dataset | Rows | Fraud rate | Link |
|---|---|---|---|---|
| `ieeecis` | IEEE-CIS (Vesta) | 561k train | 3.50% | kaggle.com/c/ieee-fraud-detection |
| `ccfraud` | ULB European CC | 227k | 0.18% | kaggle.com/mlg-ulb/creditcardfraud |
| `fraudecom` | Fraud e-commerce | 120k | 10.60% | kaggle.com/vbinh002/fraud-ecommerce |
| `sparknov` | Sparkov simulated | 1.3M | 5.70% | kaggle.com/kartik2112/fraud-detection |

Also: **PaySim** (mobile money): kaggle.com/datasets/ealaxi/paysim1. **No public Indian RTO dataset — simulate, be transparent, calibrate to 20-30%/COD 26%/prepaid <2%.**

## ⭐ CREDIBILITY SIGNALS
1. Score in bps + report approval rate alongside fraud rate — "low fraud at cost of high false declines is not success"
2. Rupee cost matrix, optimize decision threshold on **expected cost**, not AUC — show the threshold sweep
3. Model the VAMP numerator (TC40+TC15, 1,500 floor, 1.50%, $8/txn) as a distance-to-threshold dashboard tile
4. **Implement CE 3.0 evidence assembly** — auto-search 2 prior undisputed matching txns, auto-draft representment packet. Genuinely valuable, unautomated, LLM-shaped, highest-ROI dispute workflow in the industry right now
5. Use real phase names (retrieval→chargeback→pre_arbitration→arbitration), prioritize acting at Retrieval
6. Card-testing detector with the real signature (>90% decline ratio, sequential BIN PANs, single fingerprint, 1000-5000/hr) + BIN velocity
7. Handle UPI rail separately — TCC/RET means response window is "next settlement cycle," not 15-30 days. Almost nobody knows this.
8. Every block emits a human-readable reason (compliance feature, not nice-to-have)
9. Three-lane review queue (approve/review/decline) with a review-rate budget (~2.1%), not a binary

---

# TRACK 3 — AI Revenue Recovery

## Glossary
- **Involuntary churn** — 20-40% of subscription churn; up to 70% stems from failed transactions; ~9% revenue lost
- **Dunning** — retry + communication sequence for failed payments
- **Smart retries** — vary timing/routing by decline code, card type, issuer, expected credit dates
- **Soft decline** (retryable: insufficient funds, issuer-unavailable, do-not-honor, velocity) vs **hard decline** (never retry: stolen/closed/invalid card) — retrying hard declines burns issuer trust
- **Network tokenization** — PAN→token, auto-updates on reissue. **Account updater** (VAU/ABU) — query network for refreshed credentials pre-charge
- **DSO** = AR÷revenue×days. Buckets: current/1-30/31-60/61-90/90+

## Recovery numbers (realistic)
| Lever | Outcome |
|---|---|
| Naive fixed-schedule retries | 15-25% (basic), 40-60% (tuned) |
| Smart retries on soft declines | **70-85%** |
| Median industry recovery | ~47.6% |
| Smart timing vs fixed interval | **+25% lift** |
| Account updater alone | recovers up to 20% before any retry |
| Network tokenization auth lift | Visa +4.6%, Mastercard +2.1% |
| Soft-decline recoverability | 60-70% of card declines potentially recoverable |

## India B2B receivables — the standout lever
- Indian mid-market DSO 60-90 days vs ~47-day global avg
- **₹7.34 lakh crore locked in delayed MSME receivables** (Mar 2024), 6.4 crore MSMEs affected
- **⭐ Section 43B(h), Income Tax Act**: buyer loses tax deduction if a registered micro/small enterprise isn't paid within 15 days (no agreement) or 45 days (with agreement). **Strongest collections lever in India, almost nobody builds for it.** An agent emailing buyer's finance team citing 43B(h) exposure = genuinely novel, India-native.
- MSME ODR Portal replaced Samadhaan from 15 Oct 2025

## Compliance constraints — this is where a submission separates itself
**RBI e-mandate**: AFA at setup; **24-hour pre-debit notification** (amount, date, merchant, review/modify/cancel option); no per-debit AFA ≤₹15,000 (≤₹1 lakh for insurance/MF/credit-card bills); applies to UPI AutoPay + NACH; FASTag/NCMC exempt from 24h notice.

**NACH**: limited re-presentations per cycle (commonly up to 2), not unlimited. Bounce charge **~₹250-600+GST per failed presentation, charged by both banks**. Space retries around salary/credit dates, not immediately after failure.

**Collections conduct (RBI)**: contact only **08:00-19:00**; frequency itself can be harassment; board-approved policy required; **banned**: accessing contact list/photos/location, shaming messages, rotating-number bots. **Lender remains liable for every agent action — can't outsource accountability to an AI agent either.**

**Razorpay Payment Links reminders**: max 3 automated reminders, configurable.

## Razorpay primitives
**Subscription states**: created→authenticated→active→pending→halted→cancelled/completed/paused/expired. `pending`=auto-charge failed, retrying. `halted`=all retries exhausted. Cancelled can't restart; pausing an authenticated-not-yet-active sub cancels it.

**Error object**: `code`, `description`, `field`, `source`, `step`, `reason`, `metadata` — e.g. source:customer, step:payment_authentication, reason:invalid_otp. **This source×step×reason triple is Razorpay's native decline taxonomy — map soft/hard logic onto it.**

**Webhooks**: payment.authorized/captured/failed, payment.downtime.started/updated/resolved, + order/refund/settlement/subscription/payment_link/invoice/dispute families. `X-Razorpay-Signature` = HMAC-SHA256 of raw body. **At-least-once delivery — must be idempotent.**

Payment downtime events = don't retry into a known bank outage. Razorpay Optimizer creates temp 20-min downtimes on success-rate drop, reroutes (+10-30% approval vs single gateway).

## Datasets
- IBM Late Payment Histories: kaggle.com/datasets/hhenry/finance-factoring-ibm-late-payment-histories
- Payment Date Prediction for Invoices: kaggle.com/datasets/pradumn203
- Paper for framing (~81% accuracy achieved): arxiv.org/pdf/1912.10828
- No public decline-code corpus — use Razorpay's reason list + Stripe's (docs.stripe.com/declines/codes)

## ⭐ CREDIBILITY SIGNALS
1. Never retry a hard decline — say the rule out loud with Razorpay `reason` examples
2. Schedule retries against payday/credit-date priors (not fixed interval), quote +25% lift; skip retries during payment.downtime windows
3. Respect NACH's ~2 re-presentations, model ₹250-600 bounce charge as negative EV in retry calc
4. Implement 24h pre-debit notification as explicit state-machine step with ₹15k/₹1L thresholds
5. **Encode collections conduct as hard constraints that can BLOCK the LLM's proposed action** (08:00-19:00 window, frequency cap, max 3 reminders, no contact-list access) — directly answers "AI Judgment" criterion
6. Separate voluntary vs involuntary churn, only dun involuntary
7. Model account updater/tokenization as pre-retry step, state the lift numbers
8. **Build the Section 43B(h) clock for B2B AR** — genuinely novel lever
9. Report DSO, AR aging buckets, CEI, recovery rate by decline code — not "we recovered some payments"
10. Idempotent webhook handling, mention at-least-once delivery (Failure Recovery is a literal grading criterion)

---

# TRACK 4 — AI Finance Controller

## Glossary
- **T+2** = Razorpay standard domestic settlement (T=capture date). **RBI PA Directions 2025: T+1 banking day** now required.
- **UTR** — bank reference on settlement credit, the join key to your books
- **MDR/TDR** — ~2% on cards + 18% GST (ITC-eligible only if GST is a separate line item)
- **Partial settlement** — live balance < scheduled amount → Razorpay picks a subset summing to available balance
- **N-way matching** — internal ledger ↔ external statement ↔ GL entry (3-way); marketplace case connects buyer payment/seller payout/platform fee/bank deposit
- **Exception queue / recon break** — unmatched records: duplicate, missing credit, settlement break, timing variance, data-quality gap
- **Escrow/nodal account** — non-bank PAs must segregate merchant funds with an SCB; cross-border needs InCA + OCA

## ⭐ Razorpay's real settlement schema — use exact field names
```json
{ "id":"setl_...", "entity":"settlement", "amount":9973635, "status":"processed",
  "fees":471699, "tax":42070, "utr":"1568176960vxp0rj", "created_at":1568176960 }
```
**Settlement recon (combined)**: `GET /settlements/recon/combined?year=yyyy&month=mm` returns every payment/refund/transfer/adjustment settled, with fields: `entity_id`, `type`, `debit`, `credit`, `amount`, `fee`, `tax`, `on_hold`, `settled`, `settlement_id`, `settlement_utr`, `order_id`, `method`, `dispute_id`.

**Settlement identity**: `Net credit = Gross captured − MDR − GST on MDR − refunds − chargebacks ± adjustments − on_hold`

**Smart Collect / virtual accounts** — per-customer virtual account + IFSC + virtual UPI ID → NEFT/RTGS/IMPS/UPI receipts arrive pre-labelled with payer identity. **Structurally correct fix for bank-transfer AR reconciliation.**

## Why reconciliation is genuinely hard
1. One bank line = hundreds of transactions (net settlement collapses everything)
2. Timing skew — payment date, capture date, settlement date, bank posting date, GL date are 5 different dates; most "mismatches" are timing variance, not errors
3. Partial settlements break naive "sum the day's payments" logic
4. Refund/chargeback reversals land in a later cycle than the original sale
5. Fees/tax must be separable for ITC
6. Multi-PG merchants = N incompatible report formats
7. **India tax overlay**: Section 194-O TDS 0.1% on gross (5% w/o PAN); GST TCS 1% (Section 52 CGST, reported in GSTR-8)
8. Effort: manual recon of one settlement = 3-4 hrs; finance teams spend 2-4 days/month; revenue leakage 0.05-0.5% GPV (multi-channel retail), 2-3% (marketplaces)

## Cash forecasting
**13-week direct cash flow forecast** is the dominant instrument. **Best-in-class ≥95% accuracy**; mature process lands within 5% variance by week 4-5. Accuracy decays with horizon. **The named killer: "no variance review"** — forecast becomes a ritual never compared to actuals, same errors repeat.

## Regulatory
RBI PA Directions 2025: escrow w/ SCB, segregation, T+1 settlement, merchant compliance deadline 31 Dec 2025, re-onboarding wave from 1 Jan 2026. Data localization: all payment-system data stored only in India (processing abroad OK post-2019 FAQ, but must delete abroad within stipulated period); annual System Audit Report.

## Datasets (thinnest track for public data)
- **Best option: generate your own from Razorpay test mode** — create 50-200 orders/payments/refunds, let them settle, pull `/settlements/recon/combined`. This IS what the "50+ records" track brief points at. Test card: Mastercard `5105 1051 0510 5100`; mock bank page: **4-10 digit OTP = success, <4 digits = failure**.
- Synthetic bank statements: kaggle.com/datasets/apoorvwatsky/bank-transaction-data
- BPI Challenge 2019 (real 3-way-match process data, 1.5M events): data.4tu.nl/articles/dataset/BPI_Challenge_2019/12715853
- M5 for forecasting component: kaggle.com/c/m5-forecasting-accuracy

## ⭐ CREDIBILITY SIGNALS
1. Reconcile against the REAL recon schema field names, pulled from Razorpay test mode, not an invented CSV
2. Prove the settlement identity on a real settlement (gross→MDR→GST→refunds→chargebacks→adjustments→net), tie to UTR amount to the paisa
3. **Typed exception queue**: DUPLICATE, MISSING_CREDIT, TIMING_VARIANCE, FEE_MISMATCH, PARTIAL_SETTLEMENT, REFUND_IN_LATER_CYCLE, FX_DIFFERENCE — each with an auto-resolution rule; **LLM handles only the residue**. Deterministic matcher first, LLM only on exception tail — best "AI Judgment" signal in this track, say it explicitly.
4. Handle partial settlements deliberately, show the case in the demo
5. Separate GST as a line item, note ITC consequence; add 194-O TDS + GST TCS overlay
6. Match keys (order_id/payment_id/UTR/amount/date) with explicit tolerance window + documented match-confidence score
7. Cash forecast as 13-week direct forecast **with a weekly variance-review loop feeding back into the model**; report accuracy by week-out, target <5% by week 4-5
8. Every auto-posted correction gets an audit trail entry with the rule that fired + confidence
9. Be precise about T+1 (2025 PA Directions) vs T+2 (documented merchant cycle) — state which you're modelling
10. **Every number the LLM reports must be computed by code, not generated.** An LLM that arithmetics a trial balance is a disqualifying design — say so explicitly.

---

# TRACK 5 — Open Track (unclaimed problems spotted during research)
- Agentic-commerce dispute liability: AP2-mandate → CE3.0-evidence bridge is a genuinely open problem
- Merchant onboarding/KYC under the PA Directions 2025 re-onboarding wave
- Payment downtime prediction using `payment.downtime.*` webhooks
- UPI-native receivables via Smart Collect virtual UPI IDs
- Agent identity verification (TAP/Web Bot Auth) for the Indian stack — nobody has built this

---

# CROSS-CUTTING: Indian regulatory constraints any serious submission should respect

| Rule | Requirement | Effective |
|---|---|---|
| Authentication Mechanisms Directions 2025 | 2FA all digital payments, ≥1 factor dynamic | Comply by 1 Apr 2026 |
| Card-on-File Tokenisation | No storing PAN/CVV/expiry; tokens unique to (card, requester, merchant) | Since 1 Oct 2022 |
| e-Mandate framework | AFA + 24h pre-debit notice + ₹15k/₹1L thresholds | current |
| PA Directions 2025 | Escrow+SCB, segregation, T+1, InCA/OCA | Compliance 31 Dec 2025 |
| Data localization | Payment-system data stored only in India | Since 2018 |
| Recovery agent conduct | 08:00-19:00, no contact-list/shaming/rotating bots, lender liable | current + 2025 draft overhaul |
| Section 43B(h) | Buyer loses deduction if MSE unpaid past 15/45 days | AY2024-25+ |
| Section 194-O / 52 CGST | TDS 0.1% + GST TCS 1% (GSTR-8) | 194-O cut to 0.1% from 1 Oct 2024 |

**⭐ Highest-signal paragraph you can write**: if your agent sends payment data to a foreign LLM API, address data localization explicitly. Defensible architectures: (a) redact/tokenize before the model call, (b) send only derived features, never raw payment instructions, (c) India-region model deployment. Proves "AI + Indian payments" is understood as a regulated combination, not just an integration.

---

## GAPS — not found / unverified
- Exact ACP endpoint paths/header/field names (OpenAPI YAMLs didn't render — read directly from GitHub before coding)
- OpenAI Product Feed Spec's actual field tables didn't render
- Razorpay dispute entity enum values (`phase`/`status`/`reason_code` exact strings) and full webhook event list — docs page 404'd, check sidebar for live URL
- Razorpay subscription retry count/window — not published, don't assert a number
- No public Indian RTO or reconciliation dataset — must simulate, be transparent about it
- NPCI UAP technical spec not public — don't claim to implement it
- "13x false declines" is a 2021 Javelin study, cite as directional, not precise
- RBI FY26 fraud figures (293 cases/₹29cr vs FY25's 13,332/₹517cr) look anomalous — possible reporting-methodology change, don't build a headline claim on it
- VAMP 1.50% threshold confirmed for US/CA/EU/APAC; India domestic-acquirer treatment unconfirmed
- "Razorpay Vulcan" (transformer-based router) mentioned in one trade article, unverified against Razorpay's own materials — worth checking but verify first

## One-line summary per track
- **T1**: protocol literacy — `/.well-known/ucp`, signed agent identity, AP2 mandates, MoR stays with merchant, prepaid-only agent orders (RTO)
- **T2**: rupee cost matrix — false declines ~13x fraud cost, RTO=₹285, VAMP=$8/txn above 1.50%. Optimize expected cost, not AUC.
- **T3**: compliance-as-code — soft/hard decline split, NACH's 2 re-presentations + ₹250-600 bounce, 24h pre-debit notice, 08:00-19:00 window, Section 43B(h) lever
- **T4**: deterministic matcher first, LLM only on exception tail — real Razorpay recon fields, partial settlements handled, GST separated for ITC, 13-week forecast with variance feedback
- **Everywhere**: say something specific about RBI data localization and how your architecture handles it
