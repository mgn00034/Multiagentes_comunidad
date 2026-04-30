"""
Tests de integración del Agente Supervisor.

Estos tests arrancan agentes SPADE reales (supervisor + agentes
simulados) contra el servidor XMPP configurado en
``config/config.yaml`` para verificar el funcionamiento completo
del sistema en escenarios de laboratorio.

El servidor XMPP utilizado depende del ``perfil_activo`` de
``config.yaml``:

- **local**: Prosody en Docker (localhost:5222).
- **servidor**: Prosody de la asignatura (sinbad2.ujaen.es:8022).

Se puede forzar un perfil distinto al activo mediante la variable
de entorno ``XMPP_PERFIL``::

    # Usar el perfil que esté activo en config.yaml
    pytest tests/test_integracion_supervisor.py -v

    # Forzar perfil local (Docker)
    XMPP_PERFIL=local pytest tests/test_integracion_supervisor.py -v

    # Forzar perfil servidor (sinbad2.ujaen.es)
    XMPP_PERFIL=servidor pytest tests/test_integracion_supervisor.py -v

Si el servidor no está disponible, los tests se omiten
automáticamente.

Escenarios cubiertos:
- Partida con victoria, empate y abortada.
- Tablero que no responde (timeout).
- Respuesta con JSON inválido (ontología incorrecta).
- Entrada y salida de agentes en la sala MUC.
- Múltiples salas simultáneas.
- Protocolo de dos pasos (AGREE + INFORM).
- Tablero que rechaza la solicitud (REFUSE).
- Solicitudes duplicadas por redistribución (S-01/P-01).
- Ciclo completo de dos partidas consecutivas (S-01).
- Validaciones V8-V11: fichas desequilibradas, turns vs board,
  convención X-primero (P-07).
- Dos partidas idénticas con threads distintos (P-05).
- Jugador que abandona antes del informe (P-04).
"""

import asyncio
import logging
import os
import socket
import time

import aiohttp
import pytest

from agentes.agente_supervisor import AgenteSupervisor
from behaviours.supervisor_behaviours import (
    LOG_ADVERTENCIA,
    LOG_ENTRADA,
    LOG_ERROR,
    LOG_INCONSISTENCIA,
    LOG_SALIDA,
    LOG_SOLICITUD,
    LOG_TIMEOUT,
    TIMEOUT_RESPUESTA,
)
from config.configuracion import cargar_configuracion
from persistencia.almacen_supervisor import AlmacenSupervisor
from tests.simuladores.jugador_simulado import JugadorSimulado
from tests.simuladores.tablero_simulado import TableroSimulado
from utils import crear_agente, arrancar_agente

# ── Configuración del logging para los tests ─────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_integracion")


# ═══════════════════════════════════════════════════════════════
#  Carga de configuración XMPP desde config.yaml
# ═══════════════════════════════════════════════════════════════
# Se lee el perfil activo de config.yaml, salvo que la variable
# de entorno XMPP_PERFIL fuerce un perfil concreto. Esto permite
# ejecutar los tests tanto contra el servidor Docker local como
# contra el servidor de la asignatura (sinbad2.ujaen.es).

def _cargar_config_xmpp() -> dict:
    """Lee la configuración XMPP del perfil activo (o del perfil
    forzado por la variable de entorno ``XMPP_PERFIL``).

    Returns:
        Diccionario con la configuración del perfil XMPP resuelto.
    """
    config = cargar_configuracion()
    config_xmpp = config["xmpp"]

    # Si el usuario fuerza un perfil vía variable de entorno,
    # releer el fichero con ese perfil
    perfil_forzado = os.environ.get("XMPP_PERFIL", "")
    if perfil_forzado and perfil_forzado != config_xmpp.get("perfil"):
        import yaml
        with open("config/config.yaml", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        perfiles = raw.get("xmpp", {}).get("perfiles", {})
        if perfil_forzado in perfiles:
            config_xmpp = perfiles[perfil_forzado].copy()
            config_xmpp["perfil"] = perfil_forzado
            logger.info(
                "Perfil XMPP forzado por XMPP_PERFIL: %s",
                perfil_forzado,
            )

    return config_xmpp


CONFIG_XMPP = _cargar_config_xmpp()

# Información del perfil para los mensajes de log y skip
_PERFIL_NOMBRE = CONFIG_XMPP.get("perfil", "desconocido")
_XMPP_HOST = CONFIG_XMPP.get("host", "localhost")
_XMPP_PUERTO = CONFIG_XMPP.get("puerto", 5222)
_SERVICIO_MUC = CONFIG_XMPP.get(
    "servicio_muc", f"conference.{_XMPP_HOST}",
)

logger.info(
    "Tests de integración — perfil XMPP: '%s' (%s:%d)",
    _PERFIL_NOMBRE, _XMPP_HOST, _XMPP_PUERTO,
)


# ═══════════════════════════════════════════════════════════════
#  Verificación de disponibilidad del servidor XMPP
# ═══════════════════════════════════════════════════════════════

def _servidor_xmpp_disponible() -> bool:
    """Comprueba si el servidor XMPP del perfil activo acepta
    conexiones TCP en el host y puerto configurados."""
    disponible = False
    try:
        conexion = socket.create_connection(
            (_XMPP_HOST, _XMPP_PUERTO), timeout=5,
        )
        conexion.close()
        disponible = True
    except (ConnectionRefusedError, OSError):
        pass
    return disponible


pytestmark = pytest.mark.skipif(
    not _servidor_xmpp_disponible(),
    reason=(
        f"Servidor XMPP no disponible en "
        f"{_XMPP_HOST}:{_XMPP_PUERTO} "
        f"(perfil: {_PERFIL_NOMBRE})"
    ),
)


# ═══════════════════════════════════════════════════════════════
#  Constantes de temporización
# ═══════════════════════════════════════════════════════════════
# Tiempos más holgados para el perfil "servidor" (red UJA/VPN)
# que para Docker local, donde la latencia es mínima.

_ES_SERVIDOR_REMOTO = _PERFIL_NOMBRE == "servidor"

# Puerto del dashboard web para tests (distinto al de producción)
PUERTO_WEB_TEST = 10099

# Ruta del fichero SQLite para persistir los resultados de los tests
# de integración. Permite revisar después los informes y eventos con:
#   python supervisor_main.py --modo consulta --db data/integracion.db
RUTA_DB_INTEGRACION = "data/integracion.db"

# Tiempo de espera para que las presencias se propaguen (segundos)
PAUSA_PRESENCIA = 4 if _ES_SERVIDOR_REMOTO else 2

# Tiempo de espera para que el supervisor procese un informe
PAUSA_INFORME = 5 if _ES_SERVIDOR_REMOTO else 3

# Timeout de pytest para tests normales y para tests de timeout
TIMEOUT_TEST = 45 if _ES_SERVIDOR_REMOTO else 30
TIMEOUT_TEST_LARGO = 60 if _ES_SERVIDOR_REMOTO else 45


# ═══════════════════════════════════════════════════════════════
#  Utilidad: esperar una condición con timeout
# ═══════════════════════════════════════════════════════════════

async def esperar_condicion(condicion_fn, timeout=15, intervalo=0.5):
    """Espera activamente hasta que ``condicion_fn()`` devuelva
    ``True``, o lanza ``AssertionError`` si se agota el tiempo.

    Args:
        condicion_fn: Función sin argumentos que devuelve bool.
        timeout: Segundos máximos de espera.
        intervalo: Segundos entre comprobaciones.

    Raises:
        AssertionError: Si la condición no se cumple a tiempo.
    """
    inicio = time.time()
    cumplida = False
    while not cumplida and (time.time() - inicio) < timeout:
        if condicion_fn():
            cumplida = True
        else:
            await asyncio.sleep(intervalo)

    if not cumplida:
        raise AssertionError(
            f"Condición no cumplida tras {timeout} segundos",
        )


async def consultar_api_state(puerto_web: int) -> dict:
    """Consulta el endpoint /supervisor/api/state y devuelve
    el JSON de respuesta.

    Args:
        puerto_web: Puerto del dashboard web del supervisor.

    Returns:
        Diccionario con la respuesta JSON (claves: salas, timestamp).
    """
    url = f"http://localhost:{puerto_web}/supervisor/api/state"
    resultado = {}
    async with aiohttp.ClientSession() as sesion:
        async with sesion.get(url) as resp:
            if resp.status == 200:
                resultado = await resp.json()
    return resultado


# ═══════════════════════════════════════════════════════════════
#  Factoría de agentes para tests
# ═══════════════════════════════════════════════════════════════

def _nombre_unico(prefijo: str) -> str:
    """Genera un nombre de agente único basado en timestamp para
    evitar colisiones entre tests."""
    marca = int(time.time() * 1000) % 100000
    nombre = f"{prefijo}_{marca}"
    return nombre


async def _crear_supervisor(salas, puerto_web: int):
    """Crea y arranca un AgenteSupervisor configurado con
    descubrimiento manual para las salas indicadas.

    Args:
        salas: Nombre de una sala (str) o lista de nombres.
        puerto_web: Puerto para el dashboard web.

    Returns:
        Instancia del supervisor ya arrancada.
    """
    # Aceptar tanto un string como una lista
    lista_salas = [salas] if isinstance(salas, str) else list(salas)

    nombre = _nombre_unico("supervisor")
    supervisor = crear_agente(
        AgenteSupervisor, nombre, CONFIG_XMPP,
    )
    supervisor.config_xmpp = CONFIG_XMPP
    supervisor.config_parametros = {
        "intervalo_consulta": 5,
        "puerto_web": puerto_web,
        "ruta_db": RUTA_DB_INTEGRACION,
        "descubrimiento_salas": "manual",
        "salas_muc": lista_salas,
    }
    supervisor.config_llm = None
    await arrancar_agente(supervisor, CONFIG_XMPP)
    # Esperar a que se una a las salas MUC
    await asyncio.sleep(PAUSA_PRESENCIA)
    return supervisor


async def _crear_tablero(
    nick: str, sala_jid: str, modo: str = "victoria",
):
    """Crea y arranca un TableroSimulado.

    Args:
        nick: Apodo MUC del tablero.
        sala_jid: JID completo de la sala MUC.
        modo: Modo de respuesta a game-report.

    Returns:
        Instancia del tablero ya arrancada.
    """
    nombre = _nombre_unico(nick)
    tablero = crear_agente(
        TableroSimulado, nombre, CONFIG_XMPP,
    )
    tablero.nick = nick
    tablero.sala_jid = sala_jid
    tablero.modo_respuesta = modo
    await arrancar_agente(tablero, CONFIG_XMPP)
    await asyncio.sleep(PAUSA_PRESENCIA)
    return tablero


async def _crear_jugador(
    nick: str, sala_jid: str, nivel_estrategia: int = 1,
):
    """Crea y arranca un JugadorSimulado.

    Args:
        nick: Apodo MUC del jugador.
        sala_jid: JID completo de la sala MUC.
        nivel_estrategia: Nivel de estrategia simulado
            (1=Posicional, 2=Reglas, 3=Minimax, 4=LLM).

    Returns:
        Instancia del jugador ya arrancada.
    """
    nombre = _nombre_unico(nick)
    jugador = crear_agente(
        JugadorSimulado, nombre, CONFIG_XMPP,
    )
    jugador.nick = nick
    jugador.sala_jid = sala_jid
    jugador.nivel_estrategia = nivel_estrategia
    await arrancar_agente(jugador, CONFIG_XMPP)
    await asyncio.sleep(PAUSA_PRESENCIA)
    return jugador


async def _detener_agentes(*agentes):
    """Detiene una lista de agentes de forma segura, ignorando
    errores si alguno ya se desconectó.

    Si alguno de los agentes es un AgenteSupervisor, finaliza su
    persistencia antes de detenerlo para que la ejecución quede
    correctamente cerrada en la base de datos SQLite.
    """
    for agente in agentes:
        try:
            if hasattr(agente, "detener_persistencia"):
                await agente.detener_persistencia()
            await agente.stop()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  Fixture: sala de test con nombre único
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sala_test():
    """Genera un nombre de sala MUC único para cada test, usando
    el servicio MUC del perfil XMPP activo."""
    marca = int(time.time() * 1000) % 100000
    sala_id = f"test_sala_{marca}"
    sala_jid = f"{sala_id}@{_SERVICIO_MUC}"
    resultado = {"id": sala_id, "jid": sala_jid}
    return resultado


def _sala_descriptiva(nombre: str) -> dict:
    """Crea una sala con nombre significativo y sufijo único.

    Útil para que los logs y la BD reflejen qué escenario se
    está probando (ej: ``err_timeout_83021``).

    Args:
        nombre: Prefijo descriptivo del escenario de test.

    Returns:
        Diccionario con ``id`` y ``jid`` de la sala.
    """
    marca = int(time.time() * 1000) % 100000
    sala_id = f"{nombre}_{marca}"
    sala_jid = f"{sala_id}@{_SERVICIO_MUC}"
    resultado = {"id": sala_id, "jid": sala_jid}
    return resultado


# ═══════════════════════════════════════════════════════════════
#  Tests de integración
# ═══════════════════════════════════════════════════════════════

class TestPartidaNormal:
    """Verifica que el supervisor recibe correctamente los informes
    de partidas que terminan con normalidad."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_partida_victoria(self):
        """Un tablero que finaliza con victoria debe generar un
        informe con resultado 'win' en el supervisor."""
        sala = _sala_descriptiva("partida_victoria")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            # Simular ciclo de vida: waiting → playing → finished
            await tablero.cambiar_estado_muc("playing")
            await asyncio.sleep(1)
            await tablero.cambiar_estado_muc("finished")

            # Esperar a que el supervisor reciba el informe
            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informes = supervisor.informes_por_sala[sala_id]
            assert len(informes) == 1

            informe = list(informes.values())[0][-1]
            assert informe["result"] == "win"
            assert informe["winner"] == "X"
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_partida_empate(self):
        """Un tablero que finaliza en empate debe generar un
        informe con resultado 'draw'."""
        sala = _sala_descriptiva("partida_empate")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "empate",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informe = list(
                supervisor.informes_por_sala[sala_id].values(),
            )[0][-1]
            assert informe["result"] == "draw"
            assert informe["winner"] is None
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_partida_abortada(self):
        """Un tablero que envía un informe de partida abortada debe
        registrarlo con resultado 'aborted' y el motivo."""
        sala = _sala_descriptiva("partida_abortada")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "abortada",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informe = list(
                supervisor.informes_por_sala[sala_id].values(),
            )[0][-1]
            assert informe["result"] == "aborted"
            assert informe["reason"] == "both-timeout"
        finally:
            await _detener_agentes(tablero, supervisor)


class TestProtocoloDePasos:
    """Verifica el protocolo FIPA-Request con respuesta en dos
    pasos (AGREE seguido de INFORM)."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_agree_luego_inform(self):
        """Un tablero que responde primero con AGREE y luego con
        INFORM debe generar un informe válido."""
        sala = _sala_descriptiva("protocolo_dos_pasos")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "agree_luego_inform",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informes = supervisor.informes_por_sala[sala_id]
            assert len(informes) == 1
        finally:
            await _detener_agentes(tablero, supervisor)


class TestErrores:
    """Verifica que el supervisor gestiona correctamente los
    escenarios de error sin interrumpir su ejecución."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST_LARGO)
    async def test_timeout_sin_respuesta(self):
        """Si el tablero no responde al REQUEST, el supervisor
        debe registrar un evento de timeout en el log."""
        sala = _sala_descriptiva("err_timeout")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "timeout",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            # Esperar más que el TIMEOUT_RESPUESTA del FSM
            await esperar_condicion(
                lambda: any(
                    e["tipo"] == LOG_TIMEOUT
                    for e in supervisor.log_por_sala.get(
                        sala_id, [],
                    )
                ),
                timeout=TIMEOUT_RESPUESTA + 10,
            )

            # No debe haber informes almacenados
            informes = supervisor.informes_por_sala.get(
                sala_id, {},
            )
            assert len(informes) == 0
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_json_invalido(self):
        """Si el tablero envía un INFORM con JSON inválido, el
        supervisor no debe almacenar informe ni lanzar excepción,
        y debe registrar un evento de error en el log de la sala."""
        sala = _sala_descriptiva("err_json_invalido")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "json_invalido",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            # Esperar tiempo suficiente para que el FSM procese
            await asyncio.sleep(PAUSA_INFORME + 2)

            informes = supervisor.informes_por_sala.get(
                sala_id, {},
            )
            assert len(informes) == 0

            # Debe haber un evento de error en el log
            eventos_error = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_ERROR
            ]
            assert len(eventos_error) > 0
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_esquema_invalido(self):
        """Si el tablero envía un JSON válido pero con esquema
        incorrecto (campos obligatorios ausentes), el informe no
        debe almacenarse y debe registrar error en el log."""
        sala = _sala_descriptiva("err_esquema_invalido")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "esquema_invalido",
        )

        try:
            await tablero.cambiar_estado_muc("finished")
            await asyncio.sleep(PAUSA_INFORME + 2)

            informes = supervisor.informes_por_sala.get(
                sala_id, {},
            )
            assert len(informes) == 0

            # Debe haber un evento de error en el log
            eventos_error = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_ERROR
            ]
            assert len(eventos_error) > 0
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_refuse(self):
        """Si el tablero rechaza la solicitud con REFUSE, no debe
        almacenarse informe y debe registrarse una advertencia
        en el log con el motivo del rechazo."""
        sala = _sala_descriptiva("err_refuse")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "refuse",
        )

        try:
            await tablero.cambiar_estado_muc("finished")
            await asyncio.sleep(PAUSA_INFORME + 2)

            informes = supervisor.informes_por_sala.get(
                sala_id, {},
            )
            assert len(informes) == 0

            # Debe haber una advertencia en el log
            eventos_adv = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_ADVERTENCIA
            ]
            assert len(eventos_adv) > 0
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_informes_pendientes_al_detener(self):
        """Si el supervisor se detiene mientras hay solicitudes de
        informe en curso (FSM esperando respuesta del tablero),
        debe registrar un evento 'pendiente' en el log por cada
        informe solicitado y no recibido."""
        sala = _sala_descriptiva("err_pendiente_detener")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "timeout",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            # Esperar a que el supervisor envíe el REQUEST
            # (pero NO a que expire el timeout de 10 s del FSM)
            await esperar_condicion(
                lambda: any(
                    e["tipo"] == LOG_SOLICITUD
                    for e in supervisor.log_por_sala.get(
                        sala_id, [],
                    )
                ),
                timeout=TIMEOUT_RESPUESTA,
            )

            # Detener la persistencia mientras el informe sigue
            # pendiente (el tablero no responde y el timeout del
            # FSM aún no ha expirado)
            await supervisor.detener_persistencia()

            # Debe haberse registrado una advertencia
            eventos_adv = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_ADVERTENCIA
            ]
            assert len(eventos_adv) > 0
        finally:
            await _detener_agentes(tablero, supervisor)


class TestPresenciaMUC:
    """Verifica la detección de entradas, salidas y cambios de
    estado de los agentes en la sala MUC."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_entrada_de_agentes(self):
        """Cuando un jugador y un tablero se unen a la sala, el
        supervisor debe detectarlos como ocupantes."""
        sala = _sala_descriptiva("muc_entrada")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "timeout",
        )
        jugador = await _crear_jugador("jugador_ana", sala_jid)

        try:
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_id, []),
                ) >= 2,
            )

            ocupantes = supervisor.ocupantes_por_sala[sala_id]
            nicks = [o["nick"] for o in ocupantes]
            assert "tablero_mesa1" in nicks
            assert "jugador_ana" in nicks

            # Debe haber eventos de entrada en el log
            tipos_log = [
                e["tipo"]
                for e in supervisor.log_por_sala.get(sala_id, [])
            ]
            assert LOG_ENTRADA in tipos_log
        finally:
            await _detener_agentes(jugador, tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_salida_de_agente(self):
        """Cuando un jugador abandona la sala, el supervisor debe
        detectar su salida y registrar el evento."""
        sala = _sala_descriptiva("muc_salida")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        jugador = await _crear_jugador("jugador_luis", sala_jid)

        try:
            # Esperar a que el supervisor lo detecte
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_id, []),
                ) >= 1,
            )

            # El jugador abandona la sala
            await jugador.abandonar_sala()
            await asyncio.sleep(PAUSA_PRESENCIA)

            # El supervisor debe haber registrado la salida
            tipos_log = [
                e["tipo"]
                for e in supervisor.log_por_sala.get(sala_id, [])
            ]
            assert LOG_SALIDA in tipos_log
        finally:
            await _detener_agentes(jugador, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_cambio_estado_tablero_en_log(self):
        """Los cambios de estado del tablero (waiting → playing →
        finished) deben registrarse en el log del supervisor."""
        sala = _sala_descriptiva("muc_cambio_estado")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            await tablero.cambiar_estado_muc("playing")
            await asyncio.sleep(1)
            await tablero.cambiar_estado_muc("finished")

            # Esperar a que se procese el informe
            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # Buscar eventos de cambio de estado en el log
            eventos = supervisor.log_por_sala.get(sala_id, [])
            detalles = " ".join(e["detalle"] for e in eventos)
            assert "waiting" in detalles
            assert "playing" in detalles
        finally:
            await _detener_agentes(tablero, supervisor)


class TestMultiplesSalas:
    """Verifica el funcionamiento simultáneo con varias salas."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_dos_salas_independientes(self):
        """El supervisor debe gestionar dos salas de forma
        independiente, cada una con sus propios ocupantes e
        informes."""
        datos_a = _sala_descriptiva("multi_sala_a")
        datos_b = _sala_descriptiva("multi_sala_b")
        sala_a = datos_a["id"]
        sala_b = datos_b["id"]
        jid_a = datos_a["jid"]
        jid_b = datos_b["jid"]

        supervisor = await _crear_supervisor(
            [sala_a, sala_b], PUERTO_WEB_TEST,
        )

        tablero_a = await _crear_tablero(
            "tablero_mesa1", jid_a, "victoria",
        )
        tablero_b = await _crear_tablero(
            "tablero_mesa2", jid_b, "empate",
        )

        try:
            # Ambos tableros pasan a finished
            await tablero_a.cambiar_estado_muc("finished")
            await tablero_b.cambiar_estado_muc("finished")

            # Esperar informes en ambas salas
            await esperar_condicion(
                lambda: (
                    len(supervisor.informes_por_sala.get(
                        sala_a, {},
                    )) > 0
                    and len(supervisor.informes_por_sala.get(
                        sala_b, {},
                    )) > 0
                ),
            )

            informe_a = list(
                supervisor.informes_por_sala[sala_a].values(),
            )[0][-1]
            informe_b = list(
                supervisor.informes_por_sala[sala_b].values(),
            )[0][-1]

            # Cada sala tiene su propio resultado
            assert informe_a["result"] == "win"
            assert informe_b["result"] == "draw"
        finally:
            await _detener_agentes(
                tablero_a, tablero_b, supervisor,
            )


class TestAPIWeb:
    """Verifica que el dashboard web expone correctamente el
    estado del supervisor a través de la API HTTP."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_api_state_con_informe(self):
        """El endpoint /supervisor/api/state debe devolver los
        informes recibidos en formato JSON."""
        sala = _sala_descriptiva("api_informe")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # Consultar la API HTTP del dashboard
            url = (
                f"http://localhost:{PUERTO_WEB_TEST}"
                "/supervisor/api/state"
            )
            async with aiohttp.ClientSession() as sesion:
                async with sesion.get(url) as resp:
                    assert resp.status == 200
                    datos = await resp.json()

            # Buscar la sala de test en la respuesta
            sala_encontrada = None
            for sala in datos["salas"]:
                if sala["id"] == sala_id:
                    sala_encontrada = sala

            assert sala_encontrada is not None
            assert len(sala_encontrada["informes"]) == 1
            assert (
                sala_encontrada["informes"][0]["resultado"]
                == "victoria"
            )
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_api_state_con_ocupantes(self):
        """El endpoint /supervisor/api/state debe reflejar los
        ocupantes detectados en la sala MUC."""
        sala = _sala_descriptiva("api_ocupantes")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        jugador = await _crear_jugador("jugador_test", sala_jid)

        try:
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_id, []),
                ) >= 1,
            )

            url = (
                f"http://localhost:{PUERTO_WEB_TEST}"
                "/supervisor/api/state"
            )
            async with aiohttp.ClientSession() as sesion:
                async with sesion.get(url) as resp:
                    datos = await resp.json()

            sala_encontrada = None
            for sala in datos["salas"]:
                if sala["id"] == sala_id:
                    sala_encontrada = sala

            assert sala_encontrada is not None
            nicks = [
                o["nick"] for o in sala_encontrada["ocupantes"]
            ]
            assert "jugador_test" in nicks
        finally:
            await _detener_agentes(jugador, supervisor)


class TestVisibilidadProgresivaSalas:
    """Verifica que la API del dashboard solo devuelve salas con
    actividad y que estas aparecen progresivamente conforme los
    alumnos se incorporan a la sesión.

    Simula un escenario de laboratorio con 3 salas donde los
    alumnos se van incorporando en momentos distintos. Las salas
    sin actividad no deben aparecer en la respuesta de la API.
    Una sala que tuvo actividad debe seguir visible aunque los
    agentes se desconecten (porque conserva eventos en el log).
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_sala_sin_agentes_no_tiene_ocupantes(self):
        """Una sala donde nadie se ha conectado debe tener la
        lista de ocupantes vacía en la API."""
        sala = _sala_descriptiva("vis_sala_vacia")
        sala_vacia = sala["id"]

        supervisor = await _crear_supervisor(
            sala_vacia, PUERTO_WEB_TEST,
        )

        try:
            datos = await consultar_api_state(PUERTO_WEB_TEST)
            sala_encontrada = None
            for sala in datos["salas"]:
                if sala["id"] == sala_vacia:
                    sala_encontrada = sala

            assert sala_encontrada is not None
            assert len(sala_encontrada["ocupantes"]) == 0
        finally:
            await _detener_agentes(supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_salas_aparecen_conforme_se_unen_agentes(self):
        """Los alumnos se incorporan progresivamente. Cada sala
        debe aparecer con ocupantes solo cuando su primer agente
        se une, y las demás deben permanecer sin ocupantes
        hasta que les lleguen los suyos."""
        datos_a = _sala_descriptiva("vis_prog_a")
        datos_b = _sala_descriptiva("vis_prog_b")
        datos_c = _sala_descriptiva("vis_prog_c")
        sala_a = datos_a["id"]
        sala_b = datos_b["id"]
        sala_c = datos_c["id"]
        jid_a = datos_a["jid"]
        jid_b = datos_b["jid"]
        jid_c = datos_c["jid"]

        supervisor = await _crear_supervisor(
            [sala_a, sala_b, sala_c], PUERTO_WEB_TEST,
        )

        try:
            # ── Fase 1: nadie conectado ──────────────────────
            datos = await consultar_api_state(PUERTO_WEB_TEST)
            ids_con_ocupantes = [
                s["id"] for s in datos["salas"]
                if s["ocupantes"]
            ]
            assert len(ids_con_ocupantes) == 0

            # ── Fase 2: alumno se une a sala_a ───────────────
            jugador_a = await _crear_jugador(
                "jugador_alumno_a", jid_a,
            )
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_a, []),
                ) >= 1,
            )

            datos = await consultar_api_state(PUERTO_WEB_TEST)
            ids_con_ocupantes = [
                s["id"] for s in datos["salas"]
                if s["ocupantes"]
            ]
            assert sala_a in ids_con_ocupantes
            assert sala_b not in ids_con_ocupantes
            assert sala_c not in ids_con_ocupantes

            # ── Fase 3: alumno se une a sala_c (sala_b sigue
            #    vacía, sala_a ya tiene agente) ───────────────
            jugador_c = await _crear_jugador(
                "jugador_alumno_c", jid_c,
            )
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_c, []),
                ) >= 1,
            )

            datos = await consultar_api_state(PUERTO_WEB_TEST)
            ids_con_ocupantes = [
                s["id"] for s in datos["salas"]
                if s["ocupantes"]
            ]
            assert sala_a in ids_con_ocupantes
            assert sala_c in ids_con_ocupantes
            assert sala_b not in ids_con_ocupantes

            # ── Fase 4: alumno se une a sala_b (las 3 activas)
            jugador_b = await _crear_jugador(
                "jugador_alumno_b", jid_b,
            )
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_b, []),
                ) >= 1,
            )

            datos = await consultar_api_state(PUERTO_WEB_TEST)
            ids_con_ocupantes = [
                s["id"] for s in datos["salas"]
                if s["ocupantes"]
            ]
            assert sala_a in ids_con_ocupantes
            assert sala_b in ids_con_ocupantes
            assert sala_c in ids_con_ocupantes
        finally:
            await _detener_agentes(
                jugador_a, jugador_b, jugador_c, supervisor,
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_sala_persiste_tras_desconexion_agentes(self):
        """Cuando todos los agentes de una sala se desconectan, la
        sala debe seguir visible en la API porque conserva eventos
        de entrada y salida en su log."""
        sala = _sala_descriptiva("vis_desconexion")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        jugador = await _crear_jugador("jugador_efimero", sala_jid)

        try:
            # Esperar a que el supervisor detecte la entrada
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(sala_id, []),
                ) >= 1,
            )

            # El jugador abandona la sala
            await jugador.abandonar_sala()
            await asyncio.sleep(PAUSA_PRESENCIA)

            # La sala debe tener 0 ocupantes pero seguir visible
            # en la API porque tiene eventos en el log
            datos = await consultar_api_state(PUERTO_WEB_TEST)
            sala_encontrada = None
            for sala in datos["salas"]:
                if sala["id"] == sala_id:
                    sala_encontrada = sala

            assert sala_encontrada is not None
            assert len(sala_encontrada["ocupantes"]) == 0
            assert len(sala_encontrada["log"]) >= 2  # entrada + salida
        finally:
            await _detener_agentes(jugador, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_salas_sin_actividad_no_se_persisten(self):
        """Al detener el supervisor, solo las salas donde hubo
        actividad deben quedar en el almacén SQLite. Las salas
        configuradas pero sin eventos ni informes no se persisten,
        aunque sí se muestran en la interfaz en vivo."""
        sala = _sala_descriptiva("vis_activa")
        sala_activa = sala["id"]
        sala_jid = sala["jid"]

        marca = int(time.time() * 1000) % 100000
        sala_inactiva = f"vis_inactiva_{marca}"

        supervisor = await _crear_supervisor(
            [sala_activa, sala_inactiva], PUERTO_WEB_TEST,
        )
        jugador = await _crear_jugador("jugador_test", sala_jid)

        try:
            await esperar_condicion(
                lambda: len(
                    supervisor.ocupantes_por_sala.get(
                        sala_activa, [],
                    ),
                ) >= 1,
            )

            # La API en vivo debe mostrar las dos salas
            datos = await consultar_api_state(PUERTO_WEB_TEST)
            ids_api = [s["id"] for s in datos["salas"]]
            assert sala_activa in ids_api
            assert sala_inactiva in ids_api

            # Capturar el ID de ejecución antes de detener
            ejec_id = supervisor.almacen.ejecucion_id

            # Detener el supervisor (persiste y filtra salas)
            await supervisor.detener_persistencia()

            # Verificar en BD: solo la sala con actividad
            almacen_lectura = AlmacenSupervisor(
                RUTA_DB_INTEGRACION,
            )
            salas_persistidas = (
                almacen_lectura.obtener_salas_ejecucion(ejec_id)
            )
            almacen_lectura.cerrar()

            ids_persistidos = [
                s["id"] for s in salas_persistidas
            ]
            assert sala_activa in ids_persistidos
            assert sala_inactiva not in ids_persistidos
        finally:
            await _detener_agentes(jugador, supervisor)


class TestEscenariosLLM:
    """Verifica que el supervisor gestiona correctamente los
    escenarios donde algún jugador usa estrategia LLM (nivel 4).

    Los modelos LLM pueden causar dos tipos de fallo:
    - **Timeout**: el modelo no genera una respuesta a tiempo y
      el tablero aborta la partida.
    - **Movimiento inválido**: el modelo genera una respuesta que
      no corresponde a un movimiento válido y el tablero aborta.

    En ambos casos, el tablero envía un informe con
    ``result="aborted"`` y el motivo correspondiente. El supervisor
    debe almacenar el informe y reflejar el motivo en el dashboard.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_abortada_por_timeout_llm(self):
        """Cuando un jugador LLM no responde a tiempo, el tablero
        aborta con reason='timeout' y el rival gana. El supervisor
        debe almacenar el informe con el motivo correcto."""
        sala = _sala_descriptiva("llm_timeout")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "abortada_timeout_llm",
        )
        # Jugador normal y jugador con estrategia LLM
        jugador_normal = await _crear_jugador(
            "jugador_ana", sala_jid, nivel_estrategia=2,
        )
        jugador_ia = await _crear_jugador(
            "jugador_ia", sala_jid, nivel_estrategia=4,
        )

        try:
            await tablero.cambiar_estado_muc("playing")
            await asyncio.sleep(1)
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informe = list(
                supervisor.informes_por_sala[sala_id].values(),
            )[0][-1]
            assert informe["result"] == "aborted"
            assert informe["reason"] == "timeout"
            # El rival del jugador LLM gana
            assert informe["winner"] == "X"
        finally:
            await _detener_agentes(
                jugador_ia, jugador_normal, tablero, supervisor,
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_abortada_por_movimiento_invalido_llm(self):
        """Cuando un jugador LLM genera un movimiento inválido, el
        tablero aborta con reason='invalid'. El supervisor debe
        almacenar el informe con el motivo."""
        sala = _sala_descriptiva("llm_mov_invalido")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "abortada_movimiento_invalido",
        )
        jugador_ia = await _crear_jugador(
            "jugador_ia", sala_jid, nivel_estrategia=4,
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informe = list(
                supervisor.informes_por_sala[sala_id].values(),
            )[0][-1]
            assert informe["result"] == "aborted"
            assert informe["reason"] == "invalid"
        finally:
            await _detener_agentes(
                jugador_ia, tablero, supervisor,
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_ambos_jugadores_llm_timeout(self):
        """Cuando ambos jugadores LLM no responden, el tablero
        aborta con reason='both-timeout' y sin ganador. El
        supervisor debe almacenar el informe correctamente."""
        sala = _sala_descriptiva("llm_ambos_timeout")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        # Modo "abortada" ya usa both-timeout como motivo
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "abortada",
        )
        jugador_ia_x = await _crear_jugador(
            "jugador_ia_x", sala_jid, nivel_estrategia=4,
        )
        jugador_ia_o = await _crear_jugador(
            "jugador_ia_o", sala_jid, nivel_estrategia=4,
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informe = list(
                supervisor.informes_por_sala[sala_id].values(),
            )[0][-1]
            assert informe["result"] == "aborted"
            assert informe["reason"] == "both-timeout"
            assert informe["winner"] is None
        finally:
            await _detener_agentes(
                jugador_ia_x, jugador_ia_o, tablero, supervisor,
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_victoria_normal_contra_jugador_ia(self):
        """Una partida que termina con victoria normal donde uno de
        los jugadores usa estrategia LLM. El supervisor debe recibir
        un informe de victoria estándar."""
        sala = _sala_descriptiva("llm_victoria_normal")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )
        jugador_minimax = await _crear_jugador(
            "jugador_minimax", sala_jid, nivel_estrategia=3,
        )
        jugador_ia = await _crear_jugador(
            "jugador_ia", sala_jid, nivel_estrategia=4,
        )

        try:
            await tablero.cambiar_estado_muc("playing")
            await asyncio.sleep(1)
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            informe = list(
                supervisor.informes_por_sala[sala_id].values(),
            )[0][-1]
            assert informe["result"] == "win"

            # Verificar que ambos jugadores aparecen como ocupantes
            ocupantes = supervisor.ocupantes_por_sala.get(
                sala_id, [],
            )
            nicks = [o["nick"] for o in ocupantes]
            assert "jugador_minimax" in nicks
            assert "jugador_ia" in nicks
        finally:
            await _detener_agentes(
                jugador_ia, jugador_minimax, tablero, supervisor,
            )


class TestIncidenciasSemanticas:
    """Verifica que el supervisor detecta y registra como
    inconsistencias los informes con anomalías semánticas.

    Estos tests comprueban la validación cruzada que el supervisor
    aplica DESPUÉS de almacenar un informe que pasa el esquema de
    la ontología: turnos imposibles, tablero sin línea ganadora,
    jugador contra sí mismo, y jugadores no observados (D-04)."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_victoria_con_turnos_anomalos(self):
        """Un tablero que reporta una victoria con solo 2 turnos
        debe generar una inconsistencia de turnos imposibles.
        El informe se almacena (esquema válido) pero la anomalía
        se registra en el log."""
        sala = _sala_descriptiva("inc_turnos_anomalos")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria_turnos_anomalos",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # El informe debe haberse almacenado
            informes = supervisor.informes_por_sala[sala_id]
            assert len(informes) == 1

            # Debe haber al menos un evento de inconsistencia
            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            # El detalle debe mencionar los turnos
            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "turnos" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_victoria_sin_linea_ganadora(self):
        """Un tablero que reporta victoria pero cuyo tablero final
        no contiene línea ganadora debe generar inconsistencia."""
        sala = _sala_descriptiva("inc_sin_linea")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria_sin_linea",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "línea ganadora" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_jugador_contra_si_mismo(self):
        """Un informe donde players.X == players.O debe generar
        una inconsistencia de jugador contra sí mismo."""
        sala = _sala_descriptiva("inc_mismo_jugador")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "jugador_contra_si_mismo",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "mismo agente" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_empate_con_celdas_vacias(self):
        """Un empate declarado con celdas vacías en el tablero
        debe generar inconsistencia."""
        sala = _sala_descriptiva("inc_empate_vacias")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "empate_celdas_vacias",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "vacía" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_jugadores_no_observados_en_sala(self):
        """Si el tablero reporta jugadores que el supervisor no
        observó como ocupantes de la sala MUC, debe registrar
        una inconsistencia (validación cruzada D-04).

        En este test, el tablero envía un informe con jugadores
        de prueba (jugador_ana, jugador_luis) pero solo hay un
        tablero y un supervisor en la sala, sin jugadores reales."""
        sala = _sala_descriptiva("inc_jugadores_fantasma")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        # Solo el tablero está en la sala (sin jugadores reales)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "no fue observado" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_incidencias_visibles_en_api(self):
        """Las inconsistencias registradas en el log deben ser
        visibles a través del endpoint /supervisor/api/state para
        que la pestaña de Incidencias del panel las muestre."""
        sala = _sala_descriptiva("inc_api_visible")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria_turnos_anomalos",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # Consultar la API HTTP
            datos = await consultar_api_state(PUERTO_WEB_TEST)

            sala_encontrada = None
            for s in datos["salas"]:
                if s["id"] == sala_id:
                    sala_encontrada = s

            assert sala_encontrada is not None

            # El log debe contener eventos de inconsistencia
            eventos_inc = [
                e for e in sala_encontrada["log"]
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1
        finally:
            await _detener_agentes(tablero, supervisor)


class TestReintentoConRetroceso:
    """Verifica el mecanismo de reintento con retroceso exponencial
    (M-04). Usa un tablero simulado que ignora la primera solicitud
    y responde a la segunda."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST_LARGO)
    async def test_tablero_responde_en_segundo_intento(self):
        """Un tablero que no responde la primera vez pero sí la
        segunda debe generar un informe válido tras el reintento.
        El log debe contener un timeout parcial, una advertencia
        de reintento y una solicitud de reintento."""
        sala = _sala_descriptiva("reintento_ok")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        # Configurar 1 reintento con timeout corto (5 s)
        # para que el test no dure demasiado
        supervisor.timeout_respuesta = 5
        supervisor.max_reintentos = 1

        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid,
            "timeout_luego_victoria",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            # Esperar a que el supervisor reciba el informe
            # (timeout de 5 s + espera de reintento + respuesta)
            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(
                        sala_id, {},
                    ),
                ) > 0,
                timeout=TIMEOUT_RESPUESTA + 25,
            )

            # El informe debe haberse almacenado
            informes = supervisor.informes_por_sala[sala_id]
            assert len(informes) == 1
            informe = list(informes.values())[0][-1]
            assert informe["result"] == "win"

            # El log debe contener un timeout parcial
            eventos_log = supervisor.log_por_sala.get(
                sala_id, [],
            )
            tipos = [e["tipo"] for e in eventos_log]
            assert LOG_TIMEOUT in tipos
            # Debe haber una advertencia de reintento
            assert LOG_ADVERTENCIA in tipos
        finally:
            await _detener_agentes(tablero, supervisor)


class TestCargaMultiplesTableros:
    """Verifica que el supervisor gestiona correctamente múltiples
    tableros finalizando simultáneamente (D-16).

    Simula un escenario de torneo con 10 tableros en una sala.
    El límite de FSMs concurrentes obliga a encolar algunos."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST_LARGO)
    async def test_diez_tableros_simultaneos(self):
        """10 tableros finalizan casi simultáneamente. El
        supervisor debe recopilar los 10 informes sin pérdidas,
        aunque tenga que encolar algunos."""
        sala = _sala_descriptiva("carga_10")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        # Limitar FSMs para forzar el uso de la cola
        supervisor.max_fsm_concurrentes = 3

        tableros = []
        for i in range(10):
            tablero = await _crear_tablero(
                f"tablero_mesa{i}", sala_jid, "victoria",
            )
            tableros.append(tablero)

        try:
            # Todos los tableros finalizan
            for tablero in tableros:
                await tablero.cambiar_estado_muc("finished")
                await asyncio.sleep(0.3)

            # Esperar a que se reciban todos los informes
            await esperar_condicion(
                lambda: sum(
                    len(lista)
                    for lista
                    in supervisor.informes_por_sala.get(
                        sala_id, {},
                    ).values()
                ) >= 10,
                timeout=TIMEOUT_RESPUESTA + 40,
            )

            informes = supervisor.informes_por_sala.get(
                sala_id, {},
            )
            total = sum(len(v) for v in informes.values())
            assert total == 10

            # La cola debe estar vacía al final
            assert len(supervisor.tableros_en_cola) == 0
        finally:
            await _detener_agentes(*tableros, supervisor)


class TestEjecucionesPasadasCompleto:
    """Verifica el flujo completo de consultar una ejecución
    pasada a través del endpoint HTTP con filtrado de salas
    sin actividad (D-17)."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_ejecucion_pasada_filtra_salas_inactivas(self):
        """Al consultar una ejecución pasada, solo las salas que
        tuvieron actividad deben aparecer en la respuesta. Las
        salas configuradas pero sin eventos ni informes se
        descartan de la persistencia."""
        sala_activa = _sala_descriptiva("hist_activa")
        marca = int(time.time() * 1000) % 100000
        sala_inactiva_id = f"hist_inactiva_{marca}"

        sala_id = sala_activa["id"]
        sala_jid = sala_activa["jid"]

        supervisor = await _crear_supervisor(
            [sala_id, sala_inactiva_id], PUERTO_WEB_TEST,
        )
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(
                        sala_id, {},
                    ),
                ) > 0,
            )

            # Capturar ID de ejecución y detener persistencia
            ejec_id = supervisor.almacen.ejecucion_id
            await supervisor.detener_persistencia()

            # Consultar la ejecución pasada vía HTTP
            url = (
                f"http://localhost:{PUERTO_WEB_TEST}"
                f"/supervisor/api/ejecuciones/{ejec_id}"
            )
            async with aiohttp.ClientSession() as sesion:
                async with sesion.get(url) as resp:
                    assert resp.status == 200
                    datos = await resp.json()

            # Solo la sala activa debe aparecer
            ids_salas = [s["id"] for s in datos["salas"]]
            assert sala_id in ids_salas
            assert sala_inactiva_id not in ids_salas

            # La sala activa debe tener informes y log
            sala_datos = datos["salas"][0]
            assert len(sala_datos["informes"]) >= 1
            assert len(sala_datos["log"]) >= 1
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_csv_ejecucion_pasada(self):
        """El endpoint CSV de una ejecución pasada debe devolver
        datos coherentes con el estado almacenado."""
        sala = _sala_descriptiva("hist_csv")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(
            sala_id, PUERTO_WEB_TEST,
        )
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(
                        sala_id, {},
                    ),
                ) > 0,
            )

            ejec_id = supervisor.almacen.ejecucion_id
            await supervisor.detener_persistencia()

            # Consultar CSV de ranking
            url = (
                f"http://localhost:{PUERTO_WEB_TEST}"
                f"/supervisor/api/ejecuciones/{ejec_id}"
                f"/csv/ranking?sala={sala_id}"
            )
            async with aiohttp.ClientSession() as sesion:
                async with sesion.get(url) as resp:
                    assert resp.status == 200
                    texto = await resp.text()

            assert "alumno" in texto
            lineas = texto.strip().split("\n")
            # Cabecera + al menos 2 alumnos (ana y luis)
            assert len(lineas) >= 3
        finally:
            await _detener_agentes(tablero, supervisor)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de integración S-01: solicitudes duplicadas (P-01)
# ═══════════════════════════════════════════════════════════════════════════

class TestSolicitudesDuplicadasS01:
    """Verifica que la correccion S-01 evita solicitudes duplicadas
    de informes cuando el tablero permanece en status='finished'.

    Cubre los escenarios de redistribucion de presencia XMPP y de
    permanencia prolongada en 'finished' descritos en P-01."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_finished_no_genera_duplicados(self):
        """Un tablero que permanece en 'finished' solo debe generar
        un informe, no solicitudes duplicadas por redistribucion
        de presencia XMPP."""
        sala = _sala_descriptiva("s01_no_duplica")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # Solo debe haber 1 informe
            informes = supervisor.informes_por_sala[sala_id]
            assert len(informes) == 1

            # Contar solicitudes en el log: solo debe haber 1
            solicitudes = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_SOLICITUD
            ]
            assert len(solicitudes) == 1
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST_LARGO)
    async def test_ciclo_completo_dos_partidas(self):
        """Un tablero que juega dos partidas consecutivas
        (finished → waiting → playing → finished) debe generar
        exactamente dos informes, uno por cada partida."""
        sala = _sala_descriptiva("s01_dos_partidas")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            # Primera partida
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(
                        sala_id, {},
                    ).get(
                        list(
                            supervisor.informes_por_sala.get(
                                sala_id, {},
                            ).keys(),
                        )[0] if supervisor.informes_por_sala.get(
                            sala_id, {},
                        ) else "_",
                        [],
                    ),
                ) >= 1,
                timeout=20,
            )

            # Simular ciclo: volver a waiting, luego playing
            await tablero.cambiar_estado_muc("waiting")
            await asyncio.sleep(PAUSA_PRESENCIA)
            await tablero.cambiar_estado_muc("playing")
            await asyncio.sleep(PAUSA_PRESENCIA)

            # Segunda partida
            await tablero.cambiar_estado_muc("finished")

            # Esperar el segundo informe
            await asyncio.sleep(PAUSA_INFORME + 2)

            # Debe haber exactamente 2 solicitudes
            solicitudes = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_SOLICITUD
            ]
            assert len(solicitudes) == 2
        finally:
            await _detener_agentes(tablero, supervisor)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de integración: validaciones V8-V11 (P-07)
# ═══════════════════════════════════════════════════════════════════════════

class TestIncidenciasV8V11:
    """Verifica que el supervisor detecta las anomalias de
    equilibrio de fichas (V8/V10), coherencia turns vs board (V9)
    y convencion X-primero (V11) descritas en P-07."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_empate_fichas_desequilibradas_v8(self):
        """Un empate con 3X+6O (abs=3>1) debe generar una
        inconsistencia de distribucion de fichas imposible."""
        sala = _sala_descriptiva("v8_fichas_deseq")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid,
            "empate_fichas_desequilibradas",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "fichas" in detalles.lower() \
                or "distribuc" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_victoria_fichas_vs_turnos_v9(self):
        """Una victoria con 5 turnos pero solo 3 fichas en el
        tablero debe generar una inconsistencia."""
        sala = _sala_descriptiva("v9_fichas_turnos")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid,
            "victoria_fichas_vs_turnos",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "fichas" in detalles.lower() \
                or "turnos" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_empate_o_primero_v11(self):
        """Un empate con 4X+5O (O movio primero) debe generar
        una inconsistencia de convencion X-primero."""
        sala = _sala_descriptiva("v11_o_primero")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "empate_o_primero",
        )

        try:
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
            ]
            assert len(eventos_inc) >= 1

            detalles = " ".join(e["detalle"] for e in eventos_inc)
            assert "O" in detalles or "primero" in detalles.lower()
        finally:
            await _detener_agentes(tablero, supervisor)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de integración: duplicados por contenido (P-05)
# ═══════════════════════════════════════════════════════════════════════════

class TestDuplicadosPorContenidoP05:
    """Verifica que el supervisor no marca como duplicadas dos
    partidas que tienen el mismo resultado pero threads distintos
    (P-05). La deteccion de duplicados debe basarse en el thread,
    no en el contenido del informe."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST_LARGO)
    async def test_dos_partidas_identicas_no_son_duplicadas(self):
        """Dos partidas consecutivas con el mismo resultado, mismos
        jugadores y mismo tablero pero threads distintos no deben
        marcarse como duplicadas."""
        sala = _sala_descriptiva("p05_no_dup")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )

        try:
            # Primera partida
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # Ciclo completo para segunda partida
            await tablero.cambiar_estado_muc("waiting")
            await asyncio.sleep(PAUSA_PRESENCIA)
            await tablero.cambiar_estado_muc("playing")
            await asyncio.sleep(PAUSA_PRESENCIA)

            # Cambiar modo a segunda victoria identica
            tablero.modo_respuesta = "victoria_segunda_identica"
            await tablero.cambiar_estado_muc("finished")

            # Esperar el segundo informe
            await asyncio.sleep(PAUSA_INFORME + 2)

            # Verificar que no hay inconsistencia de duplicado
            eventos_inc = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
                and "duplicado" in e["detalle"].lower()
            ]
            assert len(eventos_inc) == 0
        finally:
            await _detener_agentes(tablero, supervisor)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de integración: jugador que abandona antes del informe (P-04)
# ═══════════════════════════════════════════════════════════════════════════

class TestJugadorAbandonaP04:
    """Verifica que el supervisor no genera falsos positivos cuando
    un jugador abandona la sala entre el fin de la partida y la
    recepcion del informe (P-04). El historico de ocupantes debe
    recordar al jugador aunque ya no este presente."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(TIMEOUT_TEST)
    async def test_jugador_que_abandona_no_genera_falso_positivo(
        self,
    ):
        """Un jugador que abandona la sala despues de que la partida
        termine pero antes de que el supervisor valide el informe
        no debe generar una inconsistencia de 'no observado'."""
        sala = _sala_descriptiva("p04_abandona")
        sala_id = sala["id"]
        sala_jid = sala["jid"]

        supervisor = await _crear_supervisor(sala_id, PUERTO_WEB_TEST)
        tablero = await _crear_tablero(
            "tablero_mesa1", sala_jid, "victoria",
        )
        # Crear ambos jugadores que aparecen en el informe del
        # tablero simulado (players: X=jugador_ana, O=jugador_luis)
        jugador_x = await _crear_jugador("jugador_ana", sala_jid)
        jugador_o = await _crear_jugador("jugador_luis", sala_jid)

        try:
            # Ambos jugadores presentes → registrados en historico
            await asyncio.sleep(PAUSA_PRESENCIA)

            # Jugador O abandona ANTES de que el tablero finalice
            await jugador_o.stop()
            await asyncio.sleep(PAUSA_PRESENCIA)

            # Ahora el tablero finaliza
            await tablero.cambiar_estado_muc("finished")

            await esperar_condicion(
                lambda: len(
                    supervisor.informes_por_sala.get(sala_id, {}),
                ) > 0,
            )

            # No debe haber inconsistencia de "no observado"
            # porque ambos jugadores fueron registrados en el
            # historico antes de que jugador_o abandonara
            eventos_no_obs = [
                e for e in supervisor.log_por_sala.get(
                    sala_id, [],
                )
                if e["tipo"] == LOG_INCONSISTENCIA
                and "observado" in e["detalle"].lower()
            ]
            assert len(eventos_no_obs) == 0
        finally:
            await _detener_agentes(
                jugador_x, tablero, supervisor,
            )
