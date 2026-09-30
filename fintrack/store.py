"""SQLite memory for the tracker: statements, payments and your answers."""
import re
import sqlite3
from typing import Dict, List

from fintrack.models import Statement, Txn
from fintrack.common import payee_key

KINDS = ("regular", "common", "random", "oneoff")


def open_db(path) -> sqlite3.Connection:
    """Open (and create if missing) the database. `path` may be a Path, a str or ":memory:".

    Tables (create them with IF NOT EXISTS so opening twice is fine):
      statements(id, file, start, end, opening, closing, problems, UNIQUE(start, end, opening, closing))
      payments(id, statement_id, seq, date, type, description, detail, amount, balance)
      items(key PRIMARY KEY, kind, label, source)
      rules(id INTEGER PRIMARY KEY, payer, usual, label, kind, max_days, tolerance, source)
    Dates are stored as ISO text.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # Create statements table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS statements (
            id INTEGER PRIMARY KEY,
            file TEXT,
            start TEXT,
            end TEXT,
            opening REAL,
            closing REAL,
            problems TEXT,
            UNIQUE(start, end, opening, closing)
        )
    """)

    # Create payments table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY,
            statement_id INTEGER,
            seq INTEGER,
            date TEXT,
            type TEXT,
            description TEXT,
            detail TEXT,
            amount REAL,
            balance REAL,
            FOREIGN KEY(statement_id) REFERENCES statements(id)
        )
    """)

    # Create items table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            key TEXT PRIMARY KEY,
            kind TEXT,
            label TEXT,
            source TEXT
        )
    """)

    # Create rules table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY,
            payer TEXT,
            usual REAL,
            label TEXT,
            kind TEXT,
            max_days INTEGER,
            tolerance REAL,
            source TEXT
        )
    """)

    conn.commit()
    return conn


def import_statement(conn, st: Statement, problems: List[str]) -> bool:
    """Store a statement and its payments. Returns True if stored, False if skipped.

    Skipped (False) when a statement with the same start, end, opening and closing is already
    stored, or when st.start or st.end is None. `problems` (the check_statement messages) is
    saved as text, joined with newlines ("" when there are none). Payments keep their order
    (seq = position in st.txns). Commit before returning.
    """
    # Skip if start or end is None
    if st.start is None or st.end is None:
        return False

    # Check if statement already exists with same start, end, opening, closing
    start_iso = st.start.isoformat()
    end_iso = st.end.isoformat()

    existing = conn.execute(
        "SELECT id FROM statements WHERE start = ? AND end = ? AND opening = ? AND closing = ?",
        (start_iso, end_iso, st.opening, st.closing)
    ).fetchone()

    if existing:
        return False

    # Insert the statement
    problems_text = "\n".join(problems) if problems else ""
    cursor = conn.execute(
        "INSERT INTO statements (file, start, end, opening, closing, problems) VALUES (?, ?, ?, ?, ?, ?)",
        (st.file, start_iso, end_iso, st.opening, st.closing, problems_text)
    )
    statement_id = cursor.lastrowid

    # Insert the payments
    for seq, txn in enumerate(st.txns):
        conn.execute(
            "INSERT INTO payments (statement_id, seq, date, type, description, detail, amount, balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (statement_id, seq, txn.date.isoformat(), txn.type, txn.description, txn.detail, txn.amount, txn.balance)
        )

    conn.commit()
    return True


def load_txns(conn) -> List[Txn]:
    """Every stored payment as a Txn, oldest first: order by date, then statement start, then seq."""
    rows = conn.execute("""
        SELECT p.date, p.type, p.description, p.detail, p.amount, p.balance, s.start
        FROM payments p
        JOIN statements s ON p.statement_id = s.id
        ORDER BY p.date, s.start, p.seq
    """).fetchall()

    result = []
    for row in rows:
        from datetime import date
        txn = Txn(
            date=date.fromisoformat(row[0]),
            type=row[1],
            description=row[2],
            detail=row[3],
            amount=row[4],
            balance=row[5]
        )
        result.append(txn)

    return result


def statement_rows(conn) -> List[dict]:
    """One dict per stored statement, oldest end date first:
    {"file", "start", "end", "opening", "closing", "problems", "payments"}
    where start/end are ISO strings, problems is the saved text and payments is the number stored."""
    rows = conn.execute("""
        SELECT s.file, s.start, s.end, s.opening, s.closing, s.problems, COUNT(p.id) as payments
        FROM statements s
        LEFT JOIN payments p ON s.id = p.statement_id
        GROUP BY s.id
        ORDER BY s.end
    """).fetchall()

    result = []
    for row in rows:
        result.append({
            "file": row[0],
            "start": row[1],
            "end": row[2],
            "opening": row[3],
            "closing": row[4],
            "problems": row[5],
            "payments": row[6]
        })

    return result


def item_key(t: Txn) -> str:
    """The key a payment is labelled under: "<GROUP>|<NAME>|<REFERENCE>".

    GROUP from the payment type: DD -> "DD", SO -> "SO", BP -> "BP", ATM -> "CASH",
    CR -> "IN", anything else (VIS, ")))" ...) -> "CARD".
    For DD, SO and BP: NAME = description upper-cased and stripped with a trailing " LTD",
    " LIMITED" or " PLC" removed and repeated spaces collapsed; REFERENCE = detail upper-cased
    and stripped, but "" when the detail is empty or "FIRST PAYMENT".
    For CR (income): NAME = description upper-cased and stripped (suffixes kept), REFERENCE = "".
    For the other groups (CARD, CASH): NAME = fintrack.common.payee_key(t) and REFERENCE = "".
    Example: SO, "SAM PARKER", "Rent" -> "SO|SAM PARKER|RENT"; VIS "CORNER SHOP 12" -> "CARD|CORNER SHOP|".
    """
    # Determine the group
    if t.type == "DD":
        group = "DD"
    elif t.type == "SO":
        group = "SO"
    elif t.type == "BP":
        group = "BP"
    elif t.type == "ATM":
        group = "CASH"
    elif t.type == "CR":
        group = "IN"
    else:
        group = "CARD"

    # For DD, SO, BP: extract NAME and REFERENCE
    if group in ("DD", "SO", "BP"):
        # NAME: description upper-cased, stripped, remove " LTD", " LIMITED", " PLC", collapse spaces
        name = t.description.strip().upper()
        if name.endswith(" LTD"):
            name = name[:-4].strip()
        elif name.endswith(" LIMITED"):
            name = name[:-8].strip()
        elif name.endswith(" PLC"):
            name = name[:-4].strip()
        name = re.sub(r' +', ' ', name).strip()

        # REFERENCE: detail upper-cased and stripped, but "" when empty or "FIRST PAYMENT"
        detail = t.detail.strip().upper()
        if not detail or detail == "FIRST PAYMENT":
            reference = ""
        else:
            reference = detail

        return f"{group}|{name}|{reference}"

    # For CR: just upper-case and strip (don't remove suffixes like payee_key does)
    if group == "IN":
        name = t.description.strip().upper()
        return f"{group}|{name}|"

    # For other groups (VIS, ATM, etc.): NAME = payee_key(t), REFERENCE = ""
    name = payee_key(t)
    return f"{group}|{name}|"


def set_item(conn, key: str, kind: str, label: str = "", source: str = "user") -> None:
    """Save your answer for an item (insert or update). kind must be in KINDS, else ValueError.
    source is "user" or "suggested". Commit before returning."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind}")

    # Check if key already exists
    existing = conn.execute("SELECT key FROM items WHERE key = ?", (key,)).fetchone()

    if existing:
        # Update
        conn.execute(
            "UPDATE items SET kind = ?, label = ?, source = ? WHERE key = ?",
            (kind, label, source, key)
        )
    else:
        # Insert
        conn.execute(
            "INSERT INTO items (key, kind, label, source) VALUES (?, ?, ?, ?)",
            (key, kind, label, source)
        )

    conn.commit()


def get_items(conn) -> Dict[str, dict]:
    """{key: {"kind", "label", "source"}} for every saved item."""
    rows = conn.execute("SELECT key, kind, label, source FROM items").fetchall()

    result = {}
    for row in rows:
        result[row[0]] = {
            "kind": row[1],
            "label": row[2],
            "source": row[3]
        }

    return result


def load_statements(conn) -> List[Statement]:
    """Every stored statement as a fintrack.models.Statement with its payments (txns, in order),
    oldest end date first. Dates come back as date objects; problems are not part of Statement."""
    from datetime import date

    rows = conn.execute("""
        SELECT id, file, start, end, opening, closing
        FROM statements
        ORDER BY end
    """).fetchall()

    result = []
    for row in rows:
        statement_id = row[0]
        file = row[1]
        start = date.fromisoformat(row[2])
        end = date.fromisoformat(row[3])
        opening = row[4]
        closing = row[5]

        # Load payments for this statement
        payment_rows = conn.execute("""
            SELECT date, type, description, detail, amount, balance
            FROM payments
            WHERE statement_id = ?
            ORDER BY seq
        """, (statement_id,)).fetchall()

        txns = []
        for p_row in payment_rows:
            txn = Txn(
                date=date.fromisoformat(p_row[0]),
                type=p_row[1],
                description=p_row[2],
                detail=p_row[3],
                amount=p_row[4],
                balance=p_row[5]
            )
            txns.append(txn)

        statement = Statement(
            file=file,
            start=start,
            end=end,
            opening=opening,
            closing=closing,
            txns=txns
        )
        result.append(statement)

    return result


RULE_KINDS = ("common", "declined")


def add_rule(conn, payer: str, usual: float, label: str, kind: str = "common", max_days: int = 2,
             tolerance: float = 0.10, source: str = "user") -> None:
    """Save a payday-transfer rule (see fintrack/paydayrule.py). kind must be in RULE_KINDS, else ValueError.
    Table rules(id INTEGER PRIMARY KEY, payer, usual, label, kind, max_days, tolerance, source), created
    in open_db with IF NOT EXISTS. Every call adds a new row. Commit before returning."""
    if kind not in RULE_KINDS:
        raise ValueError(f"kind must be one of {RULE_KINDS}, got {kind}")

    conn.execute(
        "INSERT INTO rules (payer, usual, label, kind, max_days, tolerance, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (payer, usual, label, kind, max_days, tolerance, source)
    )

    conn.commit()


def get_rules(conn) -> List[dict]:
    """Every saved rule, oldest first, as {"payer", "usual", "label", "kind", "max_days", "tolerance", "source"}."""
    rows = conn.execute("SELECT payer, usual, label, kind, max_days, tolerance, source FROM rules ORDER BY id").fetchall()

    result = []
    for row in rows:
        result.append({
            "payer": row[0],
            "usual": row[1],
            "label": row[2],
            "kind": row[3],
            "max_days": row[4],
            "tolerance": row[5],
            "source": row[6]
        })

    return result
