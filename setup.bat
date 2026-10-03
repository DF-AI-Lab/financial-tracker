@echo off
rem One-time setup: installs flask, makes a desktop shortcut and starts the home page when Windows starts.
cd /d "%~dp0"
set "HERE=%~dp0"

if not exist C:\ftvenv\Scripts\python.exe (
  echo Python not found at C:\ftvenv\Scripts\python.exe
  pause
  exit /b 1
)

echo 1/3 Installing flask...
C:\ftvenv\Scripts\python.exe -m pip install --quiet flask

echo 2/3 Making shortcuts (desktop + start with Windows)...
powershell -NoProfile -Command ^
  "$s = New-Object -ComObject WScript.Shell;" ^
  "$d = $s.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Financial Tracker.lnk');" ^
  "$d.TargetPath = $env:HERE + 'start.bat'; $d.WorkingDirectory = $env:HERE; $d.Save();" ^
  "$u = $s.CreateShortcut([Environment]::GetFolderPath('Startup') + '\Financial Tracker.lnk');" ^
  "$u.TargetPath = $env:HERE + 'start.bat'; $u.WorkingDirectory = $env:HERE; $u.WindowStyle = 7; $u.Save()"

echo 3/3 Starting your home page...
start "Financial Tracker" start.bat

echo.
echo Done. Desktop shortcut: Financial Tracker. It also starts by itself when you log in.
echo Bookmark: http://127.0.0.1:5000
pause
