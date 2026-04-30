"""
Paquete de validacion de informes del sistema Tic-Tac-Toe multiagente.

Re-exporta los simbolos publicos de informe_alumno.py para
permitir imports directos como:

    from validacion import validar_informe_alumno, crear_informe_alumno

En lugar de:

    from validacion.informe_alumno import validar_informe_alumno
"""
from validacion.informe_alumno import (  # noqa: F401
    ESQUEMA_INFORME_ALUMNO,
    crear_informe_alumno,
    crear_partida_observada,
    serializar_informe_alumno,
    validar_informe_alumno,
)
