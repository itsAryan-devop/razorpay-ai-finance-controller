"""
net.py — resilience helpers for the (real) API adapter path.

A live reconciliation job pulls the Razorpay settlement recon report over HTTP:
that call can flake (timeouts, 429 rate limits, 5xx). `with_retries` wraps such a
call with bounded exponential backoff and structured logging, so a transient blip
is retried and a persistent failure surfaces loudly instead of silently returning
an empty settlement list (which would mis-reconcile real money).

The demo runs against CSV/SQLite so this is exercised by tests with a flaky fake,
but it is the exact seam RazorpaySettlementsSource.load_settlements() would use.
"""
import time

import obs

log = obs.get_logger("recon.net")


class RetriesExhausted(RuntimeError):
    pass


def with_retries(fn, *, attempts=3, base_delay=0.1, max_delay=2.0,
                 exceptions=(Exception,), sleep=time.sleep):
    """Call fn(); on `exceptions`, retry up to `attempts` times with exponential
    backoff (base_delay * 2**n, capped at max_delay). Re-raises the last error
    wrapped in RetriesExhausted when all attempts fail. `sleep` is injectable so
    tests run instantly."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as e:                      # noqa: BLE001 (intentional wrap)
            last = e
            if attempt == attempts:
                log.error("retries exhausted",
                          extra={"fields": {"attempts": attempts, "error": repr(e)}})
                raise RetriesExhausted(f"failed after {attempts} attempts: {e!r}") from e
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            log.warning("retrying after error",
                        extra={"fields": {"attempt": attempt, "delay_s": round(delay, 3),
                                          "error": repr(e)}})
            sleep(delay)
    raise RetriesExhausted(repr(last))               # unreachable, kept for type-safety
