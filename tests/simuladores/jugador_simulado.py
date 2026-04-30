"""
Agente jugador simulado para tests de integración.

Se une a una sala MUC con un nick y permanece en estado ``chat``
hasta que se le pide abandonar la sala. No participa en partidas
ni responde mensajes: su único propósito es generar presencias
MUC que el supervisor debe detectar (eventos de entrada y salida).

Uso::

    jugador = crear_agente(JugadorSimulado, "jugador_test", cfg)
    jugador.nick = "jugador_ana"
    jugador.sala_jid = "test_sala@conference.localhost"
    await arrancar_agente(jugador, cfg)
    # ... el supervisor debería detectar su entrada
    await jugador.abandonar_sala()
    # ... el supervisor debería detectar su salida
"""

import logging
from xml.etree.ElementTree import SubElement

from spade.agent import Agent

logger = logging.getLogger(__name__)


class JugadorSimulado(Agent):
    """Agente SPADE ligero que simula un jugador en una sala MUC.

    Atributos inyectados antes de ``setup()``:
        nick (str): Apodo con el que se une a la sala MUC
            (ej: ``"jugador_ana"``).
        sala_jid (str): JID completo de la sala MUC
            (ej: ``"test_sala@conference.localhost"``).
        nivel_estrategia (int): Nivel de estrategia simulado
            (1=Posicional, 2=Reglas, 3=Minimax, 4=LLM).
            Solo informativo para los tests; no afecta al
            comportamiento del agente simulado. Por defecto 1.
    """

    async def setup(self) -> None:
        """Se une a la sala MUC con presencia ``show=chat``."""
        # Nivel de estrategia por defecto si no se inyectó
        if not hasattr(self, "nivel_estrategia"):
            self.nivel_estrategia = 1

        # Registrar el plugin MUC para que slixmpp interprete
        # correctamente las stanzas de presencia de la sala
        self.client.register_plugin("xep_0045")

        self._unirse_sala_muc(self.sala_jid, self.nick)
        logger.info(
            "JugadorSimulado '%s' unido a %s "
            "(nivel_estrategia=%d)",
            self.nick, self.sala_jid, self.nivel_estrategia,
        )

    # ── Gestión de presencia MUC ─────────────────────────────

    def _unirse_sala_muc(self, jid_sala: str, apodo: str) -> None:
        """Se une a una sala MUC enviando la stanza de presencia
        con namespace MUC y show=chat."""
        stanza = self.client.make_presence(
            pto=f"{jid_sala}/{apodo}",
            pshow="chat",
        )
        SubElement(
            stanza.xml,
            "{http://jabber.org/protocol/muc}x",
        )
        stanza.send()

    async def abandonar_sala(self) -> None:
        """Envía presencia ``unavailable`` a la sala MUC para que
        el supervisor detecte la salida."""
        stanza = self.client.make_presence(
            pto=f"{self.sala_jid}/{self.nick}",
            ptype="unavailable",
        )
        stanza.send()
        logger.info(
            "JugadorSimulado '%s' abandonó %s",
            self.nick, self.sala_jid,
        )
