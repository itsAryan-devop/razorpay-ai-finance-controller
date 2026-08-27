"""Pipeline guardrail tests: dry-run applies nothing, execute is gated, and
re-executing an already-applied decision is idempotent (no double-apply)."""
import os

import audit
import pipeline


def test_dry_run_applies_nothing(tmp_path):
    p = os.path.join(tmp_path, "log.jsonl")
    r = pipeline.run(dry_run=True, commit=True, reset_audit=True, audit_path=p)
    assert r["applied"] == 0
    assert r["skipped"] == 0
    assert all(e["action"] == "PROPOSED" for e in r["audit"]["rows"])


def test_execute_applies_high_confidence_and_chain_verifies(tmp_path):
    p = os.path.join(tmp_path, "log.jsonl")
    r = pipeline.run(dry_run=False, commit=True, reset_audit=True, audit_path=p)
    assert r["applied"] >= 1                       # at least the conf-1.0 AUTO_RESOLVE
    ok, n = audit.verify(p)
    assert ok and n == len(r["records"])           # every decision committed, chain intact


def test_reexecute_is_idempotent(tmp_path):
    p = os.path.join(tmp_path, "log.jsonl")
    first = pipeline.run(dry_run=False, commit=True, reset_audit=True, audit_path=p)
    applied_first = first["applied"]
    assert applied_first >= 1

    second = pipeline.run(dry_run=False, commit=True, reset_audit=False, audit_path=p)
    assert second["applied"] == 0                  # nothing applied twice
    assert second["skipped"] == applied_first      # they were skipped as idempotent

    ok, _ = audit.verify(p)
    assert ok
    # the set of applied entities did not grow on the second run
    assert len(audit.applied_entities(p)) == applied_first
