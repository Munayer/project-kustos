@echo off
rem ------------------------------------------------------------------
rem Double-click to open the logbook (read-only).
rem Opens the base in this same folder as a logbook, without a console window
rem when pythonw is available.
rem ------------------------------------------------------------------
cd /d "%~dp0"

where pythonw >nul 2>&1 && goto :sem_console
where python  >nul 2>&1 && goto :com_console

echo.
echo   Python was not found on the PATH.
echo   Install Python 3.10 or newer, ticking
echo   "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:sem_console
start "" pythonw "_kustos.py" logbook
exit /b 0

:com_console
python "_kustos.py" logbook
exit /b 0
