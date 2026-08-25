"""Exception-handler tests (keyless heuristic path — deterministic, no API needed)."""
import csv
import os

import matcher
import llm_handler


def _true_ghosts():
    notes = {}
    with open(os.path.join(matcher.D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    return notes


def test_handler_resolves_escalated_residue():
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    escalated_before = [r for r in results if r.route == "ESCALATE"]
    assert escalated_before, "fixture should contain escalated ambiguity"

    records = llm_handler.resolve_escalations(results, ledger, recon, use_llm=False)
    assert len(records) == len(escalated_before)
    assert all(x["route"] in ("AUTO_RESOLVE", "FLAG", "ESCALATE") for x in records)


def test_handler_pairings_are_correct_when_resolved():
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    truth = _true_ghosts()
    llm_handler.resolve_escalations(results, ledger, recon, use_llm=False)
    # any misattribution the handler resolved must point at the true counterpart
    for r in results:
        if r.entity_id in truth and r.matched_entity:
            assert r.matched_entity == truth[r.entity_id]


def test_confidence_gates_routing():
    # a full-code narration must beat an initials-only one on confidence
    strong = llm_handler._heuristic_choose("RN482", [("g1", "NEFT/RN482"), ("g2", "NEFT/XX")])
    weak = llm_handler._heuristic_choose("RN482", [("g1", "NEFT/RN"), ("g2", "NEFT/YY")])
    assert strong[1] > weak[1]
