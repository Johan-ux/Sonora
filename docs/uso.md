# Uso (desarrollo)

La forma más sencilla en Windows es ejecutar el atajo:

```bash
scripts\iniciar.bat
```

`iniciar.bat` activa el entorno virtual (`.venv`) y lanza la app. De forma
equivalente, desde la raíz del repositorio:

```bash
python -m sonora
```

En ambos casos se abre la **ventana propia** de Sonora (no el navegador). Por
dentro, la app arranca un pequeño servidor Flask en `127.0.0.1` sobre un puerto
libre y abre esa ventana con `pywebview`. Al cerrar la ventana, la app termina
por completo.

## De un vistazo

- **Buscar**: escribe y pulsa Enter (o pega una URL). Pulsa **＋** en cualquier
  resultado para añadirlo a la cola; con playlists puedes añadir **todo** o por
  **lotes de 100**.
- **Descargas**: elige carpeta de destino y calidad (se recuerdan) y pulsa
  **Descargar todo**. Puedes cancelar la descarga en curso, quitar pendientes
  y reintentar las fallidas.
- **Biblioteca**: pulsa play en cualquier pista; usa aleatorio/repetir y las
  teclas multimedia del sistema.
- **Historial**: consulta lo descargado anteriormente.

## Escuchar antes de descargar

Cada resultado de búsqueda tiene un botón de reproducción sobre su miniatura:
abre una ventana con el reproductor de YouTube para decidir si la canción es la
que buscabas antes de gastar la descarga. Desde ahí se añade a la cola
directamente.

Se usa el reproductor incrustado de YouTube (dominio `youtube-nocookie.com`,
que no planta cookies de seguimiento) en lugar de traer el audio por nuestra
cuenta: las URLs de stream van firmadas y caducan, así que un reproductor
propio se rompería solo. Requiere conexión, y los vídeos cuyo autor prohíbe
incrustarlos mostrarán en su lugar un aviso de YouTube.

## Descargas en paralelo

Por defecto se descargan **tres canciones a la vez**; se ajusta en
**Descargas → A la vez** (de 1 a 5). Con una playlist grande la diferencia es
notable, porque mientras una pista se convierte a MP3 las otras siguen
bajando. Subirlo mucho no siempre es mejor: YouTube estrangula la conexión
cuando se le piden demasiadas cosas a la vez.

El cambio se aplica a la siguiente tanda; las descargas ya en marcha terminan
lo suyo.

## Reintentos automáticos

Si una descarga falla por algo pasajero —un corte de red, un error del
servidor— se reintenta sola hasta tres veces, esperando un poco más en cada
intento. Los fallos definitivos (vídeo privado, borrado o bloqueado en tu
país) no se reintentan: se marcan como error directamente, para no hacer
esperar al resto de la cola.

Al cancelar una descarga (o cuando falla del todo) se borran los ficheros a
medias que deja yt-dlp, en lugar de quedarse ocupando sitio en la carpeta de
música para siempre.

## Aviso de actualización

Al abrir Sonora se comprueba el entorno y, si algo merece tu atención, aparece
un aviso abajo en la barra lateral:

- **Hay una versión nueva de yt-dlp.** Es lo que conviene vigilar: YouTube
  cambia a menudo y un yt-dlp viejo deja de descargar (`HTTP Error 403`). El
  botón **Actualizar ahora** lanza `pip install --upgrade yt-dlp` desde la
  propia app; al terminar hay que **reiniciar Sonora** para que surta efecto.
- **Tu yt-dlp pasa de 90 días** y no se pudo consultar si hay uno más nuevo
  (sin conexión, por ejemplo).
- **Falta un runtime de JavaScript**, con la orden para instalarlo.

Si no hay nada que decir, el aviso no se muestra. La comprobación consulta
PyPI con un tiempo de espera corto y cachea el resultado seis horas, así que no
retrasa el arranque; sin conexión, la app abre igual y no avisa de nada.

> En la app **empaquetada** (`.exe`), yt-dlp va dentro del ejecutable y pip no
> puede actualizarlo: el aviso lo dice y hay que reconstruirla
> (ver [empaquetado.md](empaquetado.md)).

## Atajos de teclado

| Tecla             | Acción                    |
| ----------------- | ------------------------- |
| `Espacio`         | Play / pausa              |
| `/`               | Ir al buscador            |
| Teclas multimedia | Play, anterior, siguiente |

La interfaz es navegable por completo con teclado, con foco visible, *live
regions* para lectores de pantalla, contraste AA y respeto de
`prefers-reduced-motion`.

---

Siguiente: [CLI](cli.md) · [Empaquetado](empaquetado.md) · [Arquitectura](arquitectura.md)
