"""
Validacion y construccion del informe de integracion del alumno.

Carga el JSON Schema ``esquema_informe_alumno.json`` y proporciona
constructores y validadores para que los alumnos generen informes
conformes al formato exigido en la Bateria 3 (prueba colectiva).

Este modulo NO depende de SPADE ni de Pydantic.
Solo necesita: json (stdlib) + jsonschema.

Uso desde los tests del alumno::

    from validacion import (
        crear_informe_alumno,
        crear_partida_observada,
        serializar_informe_alumno,
        validar_informe_alumno,
    )

    # Construir el informe
    informe = crear_informe_alumno(
        equipo="grupo_03",
        puesto="pc05",
        timestamp_inicio="2026-04-15T10:15:00",
        timestamp_fin="2026-04-15T10:35:00",
        agentes_desplegados=[
            {"jid": "tablero_pc05@sinbad2.ujaen.es", "rol": "tablero"},
            {"jid": "jugador_pc05_x@sinbad2.ujaen.es", "rol": "jugador"},
        ],
        partidas_observadas=[...],
    )

    # Validar antes de guardar
    resultado = validar_informe_alumno(informe)
    assert resultado["valido"], resultado["errores"]

    # Serializar a fichero
    serializar_informe_alumno(informe, "informe_integracion.json")
"""
import json
import logging
import pathlib
from datetime import datetime
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  Carga del esquema
# ═══════════════════════════════════════════════════════════════════════════

_DIRECTORIO_ONTOLOGIA = pathlib.Path(__file__).parent.parent / "ontologia"

ESQUEMA_INFORME_ALUMNO: dict = json.loads(
    (_DIRECTORIO_ONTOLOGIA / "esquema_informe_alumno.json")
    .read_text(encoding="utf-8")
)

# ═══════════════════════════════════════════════════════════════════════════
#  Constantes
# ═══════════════════════════════════════════════════════════════════════════

RESULTADOS_VALIDOS = ("win", "draw", "aborted")
FICHAS_VALIDAS = ("X", "O")
ROLES_VALIDOS = ("tablero", "jugador")
TIPOS_INCIDENCIA = ("timeout", "error", "rechazo", "desconexion", "otro")
TAMANO_TABLERO = 9

# Combinaciones ganadoras del Tic-Tac-Toe (mismas que usa el supervisor
# en su validacion semantica).
_LINEAS_GANADORAS = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # filas
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columnas
    (0, 4, 8), (2, 4, 6),             # diagonales
)


# ═══════════════════════════════════════════════════════════════════════════
#  Validador
# ═══════════════════════════════════════════════════════════════════════════


def validar_informe_alumno(informe: dict[str, Any]) -> dict[str, Any]:
    """Valida un informe de alumno contra el esquema y reglas cruzadas.

    Realiza cuatro niveles de validacion:

      0. Presencia de campos obligatorios de primer nivel.
      1. JSON Schema (tipos, enums, rangos, formato).
      2. Coherencia temporal (inicio < fin).
      3. Reglas condicionales cruzadas por partida.

    Args:
        informe: Diccionario con los campos del informe.

    Returns:
        Diccionario con claves ``valido`` (bool) y ``errores``
        (list[str]).
    """
    errores: list[str] = []

    # -- Nivel 0: campos obligatorios de primer nivel --
    campos_obligatorios = (
        "equipo", "puesto", "timestamp_inicio",
        "timestamp_fin", "agentes_desplegados",
        "partidas_observadas",
    )
    for campo in campos_obligatorios:
        if campo not in informe:
            errores.append(f"Falta el campo obligatorio '{campo}'")

    # -- Nivel 1: validar contra JSON Schema --
    try:
        jsonschema.validate(
            instance=informe, schema=ESQUEMA_INFORME_ALUMNO,
        )
    except jsonschema.ValidationError as error:
        errores.append(f"Error de esquema: {error.message}")

    # Si el esquema ya fallo, no continuar con reglas cruzadas
    # porque los campos podrian no existir o tener tipos erroneos.
    if errores:
        resultado = {"valido": False, "errores": errores}
        return resultado

    # -- Nivel 2: coherencia temporal --
    errores_temporales = _validar_coherencia_temporal(informe)
    errores.extend(errores_temporales)

    # -- Nivel 3: reglas condicionales cruzadas por partida --
    partidas = informe.get("partidas_observadas", [])
    indice = 0
    while indice < len(partidas):
        partida = partidas[indice]
        prefijo = f"partida[{indice}]"
        errores_partida = _validar_reglas_partida(partida, prefijo)
        errores.extend(errores_partida)
        indice += 1

    resultado = {"valido": len(errores) == 0, "errores": errores}
    return resultado


def _validar_coherencia_temporal(
    informe: dict[str, Any],
) -> list[str]:
    """Verifica que timestamp_inicio < timestamp_fin.

    Args:
        informe: Diccionario del informe completo.

    Returns:
        Lista de errores encontrados (vacia si todo correcto).
    """
    errores: list[str] = []

    try:
        inicio = datetime.fromisoformat(informe["timestamp_inicio"])
        fin = datetime.fromisoformat(informe["timestamp_fin"])
        if inicio >= fin:
            errores.append(
                "timestamp_inicio debe ser anterior a timestamp_fin"
            )
    except (ValueError, KeyError):
        # Si el formato es invalido, el JSON Schema ya lo detecta
        pass

    return errores


def _validar_reglas_partida(
    partida: dict[str, Any], prefijo: str,
) -> list[str]:
    """Valida reglas condicionales cruzadas de una partida.

    Args:
        partida: Diccionario con los datos de la partida.
        prefijo: Prefijo para los mensajes de error (ej: 'partida[0]').

    Returns:
        Lista de errores encontrados.
    """
    errores: list[str] = []
    resultado_partida = partida.get("resultado", "")
    ganador_ficha = partida.get("ganador_ficha")
    tablero = partida.get("tablero_final", [])
    turnos = partida.get("turnos", 0)

    # Regla 1: resultado='win' requiere ganador_ficha
    if resultado_partida == "win" and ganador_ficha is None:
        errores.append(
            f"{prefijo}: Si resultado='win', "
            f"'ganador_ficha' es obligatorio"
        )

    # Regla 2: resultado='draw' prohibe ganador_ficha
    if resultado_partida == "draw" and ganador_ficha is not None:
        errores.append(
            f"{prefijo}: Si resultado='draw', "
            f"'ganador_ficha' debe ser null"
        )

    # Regla 3: resultado='aborted' requiere razon
    if resultado_partida == "aborted" and "razon" not in partida:
        errores.append(
            f"{prefijo}: Si resultado='aborted', "
            f"'razon' es obligatorio"
        )

    # Regla 4: turnos coherentes con resultado
    if resultado_partida == "win" and turnos < 5:
        errores.append(
            f"{prefijo}: Una victoria requiere al menos 5 turnos "
            f"(declarados: {turnos})"
        )

    if turnos > TAMANO_TABLERO:
        errores.append(
            f"{prefijo}: El tablero solo tiene 9 celdas, "
            f"no puede haber {turnos} turnos"
        )

    # Regla 5: tablero coherente con resultado (si hay tablero)
    if len(tablero) == TAMANO_TABLERO:
        errores_tablero = _validar_tablero_resultado(
            tablero, resultado_partida, ganador_ficha, prefijo,
        )
        errores.extend(errores_tablero)

    # Regla 6: jugador contra si mismo
    jugadores = partida.get("jugadores", {})
    jid_x = jugadores.get("X", "")
    jid_o = jugadores.get("O", "")
    if jid_x and jid_o and jid_x == jid_o:
        errores.append(
            f"{prefijo}: Jugador contra si mismo ({jid_x})"
        )

    return errores


def _validar_tablero_resultado(
    tablero: list[str],
    resultado: str,
    ganador_ficha: str | None,
    prefijo: str,
) -> list[str]:
    """Valida coherencia entre tablero final y resultado declarado.

    Args:
        tablero: Lista de 9 celdas.
        resultado: 'win', 'draw' o 'aborted'.
        ganador_ficha: 'X', 'O' o None.
        prefijo: Prefijo para mensajes de error.

    Returns:
        Lista de errores encontrados.
    """
    errores: list[str] = []

    if resultado == "win" and ganador_ficha is not None:
        tiene_linea = _hay_linea_ganadora(tablero, ganador_ficha)
        if not tiene_linea:
            errores.append(
                f"{prefijo}: Victoria de '{ganador_ficha}' declarada "
                f"pero no hay linea ganadora en el tablero"
            )

    if resultado == "draw":
        for ficha in FICHAS_VALIDAS:
            if _hay_linea_ganadora(tablero, ficha):
                errores.append(
                    f"{prefijo}: Empate declarado pero hay linea "
                    f"ganadora de '{ficha}' en el tablero"
                )

    return errores


def _hay_linea_ganadora(tablero: list[str], ficha: str) -> bool:
    """Comprueba si existe una linea ganadora para una ficha.

    Args:
        tablero: Lista de 9 celdas.
        ficha: 'X' u 'O'.

    Returns:
        True si hay al menos una linea completa de la ficha.
    """
    encontrada = False
    indice = 0
    while indice < len(_LINEAS_GANADORAS) and not encontrada:
        a, b, c = _LINEAS_GANADORAS[indice]
        if tablero[a] == ficha and tablero[b] == ficha \
                and tablero[c] == ficha:
            encontrada = True
        indice += 1
    return encontrada


# ═══════════════════════════════════════════════════════════════════════════
#  Constructores
# ═══════════════════════════════════════════════════════════════════════════


def crear_partida_observada(
    tablero_jid: str,
    resultado: str,
    jugadores: dict[str, str],
    turnos: int,
    tablero_final: list[str],
    ganador_ficha: str | None = None,
    timestamp: str | None = None,
    razon: str | None = None,
) -> dict[str, Any]:
    """Construye el diccionario de una partida observada.

    Args:
        tablero_jid: JID del tablero que arbitro la partida.
        resultado: ``'win'``, ``'draw'`` o ``'aborted'``.
        jugadores: ``{"X": jid_x, "O": jid_o}``.
        turnos: Numero de turnos jugados (0-9).
        tablero_final: Lista de 9 celdas (``"X"``, ``"O"`` o ``""``).
        ganador_ficha: ``'X'``, ``'O'`` o None.
        timestamp: Hora de finalizacion (``HH:MM:SS``).
        razon: Razon si resultado es ``'aborted'``.

    Returns:
        Diccionario listo para incluir en ``partidas_observadas``.
    """
    partida: dict[str, Any] = {
        "tablero_jid": tablero_jid,
        "resultado": resultado,
        "ganador_ficha": ganador_ficha,
        "jugadores": jugadores,
        "turnos": turnos,
        "tablero_final": tablero_final,
    }
    if timestamp is not None:
        partida["timestamp"] = timestamp
    if razon is not None:
        partida["razon"] = razon
    return partida


def crear_informe_alumno(
    equipo: str,
    puesto: str,
    timestamp_inicio: str,
    timestamp_fin: str,
    agentes_desplegados: list[dict[str, str]],
    partidas_observadas: list[dict[str, Any]],
    incidencias: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construye el diccionario completo del informe del alumno.

    No serializa a JSON; devuelve el diccionario para que el alumno
    pueda añadir partidas o incidencias antes de serializar.

    Args:
        equipo: Identificador del equipo o nombre del alumno.
        puesto: Puesto del laboratorio (``'pcXX'``).
        timestamp_inicio: ISO 8601 del inicio de sesion.
        timestamp_fin: ISO 8601 del fin de sesion.
        agentes_desplegados: Lista de ``{"jid": ..., "rol": ...}``.
        partidas_observadas: Lista de partidas (usar
            ``crear_partida_observada`` para construir cada una).
        incidencias: Lista de incidencias (opcional).

    Returns:
        Diccionario con el informe completo, listo para validar
        y serializar.
    """
    informe: dict[str, Any] = {
        "equipo": equipo,
        "puesto": puesto,
        "timestamp_inicio": timestamp_inicio,
        "timestamp_fin": timestamp_fin,
        "agentes_desplegados": agentes_desplegados,
        "partidas_observadas": partidas_observadas,
    }
    if incidencias is not None:
        informe["incidencias"] = incidencias
    return informe


# ═══════════════════════════════════════════════════════════════════════════
#  Serializacion
# ═══════════════════════════════════════════════════════════════════════════


def serializar_informe_alumno(
    informe: dict[str, Any],
    ruta_salida: str,
) -> dict[str, Any]:
    """Valida y serializa el informe a un fichero JSON.

    Args:
        informe: Diccionario del informe (construido con
            ``crear_informe_alumno``).
        ruta_salida: Ruta del fichero de salida
            (ej: ``'informe_integracion.json'``).

    Returns:
        Resultado de la validacion (``{"valido": bool,
        "errores": list}``).

    Raises:
        ValueError: Si el informe no es valido.
    """
    resultado = validar_informe_alumno(informe)
    if not resultado["valido"]:
        raise ValueError(
            "Informe invalido: "
            + "; ".join(resultado["errores"])
        )

    with open(ruta_salida, "w", encoding="utf-8") as fichero:
        json.dump(informe, fichero, ensure_ascii=False, indent=2)

    logger.info("Informe serializado en: %s", ruta_salida)
    return resultado
