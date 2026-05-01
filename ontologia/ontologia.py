"""
Ontologia del sistema Tic-Tac-Toe multiagente.

Carga el JSON Schema generado por Pydantic (fase de diseno)
y proporciona constructores y validadores para los mensajes.

Dependencias: json (stdlib), jsonschema, spade.

- Los constructores ``crear_cuerpo_*`` generan el body JSON
  (solo necesitan jsonschema).
- El constructor ``crear_mensaje_join`` genera un Message SPADE
  completo con toda la metadata (necesita spade).

Uso desde los agentes::

    from ontologia.ontologia import (
        ONTOLOGIA, crear_cuerpo_join, crear_mensaje_join,
        crear_cuerpo_move, validar_cuerpo,
        obtener_performativa, obtener_conversation_id,
        crear_thread_unico, PREFIJO_THREAD_GAME,
    )
"""
import json
import logging
import pathlib
import uuid
from typing import Any, NamedTuple

import jsonschema
from spade.message import Message

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

# == Vocabulario de performativas FIPA ====================================
# Estas constantes simbolicas son la UNICA forma admitida en el sistema
# de referirse a las performativas FIPA-ACL. Tanto si el alumno usa los
# constructores ``crear_cuerpo_*`` (que ya emparejan performativa+body)
# como si configura el ``performative`` de un Message a mano o construye
# un Template, debe importar estas constantes en lugar de escribir las
# cadenas literales ("request", "agree", ...). Asi se garantiza que
# todos los agentes del torneo usen exactamente la misma representacion
# y se evitan inconsistencias por mayusculas, guiones o erratas.
PERFORMATIVA_REQUEST = "request"
PERFORMATIVA_AGREE = "agree"
PERFORMATIVA_REFUSE = "refuse"
PERFORMATIVA_FAILURE = "failure"
PERFORMATIVA_INFORM = "inform"
PERFORMATIVA_CFP = "cfp"
PERFORMATIVA_PROPOSE = "propose"
PERFORMATIVA_ACCEPT_PROPOSAL = "accept_proposal"
PERFORMATIVA_REJECT_PROPOSAL = "reject_proposal"

# Conjunto con todas las performativas validas del sistema, util para
# tests y validaciones genericas (p. ej. comprobar que un mensaje
# entrante trae una performativa reconocida).
PERFORMATIVAS_VALIDAS: frozenset[str] = frozenset({
    PERFORMATIVA_REQUEST,
    PERFORMATIVA_AGREE,
    PERFORMATIVA_REFUSE,
    PERFORMATIVA_FAILURE,
    PERFORMATIVA_INFORM,
    PERFORMATIVA_CFP,
    PERFORMATIVA_PROPOSE,
    PERFORMATIVA_ACCEPT_PROPOSAL,
    PERFORMATIVA_REJECT_PROPOSAL,
})

PERFORMATIVA_POR_ACCION: dict[str, str] = {
    "join": PERFORMATIVA_REQUEST,
    "join-accepted": PERFORMATIVA_AGREE,
    "join-refused": PERFORMATIVA_REFUSE,
    "join-timeout": PERFORMATIVA_FAILURE,
    "game-start": PERFORMATIVA_INFORM,
    "turn": PERFORMATIVA_CFP,
    "move": PERFORMATIVA_PROPOSE,
    "ok": PERFORMATIVA_PROPOSE,
    "game-over": PERFORMATIVA_REJECT_PROPOSAL,
    "turn-result": PERFORMATIVA_INFORM,
    "game-report": PERFORMATIVA_REQUEST,
}


class ContenidoMensaje(NamedTuple):
    """Contenido completo de un mensaje FIPA: performativa + body JSON.

    Las funciones ``crear_cuerpo_*`` devuelven esta tupla nombrada para
    que la performativa siempre viaje EMPAREJADA con su cuerpo. Asi el
    alumno no puede desincronizarlas por accidente (escribir manualmente
    una performativa con erratas o usando una accion incorrecta).

    Atributos:
        performativa: Cadena FIPA-ACL ("request", "inform", ...). Siempre
            es uno de los valores del vocabulario ``PERFORMATIVA_*``.
        cuerpo: Body JSON serializado, listo para asignar a
            ``mensaje.body``.

    Uso tipico::

        contenido = crear_cuerpo_join()
        mensaje.set_metadata("performative", contenido.performativa)
        mensaje.body = contenido.cuerpo
    """
    performativa: str
    cuerpo: str


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


def _validar_y_serializar(contenido: dict[str, Any]) -> ContenidoMensaje:
    """Valida contra el esquema, serializa a JSON y empareja con la
    performativa FIPA correspondiente a la accion.

    Devolver la performativa junto al body garantiza que el alumno no
    pueda desincronizar ambos campos: la performativa siempre se
    obtiene del vocabulario centralizado ``PERFORMATIVA_POR_ACCION``.

    Args:
        contenido: Diccionario con los campos del mensaje. Debe
            incluir la clave ``"action"`` para poder resolver la
            performativa asociada.

    Returns:
        ``ContenidoMensaje`` con la performativa FIPA y el body JSON.

    Raises:
        ValueError: Si el contenido no cumple el JSON Schema o si su
            ``action`` no tiene performativa registrada.
    """
    errores = validar_cuerpo(contenido)
    if not errores["valido"]:
        raise ValueError(
            f"Mensaje invalido: {'; '.join(errores['errores'])}"
        )
    accion = contenido["action"]
    performativa = obtener_performativa(accion)
    cuerpo_json = json.dumps(contenido, ensure_ascii=False)
    resultado = ContenidoMensaje(
        performativa=performativa, cuerpo=cuerpo_json,
    )
    return resultado


# == Constructores =========================================================


def crear_cuerpo_join() -> ContenidoMensaje:
    """Crea contenido para inscripcion (performativa REQUEST + body)."""
    resultado = _validar_y_serializar({"action": "join"})
    return resultado


def crear_cuerpo_join_accepted(simbolo: str) -> ContenidoMensaje:
    """Crea contenido de aceptacion (performativa AGREE + body).

    Args:
        simbolo: 'X' u 'O', el simbolo asignado al jugador.
    """
    contenido = {"action": "join-accepted", "symbol": simbolo}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_join_refused(razon: str) -> ContenidoMensaje:
    """Crea contenido de rechazo de inscripcion (performativa REFUSE + body).

    Args:
        razon: 'full' o 'no opponent'.
    """
    contenido = {"action": "join-refused", "reason": razon}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_join_timeout(razon: str) -> ContenidoMensaje:
    """Crea contenido de timeout esperando rival (performativa FAILURE + body).

    Args:
        razon: 'full' o 'no opponent'.
    """
    contenido = {"action": "join-timeout", "reason": razon}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_game_start(
    oponente: str, thread_partida: str,
) -> ContenidoMensaje:
    """Crea contenido de inicio de partida (performativa INFORM + body).

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


def crear_cuerpo_turn(simbolo_activo: str) -> ContenidoMensaje:
    """Crea contenido de convocatoria de turno (performativa CFP + body).

    Args:
        simbolo_activo: 'X' u 'O', quien tiene el turno.
    """
    contenido = {"action": "turn", "active_symbol": simbolo_activo}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_move(posicion: int) -> ContenidoMensaje:
    """Crea contenido para proponer movimiento (performativa PROPOSE + body).

    Args:
        posicion: Entero entre 0 y 8.

    Raises:
        ValueError: Si posicion esta fuera del rango 0-8.
    """
    contenido = {"action": "move", "position": posicion}
    resultado = _validar_y_serializar(contenido)
    return resultado


def crear_cuerpo_move_confirmado(
    posicion: int, simbolo: str,
) -> ContenidoMensaje:
    """Crea contenido de movimiento confirmado.

    El ``move`` confirmado por el tablero usa la performativa
    ACCEPT_PROPOSAL (en lugar de PROPOSE) para distinguir, en el
    template del receptor, la propuesta original del jugador de la
    confirmacion del tablero. Por eso esta funcion sobreescribe la
    performativa de ``move`` con ``PERFORMATIVA_ACCEPT_PROPOSAL``.

    Args:
        posicion: Entero entre 0 y 8.
        simbolo: 'X' u 'O', simbolo del jugador que movio.
    """
    contenido = {"action": "move", "position": posicion, "symbol": simbolo}
    base = _validar_y_serializar(contenido)
    resultado = ContenidoMensaje(
        performativa=PERFORMATIVA_ACCEPT_PROPOSAL,
        cuerpo=base.cuerpo,
    )
    return resultado


def crear_cuerpo_ok() -> ContenidoMensaje:
    """Crea contenido de confirmacion generica (performativa PROPOSE)."""
    resultado = _validar_y_serializar({"action": "ok"})
    return resultado


def crear_cuerpo_game_over(
    razon: str, ganador: str | None = None,
) -> ContenidoMensaje:
    """Crea contenido para fin de partida (performativa REJECT_PROPOSAL).

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
) -> ContenidoMensaje:
    """Crea contenido del resultado del turno (performativa INFORM + body).

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


def crear_cuerpo_game_report_request() -> ContenidoMensaje:
    """Crea contenido para solicitar informe (performativa REQUEST + body)."""
    resultado = _validar_y_serializar({"action": "game-report"})
    return resultado


def crear_cuerpo_game_report(
    resultado_partida: str,
    ganador: str | None,
    jugadores: dict[str, str],
    turnos: int,
    tablero: list[str],
    razon: str | None = None,
) -> ContenidoMensaje:
    """Crea contenido del informe de partida (performativa INFORM + body).

    El supervisor envia el ``game-report`` como REQUEST y el tablero
    responde con esta funcion. Para que el supervisor pueda distinguir
    su propio REQUEST de la respuesta del tablero por la performativa,
    esta funcion sobreescribe la performativa por defecto del action
    ``game-report`` (REQUEST) por ``PERFORMATIVA_INFORM``.

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
    base = _validar_y_serializar(contenido)
    resultado = ContenidoMensaje(
        performativa=PERFORMATIVA_INFORM, cuerpo=base.cuerpo,
    )
    return resultado


def crear_cuerpo_game_report_refused() -> ContenidoMensaje:
    """Crea contenido de rechazo de solicitud de informe (REFUSE).

    El tablero usa este mensaje para responder al REQUEST del
    supervisor cuando aun no tiene un informe que entregar (la
    partida no ha terminado). Sobreescribe la performativa por
    defecto del action ``game-report`` (REQUEST) por
    ``PERFORMATIVA_REFUSE``.
    """
    contenido = {"action": "game-report", "reason": "not-finished"}
    base = _validar_y_serializar(contenido)
    resultado = ContenidoMensaje(
        performativa=PERFORMATIVA_REFUSE, cuerpo=base.cuerpo,
    )
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
    contenido = crear_cuerpo_join()
    mensaje = Message(to=jid_tablero)
    mensaje.set_metadata("ontology", ONTOLOGIA)
    mensaje.set_metadata("performative", contenido.performativa)
    mensaje.set_metadata(
        "conversation-id", obtener_conversation_id("join"),
    )
    mensaje.thread = crear_thread_unico(
        jid_jugador, PREFIJO_THREAD_JOIN,
    )
    mensaje.body = contenido.cuerpo
    return mensaje
