"""
Tests automatizados para la ontologia del Tic-Tac-Toe.

Ejecucion: pytest tests/test_ontologia.py -v
Dependencias: pytest, jsonschema (NO pydantic).
"""
import json

import pytest

from ontologia.ontologia import (
    ACCIONES_VALIDAS,
    CAMPOS_POR_ACCION,
    CONVERSATION_ID_POR_ACCION,
    ESQUEMA_ONTOLOGIA,
    ONTOLOGIA,
    PERFORMATIVA_POR_ACCION,
    crear_cuerpo_game_over,
    crear_cuerpo_game_report,
    crear_cuerpo_game_report_refused,
    crear_cuerpo_game_report_request,
    crear_cuerpo_game_start,
    crear_cuerpo_join,
    crear_cuerpo_join_accepted,
    crear_cuerpo_join_refused,
    crear_cuerpo_join_timeout,
    crear_cuerpo_move,
    crear_cuerpo_move_confirmado,
    crear_cuerpo_ok,
    crear_cuerpo_turn,
    crear_cuerpo_turn_result,
    crear_mensaje_join,
    crear_thread_unico,
    obtener_conversation_id,
    obtener_performativa,
    validar_cuerpo,
)

# Thread de ejemplo para los tests de game-start. Se usa un literal
# estable (no aleatorio) para que los tests sean deterministas; la
# funcion crear_thread_unico ya tiene sus propios tests.
THREAD_PARTIDA_TEST = "game-tablero_test-abc123"


# =====================================================================
# 1. TESTS DEL ESQUEMA GENERADO
# =====================================================================


class TestEsquemaGenerado:
    """Verificar que el esquema JSON cargado es correcto."""

    def test_esquema_tiene_one_of(self) -> None:
        assert "oneOf" in ESQUEMA_ONTOLOGIA

    def test_esquema_tiene_13_subesquemas(self) -> None:
        assert len(ESQUEMA_ONTOLOGIA["oneOf"]) == 13

    def test_esquema_tiene_id(self) -> None:
        assert "$id" in ESQUEMA_ONTOLOGIA

    def test_todas_acciones_en_mapa(self) -> None:
        assert len(CAMPOS_POR_ACCION) == 10

    def test_acciones_esperadas_presentes(self) -> None:
        esperadas = {
            "join", "join-accepted", "join-refused", "join-timeout",
            "game-start", "turn", "move", "ok", "game-over",
            "turn-result",
        }
        assert set(CAMPOS_POR_ACCION.keys()) == esperadas

    def test_campos_join_vacios(self) -> None:
        assert CAMPOS_POR_ACCION["join"] == []

    def test_campos_join_accepted_tiene_symbol(self) -> None:
        assert "symbol" in CAMPOS_POR_ACCION["join-accepted"]

    def test_campos_move_tiene_position(self) -> None:
        assert "position" in CAMPOS_POR_ACCION["move"]

    def test_constante_ontologia(self) -> None:
        assert ONTOLOGIA == "tictactoe"


# =====================================================================
# 2. TESTS DE CONSTRUCTORES - MENSAJES VALIDOS
# =====================================================================


class TestConstructoresGeneranJsonValido:
    """Los constructores deben producir JSON que pasa la validacion."""

    def test_join_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_join())
        assert validar_cuerpo(cuerpo)["valido"]

    def test_join_accepted_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_join_accepted("X"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_join_refused_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_join_refused("full"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_join_timeout_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_join_timeout("no opponent"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_game_start_es_valido(self) -> None:
        cuerpo = json.loads(
            crear_cuerpo_game_start(
                "jugador2@localhost", THREAD_PARTIDA_TEST,
            )
        )
        assert validar_cuerpo(cuerpo)["valido"]

    def test_game_start_incluye_thread_en_body(self) -> None:
        """El body del game-start debe incluir el thread de partida
        para que el jugador pueda preparar su template antes de
        recibir el primer CFP turn."""
        cuerpo = json.loads(
            crear_cuerpo_game_start(
                "jugador2@localhost", THREAD_PARTIDA_TEST,
            )
        )
        assert cuerpo["thread"] == THREAD_PARTIDA_TEST

    def test_game_start_con_thread_generado_dinamicamente(self) -> None:
        """Patron recomendado: el tablero genera el thread con
        crear_thread_unico y lo incrusta en el body del game-start.
        El body resultante debe seguir siendo valido."""
        thread = crear_thread_unico("tablero_01@localhost")
        cuerpo = json.loads(
            crear_cuerpo_game_start("jugador2@localhost", thread)
        )
        assert validar_cuerpo(cuerpo)["valido"]
        assert cuerpo["thread"] == thread

    def test_turn_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_turn("O"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_move_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_move(4))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_move_confirmado_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_move_confirmado(0, "X"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_ok_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_ok())
        assert validar_cuerpo(cuerpo)["valido"]

    def test_game_over_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_game_over("timeout", "X"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_turn_result_continue_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_turn_result("continue"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_turn_result_win_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_turn_result("win", "X"))
        assert validar_cuerpo(cuerpo)["valido"]

    def test_turn_result_draw_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_turn_result("draw"))
        assert validar_cuerpo(cuerpo)["valido"]

    @pytest.mark.parametrize("posicion", range(9))
    def test_todas_posiciones_validas(self, posicion: int) -> None:
        cuerpo = json.loads(crear_cuerpo_move(posicion))
        assert validar_cuerpo(cuerpo)["valido"]


# =====================================================================
# 3. TESTS DE CONSTRUCTORES - RECHAZO DE DATOS INVALIDOS
# =====================================================================


class TestConstructoresRechazan:
    """Los constructores deben rechazar datos que violan el esquema."""

    def test_move_posicion_99_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_move(99)

    def test_move_posicion_negativa_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_move(-1)

    def test_simbolo_minuscula_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_join_accepted("x")

    def test_simbolo_invalido_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_join_accepted("Z")

    def test_turn_simbolo_invalido_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_turn("A")

    def test_game_start_oponente_vacio_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_game_start("", THREAD_PARTIDA_TEST)

    def test_game_start_thread_vacio_lanza_error(self) -> None:
        """El thread debe ser una cadena no vacia para que el
        jugador pueda usarlo directamente en su template."""
        with pytest.raises(ValueError):
            crear_cuerpo_game_start("jugador2@localhost", "")

    def test_game_start_sin_thread_en_body_falla_validacion(self) -> None:
        """Un game-start construido a mano sin thread debe ser
        rechazado por el validador receptor."""
        cuerpo = {"action": "game-start", "opponent": "jugador2@localhost"}
        assert not validar_cuerpo(cuerpo)["valido"]

    def test_game_over_razon_invalida_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_game_over("razon_inventada")

    def test_turn_result_win_sin_ganador_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_turn_result("win")

    def test_turn_result_draw_con_ganador_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_turn_result("draw", "X")

    def test_turn_result_continue_con_ganador_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_turn_result("continue", "X")

    def test_turn_result_resultado_invalido_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            crear_cuerpo_turn_result("desconocido")


# =====================================================================
# 4. TESTS DEL VALIDADOR RECEPTOR
# =====================================================================


class TestValidadorReceptor:
    """El validador debe rechazar mensajes malformados."""

    def test_accion_desconocida_falla(self) -> None:
        assert not validar_cuerpo({"action": "saltar"})["valido"]

    def test_posicion_fuera_rango_falla(self) -> None:
        assert not validar_cuerpo({"action": "move", "position": 99})["valido"]

    def test_posicion_string_falla(self) -> None:
        assert not validar_cuerpo({"action": "move", "position": "4"})["valido"]

    def test_simbolo_minuscula_falla(self) -> None:
        r = validar_cuerpo({"action": "join-accepted", "symbol": "x"})
        assert not r["valido"]

    def test_mensaje_sin_action_falla(self) -> None:
        assert not validar_cuerpo({"position": 4})["valido"]

    def test_move_sin_position_falla(self) -> None:
        assert not validar_cuerpo({"action": "move"})["valido"]

    @pytest.mark.parametrize("accion,campos", [
        ("join", {}),
        ("join-accepted", {"symbol": "X"}),
        ("join-refused", {"reason": "full"}),
        ("join-timeout", {"reason": "no opponent"}),
        ("game-start", {
            "opponent": "jugador2@localhost",
            "thread": THREAD_PARTIDA_TEST,
        }),
        ("turn", {"active_symbol": "O"}),
        ("move", {"position": 4}),
        ("ok", {}),
        ("game-over", {"reason": "timeout", "winner": "X"}),
        ("turn-result", {"result": "win", "winner": "X"}),
    ])
    def test_todas_acciones_validas_pasan(self, accion, campos) -> None:
        cuerpo = {"action": accion, **campos}
        assert validar_cuerpo(cuerpo)["valido"]


# =====================================================================
# 5. TESTS DE REGLAS CONDICIONALES CRUZADAS
# =====================================================================


class TestReglasCondicionales:
    """Reglas que JSON Schema basico no puede expresar."""

    def test_result_win_sin_winner_falla(self) -> None:
        cuerpo = {
            "action": "game-report", "result": "win",
            "players": {"X": "j1@h", "O": "j2@h"},
            "turns": 5,
            "board": ["X", "O", "X", "O", "X", "", "", "", ""],
        }
        r = validar_cuerpo(cuerpo)
        assert not r["valido"]
        assert any("winner" in e for e in r["errores"])

    def test_result_draw_con_winner_falla(self) -> None:
        cuerpo = {
            "action": "game-report", "result": "draw", "winner": "X",
            "players": {"X": "j1@h", "O": "j2@h"},
            "turns": 9,
            "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
        }
        assert not validar_cuerpo(cuerpo)["valido"]

    def test_result_draw_sin_winner_pasa(self) -> None:
        cuerpo = {
            "action": "game-report", "result": "draw", "winner": None,
            "players": {"X": "j1@h", "O": "j2@h"},
            "turns": 9,
            "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
        }
        assert validar_cuerpo(cuerpo)["valido"]

    def test_result_aborted_sin_reason_falla(self) -> None:
        cuerpo = {
            "action": "game-report", "result": "aborted", "winner": None,
            "players": {"X": "j1@h", "O": "j2@h"},
            "turns": 3,
            "board": ["X", "O", "", "", "", "", "", "", ""],
        }
        assert not validar_cuerpo(cuerpo)["valido"]

    def test_result_aborted_con_reason_pasa(self) -> None:
        cuerpo = {
            "action": "game-report", "result": "aborted", "winner": None,
            "players": {"X": "j1@h", "O": "j2@h"},
            "turns": 3,
            "board": ["X", "O", "", "", "", "", "", "", ""],
            "reason": "both-timeout",
        }
        assert validar_cuerpo(cuerpo)["valido"]

    def test_turn_result_win_sin_winner_falla(self) -> None:
        cuerpo = {"action": "turn-result", "result": "win", "winner": None}
        r = validar_cuerpo(cuerpo)
        assert not r["valido"]
        assert any("winner" in e for e in r["errores"])

    def test_turn_result_continue_con_winner_falla(self) -> None:
        cuerpo = {"action": "turn-result", "result": "continue", "winner": "X"}
        r = validar_cuerpo(cuerpo)
        assert not r["valido"]
        assert any("winner" in e for e in r["errores"])


# =====================================================================
# 6. TESTS DE PERFORMATIVAS
# =====================================================================


class TestPerformativas:
    """Verificar la correspondencia accion-performativa FIPA."""

    def test_join_es_request(self) -> None:
        assert obtener_performativa("join") == "request"

    def test_turn_es_cfp(self) -> None:
        assert obtener_performativa("turn") == "cfp"

    def test_move_es_propose(self) -> None:
        assert obtener_performativa("move") == "propose"

    def test_game_over_es_reject_proposal(self) -> None:
        assert obtener_performativa("game-over") == "reject_proposal"

    def test_turn_result_es_inform(self) -> None:
        assert obtener_performativa("turn-result") == "inform"

    def test_accion_desconocida_lanza_key_error(self) -> None:
        with pytest.raises(KeyError):
            obtener_performativa("inexistente")

    def test_todas_acciones_tienen_performativa(self) -> None:
        for accion in ACCIONES_VALIDAS:
            assert accion in PERFORMATIVA_POR_ACCION


# =====================================================================
# 7. TESTS DEL PROTOCOLO DE INFORME AL SUPERVISOR
# =====================================================================


class TestProtocoloSupervisor:
    """Tests para los mensajes del supervisor."""

    def test_game_report_request_es_valido(self) -> None:
        cuerpo = json.loads(crear_cuerpo_game_report_request())
        assert cuerpo["action"] == "game-report"

    def test_game_report_completo_es_valido(self) -> None:
        body = crear_cuerpo_game_report(
            resultado_partida="win", ganador="X",
            jugadores={"X": "j1@localhost", "O": "j2@localhost"},
            turnos=7,
            tablero=["X", "O", "X", "O", "X", "O", "X", "", ""],
        )
        cuerpo = json.loads(body)
        assert validar_cuerpo(cuerpo)["valido"]

    def test_game_report_refused_es_valido(self) -> None:
        body = crear_cuerpo_game_report_refused()
        cuerpo = json.loads(body)
        assert cuerpo["action"] == "game-report"
        assert cuerpo["reason"] == "not-finished"


# =====================================================================
# 8. TESTS DE CONVERSATION-ID (P-03)
# =====================================================================


class TestConversationId:
    """Verifica que el diccionario CONVERSATION_ID_POR_ACCION y la
    funcion obtener_conversation_id() devuelven los valores
    correctos para las acciones que inician protocolos REQUEST."""

    def test_join_tiene_conversation_id(self) -> None:
        """La accion 'join' debe tener conversation-id='join'."""
        assert CONVERSATION_ID_POR_ACCION["join"] == "join"

    def test_game_report_tiene_conversation_id(self) -> None:
        """La accion 'game-report' debe tener
        conversation-id='game-report'."""
        assert CONVERSATION_ID_POR_ACCION["game-report"] == "game-report"

    def test_solo_dos_acciones_tienen_conversation_id(self) -> None:
        """Solo las acciones que inician un protocolo REQUEST
        deben tener conversation-id definido."""
        assert len(CONVERSATION_ID_POR_ACCION) == 2

    def test_obtener_conversation_id_join(self) -> None:
        """obtener_conversation_id('join') debe devolver 'join'."""
        assert obtener_conversation_id("join") == "join"

    def test_obtener_conversation_id_game_report(self) -> None:
        """obtener_conversation_id('game-report') debe devolver
        'game-report'."""
        resultado = obtener_conversation_id("game-report")
        assert resultado == "game-report"

    def test_accion_sin_conversation_id_lanza_key_error(self) -> None:
        """Una accion que no inicia protocolo REQUEST (como 'move'
        o 'turn') no tiene conversation-id y debe lanzar KeyError."""
        with pytest.raises(KeyError):
            obtener_conversation_id("move")

    def test_accion_inexistente_lanza_key_error(self) -> None:
        """Una accion que no existe en la ontologia debe lanzar
        KeyError."""
        with pytest.raises(KeyError):
            obtener_conversation_id("inexistente")


# =====================================================================
# 9. TESTS DE crear_mensaje_join (P-03)
# =====================================================================


class TestCrearMensajeJoin:
    """Verifica que crear_mensaje_join() construye un Message SPADE
    con toda la metadata necesaria para que el tablero de cualquier
    alumno enrute la inscripcion correctamente."""

    JID_TABLERO = "tablero_mesa1@localhost"
    JID_JUGADOR = "jugador_01@localhost"

    def test_destinatario_es_el_tablero(self) -> None:
        """El campo 'to' del mensaje debe ser el JID del tablero
        proporcionado como argumento."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert str(msg.to) == self.JID_TABLERO

    def test_incluye_ontologia(self) -> None:
        """El mensaje debe incluir la ontologia del sistema en
        la metadata."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert msg.get_metadata("ontology") == ONTOLOGIA

    def test_incluye_performative_request(self) -> None:
        """El mensaje debe declarar performative='request' en
        la metadata."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert msg.get_metadata("performative") == "request"

    def test_incluye_conversation_id_join(self) -> None:
        """El mensaje debe incluir conversation-id='join' para
        que el tablero lo enrute al behaviour de inscripcion y
        no al de informe."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert msg.get_metadata("conversation-id") == "join"

    def test_body_contiene_action_join(self) -> None:
        """El body del mensaje debe ser un JSON con
        action='join'."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        cuerpo = json.loads(msg.body)
        assert cuerpo["action"] == "join"

    def test_body_es_json_valido(self) -> None:
        """El body debe ser un JSON valido segun la ontologia."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        cuerpo = json.loads(msg.body)
        assert validar_cuerpo(cuerpo)["valido"]

    def test_funciona_con_jid_completo(self) -> None:
        """Debe aceptar JIDs con dominio externo, como los que
        se usan en torneo."""
        msg = crear_mensaje_join(
            "tablero_grupo3@sinbad2.ujaen.es",
            "jugador_grupo3@sinbad2.ujaen.es",
        )
        assert str(msg.to) == "tablero_grupo3@sinbad2.ujaen.es"
        assert msg.get_metadata("conversation-id") == "join"

    def test_metadata_completa_para_template_tablero(self) -> None:
        """El mensaje debe ser aceptado por el template estandar
        de inscripcion del tablero. Este test simula la
        interoperabilidad en torneo: verifica que los tres campos
        del template (ontology, performative, conversation-id)
        coinciden con los valores esperados."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert msg.get_metadata("ontology") == ONTOLOGIA
        assert msg.get_metadata("performative") == "request"
        assert msg.get_metadata("conversation-id") == "join"

    def test_thread_generado_con_crear_thread_unico(self) -> None:
        """El mensaje debe incluir un thread no vacio con el prefijo
        'join' y la parte local del JID del jugador, producido por
        crear_thread_unico."""
        msg = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert msg.thread is not None
        assert msg.thread.startswith("join-jugador_01-")

    def test_threads_de_llamadas_distintas_son_distintos(self) -> None:
        """Dos invocaciones sucesivas con los mismos JIDs deben
        producir threads distintos, porque el componente UUID4 del
        thread garantiza unicidad entre invocaciones."""
        msg1 = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        msg2 = crear_mensaje_join(self.JID_TABLERO, self.JID_JUGADOR)
        assert msg1.thread != msg2.thread
