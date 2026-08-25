"""Data-integrity tests: the ground-truth answer key must be internally consistent.
Wraps the 9 invariants in selftest_data so they run in CI as real pytest cases."""
import selftest_data


def test_ground_truth_invariants_all_pass():
    # selftest_data.main() returns 0 iff every invariant holds
    assert selftest_data.main() == 0
