"""Estrategias de juego del sistema Tic-Tac-Toe multiagente.

Implementa cuatro niveles de sofisticación creciente como funciones puras.
Ninguna función modifica el tablero de entrada ni depende de infraestructura XMPP.

Niveles disponibles:
    1 — Posicional: puntuación por posición (centro > esquinas > laterales).
    2 — Reglas: ganar > bloquear > centro > esquinas > laterales.
    3 — Minimax: algoritmo óptimo con poda alfa-beta (nunca pierde).
    4 — LLM: consulta a Ollama con degradación automática a Minimax.
"""

import json
import logging
import urllib.request
import re
from typing import Any

logger = logging.getLogger(__name__)


def comprobar_ganador(tablero: list[str], simbolo: str) -> bool:
    """Comprueba si un símbolo ha completado tres en raya.

    Args:
        tablero: Lista de 9 elementos con '', 'X' u 'O'.
        simbolo: El símbolo a comprobar ('X' u 'O').

    Returns:
        True si el símbolo tiene tres en raya, False en caso contrario.
    """
    ganador = False
    lineas = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    indice = 0

    while not ganador and indice < len(lineas):
        a, b, c = lineas[indice]
        if tablero[a] == simbolo and tablero[b] == simbolo and tablero[c] == simbolo:
            ganador = True
        indice += 1

    return ganador


def tablero_lleno(tablero: list[str]) -> bool:
    """Comprueba si el tablero no tiene casillas vacías.

    Args:
        tablero: Lista de 9 elementos con '', 'X' u 'O'.

    Returns:
        True si no hay huecos libres, False si hay al menos uno.
    """
    lleno = True
    indice = 0

    while lleno and indice < len(tablero):
        if tablero[indice] == "":
            lleno = False
        indice += 1

    return lleno


def _buscar_movimiento_ganador(tablero: list[str], simbolo: str) -> int:
    """Busca un movimiento que otorgue victoria inmediata al símbolo dado.

    Args:
        tablero: Estado actual del tablero.
        simbolo: Símbolo para el que se busca el movimiento ganador.

    Returns:
        Posición ganadora (0-8) o -1 si no existe ninguna.
    """
    posicion = -1
    indice = 0
    encontrado = False
    copia = tablero[:]  # Trabajamos sobre copia para no alterar el original

    while not encontrado and indice < 9:
        if copia[indice] == "":
            copia[indice] = simbolo
            if comprobar_ganador(copia, simbolo):
                posicion = indice
                encontrado = True
            copia[indice] = ""
        indice += 1

    return posicion


def _valor_minimax(
    tablero: list[str],
    alfa: float,
    beta: float,
    es_maximizador: bool,
    mi_simbolo: str,
    rival_simbolo: str,
    profundidad: int = 0
) -> float:
    """Algoritmo recursivo Minimax con poda alfa-beta y penalización por profundidad.

    Args:
        tablero: Estado actual del tablero (copia mutable interna).
        alfa: Mejor valor garantizado para el maximizador en esta rama.
        beta: Mejor valor garantizado para el minimizador en esta rama.
        es_maximizador: True si es el turno del agente, False si es el rival.
        mi_simbolo: Símbolo del agente que busca la victoria.
        rival_simbolo: Símbolo del oponente.
        profundidad: Nivel actual en el árbol de búsqueda para preferir victorias rápidas.

    Returns:
        Puntuación heurística de la rama.
    """
    resultado = 0.0

    if comprobar_ganador(tablero, mi_simbolo):
        resultado = 10.0 - profundidad
    elif comprobar_ganador(tablero, rival_simbolo):
        resultado = -10.0 + profundidad
    elif tablero_lleno(tablero):
        resultado = 0.0
    elif es_maximizador:
        mejor_valor = -float("inf")
        indice = 0
        podado = False

        while not podado and indice < 9:
            if tablero[indice] == "":
                tablero[indice] = mi_simbolo
                valor = _valor_minimax(
                    tablero, alfa, beta, False, mi_simbolo, rival_simbolo, profundidad + 1
                )
                tablero[indice] = ""

                if valor > mejor_valor:
                    mejor_valor = valor
                if mejor_valor > alfa:
                    alfa = mejor_valor
                if beta <= alfa:
                    podado = True
            indice += 1

        resultado = mejor_valor
    else:
        mejor_valor = float("inf")
        indice = 0
        podado = False

        while not podado and indice < 9:
            if tablero[indice] == "":
                tablero[indice] = rival_simbolo
                valor = _valor_minimax(
                    tablero, alfa, beta, True, mi_simbolo, rival_simbolo, profundidad + 1
                )
                tablero[indice] = ""

                if valor < mejor_valor:
                    mejor_valor = valor
                if mejor_valor < beta:
                    beta = mejor_valor
                if beta <= alfa:
                    podado = True
            indice += 1

        resultado = mejor_valor

    return resultado


def estrategia_posicional(tablero: list[str], mi_simbolo: str, **kwargs: Any) -> int:
    """Estrategia Nivel 1: elige la casilla libre con mayor puntuación posicional.

    Puntuaciones: centro (4), esquinas (3), laterales (1).
    No reacciona al oponente.

    Args:
        tablero: Lista de 9 cadenas que representan el tablero.
        mi_simbolo: Símbolo del agente ('X' u 'O').
        **kwargs: Argumentos adicionales ignorados en este nivel.

    Returns:
        Índice de la posición elegida (0-8) o -1 si no hay huecos.
    """
    posicion_elegida = -1
    puntuaciones = [3, 1, 3, 1, 4, 1, 3, 1, 3]
    mejor_puntuacion = -1
    indice = 0

    while indice < len(tablero):
        if tablero[indice] == "" and puntuaciones[indice] > mejor_puntuacion:
            mejor_puntuacion = puntuaciones[indice]
            posicion_elegida = indice
        indice += 1

    return posicion_elegida


def estrategia_reglas(tablero: list[str], mi_simbolo: str, **kwargs: Any) -> int:
    """Estrategia Nivel 2: basada en reglas lógicas con prioridad fija.

    Prioridad: 1) Ganar, 2) Bloquear rival, 3) Centro, 4) Esquinas, 5) Laterales.

    Args:
        tablero: Lista de 9 cadenas que representan el tablero.
        mi_simbolo: Símbolo del agente ('X' u 'O').
        **kwargs: Argumentos adicionales ignorados en este nivel.

    Returns:
        Índice de la posición elegida (0-8) o -1 si no hay huecos.
    """
    posicion_elegida = -1
    rival_simbolo = "O" if mi_simbolo == "X" else "X"

    # 1. Intentar ganar
    posicion_elegida = _buscar_movimiento_ganador(tablero, mi_simbolo)

    # 2. Bloquear amenaza inminente del rival
    if posicion_elegida == -1:
        posicion_elegida = _buscar_movimiento_ganador(tablero, rival_simbolo)

    # 3. Tomar el centro si está libre
    if posicion_elegida == -1 and tablero[4] == "":
        posicion_elegida = 4

    # 4. Tomar alguna esquina libre
    esquinas = [0, 2, 6, 8]
    indice_esq = 0
    while posicion_elegida == -1 and indice_esq < len(esquinas):
        if tablero[esquinas[indice_esq]] == "":
            posicion_elegida = esquinas[indice_esq]
        indice_esq += 1

    # 5. Tomar algún lateral libre
    lados = [1, 3, 5, 7]
    indice_lado = 0
    while posicion_elegida == -1 and indice_lado < len(lados):
        if tablero[lados[indice_lado]] == "":
            posicion_elegida = lados[indice_lado]
        indice_lado += 1

    return posicion_elegida


def estrategia_minimax(tablero: list[str], mi_simbolo: str, **kwargs: Any) -> int:
    """Estrategia Nivel 3: algoritmo óptimo Minimax con poda alfa-beta.

    Nunca pierde: garantiza la mejor jugada posible en cualquier situación.

    Args:
        tablero: Lista de 9 cadenas que representan el tablero.
        mi_simbolo: Símbolo del agente ('X' u 'O').
        **kwargs: Argumentos adicionales ignorados en este nivel.

    Returns:
        Mejor posición calculada (0-8).
    """
    mejor_valor = -float("inf")
    posicion_elegida = -1
    rival_simbolo = "O" if mi_simbolo == "X" else "X"
    alfa = -float("inf")
    beta = float("inf")

    copia_tablero = tablero[:]

    indice = 0
    while indice < 9:
        if copia_tablero[indice] == "":
            copia_tablero[indice] = mi_simbolo
            valor = _valor_minimax(
                copia_tablero, alfa, beta, False, mi_simbolo, rival_simbolo, 1
            )
            copia_tablero[indice] = ""

            if valor > mejor_valor:
                mejor_valor = valor
                posicion_elegida = indice

            if mejor_valor > alfa:
                alfa = mejor_valor
        indice += 1

    return posicion_elegida


def estrategia_llm(tablero: list[str], mi_simbolo: str, **kwargs: Any) -> int:
    """Estrategia Nivel 4: consulta a un modelo LLM local (Ollama).

    Degrada automáticamente a Minimax ante cualquier fallo de red,
    timeout o respuesta inválida del modelo.
    """
    posicion_elegida = -1
    exito_llm = False
    config_llm = kwargs.get("config_llm")

    if config_llm is not None:
        url_base = config_llm.get("url_base", "http://localhost:11434")
        modelo = config_llm.get("modelo", "llama3.2:3b")
        url = f"{url_base}/api/generate"

        # 1. Preparar visualización 3x3 y lista de opciones
        matriz = []
        opciones_validas = []
        for i in range(9):
            if tablero[i] == "":
                matriz.append(str(i))
                opciones_validas.append(str(i))
            else:
                matriz.append(tablero[i])

        tablero_visual = (
            f"[{matriz[0]}, {matriz[1]}, {matriz[2]}]\n"
            f"[{matriz[3]}, {matriz[4]}, {matriz[5]}]\n"
            f"[{matriz[6]}, {matriz[7]}, {matriz[8]}]"
        )

        # 2. Prompt claro y estructurado
        prompt = (
            f"Vamos a jugar al tres en raya. Tú eres el jugador '{mi_simbolo}'.\n"
            f"Este es el estado actual del tablero, donde los números indican las casillas libres:\n"
            f"{tablero_visual}\n\n"
            f"Tus opciones válidas son: {', '.join(opciones_validas)}.\n"
            f"Responde ÚNICAMENTE con la cifra numérica de la casilla donde quieres mover. No añadas texto adicional."
        )

        logger.info(f"[LLM] 🗣️ Preguntando a Ollama:\n{prompt}")

        datos = json.dumps(
            {"model": modelo, "prompt": prompt, "stream": False}
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                url, data=datos, headers={"Content-Type": "application/json"}
            )
            # Aumentamos un pelín el timeout por si el modelo tiene que procesar el texto largo
            with urllib.request.urlopen(req, timeout=10.0) as respuesta:
                resultado = json.loads(respuesta.read().decode("utf-8"))
                respuesta_texto = resultado.get("response", "").strip()

                logger.info(f"[LLM] 🤖 Respuesta de Ollama: '{respuesta_texto}'")

                # 3. Extracción inteligente: buscamos dígitos en todo su texto
                numeros_encontrados = re.findall(r'\d+', respuesta_texto)

                # Comprobamos los números que ha mencionado
                for num_str in numeros_encontrados:
                    pos = int(num_str)
                    # Si el número que mencionó es una casilla legal y está vacía, nos lo quedamos
                    if 0 <= pos <= 8 and tablero[pos] == "":
                        posicion_elegida = pos
                        exito_llm = True
                        break  # Paramos en el primer número válido que encontremos

        except Exception as error:
            logger.warning("[LLM] Error al consultar el modelo: %s", error)

    if not exito_llm:
        logger.info(
            "[LLM] Fallo o respuesta inválida. Degradando a Minimax como respaldo."
        )
        posicion_elegida = estrategia_minimax(tablero, mi_simbolo)

    return posicion_elegida

# Diccionario para carga dinámica desde el lanzador
ESTRATEGIAS: dict[int, Any] = {
    1: estrategia_posicional,
    2: estrategia_reglas,
    3: estrategia_minimax,
    4: estrategia_llm,
}