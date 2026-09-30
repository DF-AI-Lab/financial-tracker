"""SQLite memory for the tracker: statements, payments and your answers."""
import sqlite3
from typing import Dict, List

from fintrack.models import Statement, Txn

KINDS = ("regular", "common", "random", "oneoff")


def open_db(path) -> sqlite3.Connection:
    """Open (and create if missing) the database. `path` may be a Path, a str or ":memory:".

    Tables (create them with IF NOT EXISTS so opening twice is fine):
      statements(id, file, start, end, opening, closing, problems, UNIQUE(start, end, opening, closing))
      payments(id, statement_id, seq, date, type, description, detail, amount, balance)
      items(key PRIMARY KEY, kind, label, source)
    Dates are stored as ISO text.
    """
    raise NotImplementedError


def import_statement(conn, st: Statement, problems: List[str]) -> bool:
    """Store a statement and its payments. Returns True if stored, False if skipped.

    Skipped (False) when a statement with the same start, end, opening and closing is already
    stored, or when st.start or st.end is None. `problems` (the check_statement messages) is
    saved as text, joined with newlines ("" when there are none). Payments keep their order
    (seq = position in st.txns). Commit before returning.
    """
    raise NotImplementedError


def load_txns(conn) -> List[Txn]:
    """Every stored payment as a Txn, oldest first: order by date, then statement start, then seq."""
    raise NotImplementedError


def statement_rows(conn) -> List[dict]:
    """One dict per stored statement, oldest end date first:
    {"file", "start", "end", "opening", "closing", "problems", "payments"}
    where start/end are ISO strings, problems is the saved text and payments is the number stored."""
    raise NotImplementedError


def item_key(t: Txn) -> str:
    """The key a payment is labelled under: "<GROUP>|<NAME>|<REFERENCE>".

    GROUP from the payment type: DD -> "DD", SO -> "SO", BP -> "BP", ATM -> "CASH",
    CR -> "IN", anything else (VIS, ")))" ...) -> "CARD".
    For DD, SO and BP: NAME = description upper-cased and stripped with a trailing " LTD",
    " LIMITED" or " PLC" removed and repeated spaces collapsed; REFERENCE = detail upper-cased
    and stripped, but "" when the detail is empty or "FIRST PAYMENT".
    For the other groups: NAME = fintrack.common.payee_key(t) and REFERENCE = "".
    Example: SO, "SAM PARKER", "Rent" -> "SO|SAM PARKER|RENT"; VIS "CORNER SHOP 12" -> "CARD|CORNER SHOP|".
    """
    raise NotImplementedError


def set_item(conn, key: str, kind: str, label: str = "", source: str = "user") -> None:
    """Save your answer for an item (insert or update). kind must be in KINDS, else ValueError.
    source is "user" or "suggested". Commit before returning."""
    raise NotImplementedError


def get_items(conn) -> Dict[str, dict]:
    """{key: {"kind", "label", "source"}} for every saved item."""
    raise NotImplementedError
