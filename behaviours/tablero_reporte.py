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
            conv_id = msg.metadata.get("conversation-id", "game-report")

            # --- LOG ROJO DE RECEPCIÓN ---
            logging.info(f"\033[91m[REPORTE] 📥 ¡MENSAJE RECIBIDO DEL SUPERVISOR!\033[0m")
            logging.info(f"\033[91m[REPORTE] Cuerpo original: {msg.body}\033[0m")

            try:
                cuerpo = json.loads(msg.body)

                if cuerpo.get("action") != "game-report":
                    return

                # Si llegamos aquí, el JSON es válido. Buscamos partida...
                partida_a_reportar = None
                if self.agent.historial_partidas:
                    ultima = self.agent.historial_partidas[-1]
                    if not ultima.get("report_sent", False):
                        partida_a_reportar = ultima

                if not partida_a_reportar:
                    contenido = crear_cuerpo_game_report_refused()
                    resp = msg.make_reply()
                    resp.set_metadata("conversation-id", conv_id)
                    resp.set_metadata("performative", contenido.performativa)
                    resp.body = contenido.cuerpo
                    await self.send(resp)
                else:
                    ganador_val = partida_a_reportar.get("winner")
                    if ganador_val == "None" or not ganador_val: ganador_val = None
                    turnos_jugados = max(1, len(partida_a_reportar["history"]))

                    contenido = crear_cuerpo_game_report(
                        resultado_partida=partida_a_reportar["result"],
                        ganador=ganador_val,
                        jugadores=partida_a_reportar["players"],
                        turnos=turnos_jugados,
                        tablero=partida_a_reportar["tablero"],
                        razon=partida_a_reportar.get("reason") if partida_a_reportar["result"] == "aborted" else None
                    )

                    inf = msg.make_reply()
                    inf.set_metadata("conversation-id", conv_id)
                    inf.set_metadata("performative", contenido.performativa)
                    inf.body = contenido.cuerpo
                    await self.send(inf)
                    partida_a_reportar["report_sent"] = True
                    logging.info(f"\033[92m[{origen_log}] ✅ Reporte enviado con éxito.\033[0m")

            except json.JSONDecodeError:
                logging.error(f"\033[41m\033[37m[ERROR CRÍTICO] El Supervisor mandó algo que NO es JSON:\033[0m")
                logging.error(f"\033[91m{msg.body}\033[0m")

                resp_err = msg.make_reply()
                resp_err.set_metadata("performative", "not-understood")
                resp_err.body = json.dumps({"error": "JSON Invalido"})
                await self.send(resp_err)