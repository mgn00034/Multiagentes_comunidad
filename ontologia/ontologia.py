"""
Ontologia del sistema Tic-Tac-Toe multiagente.

Carga el JSON Schema generado por Pydantic (fase de diseno)
y proporciona constructores y validadores para los mensajes.

Dependencias: json (stdlib), jsonschema, spade.

- Los constructores ``crear_cuerpo_*`` generan el body JSON
  (solo necesitan jsonschema).
- El constructor ``crear_mensaje_join`` genera un Message SPADE
  completo con toda la metadata (necesita spade).
- Los constructores ``crear_plantilla_*`` generan Templates SPADE
  listas para registrar behaviours en el tablero (necesitan spade).

Uso desde los agentes::

    from ontologia.ontologia import (
        ONTOLOGIA, crear_cuerpo_join, crear_mensaje_join,
        crear_cuerpo_move, validar_cuerpo,
        obtener_performativa, obtener_conversation_id,
        crear_plantilla_join, crear_plantilla_game_report,
        crear_thread_unico, PREFIJO_THREAD_GAME,
    )
"""
import json
import logging
import pathlib
import uuid
from typing import Any

import jsonschema
from spade.message import Message
from spade.template import Template

logger = logging.getLogger(__name__)

# == Carga del esquema generado ============================================

_DIRECTORIO_ACTUAL = pathlib.Path(__file__).parent

ESQUEMA_ONTOLOGIA: dict = json.loads(
    (_DIRECTORIO_ACTUAL / "ontologia_tictactoe.schema.json")
    .read_text(encoding="utf-8")
)

CAMPOS_POR_ACCION: dict[str, list[str]] = json.loads(
    (_DIRECTORIO_ACTUAL / "ontologia_campos.json")
    .read_text(encoding="utf-8")
)

# == Constantes derivadas del esquema ======================================

ONTOLOGIA = "tictactoe"
ACCIONES_VALIDAS = tuple(CAMPOS_POR_ACCION.keys())
SIMBOLOS_VALIDOS = ("X", "O")
POSICIONES_VALIDAS = range(0, 9)

CONVERSATION_ID_POR_ACCION: dict[str, str] = {
    "join": "join",
    "game-report": "game-report",
}

PERFORMATIVA_POR_ACCION: dict[str, str] = {
    "join": "request",
    "join-accepted": "agree",
    "join-refused": "refuse",
    "join-timeout": "failure",
    "game-start": "inform",
    "turn": "cfp",
    "move": "propose",
    "ok": "propose",
    "game-over": "reject_proposal",
    "turn-result": "inform",
    "game-report": "request",
}


def obtener_performativa(accion: str) -> str:
    """Devuelve la performativa FIPA asociada a una accion.

    Args:
        accion: Valor del campo 'action' del mensaje.

    Returns:
        Cadena con la performativa FIPA correspondiente.

    Raises:
        KeyError: Si la accion no tiene performativa asociada.
    """
    resultado = PERFORMATIVA_POR_ACCION[accion]
    return resultado


def obtener_conversation_id(accion: str) -> str:
    """Devuelve el conversation-id asociado a una accion REQUEST.

    Solo las acciones que inician un protocolo REQUEST tienen
    conversation-id definido. Las respuestas (AGREE, INFORM,
    REFUSE, FAILURE) se correlacionan por thread, no por
    conversation-id.

    Args:
        accion: Valor del campo 'action' del mensaje
            (solo 'join' o 'game-report').

    Returns:
        Cadena con el conversation-id correspondiente.

    Raises:
        KeyError: Si la accion no tiene conversation-id
            (no es un REQUEST que inicie protocolo).
    """
    resultado = CONVERSATION_ID_POR_ACCION[accion]
    return resultado


# == Validador =============================================================


def validar_cuerpo(cuerpo: dict[str, Any]) -> dict[str, Any]:
    """Valida un cuerpo de mensaje contra la ontologia.

    Realiza cuatro niveles de validacion:
      0. Presencia del campo 'action'.
      1. JSON Schema (tipos, enums, rangos).
      2. Campos obligatorios segun la accion.
      3. Reglas condicionales cruzadas.

    Args:
        cuerpo: Diccionario con los campos del mensaje.

    Returns:
        Diccionario con claves 'valido' (bool) y 'errores' (list[str]).
    """
    errores: list[str] = []

    # -- Nivel 0: presencia del campo 'action' --
    if "action" not in cuerpo:
        errores.append("Falta el campo obligatorio 'action'")

    # -- Nivel 1: validar contra JSON Schema (oneOf) --
    try:
        jsonschema.validate(instance=cuerpo, schema=ESQUEMA_ONTOLOGIA)
    except jsonschema.ValidationError as error:
        errores.append(f"Error de esquema: {error.message}")

    # -- Nivel 2: campos segun la accion --
    accion = cuerpo.get("action", "")
    for campo in CAMPOS_POR_ACCION.get(accion, []):
        if campo not in cuerpo:
            errores.append(f"Falta '{campo}' para action='{accion}'")

    # -- Nivel 3: reglas condicionales cruzadas --
    if cuerpo.get("result") == "win" and cuerpo.get("winner") is None:
        errores.append("Si result='win', 'winner' es obligatorio")

    if cuerpo.get("result") == "draw" and cuerpo.get("winner") is not None:
        errores.append("Si result='draw', 'winner' debe ser null")

    if cuerpo.get("result") == "continue" and cuerpo.get("winner") is not None:
        errores.append("Si result='continue', 'winner' debe ser null")

    if cuerpo.get("result") == "aborted" and "reason" not in cuerpo:
        errores.append("Si result='aborted', 'reason' es obligatorio")

    if cuerpo.get("action") == "game-over" and "reason" not in cuerpo:
        errores.append("Si action='game-over', 'reason' es obligatorio")

    resultado = {"valido": len(errores) == 0, "errores": errores}
    return resultado


# == Guardian interno ======================================================


def _validar_y_serializar(contenido: dict[str, Any]) -> str:
    """Valida contra el esquema y serializa a JSON.

    Args:
        contenido: Diccionario con los campos del mensaje.

    Returns:
        Cadena JSON lista para usar como body FIPA.

    Raises:
        ValueError: Si el contenido no cumple el JSON Schema.
    """
    errores = validar_cuerpo(contenido)
    if not errores["valido"]:
        raise ValueError(
            f"Mensaje invalido: {'; '.join(errores['errores'])}"
        )
    resultado = json.dumps(contenido, ensure_ascii=False)
    return resultado


# == Constructores =========================================================


def crear_cuerpo_join() -> str:
    """Crea el body JSON para inscripcion (REQUEST)."""
    resultado = _validar_y_serializar({"action": "join"})
    return resultado


def crear_cuerpo_join_accepted(simbolo: str) -> str:
    """Crea el body JSON de aceptacion (AGREE).

    Args:
        simbolo: 'X' u 'O', el simbolo asignado al jugador.
    """
    contenido = {"action": "join-accepted", "symbol": simbolo}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_join_refused(razon: str) -> str:
    """Crea el body JSON de rechazo de inscripcion (REFUSE).

    Args:
        razon: 'full' o 'no opponent'.
    """
    contenido = {"action": "join-refused", "reason": razon}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_join_timeout(razon: str) -> str:
    """Crea el body JSON de timeout esperando rival (FAILURE).

    Args:
        razon: 'full' o 'no opponent'.
    """
    contenido = {"action": "join-timeout", "reason": razon}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_game_start(oponente: str, thread_partida: str) -> str:
    """Crea el body JSON de inicio de partida (INFORM).

    El ``game-start`` cierra la fase de inscripcion y abre la fase
    de juego. Incluye el ``thread_partida`` en el body para que el
    jugador pueda construir el template de su behaviour de partida
    en el mismo instante en que recibe el mensaje, sin esperar al
    primer ``CFP turn``. Esto evita condiciones de carrera en las
    que un ``turn`` adelantado llegaria antes de que el jugador
    tenga su template listo.

    Args:
        oponente: JID completo del rival.
        thread_partida: Identificador de thread unico que el tablero
            va a usar en todos los mensajes de la partida
            (``turn``, ``move``, ``turn-result``, ``game-over``).
            Debe generarse con ``crear_thread_unico``.
    """
    contenido = {
        "action": "game-start",
        "opponent": oponente,
        "thread": thread_partida,
    }
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_turn(simbolo_activo: str) -> str:
    """Crea el body JSON de convocatoria de turno (CFP).

    Args:
        simbolo_activo: 'X' u 'O', quien tiene el turno.
    """
    contenido = {"action": "turn", "active_symbol": simbolo_activo}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_move(posicion: int) -> str:
    """Crea el body JSON para proponer movimiento (PROPOSE).

    Args:
        posicion: Entero entre 0 y 8.

    Raises:
        ValueError: Si posicion esta fuera del rango 0-8.
    """
    contenido = {"action": "move", "position": posicion}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_move_confirmado(posicion: int, simbolo: str) -> str:
    """Crea el body JSON de movimiento confirmado (ACCEPT_PROPOSAL).

    Args:
        posicion: Entero entre 0 y 8.
        simbolo: 'X' u 'O', simbolo del jugador que movio.
    """
    contenido = {"action": "move", "position": posicion, "symbol": simbolo}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_ok() -> str:
    """Crea el body JSON de confirmacion generica (PROPOSE no activo)."""
    resultado = _validar_y_serializar({"action": "ok"})
    return resultado


def crear_cuerpo_game_over(razon: str, ganador: str | None = None) -> str:
    """Crea el body JSON para fin de partida (REJECT_PROPOSAL).

    Args:
        razon: 'invalid', 'timeout' o 'both-timeout'.
        ganador: 'X', 'O' o None (si ambos pierden).
    """
    contenido: dict[str, Any] = {
        "action": "game-over", "reason": razon, "winner": ganador,
    }
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_turn_result(
    resultado_turno: str,
    ganador: str | None = None,
) -> str:
    """Crea el body JSON del resultado del turno (INFORM Jugador -> Tablero).

    El jugador activo informa al tablero del estado de la partida despues
    de aplicar su movimiento: continua, victoria o empate.

    Args:
        resultado_turno: 'continue', 'win' o 'draw'.
        ganador: 'X' u 'O' si resultado_turno='win'; None en otro caso.
    """
    contenido: dict[str, Any] = {
        "action": "turn-result",
        "result": resultado_turno,
        "winner": ganador,
    }
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_game_report_request() -> str:
    """Crea el body JSON para solicitar informe (REQUEST del supervisor)."""
    resultado = _validar_y_serializar({"action": "game-report"})
    return resultado


def crear_cuerpo_game_report(
    resultado_partida: str,
    ganador: str | None,
    jugadores: dict[str, str],
    turnos: int,
    tablero: list[str],
    razon: str | None = None,
) -> str:
    """Crea el body JSON del informe de partida (INFORM tablero -> supervisor).

    Args:
        resultado_partida: 'win', 'draw' o 'aborted'.
        ganador: 'X', 'O' o None.
        jugadores: Mapa con formato {"X": jid_x, "O": jid_o}.
        turnos: Numero de turnos jugados (1-9).
        tablero: Lista de 9 strings con "", "X" u "O".
        razon: Razon de la finalizacion (si fue abortada).
    """
    contenido: dict[str, Any] = {
        "action": "game-report",
        "result": resultado_partida,
        "winner": ganador,
        "players": jugadores,
        "turns": turnos,
        "board": tablero,
    }
    if razon is not None:
        contenido["reason"] = razon
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_game_report_refused() -> str:
    """Crea el body JSON de rechazo de solicitud de informe (REFUSE)."""
    contenido = {"action": "game-report", "reason": "not-finished"}
    resultado = _validar_y_serializar(contenido)
    return resultado


# == Generador de threads unicos =============================================
# El thread es el mecanismo FIPA-ACL que correlaciona los mensajes
# de una misma conversacion (inscripcion, partida, informe). En un
# torneo con muchos agentes compartiendo una sala MUC, dos threads
# generados con baja resolucion temporal pueden coincidir y hacer
# que el template de un agente acepte mensajes destinados a otro.
# Esta funcion elimina ese riesgo combinando prefijo + JID + UUID4.

PREFIJO_THREAD_JOIN = "join"
PREFIJO_THREAD_GAME = "game"
PREFIJO_THREAD_REPORT = "report"


def crear_thread_unico(
    jid_agente: str,
    prefijo: str = PREFIJO_THREAD_GAME,
) -> str:
    """Genera un identificador de thread unico globalmente.

    Combina tres componentes que, juntos, hacen imposible la
    colision con el thread de cualquier otro agente del torneo:

      1. ``prefijo``: etiqueta semantica del tipo de conversacion
         (``"join"``, ``"game"``, ``"report"``). Facilita la lectura
         de trazas pero no aporta unicidad por si solo.
      2. Parte local del ``jid_agente`` (lo que hay antes de ``@``).
         Garantiza unicidad entre agentes distintos del torneo
         porque los JID locales son unicos dentro del dominio XMPP.
      3. UUID4 aleatorio de 128 bits en hexadecimal. Garantiza
         unicidad entre invocaciones del mismo agente sin depender
         de la resolucion del reloj (dos llamadas en el mismo
         microsegundo producen UUIDs distintos).

    Formato resultante: ``{prefijo}-{localpart}-{uuid_hex}``.
    Ejemplo: ``game-tablero_01-7f3cab92d4e14f7b9a1c0e2f8d5b6a3c``.

    Uso tipico en un behaviour del tablero al formar pareja::

        from ontologia.ontologia import (
            crear_thread_unico, PREFIJO_THREAD_GAME,
        )

        thread_partida = crear_thread_unico(
            str(self.agent.jid), PREFIJO_THREAD_GAME,
        )
        mensaje.thread = thread_partida

    Args:
        jid_agente: JID del agente que origina la conversacion
            (bare o completo; el recurso ``/xxx`` se ignora). Por
            ejemplo ``"tablero_01@localhost"``.
        prefijo: Etiqueta del tipo de conversacion. Por convencion
            uno de ``PREFIJO_THREAD_JOIN``, ``PREFIJO_THREAD_GAME``
            o ``PREFIJO_THREAD_REPORT``. Por defecto, ``"game"``.

    Returns:
        Cadena lista para asignar a ``mensaje.thread``.
    """
    localpart = jid_agente.split("@")[0]
    aleatorio = uuid.uuid4().hex
    resultado = f"{prefijo}-{localpart}-{aleatorio}"
    return resultado


# == Constructor de mensajes SPADE completos ================================
# A diferencia de los constructores crear_cuerpo_* que solo generan
# el body JSON, estas funciones construyen un Message SPADE listo
# para enviar, con toda la metadata (ontologia, performativa,
# conversation-id) ya configurada. Esto evita que el alumno tenga
# que recordar cada campo y garantiza la interoperabilidad en torneo.


def crear_mensaje_join(jid_tablero: str, jid_jugador: str) -> Message:
    """Crea un mensaje SPADE completo para solicitar la inscripcion
    en una mesa (REQUEST join).

    El mensaje incluye toda la metadata necesaria para que el
    tablero de cualquier alumno lo enrute correctamente al
    behaviour de inscripcion mediante template matching:

    - ``ontology``: identifica el sistema (tictactoe).
    - ``performative``: tipo de acto comunicativo (request).
    - ``conversation-id``: discrimina el protocolo (join).
    - ``thread``: identificador unico de esta inscripcion, generado
      con ``crear_thread_unico`` y prefijado con ``join``. Garantiza
      que las respuestas del tablero (``join-accepted``,
      ``join-refused``, ``join-timeout``) se correlacionen con
      exactitud con esta peticion concreta, incluso si el jugador
      intenta inscribirse en varias mesas simultaneamente.
    - ``body``: contenido JSON con ``action: "join"``.

    Args:
        jid_tablero: JID completo del agente tablero al que el
            jugador quiere inscribirse (ej: ``"tablero_mesa1@localhost"``).
        jid_jugador: JID del propio jugador que origina la
            inscripcion. Se usa como parte local del thread para
            evitar colisiones entre inscripciones de jugadores
            distintos en el mismo tablero.

    Returns:
        Mensaje SPADE listo para enviar con ``await self.send(msg)``.

    Ejemplo de uso en el behaviour del jugador::

        from ontologia.ontologia import crear_mensaje_join

        mensaje = crear_mensaje_join(jid_tablero, str(self.agent.jid))
        await self.send(mensaje)
    """
    mensaje = Message(to=jid_tablero)
    mensaje.set_metadata("ontology", ONTOLOGIA)
    mensaje.set_metadata(
        "performative", obtener_performativa("join"),
    )
    mensaje.set_metadata(
        "conversation-id", obtener_conversation_id("join"),
    )
    mensaje.thread = crear_thread_unico(
        jid_jugador, PREFIJO_THREAD_JOIN,
    )
    mensaje.body = crear_cuerpo_join()
    return mensaje


# == Plantillas (Templates) para behaviours del tablero ==================
#
# Estas funciones generan Templates SPADE listas para que los tableros
# las registren en sus behaviours. Cada plantilla filtra los mensajes
# entrantes por ontologia, performativa y conversation-id, de forma
# que el behaviour solo reciba los mensajes del protocolo correcto.


def crear_plantilla_join() -> Template:
    """Crea la plantilla SPADE que el tablero debe registrar para
    aceptar solicitudes de inscripcion (REQUEST join) de los jugadores.

    La plantilla filtra por tres campos de metadata:

    - ``ontology``: ``"tictactoe"``
    - ``performative``: ``"request"``
    - ``conversation-id``: ``"join"``

    Returns:
        Template SPADE lista para usar en ``add_behaviour(behaviour, template)``.

    Ejemplo de uso en el setup del tablero::

        from ontologia.ontologia import crear_plantilla_join

        plantilla = crear_plantilla_join()
        self.add_behaviour(mi_behaviour_inscripcion, plantilla)
    """
    plantilla = Template()
    plantilla.set_metadata("ontology", ONTOLOGIA)
    plantilla.set_metadata(
        "performative", obtener_performativa("join"),
    )
    plantilla.set_metadata(
        "conversation-id", obtener_conversation_id("join"),
    )
    return plantilla


def crear_plantilla_game_report() -> Template:
    """Crea la plantilla SPADE que el tablero debe registrar para
    aceptar solicitudes de informe (REQUEST game-report) del supervisor.

    La plantilla filtra por tres campos de metadata:

    - ``ontology``: ``"tictactoe"``
    - ``performative``: ``"request"``
    - ``conversation-id``: ``"game-report"``

    Returns:
        Template SPADE lista para usar en ``add_behaviour(behaviour, template)``.

    Ejemplo de uso en el setup del tablero::

        from ontologia.ontologia import crear_plantilla_game_report

        plantilla = crear_plantilla_game_report()
        self.add_behaviour(mi_behaviour_informe, plantilla)
    """
    plantilla = Template()
    plantilla.set_metadata("ontology", ONTOLOGIA)
    plantilla.set_metadata(
        "performative", obtener_performativa("game-report"),
    )
    plantilla.set_metadata(
        "conversation-id", obtener_conversation_id("game-report"),
    )
    return plantilla
