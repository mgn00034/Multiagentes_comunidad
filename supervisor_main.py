"""
Lanzador independiente del Agente Supervisor.

Permite al profesor ejecutar el supervisor en tres modos distintos:

- **consulta**: Solo arranca el dashboard web para revisar ejecuciones
  pasadas almacenadas en la base de datos SQLite. No requiere conexión
  XMPP ni activa comportamientos de descubrimiento o comunicación.

- **laboratorio**: Crea una sala MUC por cada puesto del laboratorio
  (L2PC01 a L2PC30) y monitoriza todas simultáneamente. Usa el fichero
  ``config/salas_laboratorio.yaml``.

- **torneo**: Crea una única sala MUC compartida donde todos los
  alumnos conectan sus agentes. Usa el fichero
  ``config/sala_torneo.yaml``.

Uso::

    python supervisor_main.py --modo consulta
    python supervisor_main.py --modo laboratorio
    python supervisor_main.py --modo torneo
    python supervisor_main.py --modo torneo --db data/torneo.db
"""

import argparse
import asyncio
import logging
import signal
import sys
import webbrowser
from typing import Any

from aiohttp import web

from agentes.agente_supervisor import AgenteSupervisor
from persistencia.almacen_supervisor import AlmacenSupervisor
from utils import cargar_configuracion, cargar_torneos, crear_agente, arrancar_agente
from web.supervisor_handlers import registrar_rutas_supervisor

# ── Configuración global del logging ───────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supervisor_main")

# ── Valores por defecto ──────────────────────────────────────
INTERVALO_CONSULTA_DEFECTO = 10
PUERTO_WEB_DEFECTO = 10090

# Ficheros de salas asociados a cada modo
FICHERO_SALAS = {
    "laboratorio": "config/salas_laboratorio.yaml",
    "torneo": "config/sala_torneo.yaml",
}


def _registrar_senales_parada(
    bucle: asyncio.AbstractEventLoop,
    evento_parada: asyncio.Event,
    mensaje: str,
) -> None:
    """Registra manejadores de SIGINT/SIGTERM de forma multiplataforma.

    En Unix/macOS se usa ``loop.add_signal_handler``, que permite
    gestionar señales directamente dentro del bucle asyncio.
    En Windows esa API no está disponible, por lo que se recurre a
    ``signal.signal`` con ``call_soon_threadsafe`` para activar el
    evento de parada de forma segura desde el hilo de la señal.

    Args:
        bucle: Bucle de eventos asyncio en ejecución.
        evento_parada: Evento que se activará al recibir la señal.
        mensaje: Texto descriptivo para el log al recibir la señal.
    """
    if sys.platform != "win32":
        # Unix/macOS — add_signal_handler es la forma recomendada
        def _senal_unix() -> None:
            logger.info("Señal de parada recibida. %s", mensaje)
            evento_parada.set()

        bucle.add_signal_handler(signal.SIGINT, _senal_unix)
        bucle.add_signal_handler(signal.SIGTERM, _senal_unix)
    else:
        # Windows — signal.signal como alternativa; se usa
        # call_soon_threadsafe porque el handler se ejecuta en el
        # hilo principal, fuera del bucle asyncio.
        def _senal_windows(_signum: int, _frame: Any) -> None:
            logger.info("Señal de parada recibida. %s", mensaje)
            bucle.call_soon_threadsafe(evento_parada.set)

        signal.signal(signal.SIGINT, _senal_windows)


def parsear_argumentos() -> argparse.Namespace:
    """Parsea los argumentos de línea de órdenes.

    Returns:
        Namespace con los argumentos: modo, config, intervalo, db,
        puerto.
    """
    parser = argparse.ArgumentParser(
        description="Lanzador independiente del Agente Supervisor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modos disponibles:\n"
            "  consulta      Solo dashboard web para revisar "
            "ejecuciones pasadas\n"
            "  laboratorio   Una sala MUC por puesto "
            "(config/salas_laboratorio.yaml)\n"
            "  torneo        Sala MUC única compartida "
            "(config/sala_torneo.yaml)\n"
        ),
    )
    parser.add_argument(
        "--modo",
        choices=["consulta", "laboratorio", "torneo"],
        required=True,
        help="Modo de ejecución del supervisor",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Ruta al fichero de configuración (default: config/config.yaml)",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=INTERVALO_CONSULTA_DEFECTO,
        help=(
            "Intervalo en segundos entre consultas MUC "
            f"(default: {INTERVALO_CONSULTA_DEFECTO})"
        ),
    )
    parser.add_argument(
        "--db",
        default="data/supervisor.db",
        help=(
            "Ruta al fichero SQLite de persistencia "
            "(default: data/supervisor.db)"
        ),
    )
    parser.add_argument(
        "--puerto",
        type=int,
        default=PUERTO_WEB_DEFECTO,
        help=(
            "Puerto del dashboard web "
            f"(default: {PUERTO_WEB_DEFECTO})"
        ),
    )
    argumentos = parser.parse_args()
    return argumentos


# ══════════════════════════════════════════════════════════════════
#  Modo consulta — solo dashboard web con datos históricos
# ══════════════════════════════════════════════════════════════════

async def ejecutar_modo_consulta(ruta_db: str, puerto: int) -> None:
    """Arranca únicamente el dashboard web para consultar ejecuciones
    pasadas. No conecta con el servidor XMPP ni activa behaviours.

    Args:
        ruta_db: Ruta al fichero SQLite con los datos históricos.
        puerto: Puerto en el que escuchará el servidor web.
    """
    logger.info(
        "Modo CONSULTA — solo dashboard web (sin conexión XMPP)",
    )
    logger.info("Base de datos: %s", ruta_db)

    # Crear un almacén de solo lectura (no crea ejecución nueva)
    almacen = AlmacenSupervisor(ruta_db)

    # Contar ejecuciones disponibles para informar al usuario
    ejecuciones = almacen.listar_ejecuciones()
    logger.info(
        "Ejecuciones encontradas en la base de datos: %d",
        len(ejecuciones),
    )

    # Crear un objeto simulado que el dashboard pueda consultar.
    # En modo consulta solo se usan los endpoints de ejecuciones
    # históricas, no el estado en directo.
    from types import SimpleNamespace
    agente_consulta = SimpleNamespace(
        salas_muc=[],
        informes_por_sala={},
        ocupantes_por_sala={},
        log_por_sala={},
        almacen=almacen,
    )

    # Arrancar servidor web independiente (sin SPADE)
    app = web.Application()
    registrar_rutas_supervisor(app)
    app["agente"] = agente_consulta
    app["modo"] = "consulta"

    runner = web.AppRunner(app)
    await runner.setup()
    sitio = web.TCPSite(runner, "0.0.0.0", puerto)
    await sitio.start()

    url_dashboard = f"http://localhost:{puerto}/supervisor"
    logger.info("Dashboard web disponible en %s", url_dashboard)
    logger.info(
        "Modo consulta: seleccionar una ejecución pasada en el "
        "desplegable del dashboard. Pulsa Ctrl+C para salir.",
    )

    # Abrir el dashboard automáticamente en el navegador
    webbrowser.open(url_dashboard)

    # Mantener en ejecución hasta señal de parada
    evento_parada = asyncio.Event()
    app["evento_parada"] = evento_parada

    bucle = asyncio.get_running_loop()
    _registrar_senales_parada(
        bucle, evento_parada, "Cerrando dashboard...",
    )

    await evento_parada.wait()

    almacen.cerrar()
    # Timeout para que no se bloquee si quedan conexiones SSE
    await runner.shutdown()
    await runner.cleanup()
    logger.info("Modo consulta finalizado.")


# ══════════════════════════════════════════════════════════════════
#  Modos laboratorio y torneo — supervisor completo con XMPP
# ══════════════════════════════════════════════════════════════════

async def ejecutar_modo_activo(
    modo: str,
    ruta_config: str,
    intervalo: int,
    ruta_db: str,
    puerto: int,
) -> None:
    """Crea las salas MUC, arranca el supervisor XMPP completo y
    monitoriza las partidas en tiempo real.

    Args:
        modo: ``"laboratorio"`` o ``"torneo"``.
        ruta_config: Ruta al fichero config.yaml.
        intervalo: Segundos entre cada consulta a la sala MUC.
        ruta_db: Ruta al fichero SQLite de persistencia.
        puerto: Puerto del dashboard web.
    """
    etiqueta_modo = modo.upper()
    ruta_salas = FICHERO_SALAS[modo]

    logger.info("Modo %s — fichero de salas: %s", etiqueta_modo, ruta_salas)

    # ── Cargar configuración ───────────────────────────────────
    logger.info("Cargando configuración desde: %s", ruta_config)
    config = cargar_configuracion(ruta_config)
    config_xmpp = config["xmpp"]

    # Ajustar nivel de logging según configuración del sistema
    config_sistema = config.get("sistema", {})
    nivel_log = config_sistema.get("nivel_log", "INFO")
    logging.getLogger().setLevel(getattr(logging, nivel_log, logging.INFO))

    # ── Crear salas MUC desde el fichero correspondiente ────────
    torneos = cargar_torneos(ruta_salas)
    if torneos:
        from main import crear_salas_torneos
        await crear_salas_torneos(torneos, config_xmpp)
    else:
        logger.warning(
            "No se encontraron salas en %s. El supervisor usará "
            "el descubrimiento automático.",
            ruta_salas,
        )

    # ── Extraer los nombres de las salas del fichero de torneos ──
    # Cada entrada del fichero tiene una clave "sala" con el nombre
    # de la sala MUC. Se pasan al agente para que se una directamente
    # a ellas, sin depender del descubrimiento automático XEP-0030
    # (que puede no encontrarlas si acaban de ser creadas).
    salas_del_modo = [t["sala"] for t in torneos if "sala" in t]

    if salas_del_modo:
        logger.info(
            "Salas del modo %s: %s",
            etiqueta_modo, ", ".join(salas_del_modo),
        )

    # ── Crear el agente con la factoría ────────────────────────
    logger.info("Creando Agente Supervisor...")
    agente = crear_agente(AgenteSupervisor, "supervisor", config_xmpp)

    # Inyectar los atributos que setup() espera encontrar.
    # Se usa descubrimiento "manual" con la lista explícita de salas
    # extraída del fichero del modo, para que el supervisor se una
    # exactamente a las salas correctas.
    agente.config_xmpp = config_xmpp
    agente.config_parametros = {
        "intervalo_consulta": intervalo,
        "ruta_db": ruta_db,
        "puerto_web": puerto,
        "descubrimiento_salas": "manual",
        "salas_muc": salas_del_modo,
    }
    agente.config_llm = None

    # ── Arrancar el agente con la factoría ─────────────────────
    await arrancar_agente(agente, config_xmpp)
    logger.info(
        "Supervisor arrancado en modo %s (JID: %s, intervalo: %d s)",
        etiqueta_modo, agente.jid, intervalo,
    )

    # ── Mantener en ejecución hasta señal de parada ────────────
    evento_parada = asyncio.Event()
    bucle = asyncio.get_running_loop()
    _registrar_senales_parada(
        bucle, evento_parada, "Deteniendo supervisor...",
    )

    # Exponer el evento de parada en la app web para que el
    # handler de finalización del torneo (P-09) pueda activarlo
    # desde el dashboard sin depender de señales del SO.
    if hasattr(agente, "web") and hasattr(agente.web, "app"):
        agente.web.app["evento_parada"] = evento_parada
        agente.web.app["modo"] = modo

    # Abrir el dashboard automáticamente en el navegador
    url_dashboard = f"http://localhost:{puerto}/supervisor"
    webbrowser.open(url_dashboard)

    logger.info("Supervisor en ejecución. Pulsa Ctrl+C para detener.")
    await evento_parada.wait()

    # ── Detener el agente de forma ordenada ────────────────────
    await agente.detener_persistencia()
    await agente.stop()
    logger.info("Supervisor detenido correctamente.")


# ══════════════════════════════════════════════════════════════════
#  Punto de entrada
# ══════════════════════════════════════════════════════════════════

def main() -> None:
    """Punto de entrada principal del lanzador del supervisor.

    Parsea argumentos, determina el modo y ejecuta la función
    correspondiente.
    """
    argumentos = parsear_argumentos()

    try:
        if argumentos.modo == "consulta":
            asyncio.run(
                ejecutar_modo_consulta(argumentos.db, argumentos.puerto),
            )
        else:
            asyncio.run(
                ejecutar_modo_activo(
                    argumentos.modo, argumentos.config,
                    argumentos.intervalo, argumentos.db,
                    argumentos.puerto,
                ),
            )
    except KeyboardInterrupt:
        logger.info("Ejecución interrumpida por el usuario.")


if __name__ == "__main__":
    main()
