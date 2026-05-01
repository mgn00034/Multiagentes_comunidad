import logging
import asyncio
from spade.agent import Agent
from spade.template import Template
from spade.behaviour import FSMBehaviour
from muc_utils import configurar_muc

from behaviours.tablero_inscripcion import EstadoInscripcion, ESTADO_INSCRIPCION
from behaviours.tablero_jugando import EstadoJugando, ESTADO_JUGANDO
from behaviours.tablero_finalizado import EstadoFinalizado, ESTADO_FINALIZADO
from behaviours.tablero_reporte import MandarReporte


class FSMTablero(FSMBehaviour):
    pass


class AgenteTablero(Agent):
    def __init__(self, jid, password, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)
        self.id_tablero = str(jid).split('@')[0]
        self.jugadores = {}
        self.hilos = {}
        self.tablero = [""] * 9
        self.turno_actual = "X"
        self.historial = []
        self.estado_partida = "waiting"
        self.resultado_final = None
        self.ganador = None
        self.razon_fin = None
        self.historial_partidas = []

    def reiniciar_estado_partida(self):
        self.jugadores.clear()
        self.hilos.clear()
        self.tablero = [""] * 9
        self.turno_actual = "X"
        self.historial.clear()
        self.estado_partida = "waiting"
        self.resultado_final = None
        self.ganador = None
        self.razon_fin = None

    async def setup(self):
        sala = self.config_xmpp.get("sala_tictactoe", "tictactoe")
        servicio = self.config_xmpp.get("servicio_muc", "conference.localhost")
        self.sala_muc = f"{sala}@{servicio}"

        self.muc = configurar_muc(self, self.sala_muc, self.jid.local)
        await asyncio.sleep(1)

        t_join = Template()
        t_join.set_metadata("ontology", "tictactoe")
        t_join.set_metadata("performative", "request")
        t_join.set_metadata("conversation-id", "join")

        t_propose = Template()
        t_propose.set_metadata("ontology", "tictactoe")
        t_propose.set_metadata("performative", "propose")

        t_inform = Template()
        t_inform.set_metadata("ontology", "tictactoe")
        t_inform.set_metadata("performative", "inform")

        plantilla_fsm = t_join | t_propose | t_inform

        fsm = FSMTablero()
        fsm.add_state(name=ESTADO_INSCRIPCION, state=EstadoInscripcion(), initial=True)
        fsm.add_state(name=ESTADO_JUGANDO, state=EstadoJugando())
        fsm.add_state(name=ESTADO_FINALIZADO, state=EstadoFinalizado())

        fsm.add_transition(source=ESTADO_INSCRIPCION, dest=ESTADO_INSCRIPCION)
        fsm.add_transition(source=ESTADO_INSCRIPCION, dest=ESTADO_JUGANDO)
        fsm.add_transition(source=ESTADO_JUGANDO, dest=ESTADO_JUGANDO)
        fsm.add_transition(source=ESTADO_JUGANDO, dest=ESTADO_FINALIZADO)
        fsm.add_transition(source=ESTADO_FINALIZADO, dest=ESTADO_INSCRIPCION)

        self.add_behaviour(fsm, plantilla_fsm)

        plantilla_reporte = Template()
        plantilla_reporte.set_metadata("ontology", "tictactoe")
        plantilla_reporte.set_metadata("conversation-id", "game-report")
        plantilla_reporte.set_metadata("performative", "request")

        self.add_behaviour(MandarReporte(), plantilla_reporte)

        puerto_web = self.config_parametros.get("puerto_web", 10001)

        async def endpoint_estado_juego(request):
            return {
                "board_id": self.id_tablero,
                "status": getattr(self, "estado_partida", "waiting"),
                "players": {k: v.split('/')[0] for k, v in self.jugadores.items()},
                "current_turn": getattr(self, "turno_actual", "X"),
                "result": getattr(self, "resultado_final", None),
                "winner": getattr(self, "ganador", None),
                "history": getattr(self, "historial", []),
                "total_partidas_jugadas": len(getattr(self, "historial_partidas", [])),
                "partidas_pasadas": getattr(self, "historial_partidas", [])
            }

        try:
            self.web.start(port=puerto_web, templates_path="web/templates")
            self.web.add_get("/", endpoint_estado_juego, "index.html")
            self.web.add_get("/game", endpoint_estado_juego, "index.html")
            self.web.add_get("/game/state", endpoint_estado_juego, None)
            logging.info(f"[TABLERO {self.id_tablero}] 🌐 Interfaz web disponible en http://localhost:{puerto_web}/game")
        except Exception as e:
            logging.error(f"[TABLERO {self.id_tablero}] ❌ No se pudo arrancar la web en el puerto {puerto_web}: {e}")

        logging.info(f"[TABLERO {self.id_tablero}] Iniciado y listo para recibir peticiones (S-03).")