@echo off
rem One-time setup: installs flask, makes a desktop shortcut and starts the home page silently when Windows starts.
rem Run it again any time: it just remakes the shortcuts. Close any old black Financial Tracker window first.
cd /d "%~dp0"
set "HERE=%~dp0"

if not exist C:\ftvenv\Scripts\python.exe (
  echo Python not found at C:\ftvenv\Scripts\python.exe
  pause
  exit /b 1
)

echo 1/3 Installing flask...
C:\ftvenv\Scripts\python.exe -m pip install --quiet flask

echo 2/3 Making shortcuts (desktop + start silently with Windows)...
powershell -NoProfile -Command ^
  "$s = New-Object -ComObject WScript.Shell;" ^
  "$w = Join-Path $env:WINDIR 'System32\wscript.exe'; $q = [char]34;" ^
  "$d = $s.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Financial Tracker.lnk');" ^
  "$d.TargetPath = $w; $d.Arguments = $q + $env:HERE + 'hidden.vbs' + $q + ' open'; $d.WorkingDirectory = $env:HERE;" ^
  "$d.IconLocation = $env:HERE + 'static\app.ico'; $d.Save();" ^
  "$u = $s.CreateShortcut([Environment]::GetFolderPath('Startup') + '\Financial Tracker.lnk');" ^
  "$u.TargetPath = $w; $u.Arguments = $q + $env:HERE + 'hidden.vbs' + $q; $u.WorkingDirectory = $env:HERE; $u.Save()"

echo 3/3 Starting your home page (no black window)...
wscript "%HERE%hidden.vbs" open

echo.
echo Done. It now runs silently and starts by itself when you log in.
echo Open it: the Financial Tracker icon on your desktop, or http://127.0.0.1:5000
echo To stop it: double-click stop.bat
pause
