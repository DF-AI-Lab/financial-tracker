@echo off
rem Stops the home page running in the background (the silent one started by hidden.vbs).
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*web.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Stopped. Start it again with the Financial Tracker shortcut.
pause
