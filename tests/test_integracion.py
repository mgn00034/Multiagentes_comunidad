import pytest
import asyncio
import importlib
from spade.agent import DisconnectedException
from spade.message import Message

from ontologia import crear_cuerpo_game_report_request


@pytest.mark.asyncio
async def test_partida_integracion_completa(datos_prueba, configuracion_agentes):
    """
    Test End-to-End. Si el servidor XMPP no está encendido, hace SKIP.
    Instancia los agentes dinámicamente desde la configuración YAML sin imports hardcodeados.
    """
    config_xmpp = {"sala_muc_completa": datos_prueba["sala_muc"], "dominio": datos_prueba["dominio"]}
    config_sistema_rapida = {"intervalo_busqueda_muc": 0.5, "timeout_turno": 5.0, "timeout_inscripcion": 10.0}

    # 1. Separar definiciones del YAML
    def_tableros = [a for a in configuracion_agentes if "Tablero" in a.get("clase", "")]
    def_jugadores = [a for a in configuracion_agentes if "Jugador" in a.get("clase", "")]

    assert len(def_tableros) >= 1, "No se encontró ningún Tablero en agents.yaml"
    assert len(def_jugadores) >= 2, "Se necesitan al menos 2 Jugadores en agents.yaml"

    # 2. Función helper para instanciar dinámicamente
    def instanciar_agente_dinamico(definicion):
        modulo = importlib.import_module(definicion["modulo"])
        clase_agente = getattr(modulo, definicion["clase"])

        jid = f"{definicion['nombre']}@{datos_prueba['dominio']}"
        agente = clase_agente(jid, "secret", verify_security=False)

        agente.config_xmpp = config_xmpp
        agente.config_parametros = definicion.get("parametros", {})
        agente.config_sistema = config_sistema_rapida
        # BYPASS DE DNS PARA WINDOWS (Crítico para que no tarde 40s)
        agente.host = "127.0.0.1"

        return agente

    # 3. Creación dinámica
    tablero = instanciar_agente_dinamico(def_tableros[0])
    j1 = instanciar_agente_dinamico(def_jugadores[0])
    j2 = instanciar_agente_dinamico(def_jugadores[1])

    # 4. Ejecución del test
    try:
        await tablero.start()
    except DisconnectedException:
        pytest.skip(f"Servidor XMPP no disponible en {datos_prueba['dominio']}. Omitiendo integración.")

    await asyncio.gather(j1.start(), j2.start())

    # Usamos try...finally para garantizar que los agentes se apagan pase lo que pase
    try:
        tiempo_espera = 0
        terminado = False

        # Aumentamos el límite un poco para ordenadores más lentos (30 segundos reales)
        while not terminado and tiempo_espera < 60:
            if len(tablero.historial_partidas) > 0:
                terminado = True
            else:
                await asyncio.sleep(0.5)
                tiempo_espera += 1

        assert terminado, "La partida no logró terminar a tiempo"
        assert tablero.historial_partidas[0]["result"] in ["win", "draw"], "La partida se abortó inesperadamente"

        # --- Simulamos al Supervisor pidiendo el informe ---
        mensaje_reporte = Message(to=str(tablero.jid))
        mensaje_reporte.set_metadata("performative", "REQUEST")
        mensaje_reporte.set_metadata("ontology", "tictactoe")
        mensaje_reporte.thread = "report-test-123"
        mensaje_reporte.body = crear_cuerpo_game_report_request()

        # ¡LA CLAVE ESTÁ AQUÍ! NO HAY AWAIT DELANTE DE DISPATCH
        tablero.dispatch(mensaje_reporte)

        await asyncio.sleep(0.5)

    finally:
        # Garantizamos que todo se detiene ordenadamente
        await asyncio.gather(j1.stop(), j2.stop(), tablero.stop())