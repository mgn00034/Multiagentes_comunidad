# Carpeta `agentes/` — Clases de los agentes SPADE

## Propósito

Aquí residen las clases principales de los agentes del sistema
Tic-Tac-Toe Multiagente. Cada agente es una subclase de
`spade.agent.Agent` y su método `setup()` es el punto de entrada
donde se registran los comportamientos iniciales y se configura la
conexión a la sala MUC.

---

## Agentes del sistema

### Agente Tablero (`AgenteTablero`)

Gestiona una partida completa: inscripción de jugadores (FIPA
Request), ciclo de turnos (FIPA Contract Net), detección de resultado,
respuesta a solicitudes `game-report` del supervisor y exposición de
la interfaz web.

- **Fichero:** `agente_tablero.py`
- **Comportamientos:** registrados en [`behaviours/`](../behaviours/)

### Agente Jugador (`AgenteJugador`)

Busca tableros disponibles en la sala MUC, se inscribe en partidas,
crea dinámicamente comportamientos de partida y aplica su estrategia
de juego (posicional, reglas, minimax o LLM según configuración).

- **Fichero:** `agente_jugador.py`
- **Comportamientos:** registrados en [`behaviours/`](../behaviours/)

### Agente Supervisor (`AgenteSupervisor`)

Agente de solo lectura que observa las salas MUC, solicita informes
de partida a los tableros finalizados, persiste los datos en SQLite
y expone un panel web para el profesor.

- **Fichero:** `agente_supervisor.py`
- **Documentación completa:** [`DOCUMENTACION_SUPERVISOR.md`](../doc/DOCUMENTACION_SUPERVISOR.md)
  — Análisis y diseño del agente: arquitectura, estado interno,
  protocolo de comunicación, panel web, configuración, persistencia,
  gestión de torneos y pruebas.
- **Comportamientos:** documentados en
  [`behaviours/BEHAVIOURS_SUPERVISOR.md`](../behaviours/BEHAVIOURS_SUPERVISOR.md)
- **Persistencia:** documentada en
  [`persistencia/PERSISTENCIA_SUPERVISOR.md`](../persistencia/PERSISTENCIA_SUPERVISOR.md)
- **Interfaz web:** documentada en
  [`web/WEB_SUPERVISOR.md`](../web/WEB_SUPERVISOR.md)

### Agente Organizador (`AgenteOrganizador`)

Agente auxiliar que crea las salas MUC de los torneos definidos en
`config/torneos.yaml` y se mantiene conectado como ocupante de cada
una durante toda su ejecución. Implementa la **opción C** de gestión
de torneos. **Desactivado por defecto** (`activo: false`).

- **Fichero:** `agente_organizador.py`
- **Documentación completa:** [`DOCUMENTACION_ORGANIZADOR.md`](../doc/DOCUMENTACION_ORGANIZADOR.md)
  — Análisis y diseño del agente: contexto, arquitectura, estado
  interno, configuración de torneos, activación y extensiones futuras.

---

## Documentación de referencia

| Documento | Contenido |
|-----------|-----------|
| [`DOCUMENTACION_SUPERVISOR.md`](../doc/DOCUMENTACION_SUPERVISOR.md) | Arquitectura, protocolo FIPA-Request, panel web, persistencia SQLite, torneos y pruebas |
| [`DOCUMENTACION_ORGANIZADOR.md`](../doc/DOCUMENTACION_ORGANIZADOR.md) | Creación de salas MUC, configuración de torneos, opciones de gestión |
| [`../behaviours/BEHAVIOURS_SUPERVISOR.md`](../behaviours/BEHAVIOURS_SUPERVISOR.md) | Fichas técnicas de MonitorizarMUCBehaviour, SolicitarInformeFSM y función de presencia |
| [`../persistencia/PERSISTENCIA_SUPERVISOR.md`](../persistencia/PERSISTENCIA_SUPERVISOR.md) | Esquema SQLite, ciclo de vida, flujo de datos, API de métodos y decisiones de diseño |
| [`../web/WEB_SUPERVISOR.md`](../web/WEB_SUPERVISOR.md) | Análisis y diseño de la interfaz web del supervisor |

### Diagramas

Todos los diagramas SVG del proyecto se encuentran en
[`doc/svg/`](../doc/svg/):

| Diagrama | Fichero | Descripción |
|----------|---------|-------------|
| Arquitectura | [`arquitectura.svg`](../doc/svg/arquitectura.svg) | Tres niveles: servidor XMPP, agente supervisor y panel web |
| Flujo de datos | [`flujo-datos.svg`](../doc/svg/flujo-datos.svg) | Desde que un tablero finaliza hasta que el resultado se muestra |
| Protocolo | [`protocolo-informe-supervisor.svg`](../doc/svg/protocolo-informe-supervisor.svg) | Diagrama de secuencia FIPA-Request (4 casos) |
| Monitorización | [`behaviour-monitorizar-muc.svg`](../doc/svg/behaviour-monitorizar-muc.svg) | Diagrama de actividad del comportamiento periódico |
| FSM solicitud | [`behaviour-solicitar-informe.svg`](../doc/svg/behaviour-solicitar-informe.svg) | Máquina de estados (6 estados, 3 finales) |
| Disposición web | [`layout-general.svg`](../doc/svg/layout-general.svg) | Disposición general del panel |
| Informes | [`panel-informes.svg`](../doc/svg/panel-informes.svg) | Tarjetas de informe con filtros |
| Clasificación | [`panel-ranking.svg`](../doc/svg/panel-ranking.svg) | Clasificación con barras de porcentaje |
| Modal | [`modal-detalle.svg`](../doc/svg/modal-detalle.svg) | Ventana de detalle de informe |
| Consulta periódica | [`ciclo-polling.svg`](../doc/svg/ciclo-polling.svg) | Flujo de datos frontend ↔ backend |
| Interacciones | [`interacciones-usuario.svg`](../doc/svg/interacciones-usuario.svg) | Mapa de las 6 interacciones del usuario |
| Temas | [`temas-accesibilidad.svg`](../doc/svg/temas-accesibilidad.svg) | Paletas de color y tipografías |
| Esquema BD | [`persistencia-esquema.svg`](../doc/svg/persistencia-esquema.svg) | 3 tablas SQLite con claves foráneas |
| Ciclo vida BD | [`persistencia-ciclo-vida.svg`](../doc/svg/persistencia-ciclo-vida.svg) | Fases: init → crear → operar → finalizar → cerrar |
| Flujo persist. | [`persistencia-flujo-datos.svg`](../doc/svg/persistencia-flujo-datos.svg) | Escritura (agente → SQLite) y lectura (panel → SQLite) |

---

## Orientaciones de diseño

Cada agente debe limitarse a orquestar sus comportamientos y mantener su
estado interno. La lógica pesada (estrategia de juego, validación de
movimientos, detección de victoria) debe delegarse en módulos
separados (`estrategia/`, `behaviours/`, `ontologia/`) para facilitar
las pruebas aisladas.

El método `setup()` debe:

1. Inicializar el estado interno del agente (tablero vacío, lista de
   jugadores, historial de movimientos, etc.).
2. Registrar los comportamientos iniciales (ver carpeta `behaviours/`).
3. Unirse a la sala MUC con el apodo apropiado (`tablero_{id}` o
   `jugador_{nombre}`).
4. Arrancar el servidor web si es el Agente Tablero (ver carpeta
   `web/`).

Los parámetros de conexión (servidor XMPP, sala MUC, puerto web)
deben leerse de la configuración centralizada (ver carpeta `config/`),
nunca estar escritos directamente en el código.

## Recordatorio

- Toda clase pública necesita docstring en formato Google Style.
- Typing hints en todos los parámetros y retornos.
- Los agentes SPADE son asíncronos: todo en `async/await`.
