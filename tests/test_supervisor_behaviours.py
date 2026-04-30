"""
Tests unitarios de las funciones auxiliares y los estados del FSM
del Agente Supervisor.

Se prueban de forma aislada, sin necesidad de SPADE ni servidor XMPP:
- Funciones puras: ``_determinar_rol``, ``_construir_detalle_informe``.
- Estados del FSM: cada estado se prueba con un agente simulado
  que expone los mismos atributos que ``AgenteSupervisor``.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from behaviours.supervisor_behaviours import (
    COMBINACIONES_GANADORAS,
    FACTOR_RETROCESO,
    LOG_ADVERTENCIA,
    LOG_INCONSISTENCIA,
    LOG_SOLICITUD,
    LOG_TIMEOUT,
    MAX_REINTENTOS,
    MAX_TURNOS,
    MIN_TURNOS_VICTORIA,
    TIMEOUT_RESPUESTA,
    ST_ENVIAR_REQUEST,
    ST_ESPERAR_RESPUESTA,
    ST_ESPERAR_INFORME,
    ST_PROCESAR_INFORME,
    ST_PROCESAR_RECHAZO,
    ST_REGISTRAR_TIMEOUT,
    ST_REINTENTAR,
    EstadoEnviarRequest,
    EstadoEsperarRespuesta,
    EstadoEsperarInforme,
    EstadoProcesarInforme,
    EstadoProcesarRechazo,
    EstadoRegistrarTimeout,
    EstadoReintentar,
    _construir_detalle_informe,
    _determinar_rol,
    _hay_linea_ganadora,
    _validar_informe_duplicado,
    _validar_jugador_contra_si_mismo,
    _validar_jugadores_observados,
    _validar_tablero_resultado,
    _validar_turnos,
    validar_semantica_informe,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Datos de prueba
# ═══════════════════════════════════════════════════════════════════════════

# Los informes de prueba deben cumplir el esquema de la ontología
# (additionalProperties: false), por lo que solo incluyen los campos
# definidos en MensajeGameReport del esquema JSON.

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


# ═══════════════════════════════════════════════════════════════════════════
#  Utilidades para simular el agente y los mensajes
# ═══════════════════════════════════════════════════════════════════════════

def crear_agente_simulado():
    """Crea un objeto que imita los atributos de AgenteSupervisor
    necesarios para los tests de los estados del FSM."""
    agente = SimpleNamespace(
        informes_por_sala={"tictactoe": {}},
        tableros_consultados=set(),
        informes_pendientes={},
        log_por_sala={"tictactoe": []},
        ocupantes_por_sala={"tictactoe": []},
        ocupantes_historicos_por_sala={"tictactoe": set()},
        threads_procesados_por_sala={"tictactoe": set()},
        almacen=None,
        registrar_evento_log=MagicMock(),
        solicitar_siguiente_en_cola=MagicMock(),
    )
    return agente


def crear_mensaje_simulado(performativa, cuerpo_dict=None):
    """Crea un mensaje con los métodos mínimos que usan los estados."""
    msg = MagicMock()
    msg.get_metadata.return_value = performativa
    msg.sender = "tablero_mesa1@conference.localhost"
    msg.body = json.dumps(cuerpo_dict) if cuerpo_dict else "{}"
    return msg


def crear_estado_con_contexto(clase_estado, jid="tablero_mesa1@conference.localhost"):
    """Instancia un estado del FSM, le inyecta el contexto compartido
    y un agente simulado, y le asigna métodos send y receive simulados."""
    estado = clase_estado()
    estado.ctx = {
        "jid_tablero": jid,
        "sala_id": "tictactoe",
        "hilo": "report-test-12345",
        "mensaje": None,
        "timeout": TIMEOUT_RESPUESTA,
        "max_reintentos": MAX_REINTENTOS,
        "reintentos": 0,
    }
    estado.agent = crear_agente_simulado()
    estado.send = AsyncMock()
    estado.receive = AsyncMock(return_value=None)
    return estado


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _determinar_rol
# ═══════════════════════════════════════════════════════════════════════════

class TestDeterminarRol:
    """Verifica que se clasifica correctamente el rol de un ocupante
    MUC a partir de su apodo."""

    def test_apodo_con_prefijo_tablero(self):
        """Un apodo que empiece por 'tablero_' debe clasificarse como
        tablero."""
        assert _determinar_rol("tablero_mesa1") == "tablero"

    def test_apodo_supervisor(self):
        """El apodo 'supervisor' debe clasificarse como supervisor."""
        assert _determinar_rol("supervisor") == "supervisor"

    def test_apodo_jugador(self):
        """Cualquier otro apodo debe clasificarse como jugador."""
        assert _determinar_rol("jugador_ana") == "jugador"

    def test_apodo_desconocido_es_jugador(self):
        """Un apodo que no empiece por 'tablero_' ni sea 'supervisor'
        se considera jugador por defecto."""
        assert _determinar_rol("observador_externo") == "jugador"


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _construir_detalle_informe
# ═══════════════════════════════════════════════════════════════════════════

class TestConstruirDetalleInforme:
    """Verifica que se genera un texto descriptivo correcto para cada
    tipo de resultado de partida."""

    def test_detalle_victoria(self):
        """Una victoria debe indicar la ficha ganadora y los nombres
        de los jugadores."""
        detalle = _construir_detalle_informe(INFORME_VICTORIA)
        assert "Victoria" in detalle
        assert "ana" in detalle
        assert "luis" in detalle
        assert "7 turnos" in detalle

    def test_detalle_empate(self):
        """Un empate debe incluir la palabra 'Empate' y los nombres."""
        detalle = _construir_detalle_informe(INFORME_EMPATE)
        assert "Empate" in detalle
        assert "ana" in detalle
        assert "9 turnos" in detalle

    def test_detalle_abortada(self):
        """Una partida abortada debe incluir 'Abortada' y el motivo
        traducido al español."""
        detalle = _construir_detalle_informe(INFORME_ABORTADA)
        assert "Abortada" in detalle
        assert "ambos sin respuesta" in detalle
        assert "2 turnos" in detalle

    def test_detalle_con_campos_vacios(self):
        """Con un diccionario mínimo no debe lanzar excepciones."""
        cuerpo_minimo = {"result": "?", "players": {}, "turns": 0}
        detalle = _construir_detalle_informe(cuerpo_minimo)
        assert isinstance(detalle, str)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoEnviarRequest
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoEnviarRequest:
    """Verifica que el estado inicial envía el mensaje REQUEST,
    registra la solicitud en el log y transiciona correctamente."""

    @pytest.mark.asyncio
    async def test_envia_mensaje_al_tablero(self):
        """Debe llamar a send() con un mensaje dirigido al tablero."""
        estado = crear_estado_con_contexto(EstadoEnviarRequest)
        await estado.run()
        estado.send.assert_called_once()
        mensaje_enviado = estado.send.call_args[0][0]
        assert str(mensaje_enviado.to) == "tablero_mesa1@conference.localhost"

    @pytest.mark.asyncio
    async def test_transiciona_a_esperar_respuesta(self):
        """Tras enviar, debe establecer ESPERAR_RESPUESTA como
        siguiente estado."""
        estado = crear_estado_con_contexto(EstadoEnviarRequest)
        await estado.run()
        assert estado.next_state == ST_ESPERAR_RESPUESTA

    @pytest.mark.asyncio
    async def test_registra_solicitud_en_log(self):
        """Debe registrar un evento de tipo 'solicitud' en el log
        del dashboard al enviar el REQUEST."""
        estado = crear_estado_con_contexto(EstadoEnviarRequest)
        await estado.run()
        estado.agent.registrar_evento_log.assert_called_once()
        args = estado.agent.registrar_evento_log.call_args[0]
        assert args[0] == LOG_SOLICITUD
        assert "partida" in args[2].lower()

    @pytest.mark.asyncio
    async def test_incluye_conversation_id_game_report(self):
        """El REQUEST debe incluir conversation-id='game-report'
        para que el tablero del alumno lo enrute al behaviour de
        informe y no al de inscripcion (P-03)."""
        estado = crear_estado_con_contexto(EstadoEnviarRequest)
        await estado.run()
        mensaje_enviado = estado.send.call_args[0][0]
        cid = mensaje_enviado.get_metadata("conversation-id")
        assert cid == "game-report"


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoEsperarRespuesta
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoEsperarRespuesta:
    """Verifica las transiciones del estado que espera la primera
    respuesta del tablero."""

    @pytest.mark.asyncio
    async def test_agree_transiciona_a_esperar_informe(self):
        """Si recibe AGREE, debe transicionar a ESPERAR_INFORME."""
        estado = crear_estado_con_contexto(EstadoEsperarRespuesta)
        estado.receive = AsyncMock(
            return_value=crear_mensaje_simulado("agree"),
        )
        await estado.run()
        assert estado.next_state == ST_ESPERAR_INFORME

    @pytest.mark.asyncio
    async def test_inform_transiciona_a_procesar_informe(self):
        """Si recibe INFORM directamente, debe transicionar a
        PROCESAR_INFORME y almacenar el mensaje en el contexto."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoEsperarRespuesta)
        estado.receive = AsyncMock(return_value=msg)
        await estado.run()
        assert estado.next_state == ST_PROCESAR_INFORME
        assert estado.ctx["mensaje"] is msg

    @pytest.mark.asyncio
    async def test_refuse_transiciona_a_procesar_rechazo(self):
        """Si recibe REFUSE, debe transicionar a PROCESAR_RECHAZO."""
        msg = crear_mensaje_simulado(
            "refuse", {"reason": "not-finished"},
        )
        estado = crear_estado_con_contexto(EstadoEsperarRespuesta)
        estado.receive = AsyncMock(return_value=msg)
        await estado.run()
        assert estado.next_state == ST_PROCESAR_RECHAZO
        assert estado.ctx["mensaje"] is msg

    @pytest.mark.asyncio
    async def test_timeout_transiciona_a_registrar_timeout(self):
        """Si no llega respuesta (None), debe transicionar a
        REGISTRAR_TIMEOUT."""
        estado = crear_estado_con_contexto(EstadoEsperarRespuesta)
        estado.receive = AsyncMock(return_value=None)
        await estado.run()
        assert estado.next_state == ST_REGISTRAR_TIMEOUT

    @pytest.mark.asyncio
    async def test_performativa_inesperada_transiciona_a_timeout(self):
        """Una performativa no reconocida debe transicionar a
        REGISTRAR_TIMEOUT como respuesta segura."""
        msg = crear_mensaje_simulado("propose")
        estado = crear_estado_con_contexto(EstadoEsperarRespuesta)
        estado.receive = AsyncMock(return_value=msg)
        await estado.run()
        assert estado.next_state == ST_REGISTRAR_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoEsperarInforme
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoEsperarInforme:
    """Verifica las transiciones del estado que espera el informe tras
    un AGREE. En este estado REFUSE no es una transición válida."""

    @pytest.mark.asyncio
    async def test_inform_transiciona_a_procesar_informe(self):
        """Si recibe INFORM, debe transicionar a PROCESAR_INFORME."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoEsperarInforme)
        estado.receive = AsyncMock(return_value=msg)
        await estado.run()
        assert estado.next_state == ST_PROCESAR_INFORME
        assert estado.ctx["mensaje"] is msg

    @pytest.mark.asyncio
    async def test_timeout_transiciona_a_registrar_timeout(self):
        """Si no llega respuesta, debe transicionar a
        REGISTRAR_TIMEOUT."""
        estado = crear_estado_con_contexto(EstadoEsperarInforme)
        estado.receive = AsyncMock(return_value=None)
        await estado.run()
        assert estado.next_state == ST_REGISTRAR_TIMEOUT

    @pytest.mark.asyncio
    async def test_refuse_no_transiciona_a_procesar_rechazo(self):
        """Tras AGREE, un REFUSE no debe transicionar a
        PROCESAR_RECHAZO (no es válido en este punto del protocolo).
        Se trata como performativa inesperada → REGISTRAR_TIMEOUT."""
        msg = crear_mensaje_simulado("refuse", {"reason": "not-finished"})
        estado = crear_estado_con_contexto(EstadoEsperarInforme)
        estado.receive = AsyncMock(return_value=msg)
        await estado.run()
        assert estado.next_state != ST_PROCESAR_RECHAZO
        assert estado.next_state == ST_REGISTRAR_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoProcesarInforme
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoProcesarInforme:
    """Verifica que el estado final procesa y almacena correctamente
    los informes recibidos."""

    @pytest.mark.asyncio
    async def test_almacena_informe_con_jid_tablero_del_contexto(self):
        """El informe debe almacenarse usando el jid_tablero del
        contexto del FSM (no el sender del mensaje), para que el
        nick del tablero sea legible en el dashboard."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        # El sender es el JID real (con recurso aleatorio)
        msg.sender = "tablero_mesa1@localhost/recursoABC"
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()

        informes = estado.agent.informes_por_sala["tictactoe"]
        # La clave debe ser el jid_tablero del contexto, NO el sender
        jid_ctx = estado.ctx["jid_tablero"]
        assert jid_ctx in informes
        assert isinstance(informes[jid_ctx], list)
        assert len(informes[jid_ctx]) == 1
        assert "tablero_mesa1@localhost/recursoABC" not in informes

    @pytest.mark.asyncio
    async def test_registra_evento_en_log(self):
        """Debe llamar a registrar_evento_log del agente."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()

        estado.agent.registrar_evento_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_persiste_en_almacen_con_jid_tablero(self):
        """Si el agente tiene almacén, debe llamar a guardar_informe
        con el jid_tablero del contexto del FSM."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        estado.agent.almacen = MagicMock()
        await estado.run()

        estado.agent.almacen.guardar_informe.assert_called_once()
        args = estado.agent.almacen.guardar_informe.call_args[0]
        # El segundo argumento debe ser el jid_tablero del contexto
        assert args[1] == estado.ctx["jid_tablero"]

    @pytest.mark.asyncio
    async def test_es_estado_final(self):
        """No debe establecer siguiente estado (el FSM termina)."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()
        assert estado.next_state is None

    @pytest.mark.asyncio
    async def test_json_invalido_no_lanza_excepcion(self):
        """Si el cuerpo del mensaje no es JSON válido, no debe lanzar
        excepciones (tablero que no usa la ontología correctamente)."""
        msg = MagicMock()
        msg.get_metadata.return_value = "inform"
        msg.sender = "tablero@localhost"
        msg.body = "esto no es json"
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()
        # No debe haber almacenado nada
        assert len(estado.agent.informes_por_sala["tictactoe"]) == 0

    @pytest.mark.asyncio
    async def test_informe_con_esquema_invalido_no_se_almacena(self):
        """Si el tablero envía un JSON válido pero que no cumple el
        esquema de la ontología (campos obligatorios ausentes), el
        informe no debe almacenarse."""
        # Falta 'players', 'turns' y 'board' que son obligatorios
        cuerpo_incompleto = {"action": "game-report", "result": "win"}
        msg = crear_mensaje_simulado("inform", cuerpo_incompleto)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()
        assert len(estado.agent.informes_por_sala["tictactoe"]) == 0

    @pytest.mark.asyncio
    async def test_informe_victoria_sin_winner_no_se_almacena(self):
        """Si un tablero envía result='win' pero no incluye 'winner',
        la validación de la ontología debe rechazarlo."""
        cuerpo_sin_winner = {
            "action": "game-report",
            "result": "win",
            "players": {"X": "a@l", "O": "b@l"},
            "turns": 5,
            "board": ["X", "O", "X", "O", "X", "", "", "", ""],
        }
        msg = crear_mensaje_simulado("inform", cuerpo_sin_winner)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()
        assert len(estado.agent.informes_por_sala["tictactoe"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoProcesarRechazo
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoProcesarRechazo:
    """Verifica que el estado final gestiona correctamente los
    rechazos de los tableros, incluyendo el desbloqueo de
    tableros_consultados (S-01)."""

    @pytest.mark.asyncio
    async def test_desbloquea_tableros_consultados(self):
        """El estado debe eliminar el tablero de
        tableros_consultados para que una futura partida
        del mismo tablero pueda ser detectada (S-01)."""
        msg = crear_mensaje_simulado(
            "refuse", {"reason": "not-finished"},
        )
        jid = "tablero_mesa1@conference.localhost"
        estado = crear_estado_con_contexto(EstadoProcesarRechazo, jid)
        estado.ctx["mensaje"] = msg
        estado.agent.tableros_consultados.add(jid)
        await estado.run()

        assert jid not in estado.agent.tableros_consultados

    @pytest.mark.asyncio
    async def test_es_estado_final(self):
        """No debe establecer siguiente estado."""
        msg = crear_mensaje_simulado(
            "refuse", {"reason": "not-finished"},
        )
        estado = crear_estado_con_contexto(EstadoProcesarRechazo)
        estado.ctx["mensaje"] = msg
        await estado.run()
        assert estado.next_state is None


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoRegistrarTimeout
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoRegistrarTimeout:
    """Verifica que el estado registra la incidencia de tiempo
    agotado. Cuando no hay reintentos configurados (max=0), se
    comporta como estado final."""

    @pytest.mark.asyncio
    async def test_registra_evento_timeout(self):
        """Debe llamar a registrar_evento_log con tipo 'timeout'."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["max_reintentos"] = 0
        await estado.run()

        estado.agent.registrar_evento_log.assert_called_once()
        args = estado.agent.registrar_evento_log.call_args[0]
        assert args[0] == LOG_TIMEOUT

    @pytest.mark.asyncio
    async def test_es_estado_final_sin_reintentos(self):
        """Sin reintentos configurados no debe establecer
        siguiente estado."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["max_reintentos"] = 0
        await estado.run()
        assert estado.next_state is None


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _hay_linea_ganadora
# ═══════════════════════════════════════════════════════════════════════════

class TestHayLineaGanadora:
    """Verifica la detección de líneas ganadoras en el tablero."""

    def test_linea_horizontal_superior(self):
        """Tres X en la fila superior deben detectarse como línea
        ganadora."""
        tablero = ["X", "X", "X", "", "", "", "", "", ""]
        assert _hay_linea_ganadora(tablero, "X") is True

    def test_linea_diagonal(self):
        """Tres O en la diagonal principal deben detectarse."""
        tablero = ["O", "", "", "", "O", "", "", "", "O"]
        assert _hay_linea_ganadora(tablero, "O") is True

    def test_sin_linea(self):
        """Un tablero parcialmente lleno sin línea no debe dar
        positivo."""
        tablero = ["X", "O", "X", "O", "X", "O", "O", "X", ""]
        assert _hay_linea_ganadora(tablero, "X") is False

    def test_ficha_incorrecta(self):
        """Si X tiene línea pero se busca O, debe ser falso."""
        tablero = ["X", "X", "X", "", "", "", "", "", ""]
        assert _hay_linea_ganadora(tablero, "O") is False

    def test_tablero_vacio(self):
        """Un tablero vacío no tiene línea ganadora."""
        tablero = [""] * 9
        assert _hay_linea_ganadora(tablero, "X") is False


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _validar_turnos
# ═══════════════════════════════════════════════════════════════════════════

class TestValidarTurnos:
    """Verifica que se detectan turnos anómalos en los informes."""

    def test_victoria_con_turnos_insuficientes(self):
        """Una victoria con menos de 5 turnos es imposible."""
        cuerpo = {"result": "win", "turns": 3}
        anomalias = _validar_turnos(cuerpo)
        assert len(anomalias) == 1
        assert "mínimo" in anomalias[0].lower()

    def test_victoria_con_turnos_minimos_validos(self):
        """Una victoria con exactamente 5 turnos es válida."""
        cuerpo = {"result": "win", "turns": 5}
        anomalias = _validar_turnos(cuerpo)
        assert len(anomalias) == 0

    def test_turnos_excesivos(self):
        """Más de 9 turnos es imposible en Tic-Tac-Toe."""
        cuerpo = {"result": "draw", "turns": 12}
        anomalias = _validar_turnos(cuerpo)
        assert len(anomalias) == 1
        assert "máximo" in anomalias[0].lower()

    def test_empate_con_9_turnos_valido(self):
        """Un empate con 9 turnos es perfectamente normal."""
        cuerpo = {"result": "draw", "turns": 9}
        anomalias = _validar_turnos(cuerpo)
        assert len(anomalias) == 0

    def test_victoria_con_turnos_excesivos(self):
        """Una victoria con más de 9 turnos genera dos anomalías:
        exceso de turnos."""
        cuerpo = {"result": "win", "turns": 10}
        anomalias = _validar_turnos(cuerpo)
        assert len(anomalias) == 1
        assert "máximo" in anomalias[0].lower()

    def test_abortada_sin_restriccion_minima(self):
        """Una partida abortada puede tener cualquier número de
        turnos bajo el máximo (no aplica mínimo de victoria)."""
        cuerpo = {"result": "aborted", "turns": 1}
        anomalias = _validar_turnos(cuerpo)
        assert len(anomalias) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _validar_tablero_resultado
# ═══════════════════════════════════════════════════════════════════════════

class TestValidarTableroResultado:
    """Verifica la coherencia entre el tablero y el resultado
    declarado en el informe."""

    def test_victoria_con_linea_ganadora(self):
        """Un informe de victoria con línea ganadora real no debe
        generar anomalías."""
        cuerpo = {
            "result": "win",
            "winner": "X",
            "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) == 0

    def test_victoria_sin_linea_ganadora(self):
        """Un informe de victoria sin línea ganadora en el tablero
        debe generar una anomalía."""
        cuerpo = {
            "result": "win",
            "winner": "X",
            "board": ["X", "O", "X", "O", "", "O", "", "", ""],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) == 1
        assert "línea ganadora" in anomalias[0].lower()

    def test_empate_con_tablero_lleno(self):
        """Un empate con tablero lleno sin línea ganadora es
        correcto."""
        cuerpo = {
            "result": "draw",
            "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) == 0

    def test_empate_con_celdas_vacias(self):
        """Un empate declarado con celdas vacías es anómalo."""
        cuerpo = {
            "result": "draw",
            "board": ["X", "O", "X", "", "O", "O", "O", "X", ""],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) >= 1
        assert "vacía" in anomalias[0].lower()

    def test_empate_con_linea_ganadora_oculta(self):
        """Un empate declarado pero con línea ganadora existente
        es una anomalía grave."""
        cuerpo = {
            "result": "draw",
            "board": ["X", "X", "X", "O", "O", "X", "O", "X", "O"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) >= 1
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "línea ganadora" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert encontrada

    def test_tablero_con_tamanyo_incorrecto_no_valida(self):
        """Si el tablero no tiene 9 celdas, no se aplica esta
        validación (ya la cubre el esquema)."""
        cuerpo = {
            "result": "win",
            "winner": "X",
            "board": ["X", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de coherencia de fichas (V8, V9, V10, V11)
# ═══════════════════════════════════════════════════════════════════════════

class TestCoherenciaFichas:
    """Verifica las validaciones V8-V11: equilibrio de fichas,
    coherencia turns vs board y convención X-primero."""

    # ── V9: turns coherente con fichas en board ──────────────

    def test_v9_turns_coincide_con_fichas(self):
        """Si turns coincide con el total de fichas, no hay
        anomalía por V9."""
        cuerpo = {
            "result": "win", "winner": "X", "turns": 7,
            "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "fichas" in anomalias[i] and "turnos" in anomalias[i]:
                encontrada = True
            i += 1
        assert not encontrada

    def test_v9_turns_no_coincide_con_fichas(self):
        """Si turns no coincide con el total de fichas, V9 debe
        detectar la inconsistencia."""
        cuerpo = {
            "result": "win", "winner": "X", "turns": 5,
            "board": ["X", "O", "X", "", "", "", "", "", ""],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "3 fichas" in anomalias[i] and "5 turnos" in anomalias[i]:
                encontrada = True
            i += 1
        assert encontrada

    def test_v9_empate_9_turnos_9_fichas(self):
        """Empate con 9 turnos y 9 fichas es correcto para V9."""
        cuerpo = {
            "result": "draw", "turns": 9,
            "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "fichas" in anomalias[i] and "turnos" in anomalias[i]:
                encontrada = True
            i += 1
        assert not encontrada

    # ── V8/V10: equilibrio de fichas ─────────────────────────

    def test_v8_empate_5x_4o_correcto(self):
        """Empate con 5X+4O (distribución correcta) no genera
        anomalía de equilibrio."""
        cuerpo = {
            "result": "draw", "turns": 9,
            "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "distribución" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert not encontrada

    def test_v8_empate_3x_6o_inconsistencia(self):
        """Empate con 3X+6O (diferencia > 1) debe generar
        anomalía."""
        cuerpo = {
            "result": "draw", "turns": 9,
            "board": ["X", "O", "O", "X", "O", "O", "O", "X", "O"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "distribución" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert encontrada

    def test_v10_victoria_equilibrio_correcto(self):
        """Victoria con 4X+3O en 7 turnos es correcto."""
        cuerpo = {
            "result": "win", "winner": "X", "turns": 7,
            "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "distribución" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert not encontrada

    def test_v10_victoria_1x_6o_inconsistencia(self):
        """Victoria con 1X+6O (diferencia > 1) debe generar
        anomalía."""
        cuerpo = {
            "result": "win", "winner": "O", "turns": 7,
            "board": ["O", "O", "O", "X", "O", "O", "", "", "O"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "distribución" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert encontrada

    # ── V11: convención X-primero ────────────────────────────

    def test_v11_empate_4x_5o_x_menor_que_o(self):
        """Empate con 4X+5O indica que O movió primero, violando
        la convención. V11 debe detectarlo."""
        cuerpo = {
            "result": "draw", "turns": 9,
            "board": ["O", "X", "O", "X", "O", "X", "O", "X", "O"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "mueve primero" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert encontrada

    def test_v11_victoria_3x_4o_x_menor_que_o(self):
        """Victoria con 3X+4O en 7 turnos indica que O movió
        primero. V11 debe detectarlo."""
        cuerpo = {
            "result": "win", "winner": "O", "turns": 7,
            "board": ["O", "X", "O", "X", "O", "", "", "X", "O"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "mueve primero" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert encontrada

    def test_v11_empate_5x_4o_correcto(self):
        """Empate con 5X+4O (X >= O) no genera anomalía V11."""
        cuerpo = {
            "result": "draw", "turns": 9,
            "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "mueve primero" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert not encontrada

    def test_v11_victoria_3x_2o_correcto(self):
        """Victoria con 3X+2O en 5 turnos (X >= O) es correcto."""
        cuerpo = {
            "result": "win", "winner": "X", "turns": 5,
            "board": ["X", "O", "X", "O", "X", "", "", "", ""],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        encontrada = False
        i = 0
        while i < len(anomalias) and not encontrada:
            if "mueve primero" in anomalias[i].lower():
                encontrada = True
            i += 1
        assert not encontrada

    # ── Abortadas no afectadas ───────────────────────────────

    def test_abortada_no_genera_anomalias_v8_v11(self):
        """Las partidas abortadas no deben generar anomalías por
        V8-V11 independientemente del estado del tablero."""
        cuerpo = {
            "result": "aborted", "turns": 4,
            "board": ["O", "X", "O", "", "", "", "", "", "X"],
        }
        anomalias = _validar_tablero_resultado(cuerpo)
        assert len(anomalias) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _validar_jugador_contra_si_mismo
# ═══════════════════════════════════════════════════════════════════════════

class TestValidarJugadorContraSiMismo:
    """Verifica la detección de un jugador asignado a ambas fichas."""

    def test_mismo_jid_en_ambas_fichas(self):
        """Si X y O tienen el mismo JID, debe detectarse."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_ana@localhost",
            },
        }
        anomalias = _validar_jugador_contra_si_mismo(cuerpo)
        assert len(anomalias) == 1
        assert "mismo agente" in anomalias[0].lower()

    def test_jugadores_distintos(self):
        """Dos jugadores diferentes no generan anomalía."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
        }
        anomalias = _validar_jugador_contra_si_mismo(cuerpo)
        assert len(anomalias) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _validar_jugadores_observados
# ═══════════════════════════════════════════════════════════════════════════

class TestValidarJugadoresObservados:
    """Verifica la detección de jugadores no observados en la sala
    usando el histórico de ocupantes (P-04)."""

    def test_jugadores_presentes_por_jid(self):
        """Si ambos JIDs aparecen en el histórico, no hay
        anomalía."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
        }
        observados = {
            "jugador_ana@localhost", "jugador_ana",
            "jugador_luis@localhost", "jugador_luis",
            "tablero_mesa1@localhost", "tablero_mesa1",
        }
        anomalias = _validar_jugadores_observados(
            cuerpo, observados,
        )
        assert len(anomalias) == 0

    def test_jugador_no_observado(self):
        """Si un jugador del informe nunca estuvo en la sala, debe
        detectarse como inconsistencia."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_fantasma@localhost",
            },
        }
        observados = {
            "jugador_ana@localhost", "jugador_ana",
        }
        anomalias = _validar_jugadores_observados(
            cuerpo, observados,
        )
        assert len(anomalias) == 1
        assert "jugador_fantasma" in anomalias[0]

    def test_ambos_jugadores_no_observados(self):
        """Si ninguno de los dos jugadores estuvo en la sala, se
        registran dos anomalías."""
        cuerpo = {
            "players": {
                "X": "jugador_a@localhost",
                "O": "jugador_b@localhost",
            },
        }
        observados = {"tablero_mesa1@localhost", "tablero_mesa1"}
        anomalias = _validar_jugadores_observados(
            cuerpo, observados,
        )
        assert len(anomalias) == 2

    def test_sin_observados_no_valida(self):
        """Si el histórico está vacío, no se aplica la
        validación."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
        }
        anomalias = _validar_jugadores_observados(cuerpo, set())
        assert len(anomalias) == 0

    def test_jugador_por_nick(self):
        """Si el JID completo no coincide pero el nick sí (parte
        local del JID del jugador), debe reconocerse."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@dominio.externo",
                "O": "jugador_luis@dominio.externo",
            },
        }
        observados = {"jugador_ana", "jugador_luis"}
        anomalias = _validar_jugadores_observados(
            cuerpo, observados,
        )
        assert len(anomalias) == 0

    def test_jugador_que_abandono_no_genera_falso_positivo(self):
        """Un jugador que estuvo en la sala y luego abandonó debe
        seguir en el histórico y no generar falso positivo (P-04).
        Este es el escenario principal que P-04 resuelve."""
        cuerpo = {
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
        }
        # El histórico conserva a ambos jugadores aunque ya no
        # estén en la foto en tiempo real (ocupantes_por_sala)
        observados = {
            "jugador_ana@localhost", "jugador_ana",
            "jugador_luis@localhost", "jugador_luis",
        }
        anomalias = _validar_jugadores_observados(
            cuerpo, observados,
        )
        assert len(anomalias) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _validar_informe_duplicado
# ═══════════════════════════════════════════════════════════════════════════

class TestValidarInformeDuplicado:
    """Verifica la detección de informes duplicados por thread
    (P-05). Dos informes con el mismo thread son duplicados
    independientemente de su contenido. Dos informes con threads
    distintos no son duplicados aunque tengan contenido idéntico."""

    def test_thread_ya_procesado_es_duplicado(self):
        """Si el thread del informe ya fue procesado, debe
        detectarse como duplicado."""
        hilo = "report-tablero_01-1713264000"
        procesados = {hilo}
        anomalias = _validar_informe_duplicado(hilo, procesados)
        assert len(anomalias) == 1
        assert "duplicado" in anomalias[0].lower()

    def test_thread_nuevo_no_es_duplicado(self):
        """Un thread que no ha sido procesado no es duplicado."""
        hilo = "report-tablero_01-1713264120"
        procesados = {"report-tablero_01-1713264000"}
        anomalias = _validar_informe_duplicado(hilo, procesados)
        assert len(anomalias) == 0

    def test_sin_threads_procesados(self):
        """Sin threads procesados previos no puede haber
        duplicado."""
        hilo = "report-tablero_01-1713264000"
        anomalias = _validar_informe_duplicado(hilo, set())
        assert len(anomalias) == 0

    def test_contenido_identico_threads_distintos_no_duplicado(self):
        """Dos partidas con resultado idéntico pero threads
        distintos NO deben marcarse como duplicado (P-05)."""
        hilo_1 = "report-tablero_01-1713264000"
        hilo_2 = "report-tablero_01-1713264120"
        procesados = {hilo_1}
        # El segundo informe tiene un thread distinto
        anomalias = _validar_informe_duplicado(hilo_2, procesados)
        assert len(anomalias) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de validar_semantica_informe (función agregadora)
# ═══════════════════════════════════════════════════════════════════════════

class TestValidarSemanticaInforme:
    """Verifica que la función agregadora ejecuta todas las
    validaciones y combina sus resultados."""

    def test_informe_valido_sin_anomalias(self):
        """Un informe correcto de victoria no genera anomalías."""
        anomalias = validar_semantica_informe(INFORME_VICTORIA)
        assert len(anomalias) == 0

    def test_informe_empate_valido(self):
        """Un empate correcto no genera anomalías."""
        anomalias = validar_semantica_informe(INFORME_EMPATE)
        assert len(anomalias) == 0

    def test_multiples_anomalias_combinadas(self):
        """Un informe con múltiples problemas debe reportar
        todas las anomalías encontradas."""
        cuerpo = {
            "result": "win",
            "winner": "X",
            "turns": 3,  # Turnos insuficientes
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_ana@localhost",  # Contra sí mismo
            },
            "board": ["X", "O", "", "", "", "", "", "", ""],  # Sin línea
        }
        anomalias = validar_semantica_informe(cuerpo)
        # Debe detectar al menos: turnos insuficientes, sin línea
        # ganadora, jugador contra sí mismo
        assert len(anomalias) >= 3


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de integración: EstadoProcesarInforme con validación semántica
# ═══════════════════════════════════════════════════════════════════════════

class TestProcesarInformeValidacionSemantica:
    """Verifica que EstadoProcesarInforme ejecuta las validaciones
    semánticas y registra las anomalías como eventos de tipo
    LOG_INCONSISTENCIA en el log del dashboard."""

    @pytest.mark.asyncio
    async def test_informe_con_turnos_anomalos_registra_inconsistencia(self):
        """Un informe con turnos imposibles debe almacenarse (pasa
        el esquema) pero registrar una inconsistencia."""
        cuerpo = {
            "action": "game-report",
            "result": "win",
            "winner": "X",
            "turns": 2,  # Imposible: mínimo 5
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
            "board": ["X", "X", "X", "", "", "", "", "", ""],
        }
        msg = crear_mensaje_simulado("inform", cuerpo)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()

        # El informe se almacena (esquema válido)
        informes = estado.agent.informes_por_sala["tictactoe"]
        assert len(informes) == 1

        # Debe haber al menos una llamada con LOG_INCONSISTENCIA
        llamadas = estado.agent.registrar_evento_log.call_args_list
        tipos = [c[0][0] for c in llamadas]
        assert LOG_INCONSISTENCIA in tipos

    @pytest.mark.asyncio
    async def test_informe_correcto_no_registra_inconsistencia(self):
        """Un informe perfectamente válido no debe generar eventos
        de inconsistencia."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        tipos = [c[0][0] for c in llamadas]
        assert LOG_INCONSISTENCIA not in tipos

    @pytest.mark.asyncio
    async def test_jugador_no_observado_registra_inconsistencia(self):
        """Si un jugador del informe no fue observado en la sala,
        se registra una inconsistencia (P-04)."""
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        # El histórico solo tiene al tablero, ningún jugador
        estado.agent.ocupantes_historicos_por_sala["tictactoe"] = {
            "tablero_mesa1@localhost", "tablero_mesa1",
        }
        await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        tipos = [c[0][0] for c in llamadas]
        assert LOG_INCONSISTENCIA in tipos

    @pytest.mark.asyncio
    async def test_informe_duplicado_registra_inconsistencia(self):
        """Si el thread del FSM ya fue procesado, se registra
        inconsistencia por duplicado (P-05)."""
        jid = "tablero_mesa1@conference.localhost"
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(EstadoProcesarInforme, jid)
        estado.ctx["mensaje"] = msg

        # Pre-cargar el thread como ya procesado (simula que el
        # mismo FSM ya entregó un informe anteriormente)
        hilo = estado.ctx["hilo"]
        estado.agent.threads_procesados_por_sala["tictactoe"].add(
            hilo,
        )
        await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        tipos = [c[0][0] for c in llamadas]
        assert LOG_INCONSISTENCIA in tipos

    @pytest.mark.asyncio
    async def test_victoria_sin_linea_registra_inconsistencia(self):
        """Un informe de victoria cuyo tablero no tiene línea
        ganadora real debe registrar inconsistencia."""
        cuerpo = {
            "action": "game-report",
            "result": "win",
            "winner": "X",
            "turns": 7,
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
            "board": ["X", "O", "X", "O", "", "O", "", "", ""],
        }
        msg = crear_mensaje_simulado("inform", cuerpo)
        estado = crear_estado_con_contexto(EstadoProcesarInforme)
        estado.ctx["mensaje"] = msg
        await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        tipos = [c[0][0] for c in llamadas]
        assert LOG_INCONSISTENCIA in tipos


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoRegistrarTimeout con reintentos (M-04)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistrarTimeoutConReintentos:
    """Verifica que EstadoRegistrarTimeout transiciona a
    ST_REINTENTAR cuando quedan reintentos disponibles y se
    autodestruye cuando se agotan."""

    @pytest.mark.asyncio
    async def test_transiciona_a_reintentar_si_quedan_reintentos(self):
        """Con reintentos < max_reintentos, debe transicionar a
        ST_REINTENTAR en vez de terminar."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["reintentos"] = 0
        estado.ctx["max_reintentos"] = 2
        await estado.run()
        assert estado.next_state == ST_REINTENTAR

    @pytest.mark.asyncio
    async def test_es_final_si_reintentos_agotados(self):
        """Con reintentos == max_reintentos, no debe establecer
        siguiente estado (FSM termina)."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["reintentos"] = 2
        estado.ctx["max_reintentos"] = 2
        await estado.run()
        assert estado.next_state is None

    @pytest.mark.asyncio
    async def test_limpia_informes_pendientes_solo_al_final(self):
        """Solo debe limpiar informes_pendientes cuando los
        reintentos se agotan, no en reintentos parciales."""
        jid = "tablero_mesa1@conference.localhost"

        # Reintento parcial: no limpia
        estado = crear_estado_con_contexto(
            EstadoRegistrarTimeout, jid,
        )
        estado.ctx["reintentos"] = 0
        estado.ctx["max_reintentos"] = 2
        estado.agent.informes_pendientes[jid] = "tictactoe"
        await estado.run()
        assert jid in estado.agent.informes_pendientes

        # Timeout definitivo: limpia
        estado2 = crear_estado_con_contexto(
            EstadoRegistrarTimeout, jid,
        )
        estado2.ctx["reintentos"] = 2
        estado2.ctx["max_reintentos"] = 2
        estado2.agent.informes_pendientes[jid] = "tictactoe"
        await estado2.run()
        assert jid not in estado2.agent.informes_pendientes

    @pytest.mark.asyncio
    async def test_registra_timeout_con_info_de_reintento(self):
        """El evento de timeout debe indicar el número de
        reintento cuando no es definitivo."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["reintentos"] = 0
        estado.ctx["max_reintentos"] = 2
        await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        args = llamadas[0][0]
        assert args[0] == LOG_TIMEOUT
        assert "reintento" in args[2].lower()

    @pytest.mark.asyncio
    async def test_registra_timeout_definitivo(self):
        """Cuando se agotan los reintentos, el detalle debe
        indicar que son reintentos agotados."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["reintentos"] = 2
        estado.ctx["max_reintentos"] = 2
        await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        args = llamadas[0][0]
        assert args[0] == LOG_TIMEOUT
        assert "agotados" in args[2].lower()

    @pytest.mark.asyncio
    async def test_sin_reintentos_configurados_es_final(self):
        """Con max_reintentos=0, debe comportarse como antes:
        timeout definitivo sin transición."""
        estado = crear_estado_con_contexto(EstadoRegistrarTimeout)
        estado.ctx["reintentos"] = 0
        estado.ctx["max_reintentos"] = 0
        await estado.run()
        assert estado.next_state is None


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de S-01: discard en estados terminales y guardia de transición
# ═══════════════════════════════════════════════════════════════════════════

class TestDesbloqueoEnEstadosTerminales:
    """Verifica que todos los estados terminales del FSM ejecutan
    tableros_consultados.discard(jid_tablero) al finalizar,
    permitiendo que futuras partidas del mismo tablero sean
    detectadas (S-01, cambio 2)."""

    @pytest.mark.asyncio
    async def test_procesar_informe_desbloquea(self):
        """EstadoProcesarInforme debe eliminar el tablero de
        tableros_consultados al procesar un informe valido."""
        jid = "tablero_mesa1@conference.localhost"
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(
            EstadoProcesarInforme, jid,
        )
        estado.ctx["mensaje"] = msg
        estado.agent.tableros_consultados.add(jid)
        await estado.run()
        assert jid not in estado.agent.tableros_consultados

    @pytest.mark.asyncio
    async def test_procesar_informe_json_invalido_desbloquea(self):
        """EstadoProcesarInforme debe desbloquear incluso cuando
        el body no es JSON valido (retorno anticipado)."""
        jid = "tablero_mesa1@conference.localhost"
        msg = MagicMock()
        msg.body = "esto no es JSON"
        msg.sender = jid
        estado = crear_estado_con_contexto(
            EstadoProcesarInforme, jid,
        )
        estado.ctx["mensaje"] = msg
        estado.agent.tableros_consultados.add(jid)
        await estado.run()
        assert jid not in estado.agent.tableros_consultados

    @pytest.mark.asyncio
    async def test_procesar_rechazo_desbloquea(self):
        """EstadoProcesarRechazo debe eliminar el tablero de
        tableros_consultados."""
        jid = "tablero_mesa1@conference.localhost"
        msg = crear_mensaje_simulado(
            "refuse", {"reason": "not-finished"},
        )
        estado = crear_estado_con_contexto(
            EstadoProcesarRechazo, jid,
        )
        estado.ctx["mensaje"] = msg
        estado.agent.tableros_consultados.add(jid)
        await estado.run()
        assert jid not in estado.agent.tableros_consultados

    @pytest.mark.asyncio
    async def test_timeout_definitivo_desbloquea(self):
        """EstadoRegistrarTimeout con reintentos agotados debe
        eliminar el tablero de tableros_consultados."""
        jid = "tablero_mesa1@conference.localhost"
        estado = crear_estado_con_contexto(
            EstadoRegistrarTimeout, jid,
        )
        estado.ctx["reintentos"] = 2
        estado.ctx["max_reintentos"] = 2
        estado.agent.tableros_consultados.add(jid)
        await estado.run()
        assert jid not in estado.agent.tableros_consultados

    @pytest.mark.asyncio
    async def test_timeout_parcial_no_desbloquea(self):
        """EstadoRegistrarTimeout con reintentos pendientes NO
        debe eliminar el tablero de tableros_consultados (el FSM
        sigue activo)."""
        jid = "tablero_mesa1@conference.localhost"
        estado = crear_estado_con_contexto(
            EstadoRegistrarTimeout, jid,
        )
        estado.ctx["reintentos"] = 0
        estado.ctx["max_reintentos"] = 2
        estado.agent.tableros_consultados.add(jid)
        await estado.run()
        assert jid in estado.agent.tableros_consultados

    @pytest.mark.asyncio
    async def test_ciclo_completo_finished_waiting_finished(self):
        """Tras el desbloqueo en un estado terminal, un segundo
        ciclo finished → waiting → finished debe poder crear
        un nuevo FSM (el tablero ya no esta en
        tableros_consultados)."""
        jid = "tablero_mesa1@conference.localhost"

        # Simular primer ciclo: procesar informe desbloquea
        msg = crear_mensaje_simulado("inform", INFORME_VICTORIA)
        estado = crear_estado_con_contexto(
            EstadoProcesarInforme, jid,
        )
        estado.ctx["mensaje"] = msg
        estado.agent.tableros_consultados.add(jid)
        await estado.run()

        # Verificar que el tablero esta desbloqueado
        assert jid not in estado.agent.tableros_consultados
        assert jid not in estado.agent.informes_pendientes


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de EstadoReintentar (M-04)
# ═══════════════════════════════════════════════════════════════════════════

class TestEstadoReintentar:
    """Verifica que el estado de reintento espera con retroceso
    exponencial, reenvía el REQUEST y transiciona correctamente."""

    @pytest.mark.asyncio
    async def test_incrementa_contador_de_reintentos(self):
        """Tras ejecutarse, el contador de reintentos debe
        incrementarse en 1."""
        estado = crear_estado_con_contexto(EstadoReintentar)
        estado.ctx["reintentos"] = 0
        with patch("behaviours.supervisor_behaviours.asyncio.sleep",
                    new_callable=AsyncMock):
            await estado.run()
        assert estado.ctx["reintentos"] == 1

    @pytest.mark.asyncio
    async def test_transiciona_a_esperar_respuesta(self):
        """Tras el reintento debe transicionar a
        ST_ESPERAR_RESPUESTA."""
        estado = crear_estado_con_contexto(EstadoReintentar)
        with patch("behaviours.supervisor_behaviours.asyncio.sleep",
                    new_callable=AsyncMock):
            await estado.run()
        assert estado.next_state == ST_ESPERAR_RESPUESTA

    @pytest.mark.asyncio
    async def test_reenvia_request(self):
        """Debe llamar a send() para reenviar el REQUEST."""
        estado = crear_estado_con_contexto(EstadoReintentar)
        with patch("behaviours.supervisor_behaviours.asyncio.sleep",
                    new_callable=AsyncMock):
            await estado.run()
        estado.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_registra_advertencia_y_solicitud(self):
        """Debe registrar un LOG_ADVERTENCIA (incidencia) y un
        LOG_SOLICITUD (nueva solicitud) en el log."""
        estado = crear_estado_con_contexto(EstadoReintentar)
        with patch("behaviours.supervisor_behaviours.asyncio.sleep",
                    new_callable=AsyncMock):
            await estado.run()

        llamadas = estado.agent.registrar_evento_log.call_args_list
        tipos = [c[0][0] for c in llamadas]
        assert LOG_ADVERTENCIA in tipos
        assert LOG_SOLICITUD in tipos

    @pytest.mark.asyncio
    async def test_espera_con_retroceso_exponencial(self):
        """El tiempo de espera debe ser
        timeout × factor^reintentos."""
        estado = crear_estado_con_contexto(EstadoReintentar)
        estado.ctx["reintentos"] = 1
        estado.ctx["timeout"] = 10
        with patch("behaviours.supervisor_behaviours.asyncio.sleep",
                    new_callable=AsyncMock) as mock_sleep:
            await estado.run()
        espera_esperada = 10 * (FACTOR_RETROCESO ** 1)
        mock_sleep.assert_called_once_with(espera_esperada)

    @pytest.mark.asyncio
    async def test_reenvio_incluye_conversation_id(self):
        """El REQUEST reenviado debe incluir
        conversation-id='game-report' igual que el envio
        inicial (P-03)."""
        estado = crear_estado_con_contexto(EstadoReintentar)
        with patch("behaviours.supervisor_behaviours.asyncio.sleep",
                    new_callable=AsyncMock):
            await estado.run()
        mensaje_enviado = estado.send.call_args[0][0]
        cid = mensaje_enviado.get_metadata("conversation-id")
        assert cid == "game-report"
