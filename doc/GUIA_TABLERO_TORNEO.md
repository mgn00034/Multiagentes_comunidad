# Guia del tablero para el modo torneo

En el modo torneo, los agentes de **todos los alumnos** del
grupo juegan entre si en las mismas salas MUC. Para que esto
funcione, todos los tableros y jugadores deben seguir las
mismas convenciones de comunicacion y generar resultados
coherentes. Este documento describe los requisitos
**obligatorios** que la implementacion del tablero (y del
jugador) deben cumplir para garantizar la interoperabilidad.

Cubre dos aspectos criticos:

1. [**Enrutamiento de protocolos**](#enrutamiento) — como el
   tablero distingue los REQUEST de inscripcion de los de
   informe mediante el campo `conversation-id`.
2. [**Coherencia de resultados**](#coherencia) — que invariantes
   debe cumplir el informe `game-report` que el tablero envia
   al supervisor.

---

## <a id="enrutamiento"></a>1. Enrutamiento de protocolos REQUEST con `conversation-id`

### El problema

El tablero debe atender dos protocolos REQUEST que comparten la
misma performativa FIPA y la misma ontologia:

| Protocolo    | Iniciador  | Accion        | Performativa | Proposito                        |
|--------------|------------|---------------|--------------|----------------------------------|
| Inscripcion  | Jugador    | `join`        | `request`    | El jugador pide unirse a la mesa |
| Informe      | Supervisor | `game-report` | `request`    | El supervisor pide el resultado  |

Ambos llegan con la misma metadata:

```
ontology     = "tictactoe"
performative = "request"
```

Si el tablero registra un **unico** behaviour con template
`{ontology, performative}`, ambos tipos de REQUEST se entregan al
mismo behaviour. Cada alumno inventa su propia forma de
distinguirlos (parsear el body, inspeccionar el sender, etc.), y
las interacciones cruzadas en torneo se rompen.

### Requisito para torneo

Todos los agentes deben seguir la **misma** convencion de
enrutamiento:

1. **Declarativa**: basada en metadata, no en inspeccion del body.
2. **Resuelta por SPADE**: antes de que el behaviour ejecute
   `run()`.
3. **Un behaviour por protocolo**: responsabilidades separadas.
4. **Compatible con `thread`**: la correlacion de respuestas
   existente no cambia.

---

### La solucion: campo `conversation-id`

#### Fundamento FIPA-ACL

El estandar FIPA-ACL define el parametro `conversation-id` como
identificador de una secuencia de mensajes relacionados. En nuestro
sistema, cada accion que inicia un protocolo REQUEST establece un
`conversation-id` que identifica el **tipo de conversacion**. SPADE
enruta el mensaje al behaviour correcto mediante template matching,
antes de que se ejecute ninguna logica de negocio.

#### Valores definidos

| `conversation-id` | Quien lo establece | Cuando                          |
|--------------------|--------------------|---------------------------------|
| `"join"`           | Jugador            | Al enviar REQUEST de inscripcion |
| `"game-report"`    | Supervisor         | Al solicitar informe de partida  |

#### Enrutamiento en el tablero

![Diagrama de enrutamiento por conversation-id en el tablero](svg/enrutamiento-conversation-id.svg)

---

### Cambios obligatorios en el tablero del alumno

El tablero debe registrar **dos behaviours separados**, cada uno
con un template que incluya el `conversation-id` correspondiente.
La ontologia proporciona dos funciones que construyen las
plantillas con toda la metadata ya configurada:

```python
from ontologia.ontologia import (
    crear_plantilla_join,
    crear_plantilla_game_report,
)

async def setup(self):
    # ── Behaviour 1: inscripciones de jugadores ──────────
    self.add_behaviour(
        GestionarInscripcionBehaviour(),
        crear_plantilla_join(),
    )

    # ── Behaviour 2: informes para el supervisor ─────────
    self.add_behaviour(
        ResponderGameReportBehaviour(),
        crear_plantilla_game_report(),
    )
```

Cada funcion devuelve un `Template` SPADE con los tres campos
de metadata necesarios (`ontology`, `performative`,
`conversation-id`), garantizando que todos los tableros usen
exactamente los mismos valores. Esto evita errores por omision
o por valores incorrectos en la metadata.

Cada behaviour solo recibe los mensajes de **su** protocolo. No
hay ambiguedad y no es necesario parsear el body para distinguir
el tipo de REQUEST.

Si el alumno prefiere construir las plantillas manualmente (no
recomendado), debe incluir **todos** los campos de metadata:

```python
from spade.template import Template
from ontologia.ontologia import ONTOLOGIA

plantilla_join = Template()
plantilla_join.set_metadata("ontology", ONTOLOGIA)
plantilla_join.set_metadata("performative", "request")
plantilla_join.set_metadata("conversation-id", "join")

plantilla_report = Template()
plantilla_report.set_metadata("ontology", ONTOLOGIA)
plantilla_report.set_metadata("performative", "request")
plantilla_report.set_metadata("conversation-id", "game-report")
```

---

### Cambios obligatorios en el jugador del alumno

Al enviar el REQUEST de inscripcion, el jugador debe incluir
`conversation-id = "join"` en la metadata. La ontologia
proporciona la funcion `crear_mensaje_join()` que construye el
mensaje completo con toda la metadata ya configurada, incluido el
`thread` unico generado con `crear_thread_unico`:

```python
from ontologia.ontologia import crear_mensaje_join

mensaje = crear_mensaje_join(jid_tablero, str(self.agent.jid))
await self.send(mensaje)
```

Esta funcion configura automaticamente los cinco campos
necesarios (`ontology`, `performative`, `conversation-id`,
`thread` y `body`), evitando errores por omision de alguno de
ellos y garantizando que el thread sea globalmente unico.

Si el alumno prefiere construir el mensaje manualmente, debe
incluir **todos** los campos de metadata:

```python
from spade.message import Message
from ontologia.ontologia import (
    ONTOLOGIA, PREFIJO_THREAD_JOIN,
    crear_cuerpo_join, crear_thread_unico,
)

mensaje = Message(to=jid_tablero)
mensaje.set_metadata("ontology", ONTOLOGIA)
mensaje.set_metadata("performative", "request")
mensaje.set_metadata("conversation-id", "join")
mensaje.thread = crear_thread_unico(
    str(self.agent.jid), PREFIJO_THREAD_JOIN,
)
mensaje.body = crear_cuerpo_join()
await self.send(mensaje)
```

Sin el campo `conversation-id`, el tablero no enrutara el
mensaje al behaviour de inscripcion y el jugador no recibira
respuesta.

---

### Reglas para las respuestas

Las respuestas (AGREE, INFORM, REFUSE, FAILURE) **no necesitan**
`conversation-id`. La correlacion se realiza por `thread`:

- El **supervisor** crea un FSM con template `{thread, ontology}`.
- El **jugador** espera respuesta con template que incluya su
  `thread`.

**Regla**: toda respuesta debe copiar el `thread` del mensaje
original. El uso de `mensaje.make_reply()` lo garantiza
automaticamente:

```python
# En el behaviour del tablero, al responder:
respuesta = mensaje.make_reply()  # copia thread, sender -> to
respuesta.set_metadata("ontology", ONTOLOGIA)
respuesta.set_metadata("performative", "agree")
respuesta.body = crear_cuerpo_join_accepted("X")
await self.send(respuesta)
```

---

### Flujo completo de cada protocolo

#### Protocolo de inscripcion (jugador -> tablero)

![Diagrama de secuencia del protocolo de inscripcion](svg/protocolo-inscripcion-join.svg)

#### Protocolo de informe (supervisor -> tablero)

![Diagrama de secuencia del protocolo de informe game-report](svg/protocolo-game-report.svg)

---

### Resumen de metadata por tipo de mensaje

| Mensaje                | ontology    | performative     | conversation-id | thread               |
|------------------------|-------------|------------------|-----------------|----------------------|
| JOIN (request)         | tictactoe   | request          | **join**        | join-{jid}-{ts}      |
| JOIN-ACCEPTED (agree)  | tictactoe   | agree            | --              | (hereda del request) |
| JOIN-REFUSED (refuse)  | tictactoe   | refuse           | --              | (hereda del request) |
| GAME-REPORT (request)  | tictactoe   | request          | **game-report** | report-{jid}-{ts}    |
| GAME-REPORT (agree)    | tictactoe   | agree            | --              | (hereda del request) |
| GAME-REPORT (inform)   | tictactoe   | inform           | --              | (hereda del request) |
| GAME-REPORT (refuse)   | tictactoe   | refuse           | --              | (hereda del request) |
| GAME-START (inform)    | tictactoe   | inform           | --              | (propio, ver nota †) |
| TURN (cfp)             | tictactoe   | cfp              | --              | (propio)             |
| MOVE (propose)         | tictactoe   | propose          | --              | (propio)             |

> **† Nota (2026-04-23):** el thread de partida se genera en el tablero
> con `crear_thread_unico(str(self.agent.jid), PREFIJO_THREAD_GAME)` al
> formar pareja y **se replica dentro del cuerpo** del `GAME-START`
> (campo `thread`). Esto permite que el jugador construya el template
> de su behaviour de partida sin esperar al primer `CFP turn`. Detalles
> y diagramas en `doc/GUIA_THREAD_Y_GAME_START.md`.

Solo los mensajes que **inician** un protocolo REQUEST llevan
`conversation-id`. El resto se correlaciona por `thread`.

---

### Alternativas descartadas

**Behaviour unico con despacho por body:** descartada porque mezcla
responsabilidades de dos protocolos en un behaviour, un body
malformado colapsa ambos protocolos y no aprovecha el sistema de
templates de SPADE.

**Filtrado por prefijo de thread:** descartada porque SPADE no
soporta comodines en templates. El `thread` requiere coincidencia
exacta.

**Filtrado por sender:** descartada porque acopla el tablero a los
nombres de agentes externos. Fragil ante renombramientos y viola el
principio de comunicacion por protocolo, no por identidad.

---

### Tests de verificacion para el alumno

#### Objetivo

Una vez realizados los cambios en el tablero y en el jugador
descritos en las secciones anteriores, el alumno debe verificar
que su implementacion es correcta **antes** de probar con agentes
reales en el servidor XMPP. Para ello debe escribir tests
automatizados con `pytest` que trabajen con **datos simulados**
(mensajes y templates construidos en memoria), sin necesidad de
conexion XMPP ni de que ningun agente este arrancado.

#### Que se verifica y por que

Estos tests comprueban tres propiedades criticas para que el
torneo funcione:

1. **Enrutamiento correcto en el tablero**: que el template de
   cada behaviour acepta solo los mensajes de su protocolo y
   rechaza los del otro. Si esto falla, un REQUEST `join` podria
   llegar al behaviour de informe (o viceversa), causando errores
   silenciosos o respuestas inesperadas.

2. **Metadata correcta en el jugador**: que el REQUEST de
   inscripcion incluye todos los campos obligatorios
   (`ontology`, `performative`, `conversation-id`). Si falta
   alguno, el tablero de otro alumno no enrutara el mensaje y
   el jugador no recibira respuesta.

3. **Interoperabilidad en torneo**: que un mensaje enviado por
   el jugador de un alumno es aceptado por el template del
   tablero de otro alumno. Este es el escenario real del torneo,
   donde agentes de distintos alumnos interactuan entre si.

#### Donde colocar los tests

Los tests deben ir en el fichero de tests del agente
correspondiente, siguiendo la estructura del proyecto:

```
tests/
    test_tablero_aislado.py   <- tests del tablero (aqui van
                                 los de enrutamiento)
    test_jugador_aislado.py   <- tests del jugador (aqui van
                                 los de metadata)
```

#### Como ejecutarlos

```bash
# Ejecutar solo los tests de enrutamiento del tablero
pytest tests/test_tablero_aislado.py -v -k "conversation"

# Ejecutar solo los tests de metadata del jugador
pytest tests/test_jugador_aislado.py -v -k "conversation"

# Ejecutar todos los tests del proyecto
pytest tests/ -v
```

#### Utilidades comunes para los tests

La ontologia proporciona funciones para construir las plantillas
(`crear_plantilla_join`, `crear_plantilla_game_report`) y los
mensajes (`crear_mensaje_join`). Los tests deben usarlas
directamente en lugar de construir la metadata a mano.

Las siguientes funciones auxiliares complementan a las de la
ontologia para simular mensajes entrantes y comprobar la
coincidencia con templates. El alumno puede copiarlas
directamente en su fichero de tests o en un modulo
`tests/utilidades.py` compartido.

```python
import json
import pytest
from unittest.mock import MagicMock, AsyncMock
from spade.message import Message
from spade.template import Template
from ontologia.ontologia import (
    ONTOLOGIA,
    crear_mensaje_join,
    crear_plantilla_join,
    crear_plantilla_game_report,
)


def crear_mensaje_request(accion, conversation_id,
                          sender="agente@localhost",
                          thread="test-thread-001"):
    """Crea un mensaje REQUEST simulado con la metadata correcta.

    Args:
        accion: Valor del campo 'action' en el body JSON.
        conversation_id: Valor del campo conversation-id en
            la metadata SPADE.
        sender: JID del remitente simulado.
        thread: Identificador de hilo para correlacionar
            respuestas.

    Returns:
        Mensaje SPADE con metadata y body configurados.
    """
    msg = MagicMock()
    msg.sender = sender
    msg.thread = thread
    msg.body = json.dumps({"action": accion})

    # Simular get_metadata para que devuelva los valores
    # correctos segun la clave solicitada
    metadata = {
        "ontology": ONTOLOGIA,
        "performative": "request",
        "conversation-id": conversation_id,
    }
    msg.get_metadata = lambda clave: metadata.get(clave, "")

    # make_reply devuelve un mensaje con thread copiado
    respuesta = MagicMock()
    respuesta.thread = thread
    msg.make_reply = MagicMock(return_value=respuesta)

    return msg


def template_acepta_mensaje(plantilla, mensaje):
    """Verifica si un template SPADE aceptaria un mensaje dado.

    Compara cada campo del template con la metadata del mensaje.
    Devuelve True si todos los campos del template coinciden.

    Args:
        plantilla: Template SPADE con metadata definida.
        mensaje: Mensaje simulado con get_metadata().

    Returns:
        True si el template acepta el mensaje.
    """
    acepta = True
    i = 0
    campos = list(plantilla.metadata.items())
    while i < len(campos) and acepta:
        clave, valor = campos[i]
        if mensaje.get_metadata(clave) != valor:
            acepta = False
        i += 1
    return acepta
```

#### Tests del tablero

Estos tests van en `tests/test_tablero_aislado.py`. Verifican la
propiedad 1 (enrutamiento correcto): que cada template acepta
**solo** los mensajes de su protocolo. El alumno debe adaptar los
nombres de las clases de sus behaviours si son diferentes a los
del ejemplo, pero la logica de los templates y la metadata debe
ser identica.

**Que pasa si estos tests fallan:**
- Si `test_template_join_rechaza_request_game_report` falla, el
  supervisor entrara en el behaviour de inscripcion cuando solicite
  un informe, provocando un error o un REFUSE inesperado.
- Si `test_mensaje_sin_conversation_id_no_enruta` falla, mensajes
  de agentes que no han implementado la convencion se enrutaran
  de forma impredecible.

```python
class TestTableroEnrutamiento:
    """Verifica que el tablero enruta correctamente los REQUEST
    de inscripcion y de informe a behaviours separados mediante
    el campo conversation-id."""

    def test_template_join_acepta_request_join(self):
        """El template del behaviour de inscripcion debe aceptar
        un REQUEST con conversation-id='join'."""
        plantilla = crear_plantilla_join()
        msg = crear_mensaje_request("join", "join")
        assert template_acepta_mensaje(plantilla, msg)

    def test_template_join_rechaza_request_game_report(self):
        """El template del behaviour de inscripcion NO debe
        aceptar un REQUEST con conversation-id='game-report'.
        Si lo aceptara, el supervisor entraria en el behaviour
        de inscripcion en vez del de informe."""
        plantilla = crear_plantilla_join()
        msg = crear_mensaje_request("game-report", "game-report")
        assert not template_acepta_mensaje(plantilla, msg)

    def test_template_report_acepta_request_game_report(self):
        """El template del behaviour de informe debe aceptar
        un REQUEST con conversation-id='game-report'."""
        plantilla = crear_plantilla_game_report()
        msg = crear_mensaje_request("game-report", "game-report")
        assert template_acepta_mensaje(plantilla, msg)

    def test_template_report_rechaza_request_join(self):
        """El template del behaviour de informe NO debe aceptar
        un REQUEST con conversation-id='join'."""
        plantilla = crear_plantilla_game_report()
        msg = crear_mensaje_request("join", "join")
        assert not template_acepta_mensaje(plantilla, msg)

    def test_mensaje_sin_conversation_id_no_enruta(self):
        """Un REQUEST sin conversation-id no debe ser aceptado
        por ninguno de los dos templates. Esto detecta mensajes
        de agentes que no han implementado la convencion."""
        plantilla_join = crear_plantilla_join()
        plantilla_report = crear_plantilla_game_report()

        msg = crear_mensaje_request("join", "")
        assert not template_acepta_mensaje(plantilla_join, msg)
        assert not template_acepta_mensaje(plantilla_report, msg)

    def test_respuesta_copia_thread_del_request(self):
        """Al responder con make_reply(), el thread del mensaje
        original debe copiarse a la respuesta para que el
        iniciador pueda correlacionarla."""
        hilo_original = "join-jugador_ana-1713264000"
        msg = crear_mensaje_request(
            "join", "join", thread=hilo_original,
        )
        respuesta = msg.make_reply()
        assert respuesta.thread == hilo_original
```

#### Tests del jugador

Estos tests van en `tests/test_jugador_aislado.py`. Verifican la
propiedad 2 (metadata correcta): que el REQUEST de inscripcion
incluye todos los campos que el tablero necesita para enrutarlo.

**Nota:** si el alumno usa `crear_mensaje_join()` de la ontologia,
la metadata se configura automaticamente y estos tests pasan sin
necesidad de ajustes. Si construye el mensaje manualmente, estos
tests detectaran cualquier campo que falte.

**Que pasa si estos tests fallan:**
- Si `test_request_join_incluye_conversation_id` falla, el tablero
  de cualquier otro alumno descartara el mensaje porque no coincide
  con ningun template. El jugador no recibira respuesta y se
  quedara esperando indefinidamente.
- El ultimo test (`test_request_join_es_aceptado_por_template_tablero`)
  es el mas importante: simula la interaccion cruzada en torneo
  verificando que el mensaje del jugador seria aceptado por el
  template de un tablero ajeno.

```python
class TestJugadorMetadata:
    """Verifica que el jugador envia el REQUEST de inscripcion
    con la metadata correcta, incluyendo conversation-id.

    Si el alumno usa crear_mensaje_join() de la ontologia,
    estos tests pasan automaticamente. Si construye el mensaje
    manualmente, detectaran campos que falten."""

    def test_request_join_incluye_conversation_id(self):
        """El mensaje REQUEST del jugador debe incluir
        conversation-id='join' en la metadata."""
        msg = crear_mensaje_join(
            "tablero_mesa1@localhost", "jugador_01@localhost",
        )
        assert msg.get_metadata("conversation-id") == "join"

    def test_request_join_incluye_ontologia(self):
        """El REQUEST debe incluir la ontologia del sistema."""
        msg = crear_mensaje_join(
            "tablero_mesa1@localhost", "jugador_01@localhost",
        )
        assert msg.get_metadata("ontology") == ONTOLOGIA

    def test_request_join_incluye_performative(self):
        """El REQUEST debe declarar performative='request'."""
        msg = crear_mensaje_join(
            "tablero_mesa1@localhost", "jugador_01@localhost",
        )
        assert msg.get_metadata("performative") == "request"

    def test_request_join_body_contiene_action_join(self):
        """El body del REQUEST debe ser un JSON con
        action='join'."""
        msg = crear_mensaje_join(
            "tablero_mesa1@localhost", "jugador_01@localhost",
        )
        cuerpo = json.loads(msg.body)
        assert cuerpo["action"] == "join"

    def test_request_join_es_aceptado_por_template_tablero(self):
        """El REQUEST del jugador debe ser aceptado por el
        template de inscripcion del tablero. Este test simula
        la interaccion cruzada en torneo: el mensaje de un
        jugador de un alumno llega al tablero de otro alumno."""
        plantilla_tablero = crear_plantilla_join()

        msg = crear_mensaje_request(
            "join", "join",
            sender="jugador_otro_alumno@servidor.externo",
        )
        assert template_acepta_mensaje(plantilla_tablero, msg)
```

#### Escenario de integracion simulada

Este test puede ir en cualquiera de los dos ficheros de tests.
Verifica la propiedad 3 (interoperabilidad): simula el escenario
completo de torneo donde un jugador de un alumno se inscribe en
el tablero de otro alumno, y el supervisor del profesor solicita
el informe al mismo tablero. Ambos REQUEST deben enrutarse a
behaviours distintos sin interferencia.

**Este es el test definitivo.** Si pasa, el alumno tiene garantia
de que su implementacion funcionara en el torneo con agentes de
otros alumnos y con el supervisor del profesor. Si falla, debe
revisar los templates de su tablero o la metadata de su jugador.

```python
class TestEscenarioTorneo:
    """Simula el escenario de torneo donde el tablero recibe
    REQUEST de jugadores y del supervisor con conversation-id
    diferentes."""

    def test_torneo_enrutamiento_cruzado(self):
        """En un torneo, el tablero recibe:
        1. REQUEST join de un jugador (conversation-id='join')
        2. REQUEST game-report del supervisor
           (conversation-id='game-report')

        Cada mensaje debe ser aceptado por exactamente uno de
        los dos templates, no por ambos ni por ninguno."""
        plantilla_join = crear_plantilla_join()
        plantilla_report = crear_plantilla_game_report()

        # Mensaje del jugador de otro alumno
        msg_join = crear_mensaje_request(
            "join", "join",
            sender="jugador_ana@sinbad2.ujaen.es",
        )
        # Mensaje del supervisor del profesor
        msg_report = crear_mensaje_request(
            "game-report", "game-report",
            sender="supervisor@sinbad2.ujaen.es",
        )

        # El join va al behaviour de inscripcion, no al de
        # informe
        assert template_acepta_mensaje(plantilla_join, msg_join)
        assert not template_acepta_mensaje(
            plantilla_report, msg_join,
        )

        # El game-report va al behaviour de informe, no al
        # de inscripcion
        assert template_acepta_mensaje(
            plantilla_report, msg_report,
        )
        assert not template_acepta_mensaje(
            plantilla_join, msg_report,
        )
```

---

## <a id="coherencia"></a>2. Coherencia de resultados del `game-report`

Cuando una partida finaliza, el tablero construye un mensaje
INFORM `game-report` con los resultados y lo envia al supervisor.
El supervisor **valida la coherencia** de estos resultados
aplicando un conjunto de invariantes del Tic-Tac-Toe. Si alguna
invariante se viola, el supervisor registra una **incidencia** que
sera visible en el dashboard.

El alumno debe asegurarse de que su tablero genera informes
coherentes **antes** de participar en el torneo. Esta seccion
describe todas las invariantes que el supervisor comprueba, para
que el alumno pueda verificar que su implementacion las cumple.

### Campos del informe `game-report`

El informe se construye con la funcion `crear_cuerpo_game_report`
de la ontologia. Los campos relevantes para la validacion son:

| Campo    | Tipo           | Descripcion                                    | Valores validos                |
|----------|----------------|------------------------------------------------|--------------------------------|
| `result` | `str`          | Resultado de la partida                        | `"win"`, `"draw"`, `"aborted"` |
| `winner` | `str` o `None` | Simbolo del ganador                            | `"X"`, `"O"` o `None`         |
| `turns`  | `int`          | Numero de turnos jugados                       | 0-9                            |
| `board`  | `list[str]`    | Estado final del tablero (9 celdas)            | Cada celda: `""`, `"X"`, `"O"` |
| `players`| `dict`         | Mapa de simbolo a JID del jugador              | `{"X": jid_x, "O": jid_o}`   |

### Convencion del sistema

`"X"` **mueve primero**. El primer jugador inscrito recibe el
simbolo `"X"` y el segundo recibe `"O"`. Esto implica que `"X"`
siempre tiene **igual o mas fichas** que `"O"` en el tablero.

### Mapa completo de invariantes

La siguiente tabla muestra **todas** las invariantes que el
supervisor comprueba. El tablero del alumno debe generar
informes que las satisfagan.

#### Invariantes sobre turnos (V1-V3)

| #  | Invariante                          | Aplica a    | Regla                                          |
|----|-------------------------------------|-------------|-------------------------------------------------|
| V1 | Victoria con menos de 5 turnos      | `win`       | Una victoria necesita minimo 5 movimientos      |
| V2 | Mas de 9 turnos                     | todos       | El tablero tiene 9 celdas, maximo 9 turnos      |
| V3 | Empate con menos de 9 turnos        | `draw`      | Un empate legitimo requiere exactamente 9 turnos |

**Por que importa:** si el tablero reporta `result: "draw"` con
`turns: 7`, hay un error en la logica de finalizacion. Un empate
solo ocurre cuando el tablero esta completo (9 turnos) y ninguno
de los dos jugadores ha formado linea. De forma similar, una
victoria antes del turno 5 es imposible porque el primer jugador
necesita al menos 3 movimientos (turnos 1, 3, 5) para completar
una linea.

#### Invariantes sobre el tablero (V4-V6)

| #  | Invariante                          | Aplica a    | Regla                                          |
|----|-------------------------------------|-------------|-------------------------------------------------|
| V4 | Celdas vacias en empate             | `draw`      | Un empate tiene 0 celdas vacias                 |
| V5 | Linea ganadora ausente en victoria  | `win`       | El tablero debe contener la linea del ganador   |
| V6 | Linea ganadora oculta en empate     | `draw`      | Un empate no puede tener una linea completa     |

**Por que importa:** V4 complementa a V3 — incluso si `turns`
es 9, el tablero podria tener celdas vacias por un error al
registrar los movimientos. V5 verifica que el resultado `"win"`
es consistente con el estado del tablero (existe una fila,
columna o diagonal completa del simbolo ganador). V6 detecta
el caso contrario: si hay linea ganadora, el resultado no puede
ser empate.

#### Invariantes sobre el equilibrio de fichas (V8-V11)

| #   | Invariante                           | Aplica a       | Regla                                         |
|-----|--------------------------------------|----------------|-----------------------------------------------|
| V8  | Equilibrio de fichas en empate       | `draw`         | `abs(num_x - num_o) <= 1`                     |
| V9  | `turns` coherente con fichas         | `win`, `draw`  | `num_x + num_o == turns`                      |
| V10 | Equilibrio de fichas en victoria     | `win`          | `abs(num_x - num_o) <= 1`                     |
| V11 | Convencion X-primero                 | `win`, `draw`  | `num_x >= num_o` siempre                      |

**Por que importa:** estas invariantes detectan errores en la
alternancia de turnos del tablero del alumno.

- **V8/V10 — Equilibrio de fichas:** en Tic-Tac-Toe con `"X"`
  moviendo primero, tras 9 turnos hay exactamente 5 `"X"` y
  4 `"O"` (diferencia de 1). Tras un numero par de turnos,
  ambos tienen el mismo numero de fichas (diferencia de 0). Si
  `abs(num_x - num_o) > 1`, el tablero no esta alternando los
  turnos correctamente.

- **V9 — Turnos vs fichas:** el campo `turns` debe coincidir con
  el numero total de fichas en el `board`. Si `turns: 5` pero el
  tablero tiene 7 fichas, hay una incoherencia entre el contador
  de turnos y el registro de movimientos.

- **V11 — Convencion X-primero:** como `"X"` mueve primero,
  siempre tiene **igual o mas** fichas que `"O"`. Si `num_x <
  num_o`, el tablero esta invirtiendo el orden de movimiento (O
  movio primero en lugar de X). Esto viola la convencion del
  sistema. Ejemplo: un empate con 4X+5O cumple V8
  (`abs(4-5) = 1`), pero viola V11 porque la distribucion
  correcta es 5X+4O.

#### Invariante sobre jugadores (V7)

| #  | Invariante                          | Aplica a    | Regla                                          |
|----|-------------------------------------|-------------|-------------------------------------------------|
| V7 | Ambos jugadores son el mismo agente | todos       | `players["X"] != players["O"]`                  |

**Por que importa:** un tablero no debe permitir que un jugador
se inscriba dos veces y juegue contra si mismo.

#### Nota sobre partidas abortadas

Las validaciones V8, V9, V10 y V11 **no aplican** a partidas
abortadas (`result: "aborted"`). Una partida abortada puede
terminar con cualquier numero de turnos (incluso 0) y el estado
del tablero puede ser inconsistente si la partida se interrumpio
antes de completarse.

### Tabla de verificacion completa

La siguiente tabla muestra ejemplos de escenarios y que
invariantes los detectan como incorrectos. Los casos marcados
como **Correcto** son escenarios validos que no deben generar
incidencias.

| Caso                               | Invariantes que lo detectan       | Veredicto  |
|--------------------------------------|-----------------------------------|------------|
| `draw`, 9t, 5X+4O, sin linea        | —                                 | **Correcto** |
| `draw`, 7t, 4X+3O                   | V3, V4                            | Detectado  |
| `draw`, 9t, 3X+6O                   | V8, V11                           | Detectado  |
| `draw`, 9t, 4X+5O                   | V11                               | Detectado  |
| `draw`, 9t, 2 vacias                | V4, V9                            | Detectado  |
| `win`, 5t, 3X+2O, linea X           | —                                 | **Correcto** |
| `win`, 3t                            | V1                                | Detectado  |
| `win`, 7t, 1X+6O                    | V10, V11                          | Detectado  |
| `win`, 7t, 3X+4O                    | V11                               | Detectado  |
| `win`, 5t, board con 3 fichas       | V9                                | Detectado  |
| `aborted`, 4t                        | —                                 | **Correcto** |

### Distribucion esperada de fichas por numero de turnos

Como referencia, la distribucion correcta de fichas en funcion
del numero de turnos (asumiendo que `"X"` mueve primero):

| Turnos | Fichas X | Fichas O | Diferencia | Paridad  |
|--------|----------|----------|------------|----------|
| 5      | 3        | 2        | 1          | impar    |
| 6      | 3        | 3        | 0          | par      |
| 7      | 4        | 3        | 1          | impar    |
| 8      | 4        | 4        | 0          | par      |
| 9      | 5        | 4        | 1          | impar    |

**Regla general:**
- `turns` impar: `num_x = (turns + 1) / 2`,
  `num_o = (turns - 1) / 2`. Diferencia = 1.
- `turns` par: `num_x = num_o = turns / 2`. Diferencia = 0.

---

### Que debe verificar el alumno

El alumno debe comprobar que su tablero genera informes
`game-report` que satisfacen **todas** las invariantes anteriores.
A continuacion se detalla que debe verificar para cada aspecto,
organizado como lista de comprobacion.

#### Logica de finalizacion de partida

- [ ] Cuando la partida termina en empate, `turns` es
      exactamente 9.
- [ ] Cuando la partida termina en victoria, `turns` es mayor
      o igual a 5 y menor o igual a 9.
- [ ] El tablero nunca reporta mas de 9 turnos.

#### Estado del tablero (`board`)

- [ ] En un empate, el `board` no contiene celdas vacias (todas
      las 9 posiciones estan ocupadas por `"X"` o `"O"`).
- [ ] En una victoria, el `board` contiene al menos una linea
      completa (fila, columna o diagonal) del simbolo ganador.
- [ ] En un empate, el `board` **no** contiene ninguna linea
      completa de un mismo simbolo.
- [ ] El numero total de fichas en el `board`
      (`count("X") + count("O")`) coincide con el valor de
      `turns`.

#### Alternancia de turnos y convencion X-primero

- [ ] La diferencia entre fichas X y O en el `board` nunca
      supera 1: `abs(count("X") - count("O")) <= 1`.
- [ ] El numero de fichas X es siempre mayor o igual al de
      fichas O: `count("X") >= count("O")`. Esto garantiza que
      `"X"` mueve primero, como establece la convencion.
- [ ] Si `turns` es impar, hay exactamente una ficha X mas que
      fichas O.
- [ ] Si `turns` es par, hay exactamente el mismo numero de
      fichas X y O.

#### Campo `winner`

- [ ] Si `result` es `"win"`, `winner` es `"X"` o `"O"` (no
      `None`).
- [ ] Si `result` es `"draw"` o `"aborted"`, `winner` es `None`.
- [ ] El simbolo en `winner` coincide con el de la linea
      ganadora encontrada en el `board`.

#### Campo `players`

- [ ] El mapa `players` contiene exactamente dos entradas:
      `"X"` y `"O"`.
- [ ] Los JIDs de `players["X"]` y `players["O"]` son
      **distintos** (un jugador no puede jugar contra si mismo).
- [ ] Los JIDs corresponden a los jugadores que realmente se
      inscribieron en la mesa.

#### Partidas abortadas

- [ ] El resultado `"aborted"` solo se usa cuando la partida no
      pudo completarse (jugador desconectado, timeout, etc.).
- [ ] En partidas abortadas, el tablero no aplica las
      validaciones de equilibrio de fichas ni de X-primero
      (el estado puede ser inconsistente).

---

### Recomendacion sobre tests

El alumno debe escribir tests automatizados con `pytest` que
verifiquen las invariantes anteriores construyendo informes
`game-report` simulados y comprobando que los campos son
coherentes entre si. Estos tests deben ir en
`tests/test_tablero_aislado.py` y trabajar con datos en memoria,
sin necesidad de conexion XMPP.

A diferencia de la seccion de `conversation-id` (donde se
proporcionan los tests completos porque la convencion de
enrutamiento debe ser identica para todos), los tests de
coherencia de resultados son **responsabilidad del alumno**. Cada
alumno tiene su propia logica de partida y debe disenar los
escenarios de prueba que cubran los casos de su implementacion
(victorias en distintos turnos, empates, partidas abortadas,
distribuciones de fichas correctas e incorrectas).

**Orientacion para los tests:**

1. Construir un informe `game-report` valido (resultado correcto,
   turnos correctos, tablero coherente, fichas equilibradas) y
   verificar que pasa todas las invariantes.
2. Construir informes con **una sola invariante violada** cada vez
   y verificar que se detecta el error. Ejemplo: un empate con
   `turns: 7`, una victoria con `turns: 3`, un empate con
   4X+5O, etc.
3. Verificar los escenarios de la tabla de verificacion completa
   (seccion anterior) como referencia.
