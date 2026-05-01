"""
Paquete de ontología del sistema Tic-Tac-Toe multiagente.

Re-exporta todos los símbolos públicos de ontologia.py para
permitir imports directos como:

    from ontologia import crear_cuerpo_join, validar_cuerpo

En lugar de:

    from ontologia.ontologia import crear_cuerpo_join, validar_cuerpo
"""
from ontologia.ontologia import (  # noqa: F401
    ACCIONES_VALIDAS,
    CAMPOS_POR_ACCION,
    ESQUEMA_ONTOLOGIA,
    ONTOLOGIA,
    PERFORMATIVA_ACCEPT_PROPOSAL,
    PERFORMATIVA_AGREE,
    PERFORMATIVA_CFP,
    PERFORMATIVA_FAILURE,
    PERFORMATIVA_INFORM,
    PERFORMATIVA_POR_ACCION,
    PERFORMATIVA_PROPOSE,
    PERFORMATIVA_REFUSE,
    PERFORMATIVA_REJECT_PROPOSAL,
    PERFORMATIVA_REQUEST,
    PERFORMATIVAS_VALIDAS,
    POSICIONES_VALIDAS,
    PREFIJO_THREAD_GAME,
    PREFIJO_THREAD_JOIN,
    PREFIJO_THREAD_REPORT,
    SIMBOLOS_VALIDOS,
    ContenidoMensaje,
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
    crear_thread_unico,
    obtener_performativa,
    validar_cuerpo,
)
