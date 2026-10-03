"""No. 6a (user, 3 Oct 2026): a statement PDF dropped on the home page.

It is read and checked from a temporary copy first; only a new statement is kept (in the statements folder, under its
own file name) and stored in the database, the same way run.py does it. A duplicate or a file that is not a
statement is not kept.
"""
import os
import tempfile
from pathlib import Path

from fintrack.checks import check_statement
from fintrack.parse import parse_statement
from fintrack.store import import_statement


def import_pdf(conn, folder, filename: str, data: bytes) -> dict:
    """{"file", "new", "payments", "start", "end", "problems"} or {"file", "error"}."""
    name = Path(filename.replace("\\", "/")).name or "statement.pdf"        # only the file name, never a path
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        return {"file": name, "error": "That is not a PDF."}
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            st = parse_statement(tmp)
        except Exception:
            return {"file": name, "error": "Could not read this PDF."}
        if st.start is None or st.end is None:
            return {"file": name, "error": "This does not look like an HSBC statement."}
        st.file = name
        problems = check_statement(st)
        new = import_statement(conn, st, problems)
        if new:
            folder = Path(folder)
            folder.mkdir(parents=True, exist_ok=True)
            target, n = folder / name, 1
            while target.exists() and target.read_bytes() != data:           # never overwrite a different file
                target, n = folder / f"{Path(name).stem} ({n}).pdf", n + 1
            target.write_bytes(data)
        return {"file": name, "new": new, "payments": len(st.txns), "start": st.start, "end": st.end,
                "problems": problems}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
