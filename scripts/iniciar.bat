@echo off
REM ============================================================
REM  Atajo para arrancar la app de escritorio "Sonora"
REM  (python -m sonora) con el Python del entorno virtual.
REM
REM  La primera vez prepara el entorno solo: si no hay .venv, o el
REM  que hay no funciona, lo crea con el Python del sistema e
REM  instala las dependencias. Un .venv copiado de otro equipo no
REM  funciona: guarda la ruta absoluta del Python con el que se creo.
REM
REM  Los argumentos pasan a la app:  scripts\iniciar.bat --navegador
REM ============================================================
setlocal
REM Este script vive en scripts\; trabajamos desde la raiz del repositorio.
cd /d "%~dp0.."

REM Se usa el python del venv directamente, sin activate.bat: este lleva
REM escrita la ruta absoluta de la carpeta donde se creo el venv.
set "VENV_PY=.venv\Scripts\python.exe"

"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    call :crear_venv
    if errorlevel 1 goto :fallo
)

"%VENV_PY%" -c "import flask, mutagen, webview, yt_dlp" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias, puede tardar un par de minutos...
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: no se pudieron instalar las dependencias.
        echo Revisa la conexion a internet y vuelve a intentarlo.
        goto :fallo
    )
)

"%VENV_PY%" -m sonora %*
if errorlevel 1 (
    echo.
    echo La aplicacion termino con un error.
    goto :fallo
)
endlocal
exit /b 0

:crear_venv
REM Busca un Python 3.11+ del sistema: primero el lanzador "py" (lo instalan
REM tanto python.org como el gestor de instalacion de Python) y luego
REM "python". El "python" que trae Windows cuando no hay ninguno instalado
REM es un atajo a la Microsoft Store que no ejecuta codigo: no pasa la prueba.
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: no se encontro Python 3.11 o superior.
    echo Instalalo desde https://www.python.org/downloads/ y vuelve a ejecutar este script.
    exit /b 1
)
echo Preparando el entorno virtual .venv...
%PY% -m venv --clear .venv
if errorlevel 1 (
    echo ERROR: no se pudo crear el entorno virtual .venv.
    exit /b 1
)
exit /b 0

:fallo
echo.
pause
endlocal
exit /b 1
