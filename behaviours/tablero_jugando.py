import json
import logging
import time
import asyncio
from typing import List
from spade.message import Message
from spade.behaviour import State

from utils import log_mensaje_no_entendido
from ontologia import (
    crear_cuerpo_join_refused,
    crear_cuerpo_turn,
    crear_cuerpo_move_confirmado,
    crear_cuerpo_game_over,
    validar_cuerpo
)

ESTADO_JUGANDO = "ESTADO_JUGANDO"
ESTADO_FINALIZADO = "ESTADO_FINALIZADO"


class EstadoJugando(State):

    async def on_start(self):
        self.agent.estado_fsm = ESTADO_JUGANDO
        self.agent.client.send_presence(pto=f"{self.agent.sala_muc}/{self.agent.jid.local}", pstatus="playing")

    async def run(self) -> None:
        retorno = None
        siguiente_estado = ESTADO_FINALIZADO
        try:
            mensaje_residual = await self.receive(timeout=0.1)
            if mensaje_residual:
                perf_log = mensaje_residual.metadata.get("performative", "UNKNOWN").upper()
                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📥 Recibido mensaje residual ({perf_log}) de {mensaje_residual.sender}")
                try:
                    cuerpo = json.loads(mensaje_residual.body)
                    perf = mensaje_residual.metadata.get("performative", "").upper().replace("_", "-")
                    if validar_cuerpo(cuerpo)["valido"] and perf == "REQUEST" and cuerpo.get("action") == "join":
                        resp = mensaje_residual.make_reply()
                        resp.set_metadata("ontology", "tictactoe")

                        # Cambios Tanda 2026-04-30: Uso de la tupla ContenidoMensaje
                        contenido = crear_cuerpo_join_refused("game started")
                        resp.set_metadata("performative", contenido.performativa)
                        resp.body = contenido.cuerpo

                        logging.info(
                            f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} residual a {resp.to}")
                        await self.send(resp)
                except:
                    pass

            timeout_turno = self.agent.config_sistema.get("timeout_turno", 30.0)

            es_primer_turno = len(self.agent.historial) == 0
            max_intentos = 2 if es_primer_turno else 1
            propuestas = []

            for intento in range(max_intentos):
                await self.solicitar_movimientos()
                propuestas = await self.recolectar_respuestas("PROPOSE", timeout_turno, num_esperadas=2)

                if propuestas or not es_primer_turno:
                    break

                logging.warning(f"[TABLERO {self.agent.id_tablero}] Cortesía: Reintentando turno 1...")

            estado_movimiento, posicion = self.validar_propuestas(propuestas)

            if estado_movimiento == "missing":
                await self.finalizar_partida_por_error("timeout")
                siguiente_estado = ESTADO_FINALIZADO

            elif estado_movimiento == "invalid":
                rival = "O" if self.agent.turno_actual == "X" else "X"
                self.agent.ganador = rival
                self.agent.resultado_final = "win"
                self.agent.razon_fin = "invalid"
                await self.enviar_veredicto_movimiento("reject-proposal", razon="invalid")
                siguiente_estado = ESTADO_FINALIZADO

            elif estado_movimiento == "valid":
                self.agent.tablero[posicion] = self.agent.turno_actual
                self.agent.historial.append({"symbol": self.agent.turno_actual, "position": posicion})

                await self.enviar_veredicto_movimiento("accept-proposal", posicion)

                resultado_turno = await self.esperar_turn_results(timeout=5.0)

                if resultado_turno == "timeout":
                    await self.finalizar_partida_por_error("timeout")
                    siguiente_estado = ESTADO_FINALIZADO
                elif resultado_turno == "continue":
                    self.agent.turno_actual = "O" if self.agent.turno_actual == "X" else "X"
                    siguiente_estado = ESTADO_JUGANDO
                else:
                    self.agent.resultado_final = resultado_turno
                    self.agent.ganador = self.agent.turno_actual if resultado_turno == "win" else None
                    siguiente_estado = ESTADO_FINALIZADO

            self.set_next_state(siguiente_estado)

        except asyncio.CancelledError:
            logging.warning(f"[TABLERO {self.agent.id_tablero}] 🛑 Aborto externo. Guardando estado actual...")
            self.agent.resultado_final = "aborted"
            self.agent.razon_fin = "tournament-ended"
            registro_emergencia = {
                "id": f"Partida_{len(self.agent.historial_partidas) + 1}",
                "status": "finished",
                "result": "aborted",
                "winner": None,
                "reason": "tournament-ended",
                "players": {k: v.split('/')[0] for k, v in self.agent.jugadores.items()},
                "history": self.agent.historial.copy(),
                "tablero": self.agent.tablero.copy(),
                "report_sent": False
            }
            self.agent.historial_partidas.append(registro_emergencia)
            raise
        except Exception as e:
            logging.error(f"[TABLERO] Error en EstadoJugando: {e}")
            self.set_next_state(ESTADO_FINALIZADO)

        return retorno

    async def solicitar_movimientos(self) -> None:
        try:
            logging.info(f"[TABLERO {self.agent.id_tablero}] --- 📣 TURNO DE '{self.agent.turno_actual}' ---")
            for s in ["X", "O"]:
                jid_destino = self.agent.jugadores[s]
                cfp = Message(to=jid_destino)
                cfp.thread = self.agent.hilo_partida
                cfp.set_metadata("ontology", "tictactoe")

                # Cambios Tanda 2026-04-30: Uso de la tupla ContenidoMensaje
                contenido = crear_cuerpo_turn(self.agent.turno_actual)
                cfp.set_metadata("performative", contenido.performativa)
                cfp.body = contenido.cuerpo

                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} (turn) a {cfp.to}")
                await self.send(cfp)
        except Exception as e:
            logging.error(f"Error al solicitar turno: {e}")

    async def esperar_turn_results(self, timeout: float) -> str:
        tiempo_inicio = time.time()
        jugadores_esperados = [j.split('/')[0] for j in self.agent.jugadores.values()]
        origen_log = f"TABLERO {self.agent.id_tablero}"
        resultados = []

        while len(resultados) < 2 and (time.time() - tiempo_inicio) < timeout:
            tiempo_restante = timeout - (time.time() - tiempo_inicio)
            if tiempo_restante <= 0: break

            msg = await self.receive(timeout=tiempo_restante)
            if msg:
                perf_log = msg.metadata.get("performative", "UNKNOWN").upper()
                logging.info(f"[{origen_log}] 📥 Recibido {perf_log} de {msg.sender}")

                remitente = str(msg.sender).split("/")[0]
                if remitente not in jugadores_esperados:
                    continue

                try:
                    cuerpo = json.loads(msg.body)
                    perf = msg.metadata.get("performative", "").upper().replace("_", "-")

                    validacion = validar_cuerpo(cuerpo)
                    if not validacion["valido"]:
                        errores = ", ".join(validacion["errores"])
                        log_mensaje_no_entendido(origen_log, "ESPERANDO TURN-RESULT", msg,
                                                 f"Esquema inválido: {errores}")
                        continue

                    if perf == "INFORM" and cuerpo.get("action") == "turn-result":
                        resultados.append(cuerpo.get("result", "continue"))
                    else:
                        log_mensaje_no_entendido(origen_log, "ESPERANDO TURN-RESULT", msg,
                                                 f"Perf: {perf}, Acción: {cuerpo.get('action')}")

                except json.JSONDecodeError:
                    log_mensaje_no_entendido(origen_log, "ESPERANDO TURN-RESULT", msg, "JSON Inválido")

        if len(resultados) < 2: return "timeout"
        if "win" in resultados: return "win"
        if "draw" in resultados: return "draw"
        return "continue"

    async def recolectar_respuestas(self, performativa_esperada: str, tiempo_espera: float, num_esperadas: int = 2) -> \
    List[Message]:
        respuestas = []
        tiempo_inicio = time.time()
        jugadores_esperados = [j.split('/')[0] for j in self.agent.jugadores.values()]
        origen_log = f"TABLERO {self.agent.id_tablero}"

        while len(respuestas) < num_esperadas and (time.time() - tiempo_inicio) < tiempo_espera:
            tiempo_restante = tiempo_espera - (time.time() - tiempo_inicio)
            if tiempo_restante <= 0: break

            mensaje = await self.receive(timeout=tiempo_restante)
            if mensaje is not None:
                perf_log = mensaje.metadata.get("performative", "UNKNOWN").upper()
                logging.info(f"[{origen_log}] 📥 Recibido {perf_log} de {mensaje.sender}")

                remitente_base = str(mensaje.sender).split('/')[0]

                try:
                    cuerpo = json.loads(mensaje.body)
                    perf = mensaje.metadata.get("performative", "").upper().replace("_", "-")

                    if perf == "REQUEST" and cuerpo.get("action") == "join":
                        resp = mensaje.make_reply()
                        resp.set_metadata("ontology", "tictactoe")

                        contenido = crear_cuerpo_join_refused("game started")
                        resp.set_metadata("performative", contenido.performativa)
                        resp.body = contenido.cuerpo

                        logging.info(
                            f"[{origen_log}] 📤 Enviando {contenido.performativa.upper()} (late join) a {resp.to}")
                        await self.send(resp)
                        continue
                except:
                    pass

                if remitente_base not in jugadores_esperados: continue

                try:
                    cuerpo = json.loads(mensaje.body)
                    validacion = validar_cuerpo(cuerpo)
                    if not validacion["valido"]:
                        errores = ", ".join(validacion["errores"])
                        log_mensaje_no_entendido(origen_log, "RECOLECTANDO PROPUESTAS", mensaje,
                                                 f"Esquema inválido: {errores}")
                        continue

                    perf = mensaje.metadata.get("performative", "").upper().replace("_", "-")
                    perf_esp = performativa_esperada.upper().replace("_", "-")

                    if perf == perf_esp:
                        respuestas.append(mensaje)
                    else:
                        log_mensaje_no_entendido(origen_log, "RECOLECTANDO PROPUESTAS", mensaje,
                                                 f"Se esperaba {perf_esp}, llegó {perf}")

                except json.JSONDecodeError:
                    log_mensaje_no_entendido(origen_log, "RECOLECTANDO PROPUESTAS", mensaje, "JSON Inválido")

        return respuestas

    def validar_propuestas(self, propuestas: List[Message]) -> tuple[str, int]:
        jugador_esperado = self.agent.jugadores[self.agent.turno_actual].split("/")[0]
        estado = "missing"
        pos_final = -1

        for mensaje in propuestas:
            remitente_base = str(mensaje.sender).split("/")[0]
            try:
                cuerpo = json.loads(mensaje.body)
                if remitente_base == jugador_esperado and cuerpo.get("action") == "move":
                    pos_solicitada = cuerpo.get("position")
                    if pos_solicitada is not None and 0 <= pos_solicitada <= 8 and self.agent.tablero[
                        pos_solicitada] == "":
                        return "valid", pos_solicitada
                    else:
                        estado = "invalid"
            except:
                continue
        return estado, pos_final

    async def enviar_veredicto_movimiento(self, performativa: str, posicion: int = -1, razon: str = "") -> None:
        try:
            for simbolo in ["X", "O"]:
                jid_destino = self.agent.jugadores[simbolo]
                respuesta = Message(to=jid_destino)
                respuesta.thread = self.agent.hilo_partida
                respuesta.set_metadata("ontology", "tictactoe")

                if performativa.lower() == "accept-proposal":
                    contenido = crear_cuerpo_move_confirmado(posicion, self.agent.turno_actual)
                else:
                    razon_fin = razon if razon else "unknown"
                    contenido = crear_cuerpo_game_over(razon_fin, self.agent.ganador)

                respuesta.set_metadata("performative", contenido.performativa)
                respuesta.body = contenido.cuerpo

                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} a {respuesta.to}")
                await self.send(respuesta)
        except Exception as e:
            logging.error(f"Error al enviar veredicto: {e}")

    async def finalizar_partida_por_error(self, razon: str) -> None:
        try:
            self.agent.resultado_final = "aborted"
            self.agent.razon_fin = razon
            self.agent.ganador = None
            await self.enviar_veredicto_movimiento("reject-proposal", razon=razon)
        except:
            pass