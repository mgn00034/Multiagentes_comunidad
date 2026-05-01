# Pasos para integrar correctamente la factoría de agentes

Este documento recoge la lista ordenada de pasos que debe aplicar el alumno
para que su proyecto utilice correctamente las funciones factoría
`crear_agente()` y `arrancar_agente()` definidas en `utils.py`, tal y como
se describen en la rama `feature/utils-factoria-agentes` y en la guía
`doc/guia_utils_y_test_conexion.md`.

El objetivo es eliminar la duplicación de lógica de creación de agentes que
hay actualmente en `main.py` y en el fixture `tests/agent_factory.py`, y
centralizar todo el código de instanciación/arranque en `utils.py`.

---

## Diagnóstico previo (estado actual del proyecto)

Antes de aplicar los pasos, conviene comprender qué está mal:

1. `utils.py` ya contiene `crear_agente()` y `arrancar_agente()`, pero
   **casi nadie las usa**. Solo `tests/test_conexion_xmpp.py` las invoca.
2. `main.py` define una función propia `crear_instancia_agente()` que
   duplica la lógica de la factoría, **omite el parámetro `port`** del
   constructor de SPADE y necesita un parche posterior
   (`agente.stream.peer_jid_domain = ...`) para que funcione en servidores
   con puerto no estándar (p. ej. 8022 en `sinbad2`).
3. `main.py` llama directamente a `await agente.start(auto_register=...)`
   en lugar de delegar en `arrancar_agente()`.
4. `tests/agent_factory.py` es un fixture casero que **hardcodea**
   `@localhost`, la contraseña `"test"` y un kwarg `arrancar_web=False`
   que no existe en `spade.agent.Agent`.

Los pasos siguientes resuelven los cuatro puntos anteriores.

---

## Paso 0. Adoptar los ficheros que aporta la rama `feature/utils-factoria-agentes`

La rama `feature/utils-factoria-agentes` del repositorio del profesor
(`git@gitlab.com:ssmmaa/curso2025-26/tictactoe-nivel1.git`) **añade tres
ficheros nuevos** que deben incorporarse al proyecto del alumno:

| Fichero | Tipo | Función |
|---------|------|---------|
| `utils.py` | **Nuevo** | Contiene la factoría (`crear_agente`, `arrancar_agente`) y re-exporta `cargar_configuracion`, `cargar_agentes`, `construir_jid`. |
| `docs/guia_utils_y_test_conexion.md` | **Nuevo** | Guía didáctica del módulo `utils.py` y del test de conexión. |
| `tests/test_conexion_xmpp.py` | **Nuevo** | Test de humo que comprueba que un agente real puede conectar al servidor XMPP usando la factoría. |

> **Nota sobre la carpeta `docs/` vs `doc/`:** la rama del profesor usa
> `docs/` (con `s` final). El proyecto del alumno usa `doc/`. Al copiar la
> guía, conviene **mantener el nombre `doc/` que ya usa el alumno** para no
> romper enlaces internos del proyecto.

### 0.1. Opción recomendada (con Git): añadir el repositorio del profesor como remoto

Esta opción permite traer exactamente las versiones publicadas por el
profesor y volver a actualizarlas en el futuro con un simple `git fetch`.

```bash
# Añadir el repositorio del profesor como un remoto adicional llamado "profesor"
git remote add profesor git@gitlab.com:ssmmaa/curso2025-26/tictactoe-nivel1.git

# Descargar las ramas del profesor (no fusiona nada todavía)
git fetch profesor

# Crear una rama local para integrar la factoría sin tocar la rama actual
git checkout -b integrar-factoria

# Traer cada fichero por separado desde la rama del profesor
git checkout profesor/feature/utils-factoria-agentes -- utils.py
git checkout profesor/feature/utils-factoria-agentes -- tests/test_conexion_xmpp.py

# La guía didáctica viene en docs/, pero la copiamos a doc/ para respetar
# la estructura del proyecto del alumno
git show profesor/feature/utils-factoria-agentes:docs/guia_utils_y_test_conexion.md \
    > doc/guia_utils_y_test_conexion.md

# Revisar y commitear
git status
git add utils.py tests/test_conexion_xmpp.py doc/guia_utils_y_test_conexion.md
git commit -m "Incorporar factoría de agentes desde rama del profesor"
```

### 0.2. Opción alternativa (sin Git): copia manual

Si no se puede acceder al repositorio remoto del profesor, basta con
copiar los tres ficheros desde una clonación local del proyecto de
referencia:

1. Situarse en la rama correcta del proyecto de referencia:

   ```bash
   cd /ruta/al/proyecto/del/profesor
   git checkout feature/utils-factoria-agentes
   ```

2. Copiar los tres ficheros al proyecto del alumno:

   ```bash
   cp utils.py                                 /ruta/al/proyecto/alumno/
   cp tests/test_conexion_xmpp.py              /ruta/al/proyecto/alumno/tests/
   cp docs/guia_utils_y_test_conexion.md       /ruta/al/proyecto/alumno/doc/
   ```

3. Volver al proyecto del alumno y commitear:

   ```bash
   cd /ruta/al/proyecto/alumno
   git add utils.py tests/test_conexion_xmpp.py doc/guia_utils_y_test_conexion.md
   git commit -m "Incorporar factoría de agentes desde rama del profesor"
   ```

### 0.3. Qué **NO** se debe traer de la rama del profesor

La rama `feature/utils-factoria-agentes` también contiene cambios sobre la
ontología (`ontologia/*.py`, `ontologia/*.json`), borrados de
documentación antigua (`doc/GUIA_TABLERO_TORNEO.md`,
`doc/GUIA_THREAD_Y_GAME_START.md`, `doc/svg/*`) y el script
`scripts/comprobar_mensaje_game_start.py`. **No los toques** desde este
documento: pertenecen a otras tareas, y mezclarlos con la migración a la
factoría dificultaría la revisión del cambio.

### 0.4. Verificación tras la adopción

Comprobar que los tres ficheros existen y son sintácticamente correctos:

```bash
ls utils.py
ls tests/test_conexion_xmpp.py
ls doc/guia_utils_y_test_conexion.md
python -c "from utils import crear_agente, arrancar_agente; print('OK')"
```

Si la última orden imprime `OK`, la factoría se ha adoptado correctamente
y se puede continuar con el Paso 1.

---

## Paso 1. Verificar que `utils.py` está correcto

1.1. Abrir `utils.py` (raíz del proyecto) y comprobar que contiene
exactamente:

- La re-exportación de `cargar_configuracion`, `cargar_agentes` y
  `construir_jid` desde `config.configuracion`.
- La función `crear_agente(clase_agente, nombre, config_xmpp, contrasena=None)`.
- La función asíncrona `arrancar_agente(agente, config_xmpp)`.

1.2. Si alguna de estas tres piezas falta o está modificada, **restaurar el
fichero** a partir de la rama `feature/utils-factoria-agentes` del proyecto
de referencia. **No modificar `utils.py`**: la factoría debe quedarse tal
cual la entrega el profesor.

---

## Paso 2. Eliminar la duplicación en `main.py`

2.1. **Añadir la importación de la factoría** al principio del fichero,
junto a las otras importaciones:

```python
from utils import crear_agente, arrancar_agente
```

2.2. **Eliminar** por completo la función `crear_instancia_agente()`
(actualmente entre las líneas ~106 y ~169 de `main.py`). Esa función
duplica lo que ya hace `crear_agente()`.

2.3. En `arrancar_sistema()`, sustituir el bloque que crea y arranca cada
agente por una llamada a las funciones factoría. El patrón correcto es:

```python
clase_agente = importar_clase_agente(
    definicion["modulo"], definicion["clase"]
)

agente = crear_agente(clase_agente, definicion["nombre"], config_xmpp)

# Inyectar parámetros y configuración como atributos del agente
agente.config_parametros = definicion.get("parametros", {})
agente.config_xmpp = config_xmpp
agente.config_llm = config_llm

await arrancar_agente(agente, config_xmpp)
```

2.4. **Eliminar** el parche del puerto:

```python
if puerto_xmpp != 5222:
    agente.stream.peer_jid_domain = config_xmpp["dominio"]
```

Este parche **deja de ser necesario** porque `crear_agente()` ya pasa
`port=config_xmpp.get("puerto", 5222)` al constructor del agente.

2.5. **Eliminar** la línea `await agente.start(auto_register=...)`. Ese
arranque lo hace ahora `arrancar_agente()`.

2.6. (Opcional, recomendado) Sustituir las importaciones desde
`config.configuracion` por importaciones desde `utils`, para usar el
**punto único** que recomienda la guía:

```python
from utils import cargar_configuracion, cargar_agentes
```

---

## Paso 3. Reescribir el fixture `tests/agent_factory.py`

3.1. Abrir `tests/agent_factory.py`. El contenido actual hardcodea
`@localhost` y un kwarg `arrancar_web=False` que **no existe** en
`spade.agent.Agent`.

3.2. Reemplazar el fichero por una versión que **delegue en la factoría**.
El fixture debe construir un `config_xmpp` de prueba (puede ser un
diccionario fijo apuntando a `localhost`) y usarlo con `crear_agente()` y
`arrancar_agente()`. Esquema sugerido:

```python
import pytest
from spade.agent import Agent
from utils import crear_agente, arrancar_agente


CONFIG_XMPP_TEST = {
    "dominio": "localhost",
    "puerto": 5222,
    "verify_security": False,
    "auto_register": False,
    "password_defecto": "test",
}


@pytest.fixture
def agent_factory():
    async def _crear(nombre, cls=Agent):
        agente = crear_agente(cls, nombre, CONFIG_XMPP_TEST)
        await arrancar_agente(agente, CONFIG_XMPP_TEST)
        return agente

    return _crear
```

3.3. Si alguno de los agentes del proyecto requiere parámetros extra
(`config_parametros`, `config_xmpp`, `config_llm`), inyectarlos como
atributos sobre el `agente` antes de llamar a `arrancar_agente()`, igual
que hace `main.py`.

---

## Paso 4. Revisar los tests aislados

Los siguientes ficheros usan el fixture `agent_factory` y, por tanto, se
benefician automáticamente del cambio del Paso 3:

- `tests/test_tablero_aislado.py`
- `tests/test_jugador_aislado.py`
- `tests/test_web_endpoints.py`

4.1. Verificar que cada test sigue compilando tras el cambio del fixture.
Si alguno espera el kwarg antiguo `arrancar_web=False`, sustituirlo por la
inyección equivalente como atributo del agente:

```python
agente.arrancar_web = False
```

(o eliminar la línea si la subclase ya lo gestiona por defecto).

---

## Paso 5. Comprobar que los tests pasan

5.1. Ejecutar la suite completa:

```bash
pytest -q
```

5.2. Prestar especial atención a:

- `tests/test_conexion_xmpp.py` (debe seguir pasando, ya usaba la factoría).
- Los tres tests aislados modificados en el Paso 4.

5.3. Si algún test falla por el cambio de firma del fixture (ahora
`agent_factory` recibe `nombre` en vez de `jid_local`), ajustar la llamada
en el test correspondiente.

---

## Paso 6. Comprobar el arranque real del sistema

6.1. Arrancar el sistema con la configuración del laboratorio:

```bash
python main.py --config config/config.yaml --agents config/agents.yaml
```

6.2. Verificar en los logs que:

- Cada agente se crea y arranca sin lanzar `TypeError` por
  `auto_register`.
- El puerto utilizado es el correcto (si el perfil XMPP indica un puerto
  distinto de 5222, debe respetarse **sin** parches manuales sobre
  `agente.stream.peer_jid_domain`).
- Los agentes se conectan correctamente al servidor XMPP del perfil
  activo.

---

## Paso 7. Comprobaciones finales (lista de verificación)

Antes de dar la migración por terminada, comprobar uno a uno:

- [ ] Los tres ficheros del Paso 0 están presentes en el proyecto:
      `utils.py`, `tests/test_conexion_xmpp.py` y
      `doc/guia_utils_y_test_conexion.md`.
- [ ] `utils.py` no se ha modificado respecto a la versión del profesor.
- [ ] `main.py` ya **no** contiene la función `crear_instancia_agente()`.
- [ ] `main.py` importa `crear_agente` y `arrancar_agente` desde `utils`.
- [ ] `main.py` ya **no** llama directamente a `agente.start(...)`.
- [ ] `main.py` ya **no** asigna `agente.stream.peer_jid_domain`.
- [ ] `tests/agent_factory.py` usa la factoría y ya no contiene
      `arrancar_web=False` ni `@localhost` hardcodeados de forma rígida.
- [ ] `pytest -q` termina en verde.
- [ ] El sistema arranca con `python main.py` contra el servidor real del
      laboratorio.

Solo cuando los ocho puntos anteriores se cumplan se puede considerar que
el proyecto utiliza correctamente la factoría definida en la rama
`feature/utils-factoria-agentes`.
