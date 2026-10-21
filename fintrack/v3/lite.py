"""Lite (map #22, 21 Oct 2026): the same page from its own copy of the templates, so it can change without touching /.

/lite       = basic/templates + basic/static           (the Lite app)
/lite/demo  = basic_demo/templates + basic_demo/static (a copy to try changes on before they go to /lite)
Same data and the same sign-in as the main page; the forms still post to the main routes.
"""
from pathlib import Path

from flask import abort, request, send_from_directory
from jinja2 import FileSystemLoader

from fintrack.appversion import VERSION
from fintrack.home import home_data
from fintrack.store import open_db

ROOT = Path(__file__).resolve().parents[2]
COPIES = {"lite": ROOT / "basic", "lite_demo": ROOT / "basic_demo"}
ERRORS = {"pay": "Sorry, I could not read that as money.",
          "spend": "Sorry, type an amount and a name, e.g. 12.50 and Costa.",
          "card": "Sorry, type an amount and a name for the credit card, e.g. 40 and Shell."}


def page(app, folder: Path) -> str:
    """home.html from folder/templates with the main page's data (filters and globals shared with the app)."""
    env = app.jinja_env.overlay(loader=FileSystemLoader(str(folder / "templates")))
    db = app.config["V3_DATA_DIR"] / "tracker.db"
    if not db.exists():
        open_db(db).close()
    conn = open_db(db)
    try:
        d = home_data(conn, wage_payer=app.config["V3_WAGE_PAYER"], today=app.config["V3_TODAY"])
    finally:
        conn.close()
    code = request.args.get("error")
    vfile = ROOT / "version.txt"
    ctx = dict(d=d, error=ERRORS.get(code), error_at=code, demo=True, app_version=VERSION, cloud=True,
               version=vfile.read_text().strip() if vfile.exists() else None)
    app.update_template_context(ctx)
    return env.get_template("home.html").render(ctx)


def register(app) -> None:
    for name, prefix in (("lite", "/lite"), ("lite_demo", "/lite/demo")):
        folder = COPIES[name]

        def view(folder=folder):
            return page(app, folder)

        def static(path, folder=folder):
            if not (folder / "static" / path).is_file():
                abort(404)
            return send_from_directory(folder / "static", path)

        app.add_url_rule(prefix, name, view)
        app.add_url_rule(prefix + "/static/<path:path>", name + "_static", static)
