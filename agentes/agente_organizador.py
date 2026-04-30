"""
Agente Organizador de Torneos del sistema Tic-Tac-Toe Multiagente.

Crea las salas MUC necesarias para los torneos definidos en
``config/torneos.yaml`` y se mantiene conectado como ocupante de
cada una de ellas.  De esta forma garantiza que las salas existen
cuando los tableros y jugadores intentan unirse.

Este agente implementa la **opción C** de gestión de torneos.
Está desactivado por defecto (``activo: false`` en ``agents.yaml``).
Para utilizarlo, el alumno debe activarlo y asegurarse de que no
se usa simultáneamente la opción B (creación de salas desde
``main.py``).

Uso::

    # En agents.yaml, cambiar activo a true:
    - nombre: organizador
      activo: true

    # Ejecutar el sistema normalmente:
    python main.py

El organizador arranca como cualquier otro agente SPADE, lee la
configuración de torneos y se une a las salas.  El supervisor
descubre las salas automáticamente via XEP-0030.
"""

import logging
from typing import Any

import yaml
from spade.agent import Agent

logger = logging.getLogger(__name__)


class AgenteOrganizador(Agent):
    """Agente que crea y mantiene las salas MUC de los torneos.

    Atributos inyectados antes de ``setup()`` (por el lanzador):
        config_xmpp (dict): Configuración del perfil XMPP activo.
        config_parametros (dict): Parámetros específicos, que incluyen
            ``ruta_torneos`` con la ruta al fichero de torneos.
    """

    async def setup(self) -> None:
        """Lee los torneos y se une a cada sala para garantizar que
        existen en el servidor XMPP.

        El agente se mantiene como ocupante de las salas creadas
        durante toda su ejecución.  Esto tiene dos efectos:

        1. La sala se crea automáticamente en Prosody cuando el
           primer ocupante se une (comportamiento estándar de MUC).
        2. La sala permanece activa mientras el organizador esté
           conectado, evitando que Prosody la elimine por inactividad.
        """
        servicio_muc = self.config_xmpp.get(
            "servicio_muc", "conference.localhost",
        )
        ruta_torneos = self.config_parametros.get(
            "ruta_torneos", "config/torneos.yaml",
        )

        # ── Leer la configuración de torneos ─────────────────────
        torneos = self._cargar_torneos(ruta_torneos)

        # ── Crear las salas uniéndose a cada una ─────────────────
        self.salas_creadas: list[dict] = []

        for torneo in torneos:
            nombre_sala = torneo.get("sala", torneo.get("nombre", ""))
            if not nombre_sala:
                continue

            jid_sala = f"{nombre_sala}@{servicio_muc}"
            self.presence.subscribe(jid_sala)

            self.salas_creadas.append({
                "nombre": torneo.get("nombre", nombre_sala),
                "sala": nombre_sala,
                "jid": jid_sala,
                "descripcion": torneo.get("descripcion", ""),
                "tableros": torneo.get("tableros", []),
                "jugadores": torneo.get("jugadores", []),
            })

            logger.info(
                "Sala MUC '%s' creada para torneo '%s' "
                "(%d tableros, %d jugadores)",
                jid_sala,
                torneo.get("nombre", nombre_sala),
                len(torneo.get("tableros", [])),
                len(torneo.get("jugadores", [])),
            )

        if self.salas_creadas:
            logger.info(
                "AgenteOrganizador: %d sala(s) creada(s) — %s",
                len(self.salas_creadas),
                ", ".join(s["jid"] for s in self.salas_creadas),
            )
        else:
            logger.warning(
                "AgenteOrganizador: no se encontraron torneos en %s",
                ruta_torneos,
            )

    def _cargar_torneos(self, ruta: str) -> list[dict[str, Any]]:
        """Lee la configuración de torneos desde un fichero YAML.

        Args:
            ruta: Ruta al fichero torneos.yaml.

        Returns:
            Lista de diccionarios con la definición de cada torneo.
            Lista vacía si el fichero no existe o no es válido.
        """
        resultado = []

        try:
            with open(ruta, "r", encoding="utf-8") as fichero:
                datos = yaml.safe_load(fichero)
        except FileNotFoundError:
            logger.warning(
                "Fichero de torneos no encontrado: %s", ruta,
            )
            return resultado
        except yaml.YAMLError as error:
            logger.warning(
                "Error al parsear %s: %s", ruta, error,
            )
            return resultado

        if datos is None:
            return resultado

        # Acepta tanto un dict con clave "torneos" como una lista directa
        lista = datos
        if isinstance(datos, dict):
            lista = datos.get("torneos", [])

        if isinstance(lista, list):
            for torneo in lista:
                if torneo is not None:
                    resultado.append(torneo)

        return resultado
