"""Shared pytest setup: put src/ on the path and regenerate deterministic data once."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import generate_data  # noqa: E402


def pytest_configure(config):
    # deterministic (seed 42) — every test run sees identical data
    generate_data.generate()
