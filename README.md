# Tic-Tac-Toe con SPADE

**Asignatura:** Sistemas Multiagente — Grado en Ingeniería Informática

**Universidad de Jaén** — Departamento de Informática 

**Nivel:** 1 — Agentes FIPA con SPADE  

**Modalidad:** Individual y obligatoria  

**Curso académico:** 2025-2026

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

---

## 1. Descripción general

Esta práctica consiste en el diseño e implementación de un sistema multiagente en el que agentes autónomos juegan al Tic-Tac-Toe (tres en raya) utilizando el entorno SPADE v4.1.2 sobre XMPP. El sistema debe demostrar el uso de descubrimiento de servicios mediante salas MUC (Multi-User Chat), comunicación mediante mensajes FIPA-ACL, máquinas de estados finitos (FSM) y visualización web del estado del juego.

La práctica tiene **dos actividades asociadas** con evaluación independiente:

| Actividad | Tipo | Entregable                                | Evaluación |
|-----------|------|-------------------------------------------|------------|
| **Actividad 1** | Teoría | Documento de análisis y diseño (Markdown) | 5 a 10 (mínimo 5 para aprobar) |
| **Actividad 2** | Prácticas | Código fuente + tests ejecutables         | 5 a 10 (mínimo 5 para aprobar) |

Ambas actividades son **obligatorias**. Se necesita un mínimo de **5 en cada una** para considerarla válida. La calificación de cada actividad es independiente.

### 1.1. Material de referencia obligatorio

Antes de comenzar, el alumno debe estudiar los siguientes materiales disponibles en PLATEA:

- **Presentación «Tic-Tac-Toe Multiagente»**: describe la arquitectura, los protocolos, la ontología, los diagramas de secuencia, las FSM y la interfaz web.
- **Guía de Desarrollo de Proyectos de SMA**: explica las secciones obligatorias del documento de análisis y diseño.
- **Presentación de Ontología JSON Schema Runtime**: metodología de diseño con Pydantic y validación runtime con jsonschema.

---

## 2. Descripción del problema

Se debe implementar un sistema donde agentes autónomos juegan partidas de tres en raya. Los agentes no se conocen entre sí al inicio: deben descubrirse mediante una sala MUC del servidor XMPP. Las partidas se juegan mediante mensajes directos FIPA-ACL entre tableros y jugadores.

### 2.1. Tipos de agentes

El sistema está compuesto por exactamente **dos tipos de agentes** que el alumno debe implementar:

**Agente Tablero.** Representa una mesa de juego. Su responsabilidad se limita a registrar y representar en la cuadrícula 3x3 los movimientos que los jugadores le comunican, gestionar los turnos y exponer una interfaz web que muestra el estado del juego. La representación de la partida debe garantizar su seguimiento completo y la posibilidad de reproducción posterior. Cada tablero gestiona una única partida a la vez.

**Agente Jugador.** Es el que realmente sabe jugar al Tic-Tac-Toe: busca tableros disponibles en la sala MUC, se inscribe en partidas, aplica su estrategia de juego y envía movimientos válidos al tablero. Debe ser capaz de gestionar **al menos 3 partidas simultáneas** mediante comportamientos dinámicos independientes. Se asume que los jugadores actúan de buena fe y no realizan movimientos intencionadamente inválidos.

Existe un tercer tipo de agente, el **Agente Supervisor**, que será proporcionado por el profesor. Su función es observar las salas MUC y solicitar informes de partida a los tableros una vez finalizadas. Todo Agente Tablero **debe** implementar la capacidad de responder a las solicitudes `game-report` del Supervisor.

### 2.2. Reglas del sistema

- Los agentes no se conocen entre sí al inicio del sistema.
- Los jugadores descubren tableros disponibles mediante la sala MUC del servidor XMPP (mecanismo de descubrimiento obligatorio para esta práctica).
- Cada tablero gestiona una única partida: dos jugadores, turnos alternos, victoria por tres en línea, empate o no finalizada.
- Los jugadores pueden participar en múltiples partidas simultáneas (mínimo 3 demostradas).
- La ontología `"tictactoe"` es compartida y proporcionada por el profesor (incluida en este repositorio).
- Todo mensaje FIPA-ACL debe incluir los metadatos: `performative`, `ontology="tictactoe"` y `thread` (hilo de conversación).
- El sistema debe tolerar que los agentes arranquen en cualquier orden (requisito de robustez).

---

## 3. Arquitectura del sistema

### 3.1. Componentes principales

El sistema se apoya en la plataforma SPADE/XMPP para toda la infraestructura de comunicación. La novedad de este diseño es el uso de una **sala MUC** (Multi-User Chat, XEP-0045) como mecanismo de descubrimiento nativo de XMPP, eliminando la necesidad de un agente directorio intermediario.

La sala MUC es el punto de encuentro para el descubrimiento. Las partidas se juegan mediante mensajes directos FIPA-ACL entre tablero y jugadores. El Agente Supervisor del profesor observa las salas y solicita informes de partida a los tableros.

**Separación de responsabilidades:**

- El Agente Tablero actúa como **representador del juego**: registra movimientos, gestiona turnos, almacena historial completo para reproducción y expone la interfaz web.
- El Agente Jugador es el que **sabe jugar**: descubre tableros en la sala MUC, aplica su estrategia y envía movimientos válidos.
- La sala MUC es **infraestructura**: la proporciona el servidor XMPP, no es un agente.

### 3.2. Sala MUC: concepto y flujo

La sala MUC actúa como un tablón de anuncios donde los tableros publican su disponibilidad y los jugadores buscan partidas. Cada participante se une a la sala con un apodo (nickname) que identifica su tipo y su identidad:

- Los tableros usan el prefijo `tablero_` (ejemplo: `tablero_mesa1`).
- Los jugadores usan el prefijo `jugador_` (ejemplo: `jugador_ana`).

El flujo de descubrimiento es:

1. El Agente Tablero se une a la sala MUC con apodo `tablero_{id}` y establece su estado de presencia como `"waiting"`.
2. El Agente Jugador se une a la sala MUC con apodo `jugador_{nombre}`.
3. El Jugador consulta periódicamente la lista de ocupantes de la sala y filtra los apodos con prefijo `tablero_` cuyo estado sea `"waiting"`.
4. El Jugador envía un mensaje directo `REQUEST` con `{"action": "join"}` al JID real del tablero descubierto.
5. Al aceptar dos jugadores, el Tablero cambia su estado MUC a `"playing"`.
6. Al finalizar la partida, el Tablero cambia su estado a `"finished"`.

La implementación requiere el plugin XEP-0045 de slixmpp. La sala se configura en `config/config.yaml` para que sea la misma en todos los alumnos (dato proporcionado junto con el servidor XMPP).

### 3.3. Infraestructura XMPP

El sistema necesita un servidor XMPP con soporte MUC (XEP-0045) para
el descubrimiento entre agentes. Se ofrecen dos entornos de trabajo:

| Entorno | Servidor | Puerto c2s | Dominio | Servicio MUC | Sala por defecto |
|---------|----------|------------|---------|--------------|------------------|
| **Local** | `localhost` | 5222 | `localhost` | `conference.localhost` | `tictactoe@conference.localhost` |
| **Servidor** | `sinbad2.ujaen.es` | 8022 | `sinbad2.ujaen.es` | `conference.sinbad2.ujaen.es` | `tictactoe@conference.sinbad2.ujaen.es` |

En ambos casos: `auto_register=True`, `verify_security=False`.

El perfil activo se selecciona en `config/config.yaml` editando el
campo `perfil_activo` en la sección `xmpp`. El resto del sistema lee
automáticamente los datos del perfil seleccionado.

#### Entorno local — Prosody en Docker

Para trabajar sin conexión al servidor de la asignatura se utiliza un
contenedor Docker con Prosody. Este proyecto incluye los ficheros
necesarios listos para usar:

| Fichero | Descripción |
|---------|-------------|
| [`docker-compose.yml`](docker-compose.yml) | Define el servicio Prosody con los puertos y volúmenes necesarios |
| [`xmpp/prosody.cfg.lua`](xmpp/prosody.cfg.lua) | Configuración completa de Prosody (módulos, MUC, registro, seguridad) |

Órdenes principales:

```bash
# Arrancar el servidor XMPP en segundo plano
docker compose up -d

# Verificar que el contenedor está en ejecución
docker compose ps

# Comprobar que el puerto XMPP está abierto
nc -zv localhost 5222

# Ver registros en tiempo real
docker compose logs -f

# Detener el servidor (conserva datos persistentes)
docker compose down

# Detener y eliminar datos persistentes (cuentas, salas)
docker compose down -v
```

**Puertos expuestos por el contenedor:**

| Puerto | Protocolo | Uso |
|--------|-----------|-----|
| `5222` | c2s (cliente-a-servidor) | Conexión de los agentes SPADE |
| `5269` | s2s (servidor-a-servidor) | Federación entre servidores (no usado en desarrollo) |
| `5347` | Componentes externos | No usado |

**Configuración de Prosody** (`xmpp/prosody.cfg.lua`):

La configuración del servidor local está preparada para desarrollo y
no requiere modificaciones. Sus características principales son:

| Característica | Valor | Descripción |
|----------------|-------|-------------|
| Registro de cuentas | `allow_registration = true` | Los agentes crean su cuenta al conectarse por primera vez |
| Cifrado TLS | Desactivado | Simplifica el desarrollo local (en el servidor de la asignatura sí está activo) |
| Autenticación | `internal_plain` | Texto plano, adecuada para desarrollo |
| Salas MUC | `conference.localhost` | Cualquier usuario puede crear salas; son públicas, abiertas y persistentes |
| Descubrimiento | XEP-0030 habilitado | Las salas son descubribles mediante `disco#items` |
| Persistencia | Volumen Docker `ssmmaa-prosody-data` | Las cuentas y salas sobreviven a reinicios del contenedor; compartido entre proyectos de la asignatura |

**Módulos habilitados:** `roster`, `saslauth`, `disco` (XEP-0030),
`register`, `ping` (XEP-0199), `pep` (XEP-0163), `presence`,
`version`, `uptime`, `time`, `posix`.

**Configuración por defecto de las salas MUC:**

| Propiedad | Valor | Efecto |
|-----------|-------|--------|
| `restrict_room_creation` | `false` | Cualquier agente puede crear salas al unirse |
| `muc_room_default_public` | `true` | Las salas son descubribles (visibles en `disco#items`) |
| `muc_room_default_persistent` | `true` | Las salas persisten entre reinicios del servidor |
| `muc_room_default_members_only` | `false` | Abiertas a cualquier usuario, sin invitación |
| `muc_room_default_moderated` | `false` | Todos los participantes pueden enviar mensajes |
| `muc_room_default_history_length` | `10` | Últimos 10 mensajes al unirse a la sala |

#### Servidor de la asignatura

El servidor `sinbad2.ujaen.es` es accesible desde cualquier punto con
conexión a Internet (no solo desde la red del laboratorio). No requiere
Docker ni instalación adicional. La configuración del servidor es
equivalente a la del entorno local (registro automático, salas MUC
públicas y descubribles), pero con cifrado TLS activo y el puerto c2s
en `8022` en lugar de `5222`.

Para verificar la conectividad:

```bash
nc -zv sinbad2.ujaen.es 8022
```

---

## 4. Protocolos de comunicación

La ontología y los protocolos son la columna vertebral del sistema. Todos los mensajes utilizan la ontología `"tictactoe"` (metadato `ontology`) y un hilo (`thread`) único por conversación.

### 4.1. Protocolo de inscripción — FIPA Request

El jugador solicita unirse a un tablero mediante el protocolo FIPA Request. El tablero evalúa si hay plazas disponibles y responde en consecuencia.

| Fase | Performativa | Dirección | Contenido JSON (`body`) |
|------|-------------|-----------|------------------------|
| Inscripción | `REQUEST` | Jugador → Tablero | `{"action": "join"}` |
| Aceptación | `AGREE` | Tablero → Jugador | `{"action": "join-accepted", "symbol": "X"\|"O"}` |
| Rechazo | `REFUSE` | Tablero → Jugador | `{"action": "join-refused", "reason": "full"}` |
| Expiración | `FAILURE` | Tablero → Jugador | `{"action": "join-timeout", "reason": "no opponent"}` |
| Inicio partida | `INFORM` | Tablero → Ambos | `{"action": "game-start", "opponent": "<JID>"}` |

El campo `thread` del mensaje FIPA-ACL identifica cada conversación de inscripción. El tablero genera un hilo único y lo incluye en todas las respuestas. Los comportamientos del jugador filtran por `thread` + `ontology="tictactoe"` para separar conversaciones concurrentes.

### 4.2. Protocolo de turno — FIPA Contract Net

Una vez iniciada la partida, cada turno sigue el protocolo FIPA Contract Net. El tablero convoca (CFP) a ambos jugadores; solo el jugador activo propone un movimiento.

| Fase | Performativa | Dirección | Contenido JSON (`body`) |
|------|-------------|-----------|------------------------|
| Convocatoria | `CFP` | Tablero → Ambos | `{"action": "turn", "active_symbol": "X"\|"O"}` |
| Movimiento | `PROPOSE` | Jugador activo → Tablero | `{"action": "move", "position": 0-8}` |
| Confirmación | `PROPOSE` | Jugador rival → Tablero | `{"action": "ok"}` |
| Mov. válido | `ACCEPT_PROPOSAL` | Tablero → Ambos | `{"action": "move", "position": N, "symbol": "X"\|"O"}` |
| Fin partida | `REJECT_PROPOSAL` | Tablero → Ambos | `{"action": "game-over", "reason": "invalid"\|"timeout"\|"both-timeout", "winner": ...}` |

El tablero valida la colocación, pero **cada jugador evalúa el resultado localmente** tras recibir el `ACCEPT_PROPOSAL` y lo notifica al tablero vía `INFORM` con `{"result": "continue"\|"win"\|"draw"}`. El tablero cruza ambas evaluaciones para detectar incoherencias.

### 4.3. Protocolo de informe al Supervisor — FIPA Request

Tras finalizar cada partida, el Agente Supervisor del profesor solicita el informe al tablero. Este protocolo es **obligatorio**: todo Agente Tablero debe implementarlo.

| Fase | Performativa | Dirección | Contenido JSON (`body`) |
|------|-------------|-----------|------------------------|
| Solicitud | `REQUEST` | Supervisor → Tablero | `{"action": "game-report"}` |
| Informe | `INFORM` | Tablero → Supervisor | `{"action": "game-report", "result": "win"\|"draw"\|"aborted", "winner": ..., "players": {...}, "turns": N, "board": [...]}` |
| Rechazo | `REFUSE` | Tablero → Supervisor | `{"action": "game-report", "reason": "not-finished"}` |

El Supervisor distingue los mensajes de informe de los de juego mediante el campo `thread`: los mensajes de partida usan `"game-{tablero_id}-{timestamp}"` y los de informe usan `"report-{tablero_id}-{timestamp}"`.

---

## 5. Ontología proporcionada

La ontología del sistema se proporciona como un módulo Python reutilizable en el directorio `ontologia/` de este repositorio. **No puede modificarse**: el alumno debe usarla tal cual en sus agentes.

### 5.1. Ficheros incluidos

| Fichero | Descripción |
|---------|-------------|
| `ontologia/ontologia.py` | Módulo runtime con constructores y validador (4 niveles) |
| `ontologia/ontologia_tictactoe.schema.json` | JSON Schema con 12 subesquemas (`oneOf`) |
| `ontologia/ontologia_campos.json` | Mapa acción → campos obligatorios |
| `ontologia/__init__.py` | Re-exportaciones para import limpio |
| `tests/test_ontologia.py` | 60 tests en 7 grupos (referencia) |

### 5.2. Uso desde los agentes

```python
from ontologia import (
    ONTOLOGIA,
    crear_cuerpo_join,
    crear_cuerpo_move,
    crear_cuerpo_join_accepted,
    crear_cuerpo_game_start,
    crear_cuerpo_turn,
    crear_cuerpo_move_confirmado,
    crear_cuerpo_ok,
    crear_cuerpo_game_over,
    crear_cuerpo_game_report,
    crear_cuerpo_game_report_request,
    crear_cuerpo_game_report_refused,
    validar_cuerpo,
    obtener_performativa,
)
```

Todos los constructores validan antes de serializar. Si los datos son inválidos, lanzan `ValueError`. El validador `validar_cuerpo(cuerpo)` realiza 4 niveles de comprobación: presencia de `action`, JSON Schema, campos obligatorios según acción, y reglas condicionales cruzadas.

### 5.3. Inventario completo de mensajes

**Protocolo jugador - tablero (9 acciones):**

| Acción | Emisor | Receptor | Performativa | Campos extra |
|--------|--------|----------|-------------|-------------|
| `join` | Jugador | Tablero | REQUEST | — |
| `join-accepted` | Tablero | Jugador | AGREE | `symbol` |
| `join-refused` | Tablero | Jugador | REFUSE | `reason` |
| `join-timeout` | Tablero | Jugador | FAILURE | `reason` |
| `game-start` | Tablero | Ambos | INFORM | `opponent` |
| `turn` | Tablero | Ambos | CFP | `active_symbol` |
| `move` | Jugador/Tablero | Tablero/Ambos | PROPOSE/ACCEPT | `position` [, `symbol`] |
| `ok` | Jugador no activo | Tablero | PROPOSE | — |
| `game-over` | Tablero | Ambos | REJECT_PROPOSAL | `reason` [, `winner`] |

**Protocolo supervisor - tablero (3 variantes de `game-report`):**

| Variante | Emisor | Receptor | Performativa | Campos |
|----------|--------|----------|-------------|--------|
| Solicitud | Supervisor | Tablero | REQUEST | solo `action` |
| Informe | Tablero | Supervisor | INFORM | `result`, `winner`, `players`, `turns`, `board` [, `reason`] |
| Rechazo | Tablero | Supervisor | REFUSE | `reason` (`"not-finished"`) |

### 5.4. Lo que NO debes hacer con la ontología

- **No importar Pydantic** en los agentes. Pydantic solo se usa en la fase de diseño (`diseno/`).
- **No modificar los ficheros JSON a mano.** Si necesitas regenerar, hay que contactar con el profesor que es el único encargado de las modificaciones.
- **No saltarte la validación.** Usa siempre `validar_cuerpo()` al recibir mensajes.
- **No inventar acciones.** Solo las 9+3 definidas en la ontología son válidas.
- **No usar `json.dumps()` directamente.** Usa los constructores, que validan automáticamente.

---

## 6. Diseño de los agentes

### 6.1. Agente Tablero — FSM

El Tablero se diseña como una máquina de estados finitos (FSM). La metodología consiste en traducir cada protocolo FIPA a estados y transiciones.

**FSM del protocolo de inscripción** (proporcionada como referencia):

Los estados de decisión (`CHECK_SLOTS`, `CHECK_PAIR`) evalúan condiciones internas del tablero, mientras que los estados de acción (`SEND_AGREE`, `SEND_REFUSE`, `SEND_FAILURE`) generan los mensajes FIPA-ACL correspondientes.

**FSM del protocolo de turno** (a diseñar por el alumno):

El alumno debe aplicar el mismo enfoque: identificar las performativas del protocolo Contract Net, crear un estado por cada acción o decisión, y definir las transiciones según las condiciones del agente. Los estados seguirían el ciclo `SEND_CFP → WAIT_PROPOSALS → VALIDATE → SEND_ACCEPT/REJECT → WAIT_RESULT`.

**Interfaz web** (obligatoria):

El tablero debe exponer dos rutas HTTP personalizadas:

- `/game` — Página HTML con la rejilla 3x3 visual, nombres de jugadores, indicador de turno y registro de movimientos en tiempo real.
- `/game/state` — Ruta JSON con el estado completo: `board`, `players`, `current_turn`, `status`, `result`, `history`, `winner`.

### 6.2. Agente Jugador — Comportamientos concurrentes

El Jugador gestiona múltiples partidas simultáneas mediante comportamientos dinámicos:

**Comportamiento de búsqueda:** Consulta la lista de ocupantes de la sala MUC, filtra apodos con prefijo `tablero_` y estado `"waiting"`, comprueba que no se supere el límite de partidas activas, y si hay hueco, envía `REQUEST` con `{"action": "join"}`.

**Comportamiento de partida:** Se crea al recibir `AGREE` del tablero. Filtra mensajes por `thread` mediante `Template`. Escucha mensajes `turn` y `game-over`. Cuando le toca, calcula el movimiento usando su estrategia y lo envía. Al finalizar la partida, se elimina con `self.kill()`.

### 6.3. Estrategia de juego

Se exige un mínimo de razonamiento sobre el estado del juego. La selección puramente aleatoria no representa un comportamiento inteligente y no alcanza el aprobado. Se proponen cuatro niveles de sofisticación creciente:

| Nivel | Nombre | Descripción | Calificación orientativa |
|-------|--------|-------------|-------------------------|
| 1 | Posicional | Puntuación por posición: centro (4), esquinas (3), laterales (1). No reacciona al oponente. | 5-6 |
| 2 | Reglas | Primero intenta ganar, luego bloquea al rival, luego elige centro > esquinas > laterales. | 7-8 |
| 3 | Minimax | Algoritmo Minimax con poda alfa-beta. Estrategia óptima: nunca pierde. | 8-9 |
| 4 | LLM | Integración con Ollama local. **Prerequisito obligatorio: el nivel 3 (Minimax) debe estar implementado y activo como estrategia de respaldo.** El sistema debe degradar automáticamente a Minimax tanto ante respuestas inválidas del modelo como ante cualquier error de conexión o indisponibilidad del servicio Ollama. Un nivel 4 sin respaldo Minimax funcional se califica como nivel 2. | 9-10 |

La estrategia debe implementarse como una **función pura** `elegir_movimiento(tablero, mi_simbolo) -> int` que recibe el estado actual y devuelve una posición (0-8). Esto facilita su testeo aislado sin infraestructura XMPP.

---

## 7. Estructura del proyecto y entrega

### 7.1. Estructura obligatoria de ficheros

Cada carpeta contiene un fichero `README.md` con indicaciones sobre qué
se espera encontrar en ella y orientaciones de diseño. Los ficheros
concretos de implementación los decide el alumno.

```
tictactoe-sma-{apellido}/
│
├── ontologia/                            # Ontología proporcionada (NO modificar)
│   ├── __init__.py                       #   Re-exportaciones
│   ├── ontologia.py                      #   Módulo runtime
│   ├── ontologia_tictactoe.schema.json   #   JSON Schema (12 subesquemas)
│   ├── ontologia_campos.json             #   Mapa acción → campos
│   └── README.md                         #   Documentación de la ontología
│
├── agentes/                              # Clases de los agentes SPADE
│   ├── __init__.py
│   └── README.md                         #   → Qué incluir: clases Agent del
│                                         #     Tablero y del Jugador, con su
│                                         #     setup() y estado interno.
│
├── behaviours/                           # Comportamientos SPADE independientes
│   ├── __init__.py
│   └── README.md                         #   → Qué incluir: FSM del Tablero,
│                                         #     ciclo de turnos, búsqueda MUC,
│                                         #     comportamiento de partida, etc.
│
├── estrategia/                           # Funciones puras de estrategia de juego
│   ├── __init__.py
│   └── README.md                         #   → Qué incluir: elegir_movimiento()
│                                         #     con la lógica de decisión (nivel
│                                         #     1 a 4). Testeable sin XMPP.
│
├── web/                                  # Interfaz web del Agente Tablero
│   ├── __init__.py
│   ├── templates/                        #   Plantillas HTML para /game
│   │   └── README.md                     #     → Rejilla 3x3, turno, historial
│   ├── static/                           #   CSS y JavaScript
│   │   └── README.md                     #     → Estilos, polling/SSE
│   └── README.md                         #   → Handlers HTTP para /game y
│                                         #     /game/state, registro de rutas.
│
├── config/                               # Configuración centralizada
│   ├── __init__.py
│   ├── config.yaml                       #   Perfiles XMPP (local/servidor) y LLM
│   ├── agents.yaml                       #   Definición de agentes (nombre, clase, módulo)
│   ├── configuracion.py                  #   Funciones de carga de YAML
│   └── README.md                         #   → Documentación de los perfiles y parámetros
│
├── tests/                                # Tests del alumno
│   ├── __init__.py
│   ├── test_ontologia.py                 #   Tests de ontología (proporcionados)
│   ├── test_conexion_xmpp.py             #   Test de conectividad XMPP (proporcionado)
│   └── README.md                         #   → Qué incluir: test_estrategia,
│                                         #     test_tablero_aislado,
│                                         #     test_jugador_aislado,
│                                         #     test_web_endpoints,
│                                         #     test_integracion.
│
├── docs/
│   └── guia_utils_y_test_conexion.md     # Guía detallada de utils.py y test de conexión
│
├── main.py                               # Lanzador de agentes (lee YAML, arranque aleatorio)
├── utils.py                              # Funciones factoría para crear/arrancar agentes
├── conftest.py                           # Fixtures compartidos de pytest
├── requirements.txt                      # Dependencias del proyecto (incluye pyyaml)
└── README.md                             # Documentación del alumno
```

### 7.2. Ficheros de configuración (`config/`)

La configuración del sistema se divide en dos ficheros YAML que el lanzador (`main.py`) y los fixtures de tests (`conftest.py`) leen al arrancar:

**`config/config.yaml`** — Perfiles de conexión y parámetros del sistema:

```yaml
# Cambiar perfil_activo para alternar entre local y servidor
xmpp:
  perfil_activo: local    # "local" o "servidor"
  perfiles:
    local:
      host: localhost
      puerto: 5222
      dominio: localhost
      servicio_muc: conference.localhost
      sala_tictactoe: tictactoe
      password_defecto: secret
      auto_register: true
      verify_security: false
    servidor:
      host: sinbad2.ujaen.es
      puerto: 8022
      dominio: sinbad2.ujaen.es
      servicio_muc: conference.sinbad2.ujaen.es
      sala_tictactoe: tictactoe
      password_defecto: secret
      auto_register: true
      verify_security: false

# Solo necesario para estrategia nivel 4 (LLM)
llm:
  perfil_activo: local    # "local" o "servidor"
  perfiles:
    local:
      url_base: "http://localhost:11434"
      modelo: llama3.2:3b
    servidor:
      url_base: "http://sinbad2ia.ujaen.es:8050"
      modelo: llama3:8b

sistema:
  intervalo_busqueda_muc: 5
  max_partidas_simultaneas: 3
  timeout_inscripcion: 60
  timeout_turno: 30
  puerto_web_base: 10080
  nivel_log: INFO
```

**`config/agents.yaml`** — Definición de agentes. Cada entrada especifica el nombre (parte local del JID), la clase Python, el módulo donde reside, y los parámetros específicos. El JID se construye automáticamente como `nombre@dominio_del_perfil_xmpp_activo`:

```yaml
- nombre: tablero_mesa1
  clase: AgenteTablero
  modulo: agentes.agente_tablero
  nivel: 1
  descripcion: "Mesa de juego 1"
  parametros:
    id_tablero: mesa1
    puerto_web: 10080
  activo: true

- nombre: jugador_alice
  clase: AgenteJugador
  modulo: agentes.agente_jugador
  nivel: 1
  descripcion: "Jugadora Alice"
  parametros:
    nivel_estrategia: 2
    max_partidas: 3
  activo: true
```

**`config/configuracion.py`** — Módulo de carga que resuelve el perfil activo:

```python
from config.configuracion import cargar_configuracion, cargar_agentes, construir_jid

config = cargar_configuracion()               # Resuelve perfil activo
perfil_xmpp = config["xmpp"]                  # Datos del perfil XMPP seleccionado
perfil_llm = config["llm"]                    # Datos del perfil LLM o None

agentes = cargar_agentes(solo_activos=True)    # Lista de agentes activos
jid = construir_jid("tablero_mesa1", perfil_xmpp)  # → "tablero_mesa1@localhost"
```

### 7.3. Módulo de utilidades (`utils.py`)

El fichero [`utils.py`](utils.py) proporciona funciones factoría para crear y arrancar agentes SPADE de forma correcta. En SPADE 4.x, los parámetros de conexión se reparten entre el constructor del agente (`port`, `verify_security`) y el método `start()` (`auto_register`); las funciones `crear_agente()` y `arrancar_agente()` encapsulan esta separación para evitar errores. El módulo también re-exporta las funciones de `config/configuracion.py` para que el alumno pueda importar todo desde un único punto. Consultar la [guía detallada de `utils.py` y el test de conexión](docs/guia_utils_y_test_conexion.md) para más información.

### 7.4. Test de conexión XMPP

Antes de desarrollar los agentes, se recomienda ejecutar el test de conexión para verificar que el servidor XMPP es alcanzable y que un agente puede registrarse correctamente:

```bash
# Probar contra el servidor de la asignatura
python -m tests.test_conexion_xmpp servidor

# Probar contra localhost (requiere 'spade run' en otra terminal)
python -m tests.test_conexion_xmpp local
```

Consultar la [guía detallada](docs/guia_utils_y_test_conexion.md) para la interpretación de resultados y las opciones disponibles.

### 7.5. Fichero `requirements.txt`

```
spade>=4.1.2
jsonschema>=4.20.0
aiohttp>=3.9
pyyaml>=6.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-timeout>=2.2
beautifulsoup4>=4.12
lxml>=5.1
```

---

## 8. Repositorio Git y flujo de trabajo

### 8.1. Obtención del proyecto base

El código base de esta práctica (ontología, tests proporcionados, estructura de carpetas y este README) se encuentra en un repositorio público de GitLab. El primer paso es clonarlo en tu equipo local:

```bash
git clone https://gitlab.com/ssmmaa/curso2025-26/tictactoe-nivel1.git
cd tictactoe-nivel1
```

Verifica que la estructura inicial es correcta y que los tests de ontología proporcionados pasan antes de hacer cualquier cambio:

```bash
pip install -r requirements.txt
pytest tests/test_ontologia.py -v
```

### 8.2. Vinculación con el repositorio personal en Suleiman

Cada alumno debe trabajar en su repositorio personal alojado en el servidor GitLab de la Universidad de Jaén (`suleiman.ujaen.es:8011`). Tras clonar el proyecto base, debes añadir tu repositorio personal como nuevo remoto y subir el contenido inicial:

```bash
# Añadir tu repositorio personal como remoto "suleiman"
git remote add suleiman https://suleiman.ujaen.es:8011/<tu-usuario>/tictactoe-nivel1.git

# Subir la rama principal al repositorio personal
git push suleiman main
```

A partir de este momento trabajarás con dos remotos configurados:

| Remoto | URL | Uso |
|--------|-----|-----|
| `origin` | `https://gitlab.com/ssmmaa/curso2025-26/tictactoe-nivel1.git` | Repositorio público de la asignatura (solo lectura). Útil para incorporar actualizaciones del profesor si las hubiera (`git pull origin main`). |
| `suleiman` | `https://suleiman.ujaen.es:8011/<tu-usuario>/tictactoe-nivel1.git` | Tu repositorio personal de entrega. Aquí subes tu trabajo (`git push suleiman`). |

Si prefieres que `suleiman` sea tu remoto por defecto para `git push`, puedes reasignar los nombres:

```bash
git remote rename origin gitlab-asignatura
git remote rename suleiman origin
```

### 8.3. Ramas de entrega

La práctica tiene dos actividades con entregas independientes. Para mantenerlas organizadas, cada actividad se desarrolla y entrega en su propia rama. La convención de nombres es:

| Rama | Actividad | Contenido                                                                                                                                                                 |
|------|-----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `entrega/analisis-diseno` | Actividad 1 — Teoría | Documento Markdown de análisis y diseño, diagramas, y cualquier material complementario. Versión PDF recomendada también.                                                 |
| `entrega/implementacion` | Actividad 2 — Prácticas | Código fuente de los agentes, estrategia, interfaz web, tests diseñados por el alumno y documentación técnica (README). Ejecuciones separadas para test, pruebas y final. |

**Identificación del commit de entrega:** El profesor evaluará el estado del repositorio en un commit concreto. El alumno debe indicar en la entrega de PLATEA el **hash del commit** que desea que se evalúe, o bien asegurarse de que el **último commit de la rama de entrega** corresponde a la versión final. Si no se indica un commit específico, se tomará el último commit de la rama correspondiente en el momento de la corrección.

**Creación de las ramas de entrega:**

```bash
# Crear la rama de análisis y diseño a partir de main
git checkout -b entrega/analisis-diseno main

# ... trabajar en el documento, hacer commits ...
git add docs/analisis-diseno.pdf
git commit -m "Añadir documento de análisis y diseño"

# Subir la rama al repositorio personal
git push suleiman entrega/analisis-diseno
```

```bash
# Crear la rama de implementación a partir de main
git checkout -b entrega/implementacion main

# ... desarrollar agentes, tests, interfaz web, hacer commits ...
git add agentes/ behaviours/ estrategia/ web/ tests/
git commit -m "Implementar agente tablero con FSM de inscripción"

# Subir la rama al repositorio personal
git push suleiman entrega/implementacion
```

### 8.4. Flujo de trabajo recomendado

El desarrollo diario se realiza en `main` (o en ramas de trabajo propias si se prefiere). Las ramas de entrega se actualizan cuando se quiere consolidar el trabajo para la evaluación:

```
main ─────●────●────●────●────●────●────●────●───
           \                  \              \
            \ entrega/         \ merge        \ merge
             \ analisis-diseno  \              \
              ●─────────●────────●              \
                                                \
                         entrega/implementacion  \
                          ●──────●────────●───────●
```

Para incorporar el trabajo de `main` a una rama de entrega:

```bash
git checkout entrega/implementacion
git merge main
git push suleiman entrega/implementacion
```

Si se hace el merge en `main`, hay que crear una etiqueta que permita identificar el merge. 

### 8.5. Buenas prácticas de commits

Los commits deben reflejar progreso real del proyecto. Cada commit debe representar un avance concreto y funcional, no mera actividad en el repositorio. Algunos ejemplos de buenos mensajes de commit:

```
Implementar detección de victoria en las 8 líneas ganadoras
Añadir tests aislados del comportamiento de inscripción del tablero
Corregir filtrado de tableros MUC: ignorar apodos sin prefijo tablero_
Implementar endpoint /game/state con campos obligatorios de la ontología
Diseñar FSM del protocolo de turno (Contract Net) en documento de análisis
```

Evita commits vacíos de contenido como «avance», «cambios», «WIP» o «actualización». El historial de commits es parte de lo que el profesor revisa para entender la evolución del trabajo.

### 8.6. Resumen de órdenes de referencia

```bash
# Configuración inicial (una sola vez)
git clone https://gitlab.com/ssmmaa/curso2025-26/tictactoe-nivel1.git
cd tictactoe-nivel1
git remote add suleiman https://suleiman.ujaen.es:8011/<tu-usuario>/tictactoe-nivel1.git

# Incorporar actualizaciones del profesor (si las hubiera)
git pull origin main

# Crear ramas de entrega (una sola vez)
git checkout -b entrega/analisis-diseno main
git push suleiman entrega/analisis-diseno
git checkout -b entrega/implementacion main
git push suleiman entrega/implementacion

# Flujo diario de trabajo
git checkout main
# ... trabajar, hacer commits ...
git push suleiman main

# Consolidar entrega
git checkout entrega/implementacion
git merge main
git push suleiman entrega/implementacion
```

---

## 9. Actividad 1 — Teoría: Análisis y Diseño

### 9.1. Descripción

El alumno debe elaborar un **documento de análisis y diseño** del sistema multiagente Tic-Tac-Toe siguiendo la estructura definida en la *Guía de Desarrollo de Proyectos de SMA*. El documento debe demostrar comprensión de los conceptos de agentes, protocolos FIPA y diseño de sistemas multiagente.

### 9.2. Secciones obligatorias del documento

El documento debe contener las siguientes secciones (referencia: diapositivas 3-13 de la Guía de Proyectos):

**Fase de Análisis:**

1. **Introducción y planteamiento del problema.** Describir el dominio del Tic-Tac-Toe multiagente, identificar las entidades autónomas y justificar por qué el enfoque multiagente es adecuado (autonomía, descubrimiento, concurrencia).

2. **Identificación de agentes y responsabilidades.** Ficha descriptiva de cada agente (Tablero y Jugador) con: nombre, JID, propósito, responsabilidades concretas, recursos que gestiona y dependencias con otros agentes.

3. **Comportamientos asociados a los agentes.** Para cada agente, identificar los comportamientos necesarios respondiendo a tres preguntas: cuántas veces se ejecuta, si involucra comunicación, y si tiene etapas o estados. Documentar cada comportamiento con: nombre descriptivo, patrón de ejecución, si es comunicación o propio, evento que lo activa y resultado esperado.

**Fase de Diseño:**

4. **Arquitectura del sistema.** Diagrama de arquitectura mostrando agentes, sala MUC, servidor XMPP y flujos de comunicación. Indicar la separación entre descubrimiento (MUC) y juego (mensajes directos).

5. **Necesidades de comunicación.** Tabla de comunicación entre agentes: emisor, receptor, contenido, performativa, propósito y protocolo FIPA utilizado.

6. **Diagramas de secuencia UML.** Al menos tres diagramas:
   - Protocolo de inscripción (FIPA Request).
   - Ciclo de turno completo (FIPA Contract Net).
   - Protocolo de informe al Supervisor (FIPA Request).

7. **Ontología.** Descripción de la ontología proporcionada: inventario de mensajes, campos de cada acción, correspondencia acción-performativa. Explicar el diseño `oneOf` con `additionalProperties: false` y los 4 niveles de validación.

8. **FSM del Agente Tablero.** Diagrama de estados para al menos:
   - FSM del protocolo de inscripción (puede basarse en la proporcionada como referencia).
   - FSM del protocolo de turno (Contract Net) — **diseño propio del alumno**.

9. **Interfaz web.** Descripción de las rutas `/game` y `/game/state`, campos del JSON de estado, y mockup o prototipo visual de la página del tablero.

### 9.3. Rúbrica de evaluación — Actividad 1

| Criterio | Peso | 5-6 (Aprobado) | 7-8 (Notable) | 9-10 (Sobresaliente) |
|----------|------|----------------|---------------|---------------------|
| **Análisis del dominio** | 15% | Identifica agentes y justificación genérica | Justificación específica al Tic-Tac-Toe con análisis de autonomía, descubrimiento y concurrencia | Además compara con alternativas centralizadas y argumenta ventajas concretas del enfoque MAS |
| **Fichas de agentes** | 15% | Fichas con campos mínimos | Fichas completas con dependencias y recursos bien detallados | Además incluye análisis de qué información necesita cada agente de otros |
| **Comportamientos** | 15% | Lista de comportamientos con tipo | Tabla completa con patrón, activación y resultado para cada comportamiento | Además justifica la elección del tipo SPADE y analiza concurrencia entre behaviours |
| **Comunicación y protocolos** | 20% | Tabla de comunicación básica | Tabla completa + diagramas de secuencia UML correctos para los 3 protocolos | Diagramas con escenarios alternativos (timeout, rechazo, error) |
| **FSM del Tablero** | 15% | FSM de inscripción (puede basarse en la referencia) | FSM de inscripción + FSM de turno con estados y transiciones correctos | FSM completa con gestión de errores, timeouts y estados excepcionales |
| **Ontología e interfaz web** | 10% | Descripción del inventario de mensajes | Descripción detallada con correspondencia performativa-acción + mockup web | Análisis de decisiones de diseño (oneOf, additionalProperties, niveles de validación) + prototipo web funcional |
| **Calidad del documento** | 10% | Estructura aceptable, sin errores graves | Documento bien organizado con terminología correcta y coherente | Redacción profesional, diagramas de calidad, referencias cruzadas entre secciones |

### 9.4. Formato y entrega

- Formato: **Markdown** (**PDF** adicional recomendado máximo 20 páginas sin contar portada ni bibliografía).
- Los diagramas pueden realizarse con cualquier herramienta (draw.io, PlantUML, Mermaid, a mano escaneado con calidad suficiente).
- Entrega a través de **PLATEA** en la actividad correspondiente: se debe subir un **fichero PDF** que contenga el **enlace al repositorio del alumno** en Suleiman.
- **Planificación temporal:** la descrita en la actividad de PLATEA. El plazo **no será ampliable**.
- **Requisito de completitud:** deben completarse **ambas entregas** (PLATEA y repositorio) para considerar la entrega global como realizada.

---

## 10. Actividad 2 — Prácticas: Implementación

### 10.1. Descripción

El alumno debe implementar el sistema multiagente Tic-Tac-Toe completo y diseñar una batería de tests que valide su funcionamiento. La implementación debe seguir las reglas de código de la asignatura y pasar tanto los tests proporcionados (ontología) como los tests diseñados por el alumno.

### 10.2. Requisitos funcionales

**RF-1. Agente Tablero funcional.** El agente arranca sin errores, se une a la sala MUC con apodo `tablero_{id}`, gestiona el protocolo de inscripción completo (accept/refuse/timeout), ejecuta el ciclo de turnos Contract Net, detecta victoria/empate/error y responde a solicitudes `game-report` del Supervisor.

**RF-2. Agente Jugador funcional.** El agente arranca sin errores, se une a la sala MUC, descubre tableros periódicamente, se inscribe en partidas disponibles, gestiona al menos 3 partidas simultáneas con comportamientos dinámicos independientes, y aplica una estrategia de juego con razonamiento (no aleatoria).

**RF-3. Comunicación FIPA-ACL correcta.** Todos los mensajes usan las performativas correctas según la ontología, incluyen `ontology="tictactoe"` y `thread` coherente, y los comportamientos filtran con `Template`.

**RF-4. Ontología validada.** Se usa la ontología proporcionada sin modificaciones. Todos los mensajes salientes se construyen con los constructores de `ontologia.py`. Todos los mensajes entrantes se validan con `validar_cuerpo()`.

**RF-5. Interfaz web del Tablero.** Ruta `/game` con HTML visual (rejilla, jugadores, turno, historial). Ruta `/game/state` con JSON válido y campos obligatorios.

**RF-6. Estrategia de juego.** Función pura `elegir_movimiento(tablero, mi_simbolo) -> int` que implementa al menos el nivel posicional (nivel 1). Niveles superiores mejoran la calificación. Si se implementa el nivel 4 (LLM), el nivel 3 (Minimax) debe estar implementado como estrategia de respaldo activa: el sistema debe degradar automáticamente a Minimax cuando el servicio Ollama no esté disponible o devuelva una respuesta inválida. Un nivel 4 sin respaldo Minimax funcional se evaluará como nivel 2.

### 10.3. Tests obligatorios que debe diseñar el alumno

El alumno debe diseñar y entregar tests ejecutables con `pytest` que cubran las siguientes áreas. Los tests deben pasar para obtener la calificación correspondiente.

#### Batería 0: Tests de ontología (proporcionados)

Estos tests se proporcionan en `tests/test_ontologia.py` y deben pasar al 100%. Verifican que la ontología está correctamente integrada en el proyecto.

```bash
pytest tests/test_ontologia.py -v
```

#### Batería 1: Tests de estrategia (diseñar)

El alumno debe escribir `tests/test_estrategia.py` con tests que verifiquen:

- La función `elegir_movimiento` devuelve siempre una posición válida (0-8) en una casilla libre.
- Ante un tablero vacío, devuelve una posición válida.
- Ante un tablero casi lleno (una sola casilla libre), devuelve esa casilla.
- (Si nivel >= 2) Ante una oportunidad de ganar, la aprovecha.
- (Si nivel >= 2) Ante una amenaza del rival, la bloquea.
- La función no modifica el tablero de entrada (es pura).
- La función funciona tanto para símbolo "X" como para "O".

Estos tests **no requieren infraestructura XMPP** y deben ser rápidos (< 1 segundo cada uno).

#### Batería 2: Tests aislados de behaviours (diseñar)

El alumno debe escribir `tests/test_tablero_aislado.py` y `tests/test_jugador_aislado.py` siguiendo la técnica de la *Guía de Testing Aislado de Behaviours*. Estos tests verifican la lógica interna sin XMPP:

**Para el Tablero:**
- La lógica de gestión de plazas acepta al primer jugador y le asigna "X".
- La lógica acepta al segundo jugador y le asigna "O".
- La lógica rechaza a un tercer jugador con razón "full".
- La validación de movimiento acepta posiciones libres (0-8).
- La validación de movimiento rechaza posiciones ocupadas.
- La detección de victoria identifica las 8 líneas ganadoras.
- La detección de empate funciona correctamente (9 turnos sin ganador).
- El estado inicial del tablero es correcto (9 casillas vacías, estado "waiting").

**Para el Jugador:**
- La lógica de filtrado de tableros en MUC reconoce el prefijo `tablero_`.
- La lógica de control de partidas activas respeta el límite configurado.

#### Batería 3: Tests de interfaz web (diseñar)

El alumno debe escribir `tests/test_web_endpoints.py` siguiendo la *Guía de Testing de Interfaces Web*:

**Ruta `/game/state` (JSON):**
- Devuelve HTTP 200 con `Content-Type: application/json`.
- Contiene todos los campos obligatorios: `tablero`, `jugadores`, `turno_actual`, `estado_partida`, `historial`.
- El campo `tablero` es una estructura válida (matriz 3x3 o lista de 9 elementos).
- El campo `estado_partida` tiene un valor válido: `"waiting"`, `"playing"` o `"finished"`.
- En estado `"finished"`, el campo `ganador` existe.

**Página `/game` (HTML):**
- Devuelve HTTP 200 con `Content-Type: text/html`.
- Contiene una rejilla visual (9 celdas identificables).
- Muestra los nombres o JIDs de los jugadores.
- Tiene un indicador de turno visible.
- Tiene una sección de historial de movimientos.

**Robustez:**
- Una ruta inexistente devuelve 404, no 500.
- Peticiones concurrentes (10 simultáneas) responden correctamente.

#### Batería 4: Tests de integración (diseñar, requiere XMPP)

El alumno debe escribir `tests/test_integracion.py` con tests que arranquen agentes reales y verifiquen la comunicación. Estos tests requieren un servidor XMPP:

- Un Agente Tablero arranca y se une a la sala MUC.
- Un Agente Jugador descubre al tablero en la sala MUC.
- El protocolo de inscripción completo funciona (REQUEST → AGREE → INFORM game-start).
- Al menos un turno completo se ejecuta correctamente (CFP → PROPOSE → ACCEPT_PROPOSAL).
- El Tablero responde a solicitudes `game-report` del agente observador.

### 10.4. Rúbrica de evaluación — Actividad 2

| Criterio | Peso | 5-6 (Aprobado) | 7-8 (Notable) | 9-10 (Sobresaliente) |
|----------|------|----------------|---------------|---------------------|
| **Tests de ontología** | 10% | 100% de tests proporcionados pasan | — | — |
| **Tests de estrategia** | 10% | Tests básicos (posición válida, casilla libre) | Tests de oportunidad y bloqueo | Tests exhaustivos con todos los escenarios de tablero; si se implementa nivel 4, tests que verifiquen la degradación automática a Minimax ante fallo del LLM |
| **Agente Tablero** | 20% | Inscripción funcional (accept/refuse) | + Ciclo de turnos completo + detección victoria/empate | + Gestión de timeouts + game-report del Supervisor + FSM completa |
| **Agente Jugador** | 20% | Descubrimiento MUC + inscripción | + Estrategia nivel 2 (reglas) + al menos 2 partidas simultáneas | + Estrategia nivel 3 (Minimax) + 3 o más partidas simultáneas demostradas; la estrategia nivel 4 (LLM) suma si y solo si el nivel 3 está implementado como respaldo activo ante indisponibilidad del servicio |
| **Interfaz web** | 10% | Ruta `/game/state` funcional con JSON válido | + Página `/game` con rejilla visual y turno | + Historial, reproducción, actualización en tiempo real (consulta periódica/SSE) |
| **Tests de behaviours e integración** | 15% | Tests aislados básicos del Tablero | + Tests aislados del Jugador + tests web | + Tests de integración con agentes reales + escenarios de error |
| **Calidad de código** | 15% | Código funcional, comentarios mínimos | Código bien organizado, type hints, docstrings | Cumple todas las reglas de código, registro de trazas, manejo de errores, async correcto |

### 10.5. Orden de ejecución de tests recomendado

Los tests deben poder ejecutarse en este orden. Si una batería falla, las siguientes pueden no tener sentido:

```bash
# 1. Ontología (sin infraestructura, siempre primero)
pytest tests/test_ontologia.py -v

# 2. Estrategia (sin infraestructura, función pura)
pytest tests/test_estrategia.py -v

# 3. Tests aislados de behaviours (sin infraestructura)
pytest tests/test_tablero_aislado.py tests/test_jugador_aislado.py -v

# 4. Tests de interfaz web (sin XMPP, solo aiohttp)
pytest tests/test_web_endpoints.py -v

# 5. Tests de integración (requiere XMPP)
pytest tests/test_integracion.py -v --timeout=60
```

### 10.6. Formato y entrega

- Entregar en el repositorio con la estructura de directorios completa (sección 7.1).
- El README.md del alumno debe incluir: nombre, descripción breve, instrucciones de instalación (`pip install -r requirements.txt`), cómo configurar `config/config.yaml` para local y servidor, y órdenes exactas para ejecutar cada batería de tests.
- Entrega a través de **PLATEA** en la actividad correspondiente: se debe subir un **fichero PDF** que contenga el **enlace al repositorio del alumno** en Suleiman.
- **Planificación temporal:** la descrita en la actividad de PLATEA. El plazo **no será ampliable**.
- **Requisito de completitud:** deben completarse **ambas actividades** (PLATEA y repositorio) para considerar la entrega global como realizada.
- **Requisito crítico:** Si el profesor no puede arrancar el sistema y ejecutar los tests siguiendo las instrucciones del README, la implementación no se puede evaluar.

---

## 11. Dimensiones clave del diseño

Estas son las dimensiones que el profesor evaluará transversalmente en ambas actividades:

| Relevancia | Dimensión | Criterios principales |
|------------|-----------|----------------------|
| Alta | **Comunicación FIPA-ACL** | Performativas correctas, JSON estructurado, campo `thread` para identificar partidas, `Template` para filtrar, ontología coherente. |
| Alta | **Diseño de comportamientos** | FSM del tablero correcta con todos los estados. Búsqueda periódica de tableros. Creación dinámica de comportamientos de partida. Al menos 3 partidas simultáneas. Limpieza de behaviours al finalizar. Atención a `game-report` sin interferir con el juego. |
| Media | **Descubrimiento MUC** | Uso correcto de la sala MUC. Plugin XEP-0045. Detección de tableros por apodo. Actualización de estado (`waiting`/`playing`/`finished`). Gestión de desconexiones. |
| Media | **Interfaz web** | Rutas JSON conformes a la ontología. HTML con rejilla, turno e historial. Actualización en tiempo real. |
| Media | **Estrategia de juego** | Mínimo nivel posicional. Se valora razonamiento sobre el estado. La estrategia no debe estar acoplada al agente. |
| Alta | **Robustez** | Tolerancia al orden de arranque arbitrario. Gestión de timeouts. Mensajes `not-understood` ante mensajes malformados. Registro de trazas de errores sin silenciar excepciones. |

---

## 12. Reglas de código (recordatorio)

Todo el código debe cumplir las siguientes reglas de la asignatura:

1. **Todo en español:** respuestas, comentarios, docstrings, documentación, mensajes de error.
2. **Código didáctico:** orientado a estudiantes universitarios.
3. **Nunca incluir en el código:** URLs, puertos, credenciales. Siempre leer de `config/config.yaml`.
4. **Nunca `break` en bucles:** usar variable de control booleana.
5. **Punto de retorno único:** cada función debe tener un solo `return` al final.
6. **Imports organizados:** stdlib, third-party, locales, separados por línea en blanco.
7. **Typing hints:** en parámetros y retorno de todas las funciones.
8. **Docstrings:** formato Google Style en todas las clases y funciones públicas.
9. **Async/await:** para todo lo que involucre SPADE behaviours.
10. **Manejo de errores:** `try/except` con registro de trazas, nunca silenciar excepciones.

---

## 13. Preguntas frecuentes

**P: ¿Puedo usar el panel web que SPADE trae por defecto?**
R: El panel de SPADE (`/spade`) es independiente de la interfaz web obligatoria. Puedes activarlo para depuración, pero las rutas `/game` y `/game/state` son requisitos separados que debes implementar tú.

**P: ¿Cómo gestiono el `thread` en los mensajes?**
R: El Tablero genera un hilo único al aceptar una inscripción (por ejemplo, `f"game-{self.tablero_id}-{timestamp}"`) y lo usa en todos los mensajes de esa partida. El Jugador extrae el `thread` del primer mensaje recibido y lo usa como filtro en su `Template`.

**P: ¿Qué pasa si el Supervisor solicita un informe y la partida no ha terminado?**
R: El Tablero responde con `REFUSE` y `{"action": "game-report", "reason": "not-finished"}`. Usa el constructor `crear_cuerpo_game_report_refused()`.

**P: ¿Puedo modificar la ontología?**
R: No. La ontología es compartida entre todos los alumnos y el Supervisor del profesor. Cualquier modificación impedirá la interoperabilidad.

**P: ¿Cómo demuestro que mi jugador gestiona 3 partidas simultáneas?**
R: Arranca 3 tableros y al menos 2 jugadores. Los logs deben mostrar que un mismo jugador mantiene comportamientos activos en distintos tableros con hilos (`thread`) diferentes.

**P: ¿Qué versión de Python debo usar?**
R: Python 3.11 o superior (necesario para la sintaxis `str | None` usada en la ontología).

---

## 14. Bibliografía

- **SPADE Documentation:** https://spade-mas.readthedocs.io/
- **FIPA ACL Message Structure (FIPA00061):** http://www.fipa.org/specs/fipa00061/
- **FIPA Request Interaction Protocol (FIPA00026):** http://www.fipa.org/specs/fipa00026/
- **FIPA Contract Net Interaction Protocol (FIPA00029):** http://www.fipa.org/specs/fipa00029/
- **XEP-0045 Multi-User Chat:** https://xmpp.org/extensions/xep-0045.html
- **JSON Schema Specification (2020-12):** https://json-schema.org/specification
- **jsonschema (Python library):** https://python-jsonschema.readthedocs.io/
- **pytest Documentation:** https://docs.pytest.org/
- **pytest-asyncio:** https://pytest-asyncio.readthedocs.io/
- **aiohttp Testing:** https://docs.aiohttp.org/en/stable/testing.html
- **BeautifulSoup4:** https://www.crummy.com/software/BeautifulSoup/bs4/doc/
