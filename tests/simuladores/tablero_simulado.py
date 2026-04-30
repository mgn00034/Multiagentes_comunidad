"""
Agente tablero simulado para tests de integración.

Imita el comportamiento de un agente tablero real: se une a una
sala MUC, cambia su estado de presencia (waiting → playing →
finished) y responde a las solicitudes ``game-report`` del
supervisor según el modo de respuesta configurado.

Modos de respuesta disponibles:

- ``"victoria"``: INFORM con informe de victoria válido.
- ``"empate"``:   INFORM con informe de empate válido.
- ``"abortada"``: INFORM con informe de partida abortada.
- ``"refuse"``:   REFUSE con razón ``not-finished``.
- ``"timeout"``:  No responde (el supervisor agota el tiempo).
- ``"json_invalido"``: INFORM con cuerpo que no es JSON válido.
- ``"esquema_invalido"``: INFORM con JSON válido pero que no
  cumple el esquema de la ontología (campos obligatorios ausentes).
- ``"agree_luego_inform"``: AGREE seguido de INFORM (protocolo
  de dos pasos).
- ``"abortada_timeout_llm"``: INFORM con partida abortada porque
  un jugador con estrategia LLM no respondió a tiempo
  (``reason: "timeout"``, gana el rival).
- ``"abortada_movimiento_invalido"``: INFORM con partida abortada
  porque el LLM generó un movimiento inválido
  (``reason: "invalid"``, gana el rival).

Uso::

    tablero = crear_agente(TableroSimulado, "tablero_t1", cfg)
    tablero.nick = "tablero_mesa1"
    tablero.sala_jid = "test_sala@conference.localhost"
    tablero.modo_respuesta = "victoria"
    await arrancar_agente(tablero, cfg)
    await tablero.cambiar_estado_muc("finished")
"""

import json
import logging
from xml.etree.ElementTree import SubElement

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from ontologia.ontologia import ONTOLOGIA

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Informes de prueba — cumplen el esquema de la ontología
# ═══════════════════════════════════════════════════════════════════

INFORME_VICTORIA = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 7,
    "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
}

INFORME_EMPATE = {
    "action": "game-report",
    "result": "draw",
    "winner": None,
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 9,
    "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
}

INFORME_ABORTADA = {
    "action": "game-report",
    "result": "aborted",
    "winner": None,
    "reason": "both-timeout",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 2,
    "board": ["X", "", "", "", "O", "", "", "", ""],
}

# ── Informes de escenarios LLM ────────────────────────────────
# Simulan partidas donde un jugador usa estrategia LLM (nivel 4)
# y falla por timeout del modelo o por movimiento inválido.

INFORME_ABORTADA_TIMEOUT_LLM = {
    "action": "game-report",
    "result": "aborted",
    "winner": "X",
    "reason": "timeout",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_ia@localhost",
    },
    "turns": 4,
    "board": ["X", "O", "X", "", "O", "", "", "", ""],
}

INFORME_ABORTADA_MOVIMIENTO_INVALIDO = {
    "action": "game-report",
    "result": "aborted",
    "winner": "X",
    "reason": "invalid",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_ia@localhost",
    },
    "turns": 3,
    "board": ["X", "O", "", "", "X", "", "", "", ""],
}

# ── Informes con inconsistencias semánticas ──────────────────
# Pasan la validación de esquema pero tienen anomalías lógicas
# que la validación semántica del supervisor debe detectar.

INFORME_VICTORIA_TURNOS_ANOMALOS = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 2,  # Imposible: mínimo 5 turnos para ganar
    "board": ["X", "X", "X", "", "", "", "", "", ""],
}

INFORME_VICTORIA_SIN_LINEA = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 7,
    "board": ["X", "O", "X", "O", "", "O", "", "", ""],  # Sin línea
}

INFORME_JUGADOR_CONTRA_SI_MISMO = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_ana@localhost",  # Mismo JID
    },
    "turns": 5,
    "board": ["X", "O", "X", "O", "X", "", "", "", ""],
}

INFORME_EMPATE_CON_CELDAS_VACIAS = {
    "action": "game-report",
    "result": "draw",
    "winner": None,
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 7,
    "board": ["X", "O", "X", "O", "X", "O", "O", "", ""],  # Vacía
}

# ── Informes para validaciones V8-V11 (P-07) ────────────────

INFORME_EMPATE_FICHAS_DESEQUILIBRADAS = {
    "action": "game-report",
    "result": "draw",
    "winner": None,
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 9,
    # V8: abs(3-6) = 3 > 1 → distribucion imposible
    "board": ["X", "O", "O", "X", "O", "O", "O", "X", "O"],
}

INFORME_VICTORIA_FICHAS_VS_TURNOS = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 5,
    # V9: 5 turnos pero solo 3 fichas en el tablero
    "board": ["X", "O", "X", "", "", "", "", "", ""],
}

INFORME_EMPATE_O_PRIMERO = {
    "action": "game-report",
    "result": "draw",
    "winner": None,
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 9,
    # V11: 4X+5O indica que O movio primero (deberia ser 5X+4O)
    "board": ["O", "X", "O", "X", "O", "X", "O", "X", "O"],
}

INFORME_VICTORIA_SEGUNDA_IDENTICA = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 7,
    # Mismo contenido que INFORME_VICTORIA pero thread distinto
    "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
}


# Mapa de modo → cuerpo del informe para respuestas válidas
_INFORMES_POR_MODO = {
    "victoria": INFORME_VICTORIA,
    "empate": INFORME_EMPATE,
    "abortada": INFORME_ABORTADA,
    "agree_luego_inform": INFORME_VICTORIA,
    "abortada_timeout_llm": INFORME_ABORTADA_TIMEOUT_LLM,
    "abortada_movimiento_invalido": INFORME_ABORTADA_MOVIMIENTO_INVALIDO,
    "victoria_turnos_anomalos": INFORME_VICTORIA_TURNOS_ANOMALOS,
    "victoria_sin_linea": INFORME_VICTORIA_SIN_LINEA,
    "jugador_contra_si_mismo": INFORME_JUGADOR_CONTRA_SI_MISMO,
    "empate_celdas_vacias": INFORME_EMPATE_CON_CELDAS_VACIAS,
    "empate_fichas_desequilibradas": INFORME_EMPATE_FICHAS_DESEQUILIBRADAS,
    "victoria_fichas_vs_turnos": INFORME_VICTORIA_FICHAS_VS_TURNOS,
    "empate_o_primero": INFORME_EMPATE_O_PRIMERO,
    "victoria_segunda_identica": INFORME_VICTORIA_SEGUNDA_IDENTICA,
}


# ═══════════════════════════════════════════════════════════════════
#  Behaviour: responder a solicitudes game-report
# ═══════════════════════════════════════════════════════════════════

class ResponderGameReportBehaviour(CyclicBehaviour):
    """Escucha solicitudes game-report del supervisor y responde
    según el modo configurado en el agente.

    El modo se lee de ``self.agent.modo_respuesta``. Si el modo
    es ``"timeout"``, el behaviour recibe el mensaje pero no envía
    respuesta alguna (el supervisor agotará el tiempo de espera).
    """

    async def run(self) -> None:
        """Espera un mensaje REQUEST y responde según el modo."""
        mensaje = await self.receive(timeout=30)
        if mensaje is None:
            return

        modo = self.agent.modo_respuesta
        hilo = mensaje.thread
        remitente = str(mensaje.sender)

        logger.info(
            "TableroSimulado '%s' recibió REQUEST de %s "
            "(modo: %s, thread: %s)",
            self.agent.nick, remitente, modo, hilo,
        )

        if modo == "timeout":
            # No responder: el supervisor agotará el tiempo
            return

        if modo == "timeout_luego_victoria":
            # Primera solicitud: no responder (timeout).
            # Siguientes solicitudes: responder con victoria.
            contador = getattr(self.agent, "_contador_requests", 0)
            self.agent._contador_requests = contador + 1
            if contador == 0:
                logger.info(
                    "TableroSimulado '%s' ignora primera "
                    "solicitud (modo timeout_luego_victoria)",
                    self.agent.nick,
                )
                return
            modo = "victoria"

        if modo == "refuse":
            await self._enviar_refuse(remitente, hilo)
            return

        if modo == "json_invalido":
            await self._enviar_inform_raw(
                remitente, hilo, "esto {no es json válido",
            )
            return

        if modo == "esquema_invalido":
            # JSON válido pero sin campos obligatorios
            cuerpo_malo = {"action": "game-report", "result": "win"}
            await self._enviar_inform_raw(
                remitente, hilo, json.dumps(cuerpo_malo),
            )
            return

        if modo == "agree_luego_inform":
            await self._enviar_agree(remitente, hilo)

        # Enviar INFORM con el informe correspondiente
        informe = _INFORMES_POR_MODO.get(modo, INFORME_VICTORIA)
        await self._enviar_inform(remitente, hilo, informe)

    # ── Métodos auxiliares para construir respuestas ──────────

    async def _enviar_inform(
        self, destino: str, hilo: str, cuerpo: dict,
    ) -> None:
        """Envía un INFORM con un informe JSON válido."""
        msg = Message(to=destino)
        msg.set_metadata("ontology", ONTOLOGIA)
        msg.set_metadata("performative", "inform")
        msg.thread = hilo
        msg.body = json.dumps(cuerpo, ensure_ascii=False)
        await self.send(msg)
        logger.debug("INFORM enviado a %s", destino)

    async def _enviar_inform_raw(
        self, destino: str, hilo: str, cuerpo_raw: str,
    ) -> None:
        """Envía un INFORM con un cuerpo de texto arbitrario
        (para simular respuestas con formato incorrecto)."""
        msg = Message(to=destino)
        msg.set_metadata("ontology", ONTOLOGIA)
        msg.set_metadata("performative", "inform")
        msg.thread = hilo
        msg.body = cuerpo_raw
        await self.send(msg)
        logger.debug("INFORM (raw) enviado a %s", destino)

    async def _enviar_refuse(
        self, destino: str, hilo: str,
    ) -> None:
        """Envía un REFUSE indicando que la partida no ha
        terminado."""
        msg = Message(to=destino)
        msg.set_metadata("ontology", ONTOLOGIA)
        msg.set_metadata("performative", "refuse")
        msg.thread = hilo
        msg.body = json.dumps({
            "action": "game-report",
            "reason": "not-finished",
        })
        await self.send(msg)
        logger.debug("REFUSE enviado a %s", destino)

    async def _enviar_agree(
        self, destino: str, hilo: str,
    ) -> None:
        """Envía un AGREE antes del INFORM (protocolo de dos
        pasos)."""
        msg = Message(to=destino)
        msg.set_metadata("ontology", ONTOLOGIA)
        msg.set_metadata("performative", "agree")
        msg.thread = hilo
        msg.body = json.dumps({"action": "game-report"})
        await self.send(msg)
        logger.debug("AGREE enviado a %s", destino)


# ═══════════════════════════════════════════════════════════════════
#  Agente TableroSimulado
# ═══════════════════════════════════════════════════════════════════

class TableroSimulado(Agent):
    """Agente SPADE que simula un tablero del sistema Tic-Tac-Toe.

    Atributos inyectados antes de ``setup()``:
        nick (str): Apodo MUC (ej: ``"tablero_mesa1"``).
        sala_jid (str): JID completo de la sala MUC.
        modo_respuesta (str): Cómo responder al game-report del
            supervisor (ver docstring del módulo).
    """

    async def setup(self) -> None:
        """Se une a la sala MUC, registra el behaviour de respuesta
        y establece el estado inicial como ``waiting``."""
        self.client.register_plugin("xep_0045")

        # Unirse a la sala con estado inicial "waiting"
        self._unirse_sala_muc(self.sala_jid, self.nick)
        self._enviar_presencia_muc(self.sala_jid, self.nick, "waiting")

        # Registrar el behaviour que responde a game-report.
        # El template incluye conversation-id para enrutar solo
        # los REQUEST de informe, no los de inscripcion (P-03).
        plantilla = Template()
        plantilla.set_metadata("ontology", ONTOLOGIA)
        plantilla.set_metadata("performative", "request")
        plantilla.set_metadata("conversation-id", "game-report")
        comportamiento = ResponderGameReportBehaviour()
        self.add_behaviour(comportamiento, plantilla)

        logger.info(
            "TableroSimulado '%s' unido a %s (modo: %s)",
            self.nick, self.sala_jid, self.modo_respuesta,
        )

    # ── Gestión de presencia MUC ─────────────────────────────

    def _unirse_sala_muc(self, jid_sala: str, apodo: str) -> None:
        """Se une a la sala MUC mediante stanza de presencia con
        namespace MUC (XEP-0045)."""
        stanza = self.client.make_presence(
            pto=f"{jid_sala}/{apodo}",
        )
        x_elem = SubElement(
            stanza.xml,
            "{http://jabber.org/protocol/muc}x",
        )
        hist = SubElement(x_elem, "history")
        hist.set("maxchars", "0")
        stanza.send()

    def _enviar_presencia_muc(
        self, jid_sala: str, apodo: str, estado: str,
    ) -> None:
        """Envía una stanza de presencia MUC con el campo status
        actualizado. Esto permite al supervisor detectar cambios
        de estado del tablero (waiting, playing, finished)."""
        stanza = self.client.make_presence(
            pto=f"{jid_sala}/{apodo}",
            pstatus=estado,
        )
        stanza.send()

    async def cambiar_estado_muc(self, nuevo_estado: str) -> None:
        """Cambia el estado de presencia MUC del tablero.

        Este método es el que invocan los tests para simular el
        ciclo de vida del tablero::

            await tablero.cambiar_estado_muc("playing")
            await tablero.cambiar_estado_muc("finished")

        Args:
            nuevo_estado: Nuevo valor del campo ``status``
                (ej: ``"waiting"``, ``"playing"``, ``"finished"``).
        """
        self._enviar_presencia_muc(
            self.sala_jid, self.nick, nuevo_estado,
        )
        logger.info(
            "TableroSimulado '%s' → status=%s",
            self.nick, nuevo_estado,
        )
