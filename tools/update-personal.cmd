@echo off
rem ------------------------------------------------------------------
rem Copies the program from the repository to the synced personal folder.
rem Only the program goes; the personal folder's data is never touched.
rem Change TARGET if the personal folder moves.
rem ------------------------------------------------------------------
set "TARGET=C:\bmm\sync\_bmm_index_v3"
cd /d "%~dp0.."

if not exist "%TARGET%\" (
    echo Personal folder not found: %TARGET%
    pause
    exit /b 1
)

python -m py_compile _kustos.py || (
    echo _kustos.py has a syntax error; nothing was copied.
    pause
    exit /b 1
)

copy /y "_kustos.py"  "%TARGET%\" >nul
copy /y "_kustos.cmd" "%TARGET%\" >nul
copy /y "_kustos_logbook.cmd" "%TARGET%\" >nul
echo Program copied to %TARGET%
pause
