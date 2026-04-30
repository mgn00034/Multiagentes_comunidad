import json
import logging
from spade.behaviour import CyclicBehaviour

class EsperarInicio(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=2.0)
        if msg:
            perf_log = msg.metadata.get("performative", "UNKNOWN").upper()
            logging.info(f"[JUGADOR {self.agent.jid.local}] 📥 Recibido {perf_log} (potencial game-start) de {msg.sender}")
            try:
                cuerpo = json.loads(msg.body)
                if cuerpo.get("action") == "game-start":
                    thread_partida = cuerpo.get("thread", msg.thread)
                    simbolo = getattr(self.agent, "hilos_pendientes", {}).get(msg.thread, "X")
                    self.agent.lanzar_partida(thread_partida, str(msg.sender), simbolo)
            except Exception:
                pass