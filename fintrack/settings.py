"""Remembers where your statements folder is, outside the code folder (survives new ZIP downloads)."""
from pathlib import Path
from typing import Optional

SAVED_FILE = Path.home() / ".financial_tracker_folder.txt"


def save_folder(path, saved_file=SAVED_FILE) -> None:
    """Write the folder path (one line of text) to saved_file, replacing what was there."""
    saved_file.write_text(str(path))


def saved_folder(saved_file=SAVED_FILE) -> Optional[Path]:
    """The remembered folder as a Path, or None when the file is missing, empty, unreadable
    or the folder no longer exists."""
    try:
        text = saved_file.read_text().strip()
        if not text:
            return None
        folder = Path(text)
        if folder.exists():
            return folder
        return None
    except (FileNotFoundError, OSError):
        return None
