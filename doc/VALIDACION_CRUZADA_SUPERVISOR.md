# Validación cruzada de informes — Agente Supervisor

**Proyecto:** Tic-Tac-Toe Multiagente

**Asignatura:** Sistemas Multiagente — Universidad de Jaén

**Fecha:** 2026-04-12 (creacion) · 2026-04-17 (ultima revision)

**Ramas:**
- `feature/agente-supervisor` — Supervisor completo + piezas para alumnos
- `feature/informe-alumno` — Solo piezas para alumnos (desde `main`)

**Referencia:** Diapositiva 13 de la Guía de Proyectos Multiagente —
*README, Configuración y Ejecución de Pruebas*, protocolo de la
Batería 3 (día del examen).

---

## Índice

1. [Contexto y motivación](#1-contexto-y-motivación)
2. [Análisis del estado actual](#2-análisis-del-estado-actual)
   - 2.1 [Capacidades existentes](#21-capacidades-existentes)
   - 2.2 [Carencias identificadas](#22-carencias-identificadas)
3. [Piezas a desarrollar](#3-piezas-a-desarrollar)
   - 3.1 [V-01 — Esquema JSON del informe del alumno](#31-v-01--esquema-json-del-informe-del-alumno)
   - 3.2 [V-02 — Endpoint de informe de referencia del profesor](#32-v-02--endpoint-de-informe-de-referencia-del-profesor)
   - 3.3 [V-03 — Validador cruzado](#33-v-03--validador-cruzado)
   - 3.4 [V-04 — Endpoint de verificación de presencia (F2)](#34-v-04--endpoint-de-verificación-de-presencia-f2)
   - 3.5 [V-05 — Fichero test_config.json base](#35-v-05--fichero-test_configjson-base)
   - 3.6 [V-06 — Informe HTML consolidado de evaluación](#36-v-06--informe-html-consolidado-de-evaluación)
4. [Protocolo del día del examen desde el supervisor](#4-protocolo-del-día-del-examen-desde-el-supervisor)
5. [Matriz de trazabilidad con las fases de la diapositiva 13](#5-matriz-de-trazabilidad-con-las-fases-de-la-diapositiva-13)
6. [Estado de implementación](#6-estado-de-implementación)
7. [Comprobaciones manuales del profesor](#7-comprobaciones-manuales-del-profesor)

---

## 1. Contexto y motivación

La diapositiva 13 de la Guía de Proyectos Multiagente describe un
protocolo de cinco fases para la prueba colectiva inter-equipos
(Batería 3) que se ejecuta presencialmente el día del examen:

| Fase | Nombre | Duración | Descripción |
|------|--------|----------|-------------|
| F1 | Despliegue | 10 min | Cada alumno arranca sus agentes en el servidor compartido |
| F2 | Verificación de presencia | 5 min | El profesor verifica que todos los agentes están activos |
| F3 | Ejecución de pruebas | 20 min | Todos ejecutan simultáneamente; las partidas se desarrollan |
| F4 | Generación de informes | 10 min | Cada alumno genera su informe de integración |
| F5 | Verificación del profesor | — | El profesor ejecuta sus propias pruebas y **cruza los informes** |

El punto clave es la **coherencia cruzada** de la fase F5:

> *"El profesor cruza los informes de los diferentes equipos: si el
> Grupo A afirma haber completado un protocolo de coordinación con el
> Grupo B, el informe del Grupo B debería reflejar la misma
> interacción desde su perspectiva. Esta coherencia cruzada entre
> informes es un criterio de evaluación clave."*

Adaptado al contexto del TicTacToe, esto implica:

- El **supervisor** observa todas las partidas desde las salas MUC
  y recopila los `game-report` de los tableros. Es la **verdad
  fundamental** (ground truth).
- Cada **alumno** genera un informe con lo que observaron sus agentes
  (tablero y jugadores) durante la sesión.
- El profesor necesita **contrastar** cada informe de alumno con los
  datos del supervisor: mismos resultados, mismos jugadores, mismos
  tableros finales, mismas incidencias.

El agente supervisor ya cubre buena parte de F1/F3/F4, pero carece
de las herramientas específicas para F2 (verificación de presencia
con checklist) y F5 (validación cruzada).

---

## 2. Análisis del estado actual

### 2.1 Capacidades existentes

| Fase | Capacidad del supervisor | Fichero |
|------|------------------------|---------|
| F1 | `supervisor_main.py --modo laboratorio` se une a 30 salas (una por puesto L2PC01–L2PC30) | `supervisor_main.py` |
| F1 | Descubrimiento manual de salas desde `salas_laboratorio.yaml` | `config/salas_laboratorio.yaml` |
| F3 | Detección reactiva de tableros finalizados (callback presencia MUC) | `agentes/agente_supervisor.py` |
| F3 | Protocolo FIPA-Request completo con FSM (solicita `game-report`) | `behaviours/supervisor_behaviours.py` |
| F3 | Validación de esquema y validación semántica cruzada (7 validaciones) | `behaviours/supervisor_behaviours.py` |
| F3 | Reintentos con retroceso exponencial (2 reintentos, factor ×2) | `behaviours/supervisor_behaviours.py` |
| F4 | Exportación CSV: ranking, log, incidencias (en vivo e histórica) | `web/supervisor_handlers.py` |
| F4 | Persistencia SQLite (ejecuciones, informes, eventos) | `persistencia/almacen_supervisor.py` |
| F4 | Dashboard web con SSE, 5 pestañas, selector de ejecuciones | `web/` |
| F5 | Modo consulta para revisar ejecuciones pasadas | `supervisor_main.py --modo consulta` |

### 2.2 Carencias identificadas

| ID | Carencia | Fase afectada | Impacto |
|----|----------|---------------|---------|
| **C-01** | No existe checklist de agentes esperados por sala | F2 | El profesor no puede verificar de un vistazo si faltan agentes |
| **C-02** | No existe endpoint ni vista de verificación de presencia | F2 | No hay pantalla proyectable para mostrar estado rojo/verde por puesto |
| **C-03** | ~~No se define el formato del informe que debe entregar el alumno~~ | F4 | Resuelta en V-01. Esquema JSON en `ontologia/esquema_informe_alumno.json` |
| **C-04** | No existe informe de referencia exportable del profesor (ground truth) | F5 | El profesor solo tiene CSVs parciales, no un documento de referencia completo |
| **C-05** | No existe validador cruzado (informe alumno vs. supervisor) | F5 | La coherencia cruzada debe hacerse manualmente, inviable con 30 alumnos |
| **C-06** | No existe informe consolidado de evaluación | F5 | No hay documento final que resuma las discrepancias de todos los alumnos |
| **C-07** | ~~No existe `test_config.json` en el proyecto~~ | F1–F4 | Resuelta en V-05. Plantilla en `test_config.json` (raíz del proyecto) |

---

## 3. Piezas a desarrollar

### 3.1 V-01 — Esquema JSON del informe del alumno ✅

**Prioridad:** Alta
**Fichero:** `ontologia/esquema_informe_alumno.json`
**Carencias que resuelve:** C-03
**Estado:** Implementado. Rama `feature/informe-alumno` (para alumnos)
y `feature/agente-supervisor`. Incluye validador de 4 niveles en
`validacion/informe_alumno.py`, constructores (`crear_informe_alumno`,
`crear_partida_observada`, `serializar_informe_alumno`), 36 tests en
`tests/test_informe_alumno.py` y guía de integración para alumnos en
`doc/GUIA_INFORME_ALUMNO.md`.

#### Motivación

Para poder cruzar informes automáticamente, todos los alumnos deben
entregar su informe en un formato estructurado y validable. Se define
un esquema JSON Schema que especifica exactamente qué campos se
esperan.

#### Esquema propuesto

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "informe-alumno-tictactoe",
  "title": "Informe de integración del alumno — TicTacToe",
  "description": "Informe que cada alumno genera tras la prueba colectiva (Batería 3). Recoge lo que observaron sus agentes durante la sesión.",
  "type": "object",
  "required": ["equipo", "puesto", "timestamp_inicio", "timestamp_fin", "partidas_observadas"],
  "additionalProperties": false,
  "properties": {
    "equipo": {
      "type": "string",
      "description": "Identificador del equipo o nombre del alumno (ej: 'grupo_03', 'ana_garcia')."
    },
    "puesto": {
      "type": "string",
      "pattern": "^pc[0-9]{2}$",
      "description": "Identificador del puesto del laboratorio (ej: 'pc05'). Debe coincidir con la sala MUC asignada."
    },
    "timestamp_inicio": {
      "type": "string",
      "format": "date-time",
      "description": "Marca temporal ISO 8601 del inicio de la sesión de pruebas del alumno."
    },
    "timestamp_fin": {
      "type": "string",
      "format": "date-time",
      "description": "Marca temporal ISO 8601 del fin de la sesión de pruebas del alumno."
    },
    "agentes_desplegados": {
      "type": "array",
      "description": "Lista de agentes que el alumno desplegó en el servidor.",
      "items": {
        "type": "object",
        "required": ["jid", "rol"],
        "properties": {
          "jid": {
            "type": "string",
            "description": "JID completo del agente (ej: 'tablero_pc05@sinbad2.ujaen.es')."
          },
          "rol": {
            "type": "string",
            "enum": ["tablero", "jugador"],
            "description": "Rol del agente en el sistema."
          }
        }
      }
    },
    "partidas_observadas": {
      "type": "array",
      "description": "Lista de partidas que el alumno observó desde sus agentes.",
      "items": {
        "type": "object",
        "required": ["tablero_jid", "resultado", "jugadores", "turnos", "tablero_final"],
        "properties": {
          "tablero_jid": {
            "type": "string",
            "description": "JID del tablero que arbitró la partida."
          },
          "resultado": {
            "type": "string",
            "enum": ["win", "draw", "aborted"],
            "description": "Resultado de la partida según la ontología."
          },
          "ganador_ficha": {
            "type": ["string", "null"],
            "enum": ["X", "O", null],
            "description": "Ficha ganadora (solo si resultado='win')."
          },
          "jugadores": {
            "type": "object",
            "required": ["X", "O"],
            "properties": {
              "X": { "type": "string", "description": "JID del jugador con ficha X." },
              "O": { "type": "string", "description": "JID del jugador con ficha O." }
            }
          },
          "turnos": {
            "type": "integer",
            "minimum": 0,
            "maximum": 9,
            "description": "Número de turnos de la partida."
          },
          "tablero_final": {
            "type": "array",
            "items": { "type": "string", "enum": ["X", "O", ""] },
            "minItems": 9,
            "maxItems": 9,
            "description": "Estado final del tablero (9 celdas, fila a fila)."
          },
          "timestamp": {
            "type": "string",
            "description": "Hora a la que el agente observó el fin de la partida (HH:MM:SS)."
          }
        }
      }
    },
    "incidencias": {
      "type": "array",
      "description": "Incidencias observadas por los agentes del alumno durante la sesión.",
      "items": {
        "type": "object",
        "required": ["tipo", "detalle"],
        "properties": {
          "tipo": {
            "type": "string",
            "enum": ["timeout", "error", "rechazo", "desconexion", "otro"],
            "description": "Categoría de la incidencia."
          },
          "detalle": {
            "type": "string",
            "description": "Descripción legible de la incidencia."
          },
          "timestamp": {
            "type": "string",
            "description": "Hora de la incidencia (HH:MM:SS)."
          }
        }
      }
    }
  }
}
```

#### Generación automática del informe por parte del alumno

Los alumnos deben incluir en su `test_colectiva.py` un fixture o
bloque `teardown` que genere el fichero `informe_integracion.json`
automáticamente al finalizar las pruebas. El informe se construye
a partir de los datos que los agentes del alumno acumularon durante
la sesión. Ejemplo de fixture:

```python
@pytest.fixture(scope="session", autouse=True)
def generar_informe_json(request):
    """Genera informe_integracion.json al finalizar la sesión."""
    yield
    # Al terminar todos los tests, volcar los datos observados
    datos = request.config._informe_datos  # acumulados durante los tests
    with open("informe_integracion.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
```

---

### 3.2 V-02 — Endpoint de informe de referencia del profesor

**Prioridad:** Alta
**Fichero destino:** `web/supervisor_handlers.py` (nuevo endpoint)
**Carencias que resuelve:** C-04

#### Motivación

El profesor necesita exportar un JSON completo con todo lo que el
supervisor observó durante la sesión. Este JSON sirve como **verdad
fundamental** para la validación cruzada.

#### Endpoint

```
GET /supervisor/api/informe-referencia
GET /supervisor/api/ejecuciones/{id}/informe-referencia
```

#### Estructura del informe de referencia

```json
{
  "meta": {
    "generado_por": "supervisor",
    "version": "1.0",
    "ejecucion_id": 42,
    "timestamp_inicio": "2026-04-15T10:00:00",
    "timestamp_fin": "2026-04-15T10:45:00",
    "timestamp_generacion": "2026-04-15T11:00:00"
  },
  "salas": {
    "sala_pc05": {
      "agentes_observados": [
        {
          "nick": "tablero_pc05",
          "jid": "tablero_pc05@sinbad2.ujaen.es",
          "rol": "tablero",
          "primera_presencia": "10:12:33",
          "ultima_presencia": "10:42:10",
          "estados_observados": ["available", "playing", "finished"]
        },
        {
          "nick": "jugador_ana",
          "jid": "jugador_ana@sinbad2.ujaen.es",
          "rol": "jugador",
          "primera_presencia": "10:13:01",
          "ultima_presencia": "10:41:55",
          "estados_observados": ["available"]
        }
      ],
      "partidas": [
        {
          "tablero_jid": "tablero_pc05@sinbad2.ujaen.es",
          "resultado": "win",
          "ganador_ficha": "X",
          "jugadores": {
            "X": "jugador_ana@sinbad2.ujaen.es",
            "O": "jugador_luis@sinbad2.ujaen.es"
          },
          "turnos": 7,
          "tablero_final": ["X","O","X","","X","O","O","X",""],
          "timestamp_recepcion": "10:25:33",
          "validacion_semantica": {
            "estado": "ok",
            "anomalias": []
          }
        }
      ],
      "incidencias": [
        {
          "tipo": "timeout",
          "de": "tablero_pc05",
          "detalle": "Sin respuesta tras 10 s (intento 1/3)",
          "timestamp": "10:24:20"
        }
      ],
      "resumen": {
        "total_partidas": 1,
        "victorias": 1,
        "empates": 0,
        "abortadas": 0,
        "incidencias": 1
      }
    }
  }
}
```

#### Detalles de implementación

- Función `_construir_informe_referencia(agente, id_ejecucion=None)`.
- Para el estado en vivo: lee `informes_por_sala`, `log_por_sala`,
  `ocupantes_por_sala` del agente.
- Para ejecuciones pasadas: lee las tablas `informes` y `eventos`
  del almacén SQLite.
- El informe de referencia incorpora los resultados de la validación
  semántica que ya se ejecutó en tiempo real (campo
  `validacion_semantica` de cada partida).
- Descarga como fichero JSON con `Content-Disposition: attachment`.

---

### 3.3 V-03 — Validador cruzado

**Prioridad:** Alta
**Fichero destino:** `validacion/validar_informes.py`
**Carencias que resuelve:** C-05

#### Motivación

Pieza central de la fase F5. Recibe el informe de referencia del
profesor y uno o más informes de alumnos, y genera un resultado de
validación por cada alumno.

#### Interfaz de uso

```bash
# Validar un informe individual
python -m validacion.validar_informes \
    --referencia informe_referencia.json \
    --alumno informes/grupo_03.json

# Validar todos los informes de un directorio
python -m validacion.validar_informes \
    --referencia informe_referencia.json \
    --directorio informes/

# Generar informe HTML consolidado
python -m validacion.validar_informes \
    --referencia informe_referencia.json \
    --directorio informes/ \
    --html evaluacion.html
```

#### Algoritmo de validación

Para cada informe de alumno se ejecutan las siguientes comprobaciones:

**Nivel 1 — Validación de esquema**

| Comprobación | Detalle |
|-------------|---------|
| Esquema JSON | El informe cumple `esquema_informe_alumno.json` |
| Puesto válido | El campo `puesto` corresponde a una sala monitorizada |
| Timestamps | `timestamp_inicio` < `timestamp_fin`, ambos dentro del rango de la ejecución |

**Nivel 2 — Cobertura de partidas**

| Comprobación | Detalle |
|-------------|---------|
| Partidas declaradas vs. observadas | Cada partida del informe del alumno se busca en el informe de referencia (misma sala, mismo tablero JID) |
| Partidas no reportadas | Partidas que el supervisor observó pero el alumno no declaró |
| Partidas inventadas | Partidas que el alumno declara pero el supervisor no observó |

**Nivel 3 — Coherencia de datos por partida**

Para cada partida que exista en ambos informes:

| Campo | Comprobación |
|-------|-------------|
| `resultado` | Mismo valor (`win`, `draw`, `aborted`) |
| `ganador_ficha` | Misma ficha ganadora (si `resultado=win`) |
| `jugadores.X` | Mismo JID del jugador X |
| `jugadores.O` | Mismo JID del jugador O |
| `turnos` | Mismo número de turnos |
| `tablero_final` | Las 9 celdas coinciden |

**Nivel 4 — Coherencia de incidencias**

| Comprobación | Detalle |
|-------------|---------|
| Incidencias del supervisor no reportadas | Timeouts, errores o anomalías que el supervisor detectó pero el alumno omite |
| Incidencias del alumno no observadas | Incidencias que el alumno reporta pero el supervisor no registró |

#### Estructura del resultado de validación

```json
{
  "alumno": {
    "equipo": "grupo_03",
    "puesto": "pc05"
  },
  "resumen": {
    "estado": "con_discrepancias",
    "puntuacion": 85,
    "partidas_declaradas": 3,
    "partidas_verificadas": 3,
    "partidas_no_reportadas": 0,
    "partidas_inventadas": 0,
    "campos_coincidentes": 17,
    "campos_discrepantes": 1,
    "incidencias_omitidas": 1
  },
  "validacion_esquema": {
    "valido": true,
    "errores": []
  },
  "partidas": [
    {
      "tablero_jid": "tablero_pc05@sinbad2.ujaen.es",
      "estado": "verificada",
      "discrepancias": [
        {
          "campo": "turnos",
          "valor_alumno": 6,
          "valor_supervisor": 7,
          "severidad": "alta"
        }
      ]
    }
  ],
  "partidas_no_reportadas": [],
  "partidas_inventadas": [],
  "incidencias_omitidas": [
    {
      "tipo": "timeout",
      "detalle": "Sin respuesta tras 10 s (intento 1/3)",
      "timestamp": "10:24:20"
    }
  ]
}
```

#### Cálculo de la puntuación

La puntuación (0–100) se calcula como indicador orientativo, no como
nota final. Sirve para que el profesor identifique rápidamente los
informes con más discrepancias.

```
puntuacion = 100
  - 20 × nº partidas inventadas
  - 10 × nº partidas no reportadas
  -  5 × nº campos discrepantes (severidad alta)
  -  2 × nº campos discrepantes (severidad baja)
  -  1 × nº incidencias omitidas
```

La puntuación se satura en 0 (no puede ser negativa).

#### Severidad de las discrepancias

| Severidad | Campos |
|-----------|--------|
| Alta | `resultado`, `ganador_ficha`, `jugadores.X`, `jugadores.O` |
| Baja | `turnos`, `tablero_final` |

Un resultado distinto (`win` vs. `draw`) indica un problema grave
(posible fabricación). Un número de turnos distinto puede deberse
a un error de conteo en el agente del alumno (defecto menor).

---

### 3.4 V-04 — Endpoint de verificación de presencia (F2)

**Prioridad:** Media
**Fichero destino:** `web/supervisor_handlers.py` (nuevo endpoint) +
`config/agentes_esperados.yaml` (nuevo fichero)
**Carencias que resuelve:** C-01, C-02

#### Motivación

Durante F2 (5 minutos) el profesor necesita proyectar en pantalla
el estado de presencia de todos los agentes esperados, con indicación
clara de quién falta.

#### Fichero de agentes esperados

```yaml
# config/agentes_esperados.yaml
# Lista de agentes que deben estar presentes en cada sala
# para la prueba colectiva del día del examen.

salas:
  sala_pc01:
    agentes:
      - nick: tablero_pc01
        rol: tablero
      - nick: jugador_pc01_x
        rol: jugador
      - nick: jugador_pc01_o
        rol: jugador

  sala_pc02:
    agentes:
      - nick: tablero_pc02
        rol: tablero
      - nick: jugador_pc02_x
        rol: jugador
      - nick: jugador_pc02_o
        rol: jugador
  # ... (una entrada por puesto)
```

Este fichero se rellena antes del examen con los nicks reales que
cada alumno haya comunicado en la entrega.

#### Endpoint

```
GET /supervisor/api/verificacion
```

#### Estructura de la respuesta

```json
{
  "timestamp": "10:08:15",
  "total_esperados": 90,
  "total_presentes": 84,
  "total_ausentes": 6,
  "porcentaje": 93.3,
  "salas": [
    {
      "id": "sala_pc05",
      "estado": "completa",
      "esperados": 3,
      "presentes": 3,
      "ausentes": 0,
      "agentes": [
        { "nick": "tablero_pc05", "rol": "tablero", "presente": true },
        { "nick": "jugador_pc05_x", "rol": "jugador", "presente": true },
        { "nick": "jugador_pc05_o", "rol": "jugador", "presente": true }
      ]
    },
    {
      "id": "sala_pc12",
      "estado": "incompleta",
      "esperados": 3,
      "presentes": 1,
      "ausentes": 2,
      "agentes": [
        { "nick": "tablero_pc12", "rol": "tablero", "presente": true },
        { "nick": "jugador_pc12_x", "rol": "jugador", "presente": false },
        { "nick": "jugador_pc12_o", "rol": "jugador", "presente": false }
      ]
    }
  ]
}
```

#### Vista en el dashboard

Nueva pestaña o modal **"Verificación F2"** en el panel web:

- Cuadrícula de 30 celdas (una por puesto), estilo semáforo.
- **Verde:** todos los agentes presentes.
- **Amarillo:** presencia parcial (ej: tablero sí, un jugador no).
- **Rojo:** ningún agente presente.
- Contador global: "84/90 agentes presentes (93 %)".
- Actualización en tiempo real via SSE.
- Pantalla diseñada para ser proyectable en el laboratorio.

---

### 3.5 V-05 — Fichero test_config.json base ✅

**Prioridad:** Media
**Fichero:** `test_config.json` (raíz del proyecto)
**Carencias que resuelve:** C-07
**Estado:** Implementado. Rama `feature/informe-alumno` (para alumnos)
y `feature/agente-supervisor`. Incluye secciones `servidores` (local
y servidor), `agentes_individuales`, `agentes_grupo` y
`prueba_colectiva` con la estructura de la diapositiva 13.

#### Motivación

La diapositiva 13 define un fichero `test_config.json` que centraliza
la configuración de las pruebas. Los alumnos necesitan una plantilla
adaptada al TicTacToe.

#### Contenido propuesto

```json
{
  "entorno": "local",

  "servidores": {
    "local": {
      "xmpp_host": "localhost",
      "xmpp_port": 5222,
      "servicio_muc": "conference.localhost",
      "password_defecto": "secret"
    },
    "servidor": {
      "xmpp_host": "sinbad2.ujaen.es",
      "xmpp_port": 8022,
      "servicio_muc": "conference.sinbad2.ujaen.es",
      "password_defecto": "[proporcionada en clase]"
    }
  },

  "agentes_individuales": [
    {
      "modulo": "agentes.agente_tablero",
      "clase": "AgenteTablero",
      "jid_local": "tablero_test@localhost",
      "jid_servidor": "tablero_pcXX@sinbad2.ujaen.es"
    },
    {
      "modulo": "agentes.agente_jugador",
      "clase": "AgenteJugador",
      "jid_local": "jugador_test@localhost",
      "jid_servidor": "jugador_pcXX@sinbad2.ujaen.es"
    }
  ],

  "agentes_grupo": [
    {
      "modulo": "agentes.agente_tablero",
      "clase": "AgenteTablero",
      "jid_local": "tablero@localhost"
    },
    {
      "modulo": "agentes.agente_jugador",
      "clase": "AgenteJugador",
      "jid_local": "jugador_x@localhost",
      "parametros": { "ficha": "X" }
    },
    {
      "modulo": "agentes.agente_jugador",
      "clase": "AgenteJugador",
      "jid_local": "jugador_o@localhost",
      "parametros": { "ficha": "O" }
    }
  ],

  "prueba_colectiva": {
    "sala_muc": "sala_pcXX",
    "agentes_propios": [
      "tablero_pcXX@sinbad2.ujaen.es",
      "jugador_pcXX_x@sinbad2.ujaen.es",
      "jugador_pcXX_o@sinbad2.ujaen.es"
    ],
    "timeout_partida": 60,
    "informe_salida": "informe_integracion.json"
  }
}
```

Los alumnos sustituyen `XX` por su número de puesto asignado.

---

### 3.6 V-06 — Informe HTML consolidado de evaluación

**Prioridad:** Baja
**Fichero destino:** `validacion/generar_informe_evaluacion.py`
**Carencias que resuelve:** C-06

#### Motivación

Tras ejecutar el validador cruzado sobre todos los informes, el
profesor obtiene N ficheros JSON de resultado. Es útil tener un
informe HTML autocontenido que consolide todo en un documento
legible y navegable.

#### Contenido del informe HTML

1. **Cabecera** — Fecha del examen, ID de ejecución del supervisor,
   número de alumnos evaluados.

2. **Resumen global** — Tabla con una fila por alumno:
   - Equipo, puesto, puntuación, estado (sin discrepancias / con
     discrepancias / informe no entregado), número de partidas
     verificadas.

3. **Detalle por alumno** — Sección expandible para cada alumno:
   - Partidas verificadas con semáforo (verde = coincide, rojo =
     discrepancia).
   - Lista de discrepancias con campos afectados.
   - Partidas no reportadas y partidas inventadas.
   - Incidencias omitidas.

4. **Vista cruzada** — Para cada partida observada por el supervisor:
   - Qué alumno(s) la reportaron.
   - Si los datos coinciden entre alumnos y supervisor.
   - Útil para detectar partidas que ningún alumno reportó.

5. **Pie** — Generado por el validador cruzado v1.0, timestamp.

#### Interfaz

```bash
python -m validacion.generar_informe_evaluacion \
    --referencia informe_referencia.json \
    --resultados resultados/ \
    --html evaluacion_final.html
```

---

## 4. Protocolo del día del examen desde el supervisor

Secuencia completa de comandos que el profesor ejecuta:

```bash
# ── Antes del examen ──────────────────────────────────────────

# 1. Preparar el fichero de agentes esperados (rellenar nicks reales)
vim config/agentes_esperados.yaml

# ── F1: Despliegue (0'–10') ──────────────────────────────────

# 2. Arrancar el supervisor en modo laboratorio
python supervisor_main.py --modo laboratorio \
    --db data/examen_2026-04-15.db --puerto 10090

# Dashboard accesible en http://localhost:10090/supervisor
# Los alumnos arrancan sus agentes en sus puestos

# ── F2: Verificación de presencia (10'–15') ───────────────────

# 3. Proyectar la pantalla de verificación en el laboratorio
# Navegar a http://localhost:10090/supervisor → pestaña Verificación F2
# O consultar directamente la API:
curl http://localhost:10090/supervisor/api/verificacion | python -m json.tool

# ── F3: Ejecución de pruebas (15'–35') ────────────────────────

# 4. Dar la señal de inicio: "¡Comenzad!"
# El supervisor monitoriza automáticamente todas las partidas
# Los alumnos ejecutan: pytest tests/test_colectiva.py -v

# ── F4: Generación de informes (35'–45') ──────────────────────

# 5. Cuando los alumnos terminen, exportar el informe de referencia
curl -o informe_referencia.json \
    http://localhost:10090/supervisor/api/informe-referencia

# Los alumnos entregan informe_integracion.json (generado por sus tests)
# Recoger todos los informes en un directorio
mkdir informes_alumnos/
# (los alumnos copian o suben sus ficheros)

# ── F5: Verificación del profesor (después de la sesión) ──────

# 6. Validar esquema de todos los informes de alumnos
python -m validacion.validar_informes \
    --referencia informe_referencia.json \
    --directorio informes_alumnos/

# 7. Generar informe HTML consolidado de evaluación
python -m validacion.validar_informes \
    --referencia informe_referencia.json \
    --directorio informes_alumnos/ \
    --html evaluacion_examen.html

# ── Post-examen (opcional) ────────────────────────────────────

# 8. Consultar ejecución pasada si se necesita revisar
python supervisor_main.py --modo consulta \
    --db data/examen_2026-04-15.db
```

---

## 5. Matriz de trazabilidad con las fases de la diapositiva 13

| Fase | Necesidad | Pieza | Estado |
|------|-----------|-------|--------|
| F1 | Arrancar supervisor con salas por puesto | Existente (`--modo laboratorio`) | ✅ Implementado |
| F1 | Alumnos configuran su entorno | **V-05** `test_config.json` | ✅ Implementado |
| F2 | Definir agentes esperados por sala | **V-04** `agentes_esperados.yaml` | Pendiente |
| F2 | Verificar presencia con checklist | **V-04** Endpoint + vista | Pendiente |
| F3 | Monitorizar partidas en tiempo real | Existente (behaviours + dashboard) | ✅ Implementado |
| F3 | Solicitar y validar `game-report` | Existente (FSM + validación semántica) | ✅ Implementado |
| F4 | Exportar informe de referencia del profesor | **V-02** Endpoint | Pendiente |
| F4 | Definir formato de informe del alumno | **V-01** Esquema JSON + validador + guía | ✅ Implementado |
| F5 | Comparar informes alumno vs. supervisor | **V-03** Validador cruzado | Pendiente |
| F5 | Informe consolidado de evaluación | **V-06** HTML consolidado | Pendiente |

---

## 6. Estado de implementación

| ID | Pieza | Prioridad | Ficheros | Estado |
|----|-------|-----------|----------|--------|
| V-01 | Esquema + validador + guía informe alumno | Alta | `ontologia/esquema_informe_alumno.json`, `validacion/informe_alumno.py`, `validacion/__init__.py`, `tests/test_informe_alumno.py`, `doc/GUIA_INFORME_ALUMNO.md` | ✅ Implementado |
| V-02 | Informe referencia profesor | Alta | `web/supervisor_handlers.py` | Pendiente |
| V-03 | Validador cruzado | Alta | `validacion/validar_informes.py` | Pendiente |
| V-04 | Verificación presencia F2 | Media | `web/supervisor_handlers.py`, `config/agentes_esperados.yaml` | Pendiente |
| V-05 | test_config.json | Media | `test_config.json` | ✅ Implementado |
| V-06 | Informe HTML evaluación | Baja | `validacion/generar_informe_evaluacion.py` | Pendiente |

### Resumen del progreso

- **Implementado:** V-01, V-05 (2 de 6 piezas)
- **Siguiente prioridad:** V-02 (informe de referencia del profesor),
  V-03 (validador cruzado)
- **Rama para alumnos:** `feature/informe-alumno` contiene V-01 y V-05
  con documentación autocontenida
- **Commits sin push:** ambas ramas tienen commits locales pendientes
  de push al remoto

---

## 7. Comprobaciones manuales del profesor

Esta seccion describe las verificaciones que el profesor debe
realizar para validar el correcto funcionamiento del supervisor
antes de una sesion de laboratorio o torneo. Las comprobaciones
cubren tanto los tests automatizados como la revision de los
datos persistentes generados por los tests de integracion.

### 7.1 Ejecucion de tests automatizados

**Paso 1 — Tests unitarios (sin servidor XMPP):**

```bash
pytest tests/ --ignore=tests/test_integracion_supervisor.py -v
```

Resultado esperado: **409 passed, 0 failed**.

**Paso 2 — Tests de integracion (con servidor XMPP):**

```bash
# Asegurar que el servidor XMPP esta accesible
XMPP_PERFIL=local pytest tests/test_integracion_supervisor.py -v
```

Resultado esperado: **40 passed, 0 failed**.

### 7.2 Revision de datos persistentes tras integracion

Los tests de integracion persisten sus resultados en
`data/integracion.db`. El profesor debe verificar que los datos
almacenados son coherentes con lo esperado.

**Paso 3 — Abrir el dashboard en modo consulta:**

```bash
python supervisor_main.py --modo consulta \
    --db data/integracion.db --puerto 10090
```

Abrir `http://localhost:10090/supervisor` y verificar:

- [ ] La ejecucion mas reciente aparece en el selector.
- [ ] Las salas con actividad muestran informes en la pestaña
      Informes.
- [ ] La pestaña Log muestra los eventos de presencia,
      solicitud e informe en orden cronologico.
- [ ] La pestaña Incidencias muestra las anomalias semanticas
      (turnos anomalos, victoria sin linea, etc.) separadas
      del log operativo (P-06).
- [ ] La pestaña Ranking calcula correctamente las
      estadisticas de cada jugador.
- [ ] Los nombres largos se truncan visualmente con tooltip
      (P-08).
- [ ] El modo nocturno tiene contraste suficiente (P-10).

### 7.3 Verificacion de exportacion CSV al finalizar

**Paso 4 — Ejecutar una sesion de prueba y finalizar:**

```bash
# Arrancar en modo laboratorio o torneo
python supervisor_main.py --modo laboratorio

# Desde el dashboard, pulsar el boton "Finalizar torneo"
# Verificar que se genera la carpeta de CSV
```

Verificar:

- [ ] Se crea el directorio `data/sesiones/YYYY-MM-DD_HH-MM-SS_modo/`.
- [ ] Dentro hay un subdirectorio por cada sala con trafico.
- [ ] Cada subdirectorio contiene `ranking.csv`, `log.csv`
      y opcionalmente `incidencias.csv`.
- [ ] Los CSV se abren correctamente en una hoja de calculo.
- [ ] Las salas sin actividad no generan subdirectorio.
- [ ] La respuesta JSON del endpoint incluye
      `csv_exportados` con la ruta generada.

### 7.4 Validacion especifica de correcciones del torneo

Las siguientes comprobaciones verifican que las correcciones
de los problemas P-01 a P-07 funcionan correctamente:

**P-01 — Solicitudes duplicadas:**

- [ ] En el log, cada tablero que finaliza tiene exactamente
      1 evento de solicitud (no 2 ni mas).
- [ ] Un tablero que juega 2 partidas tiene exactamente
      2 eventos de solicitud.

**P-03 — Conversation-id:**

- [ ] En los tests unitarios de ontologia, las clases
      `TestConversationId` y `TestCrearMensajeJoin` pasan.
- [ ] En la traza del supervisor, los REQUEST de game-report
      incluyen `conversation-id` en la metadata.

**P-04 — Jugadores observados:**

- [ ] En el dashboard, no aparecen inconsistencias de "no
      observado" para jugadores que jugaron la partida.
- [ ] Un jugador que abandono antes del informe NO genera
      falso positivo.

**P-05 — Duplicados por thread:**

- [ ] Dos partidas con el mismo resultado entre los mismos
      jugadores NO se marcan como duplicadas.

**P-07 — Coherencia de resultados (V1-V11):**

- [ ] Los informes con turnos anomalos generan inconsistencia.
- [ ] Los informes con fichas desequilibradas generan
      inconsistencia.
- [ ] Los informes con O moviendo primero generan
      inconsistencia.
- [ ] Los informes correctos NO generan inconsistencia.
