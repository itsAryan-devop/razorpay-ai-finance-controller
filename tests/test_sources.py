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


def test_production_stubs_fail_loudly():
    with pytest.raises(NotImplementedError):
        sources.RazorpaySettlementsSource("k", "s").load_settlements()
    with pytest.raises(NotImplementedError):
        sources.SqlLedgerSource("dsn", None).load_ledger()
