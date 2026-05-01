"""Módulo de carga de configuración del sistema Tic-Tac-Toe Multiagente.

Lee los ficheros config.yaml y agents.yaml, resuelve el perfil activo
y devuelve diccionarios con los parámetros listos para usar tanto por
el lanzador (main.py) como por los fixtures de tests (conftest.py).

Para el perfil LLM activo se preparan automáticamente las variables
de entorno que LiteLLM/ADK necesitan según el ``proveedor`` declarado
en ``config.yaml``:

* ``ollama``: se fija ``OLLAMA_API_BASE`` con la ``url_base`` del
  perfil para que LiteLLM enrute las peticiones al servidor Ollama
  correcto.
* ``gemini``: se comprueba que la variable indicada en
  ``api_key_env`` (por defecto ``GOOGLE_API_KEY``) está definida en
  el entorno; si no, se lanza un error didáctico que indica cómo
  obtener la clave gratuita.

Ejemplo de uso:
    from config.configuracion import cargar_configuracion, cargar_agentes

    config = cargar_configuracion()
    perfil_xmpp = config["xmpp"]
    perfil_llm = config["llm"]

    plantillas = cargar_plantillas()
    agentes = generar_agentes(config, plantillas)
    for agente in agentes:
        print(agente["nombre"], agente["clase"])
"""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

# ── Configuración del logger del módulo ────────────────────────
logger = logging.getLogger(__name__)

# ── Rutas por defecto de los ficheros de configuración ─────────
_DIRECTORIO_CONFIG = Path(__file__).parent
_RUTA_CONFIG = _DIRECTORIO_CONFIG / "config.yaml"
_RUTA_AGENTES = _DIRECTORIO_CONFIG / "agents.yaml"


def _preparar_entorno_llm(datos_llm: dict[str, Any]) -> None:
    """Fija las variables de entorno que LiteLLM/ADK necesitan según
    el proveedor del perfil LLM activo.

    * ``ollama``  → exporta ``OLLAMA_API_BASE`` con la ``url_base``
      del perfil (sin sobrescribir un valor previo del entorno).
    * ``gemini``  → comprueba que la variable indicada en
      ``api_key_env`` (por defecto ``GOOGLE_API_KEY``) está definida.
      Si no lo está, lanza ``RuntimeError`` con un mensaje didáctico
      que indica dónde obtener la clave gratuita.

    Si el perfil no declara ``proveedor`` se asume ``ollama`` por
    compatibilidad con configuraciones anteriores.

    Args:
        datos_llm: Diccionario con los datos del perfil LLM activo.

    Raises:
        RuntimeError: Si el perfil ``gemini`` está activo pero la
            variable de entorno con la API key no está definida.
    """
    proveedor = datos_llm.get("proveedor", "ollama")

    if proveedor == "ollama":
        url_base = datos_llm.get("url_base")
        if url_base:
            os.environ.setdefault("OLLAMA_API_BASE", url_base)
    elif proveedor == "gemini":
        nombre_var = datos_llm.get("api_key_env", "GOOGLE_API_KEY")
        if not os.environ.get(nombre_var):
            raise RuntimeError(
                f"El perfil LLM 'gemini' requiere la variable de "
                f"entorno '{nombre_var}' con una API key de Google "
                f"AI Studio.\n"
                f"  Obtén una clave gratuita en "
                f"https://aistudio.google.com/apikey\n"
                f"  Y expórtala antes de ejecutar:\n"
                f'      export {nombre_var}="tu-api-key"'
            )


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

            # Preparar variables de entorno según el proveedor activo
            # para que LiteLLM/ADK conecten con el backend correcto.
            _preparar_entorno_llm(datos_llm)

            proveedor = datos_llm.get("proveedor", "ollama")
            destino = datos_llm.get("url_base") or f"<{proveedor} cloud>"
            logger.info(
                "Perfil LLM activo: '%s' (%s) → %s (modelo: %s)",
                perfil_llm_activo,
                proveedor,
                destino,
                datos_llm["modelo"],
            )
        else:
            resultado["llm"] = None
            logger.info("Sin configuración LLM (estrategia nivel 4 no disponible)")

        # ── Parámetros generales del sistema ───────────────────
        resultado["sistema"] = config_completa.get("sistema", {})

        # ── Parámetros del bloque "verificacion" (opcional) ────
        resultado["verificacion"] = config_completa.get("verificacion", {})

        # ── Datos del alumno y modalidad de ejecución ──────────
        # Se propagan tal cual para que generar_agentes() los
        # consulte sin tener que volver a leer el YAML.
        resultado["alumno"] = config_completa.get("alumno", {})

    except FileNotFoundError:
        logger.error("Fichero de configuración no encontrado: %s", ruta)
        raise
    except yaml.YAMLError as error_yaml:
        logger.error("Error al parsear %s: %s", ruta, error_yaml)
        raise ValueError(f"Error de sintaxis YAML en {ruta}: {error_yaml}") from error_yaml

    return resultado


def cargar_plantillas(
    ruta: str | Path = _RUTA_AGENTES,
) -> dict[str, Any]:
    """Carga el fichero de plantillas de agentes (agents.yaml).

    El fichero ya no contiene una lista de agentes concretos, sino
    plantillas (``plantilla_tablero`` y ``plantilla_jugador``) y la
    cantidad de cada uno por modalidad (``modalidades.laboratorio``,
    ``modalidades.torneo``).  Los agentes concretos se generan en
    tiempo de ejecución mediante :func:`generar_agentes`.

    Args:
        ruta: Ruta al fichero agents.yaml.

    Returns:
        Diccionario con las claves ``modalidades``,
        ``plantilla_tablero`` y ``plantilla_jugador``.

    Raises:
        FileNotFoundError: Si el fichero agents.yaml no existe.
        ValueError: Si el fichero no contiene un diccionario válido
            o le faltan claves obligatorias.
    """
    ruta = Path(ruta)
    plantillas = {}

    try:
        contenido_yaml = ruta.read_text(encoding="utf-8")
        datos = yaml.safe_load(contenido_yaml)

        if not isinstance(datos, dict):
            raise ValueError(
                f"El fichero {ruta} debe contener un diccionario YAML "
                f"con plantillas (encontrado: {type(datos).__name__})"
            )

        claves_obligatorias = (
            "modalidades", "plantilla_tablero", "plantilla_jugador",
        )
        for clave in claves_obligatorias:
            if clave not in datos:
                raise ValueError(
                    f"El fichero {ruta} debe contener la clave '{clave}'"
                )

        plantillas = datos
        logger.info("Plantillas de agentes cargadas desde: %s", ruta)

    except FileNotFoundError:
        logger.error("Fichero de plantillas no encontrado: %s", ruta)
        raise
    except yaml.YAMLError as error_yaml:
        logger.error("Error al parsear %s: %s", ruta, error_yaml)
        raise ValueError(
            f"Error de sintaxis YAML en {ruta}: {error_yaml}"
        ) from error_yaml

    return plantillas


def generar_agentes(
    config: dict[str, Any],
    plantillas: dict[str, Any],
) -> list[dict[str, Any]]:
    """Genera la lista de agentes concretos a partir de las plantillas.

    Construye los agentes propios del alumno (tableros y jugadores)
    según la modalidad activa.  El nombre de cada agente se forma
    como ``tablero_<usuario>_NN`` o ``jugador_<usuario>_NN``, con
    NN = ``01``, ``02``, …  El puerto web de cada tablero se
    asigna automáticamente como ``puerto_web_base + índice`` (con
    índice 0, 1, 2, …) para evitar colisiones.

    El nivel de estrategia se toma de ``config["alumno"]
    ["nivel_estrategia"]`` y se aplica a todos los jugadores
    generados.

    Args:
        config: Configuración resuelta (resultado de
            :func:`cargar_configuracion`).  Debe contener una sección
            ``alumno`` con ``usuario_uja``, ``modalidad`` y
            ``nivel_estrategia``.
        plantillas: Plantillas cargadas con :func:`cargar_plantillas`.

    Returns:
        Lista de definiciones de agentes con la misma estructura que
        la antigua salida de ``cargar_agentes``: cada elemento es un
        diccionario con ``nombre``, ``clase``, ``modulo``, ``nivel``,
        ``descripcion``, ``parametros`` y ``activo``.

    Raises:
        ValueError: Si la modalidad indicada en ``config`` no existe
            en las plantillas, o si falta algún dato del alumno.
    """
    seccion_alumno = config.get("alumno", {})
    usuario = seccion_alumno.get("usuario_uja", "").strip()
    modalidad = seccion_alumno.get("modalidad", "").strip()

    # Lista de niveles a probar.  Compatibilidad: si alguien aún tiene
    # el campo antiguo "nivel_estrategia" (escalar) se acepta también.
    niveles_estrategia = seccion_alumno.get("niveles_estrategia")
    if niveles_estrategia is None:
        nivel_legacy = seccion_alumno.get("nivel_estrategia")
        niveles_estrategia = [nivel_legacy] if nivel_legacy is not None else []

    if not usuario:
        raise ValueError(
            "Falta 'alumno.usuario_uja' en config.yaml. "
            "Indica tu usuario UJA para generar los agentes."
        )

    if not niveles_estrategia:
        raise ValueError(
            "Falta 'alumno.niveles_estrategia' en config.yaml "
            "(lista de niveles de estrategia a probar)."
        )

    modalidades = plantillas.get("modalidades", {})
    if modalidad not in modalidades:
        raise ValueError(
            f"Modalidad '{modalidad}' no definida en agents.yaml. "
            f"Modalidades disponibles: {list(modalidades.keys())}"
        )

    cantidades = modalidades[modalidad]
    num_tableros = int(cantidades.get("num_tableros", 0))
    num_jugadores = int(cantidades.get("num_jugadores", 0))

    plantilla_tablero = plantillas["plantilla_tablero"]
    plantilla_jugador = plantillas["plantilla_jugador"]

    # Puerto web base para los tableros (para asignación automática)
    parametros_tablero_base = plantilla_tablero.get("parametros", {})
    puerto_web_base = int(parametros_tablero_base.get("puerto_web_base", 10080))

    agentes: list[dict[str, Any]] = []

    # ── Generar agentes tablero ────────────────────────────────
    for indice in range(num_tableros):
        sufijo = f"{indice + 1:02d}"
        nombre_tablero = f"tablero_{usuario}_{sufijo}"
        parametros = {
            "id_tablero": f"mesa{sufijo}",
            "puerto_web": puerto_web_base + indice,
        }
        agentes.append({
            "nombre": nombre_tablero,
            "clase": plantilla_tablero["clase"],
            "modulo": plantilla_tablero["modulo"],
            "nivel": plantilla_tablero.get("nivel", 1),
            "descripcion": plantilla_tablero.get("descripcion", ""),
            "parametros": parametros,
            "activo": True,
        })

    # ── Reparto uniforme de jugadores entre niveles de estrategia ──
    # En LABORATORIO se distribuye num_jugadores entre todos los
    # niveles indicados (4-4-4 con 12 jugadores y 3 niveles).  Si la
    # división no es exacta, los primeros niveles reciben uno más.
    # En TORNEO solo hay un jugador y se usa el primer nivel.
    niveles_normalizados = [int(n) for n in niveles_estrategia]
    if modalidad == "torneo":
        plan_distribucion = [(niveles_normalizados[0], num_jugadores)]
    else:
        plan_distribucion = _repartir_uniformemente(
            num_jugadores, niveles_normalizados,
        )

    parametros_jugador_base = plantilla_jugador.get("parametros", {})
    max_partidas = int(parametros_jugador_base.get("max_partidas", 3))

    for nivel, cantidad in plan_distribucion:
        for indice_local in range(cantidad):
            sufijo = f"{indice_local + 1:02d}"
            # Sufijo 'n<nivel>' embebido en el nombre para que el
            # nivel sea visible a simple vista en logs y JIDs.
            nombre_jugador = f"jugador_{usuario}_n{nivel}_{sufijo}"
            parametros = {
                "nivel_estrategia": nivel,
                "max_partidas": max_partidas,
            }
            agentes.append({
                "nombre": nombre_jugador,
                "clase": plantilla_jugador["clase"],
                "modulo": plantilla_jugador["modulo"],
                "nivel": plantilla_jugador.get("nivel", 1),
                "descripcion": plantilla_jugador.get("descripcion", ""),
                "parametros": parametros,
                "activo": True,
            })

    logger.info(
        "Generados %d agentes para modalidad '%s' (usuario '%s'): "
        "%d tableros + %d jugadores (niveles %s)",
        len(agentes), modalidad, usuario, num_tableros, num_jugadores,
        niveles_normalizados,
    )

    return agentes


def _repartir_uniformemente(
    total: int,
    niveles: list[int],
) -> list[tuple[int, int]]:
    """Reparte ``total`` jugadores uniformemente entre los niveles dados.

    Si la división no es exacta, los primeros niveles de la lista
    reciben un jugador extra hasta agotar el resto.

    Args:
        total: Número total de jugadores a repartir.
        niveles: Lista de niveles de estrategia entre los que repartir.

    Returns:
        Lista de tuplas ``(nivel, cantidad)`` que indica cuántos
        jugadores se generan para cada nivel.  Mantiene el orden de
        ``niveles`` para que el resultado sea reproducible.
    """
    distribucion: list[tuple[int, int]] = []

    if not niveles or total <= 0:
        return distribucion

    base = total // len(niveles)
    resto = total % len(niveles)

    for posicion, nivel in enumerate(niveles):
        cantidad = base + (1 if posicion < resto else 0)
        if cantidad > 0:
            distribucion.append((nivel, cantidad))

    return distribucion


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
