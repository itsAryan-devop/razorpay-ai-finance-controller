"""
obs.py — minimal structured (JSON-line) logging.

Production reconciliation runs are unattended batch jobs; their output has to be
machine-parseable for log aggregation and alerting, not just pretty console text.
`configure()` installs a JSON formatter; `get_logger()` hands back a namespaced
logger. Attach structured fields via `logger.info("msg", extra={"fields": {...}})`.

Kept out of library import paths on purpose — only the entrypoints (pipeline CLI,
Streamlit app, a future service) call configure(), so importing the modules for
tests stays quiet.
"""
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure(level: str = "INFO") -> None:
    """Install a single JSON-line handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers:
        if getattr(h, "_recon_json", False):
            return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler._recon_json = True          # marker so we don't double-install
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def enable_utf8_stdout() -> None:
    """Force stdout/stderr to UTF-8 so unicode (e.g. the ₹ sign) prints on a Windows
    cp1252 console instead of crashing with UnicodeEncodeError — the root-cause fix for
    the recurring day-1 bug (see LOG.md), applied once at the CLI entrypoint rather than
    ASCII-substituting every string. errors='replace' means a truly un-renderable glyph
    degrades to '?' instead of raising. No-op where reconfigure is unavailable."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
