import json
import logging
from spade.behaviour import CyclicBehaviour

from utils import log_mensaje_no_entendido
from ontologia import (
    crear_cuerpo_game_report,
    crear_cuerpo_game_report_refused,
    validar_cuerpo
)


class MandarReporte(CyclicBehaviour):

    async def run(self):
        msg = await self.receive(timeout=2.0)

        if msg:
            origen_log = f"TABLERO {self.agent.id_tablero}"
            estado_actual = getattr(self.agent, 'estado_fsm', 'N/A')
            conv_id = msg.metadata.get("conversation-id", "game-report")

            perf_log = msg.metadata.get("performative", "UNKNOWN").upper()
            logging.info(f"[{origen_log}] 📥 Recibido {perf_log} de {msg.sender}")

            try:
                cuerpo = json.loads(msg.body)

                if cuerpo.get("action") != "game-report":
                    return

                validacion = validar_cuerpo(cuerpo)

                if not validacion["valido"]:
                    errores_str = ", ".join(validacion["errores"])
                    log_mensaje_no_entendido(origen_log, estado_actual, msg, f"Ontología inválida - {errores_str}")

                    resp_err = msg.make_reply()
                    resp_err.set_metadata("conversation-id", conv_id)
                    resp_err.set_metadata("performative", "not-understood")
                    resp_err.set_metadata("ontology", "tictactoe")
                    resp_err.body = json.dumps({"error": f"Esquema invalido: {errores_str}"})

                    logging.info(f"[{origen_log}] 📤 Enviando NOT-UNDERSTOOD a {resp_err.to}")
                    await self.send(resp_err)
                    return

                logging.info(f"\033[92m[{origen_log}] 📩 Petición de reporte recibida de {msg.sender}\033[0m")

                partida_a_reportar = None
                if self.agent.historial_partidas:
                    ultima = self.agent.historial_partidas[-1]
                    if not ultima.get("report_sent", False):
                        partida_a_reportar = ultima

                if not partida_a_reportar:
                    resp = msg.make_reply()
                    resp.set_metadata("conversation-id", conv_id)
                    resp.set_metadata("performative", "refuse")
                    resp.set_metadata("ontology", "tictactoe")
                    resp.body = crear_cuerpo_game_report_refused()

                    logging.info(f"[{origen_log}] 📤 Enviando REFUSE (game-report) a {resp.to}")
                    await self.send(resp)
                    logging.warning(f"[{origen_log}] ❌ Reporte rechazado: no hay partida finalizada pendiente.")
                else:
                    inf = msg.make_reply()
                    inf.set_metadata("conversation-id", conv_id)
                    inf.set_metadata("performative", "inform")
                    inf.set_metadata("ontology", "tictactoe")

                    ganador_val = partida_a_reportar.get("winner")
                    if ganador_val == "None" or not ganador_val:
                        ganador_val = None

                    razon_val = partida_a_reportar.get("reason")
                    if partida_a_reportar["result"] != "aborted":
                        razon_val = None

                    turnos_jugados = len(partida_a_reportar["history"])
                    if turnos_jugados < 1:
                        turnos_jugados = 1

                    inf.body = crear_cuerpo_game_report(
                        resultado_partida=partida_a_reportar["result"],
                        ganador=ganador_val,
                        jugadores=partida_a_reportar["players"],
                        turnos=turnos_jugados,
                        tablero=partida_a_reportar["tablero"],
                        razon=razon_val
                    )

                    logging.info(f"[{origen_log}] 📤 Enviando INFORM (game-report) a {inf.to}")
                    await self.send(inf)

                    partida_a_reportar["report_sent"] = True
                    logging.info(f"[{origen_log}] ✅ Reporte enviado con éxito al supervisor.")

            except json.JSONDecodeError:
                resp_err = msg.make_reply()
                resp_err.set_metadata("conversation-id", conv_id)
                resp_err.set_metadata("performative", "not-understood")
                resp_err.set_metadata("ontology", "tictactoe")
                resp_err.body = json.dumps({"error": "JSON Invalido"})

                logging.info(f"[{origen_log}] 📤 Enviando NOT-UNDERSTOOD a {resp_err.to}")
                await self.send(resp_err)
            except Exception as e:
                logging.error(f"[{origen_log}] Error inesperado procesando petición de reporte: {e}")