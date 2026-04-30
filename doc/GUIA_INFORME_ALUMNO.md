# Guia de integracion del informe de la Bateria 3

**Asignatura:** Sistemas Multiagente — Universidad de Jaen

**Proyecto:** Tic-Tac-Toe Multiagente

---

## Objetivo

Durante la prueba colectiva del dia del examen (Bateria 3), cada
alumno debe generar un **informe de integracion** en formato JSON
que recoja lo que observaron sus agentes durante la sesion. El
profesor cruzara este informe con los datos que su propio agente
supervisor registro en tiempo real. La **coherencia cruzada** entre
ambos es un criterio de evaluacion clave.

Este documento explica que ficheros debeis integrar en vuestro
proyecto y como usarlos.

---

## 1. Ficheros a copiar en vuestro proyecto

Copiad los siguientes ficheros **sin modificarlos**:

```
ontologia/esquema_informe_alumno.json   ← Esquema JSON del informe
validacion/__init__.py                  ← Paquete de validacion
validacion/informe_alumno.py            ← Validador y constructores
test_config.json                        ← Plantilla de configuracion de pruebas
```

La estructura resultante en vuestro proyecto debe ser:

```
mi-proyecto/
├── ontologia/
│   ├── ontologia_tictactoe.schema.json   (ya lo teneis)
│   ├── esquema_informe_alumno.json       ← NUEVO
│   └── ...
├── validacion/
│   ├── __init__.py                       ← NUEVO
│   └── informe_alumno.py                 ← NUEVO
├── tests/
│   ├── test_informe_alumno.py            ← NUEVO (opcional, recomendado)
│   └── ...
├── test_config.json                      ← NUEVO
└── ...
```

> **No modifiqueis** el esquema ni el validador. Si el profesor
> actualiza estos ficheros, recibireis la version nueva.

---

## 2. Configurar `test_config.json`

Editad el fichero `test_config.json` y sustituid `XX` por vuestro
numero de puesto asignado:

```json
{
  "entorno": "local",
  "prueba_colectiva": {
    "sala_muc": "sala_pc05",
    "agentes_propios": [
      "tablero_pc05@sinbad2.ujaen.es",
      "jugador_pc05_x@sinbad2.ujaen.es",
      "jugador_pc05_o@sinbad2.ujaen.es"
    ],
    "timeout_partida": 60,
    "informe_salida": "informe_integracion.json"
  }
}
```

El dia del examen, cambiad `"entorno"` a `"servidor"`.

---

## 3. Generar el informe desde vuestros tests

### 3.1 Importar los constructores

```python
from validacion import (
    crear_informe_alumno,
    crear_partida_observada,
    serializar_informe_alumno,
    validar_informe_alumno,
)
```

### 3.2 Registrar cada partida observada

Cada vez que vuestro agente (tablero o jugador) termine una partida,
cread una entrada con `crear_partida_observada()`:

```python
partida = crear_partida_observada(
    tablero_jid="tablero_pc05@sinbad2.ujaen.es",
    resultado="win",            # "win", "draw" o "aborted"
    jugadores={
        "X": "jugador_pc05_x@sinbad2.ujaen.es",
        "O": "jugador_pc07_o@sinbad2.ujaen.es",
    },
    turnos=7,
    tablero_final=["X", "O", "X", "", "X", "O", "O", "X", ""],
    ganador_ficha="X",          # obligatorio si resultado="win"
    timestamp="10:25:33",       # HH:MM:SS (opcional pero recomendado)
    razon=None,                 # obligatorio si resultado="aborted"
)
```

Acumulad las partidas en una lista durante la sesion.

### 3.3 Construir y serializar el informe al finalizar

Al terminar la sesion de pruebas, construid el informe completo y
guardadlo en disco:

```python
from datetime import datetime

informe = crear_informe_alumno(
    equipo="grupo_03",
    puesto="pc05",
    timestamp_inicio="2026-04-15T10:15:00",
    timestamp_fin=datetime.now().isoformat(),
    agentes_desplegados=[
        {"jid": "tablero_pc05@sinbad2.ujaen.es", "rol": "tablero"},
        {"jid": "jugador_pc05_x@sinbad2.ujaen.es", "rol": "jugador"},
        {"jid": "jugador_pc05_o@sinbad2.ujaen.es", "rol": "jugador"},
    ],
    partidas_observadas=lista_partidas,
    incidencias=lista_incidencias,  # opcional
)

# Valida y escribe el fichero (lanza ValueError si es invalido)
serializar_informe_alumno(informe, "informe_integracion.json")
```

### 3.4 Ejemplo con fixture de pytest

La forma recomendada es usar un fixture `scope="session"` que
acumule datos durante los tests y genere el informe al final:

```python
# conftest.py
import json
import pytest
from datetime import datetime

from validacion import (
    crear_informe_alumno,
    serializar_informe_alumno,
)


def _leer_config():
    with open("test_config.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def acumulador_informe():
    """Acumula partidas e incidencias durante toda la sesion."""
    datos = {
        "partidas": [],
        "incidencias": [],
        "inicio": datetime.now().isoformat(),
    }
    yield datos
    # --- Teardown: generar informe al finalizar todos los tests ---
    cfg = _leer_config()
    colectiva = cfg["prueba_colectiva"]
    puesto = colectiva["sala_muc"].replace("sala_", "")

    informe = crear_informe_alumno(
        equipo="grupo_XX",           # Poned vuestro grupo
        puesto=puesto,
        timestamp_inicio=datos["inicio"],
        timestamp_fin=datetime.now().isoformat(),
        agentes_desplegados=[
            {"jid": jid, "rol": "tablero" if "tablero" in jid else "jugador"}
            for jid in colectiva["agentes_propios"]
        ],
        partidas_observadas=datos["partidas"],
        incidencias=datos["incidencias"],
    )

    ruta = colectiva.get("informe_salida", "informe_integracion.json")
    try:
        serializar_informe_alumno(informe, ruta)
        print(f"\n=== Informe generado: {ruta} ===")
    except ValueError as e:
        print(f"\n=== ERROR generando informe: {e} ===")
```

En vuestros tests, usad el fixture para registrar partidas:

```python
# tests/test_colectiva.py
from validacion import crear_partida_observada


def test_partida_completa(acumulador_informe, tablero, jugador_x, jugador_o):
    """Juega una partida y registra el resultado."""
    # ... vuestra logica de test ...
    resultado = tablero.obtener_resultado()

    partida = crear_partida_observada(
        tablero_jid=str(tablero.jid),
        resultado=resultado["result"],
        jugadores=resultado["players"],
        turnos=resultado["turns"],
        tablero_final=resultado["board"],
        ganador_ficha=resultado.get("winner"),
        timestamp=datetime.now().strftime("%H:%M:%S"),
        razon=resultado.get("reason"),
    )
    acumulador_informe["partidas"].append(partida)
```

---

## 4. Formato del informe

El informe debe cumplir el esquema `esquema_informe_alumno.json`.
Estos son los campos:

### Campos obligatorios de primer nivel

| Campo | Tipo | Ejemplo |
|-------|------|---------|
| `equipo` | string | `"grupo_03"` |
| `puesto` | string (`pcXX`) | `"pc05"` |
| `timestamp_inicio` | ISO 8601 | `"2026-04-15T10:15:00"` |
| `timestamp_fin` | ISO 8601 | `"2026-04-15T10:35:00"` |
| `agentes_desplegados` | array (min 1) | ver abajo |
| `partidas_observadas` | array | ver abajo |

### Agente desplegado

| Campo | Tipo | Valores |
|-------|------|---------|
| `jid` | string | JID completo |
| `rol` | string | `"tablero"` o `"jugador"` |

### Partida observada

| Campo | Obligatorio | Tipo | Valores |
|-------|-------------|------|---------|
| `tablero_jid` | si | string | JID del tablero |
| `resultado` | si | string | `"win"`, `"draw"`, `"aborted"` |
| `ganador_ficha` | si si win | string/null | `"X"`, `"O"`, `null` |
| `jugadores` | si | objeto | `{"X": jid, "O": jid}` |
| `turnos` | si | entero | 0–9 |
| `tablero_final` | si | array[9] | `"X"`, `"O"`, `""` |
| `timestamp` | no | string | `"HH:MM:SS"` |
| `razon` | si si aborted | string/null | `"invalid"`, `"timeout"`, `"both-timeout"` |

### Incidencia (opcional)

| Campo | Obligatorio | Tipo | Valores |
|-------|-------------|------|---------|
| `tipo` | si | string | `"timeout"`, `"error"`, `"rechazo"`, `"desconexion"`, `"otro"` |
| `detalle` | si | string | descripcion legible |
| `timestamp` | no | string | `"HH:MM:SS"` |

---

## 5. Reglas de validacion

El validador comprueba automaticamente:

1. **Esquema JSON** — Todos los campos existen, tienen el tipo
   correcto y los valores estan dentro de los permitidos.

2. **Coherencia temporal** — `timestamp_inicio` es anterior a
   `timestamp_fin`.

3. **Reglas cruzadas por partida:**
   - Si `resultado="win"` → `ganador_ficha` es obligatorio.
   - Si `resultado="draw"` → `ganador_ficha` debe ser `null`.
   - Si `resultado="aborted"` → `razon` es obligatorio.
   - Victoria requiere al menos 5 turnos.
   - No puede haber mas de 9 turnos.
   - El tablero final debe ser coherente con el resultado
     (linea ganadora si victoria, sin linea si empate).
   - Un jugador no puede jugar contra si mismo.

Podeis verificar vuestro informe en cualquier momento:

```python
from validacion import validar_informe_alumno
import json

with open("informe_integracion.json", encoding="utf-8") as f:
    informe = json.load(f)

resultado = validar_informe_alumno(informe)
if resultado["valido"]:
    print("Informe valido")
else:
    for error in resultado["errores"]:
        print(f"  ERROR: {error}")
```

O desde la linea de ordenes:

```bash
python -c "
import json
from validacion import validar_informe_alumno
with open('informe_integracion.json') as f:
    r = validar_informe_alumno(json.load(f))
print('OK' if r['valido'] else '\n'.join(r['errores']))
"
```

---

## 6. Que hace el profesor con vuestro informe

1. **Valida el esquema** — Si vuestro informe no cumple el esquema,
   no se puede procesar.

2. **Cruza con el supervisor** — Cada partida que declarais se
   compara con los datos que el agente supervisor registro en
   tiempo real. Se verifican: resultado, jugadores, turnos,
   tablero final e incidencias.

3. **Detecta anomalias:**
   - *Partida no reportada*: el supervisor la observo pero
     vosotros no la declarais.
   - *Partida inventada*: la declarais pero el supervisor no
     la observo.
   - *Discrepancia de datos*: resultado, jugadores o tablero
     distintos a lo que registro el supervisor.

4. **Genera un informe de evaluacion** que consolida los resultados
   de todos los alumnos.

---

## 7. Checklist antes de la entrega

- [ ] `test_config.json` tiene vuestro numero de puesto (`pcXX`).
- [ ] `test_config.json` tiene `"entorno": "servidor"` para el examen.
- [ ] El fichero `informe_integracion.json` se genera al ejecutar
      `pytest tests/test_colectiva.py`.
- [ ] El informe pasa la validacion:
      `python -c "..." ` (ver seccion 5).
- [ ] El informe contiene **todas** las partidas que observasteis.
- [ ] Los JIDs de los jugadores son los reales del servidor
      (no `localhost`).
- [ ] Los agentes permanecen activos hasta que el profesor indique
      el cierre.

---

## 8. Dependencia

El validador requiere `jsonschema` (ya esta en `requirements.txt`).
Si no lo teneis:

```bash
pip install jsonschema>=4.20.0
```

---

## 9. Tests del informe (opcionales pero recomendados)

Copiad `tests/test_informe_alumno.py` a vuestro proyecto. Estos
tests verifican que el esquema, los constructores y el validador
funcionan correctamente en vuestro entorno:

```bash
pytest tests/test_informe_alumno.py -v
```

Si los 36 tests pasan, la integracion es correcta.
