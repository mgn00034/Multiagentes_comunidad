import pytest
from unittest.mock import AsyncMock, MagicMock
from agentes.agente_jugador import AgenteJugador
from behaviours.jugador_buscar import BuscarTablero


@pytest.mark.asyncio
async def test_jugador_filtra_prefijo_tablero_en_muc(datos_prueba):
    jid = f"{datos_prueba['jugador1_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteJugador(jid, "pass")
    agente.sala_muc = "sala@muc"
    agente.MAX_PARTIDAS = 3

    agente.muc = MagicMock()
    # Ocupantes mezclados
    agente.muc.get_roster.return_value = ["tablero_1", "jugador_2", "admin", "tablero_2"]
    agente.muc.rooms = {"sala@muc": {}}

    agente.presence = MagicMock()
    mock_contact = MagicMock()
    mock_contact.status = "waiting"
    agente.presence.get_contact.return_value = mock_contact

    buscar = BuscarTablero(period=5.0)
    buscar.set_agent(agente)
    buscar.inscribir = AsyncMock(return_value=True)

    await buscar.run()

    # Debe haber intentado inscribirse solo en tablero_1 y tablero_2
    assert buscar.inscribir.call_count == 2


@pytest.mark.asyncio
async def test_jugador_respeta_limite_partidas_simultaneas(datos_prueba):
    jid = f"{datos_prueba['jugador1_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteJugador(jid, "pass")
    agente.MAX_PARTIDAS = 1
    # Simulamos que ya está jugando el máximo de partidas
    agente.partidas_activas = {"hilo_activo": "tablero_viejo@localhost"}

    buscar = BuscarTablero(period=5.0)
    buscar.set_agent(agente)
    buscar.inscribir = AsyncMock()

    await buscar.run()

    # No debe intentar buscar más
    assert buscar.inscribir.call_count == 0