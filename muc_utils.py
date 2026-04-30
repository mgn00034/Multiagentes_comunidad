"""Utilidades para la gestión de salas MUC (XEP-0045) en SPADE.

Proporciona funciones de conexión y consulta de ocupantes para los
agentes Tablero y Jugador del sistema Tic-Tac-Toe multiagente.
"""

import logging
from typing import Any

from spade.agent import Agent

logger = logging.getLogger(__name__)


def configurar_muc(agente: Agent, sala_muc: str, apodo: str) -> Any:
    """Registra el plugin XEP-0045 y une al agente a la sala MUC.

    Usa join_muc (llamada no bloqueante) que es la API compatible con
    el setup() síncrono de SPADE. Comprueba primero si el agente ya
    está en la sala para evitar el TimeoutError por unión duplicada.

    Args:
        agente: El agente SPADE que se va a unir a la sala.
        sala_muc: JID de la sala MUC (ej. 'tictactoe@conference.localhost').
        apodo: Nick con el que el agente se unirá a la sala.

    Returns:
        El plugin XEP-0045 de la sesión XMPP del agente.
    """
    plugin_muc = None
    cliente = agente.client

    # Registrar el plugin si todavía no está cargado
    if "xep_0045" not in cliente.plugin:
        cliente.register_plugin("xep_0045")

    plugin_muc = cliente.plugin["xep_0045"]

    # Comprobamos si ya estamos en la sala para evitar uniones duplicadas
    # que causarían TimeoutError en slixmpp/XEP_0045.join_muc_wait
    salas_activas = plugin_muc.get_joined_rooms()
    if sala_muc not in salas_activas:
        plugin_muc.join_muc(sala_muc, apodo)
        logger.info(
            "[MUC] Agente '%s' solicitando unión a '%s' con apodo '%s'.",
            agente.jid.local,
            sala_muc,
            apodo,
        )
    else:
        logger.debug(
            "[MUC] Agente '%s' ya está en la sala '%s'. Se omite join.",
            agente.jid.local,
            sala_muc,
        )

    return plugin_muc


def obtener_tableros_disponibles(plugin_muc: Any, sala_muc: str) -> list[str]:
    """Obtiene la lista de apodos de tableros presentes en la sala MUC.

    Args:
        plugin_muc: El plugin XEP-0045 configurado.
        sala_muc: El JID de la sala MUC a consultar.

    Returns:
        Lista de apodos que comienzan por 'tablero_'.
    """
    ocupantes = plugin_muc.get_roster(sala_muc)
    tableros: list[str] = []

    for nick in ocupantes:
        if nick.startswith("tablero_"):
            tableros.append(nick)

    return tableros