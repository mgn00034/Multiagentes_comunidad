import socket
import argparse
import asyncio
import importlib
import logging
import os
import random
import signal
import sys
import json
from typing import Any
from datetime import datetime

old_getaddrinfo = socket.getaddrinfo

def new_getaddrinfo(*args, **kwargs):
    if args[0] == 'localhost':
        return old_getaddrinfo('127.0.0.1', *args[1:], **kwargs)
    return old_getaddrinfo(*args, **kwargs)

socket.getaddrinfo = new_getaddrinfo

from spade.agent import Agent
from config.configuracion import (
    cargar_configuracion,
    cargar_plantillas,
    generar_agentes,
    cargar_torneos,
    construir_jid
)
from utils import crear_agente, arrancar_agente
from generador_informe import generar_informe_automatico

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lanzador del sistema Tic-Tac-Toe Multiagente")
    parser.add_argument("--config", default="config/config.yaml", help="Ruta al fichero de configuración")
    parser.add_argument("--agents", default="config/agents.yaml", help="Ruta al fichero de agentes")
    return parser.parse_args()


def importar_clase_agente(modulo_ruta: str, clase_nombre: str) -> type:
    try:
        modulo = importlib.import_module(modulo_ruta)
        return getattr(modulo, clase_nombre)
    except Exception as error:
        logger.error("No se pudo importar '%s': %s", modulo_ruta, error)
        raise


async def crear_salas_torneos(torneos: list[dict[str, Any]], config_xmpp: dict[str, Any]) -> dict[str, str]:
    asignaciones: dict[str, str] = {}
    if not torneos: return asignaciones

    salas_a_crear = []
    for torneo in torneos:
        sala = torneo.get("sala")
        if not sala: continue
        salas_a_crear.append(sala)
        for tablero in torneo.get("tableros", []): asignaciones[tablero] = sala
        for jugador in torneo.get("jugadores", []): asignaciones[jugador] = sala

    if not salas_a_crear: return asignaciones

    agente_temporal = crear_agente(Agent, "admin_salas_tmp", config_xmpp)
    await arrancar_agente(agente_temporal, config_xmpp)
    servicio_muc = config_xmpp.get("servicio_muc", "conference.localhost")

    for sala in salas_a_crear:
        jid_sala = f"{sala}@{servicio_muc}"
        agente_temporal.presence.subscribe(jid_sala)

    await asyncio.sleep(0.5)
    await agente_temporal.stop()
    return asignaciones


async def arrancar_sistema(ruta_config: str, ruta_agentes: str) -> None:
    hora_inicio_sistema = datetime.now().isoformat()

    logger.info("Cargando configuración desde: %s", ruta_config)
    config = cargar_configuracion(ruta_config)
    config_xmpp = config.get("xmpp", {})
    config_llm = config.get("llm", {})
    config_sistema = config.get("sistema", {})

    logging.getLogger().setLevel(getattr(logging, config_sistema.get("nivel_log", "INFO"), logging.INFO))

    ruta_torneos = config_sistema.get("ruta_torneos", "config/torneos.yaml")
    asignaciones_salas = {}
    if os.path.exists(ruta_torneos):
        torneos = cargar_torneos(ruta_torneos)
        asignaciones_salas = await crear_salas_torneos(torneos, config_xmpp)

    logger.info("Cargando plantillas de agentes desde: %s", ruta_agentes)
    plantillas = cargar_plantillas(ruta_agentes)
    definiciones = generar_agentes(config, plantillas)
    if not definiciones: return

    supervisores = [d for d in definiciones if d["clase"] == "AgenteSupervisor"]
    otros_agentes = [d for d in definiciones if d["clase"] != "AgenteSupervisor"]
    random.shuffle(otros_agentes)
    definiciones_ordenadas = supervisores + otros_agentes

    agentes_activos: list[Agent] = []
    evento_parada = asyncio.Event()

    for definicion in definiciones_ordenadas:
        try:
            clase_agente = importar_clase_agente(definicion["modulo"], definicion["clase"])
            agente = crear_agente(clase_agente, definicion["nombre"], config_xmpp)

            agente.config_parametros = definicion.get("parametros", {})
            agente.config_xmpp = config_xmpp
            agente.config_llm = config_llm
            agente.config_sistema = config_sistema

            if definicion["nombre"] in asignaciones_salas:
                agente.config_xmpp["sala_tictactoe"] = asignaciones_salas[definicion["nombre"]]

            await arrancar_agente(agente, config_xmpp)
            agentes_activos.append(agente)

            if definicion["clase"] == "AgenteSupervisor":
                if hasattr(agente, "web") and hasattr(agente.web, "app"):
                    agente.web.app["evento_parada"] = evento_parada
                    agente.web.app["modo"] = "torneo"

            logger.info("Agente '%s' arrancado (JID: %s)", definicion["nombre"], str(agente.jid))
            await asyncio.sleep(random.uniform(0.5, 1.0))
        except Exception as error:
            logger.error("Error arrancar agente '%s': %s", definicion["nombre"], error)

    if agentes_activos:
        logger.info("Sistema arrancado: %d agentes activos. Pulsa Ctrl+C para detener.", len(agentes_activos))

        def manejar_senal(signum: int, frame: Any = None) -> None:
            logger.info("Señal de parada recibida. Activando secuencia de apagado...")
            evento_parada.set()

        try:
            signal.signal(signal.SIGINT, manejar_senal)
            signal.signal(signal.SIGTERM, manejar_senal)
        except NotImplementedError:
            pass

        try:
            await evento_parada.wait()
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Iniciando secuencia de apagado. Generando informes...")

            todas_las_partidas = []
            agente_tablero_principal = None

            for agente in agentes_activos:
                if hasattr(agente, "historial_partidas") and agente.historial_partidas:
                    todas_las_partidas.extend(agente.historial_partidas)
                    if "tablero" in str(agente.jid).lower():
                        agente_tablero_principal = agente

            if todas_las_partidas:
                try:
                    puesto_id = "pc14"
                    if agente_tablero_principal:
                        try:
                            partes = str(agente_tablero_principal.jid).split('@')[0].split('_')
                            for p in partes:
                                if p.startswith("pc"): puesto_id = p
                        except:
                            pass

                    generar_informe_automatico(
                        partidas_brutas=todas_las_partidas,
                        equipo="Equipo_Tableros",
                        puesto=puesto_id,
                        hora_inicio=hora_inicio_sistema,
                        dominio_servidor="sinbad2.ujaen.es",
                        ruta_salida="informe_integracion.json"
                    )
                except Exception as e:
                    logger.error(f"Error crítico generando el informe: {e}")
            else:
                logger.warning("No se han encontrado partidas en el historial. No se generará el informe.")

            tareas_apagado = []
            for agente in agentes_activos:
                if hasattr(agente, "detener_persistencia"):
                    asyncio.create_task(agente.detener_persistencia())
                tareas_apagado.append(agente.stop())

            if tareas_apagado:
                try:
                    await asyncio.wait_for(asyncio.gather(*tareas_apagado), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.error("Cierre forzado: el apagado ha excedido el tiempo límite.")

            logger.info("Sistema detenido correctamente.")


def main() -> None:
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    argumentos = parsear_argumentos()
    try:
        asyncio.run(arrancar_sistema(argumentos.config, argumentos.agents))
    except KeyboardInterrupt:
        pass
    except Exception as error:
        logger.error("Error inesperado en main: %s", error)
        sys.exit(1)


if __name__ == "__main__":
    main()