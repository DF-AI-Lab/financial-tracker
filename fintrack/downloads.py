"""Scan downloads folder for new HSBC statements and import them."""
import json
from pathlib import Path
from fintrack.store import get_value, set_value


def scan_downloads(conn, downloads_dir, statements_dir) -> list:
    """Scan downloads folder for new statement PDFs and import them.

    Returns list of file names newly imported (moved to statements_dir).
    Tracks seen files in kv table to avoid re-reading bad files."""
    downloads_dir = Path(downloads_dir) if downloads_dir else None
    statements_dir = Path(statements_dir)

    if not downloads_dir or not downloads_dir.is_dir():
        return []

    # Load the set of already-seen files
    seen_str = get_value(conn, "downloads_seen") or "[]"
    try:
        seen = json.loads(seen_str)
    except (ValueError, TypeError):
        seen = []
    seen_set = set(seen)

    imported = []

    # Find all PDFs with "statement" in the name
    for file_path in downloads_dir.iterdir():
        if not file_path.is_file():
            continue
        name = file_path.name
        if not name.lower().endswith(".pdf"):
            continue
        if "statement" not in name.lower():
            continue

        # Create a file signature to track if we've seen it before
        try:
            stat = file_path.stat()
            file_sig = f"{name}|{stat.st_size}|{stat.st_mtime}"
        except OSError:
            continue

        if file_sig in seen_set:
            continue

        # Try to import this file
        try:
            data = file_path.read_bytes()
        except OSError:
            # Remember it as seen even though we couldn't read it
            seen.append(file_sig)
            set_value(conn, "downloads_seen", json.dumps(seen))
            continue

        try:
            from fintrack.inbox import import_pdf
            r = import_pdf(conn, statements_dir, name, data)
        except Exception:
            # Remember it as seen even on error
            seen.append(file_sig)
            set_value(conn, "downloads_seen", json.dumps(seen))
            continue

        # Remember we've seen this file
        seen.append(file_sig)

        # Handle the result
        if r.get("error"):
            # Error importing: leave file, remember it
            set_value(conn, "downloads_seen", json.dumps(seen))
        elif r.get("new"):
            # Newly imported: delete from downloads
            try:
                file_path.unlink()
            except OSError:
                pass
            imported.append(name)
            set_value(conn, "downloads_seen", json.dumps(seen))
        else:
            # Already in database: keep a copy in the statements folder if it is not there, then delete from downloads
            try:
                target = statements_dir / name
                have = statements_dir.is_dir() and any(
                    f.is_file() and f.stat().st_size == len(data) and f.read_bytes() == data
                    for f in statements_dir.iterdir())
                if not have and not target.exists():
                    statements_dir.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                file_path.unlink()
            except OSError:
                pass
            set_value(conn, "downloads_seen", json.dumps(seen))

    return imported
