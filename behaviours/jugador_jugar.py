import json
import logging
import asyncio
import random
from spade.message import Message
from spade.behaviour import CyclicBehaviour

from utils import log_mensaje_no_entendido
from ontologia import (
    crear_cuerpo_move,
    crear_cuerpo_ok,
    validar_cuerpo,
    crear_cuerpo_turn_result
)


class Jugar(CyclicBehaviour):
    def __init__(self, jid_tablero: str, simbolo: str, hilo_inicial: str):
        super().__init__()
        self.jid_tablero = jid_tablero
        self.mi_simbolo = simbolo
        self.hilo_inicial = hilo_inicial
        self.tablero_interno = [""] * 9
        self.partida_activa = True
        self.turno_actual = ""

    async def run(self) -> None:
        try:
            if self.partida_activa:
                mensaje = await self.receive(timeout=5.0)
                origen_log = f"JUGADOR {self.agent.jid.local}"
                estado_actual = f"JUGANDO ({self.mi_simbolo})"

                if mensaje is not None:
                    perf_log = mensaje.metadata.get("performative", "UNKNOWN").upper()
                    logging.info(f"[{origen_log}] 📥 Recibido {perf_log} de {mensaje.sender}")

                    try:
                        cuerpo = json.loads(mensaje.body)
                        perf = mensaje.metadata.get("performative", "").upper().replace("_", "-")
                        accion = cuerpo.get("action", "")

                        if perf not in ("FAILURE", "REFUSE"):
                            validacion = validar_cuerpo(cuerpo)
                            if not validacion["valido"]:
                                errores = ", ".join(validacion["errores"])
                                log_mensaje_no_entendido(origen_log, estado_actual, mensaje,
                                                         f"Esquema inválido: {errores}")
                                return

                        if perf == "INFORM" and accion == "game-start":
                            logging.info(f"[{origen_log}] ¡Empezamos! Soy '{self.mi_simbolo}'.")

                        elif perf in ("FAILURE", "REFUSE"):
                            logging.warning(f"[{origen_log}] ❌ El tablero ha cerrado la mesa.")
                            self.finalizar_partida()

                        elif accion == "game-over" or perf == "REJECT-PROPOSAL":
                            razon = cuerpo.get("reason", "unknown")
                            ganador = cuerpo.get("winner", "None")
                            logging.info(
                                f"[{origen_log}] 🏁 PARTIDA ABORTADA por el Tablero. Razón: {razon} | Ganador: {ganador}")
                            self.finalizar_partida()

                        elif perf == "CFP" or accion == "turn":
                            self.turno_actual = cuerpo.get("symbol", cuerpo.get("active_symbol", self.mi_simbolo))
                            await self.gestionar_turno(self.turno_actual)

                        elif perf == "ACCEPT-PROPOSAL" or accion == "move-confirmed":
                            pos = cuerpo.get("position")
                            if pos is not None:
                                s = cuerpo.get("symbol", self.turno_actual)
                                if s:
                                    self.tablero_interno[pos] = s

                            estado_local = self.evaluar_estado_local()
                            await self.enviar_informe_resultado(estado_local)

                            if estado_local != "continue":
                                logging.info(
                                    f"[{origen_log}] 🏁 Detectado fin de partida ({estado_local}). Me retiro de la mesa.")
                                self.finalizar_partida()
                        else:
                            log_mensaje_no_entendido(origen_log, estado_actual, mensaje,
                                                     f"Mensaje no manejado. Perf: {perf}, Acción: {accion}")

                    except json.JSONDecodeError:
                        log_mensaje_no_entendido(origen_log, estado_actual, mensaje, "Cuerpo no es un JSON válido")
            else:
                self.kill()
        except Exception as e:
            logging.error(f"[JUGADOR] Error general crítico en el ciclo de juego: {e}")
            self.finalizar_partida()

    async def gestionar_turno(self, simbolo_activo: str) -> None:
        m = Message(to=self.jid_tablero)
        m.thread = self.hilo_inicial
        m.set_metadata("ontology", "tictactoe")

        if simbolo_activo == self.mi_simbolo:
            logging.info(f"[{self.agent.jid.local}] 🧠 Es MI TURNO ('{self.mi_simbolo}'). Pensando jugada...")
            pos = -1
            try:
                pos = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.agent.funcion_estrategia,
                        self.tablero_interno,
                        self.mi_simbolo,
                        config_llm=getattr(self.agent, "config_llm", None)
                    ),
                    timeout=20.0
                )
            except Exception as e_est:
                logging.warning(f"[{self.agent.jid.local}] Fallo estrategia. Forzando emergencia. {e_est}")
                pos = -1

            es_valida = pos is not None and type(pos) is int and 0 <= pos <= 8 and self.tablero_interno[pos] == ""
            if not es_valida:
                libres = [i for i, c in enumerate(self.tablero_interno) if c == ""]
                if libres: pos = random.choice(libres)

            if pos != -1:
                logging.info(f"[{self.agent.jid.local}] 🚀 Muevo a la casilla {pos}")
                contenido = crear_cuerpo_move(pos)
            else:
                contenido = crear_cuerpo_ok()

            m.set_metadata("performative", contenido.performativa)
            m.body = contenido.cuerpo
            logging.info(f"[JUGADOR {self.agent.jid.local}] 📤 Enviando {contenido.performativa.upper()} a {m.to}")
            await self.send(m)
        else:
            logging.info(f"[{self.agent.jid.local}] ⏳ Turno de '{simbolo_activo}'. Envío 'OK'.")

            contenido = crear_cuerpo_ok()
            m.set_metadata("performative", contenido.performativa)
            m.body = contenido.cuerpo

            logging.info(f"[JUGADOR {self.agent.jid.local}] 📤 Enviando {contenido.performativa.upper()} (OK) a {m.to}")
            await self.send(m)

    def evaluar_estado_local(self) -> str:
        t = self.tablero_interno
        lineas = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        for a, b, c in lineas:
            if t[a] != "" and t[a] == t[b] == t[c]: return "win"
        if "" not in t: return "draw"
        return "continue"

    async def enviar_informe_resultado(self, res: str) -> None:
        m = Message(to=self.jid_tablero)
        m.thread = self.hilo_inicial
        m.set_metadata("ontology", "tictactoe")

        ganador = self.turno_actual if res == "win" else None

        contenido = crear_cuerpo_turn_result(res, ganador)
        m.set_metadata("performative", contenido.performativa)
        m.body = contenido.cuerpo

        logging.info(
            f"[{self.agent.jid.local}] 📤 Enviando {contenido.performativa.upper()} (turn-result: '{res}') a {m.to}")
        await self.send(m)

    def finalizar_partida(self) -> None:
        if self.hilo_inicial in self.agent.partidas_activas:
            del self.agent.partidas_activas[self.hilo_inicial]
        self.partida_activa = False