"""v3 (15 Oct 2026): the page stays up to date across devices. GET /stamp = when the data last changed (the
database file's change time). The page asks when it is opened or shown again, and every 15 minutes while open, and
reloads only when the stamp is different (and nothing is being typed). Asking does not count as using the site,
so the passcode still comes back after 15 minutes."""
from pathlib import Path


def stamp(data_dir) -> str:
    try:
        return str((Path(data_dir) / "tracker.db").stat().st_mtime_ns)
    except OSError:
        return ""


def register(app) -> None:
    @app.get("/stamp")
    def data_stamp():
        return {"stamp": stamp(app.config["V3_DATA_DIR"])}, 200, {"Cache-Control": "no-store"}
