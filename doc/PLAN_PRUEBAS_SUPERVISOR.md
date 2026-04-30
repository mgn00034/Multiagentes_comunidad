# Plan de pruebas manual — Agente Supervisor

**Proyecto:** Tic-Tac-Toe Multiagente

**Asignatura:** Sistemas Multiagente — Universidad de Jaén

**Fecha:** 2026-04-17 (actualizado)

---

## Propósito

Este documento describe las acciones que debe realizar el evaluador
para verificar visualmente que todos los bloques de pruebas del
Agente Supervisor funcionan correctamente. Cada bloque incluye:

1. **Comando a ejecutar** — la orden exacta de terminal.
2. **Resultado esperado** — lo que debe aparecer en la salida.
3. **Criterio de aceptación** — condición para considerar el
   bloque superado.

Las pruebas están organizadas en dos secciones: **pruebas
unitarias** (sin servidor XMPP) y **pruebas de integración**
(requieren servidor XMPP accesible).

---

## Requisitos previos

Antes de ejecutar cualquier prueba:

```bash
# 1. Activar el entorno virtual
source venv_sma/bin/activate

# 2. Verificar dependencias instaladas
pip install -r requirements.txt

# 3. Confirmar que pytest está disponible
pytest --version
```

---

## Parte I — Pruebas unitarias

Las pruebas unitarias no requieren servidor XMPP ni conexión de
red. Se ejecutan con objetos simulados (mocks) y bases de datos
temporales.

**Comando general para ejecutar TODAS las pruebas unitarias:**

```bash
pytest tests/ --ignore=tests/test_integracion_supervisor.py -v
```

**Resultado esperado:** la linea final debe indicar
`N passed` sin ningun `FAILED` ni `ERROR`. El numero total
esperado es **409 tests**.

A continuación se detallan los bloques individuales para
verificación parcial.

---

### Bloque 1: Ontología y protocolo FIPA

**Que verifica:** esquema JSON de la ontologia, constructores de
mensajes, validacion de campos obligatorios, performativas FIPA,
protocolo del supervisor, `conversation-id` (P-03) y
`crear_mensaje_join`.

**Comando:**

```bash
pytest tests/test_ontologia.py -v
```

**Resultado esperado:**

- Todos los tests con estado `PASSED`.
- Linea final: `90 passed`.

**Criterio de aceptación:** ningún test falla. Esto garantiza que
la ontología del sistema (los mensajes que intercambian los agentes)
es correcta y que cualquier modificación posterior que rompa la
ontología será detectada.

---

### Bloque 2: Agente supervisor — métodos internos y presencia MUC

**Qué verifica:** identificación de salas, registro de eventos,
handler de presencia MUC (entradas, salidas, cambios de estado,
detección de tableros finalizados), límite de FSMs concurrentes,
cola de solicitudes y reconexión automática.

**Comando:**

```bash
pytest tests/test_agente_supervisor.py -v
```

**Resultado esperado:**

- Todos los tests con estado `PASSED`.
- Linea final: `48 passed`.
- Las clases de tests que deben aparecer en la salida:
  - `TestIdentificarSala` (4 tests)
  - `TestObtenerSalaDeTablero` (4 tests)
  - `TestRegistrarEventoLog` (5 tests)
  - `TestOnPresenciaMucEntrada` (5 tests)
  - `TestOnPresenciaMucSalida` (2 tests)
  - `TestOnPresenciaMucCambioEstado` (5 tests)
  - `TestOnPresenciaMucFinished` (8 tests)
  - `TestFiltradoRedistribucionFinished` (4 tests) — S-01
  - `TestLimiteFSMConcurrentes` (5 tests)
  - `TestDetenerConColaNoVacia` (1 test)
  - `TestReconexionMUC` (5 tests)

**Criterio de aceptacion:** los 48 tests pasan. En particular:
- `TestFiltradoRedistribucionFinished` confirma que
  redistribuciones `finished→finished` se ignoran (S-01).
- `TestReconexionMUC` confirma que la reconexion genera
  advertencias.
- `TestLimiteFSMConcurrentes` confirma que los tableros se
  encolan correctamente.

---

### Bloque 3: Behaviours del FSM — estados, validación semántica y reintentos

**Qué verifica:** funciones auxiliares (`_determinar_rol`,
`_construir_detalle_informe`), los 7 estados de la máquina de
estados (`EstadoEnviarRequest`, `EstadoEsperarRespuesta`,
`EstadoEsperarInforme`, `EstadoProcesarInforme`,
`EstadoProcesarRechazo`, `EstadoRegistrarTimeout`,
`EstadoReintentar`), validaciones semánticas de informes (turnos,
tablero, jugadores, duplicados) y retroceso exponencial.

**Comando:**

```bash
pytest tests/test_supervisor_behaviours.py -v
```

**Resultado esperado:**

- Todos los tests con estado `PASSED`.
- Linea final: `98 passed`.
- Las clases de tests que deben aparecer:
  - `TestDeterminarRol` (4 tests)
  - `TestConstruirDetalleInforme` (4 tests)
  - `TestEstadoEnviarRequest` (4 tests) — incluye conversation-id
  - `TestEstadoEsperarRespuesta` (5 tests)
  - `TestEstadoEsperarInforme` (3 tests)
  - `TestEstadoProcesarInforme` (7 tests)
  - `TestEstadoProcesarRechazo` (2 tests)
  - `TestEstadoRegistrarTimeout` (2 tests)
  - `TestHayLineaGanadora` (5 tests)
  - `TestValidarTurnos` (6 tests)
  - `TestValidarTableroResultado` (6 tests)
  - `TestCoherenciaFichas` (12 tests) — V8-V11 (P-07)
  - `TestValidarJugadorContraSiMismo` (2 tests)
  - `TestValidarJugadoresObservados` (6 tests)
  - `TestValidarInformeDuplicado` (4 tests)
  - `TestValidarSemanticaInforme` (3 tests)
  - `TestProcesarInformeValidacionSemantica` (5 tests)
  - `TestRegistrarTimeoutConReintentos` (6 tests)
  - `TestDesbloqueoEnEstadosTerminales` (6 tests) — S-01
  - `TestEstadoReintentar` (6 tests) — incluye conversation-id

**Criterio de aceptacion:** los 98 tests pasan. En particular:
- `TestDesbloqueoEnEstadosTerminales` confirma que todos los
  estados terminales del FSM desbloquean `tableros_consultados`
  (S-01).
- `TestCoherenciaFichas` confirma las validaciones V8-V11 de
  equilibrio de fichas y convencion X-primero (P-07).
- `TestEstadoReintentar::test_espera_con_retroceso_exponencial`
  confirma que la espera es `timeout * 2^n`.
- `TestProcesarInformeValidacionSemantica` confirma que los
  informes con anomalias generan eventos `LOG_INCONSISTENCIA`.

---

### Bloque 4: Almacén SQLite — persistencia y commits por lotes

**Qué verifica:** creación de la base de datos, gestión de
ejecuciones, escritura y lectura de informes y eventos,
aislamiento entre ejecuciones, filtrado de salas sin actividad
y el sistema de commits por lotes (M-08).

**Comando:**

```bash
pytest tests/test_almacen_supervisor.py -v
```

**Resultado esperado:**

- Todos los tests con estado `PASSED`.
- Línea final: `37 passed`.
- Las clases de tests que deben aparecer:
  - `TestInicializacion` (3 tests)
  - `TestCrearEjecucion` (4 tests)
  - `TestFinalizarEjecucion` (6 tests)
  - `TestGuardarInforme` (5 tests)
  - `TestGuardarEvento` (4 tests)
  - `TestListarEjecuciones` (4 tests)
  - `TestAislamientoEjecuciones` (2 tests)
  - `TestCommitsPorLotes` (9 tests)

**Criterio de aceptación:** los 37 tests pasan. En particular,
`TestCommitsPorLotes` confirma que:
- Las escrituras no se consolidan antes de alcanzar el lote.
- El flush automático funciona al alcanzar el tamaño de lote.
- Los datos se recuperan correctamente tras cerrar y reabrir.

---

### Bloque 5: Handlers HTTP — conversión, CSV, SSE y autenticación

**Qué verifica:** funciones de conversión de datos (ontología →
dashboard), cálculo de ranking, generación de CSV, las rutas HTTP
del panel web (estado en vivo, ejecuciones pasadas, exportación
CSV), Server-Sent Events y autenticación HTTP Basic.

**Comando:**

```bash
pytest tests/test_supervisor_handlers.py -v
```

**Resultado esperado:**

- Todos los tests con estado `PASSED`.
- Linea final: `87 passed`.
- Las clases de tests que deben aparecer:
  - `TestMapearResultado` (5 tests)
  - `TestNombreLegibleSala` (2 tests)
  - `TestConvertirInformes` (8 tests)
  - `TestHandlerIndex` (2 tests)
  - `TestHandlerState` (3 tests)
  - `TestHandlerListarEjecuciones` (2 tests)
  - `TestHandlerDatosEjecucion` (4 tests)
  - `TestComputarRanking` (5 tests)
  - `TestGenerarCsvRanking` (3 tests)
  - `TestGenerarCsvLog` (2 tests)
  - `TestGenerarCsvIncidencias` (2 tests)
  - `TestHandlerCsvEnVivo` (6 tests)
  - `TestHandlerCsvEjecucion` (4 tests)
  - `TestNotificarSSE` (2 tests)
  - `TestHandlerSSE` (2 tests)
  - `TestAutenticacionBasic` (6 tests)
  - `TestSeparacionLogIncidencias` (3 tests) — P-06
  - `TestTruncamientoNombresLargos` (5 tests) — P-08
  - `TestFinalizarTorneo` (11 tests) — P-09
  - `TestExportarCsvSesion` (6 tests) — exportacion al finalizar

**Criterio de aceptacion:** los 87 tests pasan. En particular:
- `TestExportarCsvSesion` confirma que al finalizar se generan
  los CSV por sala en `data/sesiones/`.
- `TestFinalizarTorneo` confirma el cierre ordenado en los tres
  modos (torneo, laboratorio, consulta).
- `TestAutenticacionBasic` confirma que sin credenciales se
  obtiene HTTP 401 y con credenciales validas HTTP 200.

---

### Bloque 6: Creación de salas MUC

**Qué verifica:** carga de ficheros YAML de configuración de
salas (laboratorio, torneo) y creación de salas MUC por modo.

**Comando:**

```bash
pytest tests/test_creacion_salas.py -v
```

**Resultado esperado:**

- Todos los tests con estado `PASSED`.
- Línea final: `13 passed`.

**Criterio de aceptación:** los 13 tests pasan. Esto confirma
que la configuración de salas se lee correctamente y que los
modos de ejecución (laboratorio, torneo) generan las salas
esperadas.

---

## Parte II — Pruebas de integración

Las pruebas de integración arrancan agentes SPADE reales
(supervisor + tableros simulados + jugadores simulados) contra
un servidor XMPP. Requieren que el servidor esté accesible.

### Requisitos previos para integración

```bash
# Verificar que el servidor XMPP está accesible
# (el perfil se lee de config/config.yaml)
python -c "
import socket
s = socket.create_connection(('localhost', 5222), timeout=5)
s.close()
print('Servidor XMPP accesible')
"

# Para usar el servidor local (Docker):
XMPP_PERFIL=local

# Para usar el servidor de la asignatura:
XMPP_PERFIL=servidor
```

Si el servidor no está disponible, todos los tests de integración
se omiten automáticamente con un mensaje indicando el host y
puerto intentados.

**Comando general para ejecutar TODAS las pruebas de integración:**

```bash
pytest tests/test_integracion_supervisor.py -v
```

**Resultado esperado:** la línea final debe indicar
`N passed` (posiblemente con algunos `skipped` si el servidor
no esta disponible). El numero total esperado es **40 tests**.

---

### Bloque 7: Partidas normales

**Qué verifica:** el supervisor recibe correctamente los informes
de partidas que terminan con victoria, empate y abortada.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestPartidaNormal -v
```

**Resultado esperado:**

- 3 tests con estado `PASSED` (o `SKIPPED` si no hay servidor).
- `test_partida_victoria`: el informe tiene `result=win`,
  `winner=X`.
- `test_partida_empate`: el informe tiene `result=draw`,
  `winner=None`.
- `test_partida_abortada`: el informe tiene `result=aborted`,
  `reason=both-timeout`.

**Criterio de aceptación:** los 3 resultados coinciden con los
modos del tablero simulado.

---

### Bloque 8: Protocolo de dos pasos (AGREE + INFORM)

**Qué verifica:** el protocolo FIPA-Request funciona cuando el
tablero responde primero con AGREE y luego con INFORM.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestProtocoloDePasos -v
```

**Resultado esperado:**

- 1 test con estado `PASSED`.
- El informe se recibe correctamente tras la secuencia
  AGREE → INFORM.

**Criterio de aceptación:** el supervisor maneja correctamente
la respuesta en dos pasos sin perder el informe.

---

### Bloque 9: Escenarios de error

**Qué verifica:** el supervisor gestiona correctamente los
escenarios de error sin interrumpir su ejecución.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestErrores -v
```

**Resultado esperado:**

- 5 tests con estado `PASSED`.
- `test_timeout_sin_respuesta`: evento `LOG_TIMEOUT` en el log,
  sin informes almacenados.
- `test_json_invalido`: evento `LOG_ERROR` en el log.
- `test_esquema_invalido`: evento `LOG_ERROR` en el log.
- `test_refuse`: evento `LOG_ADVERTENCIA` en el log.
- `test_informes_pendientes_al_detener`: evento `LOG_ADVERTENCIA`
  al detener el supervisor con FSMs en curso.

**Criterio de aceptación:** ningún error provoca una excepción
no controlada. Los eventos de error/advertencia se registran
correctamente en el log de la sala.

---

### Bloque 10: Presencia MUC

**Qué verifica:** la detección de entradas, salidas y cambios de
estado de los agentes en las salas MUC.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestPresenciaMUC -v
```

**Resultado esperado:**

- 3 tests con estado `PASSED`.
- `test_entrada_de_agentes`: tablero y jugador aparecen como
  ocupantes.
- `test_salida_de_agente`: evento `LOG_SALIDA` registrado.
- `test_cambio_estado_tablero_en_log`: los estados `waiting` y
  `playing` aparecen en el detalle de los eventos.

**Criterio de aceptación:** las presencias MUC se detectan en
tiempo real y se reflejan en los ocupantes y el log.

---

### Bloque 11: Múltiples salas

**Qué verifica:** el supervisor gestiona dos salas de forma
independiente con sus propios informes y ocupantes.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestMultiplesSalas -v
```

**Resultado esperado:**

- 1 test con estado `PASSED`.
- Sala A tiene informe de victoria; sala B tiene informe de empate.

**Criterio de aceptación:** los datos de cada sala son
independientes y no se mezclan.

---

### Bloque 12: API web

**Qué verifica:** el dashboard web expone correctamente el estado
a través de la API HTTP.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestAPIWeb -v
```

**Resultado esperado:**

- 2 tests con estado `PASSED`.
- `test_api_state_con_informe`: la respuesta JSON contiene el
  informe con resultado `victoria`.
- `test_api_state_con_ocupantes`: la respuesta JSON contiene el
  jugador como ocupante.

**Criterio de aceptación:** la API HTTP devuelve datos coherentes
con el estado interno del supervisor.

---

### Bloque 13: Visibilidad progresiva de salas

**Qué verifica:** las salas aparecen en la API conforme los
alumnos se conectan y persisten tras desconectarse.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestVisibilidadProgresivaSalas -v
```

**Resultado esperado:**

- 4 tests con estado `PASSED`.
- Las salas sin agentes no tienen ocupantes.
- Las salas aparecen progresivamente.
- Una sala con actividad pasada persiste aunque todos los agentes
  se desconecten.
- Las salas sin actividad no se persisten en SQLite.

**Criterio de aceptación:** el comportamiento de visibilidad
progresiva es correcto tanto en la API en vivo como en la
persistencia.

---

### Bloque 14: Escenarios LLM

**Qué verifica:** el supervisor gestiona correctamente las partidas
donde algún jugador usa estrategia LLM (nivel 4).

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestEscenariosLLM -v
```

**Resultado esperado:**

- 4 tests con estado `PASSED`.
- Abortada por timeout LLM: `reason=timeout`, rival gana.
- Abortada por movimiento inválido: `reason=invalid`.
- Ambos LLM timeout: `reason=both-timeout`, `winner=None`.
- Victoria normal con jugador IA: informe estándar, ambos
  jugadores visibles.

**Criterio de aceptación:** los informes reflejan correctamente
los motivos de fallo del LLM.

---

### Bloque 15: Incidencias semánticas

**Qué verifica:** el supervisor detecta y registra anomalías
semánticas en informes que pasan la validación de esquema.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestIncidenciasSemanticas -v
```

**Resultado esperado:**

- 6 tests de `TestIncidenciasSemanticas` con estado `PASSED`.
- Cada anomalia genera al menos un evento `LOG_INCONSISTENCIA`:
  - Turnos anomalos (2 turnos para victoria).
  - Victoria sin linea ganadora en el tablero.
  - Jugador contra si mismo (`players.X == players.O`).
  - Empate con celdas vacias.
  - Jugadores no observados en la sala.
- Las incidencias son visibles en la API HTTP.
- 3 tests adicionales de `TestIncidenciasV8V11`:
  - V8: empate con fichas desequilibradas (3X+6O).
  - V9: victoria con turnos que no coinciden con fichas.
  - V11: empate con O moviendo primero (4X+5O).

**Criterio de aceptacion:** todas las anomalias semanticas se
detectan y aparecen en el log con tipo `inconsistencia`.

---

### Bloque 16: Reintento con retroceso exponencial

**Qué verifica:** el supervisor reintenta la solicitud de informe
cuando el tablero no responde la primera vez.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestReintentoConRetroceso -v
```

**Resultado esperado:**

- 1 test con estado `PASSED`.
- El informe se recibe en el segundo intento.
- El log contiene un `LOG_TIMEOUT` parcial y un
  `LOG_ADVERTENCIA` de reintento.

**Criterio de aceptación:** el mecanismo de reintento recupera
informes de tableros que fallan temporalmente. **Nota:** este test
puede tardar ~30 segundos por las esperas de timeout + retroceso.

---

### Bloque 17: Carga con múltiples tableros

**Qué verifica:** el supervisor gestiona correctamente 10 tableros
finalizando casi simultáneamente con la cola de solicitudes activa.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestCargaMultiplesTableros -v
```

**Resultado esperado:**

- 1 test con estado `PASSED`.
- Se reciben los 10 informes completos.
- La cola queda vacía al final.

**Criterio de aceptación:** ningún informe se pierde. La cola
de solicitudes y el límite de FSMs concurrentes funcionan
correctamente bajo carga. **Nota:** este test puede tardar
~45 segundos.

---

### Bloque 18: Ejecuciones pasadas

**Qué verifica:** el flujo completo de persistir una ejecución,
consultarla vía HTTP y exportarla como CSV.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestEjecucionesPasadasCompleto -v
```

**Resultado esperado:**

- 2 tests con estado `PASSED`.
- `test_ejecucion_pasada_filtra_salas_inactivas`: la sala sin
  actividad no aparece en la respuesta HTTP.
- `test_csv_ejecucion_pasada`: el CSV contiene las cabeceras
  y al menos 2 alumnos.

**Criterio de aceptacion:** las ejecuciones pasadas se consultan
correctamente con el filtrado de salas inactivas funcionando.

---

### Bloque 19: Solicitudes duplicadas (S-01/P-01)

**Que verifica:** el supervisor no genera solicitudes duplicadas
cuando un tablero permanece en `"finished"` y se producen
redistribuciones de presencia XMPP. Tambien verifica que un
ciclo completo de dos partidas genera exactamente dos informes.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestSolicitudesDuplicadasS01 -v
```

**Resultado esperado:**

- 2 tests con estado `PASSED`.
- `test_finished_no_genera_duplicados`: solo 1 solicitud.
- `test_ciclo_completo_dos_partidas`: exactamente 2 solicitudes.

**Criterio de aceptacion:** no se crean FSMs duplicados por
redistribuciones. Verificar en la traza persistente (SQLite)
que los eventos `LOG_SOLICITUD` son exactamente los esperados.

**Comprobacion manual en datos persistentes:**

```bash
python supervisor_main.py --modo consulta --db data/integracion.db
```

En el dashboard, seleccionar la ejecucion del test y verificar
que la pestaña Log de la sala muestra exactamente 1 (o 2)
eventos de solicitud, sin duplicados.

---

### Bloque 20: Duplicados por contenido (P-05)

**Que verifica:** dos partidas con el mismo resultado pero
threads distintos no se marcan como duplicadas.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestDuplicadosPorContenidoP05 -v
```

**Resultado esperado:**

- 1 test con estado `PASSED`.
- Sin eventos `LOG_INCONSISTENCIA` con texto "duplicado".

**Criterio de aceptacion:** la deteccion de duplicados se basa
en el thread, no en el contenido del informe.

---

### Bloque 21: Jugador que abandona (P-04)

**Que verifica:** un jugador que abandona la sala despues de la
partida no genera falsos positivos en la validacion de jugadores
observados, gracias al historico de ocupantes.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestJugadorAbandonaP04 -v
```

**Resultado esperado:**

- 1 test con estado `PASSED`.
- Sin eventos `LOG_INCONSISTENCIA` con texto "observado".

**Criterio de aceptacion:** el historico de ocupantes evita
falsos positivos cuando un jugador se desconecta.

---

### Bloque 22: Validaciones V8-V11 (P-07)

**Que verifica:** el supervisor detecta las anomalias de
equilibrio de fichas, coherencia turns-vs-board y convencion
X-primero con agentes SPADE reales.

**Comando:**

```bash
pytest tests/test_integracion_supervisor.py::TestIncidenciasV8V11 -v
```

**Resultado esperado:**

- 3 tests con estado `PASSED`.
- Cada anomalia genera al menos un evento `LOG_INCONSISTENCIA`.

**Criterio de aceptacion:** las validaciones V8-V11 funcionan
end-to-end con el tablero simulado y se registran en la
persistencia.

---

## Verificacion completa

Para confirmar que todo el proyecto está correcto, ejecutar
ambas baterías en secuencia:

```bash
# 1. Pruebas unitarias (sin servidor XMPP)
pytest tests/ --ignore=tests/test_integracion_supervisor.py -v

# 2. Pruebas de integración (con servidor XMPP)
pytest tests/test_integracion_supervisor.py -v

# 3. Todas las pruebas juntas
pytest tests/ -v
```

**Criterio de aceptacion global:**

- **Pruebas unitarias:** 409 passed, 0 failed.
- **Pruebas de integracion:** 40 passed, 0 failed (o skipped
  si el servidor no esta disponible).
- **Total:** 449 passed.

Si algún test falla, anotar:
1. El nombre completo del test que falla.
2. El mensaje de error (las últimas 10 líneas de la salida).
3. Si el fallo es reproducible ejecutando solo ese test.

---

## Registro de ejecución

| Fecha | Evaluador | Unitarios | Integracion | Observaciones |
|-------|-----------|-----------|-------------|---------------|
|       |           |   /409    |    /40      |               |
|       |           |   /409    |    /40      |               |
|       |           |   /409    |    /40      |               |
