import logging
import asyncio
from spade.agent import Agent
from spade.template import Template
from muc_utils import configurar_muc
from estrategia.estrategias import ESTRATEGIAS
from behaviours.jugador_buscar import BuscarTablero
from behaviours.jugador_jugar import Jugar
from behaviours.jugador_esperar_inicio import EsperarInicio
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s', datefmt="%H:%M:%S")



class AgenteJugador(Agent):

    def __init__(self, jid: str, password: str, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)
        self.config_parametros = {}
        self.config_xmpp = {}
        self.config_llm = {}
        self.config_sistema = {}
        self.partidas_activas = {}
        self.hilos_pendientes = {}
        self.tablero_objetivo = None
        self.MAX_PARTIDAS = 3

    async def setup(self) -> None:
        self.partidas_activas = {}
        self.hilos_pendientes = {}
        self.tablero_objetivo = None

        self.MAX_PARTIDAS = self.config_parametros.get("max_partidas", 3)
        est = self.config_parametros.get("nivel_estrategia", 1)
        self.funcion_estrategia = ESTRATEGIAS.get(est, ESTRATEGIAS[1])

        sala = self.config_xmpp.get("sala_tictactoe", "tictactoe")
        serv = self.config_xmpp.get("servicio_muc", "conference.localhost")
        self.sala_muc = f"{sala}@{serv}"

        self.muc = configurar_muc(self, self.sala_muc, self.jid.local)

        self.client.add_event_handler(f"muc::{self.sala_muc}::got_online", self.on_muc_occupant_joined)
        self.client.add_event_handler(f"muc::{self.sala_muc}::presence", self.on_muc_occupant_joined)

        await asyncio.sleep(0.5)

        periodo_busqueda = self.config_sistema.get("intervalo_busqueda_muc", 5.0)
        self.add_behaviour(BuscarTablero(period=periodo_busqueda))

        t_start = Template()
        t_start.set_metadata("ontology", "tictactoe")
        t_start.set_metadata("performative", "inform")
        self.add_behaviour(EsperarInicio(), t_start)

        logging.info(f"[JUGADOR] Agente {self.jid.local} listo. Estrategia nivel: {est}.")

    def on_muc_occupant_joined(self, presence):
        try:
            nick = presence['muc']['nick']
            estado = presence.get('status', '')

            if nick.startswith("tablero_"):
                if estado == "waiting":
                    if len(self.partidas_activas) < getattr(self, 'MAX_PARTIDAS', 1):
                        real_jid = presence['muc'].get('jid')
                        jid_objetivo = real_jid if real_jid else f"{self.sala_muc}/{nick}"
                        self.tablero_objetivo = str(jid_objetivo)
        except KeyError:
            pass

    def lanzar_partida(self, hilo: str, jid_tablero: str, simbolo: str) -> None:
        t = Template()
        t.thread = hilo
        t.set_metadata("ontology", "tictactoe")

        self.add_behaviour(Jugar(jid_tablero, simbolo, hilo), t)

        self.partidas_activas[hilo] = jid_tablero
        logging.info(f"[JUGADOR {self.jid.local}] ⚔️ Nueva partida en el hilo: {hilo}")