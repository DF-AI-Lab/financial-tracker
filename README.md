# Financial Tracker

Personal tool: drop HSBC statement PDFs in a folder, get bills / spare cash / spending by month.
See the plan in the `python-finance-tracker` repo (`IDEA.md`).

- `fintrack/parse.py`: PDF to transactions
- `fintrack/sort.py`: income / bills (DD+SO) / random, plus monthly report
- `tests/`: fake statements (invented names) and the expected answers
- `tools/make_fake_statements.py`: rebuilds the fake PDFs

Run tests: `.venv/bin/pytest -q`

Real statements go in `statements/` (git-ignored). Never commit them.

## Run it on Windows
1. Put your statement PDFs in the `statements` folder that sits NEXT TO this code folder
   (e.g. `Financial Tracker Project\statements`). `python run.py test` uses the
   `statements` folder inside the code folder instead (for testing).
2. Open PowerShell in this folder (File Explorer address bar: type `powershell`, Enter)
3. Run: `C:\ftvenv\Scripts\python.exe run.py`
   (one-off setup: `python -m venv C:\ftvenv` then `C:\ftvenv\Scripts\python.exe -m pip install pdfplumber`)
4. Results print on screen and are saved as CSV files in `output/`

The run checks every statement's balances (OK / CHECK), skips duplicate statements,
and lists any single payment of 1,000 or more under BIG ITEMS.

## Home page
1. One-time setup: `C:\ftvenv\Scripts\python.exe -m pip install flask`
2. Double-click `start.bat` (or run `C:\ftvenv\Scripts\python.exe web.py` in PowerShell)
3. Your browser opens at http://127.0.0.1:5000 with all your spare cash, bills, spending and where the money went

Quick setup (does steps 1-2 and more): double-click `setup.bat` once. It installs flask, puts a
`Financial Tracker` shortcut on your desktop, starts the page when Windows starts, and opens it now.
Bookmark http://127.0.0.1:5000 (works while the black window is open; minimise it, don't close it).

## New statements
Drop the PDFs anywhere on the home page (or click the dashed bar). New items show in a **❓ new items to sort** card:
my guesses are picked, change any, then **Save**. Or **📋 Copy for AI**, paste into ChatGPT / Claude, copy its reply,
**📥 Paste answers**, check, **Save**.
Any other questions (same bill?, is this your rent?, a typed spend not in the statements) show in a
**❓ quick questions** card: one click each.

## Updates
Click **🔄 Update** at the top of the home page. It gets the latest version from GitHub and restarts the page.
If the page will not open, double-click `update.bat` in the code folder instead, then `start.bat`.
Your statements, `tracker.db` and settings are never touched.

The page runs on your PC only (no login, no upload). New statements still go through `run.py`.

## Commands
- `run.py` reads the statements, asks about new items, then prints the reports and asks for your latest pay
- `run.py test` uses the `statements` folder inside the code folder
- `run.py fix` lists your saved answers so you can change them (e.g. `oneoff 3`, `label 2 Rent`)
- `run.py folder "C:\path\to\statements"` remembers your statements folder
- `run.py early` lists payments made in the 3 days before a payday; `run.py early 1` counts one from that payday (e.g. rent sent a day early; same again = undo)
- `run.py wage "NEW EMPLOYER"` after a job change: money in from that name (500 or more) also counts as your wage (`run.py wage` lists them)

Your data lives in `tracker.db` next to the statements folder. It is never committed to Git.
