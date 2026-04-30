# Guía de pruebas y tests — Agente Supervisor

> Sistemas Multiagente · Universidad de Jaén
>
> Última actualización: 2026-04-10

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Estructura de tests existentes](#2-estructura-de-tests-existentes)
3. [Ejecución rápida de los tests](#3-ejecución-rápida-de-los-tests)
4. [Tests unitarios del supervisor](#4-tests-unitarios-del-supervisor)
   - 4.1 [Manejadores web (supervisor_handlers.py)](#41-manejadores-web)
   - 4.2 [Behaviours (supervisor_behaviours.py)](#42-behaviours)
   - 4.3 [Lógica de conversión de datos](#43-lógica-de-conversión-de-datos)
5. [Tests de integración del panel](#5-tests-de-integración-del-panel)
6. [Pruebas manuales del panel web](#6-pruebas-manuales-del-panel-web)
   - 6.1 [Arranque sin servidor XMPP](#61-arranque-sin-servidor-xmpp)
   - 6.2 [Verificación visual del panel](#62-verificación-visual-del-panel)
   - 6.3 [Verificación de la ruta API](#63-verificación-de-la-ruta-api)
7. [Datos de prueba](#7-datos-de-prueba)
8. [Convenciones y patrones de test](#8-convenciones-y-patrones-de-test)
9. [Resolución de problemas](#9-resolución-de-problemas)

---

## 1. Requisitos previos

### Dependencias Python

Instalar todas las dependencias del proyecto, incluidas las de testing:

```bash
pip install -r requirements.txt
```

Las dependencias relevantes para testing son:

| Paquete            | Versión mínima | Propósito                           |
|--------------------|----------------|--------------------------------------|
| `pytest`           | 8.0            | Marco de pruebas                     |
| `pytest-asyncio`   | 0.23           | Soporte para tests asíncronos        |
| `pytest-timeout`   | 2.2            | Evitar tests que no terminan         |
| `aiohttp`          | 3.9            | Servidor web y cliente de pruebas    |
| `jsonschema`       | 4.20           | Validación de ontología              |
| `beautifulsoup4`   | 4.12           | Verificación de HTML generado        |
| `lxml`             | 5.1            | Parser HTML para BeautifulSoup       |

### Servidor XMPP (opcional)

Para pruebas de integración completas se necesita un servidor XMPP
(Prosody o similar) en `localhost:5222`.  **No es necesario** para los
tests unitarios ni para las pruebas manuales del panel.

---

## 2. Estructura de tests existentes

```
tests/
├── __init__.py
├── test_ontologia.py              ← 60 tests — ontología runtime
├── test_almacen_supervisor.py     ← 28 tests — persistencia SQLite
├── test_supervisor_behaviours.py  ← 65 tests — funciones auxiliares, FSM y validación semántica
├── test_agente_supervisor.py      ← 33 tests — métodos del agente y presencia
├── test_supervisor_handlers.py    ← 25 tests — conversión de datos y rutas HTTP
├── test_creacion_salas.py         ← 13 tests — creación de salas MUC por modo
└── TESTING_SUPERVISOR.md          ← Este documento
```

**Total: 308 tests** ejecutables con `pytest tests/ -v` (277 unitarios + 31 de integración).

| Fichero | Tests | Componente verificado |
|---------|------:|-----------------------|
| `test_ontologia.py` | 60 | Esquema JSON, constructores, validación, performativas FIPA y protocolo del supervisor |
| `test_supervisor_behaviours.py` | 76 | Funciones auxiliares, los 7 estados de `SolicitarInformeFSM` (incluyendo `EstadoReintentar` M-04), validaciones semánticas y reintento con retroceso exponencial |
| `test_almacen_supervisor.py` | 37 | `AlmacenSupervisor`: inicialización, ejecuciones, informes, eventos, aislamiento, filtrado de salas sin actividad y commits por lotes (M-08) |
| `test_supervisor_handlers.py` | 52 | `_mapear_resultado`, `_nombre_legible_sala`, `_convertir_informes`, `_computar_ranking`, generación CSV, rutas HTTP, endpoints de exportación CSV y SSE |
| `test_agente_supervisor.py` | 39 | `_identificar_sala`, `obtener_sala_de_tablero`, `registrar_evento_log`, `_on_presencia_muc`, límite de FSMs concurrentes (`TestLimiteFSMConcurrentes`) y advertencias al detener con cola no vacía |
| `test_creacion_salas.py` | 13 | Carga de `salas_laboratorio.yaml`, `sala_torneo.yaml` y `torneos.yaml`; creación y visibilidad de salas MUC |
| `test_integracion_supervisor.py` | 30 | Tests de integración con agentes SPADE reales: inconsistencia semántica y reintento con retroceso (requiere servidor XMPP). Ver [TESTING_INTEGRACION_SUPERVISOR.md](TESTING_INTEGRACION_SUPERVISOR.md) |

---

## 3. Ejecución rápida de los tests

```text
# Todos los tests con detalle (169 tests)
pytest tests/ -v

# Solo tests del supervisor (5 ficheros, 109 tests)
pytest tests/test_almacen_supervisor.py \
       tests/test_supervisor_behaviours.py \
       tests/test_agente_supervisor.py \
       tests/test_supervisor_handlers.py \
       tests/test_creacion_salas.py -v

# Un fichero individual
pytest tests/test_almacen_supervisor.py -v
pytest tests/test_supervisor_behaviours.py -v
pytest tests/test_agente_supervisor.py -v
pytest tests/test_supervisor_handlers.py -v
pytest tests/test_creacion_salas.py -v

# Tests con timeout de seguridad (recomendado para behaviours async)
pytest tests/ -v --timeout=10

# Con informe de cobertura (requiere pytest-cov)
pytest tests/ -v --cov=web --cov=behaviours --cov=agentes --cov=persistencia --cov-report=term-missing
```

---

## 4. Tests unitarios del supervisor

A continuación se describen los tests implementados para verificar
cada componente del supervisor. Todos se ejecutan sin necesidad de
arrancar SPADE ni de conectarse a un servidor XMPP: utilizan objetos
simulados y bases de datos SQLite temporales.

### 4.1 Manejadores web

**Fichero:** `tests/test_supervisor_handlers.py`

Los manejadores son funciones `async` que reciben un `aiohttp.web.Request`
y devuelven un `aiohttp.web.Response`.  Se pueden testear con el
cliente de pruebas de aiohttp sin necesidad de un agente SPADE real.

#### Tests a implementar

| ID   | Test                                          | Qué verifica                                             |
|------|-----------------------------------------------|----------------------------------------------------------|
| H-01 | `test_index_devuelve_html`                    | GET `/supervisor` devuelve 200 con `text/html`           |
| H-02 | `test_index_contiene_titulo`                  | La respuesta HTML contiene el título del panel            |
| H-03 | `test_state_devuelve_json`                    | GET `/supervisor/api/state` devuelve 200 con JSON válido |
| H-04 | `test_state_tiene_campo_salas`                | La respuesta contiene la clave `"salas"` (lista)         |
| H-05 | `test_state_tiene_campo_timestamp`            | La respuesta contiene `"timestamp"` en formato `HH:MM:SS` |
| H-06 | `test_state_sala_tiene_campos_requeridos`     | Cada sala tiene: `id`, `nombre`, `jid`, `ocupantes`, `informes`, `log` |
| H-07 | `test_state_informes_mapeados_correctamente`  | Los informes se convierten de ontología a formato del panel |
| H-08 | `test_state_sin_informes_devuelve_lista_vacia`| Con agente sin informes, `salas[0].informes` es `[]`     |
| H-09 | `test_static_css_accesible`                   | GET `/supervisor/static/supervisor.css` devuelve 200     |
| H-10 | `test_static_js_accesible`                    | GET `/supervisor/static/supervisor.js` devuelve 200      |

#### Patrón de test con el cliente de pruebas de aiohttp

```python
"""Tests para los handlers HTTP del dashboard del supervisor."""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from web.supervisor_handlers import registrar_rutas_supervisor


class AgenteMock:
    """Simula el agente supervisor para los tests de handlers.

    Expone los mismos atributos que AgenteSupervisor sin depender
    de SPADE ni de XMPP.
    """

    def __init__(self):
        self.muc_sala = "tictactoe@conference.localhost"
        self.ocupantes_sala = []
        self.informes_recibidos = {}
        self.log_eventos = []


@pytest.fixture
def agente_mock():
    """Fixture que proporciona un agente simulado."""
    return AgenteMock()


@pytest.fixture
async def cliente_web(aiohttp_client, agente_mock):
    """Fixture que proporciona un cliente HTTP de prueba.

    Crea una aplicación aiohttp con las rutas del supervisor
    y un agente simulado inyectado.
    """
    app = web.Application()
    registrar_rutas_supervisor(app)
    app["agente"] = agente_mock
    cliente = await aiohttp_client(app)
    return cliente


@pytest.mark.asyncio
async def test_index_devuelve_html(cliente_web):
    """GET /supervisor debe devolver 200 con contenido HTML."""
    respuesta = await cliente_web.get("/supervisor")
    assert respuesta.status == 200
    assert "text/html" in respuesta.content_type


@pytest.mark.asyncio
async def test_state_devuelve_json(cliente_web):
    """GET /supervisor/api/state debe devolver JSON con salas."""
    respuesta = await cliente_web.get("/supervisor/api/state")
    assert respuesta.status == 200
    datos = await respuesta.json()
    assert "salas" in datos
    assert isinstance(datos["salas"], list)
    assert "timestamp" in datos
```

#### Datos de prueba para informes

```python
INFORME_VICTORIA = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 7,
    "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
    "ts": "09:28:30",
}

INFORME_EMPATE = {
    "action": "game-report",
    "result": "draw",
    "winner": None,
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 9,
    "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
    "ts": "09:35:12",
}

INFORME_ABORTADA = {
    "action": "game-report",
    "result": "aborted",
    "winner": None,
    "reason": "both-timeout",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 2,
    "board": ["X", "", "", "", "O", "", "", "", ""],
    "ts": "10:12:45",
}
```

### 4.2 Behaviours

**Fichero:** `tests/test_supervisor_behaviours.py`

Los behaviours son más difíciles de testear porque dependen del ciclo
de vida de SPADE.  Se recomienda testear las **funciones auxiliares**
de forma aislada y usar objetos simulados para los behaviours completos.

#### Funciones auxiliares testeables directamente

| ID   | Test                                              | Función bajo test          |
|------|---------------------------------------------------|-----------------------------|
| B-01 | `test_determinar_rol_tablero`                     | `_determinar_rol("tablero_mesa1")` → `"tablero"`  |
| B-02 | `test_determinar_rol_jugador`                     | `_determinar_rol("jugador_ana")` → `"jugador"`  |
| B-03 | `test_determinar_rol_supervisor`                  | `_determinar_rol("supervisor")` → `"supervisor"`  |
| B-04 | `test_determinar_rol_desconocido`                 | `_determinar_rol("otro_nick")` → `"jugador"` (default) |
| B-05 | `test_detalle_informe_victoria`                   | `_construir_detalle_informe(...)` contiene `"Victoria"` |
| B-06 | `test_detalle_informe_empate`                     | `_construir_detalle_informe(...)` contiene `"Empate"` |
| B-07 | `test_detalle_informe_abortada`                   | `_construir_detalle_informe(...)` contiene `"Abortada"` |
| B-08 | `test_detalle_informe_muestra_alumnos`            | El detalle incluye los nombres cortos de ambos jugadores |
| B-09 | `test_detalle_informe_muestra_turnos`             | El detalle incluye el número de turnos jugados    |

#### Patrón de test

```python
"""Tests para las funciones auxiliares de supervisor_behaviours."""

import pytest

from behaviours.supervisor_behaviours import (
    _construir_detalle_informe,
    _determinar_rol,
)


class TestDeterminarRol:
    """Verifica la clasificación de ocupantes MUC por apodo."""

    def test_tablero(self) -> None:
        assert _determinar_rol("tablero_mesa1") == "tablero"

    def test_jugador_con_prefijo(self) -> None:
        assert _determinar_rol("jugador_ana") == "jugador"

    def test_supervisor(self) -> None:
        assert _determinar_rol("supervisor") == "supervisor"

    def test_nick_sin_prefijo_es_jugador(self) -> None:
        # Por defecto, un nick no reconocido se clasifica como jugador
        assert _determinar_rol("observador") == "jugador"


class TestConstruirDetalleInforme:
    """Verifica la generación de texto descriptivo para el log."""

    def test_victoria_incluye_ganador(self) -> None:
        cuerpo = {
            "result": "win", "winner": "X", "turns": 7,
            "players": {"X": "jugador_ana@h", "O": "jugador_luis@h"},
        }
        detalle = _construir_detalle_informe(cuerpo)
        assert "Victoria" in detalle
        assert "ana" in detalle

    def test_empate(self) -> None:
        cuerpo = {
            "result": "draw", "turns": 9,
            "players": {"X": "jugador_ana@h", "O": "jugador_luis@h"},
        }
        detalle = _construir_detalle_informe(cuerpo)
        assert "Empate" in detalle

    def test_abortada_incluye_reason(self) -> None:
        cuerpo = {
            "result": "aborted", "reason": "both-timeout", "turns": 2,
            "players": {"X": "jugador_ana@h", "O": "jugador_luis@h"},
        }
        detalle = _construir_detalle_informe(cuerpo)
        assert "Abortada" in detalle
        assert "Abortada" in detalle
```

### 4.3 Lógica de conversión de datos

**Fichero:** `tests/test_supervisor_handlers.py` (sección adicional)

Las funciones internas de conversión (`_convertir_informes`,
`_mapear_resultado`, `_nombre_legible_sala`) deben verificarse
para asegurar que el frontend recibe datos correctos.

| ID   | Test                                    | Qué verifica                                          |
|------|-----------------------------------------|-------------------------------------------------------|
| C-01 | `test_mapear_resultado_win`             | `"win"` → `"victoria"`                               |
| C-02 | `test_mapear_resultado_draw`            | `"draw"` → `"empate"`                                |
| C-03 | `test_mapear_resultado_aborted`         | `"aborted"` → `"abortada"`                           |
| C-04 | `test_mapear_resultado_ya_en_espanol`   | `"victoria"` → `"victoria"` (idempotente)            |
| C-05 | `test_convertir_informes_vacio`         | `{}` → `[]`                                          |
| C-06 | `test_convertir_informes_victoria`      | Un informe de victoria se convierte correctamente     |
| C-07 | `test_convertir_informes_preserva_reason` | El campo `reason` se incluye si existe              |
| C-08 | `test_nombre_sala_con_guion_bajo`       | `"tictactoe_grupo_a"` → `"Sala Tictactoe Grupo A"`  |
| C-09 | `test_nombre_sala_simple`               | `"tictactoe"` → `"Sala principal"`                   |

#### Patrón de test

```python
from web.supervisor_handlers import (
    _convertir_informes,
    _mapear_resultado,
    _nombre_legible_sala,
)


class TestMapearResultado:
    """Verifica la traducción de resultados ontología → dashboard."""

    def test_win_a_victoria(self) -> None:
        assert _mapear_resultado("win") == "victoria"

    def test_draw_a_empate(self) -> None:
        assert _mapear_resultado("draw") == "empate"

    def test_aborted_a_abortada(self) -> None:
        assert _mapear_resultado("aborted") == "abortada"

    def test_valor_ya_en_espanol(self) -> None:
        assert _mapear_resultado("victoria") == "victoria"


class TestConvertirInformes:
    """Verifica la conversión de informes internos al formato API."""

    def test_dict_vacio_devuelve_lista_vacia(self) -> None:
        assert _convertir_informes({}) == []

    def test_victoria_se_convierte(self) -> None:
        informes_raw = {
            "tablero_mesa1@conference.localhost": {
                "action": "game-report",
                "result": "win",
                "winner": "X",
                "players": {
                    "X": "jugador_ana@localhost",
                    "O": "jugador_luis@localhost",
                },
                "turns": 7,
                "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
                "ts": "09:28:30",
            }
        }
        resultado = _convertir_informes(informes_raw)
        assert len(resultado) == 1
        informe = resultado[0]
        assert informe["resultado"] == "victoria"
        assert informe["ficha_ganadora"] == "X"
        assert informe["turnos"] == 7
        assert len(informe["tablero_final"]) == 9
```

---

## 5. Tests de integración del panel

Estos tests verifican que la cadena completa (agente → manejador → HTML/JSON)
funciona correctamente.  Requieren un agente simulado más completo.

| ID   | Test                                       | Qué verifica                                         |
|------|--------------------------------------------|------------------------------------------------------|
| I-01 | `test_dashboard_carga_sin_salas`           | Con 0 salas, el panel no lanza errores               |
| I-02 | `test_api_refleja_informes_inyectados`     | Inyectar informes en el objeto simulado → aparecen en la API |
| I-03 | `test_api_refleja_ocupantes_inyectados`    | Inyectar ocupantes en el objeto simulado → aparecen en la API |
| I-04 | `test_api_refleja_log_inyectados`          | Inyectar registro en el objeto simulado → aparecen en la API |
| I-05 | `test_html_incluye_enlace_css`             | El HTML contiene `<link>` a `supervisor.css`         |
| I-06 | `test_html_incluye_enlace_js`              | El HTML contiene `<script>` a `supervisor.js`        |

### Patrón de test de integración

```python
@pytest.mark.asyncio
async def test_api_refleja_informes_inyectados(cliente_web, agente_mock):
    """Los informes inyectados en el agente deben aparecer en la API."""
    # Inyectar un informe de victoria
    agente_mock.informes_recibidos = {
        "tablero_mesa1@conference.localhost": {
            "action": "game-report",
            "result": "win",
            "winner": "X",
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
            "turns": 7,
            "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
            "ts": "09:28:30",
        }
    }

    respuesta = await cliente_web.get("/supervisor/api/state")
    datos = await respuesta.json()
    informes = datos["salas"][0]["informes"]
    assert len(informes) == 1
    assert informes[0]["resultado"] == "victoria"
    assert informes[0]["ficha_ganadora"] == "X"


@pytest.mark.asyncio
async def test_api_refleja_ocupantes_inyectados(cliente_web, agente_mock):
    """Los ocupantes inyectados deben aparecer en la API."""
    agente_mock.ocupantes_sala = [
        {
            "nick": "supervisor",
            "jid": "supervisor@localhost",
            "rol": "supervisor",
            "estado": "online",
        },
        {
            "nick": "tablero_mesa1",
            "jid": "tablero_mesa1@conference.localhost",
            "rol": "tablero",
            "estado": "online",
        },
    ]

    respuesta = await cliente_web.get("/supervisor/api/state")
    datos = await respuesta.json()
    ocupantes = datos["salas"][0]["ocupantes"]
    assert len(ocupantes) == 2
```

---

## 6. Pruebas manuales del panel web

### 6.1 Arranque sin servidor XMPP

El panel puede probarse **sin un servidor XMPP real** creando
un guion mínimo que simula el agente:

```python
"""
Script para probar el dashboard del supervisor sin servidor XMPP.

Ejecutar:
    python tests/prueba_dashboard_local.py

Abrir en el navegador:
    http://localhost:10090/supervisor
"""
import asyncio

from aiohttp import web

from web.supervisor_handlers import registrar_rutas_supervisor


class SupervisorSimulado:
    """Simula el agente supervisor con datos de ejemplo."""

    def __init__(self):
        self.muc_sala = "tictactoe@conference.localhost"
        self.ocupantes_sala = [
            {"nick": "supervisor", "jid": "supervisor@localhost",
             "rol": "supervisor", "estado": "online"},
            {"nick": "tablero_mesa1", "jid": "tablero_mesa1@localhost",
             "rol": "tablero", "estado": "online"},
            {"nick": "tablero_mesa2", "jid": "tablero_mesa2@localhost",
             "rol": "tablero", "estado": "online"},
            {"nick": "jugador_ana", "jid": "jugador_ana@localhost",
             "rol": "jugador", "estado": "online"},
            {"nick": "jugador_luis", "jid": "jugador_luis@localhost",
             "rol": "jugador", "estado": "online"},
        ]
        self.informes_recibidos = {
            "tablero_mesa1@conference.localhost": {
                "action": "game-report",
                "result": "win", "winner": "X",
                "players": {"X": "jugador_ana@localhost",
                             "O": "jugador_luis@localhost"},
                "turns": 7,
                "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
                "ts": "09:28:30",
            },
            "tablero_mesa2@conference.localhost": {
                "action": "game-report",
                "result": "draw", "winner": None,
                "players": {"X": "jugador_luis@localhost",
                             "O": "jugador_ana@localhost"},
                "turns": 9,
                "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
                "ts": "09:35:12",
            },
        }
        self.log_eventos = [
            {"ts": "09:35:12", "tipo": "informe",
             "de": "tablero_mesa2",
             "detalle": "Empate · luis contra ana · 9 turnos"},
            {"ts": "09:28:30", "tipo": "informe",
             "de": "tablero_mesa1",
             "detalle": "Victoria de X (ana) contra luis · 7 turnos"},
            {"ts": "09:25:00", "tipo": "presencia",
             "de": "jugador_luis",
             "detalle": "Se une a la sala MUC"},
            {"ts": "09:24:50", "tipo": "presencia",
             "de": "jugador_ana",
             "detalle": "Se une a la sala MUC"},
            {"ts": "09:24:30", "tipo": "presencia",
             "de": "tablero_mesa2",
             "detalle": "Se une a la sala MUC"},
            {"ts": "09:24:20", "tipo": "presencia",
             "de": "tablero_mesa1",
             "detalle": "Se une a la sala MUC"},
            {"ts": "09:24:00", "tipo": "presencia",
             "de": "supervisor",
             "detalle": "Se une a la sala MUC"},
        ]


async def main():
    app = web.Application()
    registrar_rutas_supervisor(app)
    app["agente"] = SupervisorSimulado()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 10090)
    await site.start()

    print("Dashboard del supervisor disponible en:")
    print("  http://localhost:10090/supervisor")
    print()
    print("Pulsa Ctrl+C para detener.")

    # Mantener el servidor en ejecución
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServidor detenido.")
```

### 6.2 Verificación visual del panel

Con el servidor de prueba arrancado, verificar manualmente:

#### Lista de verificación de interfaz

- [ ] **Header**: Aparece el título "Supervisor · Tic-Tac-Toe Multi-Sala"
- [ ] **Header**: El reloj muestra la hora actual y se actualiza cada segundo
- [ ] **Header**: El resumen global muestra "1 sala · 2 informes"
- [ ] **Toggle tema**: Al pulsar, cambia de modo oscuro a modo claro
- [ ] **Toggle tema**: Al recargar la página, mantiene el tema seleccionado
- [ ] **Sidebar**: Aparece la sala "Sala principal" con estadísticas
- [ ] **Sidebar**: La sala activa tiene borde verde a la izquierda
- [ ] **Stats**: Las 6 cajas muestran los valores correctos
- [ ] **Tab Informes**: Muestra 2 tarjetas de informe
- [ ] **Tab Informes**: El filtro "Victorias" muestra solo 1 tarjeta
- [ ] **Tab Informes**: Al hacer clic en una tarjeta, se abre el modal
- [ ] **Modal**: Muestra los jugadores, tablero SVG y datos técnicos
- [ ] **Modal**: Se cierra con el botón ✕, pulsando Escape o clic fuera
- [ ] **Tab Agentes**: Lista 5 ocupantes agrupados por rol
- [ ] **Tab Clasificación**: Muestra ranking con barras de porcentaje
- [ ] **Tab Log**: Muestra los 7 eventos con colores por tipo
- [ ] **SVG tableros**: Las fichas X y O se representan correctamente
- [ ] **SVG tableros**: La línea ganadora aparece en victorias

#### Lista de verificación de accesibilidad

- [ ] Las fuentes Atkinson Hyperlegible y JetBrains Mono cargan
- [ ] Los contrastes de texto son legibles en ambos temas
- [ ] Los botones tienen `aria-label` descriptivo
- [ ] Los tabs tienen `role="tab"` y `aria-selected`
- [ ] El modal tiene `role="dialog"`

### 6.3 Verificación de la ruta API

Con el servidor arrancado, comprobar la respuesta de la ruta JSON:

```bash
# Obtener el estado completo del supervisor
curl -s http://localhost:10090/supervisor/api/state | python3 -m json.tool
```

Respuesta esperada (estructura):

```json
{
    "salas": [
        {
            "id": "tictactoe",
            "nombre": "Sala principal",
            "jid": "tictactoe@conference.localhost",
            "descripcion": "Sala de partidas Tic-Tac-Toe",
            "ocupantes": [
                {
                    "nick": "supervisor",
                    "jid": "supervisor@localhost",
                    "rol": "supervisor",
                    "estado": "online"
                }
            ],
            "informes": [
                {
                    "id": "informe_001",
                    "tablero": "tablero_mesa1",
                    "ts": "09:28:30",
                    "resultado": "victoria",
                    "ficha_ganadora": "X",
                    "jugadores": {
                        "X": "jugador_ana@localhost",
                        "O": "jugador_luis@localhost"
                    },
                    "turnos": 7,
                    "tablero_final": ["X","O","X","O","X","O","","","X"]
                }
            ],
            "log": [
                {
                    "ts": "09:28:30",
                    "tipo": "informe",
                    "de": "tablero_mesa1",
                    "detalle": "Victoria de X (ana) contra luis · 7 turnos"
                }
            ]
        }
    ],
    "timestamp": "12:34:56"
}
```

#### Verificaciones con curl

```bash
# El endpoint principal devuelve HTML
curl -s -o /dev/null -w "%{http_code} %{content_type}" \
    http://localhost:10090/supervisor
# Esperado: 200 text/html

# El endpoint API devuelve JSON
curl -s -o /dev/null -w "%{http_code} %{content_type}" \
    http://localhost:10090/supervisor/api/state
# Esperado: 200 application/json

# Los estáticos son accesibles
curl -s -o /dev/null -w "%{http_code}" \
    http://localhost:10090/supervisor/static/supervisor.css
# Esperado: 200

curl -s -o /dev/null -w "%{http_code}" \
    http://localhost:10090/supervisor/static/supervisor.js
# Esperado: 200
```

---

## 7. Datos de prueba

### Informe de victoria

```python
INFORME_VICTORIA = {
    "action": "game-report",
    "result": "win",
    "winner": "X",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 7,
    "board": ["X", "O", "X", "O", "X", "O", "", "", "X"],
    "ts": "09:28:30",
}
```

### Informe de empate

```python
INFORME_EMPATE = {
    "action": "game-report",
    "result": "draw",
    "winner": None,
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 9,
    "board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
    "ts": "09:35:12",
}
```

### Informe de partida abortada

```python
INFORME_ABORTADA = {
    "action": "game-report",
    "result": "aborted",
    "winner": None,
    "reason": "both-timeout",
    "players": {
        "X": "jugador_ana@localhost",
        "O": "jugador_luis@localhost",
    },
    "turns": 2,
    "board": ["X", "", "", "", "O", "", "", "", ""],
    "ts": "10:12:45",
}
```

### Ocupantes de ejemplo

```python
OCUPANTES_EJEMPLO = [
    {"nick": "supervisor", "jid": "supervisor@localhost",
     "rol": "supervisor", "estado": "online"},
    {"nick": "tablero_mesa1", "jid": "tablero_mesa1@localhost",
     "rol": "tablero", "estado": "finished"},
    {"nick": "jugador_ana", "jid": "jugador_ana@localhost",
     "rol": "jugador", "estado": "online"},
    {"nick": "jugador_luis", "jid": "jugador_luis@localhost",
     "rol": "jugador", "estado": "online"},
]
```

### Registro de eventos de ejemplo

```python
LOG_EJEMPLO = [
    {"ts": "09:28:30", "tipo": "informe", "de": "tablero_mesa1",
     "detalle": "Victoria de X (ana) contra luis · 7 turnos"},
    {"ts": "09:25:00", "tipo": "entrada", "de": "jugador_luis",
     "detalle": "Se ha unido a la sala (jugador)"},
    {"ts": "09:24:50", "tipo": "entrada", "de": "jugador_ana",
     "detalle": "Se ha unido a la sala (jugador)"},
]
```

---

## 8. Convenciones y patrones de test

### Nombres de tests

- Usar nombres descriptivos en español (el proyecto es para docencia).
- Patrón: `test_<componente>_<comportamiento_esperado>`.
- Ejemplo: `test_mapear_resultado_win_a_victoria`.

### Estructura de ficheros

```
tests/
├── __init__.py
├── test_ontologia.py                 ← 60 tests — ontología runtime
├── test_almacen_supervisor.py        ← 28 tests — persistencia SQLite
├── test_supervisor_behaviours.py     ← 30 tests — funciones auxiliares y FSM
├── test_agente_supervisor.py         ← 33 tests — métodos del agente y presencia
├── test_supervisor_handlers.py       ← 25 tests — conversión de datos y rutas HTTP
├── test_creacion_salas.py            ← 13 tests — creación de salas MUC por modo
├── test_integracion_supervisor.py    ← 23 tests — integración con XMPP
└── TESTING_SUPERVISOR.md             ← Este documento
```

### Imports con pytest-asyncio

```python
import pytest

# Para tests asíncronos (handlers aiohttp)
@pytest.mark.asyncio
async def test_ejemplo_asincrono():
    ...

# Para el test client de aiohttp
@pytest.fixture
async def cliente_web(aiohttp_client):
    ...
```

### Configuración de pytest

Si se necesita, crear `pytest.ini` o añadir a `pyproject.toml`:

```ini
[pytest]
asyncio_mode = auto
timeout = 10
```

### Punto de retorno único

Siguiendo las convenciones del proyecto, los tests **no** deben usar
múltiples `return` tempranos.  Usar `assert` directamente para
verificar resultados.

### Prohibición de `break`

Igualmente, si se itera en un test, usar variables booleanas o
condiciones del bucle en lugar de `break`.

---

## 9. Resolución de problemas

### Error: `ModuleNotFoundError: No module named 'jsonschema'`

```bash
pip install jsonschema
```

### Error: `ModuleNotFoundError: No module named 'spade'`

```bash
pip install spade
```

Los tests de los manejadores web **no requieren SPADE** si se usa el
`AgenteMock` descrito en la sección 4.1.

### Error: `ModuleNotFoundError: No module named 'aiohttp'`

```bash
pip install aiohttp
```

### El panel no carga estilos o JavaScript

Verificar que las rutas estáticas son correctas:

- CSS: `/supervisor/static/supervisor.css`
- JS: `/supervisor/static/supervisor.js`
- Los ficheros deben estar en `web/static/`.

### La ruta `/supervisor/api/state` devuelve error 500

Causas posibles:

1. El atributo `request.app["agente"]` no está inyectado.
2. El agente no tiene los atributos `muc_sala`, `ocupantes_sala`,
   `informes_recibidos` o `log_eventos`.
3. Un informe tiene un formato inesperado (falta `players`, `result`, etc.).

### El reloj no se actualiza

Verificar que `supervisor.js` se carga correctamente (sin errores
en la consola del navegador).

### Los temas no persisten al recargar

Verificar que `localStorage` no está bloqueado en el navegador.
El tema se guarda con la clave `"sv-tema"`.
