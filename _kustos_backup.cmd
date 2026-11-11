@echo off
rem ------------------------------------------------------------------
rem An encrypted, versioned backup of this Kustos folder, every day.
rem It uses restic (install once: winget install restic.restic), which
rem encrypts on this computer before anything is written.
rem
rem   _kustos_backup.cmd            set it up: where, the password, the time
rem   _kustos_backup.cmd status     the last backups, checks and restore tests
rem   _kustos_backup.cmd run        a backup now
rem   _kustos_backup.cmd test       a backup now, and a restore test
rem   _kustos_backup.cmd remove     no more daily backups (the backup stays)
rem
rem Keep the backup's password OUTSIDE this computer too: without it the
rem backup cannot be opened by anyone, you included.
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

python "_kustos.py" backup %*
echo.
pause
