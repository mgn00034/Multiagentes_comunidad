"""
Paquete de agentes simulados para tests de integración.

Contiene agentes SPADE ligeros que imitan el comportamiento de
tableros y jugadores del sistema Tic-Tac-Toe para poder probar
el agente supervisor en un entorno controlado con servidor XMPP
local (``spade run``).

Uso::

    from tests.simuladores import TableroSimulado, JugadorSimulado
"""

from tests.simuladores.tablero_simulado import TableroSimulado
from tests.simuladores.jugador_simulado import JugadorSimulado

__all__ = ["TableroSimulado", "JugadorSimulado"]
