@echo off
rem ------------------------------------------------------------------
rem Copies the program from the repository to the synced personal folder.
rem Only the program goes; the personal folder's data is never touched.
rem Refuses to copy while Kustos is open, here or on the other computer.
rem Change TARGET if the personal folder moves.
rem ------------------------------------------------------------------
set "TARGET=C:\path\to\kustos"
cd /d "%~dp0.."

if not exist "%TARGET%\" (
    echo Personal folder not found: %TARGET%
    pause
    exit /b 1
)

rem Here: any python running _kustos.py, or whose command line cannot be read.
rem On the other computer: a lock file under a day old, the age _kustos.py
rem itself trusts. If the check itself fails, nothing is copied either.
set "OPEN_HERE=Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and (-not $_.CommandLine -or $_.CommandLine -match '_kustos\.py') } | ForEach-Object { 'Open on this computer: ' + $_.Name + ', process ' + $_.ProcessId }"
set "OPEN_THERE=Get-ChildItem -LiteralPath $env:TARGET -Filter '_kustos.lock.*.json' | Where-Object { $_.Name -ne ('_kustos.lock.' + $env:COMPUTERNAME + '.json') -and $_.LastWriteTime -gt (Get-Date).AddDays(-1) } | ForEach-Object { 'Open on another computer: ' + $_.Name }"
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $open = @(%OPEN_HERE%) + @(%OPEN_THERE%); $open; exit [int]($open.Count -gt 0)" || (
    echo Kustos looks open, or the check could not run; nothing was copied.
    echo Close Kustos on both computers and run this again.
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
copy /y "_kustos_peritia.cmd" "%TARGET%\" >nul
copy /y "kustos.ico" "%TARGET%\" >nul
echo Program copied to %TARGET%
pause
