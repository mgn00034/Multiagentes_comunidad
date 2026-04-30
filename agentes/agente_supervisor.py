"""
Agente Supervisor del sistema Tic-Tac-Toe Multiagente.

Observa una o varias salas MUC para detectar tableros cuyas partidas
han finalizado y les solicita un informe de partida (``game-report``).
Los informes recibidos se almacenan internamente para consulta
posterior, organizados por sala.

La detección de tableros finalizados se realiza de forma reactiva
mediante el callback de presencia ``on_available`` de SPADE (modelo
push, coherente con XEP-0045): cuando la sala MUC notifica un cambio
de presencia con ``status="finished"``, el supervisor crea un
``SolicitarInformeBehaviour`` que gestiona el protocolo FIPA-Request
completo para ese tablero.

Además, expone un dashboard web accesible en el puerto configurado
(por defecto 10090) que permite visualizar en tiempo real los informes
recibidos, la presencia MUC, la clasificación y el log de eventos
de cada sala monitorizada.

Uso (a través de la factoría)::

    from utils import crear_agente, arrancar_agente
    from agentes.agente_supervisor import AgenteSupervisor

    agente = crear_agente(AgenteSupervisor, "supervisor", config_xmpp)
    await arrancar_agente(agente, config_xmpp)
"""

import logging
from datetime import datetime
from xml.etree.ElementTree import SubElement

from spade.agent import Agent
from spade.template import Template

from collections import deque

from behaviours.supervisor_behaviours import (
    LOG_ADVERTENCIA,
    LOG_ENTRADA,
    LOG_ERROR,
    LOG_PRESENCIA,
    LOG_SALIDA,
    LOG_SOLICITUD,
    MAX_FSM_CONCURRENTES,
    MAX_REINTENTOS,
    TIMEOUT_RESPUESTA,
    MonitorizarMUCBehaviour,
    SolicitarInformeFSM,
)
from ontologia.ontologia import (
    ONTOLOGIA, PREFIJO_THREAD_REPORT, crear_thread_unico,
)
from persistencia.almacen_supervisor import AlmacenSupervisor
from web.supervisor_handlers import (
    crear_middleware_auth,
    registrar_rutas_supervisor,
)

logger = logging.getLogger(__name__)


class AgenteSupervisor(Agent):
    """Agente que monitoriza partidas en múltiples salas MUC.

    Atributos inyectados antes de ``setup()`` (por el lanzador o la factoría):
        config_xmpp (dict): Configuración del perfil XMPP activo, que
            incluye ``servicio_muc`` y ``sala_tictactoe``.
        config_parametros (dict): Parámetros específicos del agente,
            como ``intervalo_consulta``, ``puerto_web``,
            ``descubrimiento_salas`` (``"auto"`` o ``"manual"``) y
            ``salas_muc`` (lista de salas para modo manual).
    """

    async def setup(self) -> None:
        """Inicializa el supervisor: estado interno, salas MUC, behaviours y web.

        Se une a cada sala MUC configurada con el apodo ``supervisor``,
        registra el callback de presencia para detección reactiva de
        tableros finalizados, el behaviour periódico para el dashboard
        y arranca el servidor web.
        """
        # ── Construir la lista de salas a monitorizar ────────────
        servicio_muc = self.config_xmpp.get(
            "servicio_muc", "conference.localhost",
        )
        modo_descubrimiento = self.config_parametros.get(
            "descubrimiento_salas", "auto",
        )
        salas_config = self.config_parametros.get("salas_muc", [])

        # Modo "auto" (por defecto): descubrir salas mediante
        # XEP-0030 (Service Discovery) contra el servicio MUC.
        # Modo "manual": usar la lista explícita de salas_muc.
        # Si salas_muc está vacía y el descubrimiento no encuentra
        # nada, se usa la sala por defecto del perfil XMPP.
        if modo_descubrimiento == "auto" and not salas_config:
            salas_config = await self._descubrir_salas_muc(servicio_muc)

        # Si no hay salas (ni manuales ni descubiertas), usar la
        # sala por defecto del perfil XMPP (retrocompatibilidad)
        if not salas_config:
            sala_defecto = self.config_xmpp.get(
                "sala_tictactoe", "tictactoe",
            )
            salas_config = [sala_defecto]
            logger.info(
                "Sin salas descubiertas ni configuradas; "
                "usando sala por defecto: %s",
                sala_defecto,
            )

        # Construir la lista de salas con su JID completo
        self.salas_muc: list[dict] = []
        for nombre_sala in salas_config:
            jid_sala = f"{nombre_sala}@{servicio_muc}"
            self.salas_muc.append({
                "id": nombre_sala,
                "jid": jid_sala,
            })

        # ── Estado interno organizado por sala ───────────────────
        # Informes indexados por sala y luego por JID del tablero.
        # Cada tablero puede acumular varios informes si ejecuta
        # múltiples partidas en la misma sala durante la ejecución.
        self.informes_por_sala: dict[str, dict[str, list[dict]]] = {
            s["id"]: {} for s in self.salas_muc
        }
        # Conjunto global de tableros ya consultados (JIDs únicos)
        self.tableros_consultados: set[str] = set()
        # Mapeo tablero JID → sala ID para saber a qué sala pertenece
        self.tablero_a_sala: dict[str, str] = {}

        # Ocupantes por sala para el dashboard (foto en tiempo real)
        self.ocupantes_por_sala: dict[str, list[dict]] = {
            s["id"]: [] for s in self.salas_muc
        }
        # Histórico de ocupantes: acumula JIDs y nicks de todos
        # los agentes que han estado en cada sala durante la
        # ejecución. No se eliminan al recibir 'unavailable'.
        # Se usa para la validación de jugadores observados (P-04)
        # en vez de la foto en tiempo real, evitando falsos
        # positivos cuando un jugador abandona la sala antes de
        # que se procese el informe.
        self.ocupantes_historicos_por_sala: dict[str, set[str]] = {
            s["id"]: set() for s in self.salas_muc
        }
        # Log cronológico por sala
        self.log_por_sala: dict[str, list[dict]] = {
            s["id"]: [] for s in self.salas_muc
        }

        # Threads de solicitudes cuyo informe ya se ha procesado.
        # Permite detectar informes duplicados por identidad de
        # solicitud (thread) en vez de por contenido (P-05).
        self.threads_procesados_por_sala: dict[str, set[str]] = {
            s["id"]: set() for s in self.salas_muc
        }

        # Solicitudes de informe en curso (jid_tablero → sala_id).
        # Se rellena al crear un SolicitarInformeFSM y se vacía
        # cuando el FSM alcanza un estado terminal. Al detener el
        # supervisor, las entradas restantes se registran como
        # informes no recibidos.
        self.informes_pendientes: dict[str, str] = {}

        # Cola de tableros pendientes de solicitar informe.
        # Cuando el número de FSMs activos alcanza el límite
        # (max_fsm_concurrentes), los nuevos tableros finalizados
        # se encolan aquí en vez de crear un FSM inmediatamente.
        # Se procesan conforme los FSMs activos terminan.
        self.tableros_en_cola: deque[tuple[str, str]] = deque()

        # ── Persistencia SQLite ───────────────────────────────────
        ruta_db = self.config_parametros.get(
            "ruta_db", "data/supervisor.db",
        )
        # Guardamos la ruta para que los handlers web puedan abrir
        # conexiones de lectura transitorias incluso después de que
        # detener_persistencia() haya cerrado el almacén principal.
        self.ruta_db = ruta_db
        self.almacen = AlmacenSupervisor(ruta_db)
        self.almacen.crear_ejecucion(self.salas_muc)

        # ── Keepalive XMPP ────────────────────────────────────────
        # slixmpp envía un espacio en blanco periódicamente para
        # mantener viva la conexión TCP. El intervalo por defecto
        # (300 s) es demasiado largo: los firewalls y NATs de la
        # red universitaria pueden cerrar conexiones inactivas
        # antes de que se envíe el keepalive, provocando la
        # expulsión silenciosa de las salas MUC. Un intervalo de
        # 60 s previene este problema sin generar tráfico excesivo.
        self.client.whitespace_keepalive_interval = 60

        # ── Registrar plugin MUC en el cliente XMPP ─────────────
        # Necesario para que slixmpp interprete correctamente el
        # elemento <x xmlns="...muc#user"> de las stanzas de presencia
        # (sin esto, el campo muc.item.jid no se parsea).
        self.client.register_plugin("xep_0045")

        # ── Unirse a cada sala MUC ──────────────────────────────
        # Se envía una stanza de presencia con namespace MUC a cada
        # sala. presence.subscribe() solo gestiona suscripciones
        # estándar XMPP, NO join de sala MUC (XEP-0045).
        self.muc_apodo = "supervisor"

        for sala in self.salas_muc:
            logger.info(
                "Supervisor uniéndose a la sala MUC: %s con apodo '%s'",
                sala["jid"], self.muc_apodo,
            )
            self._unirse_sala_muc(sala["jid"], self.muc_apodo)

        # ── Handler de presencia MUC (modelo push, paso 0) ───────
        # Captura las stanzas de presencia de las salas MUC para:
        # 1. Mantener actualizada la lista de ocupantes (dashboard)
        # 2. Detectar tableros con status="finished" (protocolo)
        self.client.add_event_handler(
            "presence", self._on_presencia_muc,
        )

        # ── Reconexión automática a salas MUC (M-11) ─────────
        # Cuando slixmpp restablece la sesión XMPP tras una
        # desconexión (reinicio del servidor, interrupción de
        # red), se vuelven a enviar los joins MUC para cada sala.
        # Se registra una advertencia para que quede constancia
        # en la pestaña de Incidencias.
        self.client.add_event_handler(
            "session_start", self._on_reconexion_sesion,
        )
        self.client.add_event_handler(
            "disconnected", self._on_desconexion,
        )
        self._reconexion_activa = False

        # ── Parámetros de temporización ──────────────────────────
        intervalo = self.config_parametros.get("intervalo_consulta", 10)
        self.timeout_respuesta = self.config_parametros.get(
            "timeout_respuesta", TIMEOUT_RESPUESTA,
        )
        self.max_reintentos = self.config_parametros.get(
            "max_reintentos", MAX_REINTENTOS,
        )
        self.max_fsm_concurrentes = self.config_parametros.get(
            "max_fsm_concurrentes", MAX_FSM_CONCURRENTES,
        )

        # Monitorización periódica: solo actualiza ocupantes del
        # dashboard, NO detecta tableros finalizados
        comportamiento_monitorizar = MonitorizarMUCBehaviour(
            period=intervalo,
        )
        self.add_behaviour(comportamiento_monitorizar)
        logger.info(
            "Behaviour MonitorizarMUC registrado (intervalo: %d s, "
            "salas: %d)",
            intervalo, len(self.salas_muc),
        )

        # ── Servidor web del dashboard ────────────────────────────
        puerto_web = self.config_parametros.get("puerto_web", 10090)

        # Autenticación HTTP Basic (M-10): si se configuran
        # usuario y contraseña, se añade un middleware que
        # exige credenciales en todas las rutas excepto estáticos.
        auth_usuario = self.config_parametros.get("auth_usuario", "")
        auth_contrasena = self.config_parametros.get(
            "auth_contrasena", "",
        )
        if auth_usuario and auth_contrasena:
            middleware = crear_middleware_auth(
                auth_usuario, auth_contrasena,
            )
            self.web.app.middlewares.append(middleware)
            logger.info(
                "Autenticación HTTP Basic activada "
                "(usuario: %s)", auth_usuario,
            )

        self.web.start(
            hostname="0.0.0.0",
            port=puerto_web,
        )
        registrar_rutas_supervisor(self.web.app)
        self.web.app["agente"] = self

        salas_str = ", ".join(s["jid"] for s in self.salas_muc)
        logger.info(
            "Dashboard web del supervisor disponible en "
            "http://localhost:%d/supervisor",
            puerto_web,
        )
        logger.info(
            "AgenteSupervisor configurado — %d sala(s): %s",
            len(self.salas_muc), salas_str,
        )

    # ── Reconexión automática a salas MUC (M-11) ────────────────

    def _on_desconexion(self, _evento) -> None:
        """Handler de desconexión XMPP.

        Se invoca cuando slixmpp pierde la conexión con el
        servidor. Marca la reconexión como activa para que
        ``_on_reconexion_sesion`` sepa que debe rejoin de las
        salas y registrar la advertencia.
        """
        self._reconexion_activa = True
        logger.warning(
            "Conexión XMPP perdida — se intentará "
            "reconexión automática a las salas MUC",
        )

    def _on_reconexion_sesion(self, _evento) -> None:
        """Handler de restablecimiento de sesión XMPP.

        Se invoca cuando slixmpp restablece la sesión tras una
        desconexión. Reenvía los joins MUC a todas las salas
        monitorizadas y registra una advertencia en el log de
        cada sala para que aparezca en la pestaña de Incidencias.
        """
        if not self._reconexion_activa:
            return

        self._reconexion_activa = False

        logger.info(
            "Sesión XMPP restablecida — reconectando a %d "
            "sala(s) MUC",
            len(self.salas_muc),
        )

        for sala in self.salas_muc:
            self._unirse_sala_muc(sala["jid"], self.muc_apodo)
            self.registrar_evento_log(
                LOG_ADVERTENCIA, "supervisor",
                "Reconexión automática a la sala tras "
                "pérdida de conexión XMPP — los ocupantes "
                "anteriores pueden no reflejarse hasta que "
                "vuelvan a enviar presencia",
                sala["id"],
            )
            logger.info(
                "Reconectado a sala MUC: %s", sala["jid"],
            )

    # ── Join MUC real mediante stanza de presencia ─────────────

    def _unirse_sala_muc(self, jid_sala: str, apodo: str) -> None:
        """Se une a una sala MUC enviando una stanza de presencia
        con el namespace ``http://jabber.org/protocol/muc``.

        A diferencia de ``presence.subscribe()``, este método realiza
        un join MUC real según XEP-0045: el servidor envía de vuelta
        las presencias de todos los ocupantes de la sala, lo que
        permite detectarlos en el handler ``_on_presencia_muc``.

        Args:
            jid_sala: JID completo de la sala (ej:
                ``tictactoe@conference.sinbad2.ujaen.es``).
            apodo: Nick con el que se une el supervisor.
        """
        stanza = self.client.make_presence(
            pto=f"{jid_sala}/{apodo}",
        )
        x_elem = SubElement(
            stanza.xml,
            "{http://jabber.org/protocol/muc}x",
        )
        # Solicitar 0 líneas de historial para evitar carga
        hist = SubElement(x_elem, "history")
        hist.set("maxchars", "0")
        stanza.send()

    # ── Handler de presencia MUC ─────────────────────────────────

    def _on_presencia_muc(self, presencia) -> None:
        """Handler que procesa TODAS las stanzas de presencia MUC.

        Se invoca cada vez que el cliente XMPP recibe una presencia.
        Filtra las que provienen de las salas MUC monitorizadas y
        realiza dos funciones:

        1. **Dashboard**: actualiza ``ocupantes_por_sala`` en tiempo
           real (añade, actualiza o elimina ocupantes).
        2. **Protocolo**: si un tablero cambia su status a
           ``"finished"``, crea un ``SolicitarInformeFSM`` para
           solicitar el informe de partida (paso 0).

        Args:
            presencia: Stanza de presencia recibida (slixmpp).
        """
        jid_from = presencia["from"]
        sala_jid_str = str(jid_from.bare)
        nick = str(jid_from.resource) if jid_from.resource else ""
        tipo = presencia["type"]

        # Solo procesar presencias de nuestras salas MUC
        sala_id = ""
        for sala in self.salas_muc:
            if sala["jid"] == sala_jid_str:
                sala_id = sala["id"]

        if not sala_id or not nick or nick == self.muc_apodo:
            return

        # ── Extraer información del ocupante ─────────────────
        show = str(presencia.get("show", ""))
        status = str(presencia.get("status", ""))
        jid_real = ""
        try:
            item_muc = presencia["muc"]["item"]
            if item_muc["jid"]:
                jid_real = str(item_muc["jid"])
        except Exception:
            pass

        jid_bare = jid_real.split("/")[0] if "/" in jid_real \
            else jid_real

        # Determinar rol y estado legible
        rol = "tablero" if nick.startswith("tablero_") else "jugador"
        estado = status if status else (show if show else "online")

        ocupantes = self.ocupantes_por_sala.get(sala_id, [])

        if tipo == "unavailable":
            # ── Ocupante abandona la sala ─────────────────────
            self.ocupantes_por_sala[sala_id] = [
                o for o in ocupantes if o["nick"] != nick
            ]
            self.registrar_evento_log(
                LOG_SALIDA, nick, "Ha abandonado la sala", sala_id,
            )

            # Si el tablero tenía un informe pendiente de
            # recibir, registrar un error en el log
            if nick.startswith("tablero_"):
                jid_tablero_muc = f"{sala_jid_str}/{nick}"
                jid_pendiente = ""
                if jid_tablero_muc in self.informes_pendientes:
                    jid_pendiente = jid_tablero_muc
                elif jid_bare \
                        and jid_bare in self.informes_pendientes:
                    jid_pendiente = jid_bare

                if jid_pendiente:
                    self.informes_pendientes.pop(
                        jid_pendiente, None,
                    )
                    self.registrar_evento_log(
                        LOG_ERROR, nick,
                        "Se desconectó con un informe "
                        "solicitado sin entregar",
                        sala_id,
                    )
                    logger.warning(
                        "Tablero %s abandonó sala %s con "
                        "informe pendiente",
                        nick, sala_id,
                    )
            return

        # ── Ocupante presente: añadir o actualizar ───────────
        encontrado = False
        estado_anterior = ""
        for occ in ocupantes:
            if occ["nick"] == nick:
                estado_anterior = occ["estado"]
                occ["estado"] = estado
                if jid_bare:
                    occ["jid"] = jid_bare
                encontrado = True

        if not encontrado:
            # Nuevo ocupante: registrar entrada en la sala
            ocupantes.append({
                "nick": nick,
                "jid": jid_bare,
                "rol": rol,
                "estado": estado,
            })
            self.ocupantes_por_sala[sala_id] = ocupantes

            # Registrar en el histórico (P-04): acumular JID y
            # nick para que la validación de jugadores observados
            # no genere falsos positivos si el jugador abandona
            # la sala antes de que se procese el informe.
            historico = self.ocupantes_historicos_por_sala.get(
                sala_id, set(),
            )
            if jid_bare:
                historico.add(jid_bare)
            historico.add(nick)
            self.ocupantes_historicos_por_sala[sala_id] = historico

            self.registrar_evento_log(
                LOG_ENTRADA, nick,
                f"Se ha unido a la sala ({rol})",
                sala_id,
            )
        elif estado_anterior and estado_anterior != estado \
                and nick.startswith("tablero_"):
            # Cambio de estado de un tablero: registrar transición
            self.registrar_evento_log(
                LOG_PRESENCIA, nick,
                f"Cambio de estado: {estado_anterior} → {estado}",
                sala_id,
            )

        # ── Mapeo tablero → sala ─────────────────────────────
        if nick.startswith("tablero_"):
            jid_completo = f"{sala_jid_str}/{nick}"
            self.tablero_a_sala[jid_completo] = sala_id
            if jid_bare:
                self.tablero_a_sala[jid_bare] = sala_id

        # ── Detección de tablero finalizado (paso 0) ─────────
        if not nick.startswith("tablero_") or status != "finished":
            return

        # Solo detectar si el estado CAMBIÓ a "finished" (S-01,
        # cambio 1). Ignorar redistribuciones de presencia donde
        # el tablero ya estaba en "finished" — estas son causadas
        # por eventos XMPP incidentales, no por una nueva partida.
        if estado_anterior == "finished":
            return

        jid_tablero = jid_bare if jid_bare \
            else f"{sala_jid_str}/{nick}"

        if jid_tablero in self.tableros_consultados:
            return

        self.tableros_consultados.add(jid_tablero)

        self.registrar_evento_log(
            LOG_PRESENCIA, nick, "Partida finalizada", sala_id,
        )

        # Comprobar si hay capacidad para crear un FSM nuevo
        # o si hay que encolar la solicitud para más adelante
        if len(self.informes_pendientes) \
                < self.max_fsm_concurrentes:
            self._crear_fsm_solicitud(jid_tablero, sala_id)
        else:
            self.tableros_en_cola.append(
                (jid_tablero, sala_id),
            )
            logger.info(
                "FSMs al límite (%d/%d): tablero %s encolado "
                "[sala: %s]",
                len(self.informes_pendientes),
                self.max_fsm_concurrentes,
                jid_tablero, sala_id,
            )

        # No desbloquear aqui: el discard se ejecuta en los
        # estados terminales del FSM, no en el handler de
        # presencia (S-01, cambio 2). Esto evita que una segunda
        # deteccion pase la guardia mientras el FSM esta activo.

    # ── Creación de FSM y gestión de la cola ─────────────────────────

    def _crear_fsm_solicitud(
        self, jid_tablero: str, sala_id: str,
    ) -> None:
        """Crea un SolicitarInformeFSM para un tablero finalizado.

        Registra el tablero en ``informes_pendientes`` y añade el
        behaviour al agente. Si ya existe un FSM activo para este
        tablero (defensa en profundidad S-01), ignora la solicitud.

        Args:
            jid_tablero: JID completo del tablero.
            sala_id: ID de la sala MUC.
        """
        # Guardia: evitar crear un FSM duplicado (S-01, cambio 2)
        if jid_tablero in self.informes_pendientes:
            logger.debug(
                "FSM ya activo para %s, ignorando duplicado",
                jid_tablero,
            )
            return

        self.informes_pendientes[jid_tablero] = sala_id

        nick = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]

        logger.info(
            "Creando SolicitarInformeFSM para %s [sala: %s] "
            "(activos: %d/%d, en cola: %d)",
            jid_tablero, sala_id,
            len(self.informes_pendientes),
            self.max_fsm_concurrentes,
            len(self.tableros_en_cola),
        )

        # Thread unico de la solicitud de informe. Se genera con la
        # utilidad comun de la ontologia para que todos los agentes del
        # sistema (jugador, tablero, supervisor) compartan el mismo
        # mecanismo de generacion y se evite cualquier colision.
        hilo = crear_thread_unico(jid_tablero, PREFIJO_THREAD_REPORT)

        fsm = SolicitarInformeFSM(
            jid_tablero=jid_tablero,
            sala_id=sala_id,
            hilo=hilo,
            timeout=self.timeout_respuesta,
            max_reintentos=self.max_reintentos,
        )

        plantilla = Template(thread=hilo)
        plantilla.set_metadata("ontology", ONTOLOGIA)

        self.add_behaviour(fsm, plantilla)

    def solicitar_siguiente_en_cola(self) -> None:
        """Procesa el siguiente tablero de la cola de espera.

        Se invoca desde los estados terminales del FSM cuando un
        ``informes_pendientes`` se libera. Si hay tableros
        encolados y hay capacidad, crea un nuevo FSM para el
        primero de la cola.
        """
        if not self.tableros_en_cola:
            return

        if len(self.informes_pendientes) \
                >= self.max_fsm_concurrentes:
            return

        jid_tablero, sala_id = self.tableros_en_cola.popleft()

        nick = jid_tablero.split("/")[-1] \
            if "/" in jid_tablero else jid_tablero.split("@")[0]

        logger.info(
            "Desencolando tablero %s [sala: %s] "
            "(restantes en cola: %d)",
            jid_tablero, sala_id,
            len(self.tableros_en_cola),
        )

        self.registrar_evento_log(
            LOG_SOLICITUD, nick,
            "Informe de partida solicitado (desde cola)",
            sala_id,
        )

        self._crear_fsm_solicitud(jid_tablero, sala_id)

    # ── Descubrimiento de salas MUC ────────────────────────────────

    async def _descubrir_salas_muc(self, servicio_muc: str) -> list[str]:
        """Descubre las salas disponibles en el servicio MUC mediante
        XEP-0030 (Service Discovery).

        Envía una consulta ``disco#items`` al servicio de conferencias
        (por ejemplo ``conference.sinbad2.ujaen.es``) y extrae los
        nombres de las salas que devuelve el servidor.

        Si el descubrimiento falla (servidor no disponible, servicio
        MUC sin soporte para disco, etc.), devuelve una lista vacía
        y registra un aviso en el log.

        Args:
            servicio_muc: JID del servicio de conferencias
                (ej: ``conference.sinbad2.ujaen.es``).

        Returns:
            Lista de nombres de salas descubiertas (parte local del
            JID, sin el dominio). Lista vacía si no se encuentra
            ninguna o si falla la consulta.
        """
        salas_descubiertas: list[str] = []

        try:
            self.client.register_plugin("xep_0030")

            resultado = await self.client.plugin["xep_0030"].get_items(
                jid=servicio_muc,
            )

            items = resultado["disco_items"]["items"]
            for item in items:
                jid_sala = str(item[0])
                # Extraer la parte local del JID (antes de @)
                nombre = jid_sala.split("@")[0] if "@" in jid_sala \
                    else jid_sala
                salas_descubiertas.append(nombre)

            logger.info(
                "Descubrimiento XEP-0030 en %s: %d sala(s) encontrada(s)%s",
                servicio_muc,
                len(salas_descubiertas),
                " — " + ", ".join(salas_descubiertas)
                if salas_descubiertas else "",
            )

        except Exception as error:
            logger.warning(
                "No se pudieron descubrir salas en %s: %s. "
                "Se usará la configuración por defecto.",
                servicio_muc, error,
            )

        return salas_descubiertas

    # ── Métodos auxiliares ────────────────────────────────────────

    def _identificar_sala(self, jid_str: str) -> str:
        """Determina a qué sala MUC pertenece un JID.

        Busca qué sala contiene el JID comprobando si el JID de la
        sala está incluido en el JID del contacto.

        Args:
            jid_str: JID completo del contacto.

        Returns:
            ID de la sala o cadena vacía si no pertenece a ninguna.
        """
        resultado = ""
        for sala in self.salas_muc:
            if sala["jid"] in jid_str:
                resultado = sala["id"]

        return resultado

    def obtener_sala_de_tablero(self, jid_tablero: str) -> str:
        """Busca a qué sala pertenece un tablero por su JID.

        Consulta el mapeo ``tablero_a_sala`` que se rellena durante
        la monitorización de presencia y el callback.

        Args:
            jid_tablero: JID del tablero (puede incluir recurso).

        Returns:
            ID de la sala a la que pertenece el tablero.
        """
        jid_base = jid_tablero.split("/")[0] if "/" in jid_tablero \
            else jid_tablero
        resultado = self.tablero_a_sala.get(
            jid_tablero,
            self.tablero_a_sala.get(jid_base, ""),
        )

        # Fallback: primera sala configurada
        if not resultado and self.salas_muc:
            resultado = self.salas_muc[0]["id"]

        return resultado

    def registrar_evento_log(
        self, tipo: str, de: str, detalle: str, sala_id: str = "",
    ) -> None:
        """Añade un evento al log cronológico de una sala.

        Args:
            tipo: Tipo del evento (presencia, informe, abortada,
                salida, timeout).
            de: Identificador del agente que origina el evento.
            detalle: Descripción legible del evento.
            sala_id: ID de la sala a la que pertenece el evento.
        """
        sala_destino = sala_id
        if not sala_destino and self.salas_muc:
            sala_destino = self.salas_muc[0]["id"]

        evento = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "tipo": tipo,
            "de": de,
            "detalle": detalle,
        }

        if sala_destino not in self.log_por_sala:
            self.log_por_sala[sala_destino] = []

        self.log_por_sala[sala_destino].insert(0, evento)

        # Persistir en SQLite
        if hasattr(self, "almacen") and self.almacen is not None:
            self.almacen.guardar_evento(
                sala_destino, tipo, de, detalle, evento["ts"],
            )

        # Notificar a los suscriptores SSE
        try:
            from web.supervisor_handlers import notificar_sse
            notificar_sse("state", {
                "sala_id": sala_destino,
                "evento": evento,
            })
        except ImportError:
            pass

        logger.debug(
            "Evento de log [%s/%s] %s — %s",
            sala_destino, tipo, de, detalle,
        )

    async def detener_persistencia(self) -> None:
        """Finaliza la ejecución actual y cierra el almacén SQLite.

        Debe invocarse antes de detener el agente para que la
        ejecución quede correctamente marcada como finalizada.

        Si quedan solicitudes de informe en curso (FSMs que aún
        no han recibido respuesta), se registra un evento
        ``pendiente`` en el log de cada sala afectada para dejar
        constancia de los informes no recibidos.
        """
        # Registrar informes que se solicitaron pero no se
        # recibieron antes de la detención del supervisor
        if hasattr(self, "informes_pendientes"):
            for jid_tablero, sala_id \
                    in self.informes_pendientes.items():
                nick_tablero = jid_tablero.split("/")[-1] \
                    if "/" in jid_tablero \
                    else jid_tablero.split("@")[0]
                self.registrar_evento_log(
                    LOG_ADVERTENCIA, nick_tablero,
                    "Informe solicitado sin recibir al "
                    "finalizar el supervisor",
                    sala_id,
                )
                logger.warning(
                    "Informe pendiente de %s [sala: %s] no "
                    "recibido al detener el supervisor",
                    jid_tablero, sala_id,
                )
            self.informes_pendientes.clear()

        # Registrar tableros que estaban en cola (detectados
        # como finalizados pero cuyo informe nunca se solicitó
        # porque se alcanzó el límite de FSMs concurrentes)
        if hasattr(self, "tableros_en_cola"):
            for jid_tablero, sala_id in self.tableros_en_cola:
                nick_tablero = jid_tablero.split("/")[-1] \
                    if "/" in jid_tablero \
                    else jid_tablero.split("@")[0]
                self.registrar_evento_log(
                    LOG_ADVERTENCIA, nick_tablero,
                    "Informe no solicitado al finalizar el "
                    "supervisor (estaba en cola de espera)",
                    sala_id,
                )
                logger.warning(
                    "Tablero encolado %s [sala: %s] no "
                    "solicitado al detener el supervisor",
                    jid_tablero, sala_id,
                )
            self.tableros_en_cola.clear()

        if hasattr(self, "almacen") and self.almacen is not None:
            self.almacen.finalizar_ejecucion()
            self.almacen.cerrar()
            self.almacen = None
            logger.info("Persistencia detenida correctamente")
