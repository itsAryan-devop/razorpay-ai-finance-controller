"""Resilience tests for the API-adapter retry helper (instant — sleep is stubbed)."""
import pytest

import net


def test_retries_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    out = net.with_retries(flaky, attempts=3, sleep=lambda _: None)
    assert out == "ok"
    assert calls["n"] == 3


def test_retries_exhausted_raises():
    def always_fails():
        raise TimeoutError("down")

    with pytest.raises(net.RetriesExhausted):
        net.with_retries(always_fails, attempts=3, sleep=lambda _: None)


def test_success_first_try_no_retry():
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return 42

    assert net.with_retries(ok, sleep=lambda _: None) == 42
    assert calls["n"] == 1
