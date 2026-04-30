# Carpeta `config/` — Configuración centralizada

## Propósito

Aquí residen los ficheros de configuración que permiten ejecutar el
sistema y las pruebas tanto en el entorno local (localhost) como contra
el servidor de la asignatura (sinbad2.ujaen.es) sin modificar ni una
sola línea de código fuente.

## Ficheros incluidos

### `config.yaml` — Perfiles de conexión

Define dos bloques de perfiles con un campo `perfil_activo` en cada uno:

**Perfiles XMPP** (obligatorio para todos los niveles de estrategia):

| Perfil | Host | Puerto | Dominio | Sala MUC |
|--------|------|--------|---------|----------|
| `local` | `localhost` | 5222 | `localhost` | `tictactoe@conference.localhost` |
| `servidor` | `sinbad2.ujaen.es` | 8022 | `sinbad2.ujaen.es` | `tictactoe@conference.sinbad2.ujaen.es` |

**Perfiles LLM** (solo necesario para estrategia nivel 4):

| Perfil | URL base | Modelo por defecto | Modelos disponibles |
|--------|----------|-------------------|---------------------|
| `local` | `http://localhost:11434` | `llama3.2:3b` | `llama3.2:3b`, `gemma3:4b` |
| `servidor` | `http://sinbad2ia.ujaen.es:8050` | `llama3:8b` | `llama3:8b`, `qwen3:32b` |

**Parámetros del sistema:** intervalos de búsqueda MUC, máximo de
partidas simultáneas, tiempos de espera de inscripción y turno, puerto web
base y nivel de registro de trazas.

Para cambiar de entorno, edita el campo `perfil_activo` en la sección
correspondiente. El resto del sistema lee automáticamente los datos
del perfil seleccionado.

### `agents.yaml` — Definición de agentes

Lista de agentes que el lanzador (`main.py`) instanciará dinámicamente.
Cada entrada contiene: `nombre` (parte local del JID), `clase` (nombre
de la clase Python), `modulo` (ruta del módulo en notación de puntos),
`nivel`, `descripcion`, `parametros` (diccionario inyectado al agente)
y `activo` (true/false para activar o desactivar sin borrar).

El JID completo se construye automáticamente como
`nombre@dominio_del_perfil_xmpp_activo`.

### `salas_laboratorio.yaml` — Salas MUC del modo laboratorio

Define 30 salas MUC individuales (`sala_pc01` a `sala_pc30`), una por
cada puesto del laboratorio. Lo usa `supervisor_main.py --modo laboratorio`
para crear las salas en el servidor XMPP antes de que los alumnos
conecten sus agentes.

### `sala_torneo.yaml` — Sala MUC del modo torneo

Define una única sala MUC compartida (`torneo_lab`) donde todos los
alumnos conectan sus agentes simultáneamente. Lo usa
`supervisor_main.py --modo torneo`.

### `torneos.yaml` — Definición genérica de torneos

Fichero completo con las salas de ambas fases (Fase A con las 30 salas
individuales y Fase B con la sala de torneo). Pensado para uso con
`main.py` en pruebas locales donde todos los agentes arrancan en el
mismo ordenador.

Los tres ficheros de salas comparten el mismo formato YAML: una clave
`torneos` con una lista de entradas que contienen `nombre`, `sala`,
`descripcion`, `tableros` y `jugadores`.

### `configuracion.py` — Módulo de carga

Funciones que leen los YAML, resuelven el perfil activo y devuelven
diccionarios listos para usar:

- `cargar_configuracion(ruta)` → dict con claves `"xmpp"`, `"llm"` y `"sistema"`.
- `cargar_agentes(ruta, solo_activos)` → lista de diccionarios de agentes.
- `cargar_torneos(ruta)` → lista de diccionarios con la definición de
  cada torneo/sala (nombre, sala, descripcion). Devuelve lista vacía
  si el fichero no existe (los torneos son opcionales).
- `construir_jid(nombre, config_xmpp)` → JID completo como cadena.

Tanto `main.py` como `supervisor_main.py` y `conftest.py` importan
estas funciones, de modo que agentes, supervisor y pruebas leen siempre
los mismos parámetros de la misma fuente.

## Recordatorio

- Nunca escribir directamente en el código URLs, puertos, nombres de
  servidor ni contraseñas. Todo debe venir de `config.yaml`.
- El cambio entre entorno local y servidor se hace editando los campos
  `perfil_activo`, sin tocar nada más.
- Si añades parámetros nuevos (por ejemplo, un retardo personalizado
  o un umbral de confianza para la estrategia LLM), inclúyelos en la
  sección `sistema` del YAML en lugar de usar constantes en el código.
