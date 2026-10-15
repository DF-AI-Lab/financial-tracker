"""v3 move-in (15 Oct 2026): writes v3_settings.json on PythonAnywhere by asking a few questions, so nothing has to
be edited by hand. Run in a PythonAnywhere Bash console:

    ~/wmm-venv/bin/python ~/whereismymoney/tools/pa_setup.py

The Gmail app password is typed without showing on screen and only ever stored in the data folder (never GitHub).
"""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import v3app  # noqa: E402

DATA = Path.home() / "wmm-data"


def wsgi_file() -> str:
    user = os.environ.get("USER") or Path.home().name
    return f"/var/www/{user.lower()}_pythonanywhere_com_wsgi.py"          # PythonAnywhere names it in lower case


def main(ask=input, secret=getpass.getpass, data=DATA) -> dict:
    s = v3app.load_settings(data)
    print("\nWhere's My Money? settings (press Enter to keep what is in [brackets])\n")
    email = ask(f"Your email, the only one that can sign in [{s['email']}]: ").strip() or s["email"]
    gmail = ask(f"The Gmail address that sends the codes [{s['smtp_user'] or email}]: ").strip() or s["smtp_user"] or email
    pw = secret("The 16-letter Gmail app password (it won't show as you type): ").replace(" ", "").strip()
    s.update({"email": email, "smtp_user": gmail, "update": "git", "branch": "v3", "wsgi_file": wsgi_file()})
    if pw:
        s["smtp_password"] = pw
    v3app.save_settings(data, s)
    print(f"\nSaved in {data / 'v3_settings.json'}")
    print("Email:", s["email"], "| Gmail:", s["smtp_user"], "| app password:", "set" if s["smtp_password"] else "MISSING")
    return s


if __name__ == "__main__":
    main()
