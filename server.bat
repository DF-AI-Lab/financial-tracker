@echo off
rem Runs the home page with no window (started by hidden.vbs). The Update button restarts it (exit code 3).
cd /d "%~dp0"
set FT_QUIET=1
:start
C:\ftvenv\Scripts\python.exe web.py
if errorlevel 3 if not errorlevel 4 goto start
