/* ========================================================================== */
/* Descargador de Música — JavaScript (Layout 70/30)                         */
/* ========================================================================== */

// Estado global
let videoActual = null;
let carpetaDestino = '';
let rutaExplorador = '';
let historialUrls = [];
let posHistorial = -1;
let sse = null;

// --------------------------------------------------------------------------- //
// Utilidades
// --------------------------------------------------------------------------- //

function formatearTamano(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function esUrlYoutube(url) {
    try {
        const u = new URL(url);
        return u.hostname.includes('youtube.com') || u.hostname.includes('youtu.be');
    } catch {
        return false;
    }
}

function extraerVideoId(url) {
    try {
        const u = new URL(url);
        if (u.hostname.includes('youtu.be')) return u.pathname.slice(1);
        if (u.searchParams.has('v')) return u.searchParams.get('v');
    } catch { /* ignorar */ }
    return null;
}

// --------------------------------------------------------------------------- //
// Navegación YouTube (iframe)
// --------------------------------------------------------------------------- //

function navegarA(url) {
    if (!url) return;
    if (!url.startsWith('http')) url = 'https://' + url;
    const frame = document.getElementById('youtube-frame');
    frame.src = url;
    document.getElementById('barra-url').value = url;

    // Historial simple
    if (posHistorial < historialUrls.length - 1) {
        historialUrls = historialUrls.slice(0, posHistorial + 1);
    }
    historialUrls.push(url);
    posHistorial = historialUrls.length - 1;

    // Auto-detectar si es un video
    if (esUrlYoutube(url) && extraerVideoId(url)) {
        document.getElementById('input-url-video').value = url;
    }
}

function navegarAtras() {
    if (posHistorial > 0) {
        posHistorial--;
        const url = historialUrls[posHistorial];
        document.getElementById('youtube-frame').src = url;
        document.getElementById('barra-url').value = url;
    }
}

function navegarAdelante() {
    if (posHistorial < historialUrls.length - 1) {
        posHistorial++;
        const url = historialUrls[posHistorial];
        document.getElementById('youtube-frame').src = url;
        document.getElementById('barra-url').value = url;
    }
}

function navegarHome() {
    navegarA('https://www.youtube.com');
}

// --------------------------------------------------------------------------- //
// Detección de URL y obtención de info
// --------------------------------------------------------------------------- //

async function detectarUrl() {
    const input = document.getElementById('input-url-video');
    const url = input.value.trim();
    if (!url) { input.focus(); return; }

    const infoDiv = document.getElementById('info-video');
    infoDiv.innerHTML = '<p class="texto-muted texto-centro"><span class="spinner"></span> Obteniendo información...</p>';

    try {
        const resp = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        const datos = await resp.json();

        if (datos.error) {
            infoDiv.innerHTML = `<p class="texto-muted texto-centro">⚠ ${datos.error}</p>`;
            videoActual = null;
            return;
        }

        videoActual = datos;
        mostrarInfoVideo(datos);
    } catch {
        infoDiv.innerHTML = '<p class="texto-muted texto-centro">Error de conexión</p>';
        videoActual = null;
    }
}

function mostrarInfoVideo(info) {
    const infoDiv = document.getElementById('info-video');
    infoDiv.innerHTML = `
        <div class="info-video-card">
            <img class="info-thumb" src="${info.thumbnail}" alt="" onerror="this.style.display='none'">
            <div class="info-datos">
                <div class="info-titulo">${info.titulo}</div>
                <div class="info-canal">${info.canal}</div>
                <div class="info-duracion">⏱ ${info.duracion}</div>
            </div>
        </div>
        <div class="info-acciones">
            <button class="btn-accion btn-agregar-cola" onclick="agregarACola()">
                + Añadir a la cola
            </button>
        </div>
    `;
}

// --------------------------------------------------------------------------- //
// Cola de descarga
// --------------------------------------------------------------------------- //

async function agregarACola() {
    if (!videoActual) return;

    try {
        const resp = await fetch('/api/cola/agregar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: videoActual.url,
                titulo: videoActual.titulo,
                thumbnail: videoActual.thumbnail,
                duracion: videoActual.duracion,
                canal: videoActual.canal,
                carpeta: carpetaDestino,
            }),
        });
        const datos = await resp.json();
        if (datos.id) {
            actualizarCola();
        }
    } catch { /* ignorar */ }
}

async function eliminarDeCola(id) {
    try {
        await fetch('/api/cola/eliminar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id }),
        });
        actualizarCola();
    } catch { /* ignorar */ }
}

async function actualizarCola() {
    try {
        const resp = await fetch('/api/cola');
        const datos = await resp.json();
        renderizarCola(datos.items);
    } catch { /* ignorar */ }
}

function renderizarCola(items) {
    const lista = document.getElementById('lista-cola');
    const badge = document.getElementById('badge-cola');
    const btn = document.getElementById('btn-descargar-cola');

    const enCola = items.filter(it => it.estado === 'en_cola');
    badge.textContent = enCola.length;
    btn.disabled = enCola.length === 0;

    if (items.length === 0) {
        lista.innerHTML = '<p class="texto-muted texto-centro">La cola está vacía</p>';
        return;
    }

    lista.innerHTML = items.map(it => {
        const estadoClass = it.estado === 'completado' ? 'completado' :
                           it.estado === 'error' ? 'error' :
                           it.estado === 'descargando' ? 'descargando' : '';
        const eliminarBtn = it.estado === 'en_cola'
            ? `<button class="item-cola-eliminar" onclick="eliminarDeCola('${it.id}')" title="Eliminar">✕</button>`
            : '';
        const estadoTexto = it.estado === 'en_cola' ? 'En cola' :
                           it.estado === 'descargando' ? `${it.progreso}%` :
                           it.estado === 'completado' ? '✓' :
                           it.estado === 'error' ? '✕' : '';

        return `
            <div class="item-cola ${estadoClass}">
                ${it.thumbnail ? `<img class="item-cola-thumb" src="${it.thumbnail}" alt="">` : ''}
                <div class="item-cola-info">
                    <div class="item-cola-titulo" title="${it.titulo || it.url}">${it.titulo || it.url}</div>
                    <div class="item-cola-meta">${it.duracion || ''} ${it.canal ? '· ' + it.canal : ''} · ${estadoTexto}</div>
                </div>
                ${eliminarBtn}
            </div>
        `;
    }).join('');
}

async function iniciarDescargaCola() {
    const btn = document.getElementById('btn-descargar-cola');
    btn.disabled = true;
    btn.textContent = '⏳ Descargando...';

    try {
        await fetch('/api/cola/descargar', { method: 'POST' });
    } catch { /* ignorar */ }
}

// --------------------------------------------------------------------------- //
// Progreso (SSE)
// --------------------------------------------------------------------------- //

function conectarSSE() {
    if (sse) sse.close();
    sse = new EventSource('/api/eventos');

    sse.onmessage = (event) => {
        const ev = JSON.parse(event.data);
        manejarEventoSSE(ev);
    };

    sse.onerror = () => {
        setTimeout(conectarSSE, 3000);
    };
}

function manejarEventoSSE(ev) {
    switch (ev.tipo) {
        case 'descargando':
            agregarItemProgreso(ev.id, ev.titulo || 'Descargando...', 'descargando');
            actualizarCola();
            break;

        case 'progreso':
            actualizarProgreso(ev.id, ev.progreso, ev.titulo, ev.mensaje);
            break;

        case 'completado':
            completarProgreso(ev.id, ev.titulo);
            actualizarCola();
            cargarHistorial();
            break;

        case 'error':
            errorProgreso(ev.id, ev.error);
            actualizarCola();
            break;

        case 'cola_actualizada':
            renderizarCola(ev.items);
            break;
    }
}

function agregarItemProgreso(id, titulo, estado) {
    const lista = document.getElementById('lista-progreso-activo');
    // Limpiar mensaje vacío
    if (lista.querySelector('.texto-muted')) {
        lista.innerHTML = '';
    }

    // No duplicar
    if (document.getElementById('prog-' + id)) return;

    const div = document.createElement('div');
    div.className = 'item-progreso';
    div.id = 'prog-' + id;
    div.innerHTML = `
        <div class="fila-info">
            <span class="titulo">${titulo}</span>
            <span class="estado">Descargando</span>
        </div>
        <div class="barra-contenedor">
            <div class="barra" style="width: 0%"></div>
        </div>
    `;
    lista.prepend(div);
}

function actualizarProgreso(id, progreso, titulo, mensaje) {
    const div = document.getElementById('prog-' + id);
    if (!div) {
        agregarItemProgreso(id, titulo || 'Descargando...', 'descargando');
        return;
    }
    if (titulo) div.querySelector('.titulo').textContent = titulo;
    div.querySelector('.estado').textContent = mensaje || `${progreso}%`;
    div.querySelector('.barra').style.width = progreso + '%';
}

function completarProgreso(id, titulo) {
    const div = document.getElementById('prog-' + id);
    if (div) {
        div.classList.add('completado');
        div.querySelector('.estado').textContent = '✓ Completado';
        div.querySelector('.barra').style.width = '100%';

        // Mover a completados después de un momento
        setTimeout(() => {
            div.remove();
            agregarCompletado(id, titulo);
            limpiarListaActivaVacia();
            rehabilitarBotonCola();
        }, 2000);
    }
}

function errorProgreso(id, error) {
    const div = document.getElementById('prog-' + id);
    if (div) {
        div.classList.add('error');
        div.querySelector('.estado').textContent = '✕ Error';
        div.querySelector('.barra').style.width = '100%';
        setTimeout(() => {
            rehabilitarBotonCola();
        }, 1000);
    }
}

function agregarCompletado(id, titulo) {
    const lista = document.getElementById('lista-progreso-completado');
    if (lista.querySelector('.texto-muted')) {
        lista.innerHTML = '';
    }

    const div = document.createElement('div');
    div.className = 'item-progreso completado';
    div.innerHTML = `
        <div class="fila-info">
            <span class="titulo">${titulo || 'Descarga'}</span>
            <span class="estado">✓ Completado</span>
        </div>
        <div class="barra-contenedor">
            <div class="barra" style="width: 100%"></div>
        </div>
    `;
    lista.prepend(div);
}

function limpiarListaActivaVacia() {
    const lista = document.getElementById('lista-progreso-activo');
    if (lista.children.length === 0) {
        lista.innerHTML = '<p class="texto-muted texto-centro">Sin descargas activas</p>';
    }
}

function rehabilitarBotonCola() {
    const btn = document.getElementById('btn-descargar-cola');
    btn.textContent = '⬇ Descargar Cola';
    actualizarCola();
}

// --------------------------------------------------------------------------- //
// Tabs de progreso
// --------------------------------------------------------------------------- //

function cambiarTabProgreso(tab) {
    const tabs = document.querySelectorAll('.tabs-progreso .tab');
    tabs.forEach(t => t.classList.remove('activo'));

    const activo = document.getElementById('lista-progreso-activo');
    const completado = document.getElementById('lista-progreso-completado');

    if (tab === 'activo') {
        tabs[0].classList.add('activo');
        activo.classList.remove('oculto');
        completado.classList.add('oculto');
    } else {
        tabs[1].classList.add('activo');
        activo.classList.add('oculto');
        completado.classList.remove('oculto');
    }
}

// --------------------------------------------------------------------------- //
// Explorador de carpetas
// --------------------------------------------------------------------------- //

function toggleExploradorCarpetas() {
    const overlay = document.getElementById('overlay-carpetas');
    overlay.classList.toggle('oculto');
    if (!overlay.classList.contains('oculto')) {
        cargarCarpetas(rutaExplorador);
    }
}

async function cargarCarpetas(ruta) {
    rutaExplorador = ruta || '';
    const lista = document.getElementById('lista-carpetas');
    lista.innerHTML = '<p class="texto-muted texto-centro"><span class="spinner"></span> Cargando...</p>';

    try {
        const resp = await fetch('/api/carpetas?ruta=' + encodeURIComponent(rutaExplorador));
        const datos = await resp.json();

        if (datos.error) {
            lista.innerHTML = `<p class="texto-muted texto-centro">⚠ ${datos.error}</p>`;
            return;
        }

        document.getElementById('ruta-explorador').textContent = 'descargas/' + (datos.ruta ? datos.ruta + '/' : '');
        document.getElementById('btn-subir-carpeta').disabled = !datos.puede_subir;

        if (datos.items.length === 0) {
            lista.innerHTML = '<p class="texto-muted texto-centro">Carpeta vacía</p>';
            return;
        }

        lista.innerHTML = datos.items.map(item => {
            const icono = item.es_carpeta ? '📁' : '🎵';
            const tamano = item.es_carpeta ? '' : formatearTamano(item.tamaño);
            const onclick = item.es_carpeta
                ? `onclick="cargarCarpetas('${item.ruta}')"`
                : '';
            const clase = item.es_carpeta ? 'es-carpeta' : '';

            return `
                <div class="item-carpeta ${clase}" ${onclick}>
                    <span class="icono-carpeta">${icono}</span>
                    <span class="nombre-item">${item.nombre}</span>
                    <span class="tamano-item">${tamano}</span>
                </div>
            `;
        }).join('');
    } catch {
        lista.innerHTML = '<p class="texto-muted texto-centro">Error al cargar</p>';
    }
}

function subirCarpeta() {
    if (!rutaExplorador) return;
    const partes = rutaExplorador.split('/');
    partes.pop();
    cargarCarpetas(partes.join('/'));
}

function mostrarCrearCarpeta() {
    document.getElementById('form-nueva-carpeta').classList.remove('oculto');
    document.getElementById('input-nueva-carpeta').focus();
}

function cancelarCrearCarpeta() {
    document.getElementById('form-nueva-carpeta').classList.add('oculto');
    document.getElementById('input-nueva-carpeta').value = '';
}

async function crearCarpeta() {
    const nombre = document.getElementById('input-nueva-carpeta').value.trim();
    if (!nombre) return;

    try {
        const resp = await fetch('/api/carpetas/crear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ruta_padre: rutaExplorador, nombre }),
        });
        const datos = await resp.json();
        if (datos.ok) {
            cancelarCrearCarpeta();
            cargarCarpetas(rutaExplorador);
        }
    } catch { /* ignorar */ }
}

function seleccionarCarpetaActual() {
    carpetaDestino = rutaExplorador ? 'descargas/' + rutaExplorador : '';
    document.getElementById('ruta-destino').textContent = 'descargas/' + (rutaExplorador ? rutaExplorador + '/' : '');
    toggleExploradorCarpetas();
}

// --------------------------------------------------------------------------- //
// Historial de completados
// --------------------------------------------------------------------------- //

async function cargarHistorial() {
    try {
        const resp = await fetch('/api/historial');
        const items = await resp.json();
        const lista = document.getElementById('lista-progreso-completado');

        if (items.length === 0) {
            if (!lista.querySelector('.item-progreso')) {
                lista.innerHTML = '<p class="texto-muted texto-centro">Sin descargas completadas</p>';
            }
            return;
        }

        // Solo actualizar si no hay items ya renderizados
        if (lista.querySelector('.texto-muted')) {
            lista.innerHTML = items.map(it => `
                <div class="item-progreso completado">
                    <div class="fila-info">
                        <span class="titulo">${it.titulo}</span>
                        <span class="estado">✓ Completado</span>
                    </div>
                    <div class="barra-contenedor">
                        <div class="barra" style="width: 100%"></div>
                    </div>
                </div>
            `).join('');
        }
    } catch { /* ignorar */ }
}

// --------------------------------------------------------------------------- //
// Inicialización
// --------------------------------------------------------------------------- //

document.addEventListener('DOMContentLoaded', () => {
    // Inicializar historial de navegación
    historialUrls = ['https://www.youtube.com'];
    posHistorial = 0;

    // Conectar SSE
    conectarSSE();

    // Cargar estado inicial
    actualizarCola();
    cargarHistorial();
});
