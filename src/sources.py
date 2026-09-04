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

  RazorpaySettlementsSource  REAL as of 2026-09-04: calls the official
                  razorpay-mcp-server over MCP (src/mcp_client.py). Confirmed live
                  against the real API — see tools/README.md for empirical findings.

Production stub (documented, deliberately not wired — this is the seam):
  SqlLedgerSource            would query the merchant's own orders DB — not a
                  Razorpay concept, so there's no equivalent official tool to wire.
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
    """REAL (as of 2026-09-04) — no longer a stub. Calls the official
    `razorpay-mcp-server` (github.com/razorpay/razorpay-mcp-server, checksum-verified
    binary in tools/, see tools/README.md) over MCP stdio, tool `fetch_settlement_recon_details`,
    and maps Razorpay's response fields onto SETTLEMENT_COLS. Empirically confirmed
    live against the real API with real rzp_test_ credentials: `fetch_all_payments`
    returns genuine captured test payments (e.g. pay_TTk0Us... — the same payment ID
    from the original day-1 spike); `fetch_settlement_recon_details` returns
    `{"count":0,"items":[]}` in test mode — RE-CONFIRMING, via the official tool this
    time (not just the raw SDK), that test-mode settlements never populate (pre-KYC
    gating — see LOG.md). So this path is real and working, but will return an empty
    list against a test-mode account either way; a KYC-activated account is what would
    actually populate it, not more code here. The exact field mapping for a NON-EMPTY
    settlement item is Razorpay's documented recon schema, best-effort via `.get()` —
    it could not be empirically verified against real populated data for the reason
    above, and that gap is stated honestly rather than claimed as verified."""

    def __init__(self, key_id: str, key_secret: str, year: int, month: int):
        self.key_id = key_id
        self.key_secret = key_secret
        self.year, self.month = year, month

    def load_settlements(self) -> list[dict]:
        import mcp_client
        with mcp_client.RazorpayMcpClient(self.key_id, self.key_secret) as client:
            data = client.call_tool("fetch_settlement_recon_details",
                                    {"year": self.year, "month": self.month})
        return [self._map_row(item) for item in data.get("items", [])]

    @staticmethod
    def _map_row(item: dict) -> dict:
        """Best-effort mapping to SETTLEMENT_COLS — see class docstring for the
        unverified-against-real-data caveat."""
        return {
            "entity_id": item.get("entity_id") or item.get("payment_id", ""),
            "type": item.get("type", "payment"),
            "amount": item.get("amount", 0),
            "fee": item.get("fee", 0),
            "tax": item.get("tax", 0),
            "credit": item.get("credit", 0),
            "debit": item.get("debit", 0),
            "settlement_id": item.get("id") or item.get("settlement_id", ""),
            "settlement_utr": item.get("utr", ""),
            "settled_at": item.get("settled_at", ""),
            "order_id": item.get("order_id", ""),
            "method": item.get("method", ""),
            "description": item.get("description", ""),
        }
