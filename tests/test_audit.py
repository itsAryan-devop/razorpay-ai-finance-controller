"""Audit-log guardrail tests: the chain must be verifiable and tamper-evident."""
import json
import os

import audit


def test_chain_appends_and_verifies(tmp_path):
    p = os.path.join(tmp_path, "log.jsonl")
    audit.append(p, {"decision": "A", "amount": 100})
    audit.append(p, {"decision": "B", "amount": 200})
    ok, n = audit.verify(p)
    assert ok and n == 2


def test_tampering_breaks_the_chain(tmp_path):
    p = os.path.join(tmp_path, "log.jsonl")
    audit.append(p, {"decision": "A", "amount": 100})
    audit.append(p, {"decision": "B", "amount": 200})

    # edit a past record's payload (the classic "just fix the number" attack)
    lines = open(p, encoding="utf-8").read().splitlines()
    first = json.loads(lines[0])
    first["record"]["amount"] = 999
    lines[0] = json.dumps(first)
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    ok, _ = audit.verify(p)
    assert not ok, "tampering with history must break the hash chain"
