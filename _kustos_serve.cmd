@echo off
rem ------------------------------------------------------------------
rem Kustos's web app for your own devices, behind its login: it starts
rem at every Windows login, in the background, with Tailscale in front.
rem
rem   _kustos_serve.cmd            set it up (again after any change)
rem   _kustos_serve.cmd status     is it running? the last logins
rem   _kustos_serve.cmd stop       stop it until the next login
rem   _kustos_serve.cmd start      start it again
rem   _kustos_serve.cmd remove     no more starting with Windows
rem
rem It asks for the password first if none is set (python _kustos.py
rem passwd). Nothing here opens it to the internet: only the devices of
rem your own Tailscale account can reach it.
rem ------------------------------------------------------------------
cd /d "%~dp0"

where python >nul 2>&1 || (
    echo.
    echo   Python was not found on the PATH.
    echo   Install Python 3.10 or newer, ticking
    echo   "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python "_kustos.py" service %*
echo.
pause
