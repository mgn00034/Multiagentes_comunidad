import pytest
from unittest.mock import AsyncMock
from spade.message import Message

from agentes.agente_tablero import AgenteTablero
from behaviours.tablero_inscripcion import EstadoInscripcion, ESTADO_INSCRIPCION
from behaviours.tablero_jugando import EstadoJugando, ESTADO_JUGANDO
from ontologia import crear_cuerpo_join, crear_cuerpo_move


@pytest.mark.asyncio
async def test_tablero_estado_inicial_correcto(datos_prueba):
    jid = f"{datos_prueba['tablero_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteTablero(jid, "pass")
    assert agente.estado_partida == "waiting"
    assert agente.tablero == [""] * 9


@pytest.mark.asyncio
async def test_tablero_acepta_dos_jugadores_y_rechaza_tercero(datos_prueba):
    jid_tablero = f"{datos_prueba['tablero_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteTablero(jid_tablero, "pass")
    estado = EstadoInscripcion()
    estado.set_agent(agente)
    estado.send = AsyncMock()

    # Jugador 1
    m1 = Message(to=jid_tablero, sender="j1@h")
    m1.thread, m1.body = "h1", crear_cuerpo_join()
    m1.set_metadata("performative", "REQUEST")
    await estado.procesar_peticion_join(m1)
    assert "X" in agente.jugadores

    # Jugador 2
    m2 = Message(to=jid_tablero, sender="j2@h")
    m2.thread, m2.body = "h2", crear_cuerpo_join()
    m2.set_metadata("performative", "REQUEST")
    sig_estado = await estado.procesar_peticion_join(m2)
    assert "O" in agente.jugadores
    assert sig_estado == ESTADO_JUGANDO

    # Jugador 3 (Rechazado)
    m3 = Message(to=jid_tablero, sender="j3@h")
    m3.thread, m3.body = "h3", crear_cuerpo_join()
    m3.set_metadata("performative", "REQUEST")
    await estado.procesar_peticion_join(m3)

    ultimo_mensaje_enviado = estado.send.call_args[0][0]
    assert ultimo_mensaje_enviado.metadata["performative"] == "refuse"


def test_tablero_detecta_las_8_lineas_ganadoras(datos_prueba):
    jid = f"{datos_prueba['tablero_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteTablero(jid, "pass")
    estado = EstadoJugando()
    estado.set_agent(agente)

    lineas = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
    resultado_final = True

    for a, b, c in lineas:
        agente.tablero = [""] * 9
        agente.tablero[a] = agente.tablero[b] = agente.tablero[c] = "X"
        res = estado.comprobar_resultado_partida()
        if res != "win":
            resultado_final = False

    assert resultado_final


def test_tablero_valida_movimientos(datos_prueba):
    jid = f"{datos_prueba['tablero_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteTablero(jid, "pass")
    agente.jugadores = {"X": "j1@h", "O": "j2@h"}
    agente.turno_actual = "X"
    agente.tablero = ["X", "", "", "", "", "", "", "", ""]
    estado = EstadoJugando()
    estado.set_agent(agente)

    # Movimiento válido
    m_valido = Message(sender="j1@h", body=crear_cuerpo_move(1))
    st_valido, pos = estado.validar_propuestas([m_valido])
    assert st_valido == "valid"

    # Movimiento inválido (ocupado)
    m_invalido = Message(sender="j1@h", body=crear_cuerpo_move(0))
    st_invalido, _ = estado.validar_propuestas([m_invalido])
    assert st_invalido == "invalid"