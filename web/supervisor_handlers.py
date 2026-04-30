"""
Handlers HTTP para el dashboard web del Agente Supervisor.

Proporciona los endpoints necesarios para servir la interfaz web
del supervisor y exponer su estado interno como API JSON:

- ``GET /supervisor`` — Sirve la plantilla HTML del dashboard.
- ``GET /supervisor/api/state`` — Devuelve el estado completo del
  supervisor en formato JSON (todas las salas con sus ocupantes,
  informes y log).
- ``GET /supervisor/api/csv/{tipo}`` — Exportación CSV del estado
  en vivo (clasificación, log o incidencias).
- ``GET /supervisor/api/ejecuciones/{id}/csv/{tipo}`` — Exportación
  CSV de una ejecución pasada.
- ``GET /supervisor/static/<fichero>`` — Ficheros estáticos (CSS, JS).

Los handlers acceden al agente supervisor a través de
``request.app["agente"]``, que se inyecta al registrar las rutas.
"""

import asyncio
import base64
import contextlib
import csv
import io
import json
import logging
import os
import pathlib
from datetime import datetime

from aiohttp import web

from persistencia.almacen_supervisor import AlmacenSupervisor

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _almacen_lectura(agente):
    """Obtiene un almacén para operaciones de solo lectura.

    Si el agente tiene un almacén vivo, se reutiliza y no se cierra
    al salir del bloque ``with``. Si el almacén se ha liberado ya
    (por ejemplo tras ``detener_persistencia()``) pero el agente
    conserva la ruta del fichero SQLite, se abre una conexión
    transitoria que se cierra al finalizar el bloque.

    De este modo los endpoints de consulta histórica siguen
    funcionando aunque el almacén activo se haya cerrado, sin
    cambiar la semántica del apagado ordenado del supervisor.
    """
    almacen_vivo = getattr(agente, "almacen", None)
    almacen_transitorio = None
    try:
        if almacen_vivo is not None:
            yield almacen_vivo
        else:
            ruta_db = getattr(agente, "ruta_db", None)
            if ruta_db and os.path.exists(ruta_db):
                almacen_transitorio = AlmacenSupervisor(ruta_db)
                yield almacen_transitorio
            else:
                yield None
    finally:
        if almacen_transitorio is not None:
            almacen_transitorio.cerrar()


# ═══════════════════════════════════════════════════════════════════════════
#  AUTENTICACIÓN HTTP BASIC (M-10)
# ═══════════════════════════════════════════════════════════════════════════

def crear_middleware_auth(
    usuario: str, contrasena: str,
) -> web.middleware:
    """Crea un middleware aiohttp que exige autenticación HTTP Basic.

    Las rutas de ficheros estáticos (CSS, JS) no se protegen para
    que el navegador pueda cargar los recursos antes de mostrar el
    diálogo de autenticación.

    Args:
        usuario: Nombre de usuario esperado.
        contrasena: Contraseña esperada.

    Returns:
        Middleware aiohttp que intercepta las peticiones.
    """
    credenciales_esperadas = base64.b64encode(
        f"{usuario}:{contrasena}".encode(),
    ).decode()

    @web.middleware
    async def middleware_auth(request, handler):
        """Comprueba la cabecera Authorization en cada petición."""
        # Los estáticos no requieren autenticación
        ruta = request.path
        if ruta.startswith("/supervisor/static"):
            respuesta = await handler(request)
            return respuesta

        cabecera = request.headers.get("Authorization", "")
        autenticado = False

        if cabecera.startswith("Basic "):
            token = cabecera[6:]
            if token == credenciales_esperadas:
                autenticado = True

        if not autenticado:
            respuesta = web.Response(
                text="Autenticación requerida",
                status=401,
            )
            respuesta.headers["WWW-Authenticate"] = (
                'Basic realm="Supervisor TicTacToe"'
            )
            return respuesta

        respuesta = await handler(request)
        return respuesta

    return middleware_auth

# ═══════════════════════════════════════════════════════════════════════════
#  SERVER-SENT EVENTS (M-05)
# ═══════════════════════════════════════════════════════════════════════════
# Lista de colas de suscriptores SSE. Cada conexión SSE activa
# tiene una asyncio.Queue donde el agente deposita eventos.
# Se almacena a nivel de módulo para que sea accesible tanto
# desde los handlers como desde la función de notificación.

_suscriptores_sse: list[asyncio.Queue] = []


def notificar_sse(tipo: str, datos: dict) -> None:
    """Deposita un evento en todas las colas SSE activas.

    Se invoca desde ``registrar_evento_log()`` del agente cada
    vez que se produce un cambio de estado. Los suscriptores SSE
    recibirán el evento de forma asíncrona.

    Args:
        tipo: Tipo de evento SSE (ej: ``"log"``, ``"state"``).
        datos: Diccionario con los datos del evento.
    """
    evento = {"tipo": tipo, "datos": datos}
    # Iterar sobre una copia para evitar problemas de concurrencia
    # si un suscriptor se desconecta durante la iteración
    for cola in list(_suscriptores_sse):
        try:
            cola.put_nowait(evento)
        except asyncio.QueueFull:
            pass

# Rutas a los directorios de plantillas y estáticos
_DIR_WEB = os.path.dirname(os.path.abspath(__file__))
_DIR_TEMPLATES = os.path.join(_DIR_WEB, "templates")
_DIR_STATIC = os.path.join(_DIR_WEB, "static")


async def handler_supervisor_index(request: web.Request) -> web.Response:
    """Sirve la página HTML principal del dashboard del supervisor.

    Lee el fichero ``templates/supervisor.html`` y lo devuelve como
    respuesta HTTP con tipo ``text/html``.

    Args:
        request: Petición HTTP entrante.

    Returns:
        Respuesta HTTP con el HTML del dashboard.
    """
    ruta_html = os.path.join(_DIR_TEMPLATES, "supervisor.html")

    try:
        with open(ruta_html, "r", encoding="utf-8") as fichero:
            contenido = fichero.read()
    except FileNotFoundError:
        logger.error("No se encontró la plantilla: %s", ruta_html)
        return web.Response(
            text="Error: plantilla supervisor.html no encontrada",
            status=404,
        )

    return web.Response(text=contenido, content_type="text/html")


async def handler_supervisor_state(request: web.Request) -> web.Response:
    """Devuelve el estado completo del supervisor como JSON.

    Construye la respuesta iterando sobre todas las salas MUC
    monitorizadas por el agente, incluyendo sus ocupantes, informes
    y log de eventos.

    Estructura de la respuesta::

        {
            "salas": [
                {
                    "id": "tictactoe",
                    "nombre": "Sala principal",
                    "jid": "tictactoe@conference.sinbad2.ujaen.es",
                    "descripcion": "Sala de partidas Tic-Tac-Toe",
                    "ocupantes": [...],
                    "informes": [...],
                    "log": [...]
                },
                ...
            ],
            "timestamp": "10:25:33"
        }

    Args:
        request: Petición HTTP entrante.

    Returns:
        Respuesta HTTP con JSON del estado del supervisor.
    """
    agente = request.app["agente"]

    # Obtener la lista de salas configuradas en el agente
    salas_muc = getattr(agente, "salas_muc", [])
    ocupantes_por_sala = getattr(agente, "ocupantes_por_sala", {})
    informes_por_sala = getattr(agente, "informes_por_sala", {})
    log_por_sala = getattr(agente, "log_por_sala", {})

    salas = []
    for sala_config in salas_muc:
        sala_id = sala_config["id"]
        sala_jid = sala_config["jid"]

        # Obtener datos de esta sala
        ocupantes = ocupantes_por_sala.get(sala_id, [])
        informes_raw = informes_por_sala.get(sala_id, {})
        informes = _convertir_informes(informes_raw)
        log_eventos = log_por_sala.get(sala_id, [])

        sala = {
            "id": sala_id,
            "nombre": _nombre_legible_sala(sala_id),
            "jid": sala_jid,
            "descripcion": "Sala de partidas Tic-Tac-Toe",
            "ocupantes": ocupantes,
            "informes": informes,
            "log": log_eventos,
        }

        salas.append(sala)

    # Indicar si el supervisor está en modo consulta (sin XMPP).
    # El frontend usa este campo para auto-seleccionar una ejecución
    # pasada cuando no hay sesión en vivo.
    es_modo_consulta = len(salas_muc) == 0

    respuesta = {
        "salas": salas,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "modo_consulta": es_modo_consulta,
    }

    return web.json_response(respuesta)


def _convertir_informes(
    informes_raw: dict[str, list[dict]],
) -> list[dict]:
    """Convierte los informes internos del supervisor al formato del dashboard.

    El agente almacena los informes indexados por JID del tablero, con
    una lista de informes por tablero (un tablero puede ejecutar
    múltiples partidas en la misma sala). Este método los aplana y
    transforma al formato que espera el frontend (``resultado``,
    ``ficha_ganadora``, ``turnos``, etc.).

    Args:
        informes_raw: Diccionario ``{jid_tablero: [cuerpo, ...]}``.

    Returns:
        Lista de informes en formato dashboard.
    """
    informes = []
    contador = 0

    for jid_tablero, lista_cuerpos in informes_raw.items():
        # Extraer el nick del tablero desde el JID.
        # El JID puede llegar en dos formatos:
        #   - JID real: tablero_mesa1@dominio/recurso → parte local
        #   - JID MUC:  sala@conference/nick → nick (recurso)
        # Se distingue comprobando si contiene "conference": si es
        # MUC, el nick está en el recurso; si no, en la parte local.
        if "conference" in jid_tablero:
            nick_tablero = jid_tablero.split("/")[-1] \
                if "/" in jid_tablero else jid_tablero.split("@")[0]
        else:
            nick_tablero = jid_tablero.split("@")[0] \
                if "@" in jid_tablero else jid_tablero

        for cuerpo in lista_cuerpos:
            contador += 1

            # Mapear campos de la ontología al formato del dashboard
            resultado_raw = cuerpo.get("result", "")
            resultado = _mapear_resultado(resultado_raw)
            ficha_ganadora = cuerpo.get("winner", None)

            # Construir JIDs de jugadores
            jugadores_raw = cuerpo.get("players", {})
            jugadores = {
                "X": jugadores_raw.get("X", "desconocido"),
                "O": jugadores_raw.get("O", "desconocido"),
            }

            # Tablero final: array de 9 celdas
            tablero_final = cuerpo.get("board", [""] * 9)

            # Timestamp del informe (si disponible)
            ts = cuerpo.get(
                "ts", datetime.now().strftime("%H:%M:%S"),
            )

            informe = {
                "id": f"informe_{contador:03d}",
                "tablero": nick_tablero,
                "ts": ts,
                "resultado": resultado,
                "ficha_ganadora": ficha_ganadora,
                "jugadores": jugadores,
                "turnos": cuerpo.get("turns", 0),
                "tablero_final": tablero_final,
            }

            # Incluir motivo si es abortada
            reason = cuerpo.get("reason", None)
            if reason:
                informe["reason"] = reason

            informes.append(informe)

    return informes


def _mapear_resultado(resultado_ontologia: str) -> str:
    """Mapea el campo ``result`` de la ontología al formato del dashboard.

    Args:
        resultado_ontologia: Valor del campo ``result`` (ej: "win", "draw").

    Returns:
        Resultado en español para el dashboard.
    """
    mapa = {
        "win": "victoria",
        "draw": "empate",
        "aborted": "abortada",
        # Compatibilidad con valores ya en español
        "victoria": "victoria",
        "empate": "empate",
        "abortada": "abortada",
    }
    return mapa.get(resultado_ontologia, resultado_ontologia)


def _nombre_legible_sala(id_sala: str) -> str:
    """Genera un nombre legible para una sala a partir de su identificador.

    Args:
        id_sala: Identificador de la sala (ej: "tictactoe").

    Returns:
        Nombre legible (ej: "Sala principal").
    """
    # Si el id contiene un nombre descriptivo, usarlo
    if "_" in id_sala:
        partes = id_sala.split("_")
        nombre = " ".join(p.capitalize() for p in partes)
        return f"Sala {nombre}"

    return "Sala principal"


async def handler_listar_ejecuciones(request: web.Request) -> web.Response:
    """Devuelve la lista de ejecuciones guardadas como JSON.

    Incluye la ejecución actual (con ``fin=null``) y todas las
    pasadas.  El selector del panel web utiliza esta lista.

    Args:
        request: Petición HTTP entrante.

    Returns:
        JSON con clave ``ejecuciones`` (lista ordenada por inicio
        descendente).
    """
    agente = request.app["agente"]

    ejecuciones = []
    with _almacen_lectura(agente) as almacen:
        if almacen is not None:
            ejecuciones = almacen.listar_ejecuciones()

    respuesta = {"ejecuciones": ejecuciones}
    return web.json_response(respuesta)


async def handler_datos_ejecucion(request: web.Request) -> web.Response:
    """Devuelve los datos completos de una ejecución pasada.

    La respuesta tiene el mismo formato que ``/supervisor/api/state``
    para que el panel web pueda representarla sin cambios.

    Args:
        request: Petición HTTP entrante.

    Returns:
        JSON con ``salas`` y ``timestamp``, en el mismo formato
        que la ruta de estado en vivo.
    """
    agente = request.app["agente"]

    id_texto = request.match_info.get("id", "")

    respuesta = {"salas": [], "timestamp": ""}

    with _almacen_lectura(agente) as almacen:
        if almacen is not None and id_texto.isdigit():
            id_ejec = int(id_texto)
            salas_config = almacen.obtener_salas_ejecucion(id_ejec)
            informes_por_sala = almacen.obtener_informes_ejecucion(id_ejec)
            eventos_por_sala = almacen.obtener_eventos_ejecucion(id_ejec)

            salas = []
            for sala_cfg in salas_config:
                sala_id = sala_cfg["id"]
                sala_jid = sala_cfg.get("jid", "")

                informes_raw = informes_por_sala.get(sala_id, {})
                informes = _convertir_informes(informes_raw)
                log_eventos = eventos_por_sala.get(sala_id, [])

                salas.append({
                    "id": sala_id,
                    "nombre": _nombre_legible_sala(sala_id),
                    "jid": sala_jid,
                    "descripcion": "Sala de partidas Tic-Tac-Toe",
                    "ocupantes": [],
                    "informes": informes,
                    "log": log_eventos,
                })

            respuesta = {
                "salas": salas,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }

    return web.json_response(respuesta)


# ═══════════════════════════════════════════════════════════════════════════
#  EXPORTACIÓN CSV (M-03)
# ═══════════════════════════════════════════════════════════════════════════

# Tipos de evento que se consideran incidencias (misma lista que
# TIPOS_INCIDENCIA en supervisor.js para mantener coherencia).
_TIPOS_INCIDENCIA = {
    "error", "advertencia", "timeout", "abortada", "inconsistencia",
}


def _computar_ranking(informes: list[dict]) -> list[dict]:
    """Calcula la clasificación de jugadores a partir de informes.

    Replica la lógica de ``computarRanking()`` de ``supervisor.js``
    para que el CSV sea coherente con lo que muestra el panel.

    Ordenamiento: win_rate desc → victorias desc → menos abortadas
    → menos derrotas.

    Args:
        informes: Lista de informes en formato dashboard (con campos
            ``resultado``, ``ficha_ganadora``, ``jugadores``).

    Returns:
        Lista ordenada de diccionarios con las estadísticas de cada
        alumno.
    """
    stats: dict[str, dict] = {}

    for inf in informes:
        jugadores = inf.get("jugadores", {})
        jid_x = jugadores.get("X", "desconocido")
        jid_o = jugadores.get("O", "desconocido")
        alumno_x = jid_x.split("@")[0].replace("jugador_", "")
        alumno_o = jid_o.split("@")[0].replace("jugador_", "")

        for alumno in (alumno_x, alumno_o):
            if alumno not in stats:
                stats[alumno] = {
                    "alumno": alumno,
                    "partidas": 0,
                    "victorias": 0,
                    "derrotas": 0,
                    "empates": 0,
                    "abortadas": 0,
                }

        resultado = inf.get("resultado", "")

        if resultado == "abortada":
            stats[alumno_x]["partidas"] += 1
            stats[alumno_x]["abortadas"] += 1
            stats[alumno_o]["partidas"] += 1
            stats[alumno_o]["abortadas"] += 1
        elif resultado == "empate":
            stats[alumno_x]["partidas"] += 1
            stats[alumno_x]["empates"] += 1
            stats[alumno_o]["partidas"] += 1
            stats[alumno_o]["empates"] += 1
        else:
            ficha = inf.get("ficha_ganadora", "X")
            ganador = alumno_x if ficha == "X" else alumno_o
            perdedor = alumno_o if ficha == "X" else alumno_x
            stats[ganador]["partidas"] += 1
            stats[ganador]["victorias"] += 1
            stats[perdedor]["partidas"] += 1
            stats[perdedor]["derrotas"] += 1

    ranking = sorted(
        stats.values(),
        key=lambda s: (
            -(s["victorias"] / s["partidas"]
              if s["partidas"] > 0 else 0),
            -s["victorias"],
            s["abortadas"],
            s["derrotas"],
        ),
    )

    # Añadir win_rate calculado
    for entrada in ranking:
        partidas = entrada["partidas"]
        win_rate = (
            round(entrada["victorias"] / partidas * 100, 1)
            if partidas > 0 else 0.0
        )
        entrada["win_rate"] = win_rate

    return ranking


def _generar_csv_ranking(informes: list[dict]) -> str:
    """Genera una cadena CSV con la clasificación de jugadores.

    Args:
        informes: Lista de informes en formato dashboard.

    Returns:
        Contenido CSV con cabeceras y datos.
    """
    ranking = _computar_ranking(informes)

    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([
        "alumno", "partidas", "victorias", "derrotas",
        "empates", "abortadas", "win_rate",
    ])
    for entrada in ranking:
        escritor.writerow([
            entrada["alumno"],
            entrada["partidas"],
            entrada["victorias"],
            entrada["derrotas"],
            entrada["empates"],
            entrada["abortadas"],
            entrada["win_rate"],
        ])

    resultado = salida.getvalue()
    return resultado


def _generar_csv_log(eventos: list[dict]) -> str:
    """Genera una cadena CSV con el log de eventos de una sala.

    Args:
        eventos: Lista de eventos del log.

    Returns:
        Contenido CSV con cabeceras y datos.
    """
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["timestamp", "tipo", "origen", "detalle"])
    for evento in eventos:
        escritor.writerow([
            evento.get("ts", ""),
            evento.get("tipo", ""),
            evento.get("de", ""),
            evento.get("detalle", ""),
        ])

    resultado = salida.getvalue()
    return resultado


def _generar_csv_incidencias(eventos: list[dict]) -> str:
    """Genera una cadena CSV con las incidencias (errores,
    advertencias y anomalías semánticas) de una sala.

    Filtra el log completo dejando solo los eventos cuyos tipos
    están en ``_TIPOS_INCIDENCIA``.

    Args:
        eventos: Lista completa de eventos del log.

    Returns:
        Contenido CSV con cabeceras y datos filtrados.
    """
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["timestamp", "tipo", "origen", "detalle"])
    for evento in eventos:
        if evento.get("tipo", "") in _TIPOS_INCIDENCIA:
            escritor.writerow([
                evento.get("ts", ""),
                evento.get("tipo", ""),
                evento.get("de", ""),
                evento.get("detalle", ""),
            ])

    resultado = salida.getvalue()
    return resultado


def _obtener_datos_sala(
    agente, sala_id: str,
) -> tuple[list[dict], list[dict]]:
    """Obtiene los informes y el log de una sala del estado en vivo.

    Args:
        agente: Instancia del AgenteSupervisor.
        sala_id: Identificador de la sala.

    Returns:
        Tupla (informes_dashboard, log_eventos).
    """
    informes_raw = getattr(agente, "informes_por_sala", {}).get(
        sala_id, {},
    )
    informes = _convertir_informes(informes_raw)
    log_eventos = getattr(agente, "log_por_sala", {}).get(
        sala_id, [],
    )
    resultado = (informes, log_eventos)
    return resultado


def _obtener_datos_sala_historica(
    almacen, id_ejec: int, sala_id: str,
) -> tuple[list[dict], list[dict]]:
    """Obtiene los informes y el log de una sala de una ejecución
    pasada almacenada en SQLite.

    Args:
        almacen: Instancia del AlmacenSupervisor.
        id_ejec: ID de la ejecución.
        sala_id: Identificador de la sala.

    Returns:
        Tupla (informes_dashboard, log_eventos).
    """
    informes_por_sala = almacen.obtener_informes_ejecucion(id_ejec)
    eventos_por_sala = almacen.obtener_eventos_ejecucion(id_ejec)

    informes_raw = informes_por_sala.get(sala_id, {})
    informes = _convertir_informes(informes_raw)
    log_eventos = eventos_por_sala.get(sala_id, [])

    resultado = (informes, log_eventos)
    return resultado


def _respuesta_csv(
    contenido: str, nombre_fichero: str,
) -> web.Response:
    """Construye una respuesta HTTP con contenido CSV y cabeceras
    de descarga.

    Args:
        contenido: Cadena CSV generada.
        nombre_fichero: Nombre sugerido para el fichero descargado.

    Returns:
        Respuesta HTTP con Content-Type text/csv y
        Content-Disposition attachment.
    """
    respuesta = web.Response(
        text=contenido,
        content_type="text/csv",
        charset="utf-8",
    )
    respuesta.headers["Content-Disposition"] = (
        f'attachment; filename="{nombre_fichero}"'
    )
    return respuesta


async def handler_csv_en_vivo(request: web.Request) -> web.Response:
    """Exporta datos CSV del estado en vivo del supervisor.

    Ruta: ``GET /supervisor/api/csv/{tipo}``

    Parámetros de query:
        sala: ID de la sala (obligatorio).

    Tipos válidos: ``ranking``, ``log``, ``incidencias``.

    Args:
        request: Petición HTTP entrante.

    Returns:
        Respuesta CSV con Content-Disposition attachment.
    """
    agente = request.app["agente"]
    tipo = request.match_info.get("tipo", "")
    sala_id = request.query.get("sala", "")

    if not sala_id:
        return web.Response(
            text="Parámetro 'sala' obligatorio", status=400,
        )

    informes, log_eventos = _obtener_datos_sala(agente, sala_id)

    generadores = {
        "ranking": lambda: _generar_csv_ranking(informes),
        "log": lambda: _generar_csv_log(log_eventos),
        "incidencias": lambda: _generar_csv_incidencias(log_eventos),
    }

    if tipo not in generadores:
        return web.Response(
            text=f"Tipo '{tipo}' no válido. "
            f"Tipos: {', '.join(generadores)}",
            status=400,
        )

    contenido = generadores[tipo]()
    nombre = f"supervisor_{tipo}_{sala_id}.csv"

    return _respuesta_csv(contenido, nombre)


async def handler_csv_ejecucion(
    request: web.Request,
) -> web.Response:
    """Exporta datos CSV de una ejecución pasada.

    Ruta: ``GET /supervisor/api/ejecuciones/{id}/csv/{tipo}``

    Parámetros de query:
        sala: ID de la sala (obligatorio).

    Tipos válidos: ``ranking``, ``log``, ``incidencias``.

    Args:
        request: Petición HTTP entrante.

    Returns:
        Respuesta CSV con Content-Disposition attachment.
    """
    agente = request.app["agente"]

    id_texto = request.match_info.get("id", "")
    tipo = request.match_info.get("tipo", "")
    sala_id = request.query.get("sala", "")

    if not sala_id:
        return web.Response(
            text="Parámetro 'sala' obligatorio", status=400,
        )

    if not id_texto.isdigit():
        return web.Response(
            text="Ejecución no disponible", status=404,
        )

    id_ejec = int(id_texto)

    with _almacen_lectura(agente) as almacen:
        if almacen is None:
            respuesta = web.Response(
                text="Ejecución no disponible", status=404,
            )
        else:
            informes, log_eventos = _obtener_datos_sala_historica(
                almacen, id_ejec, sala_id,
            )

            generadores = {
                "ranking": lambda: _generar_csv_ranking(informes),
                "log": lambda: _generar_csv_log(log_eventos),
                "incidencias": lambda: _generar_csv_incidencias(log_eventos),
            }

            if tipo not in generadores:
                respuesta = web.Response(
                    text=f"Tipo '{tipo}' no válido. "
                    f"Tipos: {', '.join(generadores)}",
                    status=400,
                )
            else:
                contenido = generadores[tipo]()
                nombre = f"supervisor_{tipo}_ejec{id_ejec}_{sala_id}.csv"
                respuesta = _respuesta_csv(contenido, nombre)

    return respuesta


async def handler_sse_stream(request: web.Request) -> web.StreamResponse:
    """Endpoint Server-Sent Events para actualizaciones en vivo.

    Ruta: ``GET /supervisor/api/stream``

    Mantiene una conexión HTTP abierta y envía eventos SSE cada
    vez que el supervisor registra un cambio de estado (nuevo
    informe, nuevo evento de log, cambio de ocupantes).

    El cliente recibe eventos con formato SSE estándar::

        event: state
        data: {"timestamp": "10:25:33", ...}

    Si no hay eventos durante 15 segundos, se envía un comentario
    keepalive (``: keepalive``) para mantener la conexión abierta
    a través de proxies y firewalls.

    Args:
        request: Petición HTTP entrante.

    Returns:
        StreamResponse con Content-Type text/event-stream.
    """
    respuesta = web.StreamResponse()
    respuesta.content_type = "text/event-stream"
    respuesta.headers["Cache-Control"] = "no-cache"
    respuesta.headers["X-Accel-Buffering"] = "no"
    await respuesta.prepare(request)

    cola: asyncio.Queue = asyncio.Queue(maxsize=50)
    _suscriptores_sse.append(cola)

    # Enviar el estado inicial completo como primer evento
    agente = request.app["agente"]
    estado_inicial = await _construir_estado_json(agente)
    linea_inicial = (
        f"event: state\ndata: {estado_inicial}\n\n"
    )
    await respuesta.write(linea_inicial.encode("utf-8"))

    try:
        activo = True
        while activo:
            try:
                evento = await asyncio.wait_for(
                    cola.get(), timeout=15,
                )
                tipo = evento.get("tipo", "state")
                # Evento de cierre: salir del bucle para que
                # runner.cleanup() pueda completar (P-09)
                if tipo == "cierre":
                    activo = False
                else:
                    datos = json.dumps(
                        evento.get("datos", {}),
                        ensure_ascii=False,
                    )
                    linea = f"event: {tipo}\ndata: {datos}\n\n"
                    await respuesta.write(
                        linea.encode("utf-8"),
                    )
            except asyncio.TimeoutError:
                # Keepalive para mantener la conexión abierta
                await respuesta.write(b": keepalive\n\n")
            except ConnectionResetError:
                activo = False
    finally:
        if cola in _suscriptores_sse:
            _suscriptores_sse.remove(cola)

    return respuesta


async def _construir_estado_json(agente) -> str:
    """Construye el JSON del estado completo del supervisor.

    Reutiliza la lógica de ``handler_supervisor_state`` pero
    devuelve la cadena JSON directamente en vez de un Response.

    Args:
        agente: Instancia del AgenteSupervisor.

    Returns:
        Cadena JSON con el estado completo.
    """
    salas_muc = getattr(agente, "salas_muc", [])
    ocupantes_por_sala = getattr(agente, "ocupantes_por_sala", {})
    informes_por_sala = getattr(agente, "informes_por_sala", {})
    log_por_sala = getattr(agente, "log_por_sala", {})

    salas = []
    for sala_config in salas_muc:
        sala_id = sala_config["id"]
        sala_jid = sala_config["jid"]

        ocupantes = ocupantes_por_sala.get(sala_id, [])
        informes_raw = informes_por_sala.get(sala_id, {})
        informes = _convertir_informes(informes_raw)
        log_eventos = log_por_sala.get(sala_id, [])

        salas.append({
            "id": sala_id,
            "nombre": _nombre_legible_sala(sala_id),
            "jid": sala_jid,
            "descripcion": "Sala de partidas Tic-Tac-Toe",
            "ocupantes": ocupantes,
            "informes": informes,
            "log": log_eventos,
        })

    respuesta = {
        "salas": salas,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "modo_consulta": len(salas_muc) == 0,
    }

    resultado = json.dumps(respuesta, ensure_ascii=False)
    return resultado


def _exportar_csv_sesion(agente, modo: str) -> str:
    """Exporta los CSV de la sesion actual a disco al finalizar.

    Genera los ficheros ranking.csv, log.csv e incidencias.csv
    para cada sala que haya tenido trafico de informacion. Los
    ficheros se organizan en una carpeta con marca temporal y
    modo de ejecucion para no mezclar sesiones.

    Estructura generada::

        data/sesiones/
            2026-04-17_10-30-15_torneo/
                tictactoe/
                    ranking.csv
                    log.csv
                    incidencias.csv
                sala_laboratorio_01/
                    ranking.csv
                    log.csv
                    incidencias.csv

    Args:
        agente: Instancia del AgenteSupervisor con los datos
            de la sesion en curso.
        modo: Modo de ejecucion ('laboratorio' o 'torneo').

    Returns:
        Ruta del directorio raiz de la sesion generada.
    """
    marca = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    directorio_sesion = pathlib.Path(
        "data", "sesiones", f"{marca}_{modo}",
    )

    salas_muc = getattr(agente, "salas_muc", [])
    informes_por_sala = getattr(agente, "informes_por_sala", {})
    log_por_sala = getattr(agente, "log_por_sala", {})

    salas_exportadas = 0
    i = 0
    while i < len(salas_muc):
        sala = salas_muc[i]
        sala_id = sala["id"]
        i += 1

        # Solo exportar salas con actividad (informes o eventos)
        informes_raw = informes_por_sala.get(sala_id, {})
        log_eventos = log_por_sala.get(sala_id, [])
        tiene_informes = len(informes_raw) > 0
        tiene_eventos = len(log_eventos) > 0

        if not tiene_informes and not tiene_eventos:
            continue

        # Crear directorio de la sala
        directorio_sala = directorio_sesion / sala_id
        directorio_sala.mkdir(parents=True, exist_ok=True)

        informes = _convertir_informes(informes_raw)

        # Generar ranking.csv (solo si hay informes)
        if tiene_informes:
            contenido_ranking = _generar_csv_ranking(informes)
            ruta_ranking = directorio_sala / "ranking.csv"
            ruta_ranking.write_text(
                contenido_ranking, encoding="utf-8",
            )

        # Generar log.csv
        if tiene_eventos:
            contenido_log = _generar_csv_log(log_eventos)
            ruta_log = directorio_sala / "log.csv"
            ruta_log.write_text(
                contenido_log, encoding="utf-8",
            )

        # Generar incidencias.csv (solo si hay incidencias)
        contenido_inc = _generar_csv_incidencias(log_eventos)
        lineas_inc = contenido_inc.strip().split("\n")
        tiene_incidencias = len(lineas_inc) > 1
        if tiene_incidencias:
            ruta_inc = directorio_sala / "incidencias.csv"
            ruta_inc.write_text(
                contenido_inc, encoding="utf-8",
            )

        salas_exportadas += 1

    logger.info(
        "CSV de sesion exportados en %s (%d salas)",
        directorio_sesion, salas_exportadas,
    )

    resultado = str(directorio_sesion)
    return resultado


async def handler_finalizar_torneo(
    request: web.Request,
) -> web.Response:
    """Finaliza el torneo de forma ordenada desde el dashboard.

    Funciona en los tres modos de ejecución del supervisor:

    - **Consulta**: no hay agente XMPP ni partidas activas. Se
      cierra el almacén y se activa el evento de parada para que
      el proceso termine.
    - **Laboratorio / Torneo**: ejecuta el cierre controlado del
      supervisor (registra informes pendientes, marca la ejecución
      como finalizada en la BD) y activa el evento de parada del
      proceso principal para un apagado ordenado.

    El endpoint respeta la autenticación HTTP Basic si está
    configurada (el middleware se aplica a todas las rutas no
    estáticas).

    Args:
        request: Petición HTTP POST entrante.

    Returns:
        JSON con el estado de la finalización, la marca temporal
        y el modo en que se estaba ejecutando.
    """
    agente = request.app["agente"]
    modo = request.app.get("modo", "desconocido")
    evento_parada = request.app.get("evento_parada", None)

    ts = datetime.now().strftime("%H:%M:%S")

    if modo == "consulta":
        # Modo consulta: solo cerrar el almacén (si existe)
        almacen = getattr(agente, "almacen", None)
        if almacen is not None:
            almacen.cerrar()

    else:
        # Modos laboratorio / torneo: cierre completo del agente
        salas_muc = getattr(agente, "salas_muc", [])
        registrar = getattr(agente, "registrar_evento_log", None)

        if registrar is not None:
            for sala in salas_muc:
                registrar(
                    "advertencia", "supervisor",
                    "Torneo finalizado desde el dashboard",
                    sala["id"],
                )

        # Exportar CSV de la sesion antes de cerrar la
        # persistencia. Se genera un directorio por sesion con
        # subdirectorios por sala que haya tenido trafico.
        ruta_csv = _exportar_csv_sesion(agente, modo)

        # Notificar a todos los clientes SSE antes de cerrar
        notificar_sse("torneo_finalizado", {"timestamp": ts})

        # Cierre ordenado de la persistencia
        detener = getattr(agente, "detener_persistencia", None)
        if detener is not None:
            await detener()

    # Cerrar las conexiones SSE activas para que runner.cleanup()
    # no se bloquee esperando a que terminen
    for cola in list(_suscriptores_sse):
        cola.put_nowait({"tipo": "cierre", "datos": {}})

    # Programar la activación del evento de parada con un retardo
    # para que la respuesta HTTP llegue al cliente antes de que
    # runner.cleanup() cierre el servidor web.
    if evento_parada is not None:
        loop = asyncio.get_event_loop()
        loop.call_later(1.0, evento_parada.set)

    respuesta_json = {
        "estado": "finalizado",
        "timestamp": ts,
        "modo": modo,
    }
    if modo != "consulta":
        respuesta_json["csv_exportados"] = ruta_csv

    return web.json_response(respuesta_json)


def registrar_rutas_supervisor(app: web.Application) -> None:
    """Registra todas las rutas HTTP del supervisor en la aplicación aiohttp.

    Añade las rutas para el panel web HTML, la API JSON de estado
    en vivo, las ejecuciones pasadas y los ficheros estáticos.

    Args:
        app: Aplicación aiohttp donde registrar las rutas.
    """
    # Página principal del panel
    app.router.add_get("/supervisor", handler_supervisor_index)
    app.router.add_get("/supervisor/", handler_supervisor_index)

    # API JSON — estado en vivo
    app.router.add_get("/supervisor/api/state", handler_supervisor_state)

    # API JSON — ejecuciones pasadas
    app.router.add_get(
        "/supervisor/api/ejecuciones", handler_listar_ejecuciones,
    )
    app.router.add_get(
        "/supervisor/api/ejecuciones/{id}", handler_datos_ejecucion,
    )

    # API SSE — actualizaciones en tiempo real
    app.router.add_get(
        "/supervisor/api/stream", handler_sse_stream,
    )

    # API CSV — exportación en vivo
    app.router.add_get(
        "/supervisor/api/csv/{tipo}", handler_csv_en_vivo,
    )

    # API CSV — exportación de ejecuciones pasadas
    app.router.add_get(
        "/supervisor/api/ejecuciones/{id}/csv/{tipo}",
        handler_csv_ejecucion,
    )

    # API POST — finalizar torneo desde el dashboard (P-09)
    app.router.add_post(
        "/supervisor/api/finalizar-torneo",
        handler_finalizar_torneo,
    )

    # Ficheros estáticos (CSS, JS)
    app.router.add_static("/supervisor/static", _DIR_STATIC)

    logger.info(
        "Rutas del supervisor registradas: /supervisor, "
        "/supervisor/api/state, /supervisor/api/ejecuciones, "
        "/supervisor/api/csv, /supervisor/api/finalizar-torneo, "
        "/supervisor/static/",
    )
