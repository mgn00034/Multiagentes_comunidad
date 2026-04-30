# Guía: Módulo de utilidades (`utils.py`) y test de conexión XMPP

**Asignatura:** Sistemas Multiagente — Grado en Ingeniería Informática
**Universidad de Jaén — Departamento de Informática**

---

## 1. Motivación

En SPADE 4.x los parámetros de conexión de un agente se reparten entre **dos
puntos distintos** de la API:

| Parámetro | ¿Dónde se pasa? | Descripción |
|-----------|-----------------|-------------|
| `port` | Constructor del agente | Puerto TCP del servidor XMPP |
| `verify_security` | Constructor del agente | Si se verifica el certificado TLS |
| `auto_register` | Método `start()` | Si el agente se auto-registra en el servidor |

Si se pasa `auto_register` al constructor (error muy frecuente), Python lanza
un `TypeError` porque el constructor no reconoce ese parámetro. Para evitar que
el alumno tenga que recordar esta separación, el módulo `utils.py` proporciona
**funciones factoría** que encapsulan la creación y el arranque de agentes de
forma correcta.

---

## 2. Arquitectura de configuración

El proyecto Tic-Tac-Toe organiza la configuración en el directorio `config/`:

```
config/
├── config.yaml        ← Perfiles XMPP, LLM y parámetros del sistema
├── agents.yaml        ← Definición de agentes (nombre, clase, módulo)
└── configuracion.py   ← Funciones de carga: cargar_configuracion(),
                         cargar_agentes(), construir_jid()
```

El módulo `utils.py` (en la raíz del proyecto) **re-exporta** las funciones de
`config/configuracion.py` y añade las funciones factoría `crear_agente()` y
`arrancar_agente()`. De esta forma, el alumno puede importar todo desde un
único punto:

```python
from utils import cargar_configuracion, crear_agente, arrancar_agente
```

---

## 3. Contenido de `utils.py`

### 3.1. Funciones re-exportadas de `config/configuracion.py`

- **`cargar_configuracion(ruta)`** — Carga `config.yaml` y resuelve el perfil
  XMPP y LLM activos.
- **`cargar_agentes(ruta, solo_activos)`** — Carga `agents.yaml` y devuelve la
  lista de definiciones de agentes.
- **`construir_jid(nombre, config_xmpp)`** — Construye el JID completo
  `nombre@dominio` a partir del perfil XMPP activo.

### 3.2. `crear_agente(clase_agente, nombre, config_xmpp, contrasena)`

```python
def crear_agente(
    clase_agente: type[Agent],
    nombre: str,
    config_xmpp: dict[str, Any],
    contrasena: str | None = None,
) -> Agent:
```

Función factoría que instancia un agente SPADE. Internamente:

1. Construye el JID llamando a `construir_jid()`.
2. Usa `password_defecto` del perfil si no se proporciona contraseña.
3. Pasa al constructor **solo** los parámetros que acepta: `port` y
   `verify_security`.
4. **No** pasa `auto_register` al constructor (eso lo hace
   `arrancar_agente()`).

**Ejemplo de uso:**

```python
from utils import crear_agente
from agentes.agente_tablero import AgenteTablero

config = cargar_configuracion()
config_xmpp = config["xmpp"]

agente = crear_agente(AgenteTablero, "tablero_mesa1", config_xmpp)
```

### 3.3. `arrancar_agente(agente, config_xmpp)`

```python
async def arrancar_agente(
    agente: Agent,
    config_xmpp: dict[str, Any],
) -> None:
```

Arranca un agente ya creado pasando `auto_register` al método `start()`, que es
donde SPADE 4.x espera recibirlo. Esta función es `async` y debe invocarse con
`await`.

**Ejemplo de uso:**

```python
agente = crear_agente(AgenteTablero, "tablero_mesa1", config_xmpp)
await arrancar_agente(agente, config_xmpp)
```

---

## 4. Correspondencia con `config.yaml`

Las funciones factoría leen las siguientes claves del diccionario `config_xmpp`
(perfil XMPP ya resuelto por `cargar_configuracion()`):

| Clave en `config.yaml` | Función que la usa | Parámetro SPADE |
|-------------------------|--------------------|-----------------|
| `dominio` | `construir_jid()` | Parte del JID (`nombre@dominio`) |
| `puerto` | `crear_agente()` | `port` (constructor) |
| `verify_security` | `crear_agente()` | `verify_security` (constructor) |
| `password_defecto` | `crear_agente()` | `password` (constructor) |
| `auto_register` | `arrancar_agente()` | `auto_register` (start) |

---

## 5. Flujo completo: creación y arranque de un agente

```
config/config.yaml + config/agents.yaml
    │
    ▼
cargar_configuracion()          cargar_agentes()
    │                               │
    ├── perfil_activo → "local"     ├── lista de definiciones
    │                               │
    ▼                               ▼
config_xmpp = config["xmpp"]   definiciones (nombre, clase, módulo, ...)
    │                               │
    └───────────┬───────────────────┘
                │
                ▼
crear_agente(ClaseAgente, nombre, config_xmpp)
    │
    ├── construir_jid(nombre, config_xmpp)  →  "nombre@dominio"
    ├── ClaseAgente(jid, password, port=..., verify_security=...)
    │
    ▼
agente (instancia creada, sin conectar)
    │
    ▼
arrancar_agente(agente, config_xmpp)
    │
    └── agente.start(auto_register=...)
    │
    ▼
agente conectado y operativo
```

---

## 6. Relación con `main.py`

El lanzador `main.py` ya contiene su propia función `crear_instancia_agente()`
que realiza pasos adicionales específicos del sistema (inyección de parámetros
de agente, configuración LLM, ajuste de puerto no estándar, etc.). Las
funciones factoría de `utils.py` son una versión simplificada pensada para:

- **Tests de conexión** — donde solo se necesita un agente básico.
- **Prototipos rápidos** — para probar un agente sin toda la maquinaria de
  `main.py`.
- **Código del alumno** — cuando se necesita crear agentes en scripts auxiliares
  o en tests de integración.

---

## 7. Test de conexión XMPP (`tests/test_conexion_xmpp.py`)

Este script permite verificar que el servidor XMPP es accesible y que un agente
SPADE puede registrarse y conectarse correctamente. Es útil como primera
comprobación antes de desarrollar los agentes del proyecto.

### 7.1. Uso desde la línea de comandos

```bash
# Probar solo el perfil local (localhost:5222)
python -m tests.test_conexion_xmpp local

# Probar solo el servidor de la asignatura (sinbad2.ujaen.es:8022)
python -m tests.test_conexion_xmpp servidor

# Probar ambos perfiles (por defecto)
python -m tests.test_conexion_xmpp ambos
```

### 7.2. Qué hace el test

Para cada perfil seleccionado, ejecuta dos pasos:

1. **Verificación de red** — Comprueba que el puerto TCP del servidor XMPP está
   abierto (`verificar_puerto()`). Si no lo está, informa de las posibles
   causas (servidor no arrancado, firewall, nombre de host no resuelto).

2. **Conexión SPADE** — Crea un agente temporal de prueba usando
   `crear_agente()` y lo arranca con `arrancar_agente()`. Tras una breve
   espera, comprueba si el agente está vivo (`is_alive()`). Finalmente, lo
   detiene de forma limpia.

### 7.3. Credenciales del agente de prueba

El test usa credenciales basadas en la `password_defecto` del perfil XMPP
activo (definida en `config/config.yaml`). El nombre del agente de prueba se
genera con un **sufijo aleatorio** para evitar conflictos con usuarios ya
registrados en el servidor:

```python
USUARIO_PRUEBA = f"prueba_conexion_{uuid.uuid4().hex[:8]}"
# Ejemplo: "prueba_conexion_a3f7b2c1"
```

> **¿Por qué un sufijo aleatorio?** — Cuando un usuario ya existe en el
> servidor XMPP con una contraseña diferente, SPADE ignora silenciosamente
> el error de conflicto durante el auto-registro (xep_0077) y la
> autenticación posterior falla con `not-authorized`. Usar un nombre único
> en cada ejecución garantiza que el registro siempre sea de un usuario nuevo.

Si el perfil tiene `auto_register: true` (valor por defecto en ambos perfiles),
el agente se registrará automáticamente en el servidor.

### 7.4. Interpretación de resultados

| Resultado | Significado |
|-----------|-------------|
| Paso 1 OK + Paso 2 OK | El servidor XMPP funciona y acepta agentes SPADE |
| Paso 1 OK + Paso 2 FALLO | El puerto está abierto pero el agente no consigue conectarse (posible problema de credenciales o configuración XMPP) |
| Paso 1 FALLO | El servidor no es alcanzable (no arrancado, firewall, DNS) |

### 7.5. Ejemplo de salida exitosa

```
[INFO] Configuración cargada desde config/config.yaml
============================================================
[INFO] Probando perfil: servidor (sinbad2.ujaen.es:8022)
============================================================
[INFO] [Paso 1] Verificando alcanzabilidad del puerto...
[INFO]   OK: Puerto 8022 abierto en sinbad2.ujaen.es
[INFO] [Paso 2] Conectando agente SPADE de prueba...
[INFO]   Intentando conectar agente: prueba_conexion_a3f7b2c1@sinbad2.ujaen.es (puerto 8022)
[INFO]   ¡Conexión exitosa! El agente prueba_conexion_a3f7b2c1@sinbad2.ujaen.es está vivo.
[INFO]   Agente prueba_conexion_a3f7b2c1@sinbad2.ujaen.es detenido correctamente.
[INFO]   RESULTADO: Perfil 'servidor' → CORRECTO
============================================================
[INFO] RESUMEN DE PRUEBAS DE CONEXIÓN XMPP
============================================================
[INFO]   servidor     → CORRECTO
============================================================
[INFO] Todas las pruebas de conexión superadas.
```

---

## 8. Integración en el proyecto del alumno

Para utilizar las funciones factoría en tu código (por ejemplo, en tests de
integración o scripts auxiliares):

```python
# Crear y arrancar un agente de forma correcta
from utils import cargar_configuracion, crear_agente, arrancar_agente
from agentes.agente_jugador import AgenteJugador

config = cargar_configuracion()
config_xmpp = config["xmpp"]

agente = crear_agente(AgenteJugador, "jugador_prueba", config_xmpp)
await arrancar_agente(agente, config_xmpp)
```

Esto es equivalente a escribir manualmente:

```python
# Forma manual (propensa a errores):
jid = "jugador_prueba@localhost"
agente = AgenteJugador(
    jid, "secret",
    port=5222,
    verify_security=False,
)
await agente.start(auto_register=True)
```

La ventaja de las funciones factoría es que los parámetros se leen
automáticamente del perfil XMPP activo en `config.yaml`, evitando valores
escritos directamente en el código y errores de API.

---

*Sistemas Multiagente — Grado en Ingeniería Informática — Universidad de Jaén — Curso 2025-2026*