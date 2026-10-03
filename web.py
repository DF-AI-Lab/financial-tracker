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


def create_app(db_path, wage_payer=WAGE_PAYER, today=None):
    """Create and configure the Flask app.

    Args:
        db_path: path to the database file
        wage_payer: the wage payer name
        today: optional reference date for home_data

    Returns:
        Flask app with all routes configured
    """
    # Convert to Path if needed
    db_path = Path(db_path) if not isinstance(db_path, Path) else db_path

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
            return render_template("home.html", d={"ready": False}, error="Run run.py first")

        conn = open_db(db_path)
        d = home_data(conn, wage_payer=wage_payer, today=today)

        # Get error message from query string
        error = None
        error_code = request.args.get("error")
        if error_code == "pay":
            error = "Sorry, I could not read that as money."
        elif error_code == "spend":
            error = "Sorry, type an amount and a name, e.g. 12.50 and Costa."

        return render_template("home.html", d=d, error=error)

    # POST /pay
    @app.route("/pay", methods=["POST"])
    def pay():
        wage_text = request.form.get("pay", "")
        wage = parse_money(wage_text)

        if wage is None:
            return redirect(url_for("home", error="pay"), code=303)

        conn = open_db(db_path)
        set_value(conn, "pay", str(wage))
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

    if not db_path.exists():
        print("No database yet. Run run.py first.")
        return

    print("Opening your home page... (close this window to stop it)")

    # Create the app
    app = create_app(db_path, wage_payer=WAGE_PAYER)

    # Open browser after a short delay
    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")

    timer = threading.Timer(1.0, open_browser)
    timer.daemon = True
    timer.start()

    # Run the app
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
