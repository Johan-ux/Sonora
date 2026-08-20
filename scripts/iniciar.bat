@echo off
REM ============================================================
REM  Atajo de desarrollo: activa el entorno virtual y arranca
REM  la app de escritorio "Sonora" (python -m sonora).
REM ============================================================
setlocal
REM Este script vive en scripts\; trabajamos desde la raiz del repositorio.
cd /d "%~dp0.."

REM Activar el entorno virtual si existe.
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo AVISO: no se encontro .venv; usando el Python del sistema.
)

python -m sonora
if errorlevel 1 (
    echo.
    echo La aplicacion termino con un error.
    pause
)

endlocal
