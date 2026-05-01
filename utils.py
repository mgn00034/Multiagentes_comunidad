"""
Módulo de utilidades y funciones factoría para agentes SPADE.

Centraliza la creación y el arranque de agentes SPADE encapsulando
la separación de parámetros que impone SPADE 4.x: el constructor del
agente acepta ``port`` y ``verify_security``, mientras que el método
``start()`` acepta ``auto_register``.  Las funciones factoría de este
módulo evitan que el alumno tenga que recordar estos detalles.

Las funciones de carga de configuración (``cargar_configuracion``,
``cargar_agentes``, ``construir_jid``) residen en ``config/configuracion.py``
y se re-exportan aquí por conveniencia, de forma que el alumno pueda
importar todo desde un único punto::

    from utils import cargar_configuracion, crear_agente, arrancar_agente

Autor: Profesor (material de apoyo)
"""
import logging
from typing import Any
from spade.agent import Agent
from spade.message import Message

# Re-exportar las funciones de configuración para acceso centralizado
from config.configuracion import (   # noqa: F401
    cargar_configuracion,
    cargar_plantillas,
    generar_agentes,
    cargar_torneos,
    construir_jid,
)

logger = logging.getLogger(__name__)


# ─── Funciones factoría para agentes SPADE ───────────────────────────────────

def crear_agente(
    clase_agente: type[Agent],
    nombre: str,
    config_xmpp: dict[str, Any],
    contrasena: str | None = None,
) -> Agent:
    """Crea una instancia de agente SPADE con los parámetros de conexión.

    Construye el JID y pasa al constructor únicamente los parámetros que
    este acepta (``port`` y ``verify_security``).  El parámetro
    ``auto_register`` se gestiona aparte en ``arrancar_agente()``, ya que
    pertenece a ``start()``.

    Args:
        clase_agente: Clase (o subclase) de ``spade.agent.Agent`` a
            instanciar (por ejemplo, ``AgenteTablero``).
        nombre: Nombre del agente (parte local del JID, sin dominio).
        config_xmpp: Diccionario con la configuración del perfil XMPP
            activo (resultado de ``cargar_configuracion()["xmpp"]``).
        contrasena: Contraseña del agente en el servidor XMPP.  Si no
            se proporciona, se usa ``password_defecto`` del perfil.

    Returns:
        Instancia del agente, lista para ser arrancada con
        ``arrancar_agente()``.
    """
    jid = construir_jid(nombre, config_xmpp)
    password = contrasena or config_xmpp.get("password_defecto", "secret")

    resultado = clase_agente(
        jid,
        password,
        port=config_xmpp.get("puerto", 5222),
        verify_security=config_xmpp.get("verify_security", False),
    )
    return resultado


async def arrancar_agente(
    agente: Agent,
    config_xmpp: dict[str, Any],
) -> None:
    """Arranca un agente SPADE pasando ``auto_register`` a ``start()``.

    En SPADE 4.x, ``auto_register`` es parámetro de ``start()``, no del
    constructor.  Esta función encapsula esa particularidad.

    Args:
        agente: Instancia del agente ya creada con ``crear_agente()``.
        config_xmpp: Diccionario con la configuración del perfil XMPP
            activo.
    """
    auto_registro = config_xmpp.get("auto_register", True)
    await agente.start(auto_register=auto_registro)

def log_mensaje_no_entendido(origen: str, estado: str, msg: Message, motivo: str) -> None:
    """
    Imprime un log en color azul cuando un agente recibe un mensaje que no entiende.

    Args:
        origen: Identificador de quien imprime el log (ej: 'TABLERO mesa1').
        estado: Estado o fase actual del agente que recibe el mensaje.
        msg: El objeto Message de SPADE recibido.
        motivo: Explicación breve del fallo (ej: 'JSON inválido').
    """
    logger.warning(
        f"\033[94m🔵 [{origen} | Estado: {estado}] Mensaje recibido no entendido ({motivo}):\n"
        f"   - Desde: {msg.sender}\n"
        f"   - Performativa: {msg.metadata.get('performative', 'N/A')}\n"
        f"   - Cuerpo: {msg.body}\n"
        f"   - Mensaje completo: {msg}\033[0m"
    )