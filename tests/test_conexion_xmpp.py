"""
Test de conexión XMPP para el sistema Tic-Tac-Toe Multiagente.

Comprueba que el servidor XMPP es alcanzable y que un agente SPADE
puede registrarse y conectarse correctamente, tanto en el perfil
local (localhost) como en el servidor de la asignatura (sinbad2.ujaen.es).

Uso:
    python -m tests.test_conexion_xmpp [local|servidor|ambos]

    - local    → prueba solo contra localhost:5222
    - servidor → prueba solo contra sinbad2.ujaen.es:8022
    - ambos    → prueba ambos perfiles (por defecto)

Autor: Profesor (material de apoyo)
"""
import asyncio
import logging
import socket
import sys
import uuid
from typing import Any

from spade.agent import Agent

from utils import cargar_configuracion, crear_agente, arrancar_agente

# ─── Configuración del registro de trazas ─────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Credenciales del agente de prueba ────────────────────────────────────────
# Se genera un nombre único con un sufijo aleatorio para evitar conflictos
# con usuarios ya registrados en el servidor XMPP con otra contraseña.
# SPADE ignora silenciosamente el error "conflict" (usuario ya existe)
# durante el auto-registro, y si la contraseña almacenada en el servidor
# no coincide, la autenticación posterior falla.
USUARIO_PRUEBA = f"prueba_conexion_{uuid.uuid4().hex[:8]}"


def verificar_puerto(servidor: str, puerto: int,
                     timeout: float = 5.0) -> bool:
    """Comprueba si un puerto TCP está abierto en el servidor indicado.

    Realiza una conexión TCP básica para determinar si el servicio
    XMPP está escuchando.  No envía datos, solo verifica alcanzabilidad.

    Args:
        servidor: Nombre de host o dirección IP del servidor.
        puerto: Puerto TCP a comprobar.
        timeout: Tiempo máximo de espera en segundos.

    Returns:
        True si el puerto está abierto y accesible, False en caso contrario.
    """
    accesible = False
    try:
        with socket.create_connection((servidor, puerto),
                                      timeout=timeout):
            accesible = True
    except (socket.timeout, ConnectionRefusedError, OSError) as error:
        logger.warning("  No se pudo conectar a %s:%d — %s",
                       servidor, puerto, error)
    return accesible


async def probar_conexion_spade(
    config_xmpp: dict[str, Any],
) -> bool:
    """Intenta registrar y conectar un agente SPADE al servidor XMPP.

    Crea un agente temporal mediante las funciones factoría de utils,
    lo arranca contra el servidor indicado, comprueba que está vivo
    y lo detiene limpiamente.

    Args:
        config_xmpp: Diccionario con la configuración del perfil XMPP
            activo.

    Returns:
        True si el agente logró conectarse correctamente, False si falló.
    """
    servidor = config_xmpp.get("host", "localhost")
    puerto = config_xmpp.get("puerto", 5222)
    logger.info("  Intentando conectar agente: %s@%s (puerto %d)",
                USUARIO_PRUEBA, config_xmpp.get("dominio", servidor),
                puerto)

    conexion_exitosa = False
    agente = crear_agente(Agent, USUARIO_PRUEBA, config_xmpp)

    try:
        await arrancar_agente(agente, config_xmpp)

        # Breve espera para que el agente complete el handshake XMPP
        await asyncio.sleep(2)

        if agente.is_alive():
            logger.info("  ¡Conexión exitosa! El agente %s está vivo.",
                        agente.jid)
            conexion_exitosa = True
        else:
            logger.error("  El agente %s no está vivo tras el arranque.",
                         agente.jid)

    except Exception as error:
        logger.error("  Error al conectar el agente %s: %s",
                     agente.jid, error)

    # Detener el agente de forma limpia, independientemente del resultado
    try:
        if agente.is_alive():
            await agente.stop()
            logger.info("  Agente %s detenido correctamente.", agente.jid)
    except Exception as error:
        logger.warning("  Error al detener el agente: %s", error)

    return conexion_exitosa


async def probar_perfil(nombre_perfil: str,
                        config_xmpp: dict[str, Any]) -> bool:
    """Ejecuta todas las pruebas de conexión para un perfil XMPP.

    Primero verifica que el puerto esté abierto (prueba de red básica)
    y, si lo está, intenta conectar un agente SPADE completo.

    Args:
        nombre_perfil: Identificador del perfil ("local" o "servidor").
        config_xmpp: Diccionario con la configuración del perfil XMPP.

    Returns:
        True si todas las pruebas del perfil fueron satisfactorias.
    """
    servidor = config_xmpp.get("host", "localhost")
    puerto = config_xmpp.get("puerto", 5222)

    logger.info("=" * 60)
    logger.info("Probando perfil: %s (%s:%d)", nombre_perfil, servidor,
                puerto)
    logger.info("=" * 60)

    # Paso 1: Verificar que el puerto TCP está abierto
    logger.info("[Paso 1] Verificando alcanzabilidad del puerto...")
    puerto_abierto = verificar_puerto(servidor, puerto)

    if not puerto_abierto:
        logger.error("  FALLO: El servidor %s:%d no es alcanzable.",
                     servidor, puerto)
        logger.error("  Posibles causas:")
        logger.error("    - El servidor XMPP no está arrancado")
        logger.error("    - El firewall bloquea el puerto %d", puerto)
        logger.error("    - El nombre de host '%s' no se resuelve",
                     servidor)
        resultado = False
    else:
        logger.info("  OK: Puerto %d abierto en %s", puerto, servidor)

        # Paso 2: Conectar un agente SPADE
        logger.info("[Paso 2] Conectando agente SPADE de prueba...")
        resultado = await probar_conexion_spade(config_xmpp)

        if resultado:
            logger.info("  RESULTADO: Perfil '%s' → CORRECTO",
                        nombre_perfil)
        else:
            logger.error("  RESULTADO: Perfil '%s' → FALLO",
                         nombre_perfil)

    return resultado


async def ejecutar_pruebas(perfiles_a_probar: list[str]) -> None:
    """Orquesta la ejecución de las pruebas para los perfiles indicados.

    Args:
        perfiles_a_probar: Lista con los nombres de los perfiles a
            verificar.
    """
    config = cargar_configuracion()
    config_xmpp_completa = config["xmpp"]

    # La configuración ya viene resuelta al perfil activo; para probar
    # un perfil concreto, recargamos manualmente los perfiles disponibles
    import yaml
    from pathlib import Path

    ruta_config = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(ruta_config, "r", encoding="utf-8") as fichero:
        config_completa = yaml.safe_load(fichero)
    perfiles_xmpp = config_completa.get("xmpp", {}).get("perfiles", {})

    resultados: dict[str, bool] = {}

    for nombre_perfil in perfiles_a_probar:
        if nombre_perfil not in perfiles_xmpp:
            logger.error("Perfil '%s' no encontrado en config.yaml.",
                         nombre_perfil)
            resultados[nombre_perfil] = False
            continue

        exito = await probar_perfil(nombre_perfil,
                                    perfiles_xmpp[nombre_perfil])
        resultados[nombre_perfil] = exito

    # ── Resumen final ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("RESUMEN DE PRUEBAS DE CONEXIÓN XMPP")
    logger.info("=" * 60)
    for perfil, exito in resultados.items():
        estado = "CORRECTO" if exito else "FALLO"
        logger.info("  %-12s → %s", perfil, estado)
    logger.info("=" * 60)

    # Indicar si hubo algún fallo mediante el código de salida
    algun_fallo = not all(resultados.values())
    if algun_fallo:
        logger.error("Alguna prueba de conexión ha fallado.")
        sys.exit(1)
    else:
        logger.info("Todas las pruebas de conexión superadas.")


def main() -> None:
    """Punto de entrada: parsea argumentos y lanza las pruebas."""
    # Determinar qué perfiles probar según el argumento recibido
    opcion = sys.argv[1] if len(sys.argv) > 1 else "ambos"
    opciones_validas = {
        "local": ["local"],
        "servidor": ["servidor"],
        "ambos": ["local", "servidor"],
    }

    perfiles = opciones_validas.get(opcion)
    if perfiles is None:
        logger.error("Opción no reconocida: '%s'", opcion)
        logger.error("Uso: python -m tests.test_conexion_xmpp "
                     "[local|servidor|ambos]")
        sys.exit(1)

    asyncio.run(ejecutar_pruebas(perfiles))


if __name__ == "__main__":
    main()