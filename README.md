# Financial Tracker

Personal tool: drop HSBC statement PDFs in a folder, get bills / spare cash / spending by month.
See the plan in the `python-finance-tracker` repo (`IDEA.md`).

- `fintrack/parse.py`: PDF to transactions
- `fintrack/sort.py`: income / bills (DD+SO) / random, plus monthly report
- `tests/`: fake statements (invented names) and the expected answers
- `tools/make_fake_statements.py`: rebuilds the fake PDFs

Run tests: `.venv/bin/pytest -q`

Real statements go in `statements/` (git-ignored). Never commit them.
