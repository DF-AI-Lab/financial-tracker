@echo off
rem Gets the latest version from GitHub. Your statements and tracker.db are not touched.
cd /d "%~dp0"
C:\ftvenv\Scripts\python.exe -m fintrack.update
pause
