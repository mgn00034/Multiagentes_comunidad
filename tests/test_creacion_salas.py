"""
Tests de creación y visibilidad de salas MUC para el supervisor.

Verifica que:
- ``crear_salas_torneos`` crea las salas definidas en torneos.yaml
  suscribiéndose correctamente a cada JID de sala MUC.
- El agente supervisor, en su ``setup()``, construye la lista de
  salas correctamente a partir de la configuración de torneos.
- Las salas creadas son visibles para el supervisor (aparecen en
  ``salas_muc``, ``informes_por_sala``, ``log_por_sala``, etc.).

Se prueban de forma aislada, sin arrancar SPADE ni conectarse a
un servidor XMPP real.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentes.agente_supervisor import AgenteSupervisor
from config.configuracion import cargar_torneos


# ═══════════════════════════════════════════════════════════════════════════
#  Datos de prueba
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_XMPP_TEST = {
    "host": "localhost",
    "puerto": 5222,
    "dominio": "localhost",
    "servicio_muc": "conference.localhost",
    "sala_tictactoe": "tictactoe",
    "password_defecto": "secret",
    "auto_register": True,
    "verify_security": False,
}

TORNEOS_LABORATORIO = [
    {"nombre": "pc01", "sala": "sala_pc01", "descripcion": "L2PC01",
     "tableros": [], "jugadores": []},
    {"nombre": "pc02", "sala": "sala_pc02", "descripcion": "L2PC02",
     "tableros": [], "jugadores": []},
    {"nombre": "pc03", "sala": "sala_pc03", "descripcion": "L2PC03",
     "tableros": [], "jugadores": []},
]

TORNEOS_CON_ASIGNACIONES = [
    {
        "nombre": "pc05",
        "sala": "sala_pc05",
        "descripcion": "L2PC05",
        "tableros": ["tablero_pc05_mesa1", "tablero_pc05_mesa2"],
        "jugadores": ["jugador_pc05_j01", "jugador_pc05_j02"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
#  Fixture: agente supervisor simulado
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def agente_supervisor():
    """Crea una instancia de AgenteSupervisor sin pasar por __init__
    de SPADE, inyectando los atributos que setup() necesita."""
    ag = object.__new__(AgenteSupervisor)
    ag.config_xmpp = dict(CONFIG_XMPP_TEST)
    ag.config_parametros = {
        "intervalo_consulta": 10,
        "puerto_web": 10090,
        "ruta_db": ":memory:",
    }
    ag.config_llm = None
    return ag


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de cargar_torneos
# ═══════════════════════════════════════════════════════════════════════════

class TestCargarTorneos:
    """Verifica que cargar_torneos lee correctamente el fichero de
    torneos y extrae los nombres de sala esperados."""

    def test_carga_torneos_laboratorio(self, tmp_path):
        """Debe cargar las 30 salas del fichero de torneos del
        laboratorio y cada una debe tener el campo 'sala' definido."""
        import shutil
        ruta_origen = "config/torneos.yaml"
        ruta_copia = tmp_path / "torneos.yaml"
        shutil.copy(ruta_origen, ruta_copia)

        torneos = cargar_torneos(str(ruta_copia))

        # El fichero real tiene 30 entradas (sala_pc01 a sala_pc30)
        assert len(torneos) == 30

    def test_cada_torneo_tiene_sala(self, tmp_path):
        """Cada entrada de torneos debe contener el campo 'sala' con
        el formato sala_pcNN."""
        import shutil
        ruta_copia = tmp_path / "torneos.yaml"
        shutil.copy("config/torneos.yaml", ruta_copia)

        torneos = cargar_torneos(str(ruta_copia))

        salas_encontradas = [t["sala"] for t in torneos]
        i = 0
        todas_correctas = True
        while i < len(salas_encontradas) and todas_correctas:
            esperado = f"sala_pc{(i + 1):02d}"
            if salas_encontradas[i] != esperado:
                todas_correctas = False
            i += 1

        assert todas_correctas

    def test_fichero_inexistente_devuelve_lista_vacia(self):
        """Si el fichero no existe, debe devolver lista vacía sin
        lanzar excepción."""
        resultado = cargar_torneos("/ruta/inexistente/torneos.yaml")
        assert resultado == []


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de crear_salas_torneos
# ═══════════════════════════════════════════════════════════════════════════

class TestCrearSalasTorneos:
    """Verifica que crear_salas_torneos suscribe al agente temporal
    a cada sala MUC definida en los torneos."""

    @pytest.mark.asyncio
    async def test_crea_salas_para_cada_torneo(self):
        """Debe llamar a presence.subscribe con el JID de cada sala
        definida en los torneos."""
        # Simular el agente temporal que crea las salas
        agente_mock = MagicMock()
        agente_mock.presence = MagicMock()
        agente_mock.stop = AsyncMock()

        with patch("utils.crear_agente", return_value=agente_mock), \
             patch("utils.arrancar_agente", new_callable=AsyncMock):

            from main import crear_salas_torneos
            await crear_salas_torneos(TORNEOS_LABORATORIO, CONFIG_XMPP_TEST)

        # Verificar que se suscribió a las 3 salas
        llamadas = agente_mock.presence.subscribe.call_args_list
        assert len(llamadas) == 3

        jids_suscritos = [str(c[0][0]) for c in llamadas]
        assert "sala_pc01@conference.localhost" in jids_suscritos
        assert "sala_pc02@conference.localhost" in jids_suscritos
        assert "sala_pc03@conference.localhost" in jids_suscritos

    @pytest.mark.asyncio
    async def test_devuelve_asignaciones_de_agentes(self):
        """Si los torneos definen tableros y jugadores, debe devolver
        un diccionario de asignaciones nombre→sala."""
        agente_mock = MagicMock()
        agente_mock.presence = MagicMock()
        agente_mock.stop = AsyncMock()

        with patch("utils.crear_agente", return_value=agente_mock), \
             patch("utils.arrancar_agente", new_callable=AsyncMock):

            from main import crear_salas_torneos
            asignaciones = await crear_salas_torneos(
                TORNEOS_CON_ASIGNACIONES, CONFIG_XMPP_TEST,
            )

        assert asignaciones["tablero_pc05_mesa1"] == "sala_pc05"
        assert asignaciones["tablero_pc05_mesa2"] == "sala_pc05"
        assert asignaciones["jugador_pc05_j01"] == "sala_pc05"
        assert asignaciones["jugador_pc05_j02"] == "sala_pc05"

    @pytest.mark.asyncio
    async def test_lista_vacia_no_crea_nada(self):
        """Con una lista vacía de torneos no debe crear el agente
        temporal ni suscribirse a ninguna sala."""
        from main import crear_salas_torneos
        asignaciones = await crear_salas_torneos([], CONFIG_XMPP_TEST)
        assert asignaciones == {}

    @pytest.mark.asyncio
    async def test_torneo_sin_campo_sala_se_ignora(self):
        """Un torneo sin campo 'sala' ni 'nombre' debe ignorarse
        sin provocar error."""
        agente_mock = MagicMock()
        agente_mock.presence = MagicMock()
        agente_mock.stop = AsyncMock()

        torneos_incompletos = [
            {"descripcion": "Torneo sin sala"},
        ]

        with patch("utils.crear_agente", return_value=agente_mock), \
             patch("utils.arrancar_agente", new_callable=AsyncMock):

            from main import crear_salas_torneos
            asignaciones = await crear_salas_torneos(
                torneos_incompletos, CONFIG_XMPP_TEST,
            )

        agente_mock.presence.subscribe.assert_not_called()
        assert asignaciones == {}


# ═══════════════════════════════════════════════════════════════════════════
#  Tests de visibilidad de salas en el supervisor
# ═══════════════════════════════════════════════════════════════════════════

class TestVisibilidadSalasEnSupervisor:
    """Verifica que el supervisor, tras su setup(), tiene las salas
    correctamente registradas en sus estructuras internas."""

    @pytest.mark.asyncio
    async def test_setup_registra_salas_descubiertas(self, agente_supervisor):
        """Cuando el descubrimiento automático devuelve salas, el
        supervisor debe registrarlas en salas_muc."""
        salas_descubiertas = ["sala_pc01", "sala_pc02", "sala_pc03"]

        with patch.object(
            AgenteSupervisor, "_descubrir_salas_muc",
            new_callable=AsyncMock, return_value=salas_descubiertas,
        ), \
             patch.object(
            AgenteSupervisor, "add_behaviour", new_callable=MagicMock,
        ), \
             patch("agentes.agente_supervisor.AlmacenSupervisor") as mock_alm, \
             patch("agentes.agente_supervisor.registrar_rutas_supervisor"):

            # Simular presence y web server de SPADE
            agente_supervisor.presence = MagicMock()
            agente_supervisor.web = MagicMock()
            agente_supervisor.web.app = {}
            agente_supervisor.client = MagicMock()
            agente_supervisor._unirse_sala_muc = MagicMock()

            await agente_supervisor.setup()

        # Verificar que se registraron las 3 salas
        assert len(agente_supervisor.salas_muc) == 3

        ids_salas = [s["id"] for s in agente_supervisor.salas_muc]
        assert "sala_pc01" in ids_salas
        assert "sala_pc02" in ids_salas
        assert "sala_pc03" in ids_salas

    @pytest.mark.asyncio
    async def test_setup_construye_jids_correctos(self, agente_supervisor):
        """Los JIDs de las salas deben construirse concatenando el
        nombre de la sala con el servicio MUC del perfil XMPP."""
        salas = ["sala_pc05", "sala_pc12"]

        with patch.object(
            AgenteSupervisor, "_descubrir_salas_muc",
            new_callable=AsyncMock, return_value=salas,
        ), \
             patch.object(
            AgenteSupervisor, "add_behaviour", new_callable=MagicMock,
        ), \
             patch("agentes.agente_supervisor.AlmacenSupervisor"), \
             patch("agentes.agente_supervisor.registrar_rutas_supervisor"):

            agente_supervisor.presence = MagicMock()
            agente_supervisor.web = MagicMock()
            agente_supervisor.web.app = {}
            agente_supervisor.client = MagicMock()
            agente_supervisor._unirse_sala_muc = MagicMock()

            await agente_supervisor.setup()

        jids = [s["jid"] for s in agente_supervisor.salas_muc]
        assert "sala_pc05@conference.localhost" in jids
        assert "sala_pc12@conference.localhost" in jids

    @pytest.mark.asyncio
    async def test_setup_inicializa_estructuras_por_sala(
        self, agente_supervisor,
    ):
        """Tras setup(), cada sala debe tener entrada en informes,
        ocupantes y log."""
        salas = ["sala_pc01", "sala_pc02"]

        with patch.object(
            AgenteSupervisor, "_descubrir_salas_muc",
            new_callable=AsyncMock, return_value=salas,
        ), \
             patch.object(
            AgenteSupervisor, "add_behaviour", new_callable=MagicMock,
        ), \
             patch("agentes.agente_supervisor.AlmacenSupervisor"), \
             patch("agentes.agente_supervisor.registrar_rutas_supervisor"):

            agente_supervisor.presence = MagicMock()
            agente_supervisor.web = MagicMock()
            agente_supervisor.web.app = {}
            agente_supervisor.client = MagicMock()
            agente_supervisor._unirse_sala_muc = MagicMock()

            await agente_supervisor.setup()

        # Estructuras de informes
        assert "sala_pc01" in agente_supervisor.informes_por_sala
        assert "sala_pc02" in agente_supervisor.informes_por_sala

        # Estructuras de ocupantes
        assert "sala_pc01" in agente_supervisor.ocupantes_por_sala
        assert "sala_pc02" in agente_supervisor.ocupantes_por_sala

        # Estructuras de log
        assert "sala_pc01" in agente_supervisor.log_por_sala
        assert "sala_pc02" in agente_supervisor.log_por_sala

    @pytest.mark.asyncio
    async def test_setup_se_une_a_cada_sala_muc(self, agente_supervisor):
        """El supervisor debe llamar a _unirse_sala_muc para cada
        sala descubierta, uniéndose a todas como ocupante MUC."""
        salas = ["sala_pc01", "sala_pc02", "sala_pc03"]

        with patch.object(
            AgenteSupervisor, "_descubrir_salas_muc",
            new_callable=AsyncMock, return_value=salas,
        ), \
             patch.object(
            AgenteSupervisor, "add_behaviour", new_callable=MagicMock,
        ), \
             patch("agentes.agente_supervisor.AlmacenSupervisor"), \
             patch("agentes.agente_supervisor.registrar_rutas_supervisor"):

            agente_supervisor.presence = MagicMock()
            agente_supervisor.web = MagicMock()
            agente_supervisor.web.app = {}
            agente_supervisor.client = MagicMock()
            agente_supervisor._unirse_sala_muc = MagicMock()

            await agente_supervisor.setup()

        llamadas = agente_supervisor._unirse_sala_muc.call_args_list
        jids_unidos = [str(c[0][0]) for c in llamadas]

        assert "sala_pc01@conference.localhost" in jids_unidos
        assert "sala_pc02@conference.localhost" in jids_unidos
        assert "sala_pc03@conference.localhost" in jids_unidos

    @pytest.mark.asyncio
    async def test_setup_modo_manual_usa_lista_configurada(
        self, agente_supervisor,
    ):
        """En modo manual, el supervisor debe usar la lista de salas
        explícita de config_parametros, sin llamar al descubrimiento."""
        agente_supervisor.config_parametros["descubrimiento_salas"] = "manual"
        agente_supervisor.config_parametros["salas_muc"] = [
            "sala_pc10", "sala_pc20",
        ]

        with patch.object(
            AgenteSupervisor, "_descubrir_salas_muc",
            new_callable=AsyncMock,
        ) as mock_descubrir, \
             patch.object(
            AgenteSupervisor, "add_behaviour", new_callable=MagicMock,
        ), \
             patch("agentes.agente_supervisor.AlmacenSupervisor"), \
             patch("agentes.agente_supervisor.registrar_rutas_supervisor"):

            agente_supervisor.presence = MagicMock()
            agente_supervisor.web = MagicMock()
            agente_supervisor.web.app = {}
            agente_supervisor.client = MagicMock()
            agente_supervisor._unirse_sala_muc = MagicMock()

            await agente_supervisor.setup()

        # No debe llamar al descubrimiento automático
        mock_descubrir.assert_not_called()

        ids_salas = [s["id"] for s in agente_supervisor.salas_muc]
        assert "sala_pc10" in ids_salas
        assert "sala_pc20" in ids_salas

    @pytest.mark.asyncio
    async def test_setup_sin_salas_usa_sala_por_defecto(
        self, agente_supervisor,
    ):
        """Si no se descubren ni configuran salas, el supervisor debe
        usar la sala por defecto del perfil XMPP."""
        with patch.object(
            AgenteSupervisor, "_descubrir_salas_muc",
            new_callable=AsyncMock, return_value=[],
        ), \
             patch.object(
            AgenteSupervisor, "add_behaviour", new_callable=MagicMock,
        ), \
             patch("agentes.agente_supervisor.AlmacenSupervisor"), \
             patch("agentes.agente_supervisor.registrar_rutas_supervisor"):

            agente_supervisor.presence = MagicMock()
            agente_supervisor.web = MagicMock()
            agente_supervisor.web.app = {}
            agente_supervisor.client = MagicMock()
            agente_supervisor._unirse_sala_muc = MagicMock()

            await agente_supervisor.setup()

        # Debe usar "tictactoe" (sala_tictactoe del perfil XMPP)
        assert len(agente_supervisor.salas_muc) == 1
        assert agente_supervisor.salas_muc[0]["id"] == "tictactoe"
