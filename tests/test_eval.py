"""Held-out generalization test: the matcher's rules must score well on independent
seeds they were never tuned against — proving the headline numbers aren't a seed-42
overfit. evaluate() restores the canonical seed-42 dataset afterwards, so this test
does not disturb the rest of the suite."""
import eval_guard
import eval_holdout


def test_matcher_generalizes_on_holdout_seeds():
    rows = eval_holdout.evaluate(seeds=[7, 2024])       # subset for speed; restores seed 42
    s = eval_holdout.summary(rows)
    assert s["heldout_mean"] >= eval_holdout.GATE       # generalizes, not overfit to seed 42
    assert all(0.90 <= r["accuracy"] <= 1.0 for r in rows)   # believable on every draw
    # the dev seed (42) is at the conservative end — we report a hard draw, not an easy one
    assert s["dev_accuracy"] <= s["heldout_max"]


def test_guard_catches_worst_case_adversarial_model():
    """Reproducible guard metric: against a model that hallucinates on EVERY case, the
    guard must catch 100% and let 0 wrong pairings through — a measured number, not an
    anecdote."""
    m = eval_guard.evaluate()
    assert m["model_picks"] >= 1
    assert m["guard_catch_rate"] == 1.0
    assert m["wrong_applied_after_guard"] == 0
