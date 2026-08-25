"""
audit.py — append-only, hash-chained audit log for every money-affecting decision.

Tamper-evident: each entry stores SHA-256(prev_hash + canonical(record)). Editing
any past record breaks every subsequent link, so `verify()` detects tampering.
This is the "explainable + auditable" guardrail Track 04 and RBI FREE-AI require:
a replayable, non-repudiable trail of what the agent decided and why.
"""
import hashlib
import json
import os

GENESIS = "GENESIS"


def _hash(prev: str, payload: str) -> str:
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


def last_hash(path: str) -> str:
    if not os.path.exists(path):
        return GENESIS
    last = GENESIS
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)["hash"]
    return last


def append(path: str, record: dict) -> str:
    prev = last_hash(path)
    payload = json.dumps(record, sort_keys=True)
    h = _hash(prev, payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"prev": prev, "hash": h, "record": record}) + "\n")
    return h


def verify(path: str) -> tuple[bool, int]:
    """Recompute the chain end to end. Returns (intact, n_entries)."""
    if not os.path.exists(path):
        return True, 0
    prev = GENESIS
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            payload = json.dumps(entry["record"], sort_keys=True)
            if entry["prev"] != prev or entry["hash"] != _hash(prev, payload):
                return False, n
            prev = entry["hash"]
            n += 1
    return True, n
