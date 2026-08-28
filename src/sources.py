"""
sources.py — the ingestion seam.

The matcher consumes two lists of row-dicts: the merchant LEDGER (their books) and
the Razorpay SETTLEMENT recon rows. Where those rows come from is a swappable
adapter, so the same engine runs against a CSV fixture today and a live database +
Razorpay API in production with no change to the matcher.

  LedgerSource        .load_ledger()      -> list[dict]
  SettlementSource    .load_settlements() -> list[dict]
  ReconciliationSource = both (for sources that provide the whole picture)

Concrete adapters:
  CsvSource       reads the generator's CSVs               (fixture / CI)
  SqliteSource    reads a real SQLite DB (built from CSVs)  (proves the DB path)
  CompositeSource wires a LedgerSource + a SettlementSource (the production shape:
                  the ledger comes from the merchant's own system, the settlements
                  from Razorpay — two different systems reconciled against each other)

Production stubs (documented, deliberately not wired — this is the seam):
  SqlLedgerSource            would query the merchant's orders DB
  RazorpaySettlementsSource  would page the Razorpay settlement recon report
"""
import csv
import os
import sqlite3
from abc import ABC, abstractmethod

import matcher

LEDGER_COLS = ["order_id", "payment_id", "amount", "method", "captured_at",
               "status", "customer"]
SETTLEMENT_COLS = ["entity_id", "type", "amount", "fee", "tax", "credit", "debit",
                   "settlement_id", "settlement_utr", "settled_at", "order_id",
                   "method", "description"]


class LedgerSource(ABC):
    @abstractmethod
    def load_ledger(self) -> list[dict]:
        ...


class SettlementSource(ABC):
    @abstractmethod
    def load_settlements(self) -> list[dict]:
        ...


class ReconciliationSource(LedgerSource, SettlementSource):
    """A source that provides both sides."""


# --------------------------------------------------------------------------- CSV (fixture)
class CsvSource(ReconciliationSource):
    def __init__(self, data_dir: str = matcher.D):
        self.data_dir = data_dir

    def _read(self, name: str) -> list[dict]:
        with open(os.path.join(self.data_dir, name), encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_ledger(self) -> list[dict]:
        return self._read("ledger.csv")

    def load_settlements(self) -> list[dict]:
        return self._read("settlements.csv")


# ----------------------------------------------------------------------- SQLite (real DB)
class SqliteSource(ReconciliationSource):
    """Reads from a real SQLite database. Demonstrates the storage layer end to end —
    the same rows the matcher gets from CSV, but served from a queryable DB with a
    schema. Swapping SQLite for Postgres is a connection-string change."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    @classmethod
    def from_csv(cls, csv_source: "CsvSource", db_path: str) -> "SqliteSource":
        """Materialize the CSV fixture into a SQLite DB (the one-time 'load' step a
        real ETL job would do from the merchant system + Razorpay API)."""
        if os.path.exists(db_path):
            os.remove(db_path)
        con = sqlite3.connect(db_path)
        try:
            _create_and_fill(con, "ledger", LEDGER_COLS, csv_source.load_ledger())
            _create_and_fill(con, "settlements", SETTLEMENT_COLS,
                             csv_source.load_settlements())
            con.commit()
        finally:
            con.close()
        return cls(db_path)

    def _query(self, table: str, cols: list[str]) -> list[dict]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    def load_ledger(self) -> list[dict]:
        return self._query("ledger", LEDGER_COLS)

    def load_settlements(self) -> list[dict]:
        return self._query("settlements", SETTLEMENT_COLS)


def _create_and_fill(con, table, cols, rows):
    coldefs = ", ".join(f'"{c}" TEXT' for c in cols)
    con.execute(f"CREATE TABLE {table} ({coldefs})")
    placeholders = ", ".join("?" for _ in cols)
    con.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
        [[r.get(c, "") for c in cols] for r in rows])


# ------------------------------------------------------------------ composite (prod shape)
class CompositeSource(ReconciliationSource):
    """Reconcile a ledger from one system against settlements from another — the real
    deployment shape (merchant DB ledger vs Razorpay settlement feed)."""

    def __init__(self, ledger_source: LedgerSource, settlement_source: SettlementSource):
        self._ledger = ledger_source
        self._settlements = settlement_source

    def load_ledger(self) -> list[dict]:
        return self._ledger.load_ledger()

    def load_settlements(self) -> list[dict]:
        return self._settlements.load_settlements()


# ---------------------------------------------------------- production stubs (the seam)
class SqlLedgerSource(LedgerSource):
    """PRODUCTION STUB. In a real deployment this queries the merchant's own orders
    table (Postgres / MySQL / their ERP) for captured payments in the settlement
    window, returning rows shaped like LEDGER_COLS. Left unwired on purpose — this is
    exactly where a merchant's system plugs in."""

    def __init__(self, dsn: str, window):
        self.dsn = dsn
        self.window = window

    def load_ledger(self) -> list[dict]:
        raise NotImplementedError(
            "Wire to the merchant orders DB, e.g.:\n"
            "  SELECT order_id, payment_id, amount, method, captured_at, status, customer\n"
            "  FROM orders WHERE status='captured' AND captured_at BETWEEN %s AND %s")


class RazorpaySettlementsSource(SettlementSource):
    """PRODUCTION STUB. In a real deployment this pages the Razorpay settlement recon
    report (`/v1/settlements/recon/combined`, or the SDK's settlement APIs — equivalently,
    the `fetch_settlement_recon_details` tool on the official `razorpay-mcp-server`,
    github.com/razorpay/razorpay-mcp-server, verified present in its 45-tool README as of
    2026-08-28) for a settlement id / cycle and maps Razorpay's fields onto SETTLEMENT_COLS:
        id->settlement_id, utr->settlement_utr, entity_id/payment_id->entity_id,
        type (payment|refund|adjustment), amount/fee/tax/credit/debit, settled_at,
        on_hold/on_hold_until (timing), order_id, method, description (bank narration).
    Left unwired on purpose — deliberately deferred (see ARCHITECTURE.md §8), blocked on
    fresh rzp_test_ credentials + a Go toolchain/binary, neither present when checked.
    NOTE: test-mode settlements never populate regardless (pre-KYC — see LOG.md), so this
    needs a KYC-activated account either way; the CSV/SQLite path is the demo."""

    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self.key_secret = key_secret

    def load_settlements(self) -> list[dict]:
        raise NotImplementedError(
            "Wire to Razorpay: client.settlement.all()/recon report, paginate on\n"
            "`count`/`skip`, map fields onto SETTLEMENT_COLS, handle rate limits + retries\n"
            "(see net.with_retries). Requires a KYC-activated (non-test) account.")
