@echo off
rem ------------------------------------------------------------------
rem Copies the program from this repository to a Kustos folder.
rem Only the program goes; the data in that folder is never touched.
rem Refuses to copy while Kustos is open, here or on another computer.
rem
rem The first time it asks for the folder and keeps the answer in
rem tools\target.local.txt, which Git ignores. To choose again, delete
rem that file, or pass the folder:  update-instance.cmd "D:\my\kustos"
rem ------------------------------------------------------------------
setlocal
cd /d "%~dp0.."
set "SAVED=tools\target.local.txt"
set "TARGET=%~1"
if not defined TARGET if exist "%SAVED%" set /p TARGET=<"%SAVED%"
if defined TARGET goto chosen

set "PICK=Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'The Kustos folder to update'; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
for /f "usebackq delims=" %%F in (`powershell -NoProfile -STA -Command "%PICK%"`) do set "TARGET=%%F"
if not defined TARGET (
    echo No folder chosen; nothing was copied.
    pause
    exit /b 1
)

:chosen
if not exist "%TARGET%\_kustos.py" (
    echo No Kustos program in: %TARGET%
    echo Nothing was copied. Delete %SAVED% if this folder moved.
    pause
    exit /b 1
)
for %%I in ("%TARGET%\.") do if /i "%%~fI"=="%CD%" (
    echo That is this repository; nothing was copied.
    pause
    exit /b 1
)

rem Here: any python running _kustos.py, or whose command line cannot be read.
rem On another computer: a lock file under a day old, the age _kustos.py
rem itself trusts. If the check itself fails, nothing is copied either.
set "OPEN_HERE=Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and (-not $_.CommandLine -or $_.CommandLine -match '_kustos\.py') } | ForEach-Object { 'Open on this computer: ' + $_.Name + ', process ' + $_.ProcessId }"
set "OPEN_THERE=Get-ChildItem -LiteralPath $env:TARGET -Filter '_kustos.lock.*.json' | Where-Object { $_.Name -ne ('_kustos.lock.' + $env:COMPUTERNAME + '.json') -and $_.LastWriteTime -gt (Get-Date).AddDays(-1) } | ForEach-Object { 'Open on another computer: ' + $_.Name }"
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $open = @(%OPEN_HERE%) + @(%OPEN_THERE%); $open; exit [int]($open.Count -gt 0)" || (
    echo Kustos looks open, or the check could not run; nothing was copied.
    echo Close Kustos on every computer and run this again.
    pause
    exit /b 1
)

python -m py_compile _kustos.py || (
    echo _kustos.py has a syntax error; nothing was copied.
    pause
    exit /b 1
)

for %%F in (_kustos.py _kustos.cmd _kustos_logbook.cmd _kustos_peritia.cmd kustos.ico) do (
    copy /y "%%F" "%TARGET%\" >nul || (
        echo Could not copy %%F; the folder may be half updated. Run this again.
        pause
        exit /b 1
    )
)
>"%SAVED%" echo %TARGET%
echo Program copied to %TARGET%
pause
