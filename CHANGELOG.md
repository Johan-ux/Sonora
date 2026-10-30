# Registro de cambios

Los cambios que se notan al usar Sonora, versión a versión. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones,
el [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

## [1.1.0] - 2026-10-30

Sonora funciona también en Linux y macOS, desde el código.

### Añadido

- Sonora se abre en el navegador cuando no puede abrir su ventana: así
  funciona también en Linux. Se puede pedir con `python -m sonora --navegador`.
  Sin ventana, se cierra sola al cerrar su pestaña.
- `scripts/iniciar.sh` (y `iniciar.command` para abrir con doble clic en
  macOS) prepara Sonora en Linux y macOS como `iniciar.bat` en Windows: crea
  el entorno, instala las dependencias y ofrece instalar ffmpeg si falta.
- Los dos atajos de arranque pasan sus argumentos a la app:
  `scripts\iniciar.bat --navegador` o `scripts/iniciar.sh --navegador`.
- Los avisos de la barra lateral dicen cómo instalar ffmpeg y Deno en el
  sistema en el que estás, no siempre con `winget`.

### Corregido

- Abrir Sonora estando ya abierta podía traer al frente otra ventana que se
  llamara igual, como el Explorador en la carpeta del zip, en vez de la suya.
- `iniciar.bat` aceptaba Python 3.9 y 3.10, con los que las dependencias no
  llegan a instalarse: ahora pide 3.11 o posterior.

## [1.0.0] - 2026-10-30

Primera versión publicada.

### Añadido

- Buscador de YouTube dentro de la app: por canción o artista, o pegando la
  URL de un vídeo, una playlist, un canal o un Mix. Con filtros de orden,
  fecha de subida, duración, tipo y características.
- Vista previa de un resultado antes de decidir si se descarga.
- Descargas a MP3 de 128 a 320 kbps, con carátula y metadatos, o a MP4 hasta
  4K. Cola que sobrevive al cierre, varias descargas a la vez, cancelación,
  reintentos y aviso de duplicados.
- Biblioteca por carpetas con filtro al instante, y reproductor con aleatorio,
  repetición, teclas multimedia y atajos de teclado.
- Ventana de vídeo flotante que se mueve y se redimensiona, con modo teatro y
  pantalla completa.
- Historial de descargas.
- Nueve temas de color y vista de Configuración.
- Aviso cuando yt-dlp se queda viejo y actualización en un clic.
- Ejecutable para Windows que no necesita instalar nada: lleva ffmpeg y el
  runtime de JavaScript dentro, y yt-dlp se actualiza desde la propia app.
- CLI para descargar por lotes desde la terminal.

[Sin publicar]: https://github.com/Johan-ux/Sonora/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Johan-ux/Sonora/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Johan-ux/Sonora/releases/tag/v1.0.0
