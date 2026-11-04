@echo off
rem ------------------------------------------------------------------
rem Double-click to open Peritia, the skills panel, in the browser.
rem _kustos.py serves it on 127.0.0.1 and stops by itself two minutes
rem after the page is closed. No console window when pythonw is available.
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
start "" pythonw "_kustos.py" peritia
exit /b 0

:com_console
python "_kustos.py" peritia
exit /b 0
