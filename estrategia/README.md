# Carpeta `estrategia/` — Funciones de estrategia de juego

## Propósito

Aquí debe residir la lógica de decisión del Agente Jugador: dado el
estado actual del tablero y el símbolo asignado, determinar en qué
posición colocar la ficha. Separar la estrategia en un módulo
independiente es una decisión de diseño deliberada que permite:

1. Probar la estrategia sin infraestructura XMPP (pruebas rápidas,
   deterministas, sin dependencias externas).
2. Intercambiar estrategias sin modificar el agente (patrón Strategy).
3. Reutilizar la misma función en diferentes contextos (agente real,
   simulador, evaluación offline).

## Qué se espera encontrar

Una o varias funciones puras con esta firma:

```python
def elegir_movimiento(tablero: list[str], mi_simbolo: str) -> int:
```

Donde `tablero` es una lista de 9 cadenas (`""`, `"X"` u `"O"`),
`mi_simbolo` es `"X"` u `"O"`, y el retorno es un entero entre 0 y 8
que representa la posición elegida. La función no debe modificar el
tablero de entrada.

## Niveles de estrategia

La calificación de la implementación está directamente ligada a la
sofisticación de la estrategia:

- **Nivel 1 (Posicional):** Asigna puntuación fija a cada posición
  (centro > esquinas > laterales) y elige la mejor libre. No analiza
  el estado del oponente.

- **Nivel 2 (Reglas):** Primero intenta ganar (completar tres en
  línea), luego bloquea al rival si amenaza ganar, y como último
  recurso aplica la heurística posicional.

- **Nivel 3 (Minimax):** Algoritmo Minimax con poda alfa-beta que
  explora exhaustivamente el árbol de jugadas. Nunca pierde.

- **Nivel 4 (LLM):** Integración con un modelo local vía Ollama.
  Requiere un mecanismo de respaldo que se active cuando
  el modelo devuelva una respuesta inválida o no interpretable.

## Orientaciones de diseño

La función debe ser **pura**: sin efectos secundarios, sin acceso a
red, sin estado global. Esto es lo que permite probarla con aserciones
directas en `tests/test_estrategia.py`.

Si implementas el nivel 4 (LLM), la llamada al modelo no es pura (es
asíncrona y puede fallar). En ese caso, encapsula la llamada en una
función separada (`elegir_movimiento_llm`) que internamente llame al
LLM y, si falla, delegue en la función pura de nivel inferior como
respaldo.

## Recordatorio

- La selección puramente aleatoria no alcanza el aprobado. Se exige
  un mínimo de razonamiento sobre el estado del tablero.
- Un solo `return` al final de la función.
- Documenta tu estrategia con docstring: qué criterios aplica, en
  qué orden, y cuál es su nivel de sofisticación.
