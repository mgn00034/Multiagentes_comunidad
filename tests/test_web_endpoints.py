import pytest
import pytest_asyncio
import asyncio
import aiohttp
import os
from agentes.agente_tablero import AgenteTablero


@pytest_asyncio.fixture
async def servidor_web_tablero(datos_prueba):
    jid = f"{datos_prueba['tablero_nombre']}@{datos_prueba['dominio']}"
    agente = AgenteTablero(jid, "pass")
    agente.config_parametros = {"puerto_web": datos_prueba["puerto_web"], "id_tablero": "test"}
    agente.config_xmpp = {"sala_muc_completa": "fake@muc"}

    agente.id_tablero = "test"
    agente.tablero = ["X", "O", "X", "", "", "", "", "", ""]
    agente.estado_partida = "finished"
    agente.resultado_final = "win"
    agente.ganador = "X"
    agente.jugadores = {"X": "j1", "O": "j2"}
    agente.turno_actual = "O"
    agente.historial = [{"symbol": "X", "position": 0}, {"symbol": "O", "position": 1}]
    agente.historial_partidas = []


    async def get_state(request):
        return {
            "board_id": agente.id_tablero,
            "status": agente.estado_partida,
            "players": {k: v.split('/')[0] for k, v in agente.jugadores.items()},
            "current_turn": agente.turno_actual,
            "result": agente.resultado_final,
            "winner": agente.ganador,
            "history": agente.historial,
            "total_partidas_jugadas": len(agente.historial_partidas),
            "partidas_pasadas": agente.historial_partidas
        }

    # Arrancamos solo el componente web de SPADE
    agente.web.start(port=datos_prueba["puerto_web"], templates_path="web/templates")

    # Registramos las rutas
    agente.web.add_get("/", get_state, "index.html")
    agente.web.add_get("/game", get_state, "index.html")
    agente.web.add_get("/game/state", get_state, None)

    await asyncio.sleep(0.5)

    yield agente

    # Teardown
    runner = getattr(agente.web, "runner", None)
    if runner:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_endpoint_game_state_cumple_ontologia(servidor_web_tablero, datos_prueba):
    puerto = datos_prueba["puerto_web"]
    url = f"http://127.0.0.1:{puerto}/game/state"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers["Content-Type"]
            datos = await resp.json()

            # Comprobamos los campos reales que devuelve nuestro agente
            assert "board_id" in datos
            assert "history" in datos
            assert "players" in datos
            assert "current_turn" in datos
            assert datos["status"] in ["waiting", "playing", "finished"]
            if datos["status"] == "finished":
                assert "winner" in datos


@pytest.mark.asyncio
async def test_endpoint_game_devuelve_html(servidor_web_tablero, datos_prueba):
    puerto = datos_prueba["puerto_web"]
    url = f"http://127.0.0.1:{puerto}/game"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers["Content-Type"]


@pytest.mark.asyncio
async def test_servidor_devuelve_404_ruta_invalida(servidor_web_tablero, datos_prueba):
    puerto = datos_prueba["puerto_web"]
    url = f"http://127.0.0.1:{puerto}/ruta_falsa_inexistente"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 404


@pytest.mark.asyncio
async def test_servidor_soporta_peticiones_concurrentes(servidor_web_tablero, datos_prueba):
    puerto = datos_prueba["puerto_web"]
    url = f"http://127.0.0.1:{puerto}/game/state"

    async def hacer_peticion(session):
        async with session.get(url) as resp:
            return resp.status

    async with aiohttp.ClientSession() as session:
        tareas = [hacer_peticion(session) for _ in range(10)]
        resultados = await asyncio.gather(*tareas)

        exito = True
        for r in resultados:
            if r != 200:
                exito = False

        assert exito