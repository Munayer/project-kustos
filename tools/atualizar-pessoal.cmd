@echo off
rem ------------------------------------------------------------------
rem Copia o codigo do repositorio para a pasta pessoal sincronizada.
rem Leva so o programa; os dados da pasta pessoal nao sao tocados.
rem Mude DESTINO se a pasta pessoal mudar de lugar.
rem ------------------------------------------------------------------
set "DESTINO=C:\bmm\sync\_bmm_index_v3"
cd /d "%~dp0.."

if not exist "%DESTINO%\" (
    echo Pasta pessoal nao encontrada: %DESTINO%
    pause
    exit /b 1
)

python -m py_compile _bmm_index.py || (
    echo _bmm_index.py tem erro de sintaxe; nada foi copiado.
    pause
    exit /b 1
)

copy /y "_bmm_index.py"  "%DESTINO%\" >nul
copy /y "_bmm_index.cmd" "%DESTINO%\" >nul
echo Codigo copiado para %DESTINO%
pause
