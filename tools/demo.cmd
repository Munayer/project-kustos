@echo off
rem ------------------------------------------------------------------
rem Opens Kustos on a base of INVENTED records -- the same as the web
rem demo's -- in %TEMP%\kustos_demo, apart from your own Kustos folder:
rem to try a change, to compare the window with the web page on the
rem same records, or to take pictures that can be shared.
rem
rem   demo.cmd              the window
rem   demo.cmd web          the web page, in the browser
rem   demo.cmd fresh        new invented records first (the old ones go)
rem   demo.cmd pt           in Portuguese (en: in English)
rem
rem Double-click it, or type it in the repository folder (in PowerShell
rem with .\ before it: .\tools\demo.cmd web).
rem The words combine: demo.cmd web fresh pt. The program there is this
rem repository's, copied every time; the records are kept until fresh.
rem Your own folder is never read or written.
rem ------------------------------------------------------------------
setlocal
cd /d "%~dp0.."
set "DEMO=%TEMP%\kustos_demo"
set "SHOW="
for %%A in (%*) do if /i "%%~A"=="web" set "SHOW=web"

python tools\demo_base.py "%DEMO%" %* || (
    echo The demo base could not be made; see above.
    pause
    exit /b 1
)
call "%DEMO%\_kustos.cmd" %SHOW%
