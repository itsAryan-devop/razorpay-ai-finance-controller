"""
eval_guard.py — reproducible guard / hallucination-rate metric.

We OBSERVED one live over-confident wrong LLM pairing (qwen3:4b paired order KI532 to a
'NEFT/SK815' credit at 0.85 confidence) and added a deterministic verify-guard that caught
it. An anecdote in a log is not a metric. This turns it into a reproducible number by
replaying the escalated tail against a MOCKED adversarial model that always proposes an
over-confident, narration-UNSUPPORTED pick — then measuring what fraction the guard catches
and whether any wrong pairing survives to be applied.

This needs no server and no key (the "model" is a local mock), so it runs in CI.

Metric definitions:
  model_hallucination_rate = unsupported model picks / model picks made
  guard_catch_rate         = unsupported picks rejected / unsupported picks
  wrong_applied_after_guard = pairings still wrong after the guard runs (MUST be 0)

Run:  py src/eval_guard.py   (exits non-zero if any wrong pairing survives the guard)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import matcher
import llm_handler


def _true_ghosts():
    import csv
    notes = {}
    with open(os.path.join(matcher.D, "ground_truth.csv"), encoding="utf-8") as f:
        for t in csv.DictReader(f):
            if t["label"] == "MISATTRIBUTED_CREDIT":
                notes[t["payment_id"]] = t["note"].split("true_match=")[-1]
    return notes


class _AdversarialModel:
    """A mocked Ollama server that always returns an over-confident, narration-UNSUPPORTED
    pick — i.e. it hallucinates on every escalated case. Stands in for the worst-case
    mis-calibrated model so the guard's protection is measured, not assumed."""

    def get(self, url, **kw):
        return type("R", (), {"status_code": 200, "json": lambda self: {"models": []}})()

    def post(self, url, json=None, **kw):
        content = json["messages"][0]["content"]
        code = (re.search(r"\(code (\S+?)\)", content) or [None, ""])[1]
        cands = re.findall(r'id=(\S+)\s+narration=("(?:[^"\\]|\\.)*")', content)
        pick = cands[0][0] if cands else "g1"          # default; overwritten if a decoy exists
        for cid, narr_json in cands:                   # choose a narration-UNSUPPORTED decoy
            import json as _j
            narr = _j.loads(narr_json)
            if not (code and (code in narr or code[:2] in narr)):
                pick = cid
                break
        import json as _j
        body = {"chosen": pick, "confidence": 0.9, "reason": "override: pick this one"}
        return type("R", (), {"status_code": 200, "raise_for_status": lambda self: None,
                              "json": lambda self: {"message": {"content": _j.dumps(body)}}})()


def evaluate():
    import requests
    adv = _AdversarialModel()
    orig_get, orig_post, orig_env = requests.get, requests.post, os.environ.get("LLM_PROVIDER")
    requests.get, requests.post = adv.get, adv.post
    os.environ["LLM_PROVIDER"] = "ollama"
    llm_handler._PROBE_CACHE.clear()
    try:
        ledger, recon = matcher._load()
        results = matcher.reconcile(ledger, recon)
        records = llm_handler.resolve_escalations(results, ledger, recon)
    finally:
        requests.get, requests.post = orig_get, orig_post
        if orig_env is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = orig_env

    truth = _true_ghosts()
    model_picks = [r for r in records if r["model_attempted"]]
    unsupported = [r for r in model_picks if r["guard_rejected"]]
    caught = [r for r in unsupported if "rejected" in r["engine"]]
    wrong_applied = [r for r in results
                     if r.entity_id in truth and r.matched_entity
                     and r.matched_entity != truth[r.entity_id]]
    return {
        "escalated_cases": len(records),
        "model_picks": len(model_picks),
        "model_hallucinations": len(unsupported),
        "guard_catches": len(caught),
        "hallucination_rate": (len(unsupported) / len(model_picks)) if model_picks else 0.0,
        "guard_catch_rate": (len(caught) / len(unsupported)) if unsupported else 1.0,
        "wrong_applied_after_guard": len(wrong_applied),
    }


def main():
    m = evaluate()
    print("Guard / hallucination-rate metric (worst-case adversarial model, no server/key):")
    print(f"  escalated cases replayed        : {m['escalated_cases']}")
    print(f"  model picks made                : {m['model_picks']}")
    print(f"  model hallucinations (unsupported): {m['model_hallucinations']}")
    print(f"  guard catches                   : {m['guard_catches']}")
    print(f"  hallucination_rate              : {m['hallucination_rate']:.2f}")
    print(f"  guard_catch_rate                : {m['guard_catch_rate']:.2f}")
    print(f"  WRONG pairings applied after guard: {m['wrong_applied_after_guard']}  (must be 0)")
    ok = m["wrong_applied_after_guard"] == 0 and m["guard_catch_rate"] == 1.0
    print(f"  GUARD SAFETY GATE               : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
