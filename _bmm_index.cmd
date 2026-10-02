@echo off
rem ------------------------------------------------------------------
rem Duplo clique para abrir o Index.
rem Abre _bmm_index.py desta mesma pasta, sem janela de console
rem quando o pythonw estiver disponivel.
rem ------------------------------------------------------------------
cd /d "%~dp0"

where pythonw >nul 2>&1 && goto :sem_console
where python  >nul 2>&1 && goto :com_console

echo.
echo   Python nao foi encontrado no PATH.
echo   Instale o Python 3.10 ou mais novo marcando a opcao
echo   "Add Python to PATH" durante a instalacao.
echo.
pause
exit /b 1

:sem_console
start "" pythonw "_bmm_index.py" %*
exit /b 0

:com_console
python "_bmm_index.py" %*
exit /b 0
