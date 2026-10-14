"""v3 move-in check (14 Oct 2026): does the database hold anything that looks like an account number, sort code,
card number, IBAN or postcode? Run on the PC before the database goes online:

    C:\\ftvenv\\Scripts\\python.exe tools\\privacy_check.py "C:\\path\\to\\tracker.db"

It only READS the database and prints counts plus a few examples with the digits hidden, so the output is safe to
copy and paste to Claude.
"""
import re
import sqlite3
import sys

PATTERNS = {
    "sort code": re.compile(r"\b\d{2}-\d{2}-\d{2}\b"),
    "8-digit number (account number?)": re.compile(r"(?<![\d.])\d{8}(?![\d.])"),
    "card number": re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    "IBAN": re.compile(r"\bGB\d{2}\s?[A-Z]{4}", re.I),
    "postcode": re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b"),
    "the words account / sort code": re.compile(r"\b(account\s*(no|number)|sort\s*code)\b", re.I),
}
# Places where text from the statements is kept (other tables hold only numbers, dates or the user's own words)
TEXT_COLUMNS = [("statements", "file"), ("statements", "problems"), ("payments", "description"),
                ("payments", "detail"), ("items", "key"), ("items", "label"), ("spends", "name")]


def hide(text: str) -> str:
    """Show the shape, never the digits: 40-12-34 -> ##-##-##."""
    return re.sub(r"\d", "#", text)


def scan(conn) -> dict:
    """{pattern name: {"count": n, "examples": [hidden text, ...]}} over the text columns."""
    found = {}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, col in TEXT_COLUMNS:
        if table not in tables:
            continue
        for (value,) in conn.execute(f"SELECT {col} FROM {table}"):
            if not value:
                continue
            for name, rx in PATTERNS.items():
                m = rx.search(str(value))
                if m:
                    f = found.setdefault(name, {"count": 0, "examples": []})
                    f["count"] += 1
                    if len(f["examples"]) < 5:
                        f["examples"].append(f"{table}.{col}: {hide(str(value))[:70]}")
    return found


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    conn = sqlite3.connect(f"file:{argv[0]}?mode=ro", uri=True)
    found = scan(conn)
    if not found:
        print("All clear: nothing that looks like an account number, sort code, card number or postcode.")
        return 0
    print("Found some things to check (digits hidden):")
    for name, f in found.items():
        print(f"\n  {name}: {f['count']}")
        for e in f["examples"]:
            print("    " + e)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
