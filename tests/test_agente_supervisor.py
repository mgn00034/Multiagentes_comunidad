"""
Tests unitarios de los métodos del Agente Supervisor.

Se prueban de forma aislada, sin arrancar SPADE ni conectarse a un
servidor XMPP.  Se construye un objeto que imita los atributos del
agente real y se invocan los métodos directamente.

Componentes cubiertos:
- ``_identificar_sala``
- ``obtener_sala_de_tablero``
- ``registrar_evento_log``
- ``_on_presencia_muc`` (detección de ocupantes, cambios de estado,
  tableros finalizados, entradas y salidas)
"""

from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentes.agente_supervisor import AgenteSupervisor
from behaviours.supervisor_behaviours import (
    LOG_ENTRADA,
    LOG_INFORME,
    LOG_PRESENCIA,
    LOG_SALIDA,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Datos de prueba
# ═══════════════════════════════════════════════════════════════════════════

SALAS_EJEMPLO = [
    {"id": "tictactoe", "jid": "tictactoe@conference.localhost"},
    {"id": "torneo", "jid": "torneo@conference.localhost"},
]


# ═══════════════════════════════════════════════════════════════════════════
#  Utilidades para simular stanzas de presencia MUC
# ═══════════════════════════════════════════════════════════════════════════

def _crear_jid_from(sala_jid, nick):
    """Crea un objeto que imita presencia['from'] de slixmpp."""
    jid = SimpleNamespace(
        bare=sala_jid,
        resource=nick,
    )
    return jid


class _ItemMuc:
    """Imita el item MUC de slixmpp, que soporta acceso por clave
    (item['jid']) y por atributo (item.jid)."""

    def __init__(self, jid_real):
        self._jid = jid_real if jid_real else None

    def __getitem__(self, clave):
        if clave == "jid":
            return self._jid
        raise KeyError(clave)

    def __getattr__(self, nombre):
        if nombre == "jid":
            return self._jid
        raise AttributeError(nombre)


def _crear_presencia_muc(
    sala_jid, nick, tipo="", show="", status="", jid_real="",
):
    """Crea un dict-like que imita una stanza de presencia MUC de
    slixmpp, con los campos que usa ``_on_presencia_muc``."""
    jid_from = _crear_jid_from(sala_jid, nick)

    # El item MUC con el JID real del agente
    item_muc = _ItemMuc(jid_real)
    muc_ns = {"item": item_muc}

    campos = {
        "from": jid_from,
        "type": tipo,
        "show": show,
        "status": status,
        "muc": muc_ns,
    }

    # Simular el acceso con presencia["campo"] y presencia.get("campo")
    class PresenciaSimulada:
        """Objeto que imita la interfaz de una stanza de presencia."""
        def __getitem__(self, clave):
            return campos[clave]

        def get(self, clave, defecto=""):
            return campos.get(clave, defecto)

    presencia = PresenciaSimulada()
    return presencia


# ═══════════════════════════════════════════════════════════════════════════
#  Fixture: agente simulado
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def agente():
    """Crea una instancia de AgenteSupervisor sin pasar por __init__
    de SPADE, inyectando manualmente los atributos que usan los
    métodos bajo test."""
    ag = object.__new__(AgenteSupervisor)
    ag.salas_muc = list(SALAS_EJEMPLO)
    ag.informes_por_sala = {s["id"]: {} for s in SALAS_EJEMPLO}
    ag.tableros_consultados = set()
    ag.informes_pendientes = {}
    ag.tablero_a_sala = {}
    ag.ocupantes_por_sala = {s["id"]: [] for s in SALAS_EJEMPLO}
    ag.ocupantes_historicos_por_sala = {
        s["id"]: set() for s in SALAS_EJEMPLO
    }
    ag.threads_procesados_por_sala = {
        s["id"]: set() for s in SALAS_EJEMPLO
    }
    ag.log_por_sala = {s["id"]: [] for s in SALAS_EJEMPLO}
    ag.almacen = MagicMock()
    ag.timeout_respuesta = 10
    ag.max_reintentos = 2
    ag.max_fsm_concurrentes = 5
    ag.tableros_en_cola = deque()
    ag.muc_apodo = "supervisor"
    ag._reconexion_activa = False
    ag.add_behaviour = MagicMock()
    return ag


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _identificar_sala
# ═══════════════════════════════════════════════════════════════════════════

class TestIdentificarSala:
    """Verifica que se identifica correctamente la sala a la que
    pertenece un JID."""

    def test_jid_de_sala_tictactoe(self, agente):
        """Un JID que contiene el JID de la sala tictactoe debe
        identificarse como 'tictactoe'."""
        resultado = agente._identificar_sala(
            "tictactoe@conference.localhost/tablero_mesa1",
        )
        assert resultado == "tictactoe"

    def test_jid_de_sala_torneo(self, agente):
        """Un JID que contiene el JID de la sala torneo debe
        identificarse como 'torneo'."""
        resultado = agente._identificar_sala(
            "torneo@conference.localhost/jugador_ana",
        )
        assert resultado == "torneo"

    def test_jid_no_pertenece_a_ninguna_sala(self, agente):
        """Un JID que no pertenece a ninguna sala configurada debe
        devolver cadena vacía."""
        resultado = agente._identificar_sala(
            "otra_sala@conference.localhost/agente",
        )
        assert resultado == ""

    def test_jid_sin_recurso(self, agente):
        """Debe funcionar también con JIDs sin parte de recurso."""
        resultado = agente._identificar_sala(
            "tictactoe@conference.localhost",
        )
        assert resultado == "tictactoe"


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de obtener_sala_de_tablero
# ═══════════════════════════════════════════════════════════════════════════

class TestObtenerSalaDeTablero:
    """Verifica la búsqueda de la sala a la que pertenece un tablero."""

    def test_tablero_registrado(self, agente):
        """Si el tablero está en el mapeo, debe devolver su sala."""
        agente.tablero_a_sala["tablero@localhost"] = "tictactoe"
        resultado = agente.obtener_sala_de_tablero("tablero@localhost")
        assert resultado == "tictactoe"

    def test_tablero_con_recurso_busca_sin_recurso(self, agente):
        """Si el JID completo no está pero sí la parte sin recurso,
        debe encontrarlo."""
        agente.tablero_a_sala["tablero@localhost"] = "torneo"
        resultado = agente.obtener_sala_de_tablero(
            "tablero@localhost/recurso123",
        )
        assert resultado == "torneo"

    def test_tablero_no_registrado_usa_primera_sala(self, agente):
        """Si el tablero no está registrado, debe devolver la primera
        sala configurada como valor por defecto."""
        resultado = agente.obtener_sala_de_tablero(
            "tablero_desconocido@localhost",
        )
        assert resultado == "tictactoe"

    def test_sin_salas_configuradas_devuelve_vacio(self, agente):
        """Si no hay salas configuradas ni mapeo, debe devolver cadena
        vacía."""
        agente.salas_muc = []
        agente.tablero_a_sala = {}
        resultado = agente.obtener_sala_de_tablero("tablero@localhost")
        assert resultado == ""


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de registrar_evento_log
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistrarEventoLog:
    """Verifica que los eventos se registran correctamente en el
    registro cronológico y se persisten en el almacén."""

    def test_evento_se_anade_al_registro(self, agente):
        """El evento debe aparecer en log_por_sala de la sala
        indicada."""
        agente.registrar_evento_log(
            "presencia", "tablero_mesa1", "Se une", "tictactoe",
        )
        eventos = agente.log_por_sala["tictactoe"]
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == LOG_PRESENCIA
        assert eventos[0]["de"] == "tablero_mesa1"
        assert eventos[0]["detalle"] == "Se une"

    def test_eventos_en_orden_cronologico_inverso(self, agente):
        """Los eventos más recientes deben insertarse al principio."""
        agente.registrar_evento_log(
            "presencia", "ana", "Entra", "tictactoe",
        )
        agente.registrar_evento_log(
            "informe", "tablero", "Victoria", "tictactoe",
        )
        primero = agente.log_por_sala["tictactoe"][0]
        assert primero["tipo"] == LOG_INFORME

    def test_sin_sala_usa_primera_sala(self, agente):
        """Si no se indica sala, el evento debe registrarse en la
        primera sala configurada."""
        agente.registrar_evento_log("presencia", "ana", "Entra")
        assert len(agente.log_por_sala["tictactoe"]) == 1

    def test_persiste_en_almacen(self, agente):
        """Debe llamar a guardar_evento del almacén."""
        agente.registrar_evento_log(
            "informe", "tablero", "Victoria", "tictactoe",
        )
        agente.almacen.guardar_evento.assert_called_once()

    def test_evento_contiene_marca_temporal(self, agente):
        """El evento registrado debe incluir una marca temporal con
        formato HH:MM:SS."""
        agente.registrar_evento_log(
            "presencia", "ana", "Entra", "tictactoe",
        )
        ts = agente.log_por_sala["tictactoe"][0]["ts"]
        assert len(ts.split(":")) == 3


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _on_presencia_muc — Entrada de agentes
# ═══════════════════════════════════════════════════════════════════════════

class TestOnPresenciaMucEntrada:
    """Verifica que se registra correctamente la entrada de un nuevo
    ocupante a la sala MUC."""

    def test_nuevo_jugador_se_anade_a_ocupantes(self, agente):
        """Un jugador que no estaba en la lista debe añadirse a
        ocupantes_por_sala."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_ana",
            show="chat", jid_real="jugador_ana@localhost/abc",
        )
        agente._on_presencia_muc(presencia)
        ocupantes = agente.ocupantes_por_sala["tictactoe"]
        assert len(ocupantes) == 1
        assert ocupantes[0]["nick"] == "jugador_ana"
        assert ocupantes[0]["rol"] == "jugador"

    def test_nuevo_tablero_se_anade_a_ocupantes(self, agente):
        """Un tablero que no estaba en la lista debe añadirse."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="waiting", jid_real="tablero_mesa1@localhost/xyz",
        )
        agente._on_presencia_muc(presencia)
        ocupantes = agente.ocupantes_por_sala["tictactoe"]
        assert len(ocupantes) == 1
        assert ocupantes[0]["rol"] == "tablero"
        assert ocupantes[0]["estado"] == "waiting"

    def test_entrada_registra_evento_en_log(self, agente):
        """Cuando un nuevo ocupante se une, debe registrarse un evento
        de tipo 'entrada' en el log de la sala."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_luis",
            show="chat",
        )
        agente._on_presencia_muc(presencia)
        eventos = agente.log_por_sala["tictactoe"]
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == LOG_ENTRADA
        assert "jugador_luis" in eventos[0]["de"]

    def test_entrada_indica_rol_en_detalle(self, agente):
        """El detalle del evento de entrada debe incluir el rol del
        ocupante (jugador o tablero)."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="waiting",
        )
        agente._on_presencia_muc(presencia)
        evento = agente.log_por_sala["tictactoe"][0]
        assert "tablero" in evento["detalle"]

    def test_jid_real_se_extrae_sin_recurso(self, agente):
        """El JID real (sin recurso) debe almacenarse en el campo
        'jid' del ocupante. El recurso aleatorio se descarta."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_ana",
            show="chat", jid_real="jugador_ana@localhost",
        )
        agente._on_presencia_muc(presencia)
        ocupante = agente.ocupantes_por_sala["tictactoe"][0]
        assert ocupante["jid"] == "jugador_ana@localhost"


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _on_presencia_muc — Salida de agentes
# ═══════════════════════════════════════════════════════════════════════════

class TestOnPresenciaMucSalida:
    """Verifica que se elimina un ocupante y se registra su salida."""

    def test_ocupante_se_elimina_al_irse(self, agente):
        """Cuando un ocupante envía presencia 'unavailable', debe
        eliminarse de la lista de ocupantes."""
        # Primero el agente entra
        presencia_entra = _crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_ana",
            show="chat",
        )
        agente._on_presencia_muc(presencia_entra)
        assert len(agente.ocupantes_por_sala["tictactoe"]) == 1

        # Luego se va
        presencia_sale = _crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_ana",
            tipo="unavailable",
        )
        agente._on_presencia_muc(presencia_sale)
        assert len(agente.ocupantes_por_sala["tictactoe"]) == 0

    def test_salida_registra_evento_en_log(self, agente):
        """La salida debe registrar un evento de tipo 'salida'."""
        # Primero entra
        agente._on_presencia_muc(_crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_luis",
            show="chat",
        ))
        # Luego sale
        agente._on_presencia_muc(_crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_luis",
            tipo="unavailable",
        ))
        # El segundo evento (más reciente) está al principio
        evento_salida = agente.log_por_sala["tictactoe"][0]
        assert evento_salida["tipo"] == LOG_SALIDA
        assert "jugador_luis" in evento_salida["de"]


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _on_presencia_muc — Cambios de estado de tableros
# ═══════════════════════════════════════════════════════════════════════════

class TestOnPresenciaMucCambioEstado:
    """Verifica que los cambios de estado de los tableros se detectan
    y registran en el log."""

    def test_cambio_waiting_a_playing_registra_evento(self, agente):
        """Cuando un tablero pasa de 'waiting' a 'playing', debe
        registrarse un evento de tipo 'presencia' con la transición."""
        sala = "tictactoe@conference.localhost"
        nick = "tablero_mesa1"

        # Entrada inicial con estado 'waiting'
        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="waiting",
        ))
        # Cambio a 'playing'
        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="playing",
        ))

        # Buscar el evento de cambio de estado (el más reciente)
        evento = agente.log_por_sala["tictactoe"][0]
        assert evento["tipo"] == LOG_PRESENCIA
        assert "waiting" in evento["detalle"]
        assert "playing" in evento["detalle"]

    def test_cambio_playing_a_finished_registra_evento(self, agente):
        """Cuando un tablero pasa de 'playing' a 'finished', debe
        registrarse la transición en el log."""
        sala = "tictactoe@conference.localhost"
        nick = "tablero_mesa1"

        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="playing",
        ))
        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="finished",
        ))

        # El evento de cambio de estado (presencia) es el más reciente
        # tras el de "finished" que también se registra en la detección
        eventos = agente.log_por_sala["tictactoe"]
        tipos = [e["tipo"] for e in eventos]
        assert "presencia" in tipos

    def test_estado_sin_cambio_no_registra_evento(self, agente):
        """Si un tablero mantiene el mismo estado, no debe generar
        un evento de cambio de estado en el log."""
        sala = "tictactoe@conference.localhost"
        nick = "tablero_mesa1"

        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="waiting",
        ))
        num_eventos_tras_entrada = len(agente.log_por_sala["tictactoe"])

        # Misma presencia, mismo estado
        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="waiting",
        ))
        assert len(agente.log_por_sala["tictactoe"]) == num_eventos_tras_entrada

    def test_estado_se_actualiza_en_ocupantes(self, agente):
        """Al cambiar de estado, el campo 'estado' del ocupante debe
        actualizarse en ocupantes_por_sala."""
        sala = "tictactoe@conference.localhost"
        nick = "tablero_mesa1"

        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="waiting",
        ))
        assert agente.ocupantes_por_sala["tictactoe"][0]["estado"] == "waiting"

        agente._on_presencia_muc(_crear_presencia_muc(
            sala, nick, status="playing",
        ))
        assert agente.ocupantes_por_sala["tictactoe"][0]["estado"] == "playing"

    def test_cambio_estado_jugador_no_registra_evento(self, agente):
        """Los cambios de estado de jugadores NO deben generar eventos
        de cambio de estado (solo los tableros son relevantes)."""
        sala = "tictactoe@conference.localhost"

        agente._on_presencia_muc(_crear_presencia_muc(
            sala, "jugador_ana", show="chat",
        ))
        n_eventos = len(agente.log_por_sala["tictactoe"])

        agente._on_presencia_muc(_crear_presencia_muc(
            sala, "jugador_ana", show="away",
        ))
        # Solo debería haber el evento de entrada, no de cambio
        assert len(agente.log_por_sala["tictactoe"]) == n_eventos


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de _on_presencia_muc — Detección de tableros finalizados
# ═══════════════════════════════════════════════════════════════════════════

class TestOnPresenciaMucFinished:
    """Verifica la detección de tableros con status='finished' y la
    creación del FSM para solicitar el informe."""

    def test_tablero_finished_crea_fsm(self, agente):
        """Cuando un tablero cambia a status='finished', debe crear
        un FSM y añadirlo al agente."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/recurso",
        )
        agente._on_presencia_muc(presencia)
        agente.add_behaviour.assert_called_once()

    def test_tablero_finished_permanece_bloqueado(self, agente):
        """Tras crear el FSM, el tablero debe permanecer en
        tableros_consultados hasta que el FSM termine (S-01).
        El desbloqueo lo ejecuta el estado terminal del FSM."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/recurso",
        )
        agente._on_presencia_muc(presencia)
        assert "tablero_mesa1@localhost" in agente.tableros_consultados

    def test_tablero_ya_consultado_no_crea_fsm(self, agente):
        """Si el tablero ya está en tableros_consultados, no debe
        crear un nuevo FSM."""
        # El handler usa jid_bare como clave (sin recurso)
        agente.tableros_consultados.add("tablero_mesa1@localhost")
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost",
        )
        agente._on_presencia_muc(presencia)
        agente.add_behaviour.assert_not_called()

    def test_estado_no_finished_no_crea_fsm(self, agente):
        """Un cambio de presencia con estado distinto de 'finished'
        no debe crear ningún FSM."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="playing",
        )
        agente._on_presencia_muc(presencia)
        agente.add_behaviour.assert_not_called()

    def test_jugador_finished_no_crea_fsm(self, agente):
        """Un cambio de presencia de un jugador (no tablero) no debe
        crear ningún FSM, aunque su estado sea 'finished'."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "jugador_ana",
            status="finished",
        )
        agente._on_presencia_muc(presencia)
        agente.add_behaviour.assert_not_called()

    def test_tablero_de_sala_desconocida_no_crea_fsm(self, agente):
        """Un tablero que no pertenece a ninguna sala configurada
        no debe crear un FSM."""
        presencia = _crear_presencia_muc(
            "otra_sala@conference.localhost", "tablero_mesa1",
            status="finished",
        )
        agente._on_presencia_muc(presencia)
        agente.add_behaviour.assert_not_called()

    def test_supervisor_es_ignorado(self, agente):
        """Las presencias del propio supervisor deben ignorarse."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "supervisor",
            show="chat",
        )
        agente._on_presencia_muc(presencia)
        assert len(agente.ocupantes_por_sala["tictactoe"]) == 0

    def test_registra_mapeo_tablero_a_sala(self, agente):
        """Un tablero debe registrar su correspondencia tablero→sala."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="waiting",
            jid_real="tablero_mesa1@localhost",
        )
        agente._on_presencia_muc(presencia)
        assert agente.tablero_a_sala.get(
            "tablero_mesa1@localhost",
        ) == "tictactoe"


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de S-01: filtrado de redistribuciones finished → finished
# ═══════════════════════════════════════════════════════════════════════════

class TestFiltradoRedistribucionFinished:
    """Verifica que el supervisor ignora redistribuciones de
    presencia donde el tablero ya estaba en 'finished' (S-01,
    cambio 1). Solo debe crear un FSM cuando el estado CAMBIA
    a 'finished', no cuando se redistribuye."""

    def test_redistribucion_finished_no_crea_fsm(self, agente):
        """Dos stanzas consecutivas con status='finished' deben
        generar solo un FSM. La segunda es una redistribucion
        que debe ignorarse."""
        presencia1 = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        )
        # Primera: transicion real (playing → finished)
        agente._on_presencia_muc(presencia1)
        assert agente.add_behaviour.call_count == 1

        # Segunda: redistribucion (finished → finished)
        presencia2 = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        )
        agente._on_presencia_muc(presencia2)
        # No debe haber creado un segundo FSM
        assert agente.add_behaviour.call_count == 1

    def test_ciclo_finished_waiting_finished_crea_segundo_fsm(
        self, agente,
    ):
        """La secuencia finished → waiting → playing → finished
        debe crear un segundo FSM, porque es una nueva partida."""
        # Primera partida: playing → finished
        agente._on_presencia_muc(_crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        ))
        assert agente.add_behaviour.call_count == 1

        # Simular que el FSM terminó y desbloqueó el tablero
        agente.tableros_consultados.discard(
            "tablero_mesa1@localhost",
        )
        agente.informes_pendientes.pop(
            "tablero_mesa1@localhost", None,
        )

        # Tablero vuelve a waiting (nueva partida)
        agente._on_presencia_muc(_crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="waiting",
            jid_real="tablero_mesa1@localhost/r",
        ))

        # Tablero pasa a playing
        agente._on_presencia_muc(_crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="playing",
            jid_real="tablero_mesa1@localhost/r",
        ))

        # Segunda partida: playing → finished
        agente._on_presencia_muc(_crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        ))
        assert agente.add_behaviour.call_count == 2

    def test_tablero_nuevo_en_finished_es_detectado(self, agente):
        """Un tablero que aparece directamente en 'finished' (por
        ejemplo, reconexion del supervisor) debe ser detectado
        porque estado_anterior es '' (no es 'finished')."""
        presencia = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        )
        agente._on_presencia_muc(presencia)
        agente.add_behaviour.assert_called_once()

    def test_permanencia_larga_en_finished_no_duplica(
        self, agente,
    ):
        """Un tablero que permanece en 'finished' largo tiempo
        no debe generar FSMs adicionales aunque se reciban
        multiples redistribuciones de presencia."""
        base = {
            "sala": "tictactoe@conference.localhost",
            "nick": "tablero_mesa1",
            "status": "finished",
            "jid_real": "tablero_mesa1@localhost/r",
        }
        # Transicion real
        agente._on_presencia_muc(_crear_presencia_muc(
            base["sala"], base["nick"],
            status=base["status"],
            jid_real=base["jid_real"],
        ))
        assert agente.add_behaviour.call_count == 1

        # Simular 5 redistribuciones adicionales
        i = 0
        while i < 5:
            agente._on_presencia_muc(_crear_presencia_muc(
                base["sala"], base["nick"],
                status=base["status"],
                jid_real=base["jid_real"],
            ))
            i += 1

        # Sigue habiendo solo 1 FSM
        assert agente.add_behaviour.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de límite de FSMs concurrentes (D-14)
# ═══════════════════════════════════════════════════════════════════════════

class TestLimiteFSMConcurrentes:
    """Verifica que el supervisor encola los tableros finalizados
    cuando se alcanza el límite de FSMs concurrentes y los
    desencola conforme terminan."""

    def test_tablero_se_encola_al_alcanzar_limite(self, agente):
        """Cuando hay max_fsm_concurrentes FSMs activos, el
        siguiente tablero finalizado debe encolarse en vez de
        crear un FSM."""
        agente.max_fsm_concurrentes = 1

        # Primer tablero: crea FSM (bajo el límite)
        presencia1 = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        )
        agente._on_presencia_muc(presencia1)
        assert agente.add_behaviour.call_count == 1
        assert len(agente.tableros_en_cola) == 0

        # Segundo tablero: al límite, debe encolarse
        presencia2 = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa2",
            status="finished",
            jid_real="tablero_mesa2@localhost/r",
        )
        agente._on_presencia_muc(presencia2)
        # No se debe haber llamado de nuevo a add_behaviour
        assert agente.add_behaviour.call_count == 1
        assert len(agente.tableros_en_cola) == 1

    def test_solicitar_siguiente_desencola(self, agente):
        """Al llamar a solicitar_siguiente_en_cola, el primer
        tablero de la cola debe procesarse y crear un FSM."""
        agente.max_fsm_concurrentes = 5
        agente.tableros_en_cola.append(
            ("tablero_encolado@localhost", "tictactoe"),
        )

        agente.solicitar_siguiente_en_cola()

        agente.add_behaviour.assert_called_once()
        assert len(agente.tableros_en_cola) == 0
        assert "tablero_encolado@localhost" \
            in agente.informes_pendientes

    def test_solicitar_siguiente_con_cola_vacia_no_hace_nada(
        self, agente,
    ):
        """Si la cola está vacía, solicitar_siguiente no debe
        crear ningún FSM."""
        agente.solicitar_siguiente_en_cola()
        agente.add_behaviour.assert_not_called()

    def test_solicitar_siguiente_respeta_limite(self, agente):
        """Si ya hay max FSMs activos, no debe desencolar aunque
        haya tableros en cola."""
        agente.max_fsm_concurrentes = 1
        agente.informes_pendientes["t1@localhost"] = "tictactoe"
        agente.tableros_en_cola.append(
            ("t2@localhost", "tictactoe"),
        )

        agente.solicitar_siguiente_en_cola()

        # No se crea FSM porque ya hay 1 activo (límite 1)
        agente.add_behaviour.assert_not_called()
        assert len(agente.tableros_en_cola) == 1

    def test_multiples_tableros_se_encolan_en_orden(self, agente):
        """Múltiples tableros que exceden el límite deben
        encolarse en orden FIFO."""
        agente.max_fsm_concurrentes = 1

        # Primer tablero: crea FSM
        presencia1 = _crear_presencia_muc(
            "tictactoe@conference.localhost", "tablero_mesa1",
            status="finished",
            jid_real="tablero_mesa1@localhost/r",
        )
        agente._on_presencia_muc(presencia1)

        # Segundo y tercer tablero: se encolan
        for i in (2, 3):
            presencia = _crear_presencia_muc(
                "tictactoe@conference.localhost",
                f"tablero_mesa{i}",
                status="finished",
                jid_real=f"tablero_mesa{i}@localhost/r",
            )
            agente._on_presencia_muc(presencia)

        assert len(agente.tableros_en_cola) == 2
        # El primero de la cola es mesa2
        jid_primero = agente.tableros_en_cola[0][0]
        assert "mesa2" in jid_primero


class TestDetenerConColaNoVacia:
    """Verifica que al detener el supervisor con tableros en
    cola, se registran advertencias."""

    @pytest.mark.asyncio
    async def test_registra_advertencia_por_encolados(self, agente):
        """Al detener el supervisor, cada tablero en la cola debe
        generar un evento LOG_ADVERTENCIA indicando que su informe
        nunca se solicitó."""
        agente.tableros_en_cola.append(
            ("tablero_cola1@localhost", "tictactoe"),
        )
        agente.tableros_en_cola.append(
            ("tablero_cola2@localhost", "tictactoe"),
        )

        await agente.detener_persistencia()

        # Buscar advertencias sobre tableros en cola
        eventos = agente.log_por_sala.get("tictactoe", [])
        advertencias_cola = [
            e for e in eventos
            if e["tipo"] == "advertencia"
            and "cola" in e["detalle"].lower()
        ]
        assert len(advertencias_cola) == 2
        assert len(agente.tableros_en_cola) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de reconexión automática a salas MUC (M-11)
# ═══════════════════════════════════════════════════════════════════════════

class TestReconexionMUC:
    """Verifica que los handlers de desconexión y reconexión
    funcionan correctamente."""

    def test_desconexion_activa_flag(self, agente):
        """Al recibir evento de desconexión, el flag de
        reconexión debe activarse."""
        assert agente._reconexion_activa is False
        agente._on_desconexion(None)
        assert agente._reconexion_activa is True

    def test_reconexion_rejoin_salas(self, agente):
        """Al reconectar la sesión, debe enviar joins MUC a
        todas las salas configuradas."""
        # Simular desconexión previa
        agente._on_desconexion(None)

        # Crear mock para _unirse_sala_muc
        agente._unirse_sala_muc = MagicMock()

        agente._on_reconexion_sesion(None)

        # Debe haberse llamado una vez por cada sala
        assert agente._unirse_sala_muc.call_count == len(
            agente.salas_muc,
        )

    def test_reconexion_registra_advertencia(self, agente):
        """La reconexión debe registrar una advertencia en el
        log de cada sala para la pestaña de Incidencias."""
        agente._on_desconexion(None)
        agente._unirse_sala_muc = MagicMock()

        agente._on_reconexion_sesion(None)

        # Buscar advertencias de reconexión
        for sala in agente.salas_muc:
            sala_id = sala["id"]
            eventos = agente.log_por_sala.get(sala_id, [])
            advertencias = [
                e for e in eventos
                if e["tipo"] == "advertencia"
                and "reconexión" in e["detalle"].lower()
            ]
            assert len(advertencias) >= 1

    def test_reconexion_sin_desconexion_previa_no_actua(
        self, agente,
    ):
        """Si no hubo desconexión, session_start no debe
        volver a unirse a las salas (es el primer arranque)."""
        agente._unirse_sala_muc = MagicMock()

        agente._on_reconexion_sesion(None)

        agente._unirse_sala_muc.assert_not_called()

    def test_reconexion_desactiva_flag(self, agente):
        """Tras reconectar, el flag debe desactivarse para
        no reconectar de nuevo en el próximo session_start."""
        agente._on_desconexion(None)
        agente._unirse_sala_muc = MagicMock()

        agente._on_reconexion_sesion(None)

        assert agente._reconexion_activa is False
