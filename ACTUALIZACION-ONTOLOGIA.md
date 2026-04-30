# Actualización de la ontología — Notas para los alumnos

**Fechas:** 2026-04-14 (turn-result) · 2026-04-23 (thread único y
`game-start` enriquecido)
**Alcance:** paquete `ontologia/` y `tests/test_ontologia.py`
**Afecta a:** implementación del Agente Tablero y del Agente Jugador

Este documento resume los cambios que se han introducido en el
vocabulario compartido de la ontología y explica qué modificaciones
debe contemplar el alumno en la implementación de los behaviours del
tablero y del jugador para que los agentes sigan respetando el
protocolo. Los cambios llegan en dos tandas:

1. **Tanda de 2026-04-14** — se añade la acción `turn-result`
   (INFORM Jugador → Tablero) para cerrar el ciclo Contract Net de
   cada turno.
2. **Tanda de 2026-04-23** — se unifica la generación de threads con
   la nueva utilidad `crear_thread_unico`, se eleva el thread de la
   partida al cuerpo del `game-start` y se amplía la firma de
   `crear_mensaje_join`.

La explicación detallada de la segunda tanda, con diagramas y
ejemplos, vive en
[`doc/GUIA_THREAD_Y_GAME_START.md`](doc/GUIA_THREAD_Y_GAME_START.md).
Este documento es la vista de conjunto: recoge ambas tandas en un
mismo sitio para que el alumno vea de un golpe qué tiene que
adaptar en su código.

---

## 1. Resumen de cambios

| Elemento | Antes | Ahora |
|---|---|---|
| Subesquemas del `oneOf` | 12 | **13** |
| Entradas en `CAMPOS_POR_ACCION` | 9 | **10** |
| Mensaje Jugador → Tablero «resultado del turno» | no existía | `turn-result` (2026-04-14) |
| Performativas en `PERFORMATIVA_POR_ACCION` | 10 | **11** |
| Constructores `crear_cuerpo_*` en `ontologia.py` | 13 | **14** |
| Campos del `game-start` | `opponent` | `opponent`, **`thread`** (2026-04-23) |
| Firma de `crear_cuerpo_game_start` | `(oponente)` | `(oponente, thread_partida)` (2026-04-23) |
| Firma de `crear_mensaje_join` | `(jid_tablero)` | `(jid_tablero, jid_jugador)` (2026-04-23) |
| Utilidad para generar threads únicos | no existía | **`crear_thread_unico`** (2026-04-23) |
| Reglas cruzadas en `validar_cuerpo` | 4 | **5** |
| Tests en `tests/test_ontologia.py` | 61 | **96** |

A efectos del protocolo, los cambios son **aditivos y bien
delimitados**: nada de lo que ya funcionaba ha cambiado de semántica.
Sí han cambiado dos firmas de constructores (`crear_cuerpo_game_start`
y `crear_mensaje_join`); el compilador no puede avisarte, así que
revisa los puntos de llamada al actualizar tu código.

---

## 2. Qué se ha añadido

### 2.A Tanda de 2026-04-14 — `turn-result`

#### 2.A.1 Nuevo tipo de mensaje `turn-result`

Cierra un hueco del protocolo Contract Net: tras cada turno, el
**jugador activo** informa al tablero del estado de la partida según
su propia evaluación del tablero local.

| Campo | Tipo | Obligatorio | Valores |
|---|---|---|---|
| `action` | string | sí | `"turn-result"` |
| `result` | string | sí | `"continue"` \| `"win"` \| `"draw"` |
| `winner` | string \| null | condicional | `"X"` \| `"O"` \| `null` |

- Si `result == "win"` ⇒ `winner` **obligatorio** (y no nulo).
- Si `result == "draw"` ⇒ `winner` debe ser `null`.
- Si `result == "continue"` ⇒ `winner` debe ser `null`.

**Performativa FIPA:** `INFORM`. Se consulta con
`obtener_performativa("turn-result")`.

**Dirección:** Jugador activo → Tablero (punto a punto, identificado
por `thread` como el resto de mensajes de partida).

#### 2.A.2 Nuevo constructor `crear_cuerpo_turn_result`

```python
from ontologia import crear_cuerpo_turn_result

# Partida en curso — ni victoria ni empate
body = crear_cuerpo_turn_result("continue")

# El movimiento que acabo de confirmar me da tres en raya
body = crear_cuerpo_turn_result("win", "X")

# Tablero lleno sin ganador
body = crear_cuerpo_turn_result("draw")
```

El constructor **valida por construcción**: si pasas
`crear_cuerpo_turn_result("win")` sin ganador, o
`crear_cuerpo_turn_result("continue", "X")` con ganador cuando no lo
hay, lanza `ValueError`. No hace falta validar los parámetros a mano
en el behaviour que lo invoca.

#### 2.A.3 Nuevas reglas cruzadas

El validador `validar_cuerpo` incluye la regla:

> Si `result == "continue"`, entonces `winner` debe ser `null`.

Esta regla complementa las tres que ya existían
(`win` ⇒ `winner` obligatorio, `draw` ⇒ `winner=null`,
`aborted` ⇒ `reason` obligatorio) y cierra el cuadro semántico del
campo `result` en cualquier mensaje.

Además la regla de `result="win"` se robustece: antes comprobaba
`"winner" not in cuerpo`, con lo que un mensaje con `winner: null`
explícito no disparaba; ahora se comprueba
`cuerpo.get("winner") is None`, que cubre ambos casos.

### 2.B Tanda de 2026-04-23 — thread único y `game-start`

#### 2.B.1 Utilidad `crear_thread_unico`

Se añade a `ontologia/ontologia.py`:

```python
from ontologia import (
    crear_thread_unico,
    PREFIJO_THREAD_JOIN, PREFIJO_THREAD_GAME, PREFIJO_THREAD_REPORT,
)

hilo = crear_thread_unico(str(self.agent.jid), PREFIJO_THREAD_GAME)
# → 'game-tablero_01-7f3cab92d4e14f7b9a1c0e2f8d5b6a3c'
```

El identificador combina **prefijo semántico** + **parte local del
JID emisor** + **UUID4 hexadecimal (128 bits)**. De esa forma es
imposible que dos agentes distintos del torneo generen el mismo
thread, ni siquiera aunque coincidan en el instante exacto de
creación.

**Regla general:** siempre que un agente necesite fijar el thread de
una conversación (`join`, `game-start`/partida, `game-report`…)
**debe** obtenerlo mediante `crear_thread_unico`. Las tres constantes
`PREFIJO_THREAD_*` existen para que todos los alumnos usen el mismo
vocabulario.

#### 2.B.2 El `game-start` incluye ahora `thread` en el cuerpo

El subesquema `MensajeGameStart` pasa a tener tres campos obligatorios:

| Campo | Tipo | Valor |
|---|---|---|
| `action` | string | `"game-start"` |
| `opponent` | string (no vacío) | JID del rival |
| `thread` | string (no vacío) | identificador de la partida |

Razón de ser: el `game-start` es el mensaje que cierra la inscripción
y abre la partida. Al incluir el thread también en el cuerpo, el
jugador puede construir el template de su behaviour de partida
**inmediatamente** al recibir `game-start`, sin esperar al primer
`CFP turn`. Evita una ventana de carrera en la que el turno podría
llegar antes de que el jugador haya registrado el filtro.

**Invariante:** `msg.thread == json.loads(msg.body)["thread"]`. Son
el mismo valor, en dos sitios, por conveniencia del receptor.

#### 2.B.3 Firma ampliada de `crear_cuerpo_game_start`

```python
# Antes:
body = crear_cuerpo_game_start("jugador_o@localhost")

# Ahora:
body = crear_cuerpo_game_start(
    oponente="jugador_o@localhost",
    thread_partida=thread_partida,
)
```

Si pasas una cadena vacía en cualquiera de los dos argumentos, el
constructor lanza `ValueError` (validación por construcción).

#### 2.B.4 Firma ampliada de `crear_mensaje_join`

```python
# Antes — el alumno tenía que añadir el thread a mano
mensaje = crear_mensaje_join(jid_tablero)
mensaje.thread = algun_identificador_generado_localmente

# Ahora — la función se encarga
mensaje = crear_mensaje_join(jid_tablero, str(self.agent.jid))
```

Internamente, `crear_mensaje_join` invoca `crear_thread_unico` con
`PREFIJO_THREAD_JOIN` y el JID del jugador, fijando `mensaje.thread`
antes de devolver el `Message`.

---

## 3. Lo que NO cambia

- `game-over` sigue representando **cierres anómalos** (movimiento
  inválido, timeout individual, timeout doble). Su contrato no se
  toca: `reason` obligatorio con enum
  `{"invalid", "timeout", "both-timeout"}` y `winner` opcional
  (`null` en `both-timeout`).
- Los tres mensajes del protocolo supervisor (`game-report` en sus
  tres variantes) no cambian de campos.
- Los constructores previos `crear_cuerpo_join`,
  `crear_cuerpo_move`, `crear_cuerpo_turn`, `crear_cuerpo_game_over`,
  etc. mantienen firma y semántica. **Excepción**:
  `crear_cuerpo_game_start` y `crear_mensaje_join` sí han cambiado de
  firma (ver § 2.B.3 y § 2.B.4).
- La carga del esquema
  (`_DIRECTORIO_ACTUAL / "ontologia_tictactoe.schema.json"`) sigue
  siendo relativa al paquete `ontologia/`, sin cambios para el
  alumno.
- El identificador de conversación `conversation-id` solo se usa en
  los REQUEST que inician protocolo (`"join"` y `"game-report"`); el
  resto de mensajes se correlacionan por `thread`.

---

## 4. Qué debe cambiar el alumno en su implementación

### 4.1 Agente Tablero

#### 4.1.1 Ciclo de turnos — nuevo estado de espera (tanda 2026-04-14)

El ciclo de un turno añade un paso respecto a la versión anterior:

![Ciclo de turno del Agente Tablero — antes y después](doc/svg/flujo-turn-result-antes-despues.svg)

Consecuencias para el behaviour de turno:

- **Añade un estado nuevo** a la FSM del tablero (p. ej.
  `ESPERANDO_TURN_RESULT`) entre «movimiento confirmado» y
  «siguiente turno». Este estado filtra con `Template` por
  `performative="inform"` y `thread=<id_partida>`.
- **No emitas el siguiente `CFP turn`** hasta haber recibido y
  validado el `turn-result`. Si ya lo enviabas inmediatamente después
  del `ACCEPT_PROPOSAL`, debes aplazarlo.
- **Tiempo de espera:** decide un timeout razonable para
  `turn-result`. Si expira, cierra la partida con
  `crear_cuerpo_game_over("timeout", simbolo_rival)` porque el
  jugador activo ha incumplido el protocolo.
- **Doble verificación recomendada:** aunque el jugador te diga que
  `result="win"`, el tablero debería comprobar por sí mismo el
  estado de su tablero local antes de darlo por válido. La palabra
  del jugador es la que cierra formalmente la partida, pero el
  tablero es el árbitro último en caso de torneo (es una defensa
  simple contra agentes maliciosos de otros alumnos).

```python
# Dentro del behaviour que espera el turn-result
from ontologia import validar_cuerpo
import json

cuerpo = json.loads(msg.body)
resultado = validar_cuerpo(cuerpo)
if resultado["valido"]:
    if cuerpo["result"] == "continue":
        # Conmutar simbolo activo y emitir nuevo CFP turn
        ...
    elif cuerpo["result"] == "win":
        ganador = cuerpo["winner"]
        # Cerrar partida, almacenar ganador, eventualmente
        # responder a game-report del supervisor
        ...
    elif cuerpo["result"] == "draw":
        # Cerrar partida como empate
        ...
else:
    # Protocolo incumplido: turn-result malformado
    # Opcional: game-over con reason="invalid"
    ...
```

#### 4.1.2 Generación del thread de partida (tanda 2026-04-23)

Al formar pareja (tras enviar el segundo `join-accepted`), el tablero
debe generar **un thread único por partida** con la utilidad común y
usarlo en **todos** los mensajes de esa partida:

```python
from ontologia import (
    PREFIJO_THREAD_GAME,
    crear_cuerpo_game_start,
    crear_thread_unico,
    obtener_performativa,
    ONTOLOGIA,
)

thread_partida = crear_thread_unico(
    str(self.agent.jid), PREFIJO_THREAD_GAME,
)

for jid_jugador, jid_oponente in ((jid_x, jid_o), (jid_o, jid_x)):
    mensaje = Message(to=str(jid_jugador))
    mensaje.set_metadata("ontology", ONTOLOGIA)
    mensaje.set_metadata(
        "performative", obtener_performativa("game-start"),
    )
    mensaje.thread = thread_partida
    mensaje.body = crear_cuerpo_game_start(
        oponente=str(jid_oponente),
        thread_partida=thread_partida,
    )
    await self.send(mensaje)
```

A partir de aquí, todos los `CFP turn`, `ACCEPT_PROPOSAL`,
`turn-result` y (en su caso) `game-over` de esta partida se envían
con `msg.thread = thread_partida`.

#### 4.1.3 Impacto en el informe al supervisor

`game-report` hacia el supervisor no cambia de campos. Lo único que
cambia es que el tablero ahora **conoce antes** el resultado (se lo
ha dicho el jugador), así que puede construirlo con menos
ambigüedad. El valor del campo `result` en `game-report` puede
derivarse directamente del `result` del `turn-result` recibido,
excepto el caso `aborted`, que sigue viniendo de un cierre por
`game-over`.

### 4.2 Agente Jugador

#### 4.2.1 Usar `crear_mensaje_join` con la nueva firma

El `REQUEST join` debe construirse con los dos argumentos:

```python
from ontologia import crear_mensaje_join

mensaje = crear_mensaje_join(jid_tablero, str(self.agent.jid))
await self.send(mensaje)
```

`crear_mensaje_join` se encarga internamente de fijar el `thread`
con `crear_thread_unico`; el alumno no debe asignarlo a mano.

#### 4.2.2 Registrar el behaviour de partida al recibir `game-start`

El cuerpo del `game-start` trae el `thread` de la partida. El
jugador debe leerlo inmediatamente y registrar un behaviour de
partida cuyo `Template` filtre por ese thread, **antes** de
devolver el control al bucle SPADE:

```python
import json
from spade.template import Template
from ontologia import ONTOLOGIA

cuerpo = json.loads(msg.body)
thread_partida = cuerpo["thread"]
oponente = cuerpo["opponent"]

plantilla = Template()
plantilla.thread = thread_partida
plantilla.set_metadata("ontology", ONTOLOGIA)

self.agent.add_behaviour(
    BehaviourPartida(oponente, self.simbolo_propio),
    plantilla,
)
```

Así, cuando llegue el primer `CFP turn`, encontrará ya su template
registrado y se encaminará al behaviour correcto.

#### 4.2.3 Aplicar, evaluar, informar (ciclo de turno)

Tras recibir el `ACCEPT_PROPOSAL` del tablero con su propio
movimiento confirmado (es decir, cuando el `symbol` del mensaje
coincide con el símbolo propio del jugador), el jugador activo debe:

1. **Aplicar** la posición confirmada en su tablero local.
2. **Evaluar** si hay línea ganadora, empate (tablero lleno sin
   ganador) o continuación.
3. **Emitir** `turn-result` con la performativa `inform` al tablero,
   usando el constructor correspondiente.

```python
from ontologia import (
    crear_cuerpo_turn_result, obtener_performativa, ONTOLOGIA,
)

# Suponiendo que estrategia.evaluar(tablero_local, simbolo_propio)
# devuelve ("continue"|"win"|"draw", ganador_o_None).
resultado, ganador = evaluar(tablero_local, simbolo_propio)

body = crear_cuerpo_turn_result(resultado, ganador)

respuesta = Message(to=str(jid_tablero))
respuesta.set_metadata("performative", obtener_performativa("turn-result"))
respuesta.set_metadata("ontology", ONTOLOGIA)
respuesta.set_metadata("thread", thread_partida)
respuesta.body = body
await self.send(respuesta)
```

#### 4.2.4 Jugador no-activo

El `ACCEPT_PROPOSAL` también llega al jugador no-activo (el tablero
lo notifica a ambos para que mantengan su tablero local
sincronizado). El jugador no-activo debe:

- Aplicar el movimiento en su tablero local.
- **No** emitir `turn-result`. Esa responsabilidad es exclusiva del
  jugador activo.
- Esperar el siguiente mensaje del tablero (normalmente otro
  `CFP turn` o, si la partida terminó, la notificación
  correspondiente).

### 4.3 Validación recíproca

Los alumnos deben incluir en sus tests unitarios del behaviour del
tablero al menos dos escenarios nuevos para la tanda 2026-04-14:

1. **Secuencia feliz:** `CFP turn` → `PROPOSE move` →
   `ACCEPT_PROPOSAL` → `INFORM turn-result (continue)` → se emite
   nuevo `CFP turn`.
2. **Cierre por victoria:** igual pero con
   `INFORM turn-result (win, X)` → no se emite nuevo `CFP turn`, la
   partida cierra y el tablero queda listo para responder a
   `game-report`.

Un escenario adicional para el jugador:

3. Tras recibir `ACCEPT_PROPOSAL` con su propio símbolo, el jugador
   construye un `turn-result` con los campos correctos y lo envía
   con performativa `inform`.

Para la tanda 2026-04-23 conviene añadir además:

4. Tras recibir `game-start`, `self.agent.behaviours` contiene un
   behaviour cuyo template filtra exactamente el `thread` incluido
   en `body["thread"]`.
5. Dos invocaciones consecutivas de `crear_mensaje_join` con los
   mismos JIDs producen threads distintos (garantía del UUID4).

---

## 5. Cambios en los tests del proyecto

- `tests/test_ontologia.py` acumula ambas tandas y pasa de 61 a
  **96 tests** verdes.
- Se renombró `test_esquema_tiene_12_subesquemas` a
  `test_esquema_tiene_13_subesquemas`.
- `test_todas_acciones_en_mapa` ahora espera
  `len(CAMPOS_POR_ACCION) == 10`.
- Tests específicos añadidos para la tanda 2026-04-23:
  `test_game_start_incluye_thread_en_body`,
  `test_game_start_con_thread_generado_dinamicamente`,
  `test_game_start_thread_vacio_lanza_error`,
  `test_game_start_sin_thread_en_body_falla_validacion`,
  `test_thread_generado_con_crear_thread_unico` y
  `test_threads_de_llamadas_distintas_son_distintos`.

Para ejecutarlos:

```bash
pytest tests/test_ontologia.py -v
```

Si algún test de behaviours o de integración del alumno estaba
verificando `len(ACCIONES_VALIDAS) == 9` o similares, debe
actualizarse a 10. Si verificaba la firma antigua de
`crear_cuerpo_game_start` o `crear_mensaje_join`, también.

---

## 6. Mapa resumen del ciclo de un turno

![Ciclo completo de un turno con turn-result](doc/svg/secuencia-ciclo-turno.svg)

El bloque nuevo respecto a versiones anteriores es el mensaje
`INFORM turn-result`. Todos los mensajes de la partida comparten el
mismo `thread` (el que el tablero generó con `crear_thread_unico` al
formar pareja y publicó en el cuerpo del `game-start`).

---

## 7. Checklist para el alumno

Antes de dar por terminada la actualización en su código:

### Tanda 2026-04-14 (turn-result)

- [ ] El Agente Tablero tiene un estado/behaviour que espera
      `turn-result` tras cada `ACCEPT_PROPOSAL` enviado.
- [ ] El Agente Tablero cierra la partida al recibir `result="win"` o
      `result="draw"` y no emite un nuevo `CFP turn`.
- [ ] El Agente Tablero emite `game-over` con `reason="timeout"` si
      expira la espera del `turn-result`.
- [ ] El Agente Jugador, cuando es activo, evalúa su tablero local
      tras aplicar el movimiento confirmado y emite `turn-result`
      con la performativa `inform`.
- [ ] El Agente Jugador usa `crear_cuerpo_turn_result` (nunca
      construye el JSON a mano).

### Tanda 2026-04-23 (thread único y `game-start`)

- [ ] Cualquier thread que el agente fije en un mensaje proviene de
      una llamada a `crear_thread_unico` con uno de los prefijos
      canónicos.
- [ ] El Agente Tablero genera un nuevo `thread_partida` al formar
      cada pareja (no una sola vez en `setup()`).
- [ ] El Agente Tablero construye `game-start` con
      `crear_cuerpo_game_start(oponente, thread_partida)` y fija el
      mismo valor en `msg.thread`.
- [ ] El Agente Jugador usa
      `crear_mensaje_join(jid_tablero, str(self.agent.jid))` (firma
      de dos argumentos) y no fija el thread a mano.
- [ ] El Agente Jugador, al recibir `game-start`, lee
      `body["thread"]` y registra su behaviour de partida con un
      `Template` que filtre por ese thread antes de devolver el
      control al bucle SPADE.

### Validación final

- [ ] Los tests de ontología pasan: `pytest tests/test_ontologia.py -v`
      devuelve **96 passed**.
- [ ] Los tests propios de behaviours cubren los escenarios
      descritos en § 4.3.

---

## 8. Referencias

- Paquete `ontologia/` del proyecto (contiene el esquema JSON
  generado, el mapa de campos por acción y el módulo `ontologia.py`
  con constructores, utilidades y validadores).
- `tests/test_ontologia.py` como ejemplo de uso correcto de los
  constructores y de las reglas cruzadas.
- [`doc/GUIA_THREAD_Y_GAME_START.md`](doc/GUIA_THREAD_Y_GAME_START.md)
  — guía didáctica completa de la tanda 2026-04-23, con diagramas
  SVG sobre la composición del thread único, el contrato del nuevo
  `game-start` y el modelo proactivo de registro del behaviour de
  partida por parte del jugador.
- [`doc/GUIA_TABLERO_TORNEO.md`](doc/GUIA_TABLERO_TORNEO.md) —
  metadatos por tipo de mensaje, protocolos de inscripción e informe
  al supervisor, y recomendaciones de interoperabilidad en torneo.
- Presentación «Ontología del Tic-Tac-Toe» (PLATEA) — diapositivas
  5, 8, 10, 12, 14 y 17 reflejan el contrato actualizado.
