"""Ollama provider tests — WITHOUT requiring a running Ollama server (CI-safe).
They point the client at a dead port and assert the pipeline still completes via the
heuristic fallback: a missing local model must never hang or break a keyless run."""
import csv
import json
import os
import re

import pytest

import matcher
import llm_handler

DEAD = "http://127.0.0.1:9"          # nothing listens here


class _Resp:
    """Minimal stand-in for a requests.Response."""
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


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


def test_ollama_success_path_parses_and_labels_engine(monkeypatch):
    """SUCCESS path (no real server): mock Ollama's HTTP so a valid response flows all
    the way to engine='ollama'. This validates our request shape + the
    response["message"]["content"] JSON parsing that the fallback tests can't reach."""
    import requests

    def fake_get(url, **kw):                       # the reachability probe
        return _Resp({"models": [{"name": "qwen3:4b"}]}, 200)

    def fake_post(url, json=None, **kw):           # the /api/chat call — competent model
        # A competent model picks the NARRATION-SUPPORTED candidate (so it passes the
        # deterministic guard). Parse the code + candidates back out of the prompt.
        content = json["messages"][0]["content"]
        m = re.search(r"\(code (\S+?)\)", content)
        code = m.group(1) if m else ""
        cands = re.findall(r'id=(\S+)\s+narration=("(?:[^"\\]|\\.)*")', content)
        chosen = cands[0][0] if cands else "g1"
        for cid, narr_json in cands:
            narr = __import__("json").loads(narr_json)
            if code and (code in narr or code[:2] in narr):
                chosen = cid
                break
        reply = {"chosen": chosen, "confidence": 0.9, "reason": "narration supports this order"}
        return _Resp({"message": {"content": __import__("json").dumps(reply)}}, 200)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    # unit level: the choose helper parses a well-formed server reply
    out = llm_handler._ollama_choose("RN482", "", 99900, [("g1", "NEFT/RN482")])
    assert out == ("g1", 0.9, "narration supports this order")

    # end to end: every resolved case is labelled engine='ollama' and routed by confidence
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    records = llm_handler.resolve_escalations(results, ledger, recon)
    assert records and all(x["engine"] == "ollama" for x in records)
    assert all(x["route"] == "AUTO_RESOLVE" for x in records)      # conf 0.9 >= 0.75
    valid_ids = {cid for r in results for cid in r.evidence.get("candidates", [])}
    assert all(x["chosen"] in valid_ids for x in records)


def test_guard_rejects_unsupported_llm_pick(monkeypatch):
    """'The LLM reads, code verifies': if the model picks a credit whose narration does
    NOT support the order's code (an over-confident hallucination — observed live with
    qwen3), the deterministic guard rejects it and falls back to the heuristic, so a
    wrong money pairing never auto-applies."""
    import requests

    def fake_get(url, **kw):
        return _Resp({"models": [{"name": "qwen3:4b"}]}, 200)

    def fake_post(url, json=None, **kw):           # a MIScalibrated model: picks a wrong credit
        content = json["messages"][0]["content"]
        m = re.search(r"\(code (\S+?)\)", content)
        code = m.group(1) if m else ""
        cands = re.findall(r'id=(\S+)\s+narration=("(?:[^"\\]|\\.)*")', content)
        chosen = cands[0][0] if cands else "g1"
        for cid, narr_json in cands:               # deliberately choose an UNSUPPORTED credit
            narr = __import__("json").loads(narr_json)
            if not (code and (code in narr or code[:2] in narr)):
                chosen = cid
                break
        reply = {"chosen": chosen, "confidence": 0.9, "reason": "over-confident wrong pick"}
        return _Resp({"message": {"content": __import__("json").dumps(reply)}}, 200)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    records = llm_handler.resolve_escalations(results, ledger, recon)

    assert any("rejected" in r["engine"] for r in records)         # the guard fired
    truth = _true_ghosts()                                         # and pairings stay CORRECT
    for r in results:
        if r.entity_id in truth and r.matched_entity:
            assert r.matched_entity == truth[r.entity_id]
