"""
Almacén SQLite para persistir los datos del Agente Supervisor.

Gestiona una base de datos SQLite con tres tablas (ejecuciones,
informes y eventos) que permiten conservar los datos recopilados
por el supervisor entre distintas ejecuciones del sistema.

Cada vez que el supervisor arranca se crea un nuevo registro de
ejecución.  Al detenerse, se marca como finalizada.  Las ejecuciones
pasadas pueden consultarse desde el panel web.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)


# Tamaño de lote por defecto: número de escrituras acumuladas
# antes de ejecutar un COMMIT automático (M-08).
TAMANIO_LOTE = 20


class AlmacenSupervisor:
    """Capa de persistencia SQLite para el supervisor.

    Las escrituras (informes y eventos) se acumulan en un buffer
    interno y se consolidan con COMMIT cada ``tamanio_lote``
    operaciones (M-08). Esto reduce la carga de E/S sin
    sacrificar durabilidad: ``finalizar_ejecucion()`` y
    ``cerrar()`` fuerzan un flush antes de terminar.

    Atributos:
        ruta_db (str): Ruta al fichero de la base de datos.
        ejecucion_id (int | None): Identificador de la ejecución
            en curso.  ``None`` hasta que se llame a
            ``crear_ejecucion()``.
    """

    def __init__(
        self, ruta_db: str = "data/supervisor.db",
        tamanio_lote: int = TAMANIO_LOTE,
    ) -> None:
        """Abre (o crea) la base de datos e inicializa las tablas.

        Si los directorios intermedios no existen, se crean
        automáticamente.

        Args:
            ruta_db: Ruta al fichero SQLite.
            tamanio_lote: Número de escrituras acumuladas antes de
                ejecutar COMMIT automático (por defecto
                ``TAMANIO_LOTE``). Un valor de 1 desactiva el
                buffering (commit inmediato en cada escritura).
        """
        directorio = os.path.dirname(ruta_db)
        if directorio:
            os.makedirs(directorio, exist_ok=True)

        self._conexion = sqlite3.connect(
            ruta_db, check_same_thread=False,
        )
        self._conexion.row_factory = sqlite3.Row
        self.ruta_db = ruta_db
        self.ejecucion_id = None

        # ── Buffer de escrituras por lotes (M-08) ────────────
        self._tamanio_lote = tamanio_lote
        self._escrituras_pendientes = 0

        self._crear_tablas()

        logger.info("Almacén SQLite abierto: %s", ruta_db)

    # ── Inicialización del esquema ───────────────────────────────

    def _crear_tablas(self) -> None:
        """Crea las tablas e índices si no existen."""
        cursor = self._conexion.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS ejecuciones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                inicio      TEXT    NOT NULL,
                fin         TEXT,
                salas_json  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS informes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ejecucion_id    INTEGER NOT NULL,
                sala_id         TEXT    NOT NULL,
                remitente       TEXT    NOT NULL,
                cuerpo_json     TEXT    NOT NULL,
                ts              TEXT    NOT NULL,
                FOREIGN KEY (ejecucion_id) REFERENCES ejecuciones(id)
            );

            CREATE TABLE IF NOT EXISTS eventos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ejecucion_id    INTEGER NOT NULL,
                sala_id         TEXT    NOT NULL,
                tipo            TEXT    NOT NULL,
                de              TEXT    NOT NULL,
                detalle         TEXT    NOT NULL,
                ts              TEXT    NOT NULL,
                FOREIGN KEY (ejecucion_id) REFERENCES ejecuciones(id)
            );

            CREATE INDEX IF NOT EXISTS idx_informes_ejec
                ON informes(ejecucion_id);
            CREATE INDEX IF NOT EXISTS idx_eventos_ejec
                ON eventos(ejecucion_id);
        """)

        self._conexion.commit()

    # ── Gestión de ejecuciones ───────────────────────────────────

    def crear_ejecucion(self, salas: list[dict]) -> int:
        """Registra una nueva ejecución del supervisor.

        Args:
            salas: Lista de diccionarios con ``id`` y ``jid`` de
                cada sala monitorizada.

        Returns:
            Identificador de la ejecución creada.
        """
        ahora = datetime.now().isoformat()
        salas_json = json.dumps(salas, ensure_ascii=False)

        cursor = self._conexion.cursor()
        cursor.execute(
            "INSERT INTO ejecuciones (inicio, salas_json) VALUES (?, ?)",
            (ahora, salas_json),
        )
        self._conexion.commit()

        self.ejecucion_id = cursor.lastrowid

        logger.info(
            "Ejecución %d creada (%s, %d salas)",
            self.ejecucion_id, ahora, len(salas),
        )

        return self.ejecucion_id

    def finalizar_ejecucion(self) -> None:
        """Marca la ejecución actual como finalizada.

        Fuerza un flush del buffer antes de finalizar para
        garantizar que todas las escrituras pendientes se
        consolidan. Actualiza ``salas_json`` para incluir
        únicamente las salas que registraron actividad.
        """
        if self.ejecucion_id is None:
            return

        # Consolidar escrituras pendientes antes de finalizar
        self.flush_buffer()

        # Filtrar salas: solo las que tuvieron actividad
        salas_activas = self._obtener_salas_con_actividad()

        cursor = self._conexion.execute(
            "SELECT salas_json FROM ejecuciones WHERE id = ?",
            (self.ejecucion_id,),
        )
        fila = cursor.fetchone()

        salas_json = "[]"
        if fila is not None:
            salas_originales = json.loads(fila["salas_json"])
            salas_filtradas = [
                s for s in salas_originales
                if s["id"] in salas_activas
            ]
            salas_json = json.dumps(
                salas_filtradas, ensure_ascii=False,
            )

        ahora = datetime.now().isoformat()
        self._conexion.execute(
            "UPDATE ejecuciones SET fin = ?, salas_json = ? "
            "WHERE id = ?",
            (ahora, salas_json, self.ejecucion_id),
        )
        self._conexion.commit()

        logger.info(
            "Ejecución %d finalizada (%d sala(s) con actividad)",
            self.ejecucion_id, len(salas_activas),
        )

    def _obtener_salas_con_actividad(self) -> set[str]:
        """Devuelve los IDs de salas que tienen al menos un evento
        o un informe en la ejecución actual.

        Returns:
            Conjunto de identificadores de sala con actividad.
        """
        salas: set[str] = set()

        cursor = self._conexion.execute(
            "SELECT DISTINCT sala_id FROM eventos "
            "WHERE ejecucion_id = ?",
            (self.ejecucion_id,),
        )
        for fila in cursor.fetchall():
            salas.add(fila["sala_id"])

        cursor = self._conexion.execute(
            "SELECT DISTINCT sala_id FROM informes "
            "WHERE ejecucion_id = ?",
            (self.ejecucion_id,),
        )
        for fila in cursor.fetchall():
            salas.add(fila["sala_id"])

        return salas

    # ── Escritura de datos ───────────────────────────────────────

    def guardar_informe(
        self, sala_id: str, remitente: str, cuerpo: dict,
    ) -> None:
        """Persiste un informe de partida recibido.

        La escritura se acumula en el buffer interno y se
        consolida con COMMIT cuando se alcanza el tamaño de
        lote configurado.

        Args:
            sala_id: Identificador de la sala MUC.
            remitente: JID del tablero que envió el informe.
            cuerpo: Diccionario con el cuerpo del informe
                (campos de la ontología).
        """
        if self.ejecucion_id is None:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        cuerpo_json = json.dumps(cuerpo, ensure_ascii=False)

        self._conexion.execute(
            "INSERT INTO informes "
            "(ejecucion_id, sala_id, remitente, cuerpo_json, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.ejecucion_id, sala_id, remitente, cuerpo_json, ts),
        )
        self._registrar_escritura()

    def guardar_evento(
        self, sala_id: str, tipo: str, de: str, detalle: str,
        ts: str,
    ) -> None:
        """Persiste un evento del registro cronológico.

        La escritura se acumula en el buffer interno y se
        consolida con COMMIT cuando se alcanza el tamaño de
        lote configurado.

        Args:
            sala_id: Identificador de la sala MUC.
            tipo: Tipo del evento (presencia, informe, etc.).
            de: Identificador del agente origen.
            detalle: Descripción del evento.
            ts: Marca temporal formateada (HH:MM:SS).
        """
        if self.ejecucion_id is None:
            return

        self._conexion.execute(
            "INSERT INTO eventos "
            "(ejecucion_id, sala_id, tipo, de, detalle, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.ejecucion_id, sala_id, tipo, de, detalle, ts),
        )
        self._registrar_escritura()

    def _registrar_escritura(self) -> None:
        """Incrementa el contador de escrituras pendientes y
        ejecuta COMMIT si se alcanza el tamaño de lote."""
        self._escrituras_pendientes += 1
        if self._escrituras_pendientes >= self._tamanio_lote:
            self.flush_buffer()

    def flush_buffer(self) -> None:
        """Fuerza un COMMIT de todas las escrituras acumuladas.

        Se invoca automáticamente al alcanzar el tamaño de lote,
        y de forma explícita en ``finalizar_ejecucion()`` y
        ``cerrar()`` para garantizar que no se pierden datos.
        Es seguro llamar a este método tras ``cerrar()``.
        """
        if self._conexion is None:
            return
        if self._escrituras_pendientes > 0:
            self._conexion.commit()
            logger.debug(
                "Flush: %d escritura(s) consolidadas",
                self._escrituras_pendientes,
            )
            self._escrituras_pendientes = 0

    # ── Lectura de datos ─────────────────────────────────────────

    def listar_ejecuciones(self) -> list[dict]:
        """Devuelve todas las ejecuciones ordenadas por inicio
        descendente.

        Returns:
            Lista de diccionarios con ``id``, ``inicio``, ``fin``
            y ``num_salas``.
        """
        cursor = self._conexion.execute(
            "SELECT id, inicio, fin, salas_json "
            "FROM ejecuciones ORDER BY inicio DESC",
        )

        resultado = []
        for fila in cursor.fetchall():
            salas = json.loads(fila["salas_json"])
            resultado.append({
                "id": fila["id"],
                "inicio": fila["inicio"],
                "fin": fila["fin"],
                "num_salas": len(salas),
            })

        return resultado

    def obtener_salas_ejecucion(self, ejecucion_id: int) -> list[dict]:
        """Devuelve la configuración de salas de una ejecución.

        Args:
            ejecucion_id: Identificador de la ejecución.

        Returns:
            Lista de diccionarios con ``id`` y ``jid`` de cada sala,
            o lista vacía si la ejecución no existe.
        """
        cursor = self._conexion.execute(
            "SELECT salas_json FROM ejecuciones WHERE id = ?",
            (ejecucion_id,),
        )

        fila = cursor.fetchone()
        resultado = []
        if fila is not None:
            resultado = json.loads(fila["salas_json"])

        return resultado

    def obtener_informes_ejecucion(
        self, ejecucion_id: int,
    ) -> dict[str, dict[str, list[dict]]]:
        """Carga los informes de una ejecución, organizados por sala.

        El formato de retorno es idéntico al de
        ``agente.informes_por_sala``: un diccionario indexado
        primero por sala y luego por JID del tablero remitente,
        con una lista de informes por tablero (un tablero puede
        haber ejecutado varias partidas).

        Args:
            ejecucion_id: Identificador de la ejecución.

        Returns:
            Diccionario ``{sala_id: {remitente: [cuerpo, ...]}}``.
        """
        cursor = self._conexion.execute(
            "SELECT sala_id, remitente, cuerpo_json "
            "FROM informes WHERE ejecucion_id = ? "
            "ORDER BY id ASC",
            (ejecucion_id,),
        )

        resultado: dict[str, dict[str, list[dict]]] = {}
        for fila in cursor.fetchall():
            sala_id = fila["sala_id"]
            if sala_id not in resultado:
                resultado[sala_id] = {}
            remitente = fila["remitente"]
            if remitente not in resultado[sala_id]:
                resultado[sala_id][remitente] = []
            resultado[sala_id][remitente].append(
                json.loads(fila["cuerpo_json"]),
            )

        return resultado

    def obtener_eventos_ejecucion(
        self, ejecucion_id: int,
    ) -> dict[str, list[dict]]:
        """Carga los eventos de una ejecución, organizados por sala.

        El formato de retorno es idéntico al de
        ``agente.log_por_sala``: un diccionario indexado por sala
        cuyo valor es una lista de eventos en orden cronológico
        inverso (más reciente primero).

        Args:
            ejecucion_id: Identificador de la ejecución.

        Returns:
            Diccionario ``{sala_id: [evento, ...]}``.
        """
        cursor = self._conexion.execute(
            "SELECT sala_id, tipo, de, detalle, ts "
            "FROM eventos WHERE ejecucion_id = ? "
            "ORDER BY id DESC",
            (ejecucion_id,),
        )

        resultado: dict[str, list[dict]] = {}
        for fila in cursor.fetchall():
            sala_id = fila["sala_id"]
            if sala_id not in resultado:
                resultado[sala_id] = []
            resultado[sala_id].append({
                "ts": fila["ts"],
                "tipo": fila["tipo"],
                "de": fila["de"],
                "detalle": fila["detalle"],
            })

        return resultado

    # ── Cierre ───────────────────────────────────────────────────

    def cerrar(self) -> None:
        """Cierra la conexión a la base de datos.

        Fuerza un flush del buffer antes de cerrar para
        garantizar que no se pierden escrituras pendientes.
        Es seguro llamar a este método más de una vez.
        """
        if self._conexion is None:
            return
        self.flush_buffer()
        self._conexion.close()
        self._conexion = None
        logger.info("Almacén SQLite cerrado: %s", self.ruta_db)
