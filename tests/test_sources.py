"""Ingestion-seam tests: the SQLite DB path returns exactly the CSV data, so the
same engine produces identical metrics regardless of where the rows come from.
The production stubs must fail loudly (never silently return empty)."""
import os

import pytest

import pipeline
import sources


def test_csv_and_sqlite_sources_agree(tmp_path):
    csv_src = sources.CsvSource()
    sq = sources.SqliteSource.from_csv(csv_src, os.path.join(tmp_path, "recon.db"))
    assert csv_src.load_ledger() == sq.load_ledger()
    assert csv_src.load_settlements() == sq.load_settlements()


def test_pipeline_metrics_identical_via_sqlite(tmp_path):
    sq = sources.SqliteSource.from_csv(sources.CsvSource(),
                                       os.path.join(tmp_path, "recon.db"))
    a = pipeline.run(commit=False)                                    # default CSV
    b = pipeline.run(commit=False, source=sq,
                     audit_path=os.path.join(tmp_path, "log.jsonl"))  # from SQLite
    assert a["metrics"]["accuracy"] == b["metrics"]["accuracy"]
    assert a["metrics"]["match_rate"] == b["metrics"]["match_rate"]
    assert a["pairing"] == b["pairing"]


def test_ledger_stub_fails_loudly():
    with pytest.raises(NotImplementedError):
        sources.SqlLedgerSource("dsn", None).load_ledger()


def test_razorpay_settlements_source_fails_loudly_without_the_binary(monkeypatch):
    """RazorpaySettlementsSource is REAL (calls the actual razorpay-mcp-server via MCP),
    not a stub — but the binary is a gitignored, checksum-verified download (tools/),
    never committed, so it is genuinely absent in CI (and this test forces that case
    regardless of what's on the machine running it, e.g. a dev box that fetched the
    binary). It must fail loudly (McpUnavailable), never silently return an empty list
    that could be mistaken for 'no settlements'."""
    import mcp_client
    monkeypatch.setattr(mcp_client, "EXE_PATH", "Z:\\definitely\\not\\a\\real\\path.exe")
    with pytest.raises(mcp_client.McpUnavailable):
        sources.RazorpaySettlementsSource("k", "s", year=2026, month=8).load_settlements()
