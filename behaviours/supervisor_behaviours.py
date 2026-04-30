"""
Comportamientos del Agente Supervisor.

Define los behaviours que permiten al supervisor monitorizar múltiples
salas MUC y recopilar informes de partida de los tableros:

- ``MonitorizarMUCBehaviour``: periódico, consulta los ocupantes de
  cada sala MUC y actualiza el estado del dashboard.
- ``SolicitarInformeFSM``: máquina de estados finitos (FSMBehaviour)
  que gestiona el protocolo FIPA-Request completo para solicitar y
  recibir un informe de partida de un tablero concreto.

La detección de tableros finalizados se realiza de forma reactiva
mediante el callback de presencia ``_on_presencia_muc`` del agente
(modelo push), coherente con el paso 0 del protocolo documentado.
"""

import asyncio
import json
import logging
import time

from spade.behaviour import FSMBehaviour, PeriodicBehaviour, State
from spade.message import Message
from spade.presence import PresenceNotFound

from ontologia.ontologia import (
    ONTOLOGIA,
    crear_cuerpo_game_report_request,
    obtener_conversation_id,
    obtener_performativa,
    validar_cuerpo,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  CONSTANTES — Nombres de estados, timeout y tipos de evento del log
# ═══════════════════════════════════════════════════════════════════════════

# Timeout en segundos para esperar la respuesta del tablero
# (coherente con el CASO C del diagrama de protocolo)
TIMEOUT_RESPUESTA = 10

# Número máximo de FSMs de solicitud de informe que pueden
# ejecutarse simultáneamente. Los tableros que finalizan
# mientras se alcanza el límite se encolan y se procesan
# conforme los FSMs activos terminan.
MAX_FSM_CONCURRENTES = 15

# Traducciones de las razones de la ontología a textos legibles
# en español para los mensajes del log del dashboard.
_RAZONES_LEGIBLES = {
    "both-timeout": "ambos sin respuesta",
    "timeout": "sin respuesta",
    "invalid": "movimiento no válido",
    "not-finished": "partida no finalizada",
}

# Nombres de los estados del FSM (usados como identificadores)
ST_ENVIAR_REQUEST = "ENVIAR_REQUEST"
ST_ESPERAR_RESPUESTA = "ESPERAR_RESPUESTA"
ST_ESPERAR_INFORME = "ESPERAR_INFORME"
ST_PROCESAR_INFORME = "PROCESAR_INFORME"
ST_PROCESAR_RECHAZO = "PROCESAR_RECHAZO"
ST_REGISTRAR_TIMEOUT = "REGISTRAR_TIMEOUT"
ST_REINTENTAR = "REINTENTAR"

# Número máximo de reintentos tras un timeout antes de darlo
# por definitivo. Configurable desde config_parametros.
MAX_REINTENTOS = 2

# Factor multiplicador para el retroceso exponencial.
# Espera = timeout_base × FACTOR_RETROCESO^(intento - 1).
# Con timeout_base=10 s: 10 s → 20 s → 40 s.
FACTOR_RETROCESO = 2

# ── Tipos de evento del log del supervisor ───────────────────
# Cada constante corresponde a una entrada en la leyenda del
# dashboard (icono + etiqueta + color definidos en supervisor.js,
# función obtenerConfigLog).

# Eventos de presencia MUC
LOG_ENTRADA = "entrada"       # ⊕  Agente se une a la sala
LOG_SALIDA = "salida"         # ⊖  Agente abandona la sala
LOG_PRESENCIA = "presencia"   # ↔  Cambio de estado del tablero

# Eventos del protocolo de solicitud de informes
LOG_SOLICITUD = "solicitud"   # ▸  Informe de partida solicitado
LOG_INFORME = "informe"       # ★  Informe válido recibido
LOG_ABORTADA = "abortada"     # ⚠  Partida abortada recibida
LOG_TIMEOUT = "timeout"       # ⏱  Sin respuesta en el plazo

# Error — El tablero no ha comunicado correctamente el informe.
#   Causas: el cuerpo del mensaje no es JSON válido, el informe
#   no cumple el esquema de la ontología, o el tablero abandonó
#   la sala con un informe solicitado sin entregar.
LOG_ERROR = "error"           # ✖  Fallo en la comunicación

# Advertencia — El informe solicitado no se ha recibido, pero
#   no por un fallo del tablero al comunicar, sino porque el
#   tablero lo rechazó (REFUSE) o porque el supervisor finalizó
#   antes de que el tablero pudiera responder. El detalle del
#   evento identifica el informe implicado para su trazabilidad.
LOG_ADVERTENCIA = "advertencia"  # ⚑  Informe no recibido

# Inconsistencia — Validación semántica cruzada del informe.
#   El informe cumple el esquema de la ontología pero presenta
#   anomalías que indican un posible error en el tablero emisor:
#   jugadores no observados en la sala, turnos imposibles, tablero
#   sin línea ganadora cuando el resultado es victoria, jugador
#   contra sí mismo, o informe duplicado.
LOG_INCONSISTENCIA = "inconsistencia"  # ⚐  Anomalía semántica

# ── Constantes de validación semántica del tablero ──────────

# Turnos mínimos para una victoria en Tic-Tac-Toe: X necesita
# al menos 3 fichas y O al menos 2 → mínimo 5 movimientos.
MIN_TURNOS_VICTORIA = 5

# Turnos máximos posibles: 9 celdas en el tablero.
MAX_TURNOS = 9

# Diferencia máxima permitida entre fichas X y O en un tablero
# válido. Como los jugadores alternan turnos, la diferencia nunca
# puede superar 1 (el primer jugador tiene a lo sumo 1 ficha más).
DIFERENCIA_MAXIMA_FICHAS = 1

# Ficha que mueve primero según la convención del sistema.
# El primer jugador recibe "X" (README.md, líneas 792-793).
FICHA_PRIMERA = "X"

# Combinaciones ganadoras del Tic-Tac-Toe: índices de las 8
# líneas posibles (3 filas + 3 columnas + 2 diagonales).
COMBINACIONES_GANADORAS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # filas
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columnas
    (0, 4, 8), (2, 4, 6),             # diagonales
]


# ═══════════════════════════════════════════════════════════════════════════
#  MonitorizarMUCBehaviour
# ═══════════════════════════════════════════════════════════════════════════

class MonitorizarMUCBehaviour(PeriodicBehaviour):
    """Registra periódicamente el estado de ocupantes de las salas MUC.

    La lista de ocupantes se mantiene actualizada en tiempo real
    mediante el handler de presencia MUC del agente (``_on_presencia_muc``).
    Este behaviour solo registra un resumen periódico en el log
    para depuración y mantiene el heartbeat del dashboard.
    """

    async def run(self) -> None:
        """Registra el número de ocupantes por sala en el log."""
        for sala in self.agent.salas_muc:
            sala_id = sala["id"]
            ocupantes = self.agent.ocupantes_por_sala.get(sala_id, [])
            logger.debug(
                "Sala %s: %d ocupante(s)",
                sala_id, len(ocupantes),
            )


# ═══════════════════════════════════════════════════════════════════════════
#  SolicitarInformeFSM — Máquina de estados del protocolo FIPA-Request
# ═══════════════════════════════════════════════════════════════════════════

class SolicitarInformeFSM(FSMBehaviour):
    """FSM que gestiona el protocolo FIPA-Request para un tablero.

    Cada instancia se crea dinámicamente cuando el callback de
    presencia detecta un tablero con ``status="finished"``.

    Estados::

        ENVIAR_REQUEST ──────▸ ESPERAR_RESPUESTA
                                  │
                         ┌────────┼────────┬──────────┐
                         ▼        ▼        ▼          ▼
                    ESPERAR    PROCESAR  PROCESAR   REGISTRAR
                    INFORME   INFORME   RECHAZO    TIMEOUT
                       │         ·         ·          ·
                  ┌────┼────┐  (fin)     (fin)      (fin)
                  ▼    ▼    ▼
              PROCESAR PROCESAR REGISTRAR
              INFORME  RECHAZO  TIMEOUT
                ·        ·        ·
              (fin)    (fin)    (fin)

    Los estados finales (sin transición de salida) provocan la
    autodestrucción del FSM.

    Atributos compartidos entre estados:
        ctx (dict): Contexto compartido con las claves:
            - ``jid_tablero``: JID del tablero objetivo.
            - ``sala_id``: ID de la sala MUC del tablero.
            - ``hilo``: Thread único para correlacionar mensajes.
            - ``mensaje``: Último mensaje recibido (rellenado por
              los estados de espera).
    """

    def __init__(
        self, jid_tablero: str, sala_id: str, hilo: str,
        timeout: int = TIMEOUT_RESPUESTA,
        max_reintentos: int = MAX_REINTENTOS,
    ):
        """Crea el FSM con su contexto compartido.

        Los atributos se asignan ANTES de llamar a ``super().__init__()``
        porque este invoca ``setup()``, que necesita acceder al contexto.

        Args:
            jid_tablero: JID completo del tablero objetivo.
            sala_id: Identificador de la sala MUC.
            hilo: Thread único para correlacionar solicitud y respuesta.
            timeout: Segundos de espera para la respuesta del tablero
                (por defecto ``TIMEOUT_RESPUESTA``). Configurable
                desde ``config_parametros["timeout_respuesta"]``.
            max_reintentos: Número máximo de reintentos tras timeout
                (por defecto ``MAX_REINTENTOS``). Configurable
                desde ``config_parametros["max_reintentos"]``.
        """
        # Contexto compartido entre todos los estados del FSM.
        # Los estados leen jid_tablero/sala_id/hilo y escriben
        # en 'mensaje' para pasar datos al siguiente estado.
        self.ctx = {
            "jid_tablero": jid_tablero,
            "sala_id": sala_id,
            "hilo": hilo,
            "mensaje": None,
            "timeout": timeout,
            "max_reintentos": max_reintentos,
            "reintentos": 0,
        }
        super().__init__()

    def setup(self) -> None:
        """Registra los estados y las transiciones del FSM."""
        # ── Crear instancias de cada estado ──────────────────────
        estado_enviar = EstadoEnviarRequest()
        estado_esperar_resp = EstadoEsperarRespuesta()
        estado_esperar_inf = EstadoEsperarInforme()
        estado_procesar_inf = EstadoProcesarInforme()
        estado_procesar_rech = EstadoProcesarRechazo()
        estado_registrar_to = EstadoRegistrarTimeout()
        estado_reintentar = EstadoReintentar()

        # Inyectar el contexto compartido en cada estado
        for estado in (
            estado_enviar, estado_esperar_resp, estado_esperar_inf,
            estado_procesar_inf, estado_procesar_rech,
            estado_registrar_to, estado_reintentar,
        ):
            estado.ctx = self.ctx

        # ── Registrar estados ────────────────────────────────────
        self.add_state(ST_ENVIAR_REQUEST, estado_enviar, initial=True)
        self.add_state(ST_ESPERAR_RESPUESTA, estado_esperar_resp)
        self.add_state(ST_ESPERAR_INFORME, estado_esperar_inf)
        self.add_state(ST_PROCESAR_INFORME, estado_procesar_inf)
        self.add_state(ST_PROCESAR_RECHAZO, estado_procesar_rech)
        self.add_state(ST_REGISTRAR_TIMEOUT, estado_registrar_to)
        self.add_state(ST_REINTENTAR, estado_reintentar)

        # ── Registrar transiciones ───────────────────────────────
        # Paso 1 → Esperar primera respuesta
        self.add_transition(ST_ENVIAR_REQUEST, ST_ESPERAR_RESPUESTA)

        # Primera respuesta: 4 posibles destinos
        self.add_transition(ST_ESPERAR_RESPUESTA, ST_ESPERAR_INFORME)
        self.add_transition(ST_ESPERAR_RESPUESTA, ST_PROCESAR_INFORME)
        self.add_transition(ST_ESPERAR_RESPUESTA, ST_PROCESAR_RECHAZO)
        self.add_transition(ST_ESPERAR_RESPUESTA, ST_REGISTRAR_TIMEOUT)

        # Segunda respuesta (tras AGREE): solo INFORM o timeout.
        # REFUSE no es posible tras AGREE (el tablero ya aceptó).
        self.add_transition(ST_ESPERAR_INFORME, ST_PROCESAR_INFORME)
        self.add_transition(ST_ESPERAR_INFORME, ST_REGISTRAR_TIMEOUT)

        # Reintento: REGISTRAR_TIMEOUT puede transicionar a
        # REINTENTAR si quedan reintentos disponibles.
        self.add_transition(ST_REGISTRAR_TIMEOUT, ST_REINTENTAR)

        # Desde REINTENTAR se vuelve a enviar el REQUEST y se
        # espera la respuesta con las mismas transiciones.
        self.add_transition(ST_REINTENTAR, ST_ESPERAR_RESPUESTA)


# ═══════════════════════════════════════════════════════════════════════════
#  ESTADOS DEL FSM
# ═══════════════════════════════════════════════════════════════════════════

class EstadoEnviarRequest(State):
    """Estado inicial: envía REQUEST game-report al tablero (paso 1)."""

    async def run(self) -> None:
        """Construye y envía el mensaje REQUEST."""
        jid_tablero = self.ctx["jid_tablero"]
        hilo = self.ctx["hilo"]

        mensaje = Message(to=jid_tablero)
        mensaje.set_metadata("ontology", ONTOLOGIA)
        mensaje.set_metadata(
            "performative", obtener_performativa("game-report"),
        )
        mensaje.set_metadata(
            "conversation-id",
            obtener_conversation_id("game-report"),
        )
        mensaje.thread = hilo
        mensaje.body = crear_cuerpo_game_report_request()

        await self.send(mensaje)

        sala_id = self.ctx["sala_id"]
        logger.info(
            "REQUEST game-report enviado a %s [sala: %s] (thread: %s)",
            jid_tablero, sala_id, hilo,
        )

        # Registrar la solicitud en el log del dashboard
        nick_tablero = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]
        self.agent.registrar_evento_log(
            LOG_SOLICITUD, nick_tablero,
            "Informe de partida solicitado",
            sala_id,
        )

        self.set_next_state(ST_ESPERAR_RESPUESTA)


class EstadoEsperarRespuesta(State):
    """Espera la primera respuesta del tablero tras el REQUEST.

    Transiciones posibles:
        - ``agree``   → ESPERAR_INFORME (esperar segunda respuesta)
        - ``inform``  → PROCESAR_INFORME (respuesta directa sin AGREE)
        - ``refuse``  → PROCESAR_RECHAZO
        - timeout     → REGISTRAR_TIMEOUT
    """

    async def run(self) -> None:
        """Espera y clasifica la primera respuesta."""
        respuesta = await self.receive(timeout=self.ctx["timeout"])

        if respuesta is None:
            self.set_next_state(ST_REGISTRAR_TIMEOUT)
        else:
            performativa = respuesta.get_metadata("performative")

            if performativa == "agree":
                logger.debug(
                    "AGREE recibido de %s, esperando informe...",
                    self.ctx["jid_tablero"],
                )
                self.set_next_state(ST_ESPERAR_INFORME)
            elif performativa == "inform":
                self.ctx["mensaje"] = respuesta
                self.set_next_state(ST_PROCESAR_INFORME)
            elif performativa == "refuse":
                self.ctx["mensaje"] = respuesta
                self.set_next_state(ST_PROCESAR_RECHAZO)
            else:
                logger.warning(
                    "Respuesta inesperada de %s: performativa '%s'",
                    self.ctx["jid_tablero"], performativa,
                )
                self.set_next_state(ST_REGISTRAR_TIMEOUT)


class EstadoEsperarInforme(State):
    """Espera la segunda respuesta tras haber recibido AGREE.

    Tras un AGREE el tablero se ha comprometido a responder con
    un INFORM. REFUSE no es posible en este punto del protocolo.

    Transiciones posibles:
        - ``inform``  → PROCESAR_INFORME
        - timeout     → REGISTRAR_TIMEOUT
    """

    async def run(self) -> None:
        """Espera el INFORM tras AGREE."""
        respuesta = await self.receive(timeout=self.ctx["timeout"])

        if respuesta is None:
            self.set_next_state(ST_REGISTRAR_TIMEOUT)
        else:
            performativa = respuesta.get_metadata("performative")

            if performativa == "inform":
                self.ctx["mensaje"] = respuesta
                self.set_next_state(ST_PROCESAR_INFORME)
            else:
                logger.warning(
                    "Respuesta inesperada tras AGREE de %s: '%s' "
                    "(se esperaba INFORM)",
                    self.ctx["jid_tablero"], performativa,
                )
                self.set_next_state(ST_REGISTRAR_TIMEOUT)


class EstadoProcesarInforme(State):
    """Estado final: valida y almacena el informe (CASO A / A2).

    No llama a ``set_next_state()`` → el FSM se autodestruye.
    """

    async def run(self) -> None:
        """Parsea, valida y almacena el informe recibido."""
        mensaje = self.ctx["mensaje"]
        sala_id = self.ctx["sala_id"]
        # Usar el JID del tablero del contexto del FSM en lugar de
        # mensaje.sender, porque el sender es el JID real del agente
        # (con recurso aleatorio), mientras que jid_tablero contiene
        # el JID MUC con el nick legible del tablero.
        jid_tablero = self.ctx["jid_tablero"]

        nick_tablero = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]

        try:
            cuerpo = json.loads(mensaje.body)
        except (json.JSONDecodeError, TypeError) as error:
            logger.error(
                "Error al parsear informe de %s: %s",
                jid_tablero, error,
            )
            self.agent.registrar_evento_log(
                LOG_ERROR, nick_tablero,
                f"El cuerpo del mensaje no es JSON válido "
                f"({error})",
                sala_id,
            )
            self.agent.informes_pendientes.pop(
                jid_tablero, None,
            )
            self.agent.tableros_consultados.discard(
                jid_tablero,
            )
            self.agent.solicitar_siguiente_en_cola()
            return

        resultado_validacion = validar_cuerpo(cuerpo)

        if resultado_validacion["valido"]:
            if sala_id not in self.agent.informes_por_sala:
                self.agent.informes_por_sala[sala_id] = {}

            if jid_tablero not in \
                    self.agent.informes_por_sala[sala_id]:
                self.agent.informes_por_sala[sala_id][
                    jid_tablero
                ] = []
            self.agent.informes_por_sala[sala_id][
                jid_tablero
            ].append(cuerpo)

            # Persistir en SQLite
            if hasattr(self.agent, "almacen") \
                    and self.agent.almacen is not None:
                self.agent.almacen.guardar_informe(
                    sala_id, jid_tablero, cuerpo,
                )

            resultado = cuerpo.get("result", "?")
            ganador = cuerpo.get("winner", "ninguno")
            turnos = cuerpo.get("turns", 0)

            logger.info(
                "Informe recibido de %s [sala: %s] — resultado: %s, "
                "ganador: %s, turnos: %d",
                jid_tablero, sala_id, resultado, ganador, turnos,
            )

            tipo_log = LOG_ABORTADA if resultado == "aborted" \
                else LOG_INFORME
            detalle = _construir_detalle_informe(cuerpo)
            self.agent.registrar_evento_log(
                tipo_log, nick_tablero, detalle, sala_id,
            )

            # ── Validación semántica cruzada ────────────────
            # Detectar anomalías que el esquema de la ontología
            # no puede capturar: turnos imposibles, tablero sin
            # línea ganadora, jugadores no observados, etc.
            hilo = self.ctx["hilo"]
            observados = \
                self.agent.ocupantes_historicos_por_sala.get(
                    sala_id, set(),
                )
            threads_procesados = \
                self.agent.threads_procesados_por_sala.get(
                    sala_id, set(),
                )

            anomalias = validar_semantica_informe(
                cuerpo, observados, hilo, threads_procesados,
            )

            # Registrar thread como procesado DESPUÉS de la
            # validación para que no se detecte a sí mismo
            # como duplicado (P-05).
            self.agent.threads_procesados_por_sala.setdefault(
                sala_id, set(),
            ).add(hilo)

            for anomalia in anomalias:
                logger.warning(
                    "Inconsistencia en informe de %s [sala: %s]: "
                    "%s", jid_tablero, sala_id, anomalia,
                )
                self.agent.registrar_evento_log(
                    LOG_INCONSISTENCIA, nick_tablero,
                    anomalia, sala_id,
                )
        else:
            errores_str = "; ".join(
                resultado_validacion["errores"],
            )
            logger.warning(
                "Informe de %s no válido: %s",
                jid_tablero,
                resultado_validacion["errores"],
            )
            self.agent.registrar_evento_log(
                LOG_ERROR, nick_tablero,
                f"El informe no cumple el esquema de la "
                f"ontología: {errores_str}",
                sala_id,
            )

        self.agent.informes_pendientes.pop(jid_tablero, None)
        self.agent.tableros_consultados.discard(jid_tablero)
        self.agent.solicitar_siguiente_en_cola()
        # Estado final: no se llama a set_next_state() → FSM termina


class EstadoProcesarRechazo(State):
    """Estado final: procesa REFUSE del tablero (CASO B).

    Registra la razón del rechazo en el log y desbloquea el
    tablero de ``tableros_consultados`` para que una futura
    partida pueda ser detectada (S-01).
    No llama a ``set_next_state()`` → el FSM se autodestruye.
    """

    async def run(self) -> None:
        """Extrae y registra la razón del rechazo."""
        mensaje = self.ctx["mensaje"]
        jid_tablero = self.ctx["jid_tablero"]
        sala_id = self.ctx["sala_id"]

        try:
            cuerpo = json.loads(mensaje.body)
            razon = cuerpo.get("reason", "desconocida")
        except (json.JSONDecodeError, TypeError):
            razon = "desconocida"

        razon_legible = _RAZONES_LEGIBLES.get(razon, razon)

        logger.info(
            "Tablero %s rechazó la solicitud de informe: %s",
            jid_tablero, razon,
        )

        nick_tablero = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]
        self.agent.registrar_evento_log(
            LOG_ADVERTENCIA, nick_tablero,
            f"El tablero rechazó enviar el informe "
            f"(motivo: {razon_legible})",
            sala_id,
        )

        self.agent.informes_pendientes.pop(jid_tablero, None)
        self.agent.tableros_consultados.discard(jid_tablero)
        self.agent.solicitar_siguiente_en_cola()
        # Estado final: no se llama a set_next_state() → FSM termina


class EstadoRegistrarTimeout(State):
    """Registra incidencia de timeout (CASO C).

    Si quedan reintentos disponibles, transiciona a
    ``ST_REINTENTAR`` para volver a solicitar el informe con
    retroceso exponencial. Si se han agotado los reintentos,
    no llama a ``set_next_state()`` → el FSM se autodestruye.
    """

    async def run(self) -> None:
        """Registra el timeout y decide si reintentar."""
        jid_tablero = self.ctx["jid_tablero"]
        sala_id = self.ctx["sala_id"]
        timeout = self.ctx["timeout"]
        reintentos = self.ctx.get("reintentos", 0)
        max_reintentos = self.ctx.get("max_reintentos", 0)

        nick_tablero = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]

        if reintentos < max_reintentos:
            # Quedan reintentos: registrar el timeout parcial
            # y transicionar al estado de reintento
            logger.warning(
                "Timeout esperando informe de %s [sala: %s] "
                "(%d s) — reintento %d/%d",
                jid_tablero, sala_id, timeout,
                reintentos + 1, max_reintentos,
            )
            self.agent.registrar_evento_log(
                LOG_TIMEOUT, nick_tablero,
                f"Sin respuesta tras {timeout} s "
                f"(reintento {reintentos + 1}/{max_reintentos})",
                sala_id,
            )
            self.set_next_state(ST_REINTENTAR)
        else:
            # Reintentos agotados: timeout definitivo
            logger.warning(
                "Timeout definitivo esperando informe de %s "
                "[sala: %s] (%d s sin respuesta, %d reintentos "
                "agotados)",
                jid_tablero, sala_id, timeout, max_reintentos,
            )
            self.agent.registrar_evento_log(
                LOG_TIMEOUT, nick_tablero,
                f"Sin respuesta tras {timeout} s "
                f"(reintentos agotados: {max_reintentos})",
                sala_id,
            )
            self.agent.informes_pendientes.pop(
                jid_tablero, None,
            )
            self.agent.tableros_consultados.discard(
                jid_tablero,
            )
            self.agent.solicitar_siguiente_en_cola()
            # Estado final: FSM termina


class EstadoReintentar(State):
    """Espera con retroceso exponencial y reenvía el REQUEST.

    El intervalo de espera crece exponencialmente con cada
    reintento: ``timeout × FACTOR_RETROCESO^reintentos``.
    Con timeout=10 s y factor=2: 10 s, 20 s, 40 s.

    Tras la espera, incrementa el contador de reintentos, reenvía
    el REQUEST y transiciona a ``ST_ESPERAR_RESPUESTA``.

    Se registran dos eventos en el log:
    - ``LOG_ADVERTENCIA``: para que aparezca en la pestaña de
      Incidencias indicando que hubo un timeout previo.
    - ``LOG_SOLICITUD``: la nueva solicitud de informe.
    """

    async def run(self) -> None:
        """Espera con retroceso exponencial y reenvía REQUEST."""
        jid_tablero = self.ctx["jid_tablero"]
        sala_id = self.ctx["sala_id"]
        hilo = self.ctx["hilo"]
        reintentos = self.ctx.get("reintentos", 0)
        timeout_base = self.ctx["timeout"]

        # Calcular la espera con retroceso exponencial
        espera = timeout_base * (FACTOR_RETROCESO ** reintentos)

        nick_tablero = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]

        logger.info(
            "Reintento %d para %s [sala: %s] — "
            "esperando %d s antes de reenviar",
            reintentos + 1, jid_tablero, sala_id, espera,
        )

        # Registrar advertencia en la pestaña de Incidencias
        self.agent.registrar_evento_log(
            LOG_ADVERTENCIA, nick_tablero,
            f"Reintento {reintentos + 1}: esperando {espera} s "
            f"antes de volver a solicitar el informe",
            sala_id,
        )

        # Esperar con retroceso exponencial
        await asyncio.sleep(espera)

        # Incrementar el contador de reintentos
        self.ctx["reintentos"] = reintentos + 1

        # Reenviar el REQUEST
        mensaje = Message(to=jid_tablero)
        mensaje.set_metadata("ontology", ONTOLOGIA)
        mensaje.set_metadata(
            "performative", obtener_performativa("game-report"),
        )
        mensaje.set_metadata(
            "conversation-id",
            obtener_conversation_id("game-report"),
        )
        mensaje.thread = hilo
        mensaje.body = crear_cuerpo_game_report_request()

        await self.send(mensaje)

        logger.info(
            "REQUEST game-report reenviado a %s [sala: %s] "
            "(reintento %d, thread: %s)",
            jid_tablero, sala_id, reintentos + 1, hilo,
        )

        # Registrar la nueva solicitud en el log
        self.agent.registrar_evento_log(
            LOG_SOLICITUD, nick_tablero,
            f"Informe de partida solicitado "
            f"(reintento {reintentos + 1})",
            sala_id,
        )

        self.set_next_state(ST_ESPERAR_RESPUESTA)


# ═══════════════════════════════════════════════════════════════════════════
#  FUNCIONES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════

def _obtener_estado_contacto(contacto) -> str:
    """Extrae el campo ``status`` de la presencia actual de un contacto SPADE.

    En SPADE 4.x, ``get_contacts()`` devuelve objetos ``Contact`` cuya
    presencia se obtiene mediante ``get_presence()``, que devuelve un
    ``PresenceInfo`` con los atributos ``.status``, ``.show`` y ``.type``.

    Si el contacto aún no tiene presencia disponible (acaba de
    suscribirse y no ha respondido), se devuelve ``"online"`` como
    valor por defecto.

    Args:
        contacto: Objeto ``Contact`` de ``spade.presence``.

    Returns:
        Cadena con el estado de presencia (por ejemplo ``"finished"``
        o ``"online"``).
    """
    estado = "online"
    try:
        presencia = contacto.get_presence()
        estado = presencia.status or "online"
    except PresenceNotFound:
        estado = "online"

    return estado


def _determinar_rol(nick: str) -> str:
    """Determina el rol de un ocupante MUC a partir de su apodo.

    Args:
        nick: Apodo del ocupante en la sala MUC.

    Returns:
        Rol del ocupante: ``tablero``, ``jugador`` o ``supervisor``.
    """
    resultado = "jugador"
    if nick.startswith("tablero_"):
        resultado = "tablero"
    elif nick == "supervisor":
        resultado = "supervisor"

    return resultado


def _construir_detalle_informe(cuerpo: dict) -> str:
    """Construye una descripción legible de un informe de partida.

    Se usa para el log de eventos del dashboard. Genera textos como:
    ``Victoria de X (abc001) contra def002 · 7 turnos``

    Args:
        cuerpo: Cuerpo del informe (dict con campos de la ontología).

    Returns:
        Cadena descriptiva del resultado de la partida.
    """
    resultado = cuerpo.get("result", "?")
    turnos = cuerpo.get("turns", 0)
    jugadores = cuerpo.get("players", {})
    jid_x = jugadores.get("X", "?")
    jid_o = jugadores.get("O", "?")

    alumno_x = jid_x.split("@")[0].replace("jugador_", "")
    alumno_o = jid_o.split("@")[0].replace("jugador_", "")

    detalle = (
        f"{resultado} · {alumno_x} contra {alumno_o} "
        f"· {turnos} turnos"
    )

    if resultado == "win":
        ganador = cuerpo.get("winner", "?")
        alumno_ganador = alumno_x if ganador == "X" else alumno_o
        alumno_rival = alumno_o if ganador == "X" else alumno_x
        detalle = (
            f"Victoria de {ganador} ({alumno_ganador}) "
            f"contra {alumno_rival} · {turnos} turnos"
        )
    elif resultado == "draw":
        detalle = (
            f"Empate · {alumno_x} contra {alumno_o} "
            f"· {turnos} turnos"
        )
    elif resultado == "aborted":
        reason = cuerpo.get("reason", "")
        razon_legible = _RAZONES_LEGIBLES.get(reason, reason)
        detalle = (
            f"Abortada ({razon_legible}) · {alumno_x} contra "
            f"{alumno_o} · {turnos} turnos"
        )

    return detalle


# ═══════════════════════════════════════════════════════════════════════════
#  VALIDACIONES SEMÁNTICAS DEL INFORME
# ═══════════════════════════════════════════════════════════════════════════
# Estas validaciones se ejecutan DESPUÉS de que el informe haya pasado
# la validación de esquema de la ontología. Detectan anomalías lógicas
# que el esquema no puede capturar: turnos imposibles, tablero que no
# corresponde con el resultado, jugadores fantasma, etc.
#
# Cada función recibe el cuerpo del informe (y opcionalmente el estado
# del agente) y devuelve una lista de cadenas con las anomalías
# detectadas. Una lista vacía significa que no hay inconsistencias.

def _validar_turnos(cuerpo: dict) -> list[str]:
    """Verifica que el número de turnos es coherente con el resultado.

    Reglas:
    - Una victoria requiere al menos MIN_TURNOS_VICTORIA (5) turnos.
    - Un empate requiere exactamente MAX_TURNOS (9) turnos (tablero
      lleno). Si se reporta empate con menos turnos, es una
      inconsistencia.
    - Ninguna partida puede exceder MAX_TURNOS (9) turnos.

    Args:
        cuerpo: Cuerpo del informe validado por la ontología.

    Returns:
        Lista de anomalías detectadas (vacía si todo es correcto).
    """
    anomalias = []
    turnos = cuerpo.get("turns", 0)
    resultado = cuerpo.get("result", "")

    if resultado == "win" and turnos < MIN_TURNOS_VICTORIA:
        anomalias.append(
            f"Victoria declarada con solo {turnos} turnos "
            f"(mínimo posible: {MIN_TURNOS_VICTORIA})",
        )

    if resultado == "draw" and turnos < MAX_TURNOS:
        anomalias.append(
            f"Empate declarado con solo {turnos} turnos "
            f"(un empate requiere {MAX_TURNOS} movimientos)",
        )

    if turnos > MAX_TURNOS:
        anomalias.append(
            f"Se reportan {turnos} turnos (máximo posible: "
            f"{MAX_TURNOS})",
        )

    return anomalias


def _validar_tablero_resultado(cuerpo: dict) -> list[str]:
    """Verifica coherencia entre el estado del tablero y el resultado.

    Reglas existentes (V5, V6):
    - Si result='win', debe existir una línea ganadora con la ficha
      del winner en el tablero (V5).
    - Si result='draw', no debe haber celdas vacías (tablero lleno)
      y no debe haber línea ganadora (V4, V6).

    Reglas añadidas (V8-V11, aplican a win y draw):
    - V8/V10: la diferencia entre fichas X y O no puede superar
      ``DIFERENCIA_MAXIMA_FICHAS`` (1).
    - V9: el total de fichas en el tablero debe coincidir con
      ``turns``.
    - V11: X mueve primero → ``num_x >= num_o`` siempre.

    Args:
        cuerpo: Cuerpo del informe validado por la ontología.

    Returns:
        Lista de anomalías detectadas.
    """
    anomalias = []
    resultado = cuerpo.get("result", "")
    tablero = cuerpo.get("board", [])
    ganador = cuerpo.get("winner", None)
    turnos = cuerpo.get("turns", 0)

    # Solo validar si el tablero tiene 9 celdas
    if len(tablero) != MAX_TURNOS:
        return anomalias

    # ── V5: línea ganadora en victoria ───────────────────────
    if resultado == "win" and ganador in ("X", "O"):
        tiene_linea = _hay_linea_ganadora(tablero, ganador)
        if not tiene_linea:
            anomalias.append(
                f"Victoria de {ganador} declarada pero no hay "
                f"línea ganadora en el tablero",
            )

    # ── V4, V6: celdas vacías y línea oculta en empate ──────
    if resultado == "draw":
        celdas_vacias = tablero.count("") + tablero.count(None)
        if celdas_vacias > 0:
            anomalias.append(
                f"Empate declarado pero el tablero tiene "
                f"{celdas_vacias} celda(s) vacía(s)",
            )
        # Verificar que no hay línea ganadora oculta
        hay_ganador_x = _hay_linea_ganadora(tablero, "X")
        hay_ganador_o = _hay_linea_ganadora(tablero, "O")
        if hay_ganador_x or hay_ganador_o:
            ficha = "X" if hay_ganador_x else "O"
            anomalias.append(
                f"Empate declarado pero existe línea ganadora "
                f"de {ficha} en el tablero",
            )

    # ── V8/V9/V10/V11: coherencia de fichas (win y draw) ────
    # No aplica a partidas abortadas porque el estado del tablero
    # puede ser inconsistente si la partida se interrumpió.
    # Solo se evalúa si el informe incluye el campo 'turns'
    # (los informes validados por la ontología siempre lo incluyen;
    # esta guarda protege tests unitarios que construyen cuerpos
    # parciales para probar otras validaciones).
    if resultado in ("win", "draw") and "turns" in cuerpo:
        num_x = tablero.count("X")
        num_o = tablero.count("O")
        num_fichas = num_x + num_o

        # V9: el total de fichas debe coincidir con turns
        if num_fichas != turnos:
            anomalias.append(
                f"El tablero contiene {num_fichas} fichas "
                f"pero se reportan {turnos} turnos",
            )

        # V8/V10: la diferencia entre fichas no puede superar 1
        if abs(num_x - num_o) > DIFERENCIA_MAXIMA_FICHAS:
            anomalias.append(
                f"Distribución de fichas imposible: "
                f"{num_x} X y {num_o} O (diferencia máxima "
                f"permitida: {DIFERENCIA_MAXIMA_FICHAS})",
            )

        # V11: X mueve primero → siempre tiene >= fichas que O
        if num_x < num_o:
            anomalias.append(
                f"{FICHA_PRIMERA} mueve primero pero tiene "
                f"menos fichas que O: {num_x} X y {num_o} O",
            )

    return anomalias


def _hay_linea_ganadora(tablero: list, ficha: str) -> bool:
    """Comprueba si existe una línea ganadora de la ficha dada.

    Args:
        tablero: Lista de 9 celdas del tablero.
        ficha: Ficha a buscar ('X' o 'O').

    Returns:
        True si existe al menos una combinación ganadora.
    """
    encontrada = False
    i = 0
    while i < len(COMBINACIONES_GANADORAS) and not encontrada:
        a, b, c = COMBINACIONES_GANADORAS[i]
        if tablero[a] == ficha \
                and tablero[b] == ficha \
                and tablero[c] == ficha:
            encontrada = True
        i += 1

    return encontrada


def _validar_jugador_contra_si_mismo(cuerpo: dict) -> list[str]:
    """Detecta si ambos jugadores son el mismo agente.

    Args:
        cuerpo: Cuerpo del informe validado por la ontología.

    Returns:
        Lista con una anomalía si players.X == players.O.
    """
    anomalias = []
    jugadores = cuerpo.get("players", {})
    jid_x = jugadores.get("X", "")
    jid_o = jugadores.get("O", "")

    if jid_x and jid_o and jid_x == jid_o:
        anomalias.append(
            f"Ambos jugadores son el mismo agente: {jid_x}",
        )

    return anomalias


def _validar_jugadores_observados(
    cuerpo: dict, observados: set[str],
) -> list[str]:
    """Compara los jugadores del informe con el histórico de
    ocupantes observados en la sala (P-04).

    Usa el conjunto histórico (JIDs + nicks acumulados durante
    toda la ejecución) en vez de la foto en tiempo real, para
    evitar falsos positivos cuando un jugador abandona la sala
    antes de que se procese el informe.

    Args:
        cuerpo: Cuerpo del informe validado por la ontología.
        observados: Conjunto de JIDs y nicks que han sido
            observados en la sala en algún momento.

    Returns:
        Lista de anomalías detectadas.
    """
    anomalias = []

    if not observados:
        return anomalias

    jugadores = cuerpo.get("players", {})

    for ficha in ("X", "O"):
        jid_jugador = jugadores.get(ficha, "")
        if not jid_jugador:
            continue

        nick_jugador = jid_jugador.split("@")[0] \
            if "@" in jid_jugador else jid_jugador

        presente = (
            jid_jugador in observados
            or nick_jugador in observados
        )

        if not presente:
            anomalias.append(
                f"Jugador {ficha} ({nick_jugador}) no fue "
                f"observado como ocupante de la sala",
            )

    return anomalias


def _validar_informe_duplicado(
    hilo: str, threads_procesados: set[str],
) -> list[str]:
    """Detecta si el informe es un duplicado por thread (P-05).

    Un informe es duplicado si ya se procesó otro informe para la
    misma solicitud (mismo thread). Dos partidas distintas con
    contenido idéntico pero threads distintos NO son duplicados.

    Args:
        hilo: Thread de la solicitud actual del FSM.
        threads_procesados: Threads ya procesados en la sala.

    Returns:
        Lista con una anomalía si se detecta duplicado.
    """
    anomalias = []
    if hilo in threads_procesados:
        anomalias.append(
            f"Informe duplicado: ya se recibió un informe "
            f"para la solicitud {hilo}",
        )
    return anomalias


def validar_semantica_informe(
    cuerpo: dict,
    observados: set[str] | None = None,
    hilo: str | None = None,
    threads_procesados: set[str] | None = None,
) -> list[str]:
    """Ejecuta todas las validaciones semánticas sobre un informe.

    Agrega los resultados de cada validación individual en una
    única lista de anomalías.

    Args:
        cuerpo: Cuerpo del informe validado por la ontología.
        observados: Conjunto histórico de JIDs y nicks observados
            en la sala (P-04). ``None`` desactiva la validación.
        hilo: Thread de la solicitud que originó este informe.
        threads_procesados: Threads ya procesados en la sala
            (para detección de duplicados por identidad, P-05).

    Returns:
        Lista de todas las anomalías detectadas (vacía si ninguna).
    """
    anomalias = []

    anomalias.extend(_validar_turnos(cuerpo))
    anomalias.extend(_validar_tablero_resultado(cuerpo))
    anomalias.extend(_validar_jugador_contra_si_mismo(cuerpo))

    if observados is not None:
        anomalias.extend(
            _validar_jugadores_observados(cuerpo, observados),
        )

    if hilo is not None and threads_procesados is not None:
        anomalias.extend(
            _validar_informe_duplicado(hilo, threads_procesados),
        )

    return anomalias
