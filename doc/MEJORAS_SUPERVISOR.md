# Deficiencias y plan de mejoras — Agente Supervisor

**Proyecto:** Tic-Tac-Toe Multiagente

**Asignatura:** Sistemas Multiagente — Universidad de Jaén

**Fecha:** 2026-04-10 (creación) · 2026-04-12 (última revisión)

**Rama:** `feature/agente-supervisor`

---

## Índice

1. [Deficiencias identificadas](#1-deficiencias-identificadas)
   - 1.1 [Protocolo y comunicación](#11-protocolo-y-comunicación)
   - 1.2 [Persistencia y datos](#12-persistencia-y-datos)
   - 1.3 [Panel web](#13-panel-web)
   - 1.4 [Robustez operativa](#14-robustez-operativa)
   - 1.5 [Tests](#15-tests)
2. [Plan de mejoras](#2-plan-de-mejoras)
   - 2.1 [Prioridad alta](#21-prioridad-alta)
   - 2.2 [Prioridad media](#22-prioridad-media)
   - 2.3 [Prioridad baja](#23-prioridad-baja)
3. [Matriz de trazabilidad](#3-matriz-de-trazabilidad)
4. [Nuevas deficiencias identificadas](#nuevas-deficiencias-identificadas)

---

## 1. Deficiencias identificadas

### 1.1 Protocolo y comunicación

**D-01. ~~Un único informe por tablero y sala en memoria.~~ (resuelta)**
Resuelta en M-01. `informes_por_sala[sala_id][jid_tablero]` es ahora
una lista (`list[dict]`) que acumula todos los informes del tablero.
El dashboard, la clasificación en vivo, el almacén SQLite y los
handlers web operan con la nueva estructura.

**D-02. ~~Sin reintento tras timeout.~~ (resuelta)**
Resuelta en M-04. Retroceso exponencial con reintentos configurables
(por defecto 2). Cada reintento registra `LOG_ADVERTENCIA` +
`LOG_SOLICITUD`.

**D-03. Detección de tableros finalizados solo por presencia.**
El supervisor depende exclusivamente de la stanza de presencia MUC
con `status="finished"` para detectar tableros que han terminado su
partida. Si la presencia se pierde (desconexión temporal, stanza
no entregada), el supervisor nunca solicitará el informe.

*Impacto:* en redes inestables o con alta latencia, las stanzas de
presencia pueden perderse. No hay mecanismo de reconciliación que
permita al supervisor descubrir partidas finalizadas que no detectó
en tiempo real.

**D-04. ~~Sin correlación entre informes y partidas observadas.~~ (resuelta)**
Resuelta en M-13. Validación semántica cruzada que detecta
jugadores no observados, turnos imposibles, tablero sin línea
ganadora, empate con celdas vacías, jugador contra sí mismo e
informes duplicados.

### 1.2 Persistencia y datos

**D-05. Sin exportación de datos.**
Los datos se almacenan en SQLite y solo son accesibles a través del
panel web. No existe funcionalidad para exportar los resultados a
CSV, JSON u otro formato que permita procesarlos externamente
(hojas de cálculo, scripts de análisis, actas de evaluación).

*Impacto:* el profesor debe transcribir manualmente los resultados
del panel web para generar las actas de evaluación del torneo.

**D-06. Sin compactación de la base de datos.**
Cada evento de presencia genera un INSERT en la tabla `eventos`.
En una sesión con 30 salas activas durante 2 horas, la tabla puede
acumular miles de eventos de entrada, salida y cambio de estado que
tienen valor informativo limitado tras finalizar la sesión.

*Impacto:* el fichero SQLite crece indefinidamente. En sesiones
prolongadas, las consultas de ejecuciones pasadas pueden ralentizarse.

**D-07. Commit por cada escritura.**
Tanto `guardar_informe()` como `guardar_evento()` ejecutan un
`COMMIT` inmediato tras cada INSERT. Esto garantiza durabilidad
pero penaliza el rendimiento en escrituras frecuentes.

*Impacto:* con muchas salas activas simultáneamente, las escrituras
frecuentes de eventos de presencia generan una carga de E/S
innecesaria. Un modelo de commit por lotes mejoraría el rendimiento
sin sacrificar durabilidad significativa.

### 1.3 Panel web

**D-08. Sin notificaciones en tiempo real (solo polling).**
El panel web consulta el estado cada 5 segundos mediante polling
HTTP. No utiliza WebSockets ni Server-Sent Events (SSE). Esto
introduce una latencia de hasta 5 segundos entre un evento real
y su aparición en el panel.

*Impacto:* en demostraciones en clase, el profesor puede explicar un
evento que aún no ha aparecido en el panel. Con SSE, los eventos
serían prácticamente instantáneos.

**D-09. Sin paginación en el log de eventos.**
El panel renderiza todos los eventos del log de una sala en una
única lista. En sesiones largas con decenas de partidas, la lista
puede contener cientos de entradas que se renderizan completas en
cada ciclo de polling.

*Impacto:* en sesiones prolongadas, el renderizado del panel puede
volverse lento y el scroll del log dificulta encontrar eventos
concretos.

**D-10. Clasificación limitada a victoria/derrota.**
La clasificación del panel calcula un ranking basado en victorias,
derrotas, empates y partidas abortadas. No distingue entre
estrategias de juego (nivel 1-4) ni ofrece estadísticas avanzadas
como la media de turnos por victoria, la tasa de partidas como X
frente a O, o la evolución temporal del rendimiento.

*Impacto:* el profesor no puede evaluar la calidad de la estrategia
de un alumno más allá del resultado binario (gana/pierde).

**D-11. ~~Sin autenticación ni control de acceso.~~ (resuelta)**
Resuelta en M-10. Middleware HTTP Basic configurable con
`auth_usuario` y `auth_contrasena` en `config_parametros`.
Los estáticos no requieren autenticación.

### 1.4 Robustez operativa

**D-12. ~~Sin reconexión automática a salas MUC.~~ (resuelta)**
Resuelta en M-11. Handlers de `disconnected` y `session_start`
en slixmpp que reenvían los joins MUC. Cada reconexión genera
`LOG_ADVERTENCIA` visible en la pestaña de Incidencias.

**D-13. ~~Timeout fijo de 10 segundos no configurable.~~ (resuelta)**
Resuelta en M-02. El timeout se lee de
`config_parametros["timeout_respuesta"]` (por defecto 10 s) y se
pasa al FSM vía el contexto. Configurable desde `agents.yaml`.

**D-14. ~~Sin límite de FSMs concurrentes.~~ (resuelta)**
Resuelta con cola de solicitudes y límite configurable
`max_fsm_concurrentes` (por defecto 15). Los tableros que
finalizan cuando el límite está alcanzado se encolan en
`tableros_en_cola` (FIFO) y se procesan conforme los FSMs
activos terminan. Al detener el supervisor, los encolados se
registran como advertencia.

*Impacto:* aunque en la práctica SPADE gestiona bien la
concurrencia de behaviours, no existe un mecanismo explícito de
control que proteja contra situaciones extremas (por ejemplo,
100 tableros finalizando al mismo tiempo en una configuración
atípica).

**D-18. ~~Expulsión de salas MUC por inactividad de la conexión.~~ (resuelta)**
En sesiones de laboratorio prolongadas, los agentes eran expulsados
de las salas MUC sin haber finalizado. La causa era doble: (1) el
keepalive de slixmpp se enviaba cada 300 s (5 minutos), insuficiente
para mantener viva la conexión TCP a través de firewalls/NAT de la
red universitaria que cierran conexiones inactivas a los 60-120 s;
(2) la configuración de Prosody en sinbad2 no incluía
`c2s_idle_timeout` explícito, delegando en el comportamiento por
defecto que puede cerrar sesiones inactivas.

*Solución aplicada:* reducido el intervalo de keepalive a 60 s en
`agente_supervisor.py` (`self.client.whitespace_keepalive_interval = 60`).
La solución complementaria en el servidor (añadir
`c2s_idle_timeout = 3600` a la configuración de Prosody en sinbad2)
debe aplicarse por el administrador del servidor.

### 1.5 Tests

**D-15. ~~Sin test de reconexión MUC.~~ (resuelta)**
Resuelta en M-11 (tests unitarios) y M-14 (tests de integración).
5 tests unitarios del handler de reconexión en
`test_agente_supervisor.py`.

**D-16. ~~Sin test de carga con múltiples tableros simultáneos.~~ (resuelta)**
Resuelta en M-14. Test de integración con 10 tableros simultáneos
en `TestCargaMultiplesTableros` que verifica la cola de solicitudes
y la recopilación completa de informes.

**D-17. ~~Cobertura de la persistencia en ejecuciones históricas.~~ (resuelta)**
Resuelta en M-14. Tests de integración en
`TestEjecucionesPasadasCompleto` que verifican el flujo completo:
endpoint HTTP de ejecución pasada con filtrado de salas sin
actividad, y exportación CSV de ejecuciones históricas.

---

## 2. Plan de mejoras

### 2.1 Prioridad alta

Mejoras que resuelven problemas que afectan directamente a la
funcionalidad del supervisor en sesiones de laboratorio reales.

#### M-01. Lista de informes por tablero (resuelve D-01) — ✅ Implementada

`informes_por_sala[sala_id][jid_tablero]` es ahora `list[dict]`.
Cada informe se añade con `append()`. Cambios realizados:

- `agente_supervisor.py`: tipo `dict[str, dict[str, list[dict]]]`.
- `supervisor_behaviours.py`: `EstadoProcesarInforme` crea la lista
  si no existe y añade con `append()`.
- `supervisor_handlers.py`: `_convertir_informes()` itera sobre
  listas y aplana a lista plana para el dashboard.
- `almacen_supervisor.py`: `obtener_informes_ejecucion()` devuelve
  listas por tablero.
- `supervisor.js`: sin cambios (ya consumía lista plana del API).
- Tests: adaptados todos los accesos + nuevo test
  `test_multiples_informes_mismo_tablero` en handlers.

#### M-02. Timeout configurable (resuelve D-13) — ✅ Implementada

El timeout se lee de `config_parametros["timeout_respuesta"]`
(por defecto 10 s) y se pasa al FSM vía `ctx["timeout"]`.
Cambios realizados:

- `agente_supervisor.py`: lee `timeout_respuesta` de config,
  lo pasa como parámetro a `SolicitarInformeFSM`.
- `supervisor_behaviours.py`: `SolicitarInformeFSM.__init__`
  acepta `timeout`, los estados de espera y el log usan
  `ctx["timeout"]`. `TIMEOUT_RESPUESTA` se mantiene como
  valor por defecto.
- Tests: contexto mock incluye `"timeout"`, fixture de agente
  incluye `timeout_respuesta`.

Configurable en `agents.yaml`:
```yaml
parametros:
  timeout_respuesta: 20  # Más tiempo para tableros con LLM
```

#### M-03. Exportación de resultados a CSV (resuelve D-05) — ✅ Implementada

Tres tipos de exportación CSV, disponibles tanto para el estado
en vivo como para ejecuciones pasadas:

- **Clasificación** (`ranking`): alumno, partidas, victorias,
  derrotas, empates, abortadas, win_rate. Lógica de ranking
  replicada del JS (`computarRanking`) en Python
  (`_computar_ranking`).
- **Log completo** (`log`): timestamp, tipo, origen, detalle.
  Todos los eventos de la sala.
- **Incidencias** (`incidencias`): mismo formato que el log pero
  filtrado a los tipos de severidad alta (error, advertencia,
  timeout, abortada, inconsistencia).

**Endpoints:**
- `GET /supervisor/api/csv/{tipo}?sala={id}` — estado en vivo.
- `GET /supervisor/api/ejecuciones/{id}/csv/{tipo}?sala={id}` —
  ejecución pasada.

**Cambios realizados:**
- `supervisor_handlers.py`: funciones `_computar_ranking()`,
  `_generar_csv_ranking()`, `_generar_csv_log()`,
  `_generar_csv_incidencias()`, `_obtener_datos_sala()`,
  `_obtener_datos_sala_historica()`, `_respuesta_csv()`.
  Handlers `handler_csv_en_vivo()` y `handler_csv_ejecucion()`.
  Rutas registradas en `registrar_rutas_supervisor()`.
- `supervisor.js`: función `construirUrlCsv()`, `descargarCsv()`.
  Botón «⬇ CSV» en los paneles de Clasificación, Log e
  Incidencias.
- `supervisor.css`: estilo `.sv-csv-btn`.
- Tests: 22 tests nuevos en `test_supervisor_handlers.py`
  (5 ranking puro + 5 generación CSV + 6 endpoints en vivo +
  4 endpoints ejecución pasada + 2 log/incidencias CSV).

### 2.2 Prioridad media

Mejoras que aportan robustez o mejor experiencia de uso pero que
no bloquean el funcionamiento actual.

#### M-04. Reintento con retroceso exponencial (resuelve D-02) — ✅ Implementada

Cuando `EstadoRegistrarTimeout` se activa y quedan reintentos
disponibles, transiciona a un nuevo estado `ST_REINTENTAR` que
espera un intervalo creciente (timeout × 2^n) y vuelve a enviar
el REQUEST. Tras agotar los reintentos (configurable, por defecto
2), registra el timeout definitivo.

No se crea un tipo de evento nuevo. Cada reintento registra:
- `LOG_ADVERTENCIA`: para que aparezca en la pestaña de
  Incidencias con el detalle del reintento.
- `LOG_SOLICITUD`: la nueva solicitud de informe.

**Cambios realizados:**
- `supervisor_behaviours.py`: constantes `MAX_REINTENTOS` (2),
  `FACTOR_RETROCESO` (2), `ST_REINTENTAR`. Nuevo estado
  `EstadoReintentar` con espera exponencial y reenvío del
  REQUEST. `EstadoRegistrarTimeout` modificado para transicionar
  a `ST_REINTENTAR` cuando `reintentos < max_reintentos`.
  `SolicitarInformeFSM.__init__` acepta `max_reintentos`.
  `SolicitarInformeFSM.setup()` registra el nuevo estado y
  transiciones `REGISTRAR_TIMEOUT → REINTENTAR` y
  `REINTENTAR → ESPERAR_RESPUESTA`.
- `agente_supervisor.py`: lee `max_reintentos` de
  `config_parametros` y lo pasa al FSM.
- Tests: 11 tests unitarios nuevos (`TestRegistrarTimeoutConReintentos`
  + `TestEstadoReintentar`) + 1 test de integración con
  `TableroSimulado` en modo `timeout_luego_victoria`.

Configurable en `agents.yaml`:
```yaml
parametros:
  max_reintentos: 3  # Más reintentos para tableros con LLM
```

#### M-05. Server-Sent Events para actualizaciones en vivo (resuelve D-08) — ✅ Implementada

El polling HTTP de 5 segundos se sustituye por SSE como canal
principal, con fallback automático a polling cuando SSE no está
disponible.

**Arquitectura:**
- El servidor mantiene una lista de colas de suscriptores SSE
  a nivel de módulo (`_suscriptores_sse`).
- `registrar_evento_log()` del agente invoca `notificar_sse()`
  cada vez que se produce un cambio, depositando el evento en
  todas las colas activas.
- El handler SSE envía el estado completo como primer evento
  y luego transmite eventos incrementales.
- Un keepalive cada 15 s mantiene la conexión abierta a través
  de proxies y firewalls.

**Cambios realizados:**
- `supervisor_handlers.py`: lista `_suscriptores_sse`, función
  `notificar_sse()`, handler `handler_sse_stream()`, función
  `_construir_estado_json()`. Ruta `/supervisor/api/stream`.
- `agente_supervisor.py`: `registrar_evento_log()` invoca
  `notificar_sse()` tras cada evento.
- `supervisor.js`: funciones `iniciarSSE()`, `detenerSSE()`,
  `procesarDatosEstado()`. Estado `sseConectado` y variable
  `fuenteSSE`. Polling como fallback solo cuando SSE no está
  conectado. SSE se detiene al cambiar a modo histórico.
- Tests: 4 tests nuevos (`TestNotificarSSE` +
  `TestHandlerSSE`).

#### M-06. Paginación del log y pestaña de Incidencias (resuelve D-09) — ✅ Implementada

Implementación en dos partes:

**A. Paginación del log (D-09):**
El panel de Log renderiza un máximo de 50 eventos con un botón
«Cargar más» que incrementa la ventana en bloques de 50. El estado
`logEventosMostrados` se resetea al cambiar de sala. Se muestra
el contador «N de M eventos».

**B. Pestaña de Incidencias (nueva):**
Nueva quinta pestaña en el panel que filtra y agrupa los eventos
de severidad alta: `error`, `advertencia`, `timeout`, `abortada`
e `inconsistencia`. Presenta un resumen visual con contadores por
tipo y una lista cronológica de todas las incidencias. Esto separa
la trazabilidad completa (Log) del diagnóstico (Incidencias).

**Cambios realizados:**
- `supervisor.js`: nueva función `renderIncidenciasPanel()`,
  constante `TIPOS_INCIDENCIA`, función `contarIncidencias()`,
  `renderLogPanel()` con paginación y función `cargarMasLog()`.
  Estado `logEventosMostrados` en el objeto `estado` global.
  Nuevo tipo `inconsistencia` en `obtenerConfigLog()`.
- `supervisor.css`: estilos `.sv-incidencias-resumen`,
  `.sv-incidencia-badge`, `.sv-log-paginacion`, `.sv-log-btn-mas`.
- `renderTabs()`: nueva pestaña `incidencias` con contador.
- `renderPanelActivo()`: despacha a `renderIncidenciasPanel()`.

#### M-07. Reconciliación periódica de salas MUC (resuelve D-03)

Añadir un mecanismo periódico (cada 60 s) que envíe una solicitud
de descubrimiento XEP-0030 a cada sala y compare los ocupantes
descubiertos con los que el supervisor tiene en memoria. Si detecta
tableros con `status="finished"` que no fueron procesados, crea
el FSM correspondiente.

**Cambios necesarios:**
- `agente_supervisor.py`: nuevo behaviour periódico de
  reconciliación.
- Tests de integración para el escenario de presencia perdida.

**Esfuerzo estimado:** alto (depende del soporte de XEP-0030 del
servidor XMPP).

#### M-08. Commits por lotes en la persistencia (resuelve D-07) — ✅ Implementada

Las escrituras (`guardar_informe` y `guardar_evento`) se acumulan
sin COMMIT inmediato. Un contador `_escrituras_pendientes` lleva
la cuenta y ejecuta COMMIT automático al alcanzar el tamaño de
lote configurable (`tamanio_lote`, por defecto 20).

La durabilidad se garantiza con flush forzado en:
- `finalizar_ejecucion()` — antes de marcar el cierre.
- `cerrar()` — antes de cerrar la conexión.
- `flush_buffer()` — invocable explícitamente.

Con `tamanio_lote=1` se recupera el comportamiento anterior
(COMMIT en cada escritura), útil para depuración.

**Cambios realizados:**
- `almacen_supervisor.py`: constante `TAMANIO_LOTE` (20),
  parámetro `tamanio_lote` en constructor, atributos
  `_tamanio_lote` y `_escrituras_pendientes`, métodos
  `_registrar_escritura()` y `flush_buffer()`.
  `guardar_informe()` y `guardar_evento()` ya no hacen
  `commit()` directo. `finalizar_ejecucion()` y `cerrar()`
  invocan `flush_buffer()` antes de operar.
- Tests: 9 tests nuevos en `TestCommitsPorLotes`.

### 2.3 Prioridad baja

Mejoras deseables a largo plazo pero que no afectan al uso
inmediato del supervisor en la asignatura.

#### M-09. Estadísticas avanzadas en la clasificación (resuelve D-10)

Ampliar la clasificación con métricas adicionales:
- Media de turnos por victoria (eficiencia de la estrategia).
- Tasa de victoria como X frente a como O.
- Evolución temporal (gráfico de victorias acumuladas).
- Detección de la estrategia utilizada (si el tablero informa del
  nivel).

**Esfuerzo estimado:** medio.

#### M-10. Autenticación HTTP Basic (resuelve D-11) — ✅ Implementada

Middleware aiohttp que comprueba `Authorization: Basic` en cada
petición. Las credenciales se configuran en `agents.yaml` con
`auth_usuario` y `auth_contrasena`. Si no se configuran, el panel
queda sin protección (retrocompatible). Los ficheros estáticos
(CSS, JS) no requieren autenticación.

**Cambios realizados:**
- `supervisor_handlers.py`: función `crear_middleware_auth()`
  que genera un middleware aiohttp con validación Basic.
- `agente_supervisor.py`: lee `auth_usuario` y `auth_contrasena`
  de `config_parametros` y aplica el middleware si están presentes.
- Tests: 6 tests nuevos en `TestAutenticacionBasic`.

Configurable en `agents.yaml`:
```yaml
parametros:
  auth_usuario: "profesor"
  auth_contrasena: "clave_torneo"
```

#### M-11. Reconexión automática a salas MUC (resuelve D-12) — ✅ Implementada

Handlers de eventos `disconnected` y `session_start` en slixmpp.
Cuando la conexión se pierde, se activa un flag de reconexión.
Al restablecer la sesión, se reenvían los joins MUC a todas las
salas y se registra `LOG_ADVERTENCIA` en cada sala para que
aparezca en la pestaña de Incidencias con el mensaje de que los
ocupantes anteriores pueden no reflejarse hasta que vuelvan a
enviar presencia.

**Cambios realizados:**
- `agente_supervisor.py`: handlers `_on_desconexion()` y
  `_on_reconexion_sesion()`, flag `_reconexion_activa`.
  Registrados en `setup()` con `session_start` y `disconnected`.
- Tests: 5 tests unitarios en `TestReconexionMUC`.

#### M-12. Compactación de eventos en ejecuciones finalizadas (resuelve D-06)

Al finalizar una ejecución, eliminar eventos de presencia
redundantes (entradas y salidas de agentes que ya no aportan
información relevante) y conservar solo los eventos significativos
(informes, errores, advertencias, timeouts).

**Esfuerzo estimado:** bajo.

#### M-13. Validación semántica cruzada de informes (resuelve D-04) — ✅ Implementada

Cuando el supervisor recibe un informe que pasa la validación de
esquema, ejecuta validaciones semánticas adicionales y registra
eventos `LOG_INCONSISTENCIA` por cada anomalía detectada.

**Validaciones implementadas:**
- **Turnos anómalos**: victoria con < 5 turnos, partida con > 9.
- **Tablero sin línea ganadora**: resultado `"win"` pero no existe
  combinación ganadora en el tablero.
- **Empate con celdas vacías**: resultado `"draw"` con celdas
  sin rellenar.
- **Empate con línea ganadora oculta**: resultado `"draw"` pero
  existe una combinación ganadora.
- **Jugador contra sí mismo**: `players.X == players.O`.
- **Jugadores no observados (D-04)**: jugadores del informe que
  no fueron detectados como ocupantes de la sala MUC.
- **Informe duplicado**: mismo tablero, jugadores y resultado
  que un informe anterior del mismo tablero emisor.

**Cambios realizados:**
- `supervisor_behaviours.py`: nuevo tipo `LOG_INCONSISTENCIA`,
  constantes `MIN_TURNOS_VICTORIA`, `MAX_TURNOS`,
  `COMBINACIONES_GANADORAS`. Funciones `_validar_turnos()`,
  `_validar_tablero_resultado()`, `_hay_linea_ganadora()`,
  `_validar_jugador_contra_si_mismo()`,
  `_validar_jugadores_observados()`,
  `_validar_informe_duplicado()`, `validar_semantica_informe()`.
  `EstadoProcesarInforme.run()` invoca la validación tras
  almacenar el informe.
- `test_supervisor_behaviours.py`: 35 tests nuevos que cubren
  cada función de validación individual, la función agregadora y
  la integración con `EstadoProcesarInforme`.
- `test_integracion_supervisor.py`: 6 tests de integración con
  nuevos modos de `TableroSimulado` (`victoria_turnos_anomalos`,
  `victoria_sin_linea`, `jugador_contra_si_mismo`,
  `empate_celdas_vacias`).
- `tablero_simulado.py`: 4 informes nuevos con anomalías
  semánticas y sus modos de respuesta.

#### M-14. Tests de carga, reconexión y ejecuciones (resuelve D-15, D-16, D-17) — ✅ Implementada

**Tests implementados:**
- `TestCargaMultiplesTableros::test_diez_tableros_simultaneos`:
  10 tableros en una sala con `max_fsm_concurrentes=3` para
  forzar el uso de la cola. Verifica que se reciben los 10
  informes sin pérdidas (D-16).
- `TestReconexionMUC` (unitarios): 5 tests del handler de
  reconexión (`_on_desconexion`, `_on_reconexion_sesion`),
  verificando flag, rejoin, advertencias e idempotencia (D-15).
- `TestEjecucionesPasadasCompleto::test_ejecucion_pasada_filtra_salas_inactivas`:
  flujo completo de persistir, consultar vía HTTP y verificar
  que las salas sin actividad no aparecen (D-17).
- `TestEjecucionesPasadasCompleto::test_csv_ejecucion_pasada`:
  verificación de exportación CSV de una ejecución histórica.

---

## 3. Matriz de trazabilidad

| Deficiencia | Mejora | Prioridad | Estado |
|-------------|--------|-----------|--------|
| D-01 Un informe por tablero | M-01 Lista de informes | Alta | ✅ Implementada |
| D-02 Sin reintento tras timeout | M-04 Retroceso exponencial | Media | ✅ Implementada |
| D-03 Solo detección por presencia | M-07 Reconciliación periódica | Media | Pendiente |
| D-04 Sin validación cruzada | M-13 Validación semántica cruzada | Baja | ✅ Implementada |
| D-05 Sin exportación de datos | M-03 Exportación CSV | Alta | ✅ Implementada |
| D-06 Sin compactación de BD | M-12 Compactación de eventos | Baja | Pendiente |
| D-07 Commit por cada escritura | M-08 Commits por lotes (20) | Media | ✅ Implementada |
| D-08 Solo polling (5 s) | M-05 Server-Sent Events | Media | ✅ Implementada |
| D-09 Sin paginación en log | M-06 Paginación + Incidencias | Media | ✅ Implementada |
| D-10 Clasificación limitada | M-09 Estadísticas avanzadas | Baja | Pendiente |
| D-11 Sin autenticación | M-10 Autenticación HTTP Basic | Baja | ✅ Implementada |
| D-12 Sin reconexión MUC | M-11 Reconexión automática | Baja | ✅ Implementada |
| D-13 Timeout fijo (10 s) | M-02 Timeout configurable | Alta | ✅ Implementada |
| D-14 Sin límite de FSMs | Cola + límite configurable (15) | — | ✅ Resuelta |
| D-15 Sin test reconexión | M-11 + M-14 Tests unitarios + integración | Baja | ✅ Resuelta |
| D-16 Sin test de carga | M-14 Test 10 tableros simultáneos | Baja | ✅ Resuelta |
| D-17 Sin test ejecuciones pasadas | M-14 Tests endpoint + CSV | Baja | ✅ Resuelta |
| D-18 Expulsión MUC por inactividad | Keepalive 60 s + reconexión M-11 | Alta | ✅ Resuelta |

### Estado actual

De las **18 deficiencias** identificadas, **16 están resueltas**.
Las 2 pendientes son de prioridad baja:

- **D-03** (detección por presencia): requiere M-07 (reconciliación
  periódica XEP-0030), que depende del soporte del servidor XMPP.
  La reconexión M-11 mitiga parcialmente el problema.
- **D-06** (compactación de BD): requiere M-12. El impacto se
  reduce con M-08 (commits por lotes).

De las **14 mejoras** propuestas, **12 están implementadas**.
Las 2 pendientes son:

- **M-07** (reconciliación XEP-0030): esfuerzo alto, prioridad
  media. Depende del soporte de Service Discovery del servidor.
- **M-09** (estadísticas avanzadas): esfuerzo medio, prioridad
  baja. Deseable pero no bloquea la funcionalidad actual.

M-12 (compactación) queda como mejora potencial sin prioridad
inmediata.

### Nuevas deficiencias identificadas

La implementación de las mejoras ha revelado las siguientes
deficiencias nuevas:

**D-19. Credenciales de autenticación en texto plano.**
Las credenciales HTTP Basic (`auth_usuario`, `auth_contrasena`)
se almacenan en `agents.yaml` sin cifrar. Cualquier persona con
acceso al fichero de configuración puede leerlas.

*Impacto:* en un entorno de laboratorio la exposición es mínima
(el profesor controla el sistema), pero en un despliegue más
abierto sería necesario usar variables de entorno o un almacén
de secretos.

*Mitigación:* las credenciales podrían leerse de variables de
entorno en vez del fichero YAML. No se implementa por ahora
porque el contexto de uso (laboratorio universitario) no lo
requiere.

**D-20. Reconexión MUC sin reconciliación de ocupantes.**
Tras una reconexión automática (M-11), la lista de ocupantes
`ocupantes_por_sala` se mantiene con los datos previos a la
desconexión. Los agentes que se desconectaron durante la
interrupción pueden seguir apareciendo como conectados hasta
que el siguiente ciclo de presencia los actualice.

*Impacto:* durante el intervalo entre la reconexión y la
recepción de presencias actualizadas, el dashboard puede
mostrar ocupantes desactualizados. La advertencia de M-11
ya informa al profesor de esta limitación.

*Mitigación:* vaciar `ocupantes_por_sala` en la reconexión.
No se implementa porque podrían perderse ocupantes legítimos
que no hayan reenviado presencia aún. La reconciliación M-07
(XEP-0030) resolvería esto completamente.

**D-21. SSE sin autenticación independiente.**
El endpoint `/supervisor/api/stream` (SSE) queda protegido por
el middleware HTTP Basic como cualquier otra ruta. Sin embargo,
`EventSource` del navegador no permite enviar cabeceras
personalizadas. La autenticación funciona porque el navegador
envía las credenciales de la sesión HTTP automáticamente, pero
un cliente SSE externo (no navegador) no podría autenticarse.

*Impacto:* negligible en el contexto actual (solo el navegador
del profesor usa SSE), pero limita la integración con herramientas
externas de monitorización.

*Mitigación:* aceptar token como parámetro de query
(`/supervisor/api/stream?token=...`) como alternativa al header
Basic. No se implementa por ahora.

**Acción pendiente del administrador del servidor:** añadir
`c2s_idle_timeout = 3600` a la configuración de Prosody en sinbad2
para completar la solución de D-18 en el lado servidor.
