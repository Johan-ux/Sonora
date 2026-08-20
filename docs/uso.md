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
