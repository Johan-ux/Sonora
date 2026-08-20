@echo off
REM ============================================================
REM  Construye el ejecutable de "Sonora" con PyInstaller.
REM  Resultado en:  dist\Sonora\Sonora.exe
REM ============================================================
setlocal
REM Este script vive en scripts\; PyInstaller escribe build\ y dist\ en el
REM directorio actual, asi que trabajamos desde la raiz del repositorio.
cd /d "%~dp0.."

REM Usar el Python del entorno virtual si existe; si no, el Python del sistema.
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

echo Usando interprete: %PYTHON%

REM Comprobar que PyInstaller esta instalado; si falta, instalarlo.
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller no encontrado. Instalando...
    "%PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo ERROR: no se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Construyendo "Sonora"...
"%PYTHON%" -m PyInstaller "scripts\sonora.spec" --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: la construccion fallo.
    pause
    exit /b 1
)

echo.
echo Listo. El ejecutable esta en:  dist\Sonora\Sonora.exe
pause
endlocal
