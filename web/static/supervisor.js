/*
 * ═══════════════════════════════════════════════════════════════════════════
 *  LÓGICA — Dashboard del Agente Supervisor · Tic-Tac-Toe Multiagente
 *  Sistemas Multiagente · Universidad de Jaén · Sinbad2 TIC-206
 * ═══════════════════════════════════════════════════════════════════════════
 *
 *  JavaScript vanilla que replica la lógica del componente React de
 *  referencia (ttt-supervisor-dashboard.jsx).  Realiza polling periódico
 *  al endpoint /supervisor/api/state y actualiza la interfaz sin
 *  dependencias externas.
 */

"use strict";


// ═══════════════════════════════════════════════════════════════════════════
//  ESTADO GLOBAL DE LA APLICACIÓN
// ═══════════════════════════════════════════════════════════════════════════

const estado = {
    salas: [],
    salaActivaId: null,
    tabActivo: "informes",
    filtroResultado: "all",
    informeSeleccionado: null,
    tema: localStorage.getItem("sv-tema") || "dark",
    // Historial de ejecuciones
    ejecucionActiva: "live",    // "live" o ID numérico
    ejecuciones: [],             // Lista de ejecuciones disponibles
    esHistorico: false,          // true cuando se revisa una ejecución pasada
    // Indica si el backend está en modo consulta (sin XMPP).
    // Se actualiza desde la respuesta de /api/state.
    modoConsulta: false,
    // Paginación del log (M-06)
    logEventosMostrados: 50,     // Eventos visibles en el panel de log
    // Server-Sent Events (M-05)
    sseConectado: false,         // true cuando el EventSource está activo
};

// Número de eventos por página en el log
const LOG_PAGINA_SIZE = 50;

// Referencia al EventSource activo (null si no hay conexión SSE)
let fuenteSSE = null;

// Intervalo de polling en milisegundos
const INTERVALO_POLLING = 5000;


// ═══════════════════════════════════════════════════════════════════════════
//  INICIALIZACIÓN
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
    // Aplicar tema guardado
    aplicarTema(estado.tema);

    // Reloj en tiempo real
    actualizarReloj();
    setInterval(actualizarReloj, 1000);

    // Registrar eventos del toggle de tema
    const toggleBtn = document.getElementById("theme-toggle");
    toggleBtn.addEventListener("click", toggleTema);

    // Registrar evento del botón de finalización del torneo (P-09)
    const btnFinalizar = document.getElementById("sv-finalizar-torneo");
    btnFinalizar.addEventListener("click", confirmarFinalizarTorneo);

    // Registrar evento para cerrar modal
    const overlay = document.getElementById("modal-overlay");
    overlay.addEventListener("click", (e) => {
        // Cerrar solo si se hace clic en el fondo oscuro (no en el modal)
        if (e.target === overlay) {
            cerrarModal();
        }
    });

    const modalCloseBtn = document.getElementById("modal-close");
    modalCloseBtn.addEventListener("click", cerrarModal);

    // Cerrar modal con tecla Escape
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            cerrarModal();
        }
    });

    // Selector de ejecuciones
    const selectEjec = document.getElementById("sv-ejecucion-select");
    selectEjec.addEventListener("change", cambiarEjecucion);

    // Primera carga: cargarEstado() primero para que establezca
    // estado.modoConsulta antes de que cargarEjecuciones() lo lea.
    cargarEstado().then(() => {
        cargarEjecuciones();
        // Iniciar SSE tras la primera carga completa
        iniciarSSE();
    });
    // Polling como fallback: solo se activa si SSE no está conectado
    setInterval(() => {
        if (!estado.sseConectado) {
            cargarEstado();
        }
    }, INTERVALO_POLLING);
    // Actualizar lista de ejecuciones cada 30 s
    setInterval(cargarEjecuciones, 30000);
});


// ═══════════════════════════════════════════════════════════════════════════
//  SERVER-SENT EVENTS (M-05)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Inicia la conexión SSE con el servidor para recibir
 * actualizaciones en tiempo real. Si la conexión se pierde,
 * el navegador reconecta automáticamente (comportamiento
 * estándar de EventSource) y el polling de fallback se activa
 * mientras tanto.
 */
function iniciarSSE() {
    // No iniciar SSE en modo histórico ni si ya hay conexión
    if (estado.esHistorico || fuenteSSE !== null) {
        return;
    }

    // Verificar soporte del navegador
    if (typeof EventSource === "undefined") {
        console.warn("SSE no soportado; usando polling");
        return;
    }

    fuenteSSE = new EventSource("/supervisor/api/stream");

    fuenteSSE.addEventListener("state", (evento) => {
        if (estado.esHistorico) {
            return;
        }

        try {
            const datos = JSON.parse(evento.data);

            // Si el evento contiene el estado completo (salas),
            // actualizar directamente
            if (datos.salas) {
                procesarDatosEstado(datos);
            } else {
                // Evento parcial: recargar el estado completo
                // para mantener coherencia
                cargarEstado();
            }
        } catch (error) {
            console.error("Error al procesar evento SSE:", error);
        }
    });

    fuenteSSE.onopen = () => {
        estado.sseConectado = true;
        console.info("SSE conectado");
    };

    fuenteSSE.onerror = () => {
        estado.sseConectado = false;
        // EventSource reconecta automáticamente; mientras
        // tanto, el polling de fallback se activa
    };
}

/**
 * Detiene la conexión SSE activa. Se usa al cambiar a modo
 * histórico.
 */
function detenerSSE() {
    if (fuenteSSE !== null) {
        fuenteSSE.close();
        fuenteSSE = null;
        estado.sseConectado = false;
    }
}

/**
 * Procesa los datos del estado recibidos (desde polling o SSE).
 * Extrae la lógica común de actualización del estado global.
 * @param {object} datos - Respuesta JSON del servidor.
 */
function procesarDatosEstado(datos) {
    const todasLasSalas = datos.salas || [];

    estado.modoConsulta = datos.modo_consulta || false;
    estado.salas = todasLasSalas;

    // Ordenar: salas con agentes activos primero, luego por nombre
    estado.salas.sort((a, b) => {
        const actA = a.ocupantes.length > 0 ? 0 : 1;
        const actB = b.ocupantes.length > 0 ? 0 : 1;
        if (actA !== actB) { return actA - actB; }
        return a.id.localeCompare(b.id);
    });

    // Si no hay sala activa, seleccionar la primera con agentes
    if (estado.salaActivaId === null && estado.salas.length > 0) {
        const conAgentes = estado.salas.find(
            (s) => s.ocupantes.length > 0
        );
        estado.salaActivaId = conAgentes
            ? conAgentes.id : estado.salas[0].id;
    }

    renderTodo();

    // P-09: En modo consulta, el botón cambia su texto para
    // indicar que cierra el dashboard (no hay torneo activo)
    const btnFinalizar = document.getElementById("sv-finalizar-torneo");
    if (btnFinalizar) {
        btnFinalizar.textContent = estado.modoConsulta
            ? "Cerrar dashboard" : "Finalizar torneo";
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  POLLING AL SERVIDOR (fallback cuando SSE no está disponible)
// ═══════════════════════════════════════════════════════════════════════════

async function cargarEstado() {
    // En modo histórico no se consulta el estado en vivo
    if (estado.esHistorico) {
        return;
    }

    try {
        const respuesta = await fetch("/supervisor/api/state");
        if (!respuesta.ok) {
            console.error("Error al obtener estado:", respuesta.status);
            return;
        }
        const datos = await respuesta.json();
        procesarDatosEstado(datos);
    } catch (error) {
        console.error("Error en polling:", error);
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  HISTORIAL DE EJECUCIONES
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Carga la lista de ejecuciones desde la API y actualiza el selector.
 */
async function cargarEjecuciones() {
    try {
        const respuesta = await fetch("/supervisor/api/ejecuciones");
        if (!respuesta.ok) { return; }
        const datos = await respuesta.json();
        estado.ejecuciones = datos.ejecuciones || [];
        renderSelectorEjecuciones();

        // En modo consulta (sin conexión XMPP), el estado en vivo
        // no tiene salas. Si hay ejecuciones disponibles y no se
        // ha seleccionado ninguna, auto-seleccionar la más reciente
        // para que el usuario vea datos desde el primer momento.
        // Solo se activa cuando el backend confirma modo consulta
        // (modo_consulta=true), nunca en modo en vivo.
        if (
            estado.modoConsulta
            && !estado.esHistorico
            && estado.ejecuciones.length > 0
        ) {
            const ultima = estado.ejecuciones[0];
            estado.ejecucionActiva = String(ultima.id);
            estado.esHistorico = true;

            const select = document.getElementById("sv-ejecucion-select");
            if (select) {
                select.value = String(ultima.id);
            }

            cargarDatosEjecucionPasada(ultima.id);
        }
    } catch (error) {
        console.error("Error al cargar ejecuciones:", error);
    }
}

/**
 * Actualiza las opciones del selector de ejecuciones.
 */
function renderSelectorEjecuciones() {
    const select = document.getElementById("sv-ejecucion-select");
    const valorActual = select.value;

    let html = '<option value="live">En vivo</option>';

    estado.ejecuciones.forEach((ejec) => {
        // La ejecución en curso tiene fin === null
        if (ejec.fin === null) {
            return;
        }

        // Formatear las fechas para el selector
        const inicio = _formatearFechaCorta(ejec.inicio);
        const fin = _formatearFechaCorta(ejec.fin);
        const etiqueta = inicio + " — " + fin
            + " (" + ejec.num_salas + " sala"
            + (ejec.num_salas !== 1 ? "s" : "") + ")";

        html += '<option value="' + ejec.id + '">'
            + etiqueta + "</option>";
    });

    select.innerHTML = html;

    // Restaurar la selección actual
    select.value = valorActual;
    // Si el valor ya no existe (ejecución eliminada), volver a "live"
    if (select.value !== valorActual) {
        select.value = "live";
    }
}

/**
 * Maneja el cambio en el selector de ejecuciones.
 */
function cambiarEjecucion() {
    const select = document.getElementById("sv-ejecucion-select");
    const valor = select.value;

    if (valor === "live") {
        estado.ejecucionActiva = "live";
        estado.esHistorico = false;
        cargarEstado();
        iniciarSSE();
    } else {
        estado.ejecucionActiva = valor;
        estado.esHistorico = true;
        detenerSSE();
        cargarDatosEjecucionPasada(valor);
    }
}

/**
 * Carga los datos de una ejecución pasada y los muestra.
 * @param {string|number} idEjecucion - ID de la ejecución a cargar.
 */
async function cargarDatosEjecucionPasada(idEjecucion) {
    try {
        const respuesta = await fetch(
            "/supervisor/api/ejecuciones/" + idEjecucion
        );
        if (!respuesta.ok) {
            console.error(
                "Error al cargar ejecución:", respuesta.status
            );
            return;
        }
        const datos = await respuesta.json();

        // En modo histórico las salas ya vienen del backend con
        // sus datos (informes, log). Se muestran todas directamente.
        estado.salas = datos.salas || [];

        // Seleccionar la primera sala si la actual ya no existe
        let salaExiste = false;
        estado.salas.forEach((s) => {
            if (s.id === estado.salaActivaId) {
                salaExiste = true;
            }
        });
        if (!salaExiste && estado.salas.length > 0) {
            estado.salaActivaId = estado.salas[0].id;
        }

        // Si estamos en la pestaña de agentes, cambiar a informes
        // (las ejecuciones pasadas no tienen datos de presencia)
        if (estado.tabActivo === "agentes") {
            estado.tabActivo = "informes";
        }

        renderTodo();
    } catch (error) {
        console.error("Error al cargar ejecución pasada:", error);
    }
}

/**
 * Formatea una fecha ISO a formato corto DD/MM HH:MM.
 * @param {string} isoStr - Fecha en formato ISO 8601.
 * @returns {string} Fecha formateada.
 */
function _formatearFechaCorta(isoStr) {
    let resultado = isoStr;
    try {
        const d = new Date(isoStr);
        const dia = String(d.getDate()).padStart(2, "0");
        const mes = String(d.getMonth() + 1).padStart(2, "0");
        const hora = String(d.getHours()).padStart(2, "0");
        const min = String(d.getMinutes()).padStart(2, "0");
        resultado = dia + "/" + mes + " " + hora + ":" + min;
    } catch (e) {
        // Si falla el parseo, devolver la cadena original
    }
    return resultado;
}


// ═══════════════════════════════════════════════════════════════════════════
//  TEMA CLARO / OSCURO
// ═══════════════════════════════════════════════════════════════════════════

function aplicarTema(tema) {
    document.documentElement.setAttribute("data-theme", tema);
    estado.tema = tema;
    localStorage.setItem("sv-tema", tema);

    // Actualizar el icono del toggle
    const knob = document.getElementById("theme-toggle-knob");
    knob.textContent = tema === "dark" ? "🌙" : "☀️";

    // Actualizar aria-label del botón
    const btn = document.getElementById("theme-toggle");
    const nuevoModo = tema === "dark" ? "diurno" : "nocturno";
    btn.setAttribute("aria-label", `Cambiar a modo ${nuevoModo}`);
    btn.setAttribute("title", `Cambiar a modo ${nuevoModo}`);
}

function toggleTema() {
    const nuevoTema = estado.tema === "dark" ? "light" : "dark";
    aplicarTema(nuevoTema);
}


// ═══════════════════════════════════════════════════════════════════════════
//  RELOJ EN TIEMPO REAL
// ═══════════════════════════════════════════════════════════════════════════

function actualizarReloj() {
    const el = document.getElementById("sv-clock");
    el.textContent = new Date().toLocaleTimeString("es-ES");
}


// ═══════════════════════════════════════════════════════════════════════════
//  NAVEGACIÓN: SALAS Y TABS
// ═══════════════════════════════════════════════════════════════════════════

function seleccionarSala(salaId) {
    estado.salaActivaId = salaId;
    estado.tabActivo = "informes";
    estado.filtroResultado = "all";
    estado.logEventosMostrados = LOG_PAGINA_SIZE;
    renderTodo();
}

function seleccionarTab(tabId) {
    estado.tabActivo = tabId;
    renderTodo();
}

function seleccionarFiltro(filtro) {
    estado.filtroResultado = filtro;
    renderInformesPanel();
}


// ═══════════════════════════════════════════════════════════════════════════
//  EXPORTACIÓN CSV (M-03)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Construye la URL del endpoint CSV según el modo (vivo/histórico).
 * @param {string} tipo - Tipo de CSV: "ranking", "log" o "incidencias".
 * @returns {string} URL completa con parámetro de sala.
 */
function construirUrlCsv(tipo) {
    const salaId = estado.salaActivaId || "";
    let url = "";

    if (estado.esHistorico) {
        const ejId = estado.ejecucionActiva;
        url = `/supervisor/api/ejecuciones/${ejId}/csv/${tipo}`
            + `?sala=${encodeURIComponent(salaId)}`;
    } else {
        url = `/supervisor/api/csv/${tipo}`
            + `?sala=${encodeURIComponent(salaId)}`;
    }

    return url;
}

/**
 * Inicia la descarga de un CSV abriendo la URL en una pestaña nueva.
 * @param {string} tipo - Tipo de CSV: "ranking", "log" o "incidencias".
 */
function descargarCsv(tipo) {
    const url = construirUrlCsv(tipo);
    window.open(url, "_blank");
}


// ═══════════════════════════════════════════════════════════════════════════
//  FINALIZACIÓN DEL TORNEO (P-09)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Muestra un diálogo de confirmación antes de finalizar el torneo.
 * Previene finalizaciones accidentales con un clic involuntario.
 */
function confirmarFinalizarTorneo() {
    const mensaje = estado.modoConsulta
        ? "¿Cerrar el dashboard?\n\n"
          + "Se cerrará la conexión con la base de datos y "
          + "el servidor web se detendrá."
        : "¿Finalizar el torneo?\n\n"
          + "Esta acción detendrá la monitorización de todas las "
          + "salas y cerrará el supervisor. Los datos quedarán "
          + "guardados en el histórico de ejecuciones.";
    const confirmado = window.confirm(mensaje);
    if (confirmado) {
        finalizarTorneo();
    }
}

/**
 * Envía la petición POST al backend para finalizar el torneo.
 * Desactiva el botón durante la operación para evitar doble clic.
 */
async function finalizarTorneo() {
    const btn = document.getElementById("sv-finalizar-torneo");
    btn.disabled = true;
    btn.textContent = "Finalizando...";

    try {
        const respuesta = await fetch(
            "/supervisor/api/finalizar-torneo",
            { method: "POST" }
        );

        if (respuesta.ok) {
            mostrarPantallaFinalizada();
        } else {
            btn.disabled = false;
            btn.textContent = estado.modoConsulta
                ? "Cerrar dashboard" : "Finalizar torneo";
            console.error(
                "Error al finalizar:", respuesta.status
            );
        }
    } catch (error) {
        btn.disabled = false;
        btn.textContent = estado.modoConsulta
            ? "Cerrar dashboard" : "Finalizar torneo";
        console.error("Error de red al finalizar:", error);
    }
}

/**
 * Reemplaza el contenido del dashboard por una pantalla de
 * finalización. El servidor se ha detenido, así que la interfaz
 * ya no puede consultar la API ni recibir eventos SSE.
 */
function mostrarPantallaFinalizada() {
    // Detener SSE y polling para evitar errores de conexión
    if (fuenteSSE) {
        fuenteSSE.close();
        fuenteSSE = null;
    }

    const titulo = estado.modoConsulta
        ? "Dashboard cerrado" : "Torneo finalizado";
    const mensaje = estado.modoConsulta
        ? "El servidor de consulta se ha detenido."
        : "El supervisor ha finalizado la monitorización "
          + "y los datos se han guardado en el histórico.";

    document.body.innerHTML = '<div style="'
        + "display:flex;flex-direction:column;"
        + "align-items:center;justify-content:center;"
        + "height:100vh;font-family:var(--mono),monospace;"
        + "background:var(--body);color:var(--primary);"
        + "text-align:center;gap:16px;"
        + '">'
        + '<div style="font-size:48px;opacity:0.6">#</div>'
        + '<h1 style="margin:0;font-size:22px">'
        + titulo + "</h1>"
        + '<p style="margin:0;color:var(--secondary);'
        + 'max-width:400px">'
        + mensaje + "</p>"
        + '<p style="margin:16px 0 0;font-size:13px;'
        + 'color:var(--muted)">'
        + "Puedes cerrar esta pestaña.</p>"
        + "</div>";
}


// ═══════════════════════════════════════════════════════════════════════════
//  MODAL DE DETALLE DE INFORME
// ═══════════════════════════════════════════════════════════════════════════

function abrirModal(informe) {
    estado.informeSeleccionado = informe;
    renderModal(informe);
    document.getElementById("modal-overlay").classList.remove("hidden");
}

function cerrarModal() {
    estado.informeSeleccionado = null;
    document.getElementById("modal-overlay").classList.add("hidden");
}


// ═══════════════════════════════════════════════════════════════════════════
//  UTILIDADES
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Obtiene la sala activa del estado actual.
 * @returns {object|null} Sala activa o null si no hay ninguna.
 */
function obtenerSalaActiva() {
    let resultado = null;
    estado.salas.forEach((s) => {
        if (s.id === estado.salaActivaId) {
            resultado = s;
        }
    });
    return resultado;
}

/**
 * Extrae el nombre corto de un JID de jugador.
 * @param {string} jid - JID completo (ej: jugador_abc001@servidor.es)
 * @returns {string} Nombre corto (ej: abc001)
 */
function extraerAlumno(jid) {
    return jid.split("@")[0].replace("jugador_", "");
}

/**
 * Cuenta ocupantes de una sala por rol.
 * @param {Array} ocupantes - Lista de ocupantes de la sala.
 * @param {string} rol - Rol a contar (tablero, jugador, supervisor).
 * @returns {number} Número de ocupantes con ese rol.
 */
function contarPorRol(ocupantes, rol) {
    let cuenta = 0;
    ocupantes.forEach((o) => {
        if (o.rol === rol) {
            cuenta += 1;
        }
    });
    return cuenta;
}

/**
 * Crea un elemento HTML con badge (etiqueta con color).
 * @param {string} texto - Texto del badge.
 * @param {string} color - Color CSS del badge.
 * @returns {string} HTML del badge.
 */
function crearBadge(texto, color) {
    return `<span class="sv-badge" style="background:${color}1a;`
        + `color:${color}">${texto}</span>`;
}

/**
 * Devuelve la configuración visual para cada tipo de evento del log.
 * @param {string} tipo - Tipo de evento (informe, abortada, presencia, salida).
 * @returns {object} Objeto con color, icono y etiqueta.
 */
function obtenerConfigLog(tipo) {
    const configs = {
        informe:     { color: "var(--waiting)",  icon: "★", label: "Informe" },
        abortada:    { color: "var(--aborted)",  icon: "⚠", label: "Abortada" },
        presencia:   { color: "var(--green)",    icon: "↔", label: "Estado" },
        entrada:     { color: "var(--green)",    icon: "⊕", label: "Entrada" },
        salida:      { color: "var(--error)",    icon: "⊖", label: "Salida" },
        solicitud:   { color: "var(--x-color)",  icon: "▸", label: "Solicitud" },
        timeout:     { color: "var(--aborted)",  icon: "⏱", label: "Timeout" },
        error:       { color: "var(--error)",    icon: "✖", label: "Error" },
        advertencia:    { color: "var(--waiting)",  icon: "⚑", label: "Advertencia" },
        inconsistencia: { color: "var(--aborted)", icon: "⚐", label: "Inconsistencia" },
    };
    return configs[tipo] || configs.presencia;
}


// ═══════════════════════════════════════════════════════════════════════════
//  CÁLCULO DE RANKING — idéntico al del JSX
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Computa la clasificación a partir de los informes de partida.
 *
 * El ranking se calcula dinámicamente porque el supervisor no recibe
 * un ranking precalculado: solo acumula los resultados de cada
 * INFORM game-over.
 *
 * Ordenamiento: win_rate descendente → victorias → menos abortadas
 *               → menos derrotas.
 *
 * @param {Array} informes - Lista de informes de partida.
 * @returns {Array} Lista ordenada de estadísticas por alumno.
 */
function computarRanking(informes) {
    const stats = {};

    informes.forEach((inf) => {
        const jidX = inf.jugadores.X;
        const jidO = inf.jugadores.O;
        const alumnoX = extraerAlumno(jidX);
        const alumnoO = extraerAlumno(jidO);

        // Inicializar si es la primera vez que aparece el alumno
        [alumnoX, alumnoO].forEach((a) => {
            if (!stats[a]) {
                stats[a] = {
                    alumno: a,
                    partidas: 0,
                    victorias: 0,
                    derrotas: 0,
                    empates: 0,
                    abortadas: 0,
                };
            }
        });

        if (inf.resultado === "abortada") {
            // Partida abortada: categoría separada, no afecta a V/D/E
            stats[alumnoX].partidas += 1;
            stats[alumnoX].abortadas += 1;
            stats[alumnoO].partidas += 1;
            stats[alumnoO].abortadas += 1;
        } else if (inf.resultado === "empate") {
            stats[alumnoX].partidas += 1;
            stats[alumnoX].empates += 1;
            stats[alumnoO].partidas += 1;
            stats[alumnoO].empates += 1;
        } else {
            // Victoria: determinar quién ganó según la ficha ganadora
            const ganador = inf.ficha_ganadora === "X" ? alumnoX : alumnoO;
            const perdedor = inf.ficha_ganadora === "X" ? alumnoO : alumnoX;
            stats[ganador].partidas += 1;
            stats[ganador].victorias += 1;
            stats[perdedor].partidas += 1;
            stats[perdedor].derrotas += 1;
        }
    });

    // Ordenar: más win_rate → más victorias → menos abortadas → menos derrotas
    const resultado = Object.values(stats).sort((a, b) => {
        const rateA = a.partidas > 0 ? a.victorias / a.partidas : 0;
        const rateB = b.partidas > 0 ? b.victorias / b.partidas : 0;
        if (rateB !== rateA) {
            return rateB - rateA;
        }
        if (b.victorias !== a.victorias) {
            return b.victorias - a.victorias;
        }
        if (a.abortadas !== b.abortadas) {
            return a.abortadas - b.abortadas;
        }
        return a.derrotas - b.derrotas;
    });

    return resultado;
}


// ═══════════════════════════════════════════════════════════════════════════
//  TABLERO SVG — Estado final con línea ganadora
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Genera el SVG de un tablero Tic-Tac-Toe con fichas y línea ganadora.
 *
 * @param {Array}  board         - Array de 9 celdas ("X", "O" o "").
 * @param {string} resultado     - "victoria", "empate" o "abortada".
 * @param {string} fichaGanadora - "X", "O" o null.
 * @param {number} size          - Tamaño en píxeles del SVG.
 * @returns {string} Cadena SVG completa.
 */
function renderBoardSVG(board, resultado, fichaGanadora, size) {
    const cell = size / 3;
    const pad = cell * 0.22;

    // Colores extraídos de las variables CSS según el tema activo
    const estilos = getComputedStyle(document.documentElement);
    const borderColor = estilos.getPropertyValue("--border").trim();
    const xColor = estilos.getPropertyValue("--x-color").trim();
    const oColor = estilos.getPropertyValue("--o-color").trim();

    // Texto accesible para lectores de pantalla
    let ariaLabel = "Tablero";
    if (resultado === "abortada") {
        ariaLabel = "Tablero parcial: partida abortada";
    } else if (resultado === "empate") {
        ariaLabel = "Tablero final: empate";
    } else if (resultado === "victoria") {
        ariaLabel = `Tablero final: victoria de ${fichaGanadora}`;
    }

    let svg = `<svg width="${size}" height="${size}" `
        + `viewBox="0 0 ${size} ${size}" `
        + `style="display:block" role="img" aria-label="${ariaLabel}">`;

    // Cuadrícula (dos líneas verticales + dos horizontales)
    for (let i = 1; i <= 2; i++) {
        svg += `<line x1="${cell * i}" y1="4" x2="${cell * i}" `
            + `y2="${size - 4}" stroke="${borderColor}" `
            + `stroke-width="1.5" stroke-linecap="round"/>`;
        svg += `<line x1="4" y1="${cell * i}" x2="${size - 4}" `
            + `y2="${cell * i}" stroke="${borderColor}" `
            + `stroke-width="1.5" stroke-linecap="round"/>`;
    }

    // Fichas (X y O)
    board.forEach((val, idx) => {
        const col = idx % 3;
        const row = Math.floor(idx / 3);
        const cx = col * cell + cell / 2;
        const cy = row * cell + cell / 2;

        if (val === "X") {
            svg += `<line x1="${cx - pad}" y1="${cy - pad}" `
                + `x2="${cx + pad}" y2="${cy + pad}" `
                + `stroke="${xColor}" stroke-width="2.5" `
                + `stroke-linecap="round"/>`;
            svg += `<line x1="${cx + pad}" y1="${cy - pad}" `
                + `x2="${cx - pad}" y2="${cy + pad}" `
                + `stroke="${xColor}" stroke-width="2.5" `
                + `stroke-linecap="round"/>`;
        } else if (val === "O") {
            svg += `<circle cx="${cx}" cy="${cy}" r="${pad}" `
                + `fill="none" stroke="${oColor}" stroke-width="2.5"/>`;
        }
    });

    // Línea ganadora: solo si hay victoria con ficha ganadora
    if (fichaGanadora && resultado === "victoria") {
        const lineas = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6],
        ];
        const mid = (i) => i * cell + cell / 2;

        // Buscar la línea ganadora recorriendo las 8 combinaciones
        let lineaEncontrada = false;
        lineas.forEach((combo) => {
            const a = combo[0];
            const b = combo[1];
            const c = combo[2];
            if (!lineaEncontrada
                && board[a]
                && board[a] === board[b]
                && board[b] === board[c]) {
                const color = fichaGanadora === "X" ? xColor : oColor;
                svg += `<line x1="${mid(a % 3)}" y1="${mid(Math.floor(a / 3))}" `
                    + `x2="${mid(c % 3)}" y2="${mid(Math.floor(c / 3))}" `
                    + `stroke="${color}" stroke-width="3" `
                    + `stroke-linecap="round" opacity="0.6"/>`;
                lineaEncontrada = true;
            }
        });
    }

    svg += "</svg>";
    return svg;
}


// ═══════════════════════════════════════════════════════════════════════════
//  RENDERIZADO PRINCIPAL
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Actualiza todos los componentes de la interfaz.
 * Se invoca tras cada polling o cambio de navegación.
 */
function renderTodo() {
    renderGlobalStats();
    renderSalas();
    renderContenidoPrincipal();
}

/**
 * Actualiza el resumen global en el header.
 */
function renderGlobalStats() {
    let totalAgentes = 0;
    let totalInformes = 0;
    estado.salas.forEach((s) => {
        totalAgentes += s.ocupantes.length;
        totalInformes += s.informes.length;
    });

    const el = document.getElementById("sv-global-stats");
    el.textContent = `${estado.salas.length} sala`
        + `${estado.salas.length !== 1 ? "s" : ""}`
        + ` · ${totalAgentes} agentes`
        + ` · ${totalInformes} informes`;
}


// ═══════════════════════════════════════════════════════════════════════════
//  RENDERIZADO: SIDEBAR DE SALAS
// ═══════════════════════════════════════════════════════════════════════════

function renderSalas() {
    const contenedor = document.getElementById("sv-salas-list");
    let html = "";

    estado.salas.forEach((s) => {
        const activa = s.id === estado.salaActivaId;
        const claseActiva = activa ? " active" : "";
        const numInformes = s.informes.length;
        const numAgentes = s.ocupantes.length;
        // Atenuar visualmente las salas vacías
        const claseVacia = numAgentes === 0 ? " sv-sala-vacia" : "";
        // Color del indicador: verde si tiene agentes, gris si vacía
        const colorDot = numAgentes > 0
            ? "var(--green)" : "var(--text-secondary)";

        html += `<button class="sv-sala-btn${claseActiva}${claseVacia}" `
            + `onclick="seleccionarSala('${s.id}')">
            <div class="sv-sala-nombre">${s.nombre}</div>
            <div class="sv-sala-meta">
                <span class="sv-sala-agentes">
                    <span class="sv-sala-agentes-dot" `
            + `style="color:${colorDot}">●</span> `
            + `${numAgentes} agentes
                </span>
                <span class="sv-sala-informes">`
            + `★ ${numInformes} informes</span>
            </div>
            <div class="sv-sala-jid">${s.jid}</div>
        </button>`;
    });

    contenedor.innerHTML = html;
}


// ═══════════════════════════════════════════════════════════════════════════
//  RENDERIZADO: CONTENIDO PRINCIPAL (stats, tabs, panel activo)
// ═══════════════════════════════════════════════════════════════════════════

function renderContenidoPrincipal() {
    const sala = obtenerSalaActiva();
    if (!sala) {
        // Limpiar los paneles sin destruir la estructura del DOM.
        // Si se sobrescribe el innerHTML de sv-main-content, los
        // elementos hijos (sv-sala-nombre, sv-stats, sv-tabs, etc.)
        // desaparecen y ya no pueden actualizarse cuando se carguen
        // los datos de una ejecución pasada en modo consulta.
        document.getElementById("sv-sala-nombre").textContent = "—";
        document.getElementById("sv-sala-desc").innerHTML = "";
        document.getElementById("sv-stats").innerHTML = "";
        document.getElementById("sv-tabs").innerHTML = "";
        document.getElementById("sv-panel-content").innerHTML =
            '<div class="sv-empty-msg">'
            + "No hay salas disponibles.</div>";
        // Eliminar banner histórico residual si lo hubiera
        const bannerVacio = document.querySelector(
            ".sv-historico-banner"
        );
        if (bannerVacio) {
            bannerVacio.remove();
        }
        return;
    }

    // Aviso de modo histórico si se está revisando una ejecución pasada
    const bannerExistente = document.querySelector(".sv-historico-banner");
    if (bannerExistente) {
        bannerExistente.remove();
    }
    if (estado.esHistorico) {
        let etiqueta = "";
        estado.ejecuciones.forEach((e) => {
            if (String(e.id) === String(estado.ejecucionActiva)) {
                etiqueta = _formatearFechaCorta(e.inicio)
                    + " — " + _formatearFechaCorta(e.fin);
            }
        });
        const salaHeader = document.querySelector(".sv-sala-header");
        if (salaHeader) {
            salaHeader.insertAdjacentHTML("beforebegin",
                '<div class="sv-historico-banner">'
                + "Modo historico — Ejecucion del "
                + etiqueta + " (solo lectura)</div>");
        }
    }

    renderCabeceraSala(sala);
    renderStats(sala);
    renderTabs(sala);
    renderPanelActivo(sala);
}

function renderCabeceraSala(sala) {
    document.getElementById("sv-sala-nombre").textContent = sala.nombre;

    const descEl = document.getElementById("sv-sala-desc");
    const desc = sala.descripcion || "";
    descEl.innerHTML = `${desc} · <span class="sv-sala-header-jid">`
        + `${sala.jid}</span>`;
}

function renderStats(sala) {
    const informes = sala.informes;
    const ranking = computarRanking(informes);

    let victorias = 0;
    let empates = 0;
    let abortadas = 0;
    informes.forEach((inf) => {
        if (inf.resultado === "victoria") { victorias += 1; }
        else if (inf.resultado === "empate") { empates += 1; }
        else if (inf.resultado === "abortada") { abortadas += 1; }
    });

    const contenedor = document.getElementById("sv-stats");
    contenedor.innerHTML =
        renderStatBox(sala.ocupantes.length, "En sala", "◎", "var(--green)")
        + renderStatBox(informes.length, "Informes", "★", "var(--waiting)")
        + renderStatBox(victorias, "Victorias", "🏆", "var(--green)")
        + renderStatBox(empates, "Empates", "⬡", "var(--draw)")
        + renderStatBox(abortadas, "Abortadas", "⚠", "var(--aborted)")
        + renderStatBox(ranking.length, "Jugadores", "⊕", "var(--x-color)");
}

function renderStatBox(value, label, icon, color) {
    return `<div class="sv-stat-box">
        <div class="sv-stat-icon" style="background:${color}18">`
        + `${icon}</div>
        <div>
            <div class="sv-stat-value">${value}</div>
            <div class="sv-stat-label">${label}</div>
        </div>
    </div>`;
}

// ── Tipos de evento que se consideran incidencias ──────────
// Estos tipos se filtran del log para poblar la pestaña de
// Incidencias. Incluyen errores, advertencias y anomalías
// semánticas detectadas por la validación cruzada.
const TIPOS_INCIDENCIA = [
    "error", "advertencia", "timeout", "abortada", "inconsistencia",
];

/**
 * Cuenta las incidencias (eventos de severidad alta) en el log.
 * @param {Array} log - Log de eventos de la sala.
 * @returns {number} Número de eventos que son incidencias.
 */
function contarIncidencias(log) {
    let cuenta = 0;
    log.forEach((entry) => {
        if (TIPOS_INCIDENCIA.indexOf(entry.tipo) !== -1) {
            cuenta += 1;
        }
    });
    return cuenta;
}

function renderTabs(sala) {
    const ranking = computarRanking(sala.informes);
    const numIncidencias = contarIncidencias(sala.log);
    const tabs = [
        {
            id: "informes", label: "Informes",
            icon: "★", count: sala.informes.length,
        },
        {
            id: "agentes", label: "Agentes",
            icon: "◎", count: sala.ocupantes.length,
        },
        {
            id: "ranking", label: "Clasificación",
            icon: "🏆", count: ranking.length,
        },
        {
            id: "incidencias", label: "Incidencias",
            icon: "⚑", count: numIncidencias,
        },
        {
            id: "log", label: "Log",
            icon: "▤", count: sala.log.length,
        },
    ];

    // En modo histórico no hay datos de presencia: excluir la
    // pestaña de agentes para evitar mostrar una lista vacía
    const tabsFiltrados = [];
    tabs.forEach((t) => {
        let incluir = true;
        if (estado.esHistorico && t.id === "agentes") {
            incluir = false;
        }
        if (incluir) {
            tabsFiltrados.push(t);
        }
    });

    const contenedor = document.getElementById("sv-tabs");
    let html = "";

    tabsFiltrados.forEach((t) => {
        const activo = estado.tabActivo === t.id ? " active" : "";
        html += `<button class="sv-tab-btn${activo}" role="tab" `
            + `aria-selected="${estado.tabActivo === t.id}" `
            + `onclick="seleccionarTab('${t.id}')">
            <span class="sv-tab-icon">${t.icon}</span>
            ${t.label}
            <span class="sv-tab-count">${t.count}</span>
        </button>`;
    });

    contenedor.innerHTML = html;
}

function renderPanelActivo(sala) {
    const contenedor = document.getElementById("sv-panel-content");

    if (estado.tabActivo === "informes") {
        renderInformesPanel(sala);
    } else if (estado.tabActivo === "agentes") {
        renderAgentesPanel(sala, contenedor);
    } else if (estado.tabActivo === "ranking") {
        renderRankingPanel(sala, contenedor);
    } else if (estado.tabActivo === "incidencias") {
        renderIncidenciasPanel(sala, contenedor);
    } else if (estado.tabActivo === "log") {
        renderLogPanel(sala, contenedor);
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  PANEL: INFORMES DE PARTIDA
// ═══════════════════════════════════════════════════════════════════════════

function renderInformesPanel(salaArg) {
    const sala = salaArg || obtenerSalaActiva();
    if (!sala) { return; }

    const contenedor = document.getElementById("sv-panel-content");
    const filtro = estado.filtroResultado;

    // Filtrar informes según el filtro activo
    let informesFiltrados = sala.informes;
    if (filtro !== "all") {
        informesFiltrados = [];
        sala.informes.forEach((inf) => {
            if (inf.resultado === filtro) {
                informesFiltrados.push(inf);
            }
        });
    }

    // Filtros
    const filtros = [
        { id: "all",       label: "Todos",     color: "var(--secondary)" },
        { id: "victoria",  label: "Victorias", color: "var(--green)" },
        { id: "empate",    label: "Empates",   color: "var(--draw)" },
        { id: "abortada",  label: "Abortadas", color: "var(--aborted)" },
    ];

    let html = '<div class="sv-filters">'
        + '<div class="sv-filter-group" role="group" '
        + 'aria-label="Filtrar por resultado">';

    filtros.forEach((f) => {
        const activo = filtro === f.id ? " active" : "";
        // Estilo inline para color dinámico del filtro activo
        let estilo = "";
        if (filtro === f.id) {
            estilo = `background:${f.color}22;color:${f.color}`;
        }
        html += `<button class="sv-filter-btn${activo}" `
            + `aria-pressed="${filtro === f.id}" `
            + `style="${estilo}" `
            + `onclick="seleccionarFiltro('${f.id}')">`
            + `${f.label}</button>`;
    });

    html += '</div><span class="sv-filter-count">'
        + `${informesFiltrados.length} informe(s) recibido(s)</span></div>`;

    // Grid de tarjetas
    html += '<div class="sv-informes-grid">';

    informesFiltrados.forEach((inf, idx) => {
        html += renderInformeCard(inf, idx);
    });

    html += "</div>";

    if (informesFiltrados.length === 0) {
        html += '<div class="sv-empty-msg">'
            + "No hay informes con el filtro seleccionado "
            + "en esta sala.</div>";
    }

    contenedor.innerHTML = html;
}

function renderInformeCard(informe, indice) {
    const esVictoria = informe.resultado === "victoria";
    const esAbortada = informe.resultado === "abortada";
    const alumnoX = extraerAlumno(informe.jugadores.X);
    const alumnoO = extraerAlumno(informe.jugadores.O);
    const ganador = esVictoria
        ? (informe.ficha_ganadora === "X" ? alumnoX : alumnoO)
        : null;

    // Color y texto del badge según resultado
    let badgeColor = "var(--draw)";
    let badgeText = "⬡ Empate";
    if (esAbortada) {
        badgeColor = "var(--aborted)";
        badgeText = "⚠ Abortada";
    } else if (esVictoria) {
        badgeColor = "var(--green)";
        badgeText = `★ Victoria ${informe.ficha_ganadora}`;
    }

    const claseAbortada = esAbortada ? " abortada" : "";

    // Tablero SVG miniatura (96px)
    const svgTablero = renderBoardSVG(
        informe.tablero_final, informe.resultado,
        informe.ficha_ganadora, 96
    );

    // Jugadores con indicación de ganador
    let playersHtml = '<div class="sv-informe-players">';
    ["X", "O"].forEach((sym) => {
        const alumno = sym === "X" ? alumnoX : alumnoO;
        const esGanador = esVictoria && informe.ficha_ganadora === sym;
        const claseGanador = esGanador ? " winner" : "";
        const colorSym = sym === "X" ? "var(--x-color)" : "var(--o-color)";

        // Solo destacar visualmente al ganador en victorias.
        // En empates y abortadas ningún jugador se resalta.
        let bgEstilo = "";
        if (esGanador) {
            bgEstilo = `background:${colorSym}12;border-color:${colorSym}30`;
        }

        playersHtml += `<div class="sv-informe-player${claseGanador}" `
            + `style="${bgEstilo}">
            <span class="sv-informe-player-sym" `
            + `style="color:${colorSym}">${sym}</span>
            <span class="sv-informe-player-name" `
            + `title="${alumno}">${alumno}</span>
        </div>`;
    });
    playersHtml += "</div>";

    // Pie con turnos, reason y tablero emisor
    let reasonHtml = "";
    if (esAbortada && informe.reason) {
        reasonHtml = `<span class="sv-informe-reason">`
            + `${informe.reason}</span>`;
    }

    const tableroId = informe.tablero.replace("tablero_", "");

    // Se usa un atributo data para poder pasar el informe al clic
    return `<div class="sv-informe-card${claseAbortada}" `
        + `onclick="abrirInformePorIndice(${indice})">
        <div class="sv-informe-card-header">
            ${crearBadge(badgeText, badgeColor)}
            <span class="sv-informe-card-ts">${informe.ts}</span>
        </div>
        <div class="sv-informe-board-wrap">${svgTablero}</div>
        ${playersHtml}
        <div class="sv-informe-card-footer">
            <span class="sv-informe-turnos">${informe.turnos} turnos</span>
            ${reasonHtml}
            <span class="sv-informe-tablero-id">${tableroId}</span>
        </div>
    </div>`;
}

/**
 * Abre el modal de detalle para un informe identificado por su índice
 * en la lista filtrada actual.
 */
function abrirInformePorIndice(indice) {
    const sala = obtenerSalaActiva();
    if (!sala) { return; }

    const filtro = estado.filtroResultado;
    let informesFiltrados = sala.informes;
    if (filtro !== "all") {
        informesFiltrados = [];
        sala.informes.forEach((inf) => {
            if (inf.resultado === filtro) {
                informesFiltrados.push(inf);
            }
        });
    }

    if (indice >= 0 && indice < informesFiltrados.length) {
        abrirModal(informesFiltrados[indice]);
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  PANEL: AGENTES (presencia MUC)
// ═══════════════════════════════════════════════════════════════════════════

function renderAgentesPanel(sala, contenedor) {
    const numTableros = contarPorRol(sala.ocupantes, "tablero");
    const numJugadores = contarPorRol(sala.ocupantes, "jugador");
    const numSupervisor = contarPorRol(sala.ocupantes, "supervisor");

    let html = `<div class="sv-panel">
        <div class="sv-panel-header">
            <div>
                <h3>Ocupantes de la sala MUC</h3>
                <span class="sv-panel-header-sub">`
        + `${sala.jid} · Presencia XEP-0045</span>
            </div>
            <div class="sv-panel-header-stats">
                <span class="sv-panel-header-stat" `
        + `style="color:var(--o-color)">`
        + `⊞ ${numTableros} tableros</span>
                <span class="sv-panel-header-stat" `
        + `style="color:var(--x-color)">`
        + `⊕ ${numJugadores} jugadores</span>
                <span class="sv-panel-header-stat" `
        + `style="color:var(--green)">`
        + `◉ ${numSupervisor} supervisor</span>
            </div>
        </div>`;

    // Agrupar por rol
    const roles = ["tablero", "jugador", "supervisor"];
    const etiquetasRol = {
        tablero: "Agentes tablero",
        jugador: "Agentes jugador",
        supervisor: "Supervisor (profesor)",
    };
    const coloresRol = {
        tablero: "var(--o-color)",
        jugador: "var(--x-color)",
        supervisor: "var(--green)",
    };

    roles.forEach((rol) => {
        const agentes = [];
        sala.ocupantes.forEach((o) => {
            if (o.rol === rol) {
                agentes.push(o);
            }
        });

        if (agentes.length > 0) {
            html += `<div class="sv-grupo">
                <div class="sv-grupo-label">${etiquetasRol[rol]}</div>`;

            agentes.forEach((o) => {
                const dominio = o.jid.split("@")[1] || "";
                const rolBadge = crearBadge(o.rol, coloresRol[rol]);
                html += `<div class="sv-ocupante-row">
                    <div class="sv-ocupante-dot" aria-hidden="true"></div>
                    <span class="sv-ocupante-nick" title="${o.nick}">`
                    + `${o.nick}</span>
                    ${rolBadge}
                    <span class="sv-ocupante-domain">${dominio}</span>
                </div>`;
            });

            html += "</div>";
        }
    });

    html += `<div class="sv-panel-note">
        La presencia se obtiene vía XEP-0045 al unirse a la sala MUC.
        El supervisor ve qué agentes están conectados pero no conoce
        el estado interno de las partidas en curso. Las partidas abortadas
        (ambos jugadores sin respuesta) también generan informes válidos.
    </div></div>`;

    contenedor.innerHTML = html;
}


// ═══════════════════════════════════════════════════════════════════════════
//  PANEL: CLASIFICACIÓN
// ═══════════════════════════════════════════════════════════════════════════

function renderRankingPanel(sala, contenedor) {
    const ranking = computarRanking(sala.informes);
    const medallas = ["🥇", "🥈", "🥉"];

    let html = `<div class="sv-panel">
        <div class="sv-panel-header">
            <div>
                <h3>Clasificación — ${sala.nombre}</h3>
                <span class="sv-panel-header-sub">`
        + `Computada a partir de ${sala.informes.length} `
        + `informes recibidos</span>
            </div>`
        + `<button class="sv-csv-btn" `
        + `onclick="descargarCsv('ranking')" `
        + `title="Descargar clasificación en CSV">`
        + `⬇ CSV</button>`
        + `</div>

        <div class="sv-ranking-header">
            <span class="sv-ranking-header-pos">#</span>
            <span class="sv-ranking-header-name">Alumno</span>
            <div class="sv-ranking-header-stats">
                <span>V</span><span>D</span><span>E</span><span>A</span>
            </div>
            <span class="sv-ranking-header-pct">% Vict.</span>
        </div>`;

    ranking.forEach((alumno, i) => {
        const winRate = alumno.partidas > 0
            ? Math.round((alumno.victorias / alumno.partidas) * 100)
            : 0;

        // Posición con medalla o número
        const esMedalla = i < 3;
        const clasePosicion = esMedalla ? "medal" : "normal";
        const textoPosicion = esMedalla ? medallas[i] : (i + 1);

        // Color de la barra de porcentaje según rendimiento
        let colorBarra = "var(--error)";
        if (winRate >= 60) {
            colorBarra = "var(--green)";
        } else if (winRate >= 40) {
            colorBarra = "var(--waiting)";
        }

        html += `<div class="sv-ranking-row">
            <div class="sv-ranking-pos ${clasePosicion}">`
            + `${textoPosicion}</div>
            <div class="sv-ranking-name">
                <div class="sv-ranking-alumno" `
            + `title="${alumno.alumno}">${alumno.alumno}</div>
                <div class="sv-ranking-partidas">`
            + `${alumno.partidas} partidas</div>
            </div>
            <div class="sv-ranking-stats">
                <div class="sv-ranking-stat">
                    <div class="sv-ranking-stat-val" `
            + `style="color:var(--green)">${alumno.victorias}</div>
                    <div class="sv-ranking-stat-lbl">V</div>
                </div>
                <div class="sv-ranking-stat">
                    <div class="sv-ranking-stat-val" `
            + `style="color:var(--error)">${alumno.derrotas}</div>
                    <div class="sv-ranking-stat-lbl">D</div>
                </div>
                <div class="sv-ranking-stat">
                    <div class="sv-ranking-stat-val" `
            + `style="color:var(--draw)">${alumno.empates}</div>
                    <div class="sv-ranking-stat-lbl">E</div>
                </div>
                <div class="sv-ranking-stat">
                    <div class="sv-ranking-stat-val" `
            + `style="color:var(--aborted)">${alumno.abortadas}</div>
                    <div class="sv-ranking-stat-lbl">A</div>
                </div>
            </div>
            <div class="sv-ranking-bar-wrap">
                <div class="sv-ranking-pct">${winRate}%</div>
                <div class="sv-ranking-bar">
                    <div class="sv-ranking-bar-fill" `
            + `style="width:${winRate}%;background:${colorBarra}"></div>
                </div>
            </div>
        </div>`;
    });

    if (ranking.length === 0) {
        html += '<div class="sv-empty-msg">'
            + "Aún no se han recibido informes de partida "
            + "en esta sala.</div>";
    }

    html += "</div>";
    contenedor.innerHTML = html;
}


// ═══════════════════════════════════════════════════════════════════════════
//  PANEL: INCIDENCIAS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Renderiza la pestaña de incidencias: errores, advertencias y
 * anomalías semánticas agrupadas por tipo.
 *
 * Esta pestaña presenta únicamente los eventos que requieren
 * atención del profesor, separados del log cronológico completo.
 *
 * @param {object} sala - Datos de la sala activa.
 * @param {HTMLElement} contenedor - Elemento DOM donde renderizar.
 */
function renderIncidenciasPanel(sala, contenedor) {
    // Filtrar solo eventos que son incidencias
    const incidencias = [];
    sala.log.forEach((entry) => {
        if (TIPOS_INCIDENCIA.indexOf(entry.tipo) !== -1) {
            incidencias.push(entry);
        }
    });

    // Agrupar por tipo para mostrar contadores
    const porTipo = {};
    incidencias.forEach((entry) => {
        if (!porTipo[entry.tipo]) {
            porTipo[entry.tipo] = [];
        }
        porTipo[entry.tipo].push(entry);
    });

    let html = `<div class="sv-panel">
        <div class="sv-panel-header">
            <div>
                <h3>Incidencias — ${sala.nombre}</h3>
                <span class="sv-panel-header-sub">`
        + "Errores, advertencias y anomalías semánticas detectadas"
        + `</span></div>`
        + `<button class="sv-csv-btn" `
        + `onclick="descargarCsv('incidencias')" `
        + `title="Descargar incidencias en CSV">`
        + `⬇ CSV</button>`
        + `</div>`;

    // Resumen de contadores por tipo
    const tiposOrden = [
        "error", "inconsistencia", "timeout",
        "abortada", "advertencia",
    ];

    html += '<div class="sv-incidencias-resumen">';
    tiposOrden.forEach((tipo) => {
        const lista = porTipo[tipo] || [];
        const cfg = obtenerConfigLog(tipo);
        const claseActiva = lista.length > 0
            ? "" : " sv-incidencia-cero";
        html += `<div class="sv-incidencia-badge${claseActiva}">
            <span class="sv-incidencia-icon" `
            + `style="color:${cfg.color}">${cfg.icon}</span>
            <span class="sv-incidencia-count">${lista.length}</span>
            <span class="sv-incidencia-label">${cfg.label}</span>
        </div>`;
    });
    html += "</div>";

    // Lista cronológica de incidencias
    html += '<div class="sv-log-scroll">';

    incidencias.forEach((entry) => {
        const cfg = obtenerConfigLog(entry.tipo);
        html += `<div class="sv-log-row sv-incidencia-row">
            <span class="sv-log-ts">${entry.ts}</span>
            <span class="sv-log-icon" style="color:${cfg.color}">`
            + `${cfg.icon}</span>
            <span class="sv-log-tipo" `
            + `style="background:${cfg.color}18;color:${cfg.color}">`
            + `${cfg.label}</span>
            <span class="sv-log-de" title="${entry.de}">`
            + `${entry.de}</span>
            <span class="sv-log-detalle">${entry.detalle}</span>
        </div>`;
    });

    html += "</div>";

    if (incidencias.length === 0) {
        html += '<div class="sv-empty-msg">'
            + "No se han detectado incidencias en esta sala.</div>";
    }

    html += "</div>";
    contenedor.innerHTML = html;
}


// ═══════════════════════════════════════════════════════════════════════════
//  PANEL: LOG
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Incrementa el número de eventos visibles en el log y vuelve
 * a renderizar el panel.
 */
function cargarMasLog() {
    estado.logEventosMostrados += LOG_PAGINA_SIZE;
    renderTodo();
}

function renderLogPanel(sala, contenedor) {
    const tiposLeyenda = [
        "entrada", "salida", "presencia", "solicitud", "informe",
    ];

    // Filtrar: el Log solo muestra eventos operativos.
    // Los tipos de incidencia se muestran exclusivamente en la
    // pestaña Incidencias (P-06: evitar duplicados entre pestañas).
    const eventosLog = sala.log.filter(
        (e) => TIPOS_INCIDENCIA.indexOf(e.tipo) === -1
    );

    // Paginación: mostrar solo los primeros N eventos
    const totalEventos = eventosLog.length;
    const limite = estado.logEventosMostrados;
    const eventosVisibles = eventosLog.slice(0, limite);
    const hayMas = totalEventos > limite;

    let html = `<div class="sv-panel">
        <div class="sv-panel-header">
            <div>
                <h3>Log del supervisor — ${sala.nombre}</h3>
                <span class="sv-panel-header-sub">`
        + `Mostrando ${eventosVisibles.length} de `
        + `${totalEventos} eventos`
        + `</span></div>`
        + `<button class="sv-csv-btn" `
        + `onclick="descargarCsv('log')" `
        + `title="Descargar log completo en CSV">`
        + `⬇ CSV</button>`
        + '</div><div class="sv-log-legend">';

    tiposLeyenda.forEach((tipo) => {
        const cfg = obtenerConfigLog(tipo);
        html += `<span class="sv-log-legend-item" style="color:${cfg.color}">
            <span class="sv-log-legend-icon">${cfg.icon}</span> ${cfg.label}
        </span>`;
    });

    html += '</div></div><div class="sv-log-scroll">';

    eventosVisibles.forEach((entry) => {
        const cfg = obtenerConfigLog(entry.tipo);
        html += `<div class="sv-log-row">
            <span class="sv-log-ts">${entry.ts}</span>
            <span class="sv-log-icon" style="color:${cfg.color}">`
            + `${cfg.icon}</span>
            <span class="sv-log-tipo" `
            + `style="background:${cfg.color}18;color:${cfg.color}">`
            + `${cfg.label}</span>
            <span class="sv-log-de" title="${entry.de}">`
            + `${entry.de}</span>
            <span class="sv-log-detalle">${entry.detalle}</span>
        </div>`;
    });

    html += "</div>";

    if (hayMas) {
        const restantes = totalEventos - limite;
        html += '<div class="sv-log-paginacion">'
            + `<button class="sv-log-btn-mas" `
            + `onclick="cargarMasLog()">`
            + `Cargar más (${restantes} restantes)`
            + "</button></div>";
    }

    if (eventosLog.length === 0) {
        html += '<div class="sv-empty-msg">'
            + "No hay actividad registrada en esta sala.</div>";
    }

    html += "</div>";
    contenedor.innerHTML = html;
}


// ═══════════════════════════════════════════════════════════════════════════
//  MODAL: DETALLE DE INFORME DE PARTIDA
// ═══════════════════════════════════════════════════════════════════════════

function renderModal(informe) {
    const esVictoria = informe.resultado === "victoria";
    const esAbortada = informe.resultado === "abortada";
    const alumnoX = extraerAlumno(informe.jugadores.X);
    const alumnoO = extraerAlumno(informe.jugadores.O);

    const ganador = esVictoria
        ? (informe.ficha_ganadora === "X" ? alumnoX : alumnoO)
        : null;

    // Color y fondo según resultado
    let resultColor = "var(--draw)";
    let resultBgVar = "var(--draw-bg)";
    let resultIcon = "🤝";
    let titulo = "Empate";

    if (esAbortada) {
        resultColor = "var(--aborted)";
        resultBgVar = "var(--aborted-bg)";
        resultIcon = "⚠";
        titulo = "Partida abortada";
    } else if (esVictoria) {
        resultColor = "var(--green)";
        resultBgVar = "var(--victory-bg)";
        resultIcon = "🏆";
        titulo = `Victoria de ${ganador}`;
    }

    const modal = document.getElementById("modal-body");

    // Texto del resultado
    let textoResultado = `Empate tras ${informe.turnos} turnos`;
    if (esAbortada) {
        textoResultado = `Partida abortada tras ${informe.turnos} turnos`;
    } else if (esVictoria) {
        textoResultado = `Ficha ${informe.ficha_ganadora} gana en `
            + `${informe.turnos} turnos`;
    }

    // Motivo si abortada
    let reasonHtml = "";
    if (esAbortada && informe.reason) {
        const motivoTexto = informe.reason === "both-timeout"
            ? "ambos jugadores no respondieron al CFP"
            : informe.reason;
        reasonHtml = `<div class="sv-modal-reason">`
            + `Motivo: ${motivoTexto}</div>`;
    }

    // Jugadores
    let playersHtml = '<div class="sv-modal-players">';
    ["X", "O"].forEach((sym) => {
        const jid = informe.jugadores[sym];
        const alumno = extraerAlumno(jid);
        const color = sym === "X" ? "var(--x-color)" : "var(--o-color)";
        const esGanador = esVictoria && informe.ficha_ganadora === sym;
        const claseGanador = esGanador ? " winner" : "";

        // Badge según resultado
        let badgeHtml = "";
        if (esGanador) {
            badgeHtml = crearBadge("★ Ganador", "var(--green)");
        } else if (esVictoria && !esGanador) {
            badgeHtml = crearBadge("Derrota", "var(--error)");
        } else if (!esVictoria && !esAbortada) {
            badgeHtml = crearBadge("Empate", "var(--draw)");
        } else if (esAbortada) {
            badgeHtml = crearBadge("⚠ Abortada", "var(--aborted)");
        }

        playersHtml += `<div class="sv-modal-player`
            + `${claseGanador} ficha-${sym}">
            <div class="sv-modal-player-header">
                <span class="sv-modal-player-sym" `
            + `style="color:${color}">${sym}</span>
                <span class="sv-modal-player-name" `
            + `title="${alumno}">${alumno}</span>
            </div>
            <div class="sv-modal-player-jid">${jid}</div>
            <div style="margin-top:6px">${badgeHtml}</div>
        </div>`;
    });
    playersHtml += "</div>";

    // Tablero SVG grande (200px)
    const svgTablero = renderBoardSVG(
        informe.tablero_final, informe.resultado,
        informe.ficha_ganadora, 200
    );

    const etiquetaTablero = esAbortada
        ? "Estado parcial del tablero"
        : "Estado final del tablero";

    // Datos técnicos
    let techReasonHtml = "";
    if (esAbortada && informe.reason) {
        techReasonHtml = `<div class="sv-modal-tech-row">
            <span class="sv-modal-tech-label">Motivo (reason):</span> `
            + `<span style="color:var(--aborted);font-weight:600">`
            + `${informe.reason}</span></div>`;
    }

    modal.innerHTML = `
        <div class="sv-modal-header">
            <div class="sv-modal-header-left">
                <div class="sv-modal-result-icon" `
        + `style="background:${resultBgVar};`
        + `border:1px solid ${resultColor}30">
                    ${resultIcon}
                </div>
                <div>
                    <div class="sv-modal-title">${titulo}</div>
                    <div class="sv-modal-subtitle">`
        + `${informe.tablero} · ${informe.ts}</div>
                </div>
            </div>
        </div>

        <div class="sv-modal-result-banner" `
        + `style="background:${resultBgVar};`
        + `border:1px solid ${resultColor}25">
            <div class="sv-modal-result-text" `
        + `style="color:${resultColor}">
                ${textoResultado}
            </div>
            ${reasonHtml}
        </div>

        ${playersHtml}

        <div>
            <div class="sv-modal-board-label">${etiquetaTablero}</div>
            <div class="sv-modal-board-wrap">${svgTablero}</div>
        </div>

        <div class="sv-modal-tech">
            <div class="sv-modal-tech-row">
                <span class="sv-modal-tech-label">Tablero emisor:</span> `
        + `<span class="sv-modal-tech-value">`
        + `${informe.tablero}</span>
            </div>
            <div class="sv-modal-tech-row">
                <span class="sv-modal-tech-label">`
        + `Hora de recepción:</span> `
        + `<span class="sv-modal-tech-value">${informe.ts}</span>
            </div>
            ${techReasonHtml}
            <div class="sv-modal-tech-row">
                <span class="sv-modal-tech-label">Turnos jugados:</span> `
        + `<span class="sv-modal-tech-value">${informe.turnos}</span>
            </div>
        </div>`;
}
