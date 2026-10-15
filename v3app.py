"""v3 (14 Oct 2026): the whole app as one website.

On PythonAnywhere the WSGI file says:
    import sys; sys.path.insert(0, "/home/<you>/whereismymoney")
    from v3app import make_app
    application = make_app("/home/<you>/wmm-data")

On the PC (testing, next to v2):  C:\\ftvenv\\Scripts\\python.exe v3app.py   (or double-click v3.bat)
It runs at http://127.0.0.1:5001 on its own copy of the database (the folder v3data next to the statements folder),
so v2 at :5000 and its data are never touched.

The data folder holds tracker.db, v3_settings.json (never in GitHub) and backups/. The settings file is made on the
first start with a random secret key; Darren fills in his email (and the Gmail app password) by hand.
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
PORT = 5001

DEFAULTS = {
    "email": "",                 # the only address allowed to sign in
    "smtp_user": "",             # the Gmail address that sends the codes
    "smtp_password": "",         # its Gmail app password
    "update": "zip",             # "zip" (download the branch zip, PC) or "git" (git pull, PythonAnywhere)
    "branch": "v3",              # which GitHub branch Update follows
    "wsgi_file": "",             # PythonAnywhere: touching this file restarts the website
    "secret_key": "",            # made on the first start
}


def load_settings(data_dir) -> dict:
    """The settings file in the data folder, made (with a new secret key) when missing. Missing keys get defaults."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "v3_settings.json"
    saved = {}
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8-sig"))     # -sig: Notepad may add a hidden mark
        except (OSError, ValueError) as e:
            # A typo while editing by hand: say so, and never write over the file (that would lose the email)
            print(f"Could not read {path} ({e}). Check the quotes and commas.")
            return {**DEFAULTS, "secret_key": secrets.token_hex(32)}
    settings = {**DEFAULTS, **saved}
    if not settings["secret_key"]:
        settings["secret_key"] = secrets.token_hex(32)
    if settings != saved:
        save_settings(data_dir, settings)
    return settings


def save_settings(data_dir, settings) -> None:
    (Path(data_dir) / "v3_settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")


LIVE_BRANCH = "live"     # the real site follows this; Claude moves it only when Darren has agreed the test copy (15 Oct 2026)


def git_update(code_dir=CODE_DIR, run=subprocess.run, branch=LIVE_BRANCH) -> dict:
    """PythonAnywhere: get the agreed code (branch 'live'). {"changed": [...lines], "version": short commit}."""
    def git(*args, timeout=120):
        r = run(["git", "-C", str(code_dir), *args], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "git failed").strip()[:200])
        return (r.stdout or "").strip()
    old = git("rev-parse", "--short", "HEAD", timeout=30)
    git("fetch", "origin", branch)
    git("checkout", "-B", branch, f"origin/{branch}")       # fails (changes nothing) if a file was edited by hand
    new = git("rev-parse", "--short", "HEAD", timeout=30)
    changed = [] if new == old else [line.strip() for line in git("diff", "--stat", old, new).splitlines() if "|" in line]
    return {"changed": changed, "version": new}


def make_app(data_dir, wage_payer=None, today=None, updater=None, restart=None):
    """The v3 website for the data folder."""
    import web
    from fintrack.cycles import WAGE_PAYER
    from fintrack.v3 import setup

    data_dir = Path(data_dir)
    settings = load_settings(data_dir)

    if updater is None:
        if settings["update"] == "git":
            updater = git_update
        else:
            from fintrack.update import update_code, download
            updater = lambda: update_code(fetch=lambda: download(settings["branch"]))       # noqa: E731
    if restart is None:
        if settings["wsgi_file"]:
            wsgi = Path(settings["wsgi_file"])
            if not wsgi.exists() and (wsgi.parent / wsgi.name.lower()).exists():
                wsgi = wsgi.parent / wsgi.name.lower()                # PythonAnywhere's file name is lower case
            restart = lambda: wsgi.touch()                                                # noqa: E731
        else:
            restart = lambda: threading.Timer(1.0, lambda: os._exit(3)).start()           # noqa: E731

    app = web.create_app(data_dir / "tracker.db", wage_payer=wage_payer or WAGE_PAYER, today=today,
                         updater=updater, restart=restart, statements_dir=data_dir / "statements",
                         phone_http=None, cloud=True, setup=None)
    app.secret_key = settings["secret_key"]
    app.config["V3_SETTINGS"] = settings
    app.config["V3_DATA_DIR"] = data_dir
    setup(app)
    return app


def pc_data_dir(argv=()) -> Path:
    """On the PC: the folder v3data next to the statements folder, with a copy of the v2 database the first time."""
    from run import pick_folder
    statements = pick_folder(list(argv))
    data_dir = statements.parent / "v3data"
    data_dir.mkdir(parents=True, exist_ok=True)
    v2_db, v3_db = statements.parent / "tracker.db", data_dir / "tracker.db"
    if not v3_db.exists() and v2_db.exists():
        shutil.copy2(v2_db, v3_db)
        print("Made a copy of your database for v3 (your v2 data is not touched).")
    return data_dir


def newest_backup(downloads) -> Path:
    """The newest backup downloaded from the real site (Settings → Download backup), or None."""
    found = sorted(Path(downloads).glob("wheres-my-money-backup-*.db"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def offer_fresh_copy(data_dir, downloads=None, ask=input) -> bool:
    """PC test: a backup from the real site that is newer than the test data can become the test data (asked first).
    The real site is never touched: this only copies a file on the PC."""
    data_dir = Path(data_dir)
    backup = newest_backup(downloads or Path.home() / "Downloads")
    test_db = data_dir / "tracker.db"
    if backup is None or (test_db.exists() and backup.stat().st_mtime <= test_db.stat().st_mtime):
        return False
    if ask(f"Use {backup.name} from Downloads as the test data? (y/N) ").strip().lower() not in ("y", "yes"):
        return False
    shutil.copy2(backup, test_db)
    print("Test data replaced with that backup. Your real site is not touched.")
    return True


def main():
    data_dir = pc_data_dir(sys.argv[1:])
    offer_fresh_copy(data_dir)
    app = make_app(data_dir)
    app.config["V3_TEST"] = True                      # the orange TEST COPY label
    print(f"v3 test site: http://localhost:{PORT}   (data: {data_dir})   close this window to stop it")
    if not os.environ.get("FT_RESTART"):
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
