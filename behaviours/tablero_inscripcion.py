import json
import logging
from spade.message import Message
from spade.behaviour import State

from utils import log_mensaje_no_entendido
from ontologia import (
    crear_cuerpo_join_accepted,
    crear_cuerpo_join_refused,
    crear_cuerpo_join_timeout,
    crear_cuerpo_game_start,
    validar_cuerpo,
    crear_thread_unico,
    PREFIJO_THREAD_GAME
)

ESTADO_INSCRIPCION = "ESTADO_INSCRIPCION"
ESTADO_JUGANDO = "ESTADO_JUGANDO"


class EstadoInscripcion(State):

    async def on_start(self):
        self.agent.estado_fsm = ESTADO_INSCRIPCION
        self.agent.client.send_presence(pto=f"{self.agent.sala_muc}/{self.agent.jid.local}", pstatus="waiting")
        logging.info(f"[TABLERO {self.agent.id_tablero}] ⏳ Esperando jugadores...")

    async def run(self) -> None:
        retorno = None
        siguiente_estado = ESTADO_INSCRIPCION
        origen_log = f"TABLERO {self.agent.id_tablero}"
        estado_actual = getattr(self.agent, 'estado_fsm', ESTADO_INSCRIPCION)

        try:
            timeout_cfg = self.agent.config_sistema.get("timeout_inscripcion", 60.0)
            timeout = timeout_cfg if len(self.agent.jugadores) == 1 else 20.0

            mensaje = await self.receive(timeout=timeout)

            if mensaje is not None:
                perf_log = mensaje.metadata.get("performative", "UNKNOWN").upper()
                logging.info(f"[{origen_log}] 📥 Recibido {perf_log} de {mensaje.sender}")
                try:
                    cuerpo = json.loads(mensaje.body)
                    accion = cuerpo.get("action", "")

                    validacion = validar_cuerpo(cuerpo)
                    if not validacion["valido"]:
                        errores = ", ".join(validacion["errores"])
                        log_mensaje_no_entendido(origen_log, estado_actual, mensaje, f"Esquema inválido: {errores}")

                        err_reply = mensaje.make_reply()
                        err_reply.set_metadata("performative", "not-understood")
                        err_reply.set_metadata("ontology", "tictactoe")
                        err_reply.body = json.dumps({"error": f"Esquema invalido: {errores}"})

                        logging.info(f"[{origen_log}] 📤 Enviando NOT-UNDERSTOOD a {err_reply.to}")
                        await self.send(err_reply)
                        self.set_next_state(ESTADO_INSCRIPCION)
                        return

                    if accion == "join":
                        siguiente_estado = await self.procesar_peticion_join(mensaje)
                    else:
                        log_mensaje_no_entendido(origen_log, estado_actual, mensaje,
                                                 f"Acción inesperada en inscripción: {accion}")

                except json.JSONDecodeError:
                    log_mensaje_no_entendido(origen_log, estado_actual, mensaje, "Cuerpo no es un JSON válido")
            else:
                if len(self.agent.jugadores) == 1:
                    await self.enviar_failure_timeout()
                    self.agent.reiniciar_estado_partida()
                    self.set_next_state(ESTADO_INSCRIPCION)
                    return

            self.set_next_state(siguiente_estado)
        except Exception as e:
            logging.error(f"[{origen_log}] Error en EstadoInscripcion: {e}")
            self.set_next_state(ESTADO_INSCRIPCION)

        return retorno

    async def procesar_peticion_join(self, mensaje: Message) -> str:
        retorno_estado = ESTADO_INSCRIPCION
        try:
            remitente = str(mensaje.sender).split('/')[0]
            respuesta = mensaje.make_reply()
            respuesta.set_metadata("ontology", "tictactoe")
            jugadores_base = [j.split('/')[0] for j in self.agent.jugadores.values()]

            if remitente in jugadores_base:
                simbolo_asignado = "X" if self.agent.jugadores.get("X", "").split('/')[0] == remitente else "O"
                contenido = crear_cuerpo_join_accepted(simbolo_asignado)
                respuesta.set_metadata("performative", contenido.performativa)
                respuesta.body = contenido.cuerpo

                logging.info(f"[TABLERO {self.agent.id_tablero}] 📤 Reenviando AGREE al jugador impaciente {remitente}")
                await self.send(respuesta)
                return ESTADO_JUGANDO if len(self.agent.jugadores) == 2 else ESTADO_INSCRIPCION

            if len(self.agent.jugadores) < 2:
                simbolo_asignado = "X" if len(self.agent.jugadores) == 0 else "O"
                self.agent.jugadores[simbolo_asignado] = str(mensaje.sender)
                self.agent.hilos[simbolo_asignado] = mensaje.thread

                contenido = crear_cuerpo_join_accepted(simbolo_asignado)
                respuesta.set_metadata("performative", contenido.performativa)
                respuesta.body = contenido.cuerpo

                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} (join-accepted) a {respuesta.to}")
                await self.send(respuesta)

                if len(self.agent.jugadores) == 2:
                    await self.iniciar_partida()
                    retorno_estado = ESTADO_JUGANDO

            else:
                contenido = crear_cuerpo_join_refused("full")
                respuesta.set_metadata("performative", contenido.performativa)
                respuesta.body = contenido.cuerpo

                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} (join-refused) a {respuesta.to}")
                await self.send(respuesta)

        except Exception as e:
            logging.error(f"[TABLERO] Error en procesar_peticion_join: {e}")

        return retorno_estado

    async def enviar_failure_timeout(self) -> None:
        try:
            if "X" in self.agent.jugadores:
                jid_jugador = self.agent.jugadores["X"]
                respuesta = Message(to=jid_jugador)
                respuesta.thread = self.agent.hilos.get("X", "timeout")
                respuesta.set_metadata("ontology", "tictactoe")

                # Cambios Tanda 2026-04-30: Uso de la tupla ContenidoMensaje
                contenido = crear_cuerpo_join_timeout("no opponent")
                respuesta.set_metadata("performative", contenido.performativa)
                respuesta.body = contenido.cuerpo

                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} (join-timeout) a {respuesta.to}")
                await self.send(respuesta)
        except Exception as e:
            logging.error(f"[TABLERO] Error en enviar_failure_timeout: {e}")

    async def iniciar_partida(self) -> None:
        try:
            self.agent.hilo_partida = crear_thread_unico(str(self.agent.jid), PREFIJO_THREAD_GAME)

            simbolos = ["X", "O"]
            for mi_simbolo in simbolos:
                simbolo_rival = "O" if mi_simbolo == "X" else "X"
                jid_destino = self.agent.jugadores[mi_simbolo]
                jid_rival = self.agent.jugadores[simbolo_rival]

                notificacion = Message(to=jid_destino)
                notificacion.thread = self.agent.hilos[mi_simbolo]
                notificacion.set_metadata("ontology", "tictactoe")

                contenido = crear_cuerpo_game_start(jid_rival, self.agent.hilo_partida)
                notificacion.set_metadata("performative", contenido.performativa)
                notificacion.body = contenido.cuerpo

                logging.info(
                    f"[TABLERO {self.agent.id_tablero}] 📤 Enviando {contenido.performativa.upper()} (game-start) a {notificacion.to}")
                await self.send(notificacion)

            self.agent.estado_partida = "playing"
            j_x = self.agent.jugadores['X'].split('/')[0]
            j_o = self.agent.jugadores['O'].split('/')[0]
            logging.info(f"\n[TABLERO {self.agent.id_tablero}] ⚔️ ¡PARTIDA INICIADA! X: {j_x} vs O: {j_o}\n")
        except Exception as e:
            logging.error(f"[TABLERO] Error al iniciar_partida: {e}")