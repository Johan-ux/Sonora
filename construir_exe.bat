@echo off
REM ============================================================
REM  Construye el ejecutable de "Mi Música" con PyInstaller.
REM  Resultado en:  dist\Mi Musica\Mi Musica.exe
REM ============================================================
setlocal
cd /d "%~dp0"

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
echo Construyendo "Mi Musica"...
"%PYTHON%" -m PyInstaller mi_musica.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: la construccion fallo.
    pause
    exit /b 1
)

echo.
echo Listo. El ejecutable esta en:  dist\Mi Musica\Mi Musica.exe
pause
endlocal
