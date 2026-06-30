/* ========================================================================== */
/* Descargador de Música — JavaScript                                        */
/* ========================================================================== */

/**
 * Formatea bytes a una cadena legible (KB, MB, GB).
 */
function formatearTamano(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

/**
 * Acorta una URL para mostrarla.
 */
function acortarUrl(url) {
    try {
        const u = new URL(url);
        return u.hostname + u.pathname.substring(0, 30) + (u.pathname.length > 30 ? '…' : '');
    } catch {
        return url.substring(0, 50);
    }
}

/**
 * Carga y muestra la lista de archivos MP3 descargados.
 */
async function cargarArchivos() {
    const contenedor = document.getElementById('lista-archivos');
    try {
        const resp = await fetch('/api/archivos');
        const archivos = await resp.json();

        if (archivos.length === 0) {
            contenedor.innerHTML = '<p class="vacio">No hay descargas todavía.</p>';
            return;
        }

        contenedor.innerHTML = archivos.map(f => `
            <div class="archivo">
                <span class="nombre" title="${f.nombre}">🎵 ${f.nombre}</span>
                <span>
                    <span class="tamano">${formatearTamano(f.tamaño)}</span>
                    <a href="/descargas/${encodeURIComponent(f.nombre)}">Descargar</a>
                </span>
            </div>
        `).join('');
    } catch {
        contenedor.innerHTML = '<p class="vacio">Error al cargar archivos.</p>';
    }
}

/**
 * Inicia la descarga enviando las URLs al servidor y conectando el stream SSE.
 */
async function iniciarDescarga() {
    const textarea = document.getElementById('urls');
    const bitrate = document.getElementById('bitrate').value;
    const btn = document.getElementById('btn-descargar');
    const texto = textarea.value.trim();

    if (!texto) {
        textarea.focus();
        return;
    }

    // Deshabilitar botón durante la descarga.
    btn.disabled = true;
    btn.innerHTML = '<span class="icono">⏳</span> Descargando…';

    // Mostrar sección de progreso.
    const secProgreso = document.getElementById('sec-progreso');
    const listaProgreso = document.getElementById('lista-progreso');
    const resumen = document.getElementById('resumen');
    secProgreso.classList.remove('oculto');
    listaProgreso.innerHTML = '';
    resumen.classList.add('oculto');

    try {
        const resp = await fetch('/api/descargar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: texto, bitrate }),
        });

        const datos = await resp.json();

        if (datos.error) {
            listaProgreso.innerHTML = `<p class="vacio">${datos.error}</p>`;
            rehabilitarBoton();
            return;
        }

        // Crear elementos de progreso para cada URL.
        const elementos = {};
        datos.urls.forEach(url => {
            const div = document.createElement('div');
            div.className = 'item-progreso';
            div.innerHTML = `
                <div class="fila-info">
                    <span class="titulo">${acortarUrl(url)}</span>
                    <span class="estado">Pendiente</span>
                </div>
                <div class="barra-contenedor">
                    <div class="barra" style="width: 0%"></div>
                </div>
            `;
            listaProgreso.appendChild(div);
            elementos[url] = div;
        });

        // Conectar al stream SSE.
        const sse = new EventSource(`/api/progreso/${datos.tarea_id}`);

        sse.onmessage = (event) => {
            const ev = JSON.parse(event.data);
            const el = elementos[ev.url];

            switch (ev.tipo) {
                case 'descargando':
                    if (el) {
                        el.querySelector('.estado').textContent = `Descargando (${ev.indice}/${ev.total})`;
                    }
                    break;

                case 'progreso':
                    if (el) {
                        const titulo = ev.titulo || acortarUrl(ev.url);
                        el.querySelector('.titulo').textContent = titulo;
                        el.querySelector('.barra').style.width = ev.progreso + '%';
                        const msg = ev.mensaje || `${ev.progreso}%`;
                        el.querySelector('.estado').textContent = msg;
                    }
                    break;

                case 'completado':
                    if (el) {
                        el.classList.add('completado');
                        el.querySelector('.barra').style.width = '100%';
                        el.querySelector('.estado').textContent = '✓ Completado';
                        if (ev.titulo) el.querySelector('.titulo').textContent = ev.titulo;
                    }
                    break;

                case 'error':
                    if (el) {
                        el.classList.add('error');
                        el.querySelector('.barra').style.width = '100%';
                        el.querySelector('.estado').textContent = '✗ Error';
                        el.querySelector('.titulo').title = ev.error || '';
                    }
                    break;

                case 'fin':
                    sse.close();
                    resumen.classList.remove('oculto');
                    if (ev.completados === ev.total) {
                        resumen.className = 'exito';
                        resumen.textContent = `✓ ${ev.completados}/${ev.total} descargas completadas`;
                    } else {
                        resumen.className = 'parcial';
                        resumen.textContent = `${ev.completados}/${ev.total} completadas — ${ev.total - ev.completados} fallidas`;
                    }
                    rehabilitarBoton();
                    cargarArchivos();
                    break;
            }
        };

        sse.onerror = () => {
            sse.close();
            rehabilitarBoton();
        };

    } catch (err) {
        listaProgreso.innerHTML = `<p class="vacio">Error de conexión: ${err.message}</p>`;
        rehabilitarBoton();
    }
}

function rehabilitarBoton() {
    const btn = document.getElementById('btn-descargar');
    btn.disabled = false;
    btn.innerHTML = '<span class="icono">⬇</span> Descargar';
}

// Cargar archivos al iniciar.
document.addEventListener('DOMContentLoaded', cargarArchivos);
