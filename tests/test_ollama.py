"""Ollama provider tests — WITHOUT requiring a running Ollama server (CI-safe).
They point the client at a dead port and assert the pipeline still completes via the
heuristic fallback: a missing local model must never hang or break a keyless run."""
import csv
import os

import pytest

import matcher
import llm_handler

DEAD = "http://127.0.0.1:9"          # nothing listens here


@pytest.fixture(autouse=True)
def _fast_and_dead(monkeypatch):
    """Point every provider probe/call at a closed port with tiny timeouts, so these
    tests are instant and OS-independent (a dead port may DROP rather than refuse on
    Windows, so we cap the wait instead of relying on a fast refusal)."""
    monkeypatch.setattr(llm_handler, "OLLAMA_HOST", DEAD)
    monkeypatch.setattr(llm_handler, "OLLAMA_PROBE_TIMEOUT", 0.05)
    monkeypatch.setattr(llm_handler, "OLLAMA_CONNECT_TIMEOUT", 0.05)
    llm_handler._PROBE_CACHE.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _true_ghosts():
    notes = {}
    with open(os.path.join(matcher.D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    return notes


def test_ollama_choose_returns_none_when_server_down():
    assert llm_handler._ollama_choose("RN482", "", 99900, [("g1", "NEFT/RN482")]) is None


def test_active_provider_downgrades_to_heuristic():
    assert llm_handler._active_provider("heuristic") == "heuristic"
    assert llm_handler._active_provider("ollama") == "heuristic"   # server down
    assert llm_handler._active_provider("auto") == "heuristic"     # nothing available


def test_resolve_falls_back_to_heuristic_without_server(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    records = llm_handler.resolve_escalations(results, ledger, recon)

    assert records
    assert all(x["engine"] == "heuristic" for x in records)        # honest engine label
    assert all(x["route"] in ("AUTO_RESOLVE", "FLAG", "ESCALATE") for x in records)

    truth = _true_ghosts()                                         # pairings still correct
    for r in results:
        if r.entity_id in truth and r.matched_entity:
            assert r.matched_entity == truth[r.entity_id]
