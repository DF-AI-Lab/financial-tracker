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
1. Drop your statement PDFs in the `statements` folder
2. Open PowerShell in this folder (File Explorer address bar: type `powershell`, Enter)
3. Run: `C:\ftvenv\Scripts\python.exe run.py`
   (one-off setup: `python -m venv C:\ftvenv` then `C:\ftvenv\Scripts\python.exe -m pip install pdfplumber`)
4. Results print on screen and are saved as CSV files in `output/`

The run checks every statement's balances (OK / CHECK), skips duplicate statements,
and lists any single payment of 1,000 or more under BIG ITEMS.
