"""
app.py — Streamlit UI for the AI Finance Controller (Track 04).

A thin, honest read-layer over the reconciliation engine. It runs the SAME
matcher + handler + guardrail pipeline in-process (src/pipeline.py:run) and
renders it, so every number on screen is recomputed live — never hardcoded.

Three views:
  1. Reconciliation dashboard  — headline metrics, exception mix, per-class P/R
  2. Exception queue            — the typed queue + the escalated→handler decisions
  3. Audit-log viewer           — the hash-chained trail + a live integrity check

The engine is deterministic (seed 42) and the LLM handler falls back to a
transparent heuristic when no ANTHROPIC_API_KEY is set, so this runs keyless.

Run:  streamlit run app.py
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import generate_data  # noqa: E402
import matcher        # noqa: E402
import pipeline       # noqa: E402
import audit          # noqa: E402

DATA = matcher.D
LEDGER = os.path.join(DATA, "ledger.csv")


def rupees(paise) -> str:
    try:
        return f"₹{int(paise) / 100:,.2f}"
    except (TypeError, ValueError):
        return "—"


def ensure_data():
    if not os.path.exists(LEDGER):
        with st.spinner("Generating deterministic dataset (seed 42)…"):
            generate_data.generate()


st.set_page_config(page_title="AI Finance Controller — Reconciliation",
                   page_icon="\U0001f9fe", layout="wide")

ensure_data()

# --- guardrail state: dry-run by default, execute is a deliberate, per-session action ---
if "execute" not in st.session_state:
    st.session_state.execute = False

# The engine is ~1ms; re-run it every render so the UI is always consistent with disk.
result = pipeline.run(dry_run=not st.session_state.execute)
m = result["metrics"]
results = result["results"]

# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### AI Finance Controller")
    st.caption("Razorpay AI Buildathon 2026 · Track 04 · settlement reconciliation")

    llm_on = bool(os.getenv("ANTHROPIC_API_KEY"))
    st.markdown(
        f"**Handler engine:** {'LLM (Anthropic)' if llm_on else 'heuristic (keyless)'}  \n"
        f"**Dataset:** seed 42, synthetic  \n"
        f"**Records:** {result['n_records']} ledger + recon rows"
    )

    st.divider()
    st.markdown("#### Run controls")
    if st.button("\U0001f504 Re-run reconciliation", use_container_width=True):
        st.rerun()

    st.markdown("#### Execute gate")
    if st.session_state.execute:
        st.warning("EXECUTE mode — high-confidence auto-resolutions are applied.")
        if st.button("↩️ Reset to dry-run", use_container_width=True):
            st.session_state.execute = False
            st.rerun()
    else:
        st.info("DRY-RUN (default) — nothing is applied; every decision is proposed.")
        confirm = st.checkbox("I understand this applies auto-resolutions")
        if st.button("▶️ Apply auto-resolutions", disabled=not confirm,
                     use_container_width=True):
            st.session_state.execute = True
            st.rerun()
    st.caption("Bounded & gated: only AUTO_RESOLVE (confidence ≥ 0.75) can apply, "
               "and only in EXECUTE mode. FLAG / ESCALATE always wait for a human.")

# ------------------------------------------------------------------------------- header
mode = result["mode"]
badge = "\U0001f7e2 DRY-RUN" if mode == "DRY-RUN" else "\U0001f534 EXECUTE"
st.title("Settlement Reconciliation")
st.markdown(
    f"Mode **{badge}** — {result['applied']} applied, {result['held']} held for "
    f"human review. The LLM *reads*; deterministic code does the math."
)

tab_dash, tab_queue, tab_audit = st.tabs(
    ["\U0001f4ca Dashboard", "\U0001f4cb Exception queue", "\U0001f512 Audit log"])

# ============================================================================ DASHBOARD
with tab_dash:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Classification accuracy", f"{m['accuracy']:.3f}",
              help=f"{m['correct']}/{m['total']} entities classified with the correct "
                   "exception type. Deliberately < 1.0 — see the honesty note below.")
    c2.metric("Reconciliation match rate", f"{m['match_rate']:.3f}",
              help=f"{m['matched']}/{m['ledger_total']} ledger orders tied to a "
                   "settlement (the rest are genuinely missing credits).")
    pr = result["pairing"]
    c3.metric("Misattribution pairing", f"{pr['after']}/{pr['total']}",
              delta=f"+{pr['after'] - pr['before']} vs rules ({pr['before']}/{pr['total']})",
              help="Ambiguous credits the rules escalated, then the handler resolved.")
    c4.metric("Throughput", f"{result['throughput']:,.0f} rec/s",
              help=f"{result['n_records']} records reconciled in "
                   f"{result['elapsed'] * 1000:.1f} ms (in-memory deterministic matcher).")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.markdown("#### Exception mix (as classified)")
        counts = pd.Series([r.label for r in results]).value_counts()
        counts = counts.reindex(matcher.EXCEPTION_LABELS).fillna(0).astype(int)
        st.bar_chart(counts, height=300, color="#528FF0")

    with right:
        st.markdown("#### EXTRA_CREDIT queue precision")
        ec_before = m["extra_credit_precision"]
        ec = result["extra_credit_after"]
        d1, d2 = st.columns(2)
        d1.metric("rules only", f"{ec_before:.2f}",
                  help=f"{m['extra_credit_tp']}/{m['extra_credit_predicted']} flagged "
                       "as unexplained money are truly orphan credits.")
        d2.metric("after handler", f"{ec['precision']:.2f}",
                  delta=f"{ec['reclassified']} paired",
                  help=f"{ec['tp']}/{ec['predicted']} after the handler paired "
                       "colliding credits to their true order.")
        st.caption("The colliding credits the rules couldn't place leak into "
                   "EXTRA_CREDIT (honest cost of not guessing). The handler pairs "
                   "them to their order, so they are no longer 'unexplained money'.")

    st.divider()
    st.markdown("#### Per-class precision / recall")
    pc = pd.DataFrame(
        [{"exception type": L,
          "precision": round(m["per_class"][L]["precision"], 2),
          "recall": round(m["per_class"][L]["recall"], 2),
          "support": m["per_class"][L]["support"]}
         for L in matcher.EXCEPTION_LABELS]
    ).set_index("exception type")
    st.dataframe(pc, use_container_width=True)

    st.info(
        "**Why not 100%?** On self-generated data a perfect score would only prove "
        "the matcher inverts the generator — a tell, not an achievement. The honest "
        "difficulty lives in *misattributed credits* with colliding amounts; the "
        "matcher escalates those rather than guessing, and the handler resolves them "
        "with a confidence-gated, audited decision. The test suite even asserts "
        "accuracy `< 1.0`, so a tautological 100% turns CI red.")

# ======================================================================= EXCEPTION QUEUE
with tab_queue:
    st.markdown("#### Typed exception queue")
    st.caption("The reconciler's honest output: everything that is not a clean match, "
               "typed and routed. Ambiguous collisions are ESCALATE, not a guess.")

    exc = [r for r in results if r.label != "CLEAN"]
    types = sorted({r.label for r in exc})
    routes = sorted({r.route for r in exc})

    f1, f2 = st.columns(2)
    sel_types = f1.multiselect("Filter by exception type", types, default=types)
    sel_routes = f2.multiselect("Filter by route", routes, default=routes)

    rows = []
    for r in exc:
        if r.label not in sel_types or r.route not in sel_routes:
            continue
        rows.append({
            "entity_id": r.entity_id,
            "exception_type": r.label,
            "route": r.route,
            "amount": rupees(r.evidence.get("amount")) if "amount" in r.evidence else "—",
            "paired_to": r.matched_entity or "—",
            "settlement_id": r.matched_settlement_id or "—",
            "reason": r.reason,
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"reason": st.column_config.TextColumn(width="large")})
    st.caption(f"{len(rows)} of {len(exc)} exceptions shown "
               f"({len(results) - len(exc)} clean matches hidden).")

    st.divider()
    st.markdown("#### Escalated → handler decisions")
    st.caption("The residue the deterministic rules refused to guess. The handler "
               "weighs a noisy bank-narration signal and proposes a pairing + "
               "confidence + justification. Routing is confidence-gated.")
    if result["records"]:
        hrows = [{
            "entity_id": rec["entity_id"],
            "route": rec["route"],
            "confidence": rec["confidence"],
            "engine": rec["engine"],
            "paired_to": rec["chosen"],
            "justification": rec["reason"],
        } for rec in result["records"]]
        st.dataframe(pd.DataFrame(hrows), use_container_width=True, hide_index=True,
                     column_config={"justification":
                                    st.column_config.TextColumn(width="large")})
    else:
        st.write("No escalated cases in this run.")

# ========================================================================== AUDIT VIEWER
with tab_audit:
    st.markdown("#### Hash-chained audit log")
    st.caption("Every money-affecting decision is appended to a tamper-evident, "
               "SHA-256 hash-chained log. Editing any past entry breaks every "
               "later link — there is a test that proves it.")

    a = result["audit"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Entries", a["count"])
    c2.metric("Mode", mode)
    c3.metric("Applied / held", f"{result['applied']} / {result['held']}")

    if st.button("\U0001f50e Verify chain integrity"):
        ok, count = audit.verify(a["path"])
        if ok:
            st.success(f"✅ Integrity OK — all {count} entries verify against "
                       "the recomputed SHA-256 chain.")
        else:
            st.error(f"❌ BROKEN — chain diverges at entry {count}.")

    arows = []
    for i, entry in enumerate(a["rows"]):
        rec = entry
        arows.append({
            "#": i,
            "action": rec["action"],
            "route": rec["route"],
            "confidence": rec["confidence"],
            "entity_id": rec["entity_id"],
            "engine": rec["engine"],
            "reason": rec["reason"],
        })
    if arows:
        st.dataframe(pd.DataFrame(arows), use_container_width=True, hide_index=True,
                     column_config={"reason": st.column_config.TextColumn(width="large")})
    else:
        st.write("No audit entries in this run.")

    st.caption("Maps to RBI FREE-AI: Accountability and Understandable-by-Design "
               "(a replayable, non-repudiable trail), with humans retaining final "
               "authority (the execute gate).")
