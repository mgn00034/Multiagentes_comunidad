"""Módulo de carga de configuración del sistema Tic-Tac-Toe Multiagente.

Lee los ficheros config.yaml y agents.yaml, resuelve el perfil activo
y devuelve diccionarios con los parámetros listos para usar tanto por
el lanzador (main.py) como por los fixtures de tests (conftest.py).

Ejemplo de uso:
    from config.configuracion import cargar_configuracion, cargar_agentes

    config = cargar_configuracion()
    perfil_xmpp = config["xmpp"]
    perfil_llm = config["llm"]

    agentes = cargar_agentes()
    for agente in agentes:
        print(agente["nombre"], agente["clase"])
"""

import logging
from pathlib import Path
from typing import Any

import yaml

# ── Configuración del logger del módulo ────────────────────────
logger = logging.getLogger(__name__)

# ── Rutas por defecto de los ficheros de configuración ─────────
_DIRECTORIO_CONFIG = Path(__file__).parent
_RUTA_CONFIG = _DIRECTORIO_CONFIG / "config.yaml"
_RUTA_AGENTES = _DIRECTORIO_CONFIG / "agents.yaml"


def cargar_configuracion(ruta: str | Path = _RUTA_CONFIG) -> dict[str, Any]:
    """Carga la configuración general y resuelve los perfiles activos.

    Lee el fichero config.yaml, identifica el perfil activo de XMPP y
    el perfil activo de LLM, y devuelve un diccionario con las claves
    "xmpp", "llm" y "sistema" ya resueltas (es decir, con los datos
    del perfil seleccionado, no con todos los perfiles).

    Args:
        ruta: Ruta al fichero config.yaml. Por defecto usa el que
            está en el mismo directorio que este módulo.

    Returns:
        Diccionario con tres claves principales:
        - "xmpp": datos del perfil XMPP activo (host, puerto, dominio,
          servicio_muc, sala_tictactoe, password_defecto, etc.)
        - "llm": datos del perfil LLM activo (url_base, modelo,
          timeout_segundos, etc.) o None si no hay configuración LLM.
        - "sistema": parámetros generales (intervalos, timeouts, puertos, etc.)

    Raises:
        FileNotFoundError: Si el fichero config.yaml no existe.
        ValueError: Si el perfil activo referenciado no existe en los perfiles.
    """
    ruta = Path(ruta)
    resultado = {}

    try:
        contenido_yaml = ruta.read_text(encoding="utf-8")
        config_completa = yaml.safe_load(contenido_yaml)

        # ── Resolver perfil XMPP ───────────────────────────────
        seccion_xmpp = config_completa.get("xmpp", {})
        perfil_xmpp_activo = seccion_xmpp.get("perfil_activo", "local")
        perfiles_xmpp = seccion_xmpp.get("perfiles", {})

        if perfil_xmpp_activo not in perfiles_xmpp:
            raise ValueError(
                f"Perfil XMPP '{perfil_xmpp_activo}' no encontrado. "
                f"Perfiles disponibles: {list(perfiles_xmpp.keys())}"
            )

        datos_xmpp = perfiles_xmpp[perfil_xmpp_activo].copy()
        datos_xmpp["perfil"] = perfil_xmpp_activo
        # Construir la dirección completa de la sala MUC
        sala = datos_xmpp.get("sala_tictactoe", "tictactoe")
        servicio = datos_xmpp.get("servicio_muc", f"conference.{datos_xmpp['dominio']}")
        datos_xmpp["sala_muc_completa"] = f"{sala}@{servicio}"
        resultado["xmpp"] = datos_xmpp

        logger.info(
            "Perfil XMPP activo: '%s' → %s:%s",
            perfil_xmpp_activo,
            datos_xmpp["host"],
            datos_xmpp["puerto"],
        )

        # ── Resolver perfil LLM (opcional) ─────────────────────
        seccion_llm = config_completa.get("llm", {})
        if seccion_llm:
            perfil_llm_activo = seccion_llm.get("perfil_activo", "local")
            perfiles_llm = seccion_llm.get("perfiles", {})

            if perfil_llm_activo not in perfiles_llm:
                raise ValueError(
                    f"Perfil LLM '{perfil_llm_activo}' no encontrado. "
                    f"Perfiles disponibles: {list(perfiles_llm.keys())}"
                )

            datos_llm = perfiles_llm[perfil_llm_activo].copy()
            datos_llm["perfil"] = perfil_llm_activo
            resultado["llm"] = datos_llm

            logger.info(
                "Perfil LLM activo: '%s' → %s (modelo: %s)",
                perfil_llm_activo,
                datos_llm["url_base"],
                datos_llm["modelo"],
            )
        else:
            resultado["llm"] = None
            logger.info("Sin configuración LLM (estrategia nivel 4 no disponible)")

        # ── Parámetros generales del sistema ───────────────────
        resultado["sistema"] = config_completa.get("sistema", {})

    except FileNotFoundError:
        logger.error("Fichero de configuración no encontrado: %s", ruta)
        raise
    except yaml.YAMLError as error_yaml:
        logger.error("Error al parsear %s: %s", ruta, error_yaml)
        raise ValueError(f"Error de sintaxis YAML en {ruta}: {error_yaml}") from error_yaml

    return resultado


def cargar_agentes(
    ruta: str | Path = _RUTA_AGENTES,
    solo_activos: bool = True,
) -> list[dict[str, Any]]:
    """Carga la lista de agentes desde agents.yaml.

    Lee el fichero de definición de agentes y devuelve una lista de
    diccionarios, cada uno con los campos: nombre, clase, modulo,
    nivel, descripcion, parametros y activo.

    Args:
        ruta: Ruta al fichero agents.yaml. Por defecto usa el que
            está en el mismo directorio que este módulo.
        solo_activos: Si es True (por defecto), filtra y devuelve
            solo los agentes con activo=true. Si es False, devuelve
            todos los agentes definidos.

    Returns:
        Lista de diccionarios con la definición de cada agente.

    Raises:
        FileNotFoundError: Si el fichero agents.yaml no existe.
        ValueError: Si el fichero no contiene una lista válida.
    """
    ruta = Path(ruta)
    resultado = []

    try:
        contenido_yaml = ruta.read_text(encoding="utf-8")
        lista_agentes = yaml.safe_load(contenido_yaml)

        if not isinstance(lista_agentes, list):
            raise ValueError(
                f"El fichero {ruta} debe contener una lista YAML de agentes "
                f"(encontrado: {type(lista_agentes).__name__})"
            )

        for definicion in lista_agentes:
            # Asegurar que los campos opcionales tienen valores por defecto
            definicion.setdefault("parametros", {})
            definicion.setdefault("activo", True)
            definicion.setdefault("nivel", 1)

            if solo_activos and not definicion.get("activo", True):
                logger.debug("Agente '%s' desactivado, se omite", definicion["nombre"])
            else:
                resultado.append(definicion)

        logger.info(
            "Agentes cargados: %d activos de %d definidos",
            len(resultado),
            len(lista_agentes),
        )

    except FileNotFoundError:
        logger.error("Fichero de agentes no encontrado: %s", ruta)
        raise
    except yaml.YAMLError as error_yaml:
        logger.error("Error al parsear %s: %s", ruta, error_yaml)
        raise ValueError(f"Error de sintaxis YAML en {ruta}: {error_yaml}") from error_yaml

    return resultado


def cargar_torneos(ruta: str | Path = "config/torneos.yaml") -> list[dict[str, Any]]:
    """Carga la configuración de torneos desde torneos.yaml.

    Si el fichero no existe o está vacío, devuelve una lista vacía
    sin lanzar excepciones (los torneos son opcionales).

    Args:
        ruta: Ruta al fichero torneos.yaml.

    Returns:
        Lista de diccionarios con la definición de cada torneo
        (nombre, sala, descripcion, tableros, jugadores).
        Lista vacía si no hay torneos configurados.
    """
    ruta = Path(ruta)
    resultado = []

    if not ruta.exists():
        logger.debug("Fichero de torneos no encontrado: %s (opcional)", ruta)
        return resultado

    try:
        contenido_yaml = ruta.read_text(encoding="utf-8")
        datos = yaml.safe_load(contenido_yaml)

        if datos is None:
            return resultado

        # El fichero puede contener un dict con clave "torneos"
        # o directamente una lista
        lista_torneos = datos
        if isinstance(datos, dict):
            lista_torneos = datos.get("torneos", [])

        if not isinstance(lista_torneos, list):
            logger.warning(
                "El fichero %s no contiene una lista de torneos válida",
                ruta,
            )
            return resultado

        for torneo in lista_torneos:
            if torneo is None:
                continue
            torneo.setdefault("tableros", [])
            torneo.setdefault("jugadores", [])
            torneo.setdefault("descripcion", "")
            resultado.append(torneo)

        logger.info("Torneos cargados: %d desde %s", len(resultado), ruta)

    except yaml.YAMLError as error_yaml:
        logger.warning(
            "Error al parsear %s: %s. Se continúa sin torneos.",
            ruta, error_yaml,
        )

    return resultado


def construir_jid(nombre_agente: str, config_xmpp: dict[str, Any]) -> str:
    """Construye el JID completo de un agente a partir de su nombre y el perfil XMPP.

    El JID se forma como: nombre@dominio_del_perfil_activo.
    Por ejemplo, con perfil local: "tablero_mesa1@localhost".
    Con perfil servidor: "tablero_mesa1@sinbad2.ujaen.es".

    Args:
        nombre_agente: Nombre del agente (parte local del JID).
        config_xmpp: Diccionario con la configuración XMPP resuelta
            (resultado de cargar_configuracion()["xmpp"]).

    Returns:
        JID completo como cadena (ej: "tablero_mesa1@sinbad2.ujaen.es").
    """
    dominio = config_xmpp.get("dominio", "localhost")
    jid_completo = f"{nombre_agente}@{dominio}"
    return jid_completo
