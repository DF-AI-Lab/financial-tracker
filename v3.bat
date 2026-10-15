@echo off
rem v3 test site at http://localhost:5001 (its own copy of your data in the v3data folder). Keep this window open.
cd /d "%~dp0"
:start
C:\ftvenv\Scripts\python.exe v3app.py
if errorlevel 3 if not errorlevel 4 (
  set FT_RESTART=1
  goto start
)
pause
