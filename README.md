# Sonora — Reproductor y gestor de descargas de música

**Sonora** es una **app de escritorio** (ventana propia, no el navegador) para
descargar música de YouTube a **MP3 de alta calidad** y reproducirla desde tu
propia biblioteca local. Interfaz negra con el acento en degradado (nueve
temas de color a elegir), con tres piezas en una sola ventana:

- 🔎 **Buscador integrado** de YouTube (texto, URLs, playlists y canales).
- ⬇️ **Gestor de descargas** a MP3 (hasta 320 kbps) con progreso en vivo,
  lotes, cancelación y reintentos.
- 🎧 **Reproductor + biblioteca** con aleatorio, repetición y control por
  teclas multimedia.

Construida con **Python + Flask + pywebview** y empaquetable a un `.exe` con
**PyInstaller**.

> ⚠️ Proyecto de uso **personal y privado**. No es comercial.

---

## 🚀 Empezar

```bash
# 1) Dependencias (requiere ffmpeg instalado en el sistema)
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 2) Arrancar la app
python -m sonora              # en Windows también: scripts\iniciar.bat
```

Guía detallada en [docs/instalacion.md](docs/instalacion.md).

---

## 📚 Documentación

| Documento                            | Contenido                                                |
| ------------------------------------ | -------------------------------------------------------- |
| [Instalación](docs/instalacion.md)   | Requisitos, ffmpeg, dependencias y dónde viven tus datos |
| [Uso](docs/uso.md)                   | Arranque, recorrido por la interfaz y atajos de teclado  |
| [CLI](docs/cli.md)                   | Descarga por lotes desde la terminal y cookies           |
| [Empaquetado](docs/empaquetado.md)   | Generar `Sonora.exe` con PyInstaller                     |
| [Arquitectura](docs/arquitectura.md) | Estructura del proyecto, decisiones de diseño, tests     |

---

## ✨ Funciones

- 🔎 **Buscador integrado**: busca por canción o artista, o pega una URL de
  vídeo, **playlist**, **canal** o **Mix** de YouTube. Con **filtros** como
  los de YouTube: orden (también por más recientes), fecha de subida,
  duración, tipo y características (4K, HD, subtítulos…).
- 📥 **Cola persistente**: sobrevive al reinicio (SQLite). Elige carpeta de
  destino y calidad; las preferencias **se recuerdan**.
- 🚦 **Gestión completa de descargas**: progreso en vivo por canción,
  **cancelar** la descarga en curso, **reintentar** las fallidas (una a una o
  todas), lotes plegables para playlists grandes y aviso de duplicados.
- 🎵 **MP3 de calidad**: bitrate configurable (128/192/256/**320** kbps) con
  **carátula** y **metadatos** incrustados. Los nombres de archivo incluyen el
  id del vídeo para que dos canciones con el mismo título no se pisen.
- 📚 **Biblioteca**: explora por carpetas, filtra al instante (los tags se
  cachean: rápido incluso con cientos de MP3).
- ▶️ **Reproductor**: play/pausa, anterior/siguiente, **aleatorio**,
  **repetir (lista/pista)**, barra de progreso, volumen persistente, teclas
  multimedia del sistema y atajos (espacio = play/pausa, `/` = buscar).
- 🎬 **Vídeo**: los MP4 de la biblioteca y la vista previa del buscador se ven
  en una ventana flotante que se mueve y se redimensiona a mano, en modo teatro
  o a pantalla completa; los de la biblioteca, con controles propios (posición,
  volumen y velocidad).
- 🕑 **Historial** de descargas completadas.
- ♿ **Accesible**: navegación por teclado completa, foco visible, lectores de
  pantalla (live regions), contraste AA y respeto de `prefers-reduced-motion`.
- 🖥️ **CLI incluida**: descarga por lotes desde la terminal con
  `python -m sonora.cli urls.txt`.

---

## 📁 Estructura

```text
sonora/       Paquete principal: app de escritorio (__main__, escritorio) y CLI (cli),
              con api/ (blueprints HTTP), servicios/ (lógica), db.py, templates/ y static/
datos/        Tus datos en desarrollo: descargas/ + biblioteca.db (fuera de git)
docs/         Documentación
ejemplos/     Ficheros de ejemplo (urls.example.txt para la CLI)
scripts/      iniciar.bat, construir_exe.bat y sonora.spec (PyInstaller)
tests/        Suite de pytest
```

Detalle completo en [docs/arquitectura.md](docs/arquitectura.md).

---

## 🧪 Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

---

## 📄 Aviso legal

Usa esta herramienta únicamente con contenido para el que tengas derechos o
permiso, y respeta los Términos de Servicio de YouTube y la legislación
aplicable sobre derechos de autor. Código bajo licencia MIT (ver
[`LICENSE`](LICENSE)).
