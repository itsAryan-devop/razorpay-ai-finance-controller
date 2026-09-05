"""
Format-level held-out tests — the narration reader must generalize across bank-narration
FORMATS, not just the one style it was tuned on ("NEFT/{code}").

These lock in three things:
  1. the strict (as-tuned) reader really does collapse on unseen formats — so the held-out
     is genuine, not a straw man;
  2. the shipped normalized reader recovers the code-embedded unseen formats deterministically;
  3. nothing is ever mis-paired — an unreadable format ESCALATES, it does not guess;
  4. the _norm fix keeps the verify-guard from rejecting a CORRECT LLM pick on an unseen
     format (the bug that building this feature surfaced).
"""
import csv
import os
import re

import pytest

import matcher
import llm_handler
import generate_data
import eval_formats


@pytest.fixture(autouse=True)
def _isolate_probe(monkeypatch):
    """Keep the Ollama reachability probe from leaking across tests: clear its cache before
    and after each test, and cap the probe timeout so a real dead-port probe (in a no-Ollama
    CI run) returns instantly instead of waiting out the default. Without this, the mocked
    success test would leave `available=True` cached and the gate test would then make real
    LLM calls to a dead port with long timeouts."""
    llm_handler._PROBE_CACHE.clear()
    monkeypatch.setattr(llm_handler, "OLLAMA_HOST", "http://127.0.0.1:9")  # dead port: never
    monkeypatch.setattr(llm_handler, "OLLAMA_PROBE_TIMEOUT", 0.05)          # hit a real local
    monkeypatch.setattr(llm_handler, "OLLAMA_CONNECT_TIMEOUT", 0.05)        # Ollama, so the
    yield                                                                    # suite is fast +
    llm_handler._PROBE_CACHE.clear()                                         # deterministic


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _recall(fmt, sim_fn):
    return eval_formats._score_format(fmt, "heuristic", sim_fn)


def test_format_fixture_integrity():
    """5 narration formats x 12 misattribution cases, all money integer paise, truth keyed
    (format, payment_id) with exactly one seen format."""
    seen = [f for f, (_r, s) in generate_data.NARRATION_FORMATS.items() if s]
    assert seen == ["dev_neft"]                                   # exactly one seen format
    truth = eval_formats._load_format_truth()
    assert set(truth) == set(generate_data.NARRATION_FORMATS)
    for fmt in generate_data.NARRATION_FORMATS:
        assert len(truth[fmt]) == generate_data.FORMAT_N
        ledger, recon = eval_formats._load_format(fmt)
        for row in recon:
            assert int(row["amount"]) == float(row["amount"])    # integer paise, never float


def test_strict_reader_collapses_on_unseen_casing():
    """The as-tuned case-sensitive reader scores a perfect pairing on the seen format but
    ZERO on a lowercase format — proving the held-out actually stresses format overfit."""
    assert _recall("dev_neft", eval_formats._strict_similarity)[0] == 1.0
    assert _recall("lower_imps", eval_formats._strict_similarity)[0] == 0.0


def test_normalized_reader_recovers_code_embedded_formats():
    """The shipped normalized reader generalizes across every format that still CONTAINS the
    code — case, spacing, and delimiter variants alike — with full recall, no model needed."""
    for fmt in ("dev_neft", "lower_imps", "spaced", "hyphen_upi"):
        recall, _c, wrong, _e, _n = _recall(fmt, llm_handler._similarity)
        assert recall == 1.0, f"normalized reader should fully recover {fmt}"
        assert wrong == 0


def test_normalized_beats_strict_on_unseen_mean():
    """Aggregate the finding: on unseen formats the normalized reader strictly out-recalls
    the as-tuned reader (the whole reason the _norm fix exists)."""
    unseen = [f for f, (_r, s) in generate_data.NARRATION_FORMATS.items() if not s]
    strict = sum(_recall(f, eval_formats._strict_similarity)[0] for f in unseen) / len(unseen)
    norm = sum(_recall(f, llm_handler._similarity)[0] for f in unseen) / len(unseen)
    assert norm > strict


def test_name_only_escalates_never_mispairs():
    """A narration carrying only the customer NAME (no code) is beyond any code-only reader.
    The honest behaviour is to ESCALATE every case, not to mis-pair by a spurious signal."""
    recall, _c, wrong, escalated, n = _recall("name_only", llm_handler._similarity)
    assert wrong == 0                                            # never guesses
    assert escalated == n                                        # all deferred to a human


def test_no_wrong_pairings_any_reader_any_format():
    """Across every format and both deterministic readers: zero confidently-wrong pairings.
    Format brittleness must always surface as an escalation, never as misrouted money."""
    for fmt in generate_data.NARRATION_FORMATS:
        for sim in (eval_formats._strict_similarity, llm_handler._similarity):
            assert _recall(fmt, sim)[2] == 0


def test_llm_pick_on_unseen_format_survives_the_guard(monkeypatch):
    """Regression for the fix this feature surfaced: on an UNSEEN (lowercase) narration
    format, a competent model picks the correct credit — and the verify-guard, now that
    _similarity is format-normalized, must NOT reject that correct pick. Before the fix the
    guard's case-sensitive substring check would have rejected it and nullified the LLM."""
    import requests

    def fake_get(url, **kw):
        return _Resp({"models": [{"name": "qwen3:4b"}]}, 200)

    def fake_post(url, json=None, **kw):
        content = json["messages"][0]["content"]
        code = re.search(r"\(code (\S+?)\)", content).group(1)
        cands = re.findall(r'id=(\S+)\s+narration=("(?:[^"\\]|\\.)*")', content)
        chosen = cands[0][0]
        for cid, narr_json in cands:                            # pick the code-supported one
            if llm_handler._similarity(code, __import__("json").loads(narr_json)) > 0:
                chosen = cid
                break
        reply = {"chosen": chosen, "confidence": 0.9, "reason": "narration supports it"}
        return _Resp({"message": {"content": __import__("json").dumps(reply)}}, 200)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    llm_handler._PROBE_CACHE.clear()

    ledger, recon = eval_formats._load_format("lower_imps")
    truth = eval_formats._load_format_truth()["lower_imps"]
    results = matcher.reconcile(ledger, recon)
    records = llm_handler.resolve_escalations(results, ledger, recon, provider="ollama")

    assert records and all(x["engine"] == "ollama" for x in records)     # LLM actually used
    assert all(not x["guard_rejected"] for x in records)                 # guard did NOT nullify
    by_pid = {r.entity_id: r for r in results}
    for pid, want in truth.items():
        assert by_pid[pid].matched_entity == want                        # and it's correct


def test_format_generalization_gate_passes():
    assert eval_formats.main() == 0
