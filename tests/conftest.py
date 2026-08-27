"""Shared pytest setup: put src/ on the path and regenerate deterministic data once."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import generate_data  # noqa: E402


def pytest_configure(config):
    # Force the deterministic heuristic engine for the whole suite so tests never touch
    # a developer's local Ollama server (which would make them slow + nondeterministic).
    # test_ollama.py overrides this via monkeypatch to exercise the fallback path.
    os.environ["LLM_PROVIDER"] = "heuristic"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    # deterministic (seed 42) — every test run sees identical data
    generate_data.generate()
