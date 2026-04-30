import json
import logging
import time
from spade.behaviour import PeriodicBehaviour
from utils import log_mensaje_no_entendido
from ontologia.ontologia import crear_mensaje_join
from ontologia import validar_cuerpo


class BuscarTablero(PeriodicBehaviour):
    async def run(self) -> None:
        try:
            max_partidas = getattr(self.agent, 'MAX_PARTIDAS', 1)
            if len(self.agent.partidas_activas) >= max_partidas:
                return

            jid_destino = getattr(self.agent, 'tablero_objetivo', None)
            if jid_destino:
                self.agent.tablero_objetivo = None
                await self.inscribir(jid_destino)
                return

            sala_muc = getattr(self.agent, 'sala_muc', None)
            if sala_muc and hasattr(self.agent, 'muc'):
                try:
                    ocupantes = self.agent.muc.get_roster(sala_muc)
                except TypeError:
                    ocupantes = self.agent.muc.get_roster()

                for nick in ocupantes:
                    if nick.startswith("tablero_"):
                        jid_tablero = f"{sala_muc}/{nick}"
                        contacto = self.agent.presence.get_contact(jid_tablero)

                        if contacto and getattr(contacto, 'status', None) == "waiting":
                            await self.inscribir(jid_tablero)

        except Exception as e:
            logging.error(f"[JUGADOR {self.agent.jid.local}] Error general en BuscarTablero: {e}")

    async def inscribir(self, jid_destino: str) -> bool:
        origen_log = f"JUGADOR {self.agent.jid.local}"
        estado_actual = "BUSCANDO_PARTIDA"

        tableros_activos = [jid.split('/')[0] for jid in self.agent.partidas_activas.values()]
        base_destino = jid_destino.split('/')[0]

        if base_destino in tableros_activos:
            return False

        logging.info(f"[{origen_log}] Intentando unirse al tablero: {jid_destino}")

        peticion = crear_mensaje_join(jid_destino, str(self.agent.jid))
        hilo_partida = peticion.thread

        logging.info(f"[{origen_log}] 📤 Enviando REQUEST (join) a {peticion.to}")
        await self.send(peticion)

        tiempo_espera = 10.0
        tiempo_inicio = time.time()
        respuesta_procesada = False

        while (time.time() - tiempo_inicio) < tiempo_espera:
            respuesta = await self.receive(timeout=1.0)

            if respuesta:
                perf_log = respuesta.metadata.get("performative", "UNKNOWN").upper()
                logging.info(f"[{origen_log}] 📥 Recibido {perf_log} de {respuesta.sender}")

                if respuesta.thread == hilo_partida:
                    perf = respuesta.metadata.get("performative", "").upper().replace("_", "-")

                    if perf == "AGREE":
                        try:
                            datos = json.loads(respuesta.body)
                            validacion = validar_cuerpo(datos)
                            if not validacion["valido"]:
                                errores = ", ".join(validacion["errores"])
                                log_mensaje_no_entendido(origen_log, estado_actual, respuesta,
                                                         f"Esquema inválido: {errores}")
                                continue

                            simbolo = datos.get("symbol", "X")
                            logging.info(
                                f"[{origen_log}] ✅ ¡Unión ACEPTADA! Jugaremos como '{simbolo}'. Esperando game-start...")

                            if not hasattr(self.agent, "hilos_pendientes"):
                                self.agent.hilos_pendientes = {}
                            self.agent.hilos_pendientes[hilo_partida] = simbolo
                            return True

                        except json.JSONDecodeError:
                            log_mensaje_no_entendido(origen_log, estado_actual, respuesta, "JSON Inválido en AGREE")

                    elif perf == "REFUSE":
                        logging.warning(f"[{origen_log}] ❌ Unión RECHAZADA (sala llena o iniciada).")
                    else:
                        log_mensaje_no_entendido(origen_log, estado_actual, respuesta,
                                                 f"Performativa '{perf}' inesperada")

                    respuesta_procesada = True
                    break

        if not respuesta_procesada:
            logging.warning(f"[{origen_log}] ⏳ Timeout al inscribirse en {jid_destino}.")

        return respuesta_procesada