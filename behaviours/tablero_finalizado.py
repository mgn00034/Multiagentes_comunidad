import logging
import asyncio
from spade.behaviour import State
from spade.message import Message
from ontologia import crear_cuerpo_game_over

ESTADO_INSCRIPCION = "ESTADO_INSCRIPCION"
ESTADO_FINALIZADO = "ESTADO_FINALIZADO"


class EstadoFinalizado(State):
    async def run(self) -> None:
        try:
            self.agent.estado_fsm = ESTADO_FINALIZADO
            self.agent.estado_partida = "finished"

            self.agent.client.send_presence(pto=f"{self.agent.sala_muc}/{self.agent.jid.local}", pstatus="finished")

            razon_termino = getattr(self.agent, "razon_fin", None)

            registro_partida = {
                "id": f"Partida_{len(self.agent.historial_partidas) + 1}",
                "status": "finished",
                "result": self.agent.resultado_final,
                "winner": self.agent.ganador,
                "reason": razon_termino if razon_termino else "normal",
                "players": {k: v.split('/')[0] for k, v in self.agent.jugadores.items()},
                "history": self.agent.historial.copy(),
                "tablero": self.agent.tablero.copy(),
                "report_sent": False
            }
            self.agent.historial_partidas.append(registro_partida)

            if self.agent.resultado_final == "aborted":
                for simbolo, jid_jugador in self.agent.jugadores.items():
                    hilo = self.agent.hilos.get(simbolo)
                    if hilo:
                        msg = Message(to=jid_jugador)
                        msg.thread = hilo
                        msg.set_metadata("performative", "reject-proposal")
                        msg.set_metadata("ontology", "tictactoe")

                        razon_fin = razon_termino if razon_termino and razon_termino not in ["finished",
                                                                                             "normal"] else "unknown"
                        contenido = crear_cuerpo_game_over(razon_fin, self.agent.ganador)
                        msg.set_metadata("performative", contenido.performativa)
                        msg.body = contenido.cuerpo

                        logging.info(f"[TABLERO {self.agent.id_tablero}] 📤 Enviando REJECT-PROPOSAL (game-over abortado) a {msg.to}")
                        await self.send(msg)

            logging.info(f"\n============================================================")
            logging.info(f"🎯 RESUMEN FINAL - {registro_partida['id']}")
            logging.info(f"============================================================")
            logging.info(f"Resultado: {str(self.agent.resultado_final).upper()}")
            if self.agent.resultado_final == "win":
                j_ganador = self.agent.jugadores[self.agent.ganador].split('/')[0]
                logging.info(f"🏆 ¡EL GANADOR ES '{self.agent.ganador}'! ({j_ganador})")
            elif self.agent.resultado_final == "aborted":
                logging.info(f"❌ Partida ABORTADA. Motivo: {razon_termino}")
            else:
                logging.info(f"🤝 ¡EMPATE!")
            logging.info(f"Turnos jugados: {len(self.agent.historial)}")
            logging.info(f"============================================================\n")

            logging.info(f"[TABLERO {self.agent.id_tablero}] ⏳ Mostrando resultado 5s antes de reiniciar...")
            await asyncio.sleep(5.0)

            self.agent.reiniciar_estado_partida()
            self.set_next_state(ESTADO_INSCRIPCION)

        except Exception as e:
            logging.error(f"[TABLERO] Error crítico en EstadoFinalizado: {e}")
            self.agent.reiniciar_estado_partida()
            self.set_next_state(ESTADO_INSCRIPCION)