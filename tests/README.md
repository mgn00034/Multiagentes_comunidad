# Carpeta `tests/` — Baterías de tests del proyecto

## Propósito

Aquí deben residir todos los tests ejecutables con `pytest` que el alumno
diseña para validar su implementación. Los tests proporcionados por el
profesor (`test_ontologia.py`) ya están incluidos y deben pasar al 100%.

## Tests proporcionados

El proyecto incluye **322 tests** organizados en 7 ficheros:

| Fichero | Tests | Componente verificado |
|---------|------:|-----------------------|
| `test_ontologia.py` | 60 | Ontología runtime: esquema JSON, constructores, validación, performativas FIPA y protocolo del supervisor |
| `test_supervisor_behaviours.py` | 76 | Funciones auxiliares, los 7 estados de `SolicitarInformeFSM` (incluyendo reintento M-04), tipos de evento del log (`LOG_*`) y validaciones semánticas de informes |
| `test_almacen_supervisor.py` | 37 | Capa de persistencia SQLite (`AlmacenSupervisor`): creación, escritura, lectura, aislamiento, filtrado de salas sin actividad y commits por lotes (M-08) |
| `test_supervisor_handlers.py` | 58 | Funciones de conversión, cálculo de ranking, generación CSV, rutas HTTP, endpoints CSV, SSE y autenticación HTTP Basic |
| `test_agente_supervisor.py` | 44 | Métodos internos del agente supervisor, presencia MUC, límite de FSMs concurrentes, cola de solicitudes y reconexión MUC |
| `test_creacion_salas.py` | 13 | Creación de salas MUC desde ficheros YAML de torneos y modos de ejecución |
| `test_integracion_supervisor.py` | 34 | Integración con agentes SPADE reales: partidas, errores, presencia, LLM, incidencias semánticas, reintento, carga (10 tableros) y ejecuciones pasadas |

Los tests de ontología (`test_ontologia.py`) sirven como referencia de
estilo y estructura para los tests propios del alumno.

## Tests que el alumno debe diseñar

El alumno decidirá cómo organizar sus ficheros de test. A continuación se
describe qué debe cubrir cada batería. El orden de ejecución importa: si
una batería falla, las siguientes pueden no tener sentido.

### Batería 1: Tests de estrategia

Validan la función `elegir_movimiento()` como función pura. No requieren
XMPP ni agentes. Deben ser los tests más rápidos del proyecto (< 1s cada
uno). Verificar como mínimo: que devuelve posición válida (0-8), que
elige casilla libre, que ante un tablero con una sola casilla libre la
elige, y que no modifica el tablero de entrada.

### Batería 2: Tests aislados de behaviours

Validan la lógica interna de los behaviours sin infraestructura XMPP,
siguiendo la técnica de la Guía de Testing Aislado de Behaviours. Para
el Tablero: gestión de plazas, asignación de símbolos, validación de
movimientos, detección de victoria y empate. Para el Jugador: filtrado
de tableros por prefijo MUC, control de partidas activas.

### Batería 3: Tests de interfaz web

Validan las rutas HTTP del Agente Tablero sin XMPP, usando
`aiohttp.test_utils` y `BeautifulSoup`. Para `/game/state`: HTTP 200,
JSON con campos obligatorios, estados válidos. Para `/game`: HTML con
rejilla, turno, jugadores, historial. Robustez: 404 ante rutas
inexistentes, concurrencia.

### Batería 4: Tests de integración

Requieren un servidor XMPP activo. Verifican el sistema completo:
arranque de agentes, unión a sala MUC, descubrimiento, inscripción,
al menos un turno, y respuesta a `game-report`.

## Orden de ejecución recomendado

```text
# Tests proporcionados (ontología + supervisor)
pytest tests/test_ontologia.py -v
pytest tests/test_almacen_supervisor.py -v
pytest tests/test_supervisor_behaviours.py -v
pytest tests/test_agente_supervisor.py -v
pytest tests/test_supervisor_handlers.py -v
pytest tests/test_creacion_salas.py -v

# Tests del alumno (nombres orientativos)
pytest tests/test_estrategia.py -v
pytest tests/test_tablero_aislado.py -v
pytest tests/test_jugador_aislado.py -v
pytest tests/test_web_endpoints.py -v
pytest tests/test_integracion.py -v --timeout=60

# Ejecutar todos de una vez
pytest tests/ -v
```

## Recordatorio

- Todo test debe tener docstring descriptivo.
- Usar `pytest.mark.asyncio` para tests asíncronos.
- Usar `pytest.mark.parametrize` cuando tenga sentido (como hace
  `test_ontologia.py` para las 9 posiciones válidas).
- Los tests de integración deben tener tiempo de espera explícito para no
  quedarse bloqueados si un agente no responde.
