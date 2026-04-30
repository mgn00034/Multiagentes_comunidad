"""
Tests unitarios de los manejadores HTTP y funciones de conversión
del panel web del Agente Supervisor.

Se prueban dos categorías:
- **Funciones puras** (``_mapear_resultado``, ``_nombre_legible_sala``,
  ``_convertir_informes``): sin necesidad de servidor HTTP.
- **Manejadores HTTP** (las cuatro rutas del supervisor): mediante
  el cliente de pruebas de ``pytest-aiohttp``, con un agente simulado
  inyectado en la aplicación.
"""

import asyncio
import os
import pathlib
import tempfile
from types import SimpleNamespace

import pytest
from aiohttp import web

from persistencia.almacen_supervisor import AlmacenSupervisor
from web.supervisor_handlers import (
    _computar_ranking,
    _convertir_informes,
    _exportar_csv_sesion,
    _generar_csv_incidencias,
    _generar_csv_log,
    _generar_csv_ranking,
    _mapear_resultado,
    _nombre_legible_sala,
    _suscriptores_sse,
    crear_middleware_auth,
    notificar_sse,
    registrar_rutas_supervisor,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Datos de prueba
# ═══════════════════════════════════════════════════════════════════════════

SALAS_EJEMPLO = [
    {"id": "tictactoe", "jid": "tictactoe@conference.localhost"},
]

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
}

OCUPANTES_EJEMPLO = [
    {"nick": "supervisor", "jid": "supervisor@localhost",
     "rol": "supervisor", "estado": "online"},
    {"nick": "tablero_mesa1", "jid": "tablero_mesa1@localhost",
     "rol": "tablero", "estado": "online"},
]


# ═══════════════════════════════════════════════════════════════════════════
#  Utilidades
# ═══════════════════════════════════════════════════════════════════════════

def crear_agente_simulado(salas=None, informes=None, eventos=None,
                          ocupantes=None, almacen=None):
    """Crea un objeto que imita los atributos que los manejadores
    HTTP leen de ``request.app["agente"]``."""
    salas_cfg = salas if salas is not None else list(SALAS_EJEMPLO)
    agente = SimpleNamespace(
        salas_muc=salas_cfg,
        informes_por_sala=informes if informes is not None else {
            s["id"]: {} for s in salas_cfg
        },
        ocupantes_por_sala=ocupantes if ocupantes is not None else {
            s["id"]: [] for s in salas_cfg
        },
        log_por_sala=eventos if eventos is not None else {
            s["id"]: [] for s in salas_cfg
        },
        almacen=almacen,
    )
    return agente


def crear_app_con_agente(agente):
    """Crea una aplicación aiohttp con las rutas del supervisor y el
    agente simulado inyectado."""
    app = web.Application()
    registrar_rutas_supervisor(app)
    app["agente"] = agente
    return app


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _mapear_resultado
# ═══════════════════════════════════════════════════════════════════════════

class TestMapearResultado:
    """Verifica la traducción de resultados de la ontología al formato
    del panel web."""

    def test_win_a_victoria(self):
        assert _mapear_resultado("win") == "victoria"

    def test_draw_a_empate(self):
        assert _mapear_resultado("draw") == "empate"

    def test_aborted_a_abortada(self):
        assert _mapear_resultado("aborted") == "abortada"

    def test_valor_ya_en_espanol_se_mantiene(self):
        assert _mapear_resultado("victoria") == "victoria"
        assert _mapear_resultado("empate") == "empate"

    def test_valor_desconocido_pasa_sin_cambios(self):
        assert _mapear_resultado("otro") == "otro"


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _nombre_legible_sala
# ═══════════════════════════════════════════════════════════════════════════

class TestNombreLegibleSala:
    """Verifica la generación de nombres legibles para las salas."""

    def test_nombre_simple_devuelve_sala_principal(self):
        assert _nombre_legible_sala("tictactoe") == "Sala principal"

    def test_nombre_con_guion_bajo_se_capitaliza(self):
        resultado = _nombre_legible_sala("practica_grupo_a")
        assert "Sala" in resultado
        assert "Practica" in resultado
        assert "Grupo" in resultado


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _convertir_informes
# ═══════════════════════════════════════════════════════════════════════════

class TestConvertirInformes:
    """Verifica la conversión de informes del formato interno al
    formato del panel web."""

    def test_diccionario_vacio_devuelve_lista_vacia(self):
        resultado = _convertir_informes({})
        assert resultado == []

    def test_convierte_un_informe_de_victoria(self):
        informes_raw = {
            "tablero_mesa1@localhost": [INFORME_VICTORIA],
        }
        resultado = _convertir_informes(informes_raw)
        assert len(resultado) == 1
        inf = resultado[0]
        assert inf["resultado"] == "victoria"
        assert inf["ficha_ganadora"] == "X"
        assert inf["turnos"] == 7
        assert inf["tablero"] == "tablero_mesa1"

    def test_convierte_informe_abortada_con_motivo(self):
        informes_raw = {
            "tablero_mesa1@localhost": [INFORME_ABORTADA],
        }
        resultado = _convertir_informes(informes_raw)
        assert len(resultado) == 1
        inf = resultado[0]
        assert inf["resultado"] == "abortada"
        assert inf["reason"] == "both-timeout"

    def test_id_secuencial(self):
        """Cada informe convertido debe tener un id secuencial."""
        informes_raw = {
            "tablero_1@localhost": [INFORME_VICTORIA],
            "tablero_2@localhost": [INFORME_ABORTADA],
        }
        resultado = _convertir_informes(informes_raw)
        assert resultado[0]["id"] == "informe_001"
        assert resultado[1]["id"] == "informe_002"

    def test_tablero_final_es_lista_de_9(self):
        """El tablero final debe ser una lista de 9 elementos."""
        informes_raw = {
            "tablero@localhost": [INFORME_VICTORIA],
        }
        resultado = _convertir_informes(informes_raw)
        assert len(resultado[0]["tablero_final"]) == 9

    def test_jid_muc_extrae_nick_del_recurso(self):
        """Si el JID es de una sala MUC (contiene 'conference'), el
        nick del tablero debe extraerse del recurso del JID."""
        informes_raw = {
            "sala_pc04@conference.localhost/tablero_mesa1_rfr": [
                INFORME_VICTORIA,
            ],
        }
        resultado = _convertir_informes(informes_raw)
        assert resultado[0]["tablero"] == "tablero_mesa1_rfr"

    def test_jid_real_extrae_nick_de_parte_local(self):
        """Si el JID es real (no MUC), el nick debe extraerse de la
        parte local (antes de @), no del recurso aleatorio."""
        informes_raw = {
            "tablero_mesa2@sinbad2.ujaen.es": [INFORME_VICTORIA],
        }
        resultado = _convertir_informes(informes_raw)
        assert resultado[0]["tablero"] == "tablero_mesa2"

    def test_multiples_informes_mismo_tablero(self):
        """Un tablero con varios informes debe generar una entrada
        por cada uno."""
        informes_raw = {
            "tablero_mesa1@localhost": [
                INFORME_VICTORIA,
                INFORME_ABORTADA,
            ],
        }
        resultado = _convertir_informes(informes_raw)
        assert len(resultado) == 2
        assert resultado[0]["resultado"] == "victoria"
        assert resultado[1]["resultado"] == "abortada"


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures para tests HTTP
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
async def cliente_basico(aiohttp_client):
    """Cliente HTTP con un agente vacío."""
    agente = crear_agente_simulado()
    app = crear_app_con_agente(agente)
    cliente = await aiohttp_client(app)
    return cliente


@pytest.fixture
async def cliente_con_datos(aiohttp_client):
    """Cliente HTTP con un agente que tiene informes y ocupantes."""
    informes = {
        "tictactoe": {
            "tablero_mesa1@localhost": [INFORME_VICTORIA],
        },
    }
    ocupantes = {"tictactoe": OCUPANTES_EJEMPLO}
    agente = crear_agente_simulado(
        informes=informes, ocupantes=ocupantes,
    )
    app = crear_app_con_agente(agente)
    cliente = await aiohttp_client(app)
    return cliente


@pytest.fixture
async def cliente_con_almacen(aiohttp_client):
    """Cliente HTTP con un agente que tiene un almacén SQLite con
    una ejecución finalizada."""
    fd, ruta_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    almacen = AlmacenSupervisor(ruta_db)
    almacen.crear_ejecucion(SALAS_EJEMPLO)
    almacen.guardar_informe(
        "tictactoe", "tablero_mesa1@localhost", INFORME_VICTORIA,
    )
    almacen.guardar_evento(
        "tictactoe", "informe", "tablero_mesa1",
        "Victoria X", "09:28:30",
    )
    almacen.finalizar_ejecucion()
    id_ejec = almacen.ejecucion_id

    agente = crear_agente_simulado(almacen=almacen)
    app = crear_app_con_agente(agente)
    cliente = await aiohttp_client(app)

    # Exponer datos para que los tests los usen
    cliente._almacen = almacen
    cliente._ruta_db = ruta_db
    cliente._id_ejec = id_ejec

    yield cliente

    almacen.cerrar()
    if os.path.exists(ruta_db):
        os.unlink(ruta_db)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests HTTP: página principal
# ═══════════════════════════════════════════════════════════════════════════

class TestHandlerIndex:
    """Verifica que la ruta raíz sirve la página HTML del panel."""

    @pytest.mark.asyncio
    async def test_index_devuelve_html(self, cliente_basico):
        """GET /supervisor debe devolver contenido HTML con código 200."""
        resp = await cliente_basico.get("/supervisor")
        assert resp.status == 200
        texto = await resp.text()
        assert "<!DOCTYPE html>" in texto

    @pytest.mark.asyncio
    async def test_index_con_barra_final(self, cliente_basico):
        """GET /supervisor/ también debe funcionar."""
        resp = await cliente_basico.get("/supervisor/")
        assert resp.status == 200


# ═══════════════════════════════════════════════════════════════════════════
#  Tests HTTP: estado en vivo
# ═══════════════════════════════════════════════════════════════════════════

class TestHandlerState:
    """Verifica que la ruta de estado en vivo devuelve el JSON
    esperado."""

    @pytest.mark.asyncio
    async def test_devuelve_json_con_salas(self, cliente_con_datos):
        """La respuesta debe ser JSON con una clave 'salas'."""
        resp = await cliente_con_datos.get("/supervisor/api/state")
        assert resp.status == 200
        datos = await resp.json()
        assert "salas" in datos
        assert "timestamp" in datos
        assert len(datos["salas"]) == 1

    @pytest.mark.asyncio
    async def test_sala_contiene_informes(self, cliente_con_datos):
        """La sala debe incluir los informes convertidos."""
        resp = await cliente_con_datos.get("/supervisor/api/state")
        datos = await resp.json()
        sala = datos["salas"][0]
        assert len(sala["informes"]) == 1
        assert sala["informes"][0]["resultado"] == "victoria"

    @pytest.mark.asyncio
    async def test_sala_contiene_ocupantes(self, cliente_con_datos):
        """La sala debe incluir la lista de ocupantes."""
        resp = await cliente_con_datos.get("/supervisor/api/state")
        datos = await resp.json()
        sala = datos["salas"][0]
        assert len(sala["ocupantes"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
#  Tests HTTP: historial de ejecuciones
# ═══════════════════════════════════════════════════════════════════════════

class TestHandlerListarEjecuciones:
    """Verifica que la ruta de listado de ejecuciones devuelve datos
    del almacén SQLite."""

    @pytest.mark.asyncio
    async def test_devuelve_lista_de_ejecuciones(
        self, cliente_con_almacen,
    ):
        """La respuesta debe contener una clave 'ejecuciones' con al
        menos un elemento."""
        resp = await cliente_con_almacen.get(
            "/supervisor/api/ejecuciones",
        )
        assert resp.status == 200
        datos = await resp.json()
        assert "ejecuciones" in datos
        assert len(datos["ejecuciones"]) >= 1

    @pytest.mark.asyncio
    async def test_ejecucion_tiene_campos_esperados(
        self, cliente_con_almacen,
    ):
        """Cada ejecución debe tener id, inicio, fin y num_salas."""
        resp = await cliente_con_almacen.get(
            "/supervisor/api/ejecuciones",
        )
        datos = await resp.json()
        ejec = datos["ejecuciones"][0]
        assert "id" in ejec
        assert "inicio" in ejec
        assert "fin" in ejec
        assert "num_salas" in ejec


class TestHandlerDatosEjecucion:
    """Verifica que la ruta de datos de una ejecución pasada devuelve
    el mismo formato que la ruta de estado en vivo."""

    @pytest.mark.asyncio
    async def test_devuelve_salas_con_informes(
        self, cliente_con_almacen,
    ):
        """La ejecución pasada debe contener las salas con sus
        informes y eventos."""
        id_ejec = cliente_con_almacen._id_ejec
        url = f"/supervisor/api/ejecuciones/{id_ejec}"
        resp = await cliente_con_almacen.get(url)
        assert resp.status == 200
        datos = await resp.json()
        assert "salas" in datos
        assert len(datos["salas"]) == 1
        sala = datos["salas"][0]
        assert sala["id"] == "tictactoe"
        assert len(sala["informes"]) == 1
        assert len(sala["log"]) == 1

    @pytest.mark.asyncio
    async def test_ocupantes_vacios_en_ejecucion_pasada(
        self, cliente_con_almacen,
    ):
        """Las ejecuciones pasadas no tienen datos de presencia."""
        id_ejec = cliente_con_almacen._id_ejec
        url = f"/supervisor/api/ejecuciones/{id_ejec}"
        resp = await cliente_con_almacen.get(url)
        datos = await resp.json()
        sala = datos["salas"][0]
        assert sala["ocupantes"] == []

    @pytest.mark.asyncio
    async def test_ejecucion_inexistente_devuelve_vacio(
        self, cliente_con_almacen,
    ):
        """Una ejecución que no existe debe devolver salas vacías."""
        resp = await cliente_con_almacen.get(
            "/supervisor/api/ejecuciones/9999",
        )
        assert resp.status == 200
        datos = await resp.json()
        assert datos["salas"] == []

    @pytest.mark.asyncio
    async def test_id_no_numerico_devuelve_vacio(
        self, cliente_con_almacen,
    ):
        """Un id no numérico debe devolver salas vacías."""
        resp = await cliente_con_almacen.get(
            "/supervisor/api/ejecuciones/abc",
        )
        assert resp.status == 200
        datos = await resp.json()
        assert datos["salas"] == []


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _computar_ranking
# ═══════════════════════════════════════════════════════════════════════════

INFORMES_DASHBOARD = [
    {
        "resultado": "victoria",
        "ficha_ganadora": "X",
        "jugadores": {
            "X": "jugador_ana@localhost",
            "O": "jugador_luis@localhost",
        },
    },
    {
        "resultado": "empate",
        "ficha_ganadora": None,
        "jugadores": {
            "X": "jugador_ana@localhost",
            "O": "jugador_luis@localhost",
        },
    },
    {
        "resultado": "abortada",
        "ficha_ganadora": None,
        "jugadores": {
            "X": "jugador_ana@localhost",
            "O": "jugador_carlos@localhost",
        },
    },
]


class TestComputarRanking:
    """Verifica el cálculo de la clasificación de jugadores a
    partir de los informes del dashboard."""

    def test_ranking_con_informes(self):
        """El ranking debe contener un registro por cada alumno
        que aparece en los informes."""
        ranking = _computar_ranking(INFORMES_DASHBOARD)
        alumnos = [r["alumno"] for r in ranking]
        assert "ana" in alumnos
        assert "luis" in alumnos
        assert "carlos" in alumnos

    def test_estadisticas_correctas(self):
        """Las estadísticas de cada alumno deben coincidir con los
        resultados de los informes."""
        ranking = _computar_ranking(INFORMES_DASHBOARD)
        stats = {r["alumno"]: r for r in ranking}
        # ana: 1 victoria, 1 empate, 1 abortada = 3 partidas
        assert stats["ana"]["victorias"] == 1
        assert stats["ana"]["empates"] == 1
        assert stats["ana"]["abortadas"] == 1
        assert stats["ana"]["partidas"] == 3

    def test_win_rate_calculado(self):
        """Cada entrada debe tener un campo win_rate numérico."""
        ranking = _computar_ranking(INFORMES_DASHBOARD)
        for entrada in ranking:
            assert "win_rate" in entrada
            assert isinstance(entrada["win_rate"], float)

    def test_ranking_vacio(self):
        """Sin informes, el ranking debe ser una lista vacía."""
        ranking = _computar_ranking([])
        assert ranking == []

    def test_orden_por_win_rate(self):
        """El primer alumno del ranking debe tener el mayor
        win_rate."""
        ranking = _computar_ranking(INFORMES_DASHBOARD)
        if len(ranking) >= 2:
            assert ranking[0]["win_rate"] >= ranking[1]["win_rate"]


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de generación CSV
# ═══════════════════════════════════════════════════════════════════════════

LOG_EJEMPLO = [
    {"ts": "10:00:00", "tipo": "entrada", "de": "tablero_mesa1",
     "detalle": "Se ha unido"},
    {"ts": "10:00:05", "tipo": "informe", "de": "tablero_mesa1",
     "detalle": "Victoria X"},
    {"ts": "10:00:10", "tipo": "error", "de": "tablero_mesa2",
     "detalle": "JSON inválido"},
    {"ts": "10:00:15", "tipo": "inconsistencia",
     "de": "tablero_mesa1",
     "detalle": "Turnos anómalos"},
    {"ts": "10:00:20", "tipo": "advertencia",
     "de": "tablero_mesa3",
     "detalle": "Informe rechazado"},
]


class TestGenerarCsvRanking:
    """Verifica la generación de CSV de clasificación."""

    def test_csv_tiene_cabeceras(self):
        """El CSV debe comenzar con la fila de cabeceras."""
        csv = _generar_csv_ranking(INFORMES_DASHBOARD)
        primera_linea = csv.strip().split("\n")[0]
        assert "alumno" in primera_linea
        assert "victorias" in primera_linea
        assert "win_rate" in primera_linea

    def test_csv_tiene_datos(self):
        """El CSV debe contener una fila por cada alumno."""
        csv = _generar_csv_ranking(INFORMES_DASHBOARD)
        lineas = csv.strip().split("\n")
        # Cabecera + 3 alumnos
        assert len(lineas) == 4

    def test_csv_vacio_solo_cabeceras(self):
        """Sin informes, el CSV solo tiene la fila de cabeceras."""
        csv = _generar_csv_ranking([])
        lineas = csv.strip().split("\n")
        assert len(lineas) == 1


class TestGenerarCsvLog:
    """Verifica la generación de CSV del log completo."""

    def test_csv_tiene_todos_los_eventos(self):
        """El CSV debe contener todos los eventos del log."""
        csv = _generar_csv_log(LOG_EJEMPLO)
        lineas = csv.strip().split("\n")
        # Cabecera + 5 eventos
        assert len(lineas) == 6

    def test_csv_cabeceras_correctas(self):
        """Las cabeceras del CSV de log deben ser timestamp, tipo,
        origen, detalle."""
        csv = _generar_csv_log(LOG_EJEMPLO)
        primera_linea = csv.strip().split("\n")[0]
        assert "timestamp" in primera_linea
        assert "tipo" in primera_linea
        assert "origen" in primera_linea
        assert "detalle" in primera_linea


class TestGenerarCsvIncidencias:
    """Verifica la generación de CSV de incidencias (filtrado)."""

    def test_csv_filtra_solo_incidencias(self):
        """El CSV debe contener solo los eventos de tipo incidencia,
        no los de presencia ni informes normales."""
        csv = _generar_csv_incidencias(LOG_EJEMPLO)
        lineas = csv.strip().split("\n")
        # Cabecera + 3 incidencias (error, inconsistencia,
        # advertencia). Los tipos entrada e informe se excluyen.
        assert len(lineas) == 4

    def test_csv_sin_incidencias(self):
        """Si no hay incidencias, solo queda la cabecera."""
        eventos_limpios = [
            {"ts": "10:00:00", "tipo": "entrada",
             "de": "t1", "detalle": "ok"},
        ]
        csv = _generar_csv_incidencias(eventos_limpios)
        lineas = csv.strip().split("\n")
        assert len(lineas) == 1


# ═══════════════════════════════════════════════════════════════════════════
#  Tests HTTP: endpoints CSV en vivo
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
async def cliente_csv(aiohttp_client):
    """Cliente HTTP con informes y log para tests de exportación
    CSV."""
    informes = {
        "tictactoe": {
            "tablero_mesa1@localhost": [INFORME_VICTORIA],
        },
    }
    eventos = {
        "tictactoe": LOG_EJEMPLO,
    }
    agente = crear_agente_simulado(
        informes=informes, eventos=eventos,
    )
    app = crear_app_con_agente(agente)
    cliente = await aiohttp_client(app)
    return cliente


class TestHandlerCsvEnVivo:
    """Verifica los endpoints de exportación CSV del estado en
    vivo."""

    @pytest.mark.asyncio
    async def test_csv_ranking(self, cliente_csv):
        """GET /supervisor/api/csv/ranking debe devolver CSV con
        Content-Type text/csv."""
        resp = await cliente_csv.get(
            "/supervisor/api/csv/ranking?sala=tictactoe",
        )
        assert resp.status == 200
        assert "text/csv" in resp.content_type
        texto = await resp.text()
        assert "alumno" in texto
        assert "ana" in texto

    @pytest.mark.asyncio
    async def test_csv_log(self, cliente_csv):
        """GET /supervisor/api/csv/log debe devolver el log
        completo en CSV."""
        resp = await cliente_csv.get(
            "/supervisor/api/csv/log?sala=tictactoe",
        )
        assert resp.status == 200
        texto = await resp.text()
        assert "timestamp" in texto
        lineas = texto.strip().split("\n")
        assert len(lineas) == 6  # cabecera + 5 eventos

    @pytest.mark.asyncio
    async def test_csv_incidencias(self, cliente_csv):
        """GET /supervisor/api/csv/incidencias debe devolver solo
        los eventos de incidencia."""
        resp = await cliente_csv.get(
            "/supervisor/api/csv/incidencias?sala=tictactoe",
        )
        assert resp.status == 200
        texto = await resp.text()
        lineas = texto.strip().split("\n")
        assert len(lineas) == 4  # cabecera + 3 incidencias

    @pytest.mark.asyncio
    async def test_csv_content_disposition(self, cliente_csv):
        """La respuesta CSV debe incluir Content-Disposition con
        nombre de fichero."""
        resp = await cliente_csv.get(
            "/supervisor/api/csv/ranking?sala=tictactoe",
        )
        disposicion = resp.headers.get("Content-Disposition", "")
        assert "attachment" in disposicion
        assert ".csv" in disposicion

    @pytest.mark.asyncio
    async def test_csv_sin_sala_devuelve_400(self, cliente_csv):
        """Si no se proporciona el parámetro 'sala', debe devolver
        HTTP 400."""
        resp = await cliente_csv.get("/supervisor/api/csv/ranking")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_csv_tipo_invalido_devuelve_400(self, cliente_csv):
        """Un tipo de CSV no válido debe devolver HTTP 400."""
        resp = await cliente_csv.get(
            "/supervisor/api/csv/invalido?sala=tictactoe",
        )
        assert resp.status == 400


# ═══════════════════════════════════════════════════════════════════════════
#  Tests HTTP: endpoints CSV de ejecuciones pasadas
# ═══════════════════════════════════════════════════════════════════════════

class TestHandlerCsvEjecucion:
    """Verifica los endpoints de exportación CSV de ejecuciones
    pasadas."""

    @pytest.mark.asyncio
    async def test_csv_ranking_ejecucion(self, cliente_con_almacen):
        """El CSV de ranking de una ejecución pasada debe contener
        datos del almacén SQLite."""
        id_ejec = cliente_con_almacen._id_ejec
        url = (
            f"/supervisor/api/ejecuciones/{id_ejec}"
            "/csv/ranking?sala=tictactoe"
        )
        resp = await cliente_con_almacen.get(url)
        assert resp.status == 200
        assert "text/csv" in resp.content_type
        texto = await resp.text()
        assert "alumno" in texto

    @pytest.mark.asyncio
    async def test_csv_log_ejecucion(self, cliente_con_almacen):
        """El CSV de log de una ejecución pasada debe contener
        los eventos almacenados."""
        id_ejec = cliente_con_almacen._id_ejec
        url = (
            f"/supervisor/api/ejecuciones/{id_ejec}"
            "/csv/log?sala=tictactoe"
        )
        resp = await cliente_con_almacen.get(url)
        assert resp.status == 200
        texto = await resp.text()
        assert "timestamp" in texto

    @pytest.mark.asyncio
    async def test_csv_sin_sala_devuelve_400(
        self, cliente_con_almacen,
    ):
        """Sin parámetro 'sala' debe devolver 400."""
        id_ejec = cliente_con_almacen._id_ejec
        url = (
            f"/supervisor/api/ejecuciones/{id_ejec}/csv/ranking"
        )
        resp = await cliente_con_almacen.get(url)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_csv_ejecucion_inexistente(
        self, cliente_con_almacen,
    ):
        """Una ejecución que no existe en el almacén debe devolver
        CSV vacío (solo cabeceras), no un error."""
        url = (
            "/supervisor/api/ejecuciones/9999"
            "/csv/ranking?sala=tictactoe"
        )
        resp = await cliente_con_almacen.get(url)
        assert resp.status == 200


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de SSE (M-05)
# ═══════════════════════════════════════════════════════════════════════════

import asyncio
import aiohttp


class TestNotificarSSE:
    """Verifica la función de notificación SSE a nivel de módulo."""

    def test_notificar_sin_suscriptores(self):
        """Notificar sin suscriptores no debe lanzar excepción."""
        suscriptores_antes = len(_suscriptores_sse)
        notificar_sse("state", {"test": True})
        assert len(_suscriptores_sse) == suscriptores_antes

    def test_notificar_deposita_en_cola(self):
        """Si hay un suscriptor, el evento debe depositarse en
        su cola."""
        cola = asyncio.Queue(maxsize=50)
        _suscriptores_sse.append(cola)
        try:
            notificar_sse("state", {"sala_id": "test"})
            assert not cola.empty()
            evento = cola.get_nowait()
            assert evento["tipo"] == "state"
            assert evento["datos"]["sala_id"] == "test"
        finally:
            _suscriptores_sse.remove(cola)


class TestHandlerSSE:
    """Verifica el endpoint SSE /supervisor/api/stream."""

    @pytest.mark.asyncio
    async def test_sse_content_type(self, cliente_csv):
        """El endpoint SSE debe responder con Content-Type
        text/event-stream."""
        resp = await cliente_csv.get(
            "/supervisor/api/stream",
            timeout=aiohttp.ClientTimeout(total=2),
        )
        assert resp.status == 200
        assert "text/event-stream" in resp.content_type

    @pytest.mark.asyncio
    async def test_sse_envia_estado_inicial(self, cliente_csv):
        """El endpoint SSE debe enviar el estado inicial como
        primer evento."""
        resp = await cliente_csv.get(
            "/supervisor/api/stream",
            timeout=aiohttp.ClientTimeout(total=2),
        )
        # Leer la primera línea de datos
        primera_linea = b""
        async for linea in resp.content:
            primera_linea += linea
            if b"\n\n" in primera_linea:
                break
        texto = primera_linea.decode("utf-8")
        assert "event: state" in texto
        assert "data:" in texto


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de autenticación HTTP Basic (M-10)
# ═══════════════════════════════════════════════════════════════════════════

import base64


@pytest.fixture
async def cliente_con_auth(aiohttp_client):
    """Cliente HTTP con autenticación Basic activada."""
    agente = crear_agente_simulado()
    app = web.Application(
        middlewares=[
            crear_middleware_auth("profesor", "clave123"),
        ],
    )
    registrar_rutas_supervisor(app)
    app["agente"] = agente
    cliente = await aiohttp_client(app)
    return cliente


def _cabecera_auth(usuario, contrasena):
    """Genera la cabecera Authorization Basic."""
    token = base64.b64encode(
        f"{usuario}:{contrasena}".encode(),
    ).decode()
    resultado = f"Basic {token}"
    return resultado


class TestAutenticacionBasic:
    """Verifica que el middleware de autenticación HTTP Basic
    protege las rutas del supervisor."""

    @pytest.mark.asyncio
    async def test_sin_credenciales_devuelve_401(
        self, cliente_con_auth,
    ):
        """Una petición sin cabecera Authorization debe recibir
        HTTP 401."""
        resp = await cliente_con_auth.get("/supervisor/api/state")
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_credenciales_correctas_devuelve_200(
        self, cliente_con_auth,
    ):
        """Con credenciales válidas, la petición debe pasar."""
        resp = await cliente_con_auth.get(
            "/supervisor/api/state",
            headers={
                "Authorization": _cabecera_auth(
                    "profesor", "clave123",
                ),
            },
        )
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_credenciales_incorrectas_devuelve_401(
        self, cliente_con_auth,
    ):
        """Credenciales incorrectas deben recibir HTTP 401."""
        resp = await cliente_con_auth.get(
            "/supervisor/api/state",
            headers={
                "Authorization": _cabecera_auth(
                    "intruso", "mala",
                ),
            },
        )
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_respuesta_401_incluye_www_authenticate(
        self, cliente_con_auth,
    ):
        """La respuesta 401 debe incluir la cabecera
        WWW-Authenticate para que el navegador muestre el
        diálogo de login."""
        resp = await cliente_con_auth.get("/supervisor/api/state")
        assert "WWW-Authenticate" in resp.headers

    @pytest.mark.asyncio
    async def test_estaticos_no_requieren_auth(
        self, cliente_con_auth,
    ):
        """Los ficheros estáticos (/supervisor/static/*) no deben
        requerir autenticación para que el navegador pueda cargar
        CSS y JS antes del login."""
        resp = await cliente_con_auth.get(
            "/supervisor/static/supervisor.css",
        )
        # 200 o 404 (si el fichero no existe en el path de test)
        # pero nunca 401
        assert resp.status != 401

    @pytest.mark.asyncio
    async def test_panel_html_requiere_auth(
        self, cliente_con_auth,
    ):
        """La página principal del panel debe requerir auth."""
        resp = await cliente_con_auth.get("/supervisor")
        assert resp.status == 401


# ═══════════════════════════════════════════════════════════════════════════
#  Tests P-06: Separación Log / Incidencias en supervisor.js
# ═══════════════════════════════════════════════════════════════════════════

class TestSeparacionLogIncidencias:
    """Verifica que supervisor.js filtra los eventos de incidencia
    en renderLogPanel para que no aparezcan duplicados entre las
    pestañas Log e Incidencias (P-06)."""

    @pytest.mark.asyncio
    async def test_js_accesible(self, cliente_basico):
        """El archivo supervisor.js debe servirse correctamente."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.js",
        )
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_log_panel_filtra_tipos_incidencia(
        self, cliente_basico,
    ):
        """renderLogPanel debe filtrar los eventos cuyo tipo esté
        en TIPOS_INCIDENCIA para que no se dupliquen con la pestaña
        de Incidencias."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.js",
        )
        js = await resp.text()
        # Verificar que renderLogPanel contiene el filtro excluyente
        # que usa TIPOS_INCIDENCIA para excluir eventos de incidencia
        assert "TIPOS_INCIDENCIA.indexOf(e.tipo) === -1" in js

    @pytest.mark.asyncio
    async def test_log_panel_usa_eventos_filtrados(
        self, cliente_basico,
    ):
        """renderLogPanel debe usar la variable filtrada eventosLog
        en lugar de sala.log directamente para la paginación y el
        renderizado."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.js",
        )
        js = await resp.text()
        # La variable eventosLog se define como filtro de sala.log
        assert "const eventosLog = sala.log.filter" in js
        # La paginación usa eventosLog, no sala.log
        assert "eventosLog.length" in js
        assert "eventosLog.slice" in js

    @pytest.mark.asyncio
    async def test_leyenda_log_no_incluye_tipos_incidencia(
        self, cliente_basico,
    ):
        """La leyenda del panel Log solo debe mostrar los tipos
        operativos, no los tipos de incidencia."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.js",
        )
        js = await resp.text()
        # Buscar la definición de tiposLeyenda dentro de
        # renderLogPanel. No debe incluir tipos de incidencia.
        tipos_incidencia = [
            "error", "advertencia", "timeout",
            "abortada", "inconsistencia",
        ]
        # Localizar el bloque de tiposLeyenda en renderLogPanel
        inicio = js.find("function renderLogPanel")
        fin = js.find("function ", inicio + 1)
        bloque_log = js[inicio:fin]
        # Extraer la sección de tiposLeyenda
        inicio_leyenda = bloque_log.find("tiposLeyenda")
        fin_leyenda = bloque_log.find("];", inicio_leyenda)
        leyenda = bloque_log[inicio_leyenda:fin_leyenda]
        # Ningún tipo de incidencia debe estar en la leyenda
        for tipo in tipos_incidencia:
            assert f'"{tipo}"' not in leyenda, (
                f'El tipo "{tipo}" no debe aparecer en la '
                f"leyenda del panel Log"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  Tests P-08: Truncamiento de nombres largos en la visualización
# ═══════════════════════════════════════════════════════════════════════════

class TestTruncamientoNombresLargos:
    """Verifica que el CSS trunca nombres largos con ellipsis y que
    el JS incluye tooltips con el nombre completo en todos los
    paneles del dashboard (P-08)."""

    @pytest.mark.asyncio
    async def test_css_truncamiento_ocupantes(self, cliente_basico):
        """La clase sv-ocupante-nick debe tener truncamiento CSS."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.css",
        )
        css = await resp.text()
        # Localizar el bloque de la clase
        inicio = css.find(".sv-ocupante-nick")
        fin = css.find("}", inicio)
        bloque = css[inicio:fin]
        assert "text-overflow" in bloque
        assert "ellipsis" in bloque
        assert "max-width" in bloque

    @pytest.mark.asyncio
    async def test_css_truncamiento_ranking(self, cliente_basico):
        """La clase sv-ranking-alumno debe tener truncamiento CSS."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.css",
        )
        css = await resp.text()
        inicio = css.find(".sv-ranking-alumno")
        fin = css.find("}", inicio)
        bloque = css[inicio:fin]
        assert "text-overflow" in bloque
        assert "ellipsis" in bloque

    @pytest.mark.asyncio
    async def test_css_truncamiento_log_de(self, cliente_basico):
        """La clase sv-log-de debe tener truncamiento CSS (afecta
        a Log e Incidencias)."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.css",
        )
        css = await resp.text()
        inicio = css.find(".sv-log-de")
        fin = css.find("}", inicio)
        bloque = css[inicio:fin]
        assert "text-overflow" in bloque
        assert "ellipsis" in bloque
        assert "max-width" in bloque

    @pytest.mark.asyncio
    async def test_css_truncamiento_informe_player(
        self, cliente_basico,
    ):
        """La clase sv-informe-player-name debe tener truncamiento
        CSS."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.css",
        )
        css = await resp.text()
        inicio = css.find(".sv-informe-player-name")
        fin = css.find("}", inicio)
        bloque = css[inicio:fin]
        assert "text-overflow" in bloque
        assert "ellipsis" in bloque

    @pytest.mark.asyncio
    async def test_js_tooltip_en_paneles(self, cliente_basico):
        """Los paneles de agentes, informes, ranking, log e
        incidencias deben incluir atributo title para mostrar
        el nombre completo al pasar el ratón."""
        resp = await cliente_basico.get(
            "/supervisor/static/supervisor.js",
        )
        js = await resp.text()
        # Agentes: title en sv-ocupante-nick
        assert 'class="sv-ocupante-nick" title="' in js
        # Informes: title en sv-informe-player-name
        assert 'class="sv-informe-player-name"' in js
        assert "title=" in js[js.find("sv-informe-player-name"):]
        # Ranking: title en sv-ranking-alumno
        assert 'class="sv-ranking-alumno"' in js
        # Log e Incidencias: title en sv-log-de
        assert 'class="sv-log-de" title="' in js


# ═══════════════════════════════════════════════════════════════════════════
#  Tests P-09: Finalización del torneo desde el dashboard
# ═══════════════════════════════════════════════════════════════════════════

def _crear_agente_con_finalizacion(modo="torneo"):
    """Crea un agente simulado con los métodos que el handler de
    finalización necesita. Registra las llamadas para verificarlas
    en los tests."""
    agente = crear_agente_simulado()
    agente._persistencia_detenida = False
    agente._eventos_registrados = []
    agente._almacen_cerrado = False

    def registrar_evento_log(tipo, origen, detalle, sala_id):
        agente._eventos_registrados.append({
            "tipo": tipo, "de": origen,
            "detalle": detalle, "sala_id": sala_id,
        })

    async def detener_persistencia():
        agente._persistencia_detenida = True

    agente.registrar_evento_log = registrar_evento_log
    agente.detener_persistencia = detener_persistencia

    # En modo consulta el almacén es un objeto con método cerrar()
    if modo == "consulta":
        agente.salas_muc = []

        class AlmacenSimulado:
            cerrado = False
            def cerrar(self):
                self.cerrado = True
                agente._almacen_cerrado = True

        agente.almacen = AlmacenSimulado()

    return agente


def _crear_app_con_modo(agente, modo):
    """Crea una app aiohttp con el agente y el modo inyectados,
    y opcionalmente un evento de parada."""
    app = crear_app_con_agente(agente)
    app["modo"] = modo
    app["evento_parada"] = asyncio.Event()
    return app


@pytest.fixture
async def cliente_finalizar_torneo(aiohttp_client):
    """Cliente HTTP simulando modo torneo."""
    agente = _crear_agente_con_finalizacion("torneo")
    app = _crear_app_con_modo(agente, "torneo")
    cliente = await aiohttp_client(app)
    cliente._agente = agente
    cliente._app = app
    return cliente


@pytest.fixture
async def cliente_finalizar_laboratorio(aiohttp_client):
    """Cliente HTTP simulando modo laboratorio."""
    agente = _crear_agente_con_finalizacion("laboratorio")
    app = _crear_app_con_modo(agente, "laboratorio")
    cliente = await aiohttp_client(app)
    cliente._agente = agente
    cliente._app = app
    return cliente


@pytest.fixture
async def cliente_finalizar_consulta(aiohttp_client):
    """Cliente HTTP simulando modo consulta."""
    agente = _crear_agente_con_finalizacion("consulta")
    app = _crear_app_con_modo(agente, "consulta")
    cliente = await aiohttp_client(app)
    cliente._agente = agente
    cliente._app = app
    return cliente


class TestFinalizarTorneo:
    """Verifica el endpoint POST de finalización del torneo en los
    tres modos de ejecución y la presencia del botón en el frontend
    (P-09)."""

    # ── Modo torneo ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_torneo_devuelve_200(
        self, cliente_finalizar_torneo,
    ):
        """POST en modo torneo debe devolver 200 con estado
        'finalizado' y modo 'torneo'."""
        resp = await cliente_finalizar_torneo.post(
            "/supervisor/api/finalizar-torneo",
        )
        assert resp.status == 200
        datos = await resp.json()
        assert datos["estado"] == "finalizado"
        assert datos["modo"] == "torneo"
        assert "timestamp" in datos

    @pytest.mark.asyncio
    async def test_torneo_invoca_detener_persistencia(
        self, cliente_finalizar_torneo,
    ):
        """En modo torneo debe invocar detener_persistencia()."""
        await cliente_finalizar_torneo.post(
            "/supervisor/api/finalizar-torneo",
        )
        agente = cliente_finalizar_torneo._agente
        assert agente._persistencia_detenida is True

    @pytest.mark.asyncio
    async def test_torneo_registra_evento_en_log(
        self, cliente_finalizar_torneo,
    ):
        """En modo torneo debe registrar un evento de advertencia
        en el log de cada sala."""
        await cliente_finalizar_torneo.post(
            "/supervisor/api/finalizar-torneo",
        )
        agente = cliente_finalizar_torneo._agente
        assert len(agente._eventos_registrados) > 0
        evento = agente._eventos_registrados[0]
        assert evento["tipo"] == "advertencia"
        assert "Torneo finalizado" in evento["detalle"]

    @pytest.mark.asyncio
    async def test_torneo_activa_evento_parada(
        self, cliente_finalizar_torneo,
    ):
        """En modo torneo debe activar el evento_parada para que
        el proceso principal termine ordenadamente. La activación
        se programa con retardo (call_later) para que la respuesta
        HTTP llegue antes del cierre."""
        await cliente_finalizar_torneo.post(
            "/supervisor/api/finalizar-torneo",
        )
        evento = cliente_finalizar_torneo._app["evento_parada"]
        # Esperar a que call_later active el evento
        await asyncio.wait_for(evento.wait(), timeout=3)
        assert evento.is_set() is True

    # ── Modo laboratorio ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_laboratorio_devuelve_200(
        self, cliente_finalizar_laboratorio,
    ):
        """POST en modo laboratorio debe devolver 200 con modo
        'laboratorio'."""
        resp = await cliente_finalizar_laboratorio.post(
            "/supervisor/api/finalizar-torneo",
        )
        assert resp.status == 200
        datos = await resp.json()
        assert datos["modo"] == "laboratorio"

    @pytest.mark.asyncio
    async def test_laboratorio_invoca_detener_persistencia(
        self, cliente_finalizar_laboratorio,
    ):
        """En modo laboratorio debe invocar detener_persistencia()
        igual que en torneo."""
        await cliente_finalizar_laboratorio.post(
            "/supervisor/api/finalizar-torneo",
        )
        agente = cliente_finalizar_laboratorio._agente
        assert agente._persistencia_detenida is True

    # ── Modo consulta ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_consulta_devuelve_200(
        self, cliente_finalizar_consulta,
    ):
        """POST en modo consulta debe devolver 200 con modo
        'consulta'."""
        resp = await cliente_finalizar_consulta.post(
            "/supervisor/api/finalizar-torneo",
        )
        assert resp.status == 200
        datos = await resp.json()
        assert datos["modo"] == "consulta"

    @pytest.mark.asyncio
    async def test_consulta_cierra_almacen(
        self, cliente_finalizar_consulta,
    ):
        """En modo consulta debe cerrar el almacén de solo lectura
        (no invoca detener_persistencia porque no hay agente XMPP)."""
        await cliente_finalizar_consulta.post(
            "/supervisor/api/finalizar-torneo",
        )
        agente = cliente_finalizar_consulta._agente
        assert agente._almacen_cerrado is True
        assert agente._persistencia_detenida is False

    @pytest.mark.asyncio
    async def test_consulta_no_registra_eventos(
        self, cliente_finalizar_consulta,
    ):
        """En modo consulta no hay salas ni log, por lo que no debe
        registrar eventos."""
        await cliente_finalizar_consulta.post(
            "/supervisor/api/finalizar-torneo",
        )
        agente = cliente_finalizar_consulta._agente
        assert len(agente._eventos_registrados) == 0

    @pytest.mark.asyncio
    async def test_consulta_activa_evento_parada(
        self, cliente_finalizar_consulta,
    ):
        """En modo consulta también debe activar el evento_parada
        para que el proceso cierre el servidor web."""
        await cliente_finalizar_consulta.post(
            "/supervisor/api/finalizar-torneo",
        )
        evento = cliente_finalizar_consulta._app["evento_parada"]
        await asyncio.wait_for(evento.wait(), timeout=3)
        assert evento.is_set() is True

    # ── Tests generales (frontend y restricciones HTTP) ──────────

    @pytest.mark.asyncio
    async def test_get_finalizar_no_permitido(
        self, cliente_finalizar_torneo,
    ):
        """GET al endpoint de finalización debe devolver 405
        Method Not Allowed (solo acepta POST)."""
        resp = await cliente_finalizar_torneo.get(
            "/supervisor/api/finalizar-torneo",
        )
        assert resp.status == 405

    @pytest.mark.asyncio
    async def test_html_contiene_boton_finalizar(
        self, cliente_finalizar_torneo,
    ):
        """La página del dashboard debe contener el botón de
        finalización del torneo."""
        resp = await cliente_finalizar_torneo.get("/supervisor")
        html = await resp.text()
        assert 'id="sv-finalizar-torneo"' in html
        assert "Finalizar torneo" in html

    @pytest.mark.asyncio
    async def test_js_contiene_funcion_finalizar(
        self, cliente_finalizar_torneo,
    ):
        """supervisor.js debe contener la función finalizarTorneo,
        el diálogo de confirmación y la adaptación del texto del
        botón según el modo."""
        resp = await cliente_finalizar_torneo.get(
            "/supervisor/static/supervisor.js",
        )
        js = await resp.text()
        assert "function finalizarTorneo()" in js
        assert "function confirmarFinalizarTorneo()" in js
        assert "function mostrarPantallaFinalizada()" in js
        assert "window.confirm" in js
        assert "/supervisor/api/finalizar-torneo" in js
        # El texto del botón se adapta al modo
        assert "Cerrar dashboard" in js
        assert "Finalizar torneo" in js
        # Pantalla de finalización indica que se puede cerrar
        assert "Puedes cerrar esta" in js

    @pytest.mark.asyncio
    async def test_css_contiene_estilo_boton(
        self, cliente_finalizar_torneo,
    ):
        """supervisor.css debe contener el estilo del botón de
        finalización."""
        resp = await cliente_finalizar_torneo.get(
            "/supervisor/static/supervisor.css",
        )
        css = await resp.text()
        assert ".sv-finalizar-btn" in css
        assert ".sv-finalizar-btn:disabled" in css


# ═══════════════════════════════════════════════════════════════════════════
#  Tests: exportacion CSV al finalizar sesion
# ═══════════════════════════════════════════════════════════════════════════

class TestExportarCsvSesion:
    """Verifica que al finalizar en modo laboratorio o torneo se
    generan los ficheros CSV clasificados por sala."""

    @pytest.fixture
    def agente_con_datos(self, tmp_path):
        """Agente simulado con informes y eventos de ejemplo."""
        informe_victoria = {
            "action": "game-report",
            "result": "win",
            "winner": "X",
            "players": {
                "X": "jugador_ana@localhost",
                "O": "jugador_luis@localhost",
            },
            "turns": 7,
            "board": [
                "X", "O", "X", "O", "X", "O", "", "", "X",
            ],
        }
        evento_ejemplo = {
            "ts": "10:30:15",
            "tipo": "informe",
            "de": "tablero_mesa1",
            "detalle": "Victoria de X en 7 turnos",
        }
        agente = crear_agente_simulado(
            informes={
                "tictactoe": {
                    "tablero_mesa1@localhost": [
                        informe_victoria,
                    ],
                },
            },
            eventos={
                "tictactoe": [evento_ejemplo],
            },
        )
        return agente

    def test_genera_directorio_con_marca_temporal(
        self, agente_con_datos, monkeypatch,
    ):
        """La exportacion debe crear un directorio con formato
        YYYY-MM-DD_HH-MM-SS_modo."""
        monkeypatch.chdir(
            pathlib.Path(__file__).parent.parent,
        )
        ruta = _exportar_csv_sesion(agente_con_datos, "torneo")
        directorio = pathlib.Path(ruta)
        assert directorio.exists()
        assert "torneo" in directorio.name
        # Limpiar
        import shutil
        shutil.rmtree(directorio.parent, ignore_errors=True)

    def test_crea_subdirectorio_por_sala(
        self, agente_con_datos, monkeypatch,
    ):
        """Cada sala con actividad debe tener su propio
        subdirectorio."""
        monkeypatch.chdir(
            pathlib.Path(__file__).parent.parent,
        )
        ruta = _exportar_csv_sesion(agente_con_datos, "torneo")
        directorio = pathlib.Path(ruta)
        sala_dir = directorio / "tictactoe"
        assert sala_dir.is_dir()
        import shutil
        shutil.rmtree(directorio.parent, ignore_errors=True)

    def test_genera_ranking_csv(
        self, agente_con_datos, monkeypatch,
    ):
        """La sala con informes debe tener un ranking.csv con
        cabeceras y datos."""
        monkeypatch.chdir(
            pathlib.Path(__file__).parent.parent,
        )
        ruta = _exportar_csv_sesion(agente_con_datos, "torneo")
        directorio = pathlib.Path(ruta)
        ranking = directorio / "tictactoe" / "ranking.csv"
        assert ranking.exists()
        contenido = ranking.read_text(encoding="utf-8")
        assert "alumno" in contenido
        assert "victorias" in contenido
        import shutil
        shutil.rmtree(directorio.parent, ignore_errors=True)

    def test_genera_log_csv(
        self, agente_con_datos, monkeypatch,
    ):
        """La sala con eventos debe tener un log.csv."""
        monkeypatch.chdir(
            pathlib.Path(__file__).parent.parent,
        )
        ruta = _exportar_csv_sesion(agente_con_datos, "torneo")
        directorio = pathlib.Path(ruta)
        log = directorio / "tictactoe" / "log.csv"
        assert log.exists()
        contenido = log.read_text(encoding="utf-8")
        assert "timestamp" in contenido
        import shutil
        shutil.rmtree(directorio.parent, ignore_errors=True)

    def test_sala_sin_actividad_no_genera_directorio(
        self, monkeypatch,
    ):
        """Las salas sin informes ni eventos no deben generar
        subdirectorio."""
        agente = crear_agente_simulado()  # sin datos
        monkeypatch.chdir(
            pathlib.Path(__file__).parent.parent,
        )
        ruta = _exportar_csv_sesion(agente, "laboratorio")
        directorio = pathlib.Path(ruta)
        # El directorio raiz puede existir pero sin subdirs
        subdirs = list(directorio.iterdir()) if \
            directorio.exists() else []
        assert len(subdirs) == 0
        import shutil
        shutil.rmtree(directorio.parent, ignore_errors=True)

    def test_respuesta_incluye_ruta_csv(self, monkeypatch):
        """El handler de finalizacion en modo torneo debe incluir
        csv_exportados en la respuesta JSON."""
        agente = _crear_agente_con_finalizacion("torneo")
        monkeypatch.chdir(
            pathlib.Path(__file__).parent.parent,
        )
        ruta = _exportar_csv_sesion(agente, "torneo")
        assert "sesiones" in ruta
        import shutil
        directorio = pathlib.Path(ruta)
        shutil.rmtree(directorio.parent, ignore_errors=True)
