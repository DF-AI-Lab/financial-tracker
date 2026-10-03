"""Step 9 of SPEC.md: the home page (Flask, on this PC only)."""
import sys
import threading
import webbrowser
from datetime import date
from pathlib import Path

try:
    from flask import Flask, render_template, request, redirect, url_for
except ImportError:
    raise ImportError("Flask is required. Install with: python -m pip install flask")

from fintrack.home import home_data
from fintrack.store import open_db, set_value, add_spend, delete_spend
from fintrack.left import parse_money
from fintrack.typed import parse_add
from fintrack.categories import guess_category
from fintrack.cycles import WAGE_PAYER


def create_app(db_path, wage_payer=WAGE_PAYER, today=None, updater=None, restart=None, statements_dir=None):
    """Create and configure the Flask app.

    Args:
        db_path: path to the database file
        wage_payer: the wage payer name
        today: optional reference date for home_data

    Returns:
        Flask app with all routes configured
    """
    # The Update button: updater() gets the new code (fintrack/update.py), restart() starts the page again with it
    # (exit code 3 tells start.bat to run web.py again). Tests pass their own.
    if updater is None:
        from fintrack.update import update_code as updater
    if restart is None:
        def restart():
            import os
            threading.Timer(1.0, lambda: os._exit(3)).start()

    # Convert to Path if needed
    db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
    statements_dir = Path(statements_dir) if statements_dir else db_path.parent / "statements"

    # Create app with templates folder at repo root
    template_folder = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(template_folder))

    # Register Jinja filters
    @app.template_filter('money')
    def filter_money(x):
        """Format as £1,234.56 or -£12.00 for negatives."""
        if x >= 0:
            return f"£{x:,.2f}"
        else:
            return f"-£{-x:,.2f}"

    @app.template_filter('diff')
    def filter_diff(x):
        """Format a difference as +£12.00 / -£20.83 / £0.00."""
        if x is None:
            return ""
        if abs(x) < 0.005:
            return "£0.00"
        return f"+£{x:,.2f}" if x > 0 else f"-£{-x:,.2f}"

    @app.template_filter('day')
    def filter_day(d):
        """Format as '5 Oct 2024'."""
        return f"{d.day} {d:%b %Y}"

    @app.template_filter('month')
    def filter_month(d):
        """Format as 'Oct 2024'."""
        return f"{d:%b %Y}"

    # GET /
    @app.route("/")
    def home():
        if not db_path.exists():
            open_db(db_path).close()                    # an empty database, so PDFs can be dropped on the page

        conn = open_db(db_path)
        d = home_data(conn, wage_payer=wage_payer, today=today)

        # Get error message from query string
        error = None
        error_code = request.args.get("error")
        if error_code == "pay":
            error = "Sorry, I could not read that as money."
        elif error_code == "spend":
            error = "Sorry, type an amount and a name, e.g. 12.50 and Costa."

        vfile = Path(__file__).parent / "version.txt"
        version = vfile.read_text().strip() if vfile.exists() else None
        return render_template("home.html", d=d, error=error, version=version)

    # POST /pay
    @app.route("/pay", methods=["POST"])
    def pay():
        wage_text = request.form.get("pay", "")
        wage = parse_money(wage_text)

        if wage is None:
            return redirect(url_for("home", error="pay"), code=303)

        conn = open_db(db_path)
        set_value(conn, "pay", str(wage))
        if request.form.get("clear") == "1":           # the page asked "New pay. Clear your typed spends?" -> yes
            from fintrack.store import clear_spends
            clear_spends(conn)
        conn.close()

        return redirect(url_for("home"), code=303)

    # POST /add
    @app.route("/add", methods=["POST"])
    def add():
        amount_str = request.form.get("amount", "")
        name_str = request.form.get("name", "")

        # Use parse_add to parse
        parsed = parse_add([amount_str, name_str])

        if parsed is None:
            return redirect(url_for("home", error="spend"), code=303)

        amount, name = parsed

        conn = open_db(db_path)
        category = guess_category(name)
        add_spend(conn, date.today() if today is None else today, amount, name, category)
        conn.close()

        return redirect(url_for("home"), code=303)

    # POST /bill: change a bill for this pay cycle only (empty amount = put it back)
    @app.route("/bill", methods=["POST"])
    def bill():
        from fintrack.billchange import set_change, clear_change
        key = request.form.get("key", "")
        amount_text = request.form.get("amount", "").strip()
        conn = open_db(db_path)
        d = home_data(conn, wage_payer=wage_payer, today=today)
        if not d["ready"] or key not in [b["key"] for b in d["pay"]["bills"]]:
            conn.close()
            return redirect(url_for("home"), code=303)
        if amount_text == "":
            clear_change(conn, d["cycle_start"], key)
        else:
            amount = parse_money(amount_text)
            if amount is None and amount_text.lstrip("£").replace(".", "").strip("0") == "":
                amount = 0.0                         # 0 = not paying it this month
            if amount is None:
                conn.close()
                if request.headers.get("X-Requested-With") == "fetch":
                    return ("", 400)
                return redirect(url_for("home", error="pay"), code=303)
            set_change(conn, d["cycle_start"], key, amount)
        conn.close()
        if request.headers.get("X-Requested-With") == "fetch":
            return ("", 204)                         # saved quietly by the page script, no reload
        return redirect(url_for("home"), code=303)

    # POST /left: left from last month, added to the spare cash until the next payday (empty amount = remove)
    @app.route("/left", methods=["POST"])
    def left():
        from fintrack.billchange import set_left, clear_left
        amount_text = request.form.get("amount", "").strip()
        conn = open_db(db_path)
        d = home_data(conn, wage_payer=wage_payer, today=today)
        if not d["ready"]:
            conn.close()
            return redirect(url_for("home"), code=303)
        if amount_text == "":
            clear_left(conn, d["cycle_start"])
        else:
            amount = parse_money(amount_text)
            if amount is None:
                conn.close()
                return redirect(url_for("home", error="pay"), code=303)
            set_left(conn, d["cycle_start"], amount)
        conn.close()
        return redirect(url_for("home"), code=303)

    # Layout (page only, kept for good): POST /layout {"sort", "ids"} after a drag, POST /name {"id", "name"},
    # POST /layout/reset puts the order back (names are kept).
    @app.route("/layout", methods=["POST"])
    def layout():
        from fintrack.layout import save_order, SORTS
        data = request.get_json(silent=True) or {}
        if data.get("sort") not in SORTS or not isinstance(data.get("ids"), list):
            return ("", 400)
        conn = open_db(db_path)
        save_order(conn, data["sort"], data["ids"])
        conn.close()
        return ("", 204)

    @app.route("/name", methods=["POST"])
    def name():
        from fintrack.layout import set_name
        data = request.get_json(silent=True) or {}
        if not isinstance(data.get("id"), str):
            return ("", 400)
        conn = open_db(db_path)
        set_name(conn, data["id"], str(data.get("name", ""))[:60])
        conn.close()
        return ("", 204)

    @app.route("/layout/reset", methods=["POST"])
    def layout_reset():
        from fintrack.layout import reset_order
        conn = open_db(db_path)
        reset_order(conn)
        conn.close()
        return redirect(url_for("home"), code=303)

    # POST /update: get the latest code from GitHub; restart only when something changed
    @app.route("/update", methods=["POST"])
    def update():
        try:
            r = updater()
        except Exception as e:                          # no internet, GitHub down, a bad download...
            return {"ok": False, "error": str(e)}
        if r["changed"]:
            restart()
        return {"ok": True, "changed": len(r["changed"]), "version": r["version"]}

    # No. 6 (3 Oct 2026): PDFs dropped on the page, and new items sorted on the page
    @app.route("/upload", methods=["POST"])
    def upload():
        from fintrack.inbox import import_pdf
        conn = open_db(db_path)
        results = []
        for f in request.files.getlist("files"):
            r = import_pdf(conn, statements_dir, f.filename or "", f.read())
            for k in ("start", "end"):
                if r.get(k):
                    r[k] = f"{r[k].day} {r[k]:%b %Y}"
            results.append(r)
        conn.close()
        return {"results": results}

    @app.route("/sort/parse", methods=["POST"])
    def sort_parse():
        from fintrack.sortpage import parse_ai, category_names
        data = request.get_json(silent=True) or {}
        conn = open_db(db_path)
        got = parse_ai(str(data.get("text", "")), int(data.get("count", 0) or 0), category_names(conn))
        conn.close()
        return {str(n): v for n, v in got.items()}

    @app.route("/sort/save", methods=["POST"])
    def sort_save():
        from fintrack.sortpage import save_answers
        data = request.get_json(silent=True) or {}
        conn = open_db(db_path)
        save_answers(conn, data.get("answers") or [])
        conn.close()
        return ("", 204)

    # POST /remove
    @app.route("/remove", methods=["POST"])
    def remove():
        spend_id_str = request.form.get("id", "")

        try:
            spend_id = int(spend_id_str)
            conn = open_db(db_path)
            delete_spend(conn, spend_id)
            conn.close()
        except (ValueError, TypeError):
            # Ignore bad id
            pass

        return redirect(url_for("home"), code=303)

    return app


def main():
    """Run the home page server.

    Opens the database at the same path run.py uses (via pick_folder) and starts
    a Flask server at 127.0.0.1:5000.
    """
    # Find the database exactly like run.py does (the remembered folder, else the statements folder)
    from run import pick_folder
    db_path = pick_folder(sys.argv[1:]).parent / "tracker.db"


    print("Opening your home page... (close this window to stop it)")

    # Create the app
    app = create_app(db_path, wage_payer=WAGE_PAYER, statements_dir=pick_folder(sys.argv[1:]))

    # Open browser after a short delay (not after an update: the page is already open and reloads itself)
    import os
    if os.environ.get("FT_RESTART"):
        app.run(host="127.0.0.1", port=5000, debug=False)
        return

    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")

    timer = threading.Timer(1.0, open_browser)
    timer.daemon = True
    timer.start()

    # Run the app
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
