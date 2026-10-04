@echo off
cd /d "%~dp0"
:start
C:\ftvenv\Scripts\python.exe web.py
rem 3 = the Update button got new code: start again with it
if errorlevel 3 if not errorlevel 4 (
  set FT_RESTART=1
  goto start
)
pause
