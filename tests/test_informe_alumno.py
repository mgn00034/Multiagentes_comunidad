"""
Tests del esquema y validador del informe de integracion del alumno.

Verifica que:
  - El esquema JSON esta bien formado y carga sin errores.
  - Los constructores generan informes validos.
  - El validador rechaza informes con campos faltantes o incorrectos.
  - Las reglas condicionales cruzadas funcionan correctamente.
  - La serializacion escribe un fichero JSON valido.

Ejecucion::

    pytest tests/test_informe_alumno.py -v
"""
import copy
import json
import os
import tempfile

import pytest

from validacion.informe_alumno import (
    ESQUEMA_INFORME_ALUMNO,
    crear_informe_alumno,
    crear_partida_observada,
    serializar_informe_alumno,
    validar_informe_alumno,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Datos de ejemplo reutilizables
# ═══════════════════════════════════════════════════════════════════════════
# IMPORTANTE: las funciones auxiliares _crear_* devuelven copias frescas
# para que los tests que muten datos no contaminen a los demas.

_AGENTES_BASE = [
    {"jid": "tablero_pc05@sinbad2.ujaen.es", "rol": "tablero"},
    {"jid": "jugador_pc05_x@sinbad2.ujaen.es", "rol": "jugador"},
    {"jid": "jugador_pc05_o@sinbad2.ujaen.es", "rol": "jugador"},
]

_TABLERO_VICTORIA_X = ["X", "X", "X", "O", "O", "", "", "", ""]

_TABLERO_EMPATE = ["X", "O", "X", "X", "O", "O", "O", "X", "X"]

_JUGADORES_BASE = {
    "X": "jugador_pc05_x@sinbad2.ujaen.es",
    "O": "jugador_pc05_o@sinbad2.ujaen.es",
}


def _agentes():
    """Devuelve una copia fresca de la lista de agentes."""
    return copy.deepcopy(_AGENTES_BASE)


def _jugadores():
    """Devuelve una copia fresca del mapa de jugadores."""
    return copy.deepcopy(_JUGADORES_BASE)


def _crear_partida_victoria():
    """Crea una partida de victoria valida para reutilizar en tests."""
    partida = crear_partida_observada(
        tablero_jid="tablero_pc05@sinbad2.ujaen.es",
        resultado="win",
        jugadores=_jugadores(),
        turnos=5,
        tablero_final=_TABLERO_VICTORIA_X,
        ganador_ficha="X",
        timestamp="10:25:33",
    )
    return partida


def _crear_partida_empate():
    """Crea una partida de empate valida para reutilizar en tests."""
    partida = crear_partida_observada(
        tablero_jid="tablero_pc05@sinbad2.ujaen.es",
        resultado="draw",
        jugadores=_jugadores(),
        turnos=9,
        tablero_final=_TABLERO_EMPATE,
        timestamp="10:30:00",
    )
    return partida


def _crear_informe_valido():
    """Crea un informe completo valido para reutilizar en tests."""
    informe = crear_informe_alumno(
        equipo="grupo_03",
        puesto="pc05",
        timestamp_inicio="2026-04-15T10:15:00",
        timestamp_fin="2026-04-15T10:35:00",
        agentes_desplegados=_agentes(),
        partidas_observadas=[_crear_partida_victoria()],
    )
    return informe


# ═══════════════════════════════════════════════════════════════════════════
#  Tests del esquema
# ═══════════════════════════════════════════════════════════════════════════


class TestEsquemaInformeAlumno:
    """Verifica que el esquema JSON se carga correctamente."""

    def test_esquema_tiene_schema(self):
        """El esquema tiene la referencia a JSON Schema draft 2020-12."""
        assert "$schema" in ESQUEMA_INFORME_ALUMNO

    def test_esquema_tiene_id(self):
        """El esquema tiene un identificador unico."""
        assert "$id" in ESQUEMA_INFORME_ALUMNO

    def test_esquema_tiene_propiedades(self):
        """El esquema define las propiedades del informe."""
        assert "properties" in ESQUEMA_INFORME_ALUMNO

    def test_esquema_campos_obligatorios(self):
        """El esquema exige los campos obligatorios del informe."""
        requeridos = set(ESQUEMA_INFORME_ALUMNO["required"])
        esperados = {
            "equipo", "puesto", "timestamp_inicio",
            "timestamp_fin", "agentes_desplegados",
            "partidas_observadas",
        }
        assert esperados == requeridos

    def test_esquema_prohibe_campos_extra(self):
        """El esquema rechaza campos no definidos."""
        assert ESQUEMA_INFORME_ALUMNO.get("additionalProperties") is False


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de los constructores
# ═══════════════════════════════════════════════════════════════════════════


class TestConstructores:
    """Verifica que los constructores generan informes validos."""

    def test_crear_partida_victoria(self):
        """Constructor de partida con victoria genera datos validos."""
        partida = _crear_partida_victoria()
        assert partida["resultado"] == "win"
        assert partida["ganador_ficha"] == "X"
        assert partida["turnos"] == 5

    def test_crear_partida_empate(self):
        """Constructor de partida con empate genera datos validos."""
        partida = _crear_partida_empate()
        assert partida["resultado"] == "draw"
        assert partida["ganador_ficha"] is None

    def test_crear_partida_abortada(self):
        """Constructor de partida abortada incluye razon."""
        partida = crear_partida_observada(
            tablero_jid="tablero_pc05@sinbad2.ujaen.es",
            resultado="aborted",
            jugadores=_jugadores(),
            turnos=3,
            tablero_final=["X", "O", "X", "", "", "", "", "", ""],
            razon="timeout",
        )
        assert partida["razon"] == "timeout"

    def test_crear_informe_completo_es_valido(self):
        """Un informe construido con los constructores pasa validacion."""
        informe = _crear_informe_valido()
        resultado = validar_informe_alumno(informe)
        assert resultado["valido"], resultado["errores"]

    def test_crear_informe_con_incidencias(self):
        """Un informe con incidencias es valido."""
        informe = crear_informe_alumno(
            equipo="grupo_07",
            puesto="pc12",
            timestamp_inicio="2026-04-15T10:15:00",
            timestamp_fin="2026-04-15T10:35:00",
            agentes_desplegados=_agentes(),
            partidas_observadas=[_crear_partida_victoria()],
            incidencias=[
                {
                    "tipo": "timeout",
                    "detalle": "El tablero no respondio en 10 s",
                    "timestamp": "10:24:20",
                },
            ],
        )
        resultado = validar_informe_alumno(informe)
        assert resultado["valido"], resultado["errores"]

    def test_crear_informe_multiples_partidas(self):
        """Un informe con varias partidas es valido."""
        informe = crear_informe_alumno(
            equipo="grupo_03",
            puesto="pc05",
            timestamp_inicio="2026-04-15T10:15:00",
            timestamp_fin="2026-04-15T10:35:00",
            agentes_desplegados=_agentes(),
            partidas_observadas=[
                _crear_partida_victoria(),
                _crear_partida_empate(),
            ],
        )
        resultado = validar_informe_alumno(informe)
        assert resultado["valido"], resultado["errores"]


# ═══════════════════════════════════════════════════════════════════════════
#  Tests del validador — campos obligatorios
# ═══════════════════════════════════════════════════════════════════════════


class TestValidadorCamposObligatorios:
    """Verifica que el validador rechaza informes incompletos."""

    def test_informe_vacio_rechazado(self):
        """Un diccionario vacio es rechazado."""
        resultado = validar_informe_alumno({})
        assert not resultado["valido"]

    def test_falta_equipo(self):
        """Se rechaza si falta el campo 'equipo'."""
        informe = _crear_informe_valido()
        del informe["equipo"]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_falta_puesto(self):
        """Se rechaza si falta el campo 'puesto'."""
        informe = _crear_informe_valido()
        del informe["puesto"]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_falta_agentes_desplegados(self):
        """Se rechaza si falta la lista de agentes desplegados."""
        informe = _crear_informe_valido()
        del informe["agentes_desplegados"]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_falta_partidas_observadas(self):
        """Se rechaza si falta la lista de partidas."""
        informe = _crear_informe_valido()
        del informe["partidas_observadas"]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_puesto_formato_invalido(self):
        """Se rechaza si el puesto no sigue el patron pcXX."""
        informe = _crear_informe_valido()
        informe["puesto"] = "mesa5"
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_resultado_invalido(self):
        """Se rechaza si el resultado de una partida no es valido."""
        informe = _crear_informe_valido()
        informe["partidas_observadas"][0]["resultado"] = "victoria"
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_rol_invalido(self):
        """Se rechaza si un agente tiene rol desconocido."""
        informe = _crear_informe_valido()
        informe["agentes_desplegados"][0]["rol"] = "observador"
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_tablero_final_tamano_incorrecto(self):
        """Se rechaza si el tablero no tiene exactamente 9 celdas."""
        informe = _crear_informe_valido()
        informe["partidas_observadas"][0]["tablero_final"] = ["X", "O"]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_campo_extra_rechazado(self):
        """Se rechaza si el informe contiene campos no definidos."""
        informe = _crear_informe_valido()
        informe["campo_inventado"] = "valor"
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_agentes_desplegados_vacia(self):
        """Se rechaza si la lista de agentes esta vacia."""
        informe = _crear_informe_valido()
        informe["agentes_desplegados"] = []
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_tipo_incidencia_invalido(self):
        """Se rechaza si una incidencia tiene tipo no reconocido."""
        informe = _crear_informe_valido()
        informe["incidencias"] = [
            {"tipo": "catastrofe", "detalle": "algo raro"},
        ]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]


# ═══════════════════════════════════════════════════════════════════════════
#  Tests del validador — reglas condicionales cruzadas
# ═══════════════════════════════════════════════════════════════════════════


class TestReglasCondicionales:
    """Verifica las reglas cruzadas entre campos de una partida."""

    def test_victoria_sin_ganador_ficha(self):
        """Victoria sin ganador_ficha es rechazada."""
        informe = _crear_informe_valido()
        informe["partidas_observadas"][0]["ganador_ficha"] = None
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]
        encontrado = False
        indice = 0
        while indice < len(resultado["errores"]) and not encontrado:
            if "ganador_ficha" in resultado["errores"][indice]:
                encontrado = True
            indice += 1
        assert encontrado

    def test_empate_con_ganador_ficha(self):
        """Empate con ganador_ficha no nulo es rechazado."""
        informe = _crear_informe_valido()
        informe["partidas_observadas"] = [_crear_partida_empate()]
        informe["partidas_observadas"][0]["ganador_ficha"] = "X"
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_abortada_sin_razon(self):
        """Partida abortada sin razon es rechazada."""
        partida = crear_partida_observada(
            tablero_jid="tablero_pc05@sinbad2.ujaen.es",
            resultado="aborted",
            jugadores=_jugadores(),
            turnos=3,
            tablero_final=["X", "O", "X", "", "", "", "", "", ""],
        )
        informe = _crear_informe_valido()
        informe["partidas_observadas"] = [partida]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_victoria_con_menos_de_5_turnos(self):
        """Victoria con menos de 5 turnos es anomala."""
        informe = _crear_informe_valido()
        informe["partidas_observadas"][0]["turnos"] = 3
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_mas_de_9_turnos(self):
        """Partida con mas de 9 turnos es rechazada."""
        informe = _crear_informe_valido()
        informe["partidas_observadas"][0]["turnos"] = 12
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_victoria_sin_linea_ganadora_en_tablero(self):
        """Victoria declarada pero sin linea ganadora es rechazada."""
        informe = _crear_informe_valido()
        # Tablero sin linea ganadora de X
        informe["partidas_observadas"][0]["tablero_final"] = [
            "X", "O", "X", "O", "X", "O", "O", "X", "",
        ]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_empate_con_linea_ganadora_oculta(self):
        """Empate declarado pero con linea ganadora es rechazado."""
        partida = crear_partida_observada(
            tablero_jid="tablero_pc05@sinbad2.ujaen.es",
            resultado="draw",
            jugadores=_jugadores(),
            turnos=9,
            # Hay linea ganadora de X en fila 0
            tablero_final=["X", "X", "X", "O", "O", "X", "O", "X", "O"],
        )
        informe = _crear_informe_valido()
        informe["partidas_observadas"] = [partida]
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_jugador_contra_si_mismo(self):
        """Jugador contra si mismo es rechazado."""
        informe = _crear_informe_valido()
        jid_repetido = "jugador_pc05_x@sinbad2.ujaen.es"
        informe["partidas_observadas"][0]["jugadores"] = {
            "X": jid_repetido, "O": jid_repetido,
        }
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de coherencia temporal
# ═══════════════════════════════════════════════════════════════════════════


class TestCoherenciaTemporal:
    """Verifica la validacion de timestamps."""

    def test_inicio_posterior_a_fin(self):
        """Se rechaza si inicio es posterior a fin."""
        informe = crear_informe_alumno(
            equipo="grupo_03",
            puesto="pc05",
            timestamp_inicio="2026-04-15T10:35:00",
            timestamp_fin="2026-04-15T10:15:00",
            agentes_desplegados=_agentes(),
            partidas_observadas=[_crear_partida_victoria()],
        )
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]

    def test_inicio_igual_a_fin(self):
        """Se rechaza si inicio es igual a fin."""
        informe = crear_informe_alumno(
            equipo="grupo_03",
            puesto="pc05",
            timestamp_inicio="2026-04-15T10:15:00",
            timestamp_fin="2026-04-15T10:15:00",
            agentes_desplegados=_agentes(),
            partidas_observadas=[_crear_partida_victoria()],
        )
        resultado = validar_informe_alumno(informe)
        assert not resultado["valido"]


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de serializacion
# ═══════════════════════════════════════════════════════════════════════════


class TestSerializacion:
    """Verifica la escritura a fichero JSON."""

    def test_serializar_informe_valido(self):
        """Un informe valido se serializa correctamente a fichero."""
        informe = _crear_informe_valido()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False,
        ) as tmp:
            ruta = tmp.name

        try:
            resultado = serializar_informe_alumno(informe, ruta)
            assert resultado["valido"]

            with open(ruta, "r", encoding="utf-8") as f:
                leido = json.load(f)
            assert leido["equipo"] == "grupo_03"
            assert leido["puesto"] == "pc05"
            assert len(leido["partidas_observadas"]) == 1
        finally:
            os.unlink(ruta)

    def test_serializar_informe_invalido_lanza_error(self):
        """Un informe invalido lanza ValueError al serializar."""
        informe = {"equipo": "test"}
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False,
        ) as tmp:
            ruta = tmp.name

        try:
            with pytest.raises(ValueError):
                serializar_informe_alumno(informe, ruta)
        finally:
            if os.path.exists(ruta):
                os.unlink(ruta)

    def test_fichero_serializado_es_json_valido(self):
        """El fichero generado se puede leer y revalidar."""
        informe = _crear_informe_valido()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False,
        ) as tmp:
            ruta = tmp.name

        try:
            serializar_informe_alumno(informe, ruta)
            with open(ruta, "r", encoding="utf-8") as f:
                leido = json.load(f)
            resultado = validar_informe_alumno(leido)
            assert resultado["valido"], resultado["errores"]
        finally:
            os.unlink(ruta)
