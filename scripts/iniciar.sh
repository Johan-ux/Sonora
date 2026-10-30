#!/bin/sh
# ============================================================
#  Atajo para arrancar la app de escritorio "Sonora" en Linux y
#  macOS (python -m sonora), como scripts\iniciar.bat en Windows.
#
#  La primera vez prepara el entorno solo: busca un Python 3.11 o
#  posterior, crea el entorno virtual (o lo rehace si el que hay no
#  funciona) e instala las dependencias. Si falta ffmpeg, ofrece
#  instalarlo con el gestor de paquetes del sistema.
#
#  Los argumentos pasan a la app:  scripts/iniciar.sh --navegador
# ============================================================
set -u

# Este script vive en scripts/; trabajamos desde la raíz del repositorio.
cd "$(dirname "$0")/.." || exit 1

fallo() {
    printf '\nERROR: %s\n' "$1" >&2
    exit 1
}

# Un .venv de Windows en la misma carpeta (desde WSL, o una carpeta
# compartida) aquí no sirve, y rehacerlo rompería el de Windows: se usa otro.
VENV=.venv
if [ -f .venv/Scripts/python.exe ] && [ ! -d .venv/bin ]; then
    VENV=.venv-unix
fi
VENV_PY="$VENV/bin/python"

# yt-dlp y el resto exigen Python 3.11 o posterior.
python_valido() {
    "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1
}

buscar_python() {
    for candidato in python3 python3.14 python3.13 python3.12 python3.11 python; do
        if command -v "$candidato" >/dev/null 2>&1 && python_valido "$candidato"; then
            echo "$candidato"
            return 0
        fi
    done
    return 1
}

# La orden para instalar un paquete con el gestor del sistema, o nada.
orden_instalar() {
    if [ "$(uname -s)" = Darwin ]; then
        command -v brew >/dev/null 2>&1 && echo "brew install $1"
    elif command -v apt-get >/dev/null 2>&1; then
        echo "sudo apt-get install -y $1"
    elif command -v dnf >/dev/null 2>&1; then
        echo "sudo dnf install -y $1"
    elif command -v pacman >/dev/null 2>&1; then
        echo "sudo pacman -S --needed --noconfirm $1"
    elif command -v zypper >/dev/null 2>&1; then
        echo "sudo zypper install -y $1"
    fi
    return 0
}

crear_venv() {
    if ! PY=$(buscar_python); then
        orden=$(orden_instalar python3)
        [ "$(uname -s)" = Darwin ] && orden=$(orden_instalar python)
        fallo "no se encontró Python 3.11 o posterior.
Instálalo con ${orden:-el gestor de paquetes de tu sistema} (o desde
https://www.python.org/downloads/) y vuelve a ejecutar este script."
    fi
    echo "Preparando el entorno virtual $VENV con $PY..."
    if ! "$PY" -m venv --clear "$VENV"; then
        rm -rf -- "$VENV"
        # Debian y Ubuntu traen Python sin el módulo venv: va en otro paquete.
        if command -v apt-get >/dev/null 2>&1; then
            version=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
            fallo "falta el módulo venv de Python. Instálalo con:
    sudo apt install python$version-venv
y vuelve a ejecutar este script."
        fi
        fallo "no se pudo crear el entorno virtual $VENV."
    fi
}

# Sin pip no se puede instalar nada: un venv así también se rehace.
if ! "$VENV_PY" -c 'import sys, pip; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    crear_venv
fi

if ! "$VENV_PY" -c 'import flask, mutagen, webview, yt_dlp' >/dev/null 2>&1; then
    echo "Instalando dependencias, puede tardar un par de minutos..."
    "$VENV_PY" -m pip install -r requirements.txt ||
        fallo "no se pudieron instalar las dependencias.
Revisa la conexión a internet y vuelve a intentarlo."
fi

# ffmpeg no se instala con pip. Sin él Sonora se abre, pero no convierte a MP3.
if ! command -v ffmpeg >/dev/null 2>&1; then
    orden=$(orden_instalar ffmpeg)
    echo "Falta ffmpeg: sin él Sonora no puede convertir a MP3 ni unir los vídeos."
    if [ -n "$orden" ] && [ -t 0 ]; then
        printf '¿Instalarlo ahora con «%s»? [S/n] ' "$orden"
        read -r respuesta || respuesta=n
        case "$respuesta" in
            [nN]*) ;;
            *) $orden || echo "No se pudo instalar ffmpeg; Sonora se abre igual." ;;
        esac
    else
        echo "Instálalo con: ${orden:-el gestor de paquetes de tu sistema}"
    fi
fi

# Opcional: con un runtime de JavaScript, YouTube no niega formatos.
if ! command -v deno >/dev/null 2>&1 && ! command -v node >/dev/null 2>&1; then
    if [ "$(uname -s)" = Darwin ]; then
        echo "Recomendado: instala Deno con «brew install deno»."
    else
        echo "Recomendado: instala Deno con «curl -fsSL https://deno.land/install.sh | sh»."
    fi
fi

exec "$VENV_PY" -m sonora "$@"
