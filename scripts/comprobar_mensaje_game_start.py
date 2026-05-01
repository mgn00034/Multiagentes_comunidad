"""
Script de comprobación del mensaje INFORM game-start.

Reconstruye el mensaje exacto que el tablero enviaría a cada
jugador al cerrar la fase de inscripción y abrir la partida.
Muestra su estructura completa: metadata, thread, body y la
plantilla (Template) que el jugador usaría para registrar su
behaviour de partida antes de recibir el primer CFP turn.

Uso::

    python -m scripts.comprobar_mensaje_game_start
"""

import json

from spade.message import Message
from spade.template import Template

from ontologia import (
    ONTOLOGIA,
    PREFIJO_THREAD_GAME,
    crear_cuerpo_game_start,
    crear_thread_unico,
)

# Parametros de ejemplo ----------------------------------------------
JID_TABLERO = "tablero_01@localhost"
JID_JUGADOR_X = "jugador_x@localhost"
JID_JUGADOR_O = "jugador_o@localhost"

SEPARADOR = "=" * 64


def construir_game_start(
    jid_destino: str, jid_oponente: str, thread_partida: str,
) -> Message:
    """Construye el INFORM game-start tal como lo emitiria el tablero."""
    contenido = crear_cuerpo_game_start(
        oponente=jid_oponente, thread_partida=thread_partida,
    )
    mensaje = Message(to=jid_destino)
    mensaje.sender = JID_TABLERO
    mensaje.set_metadata("ontology", ONTOLOGIA)
    mensaje.set_metadata("performative", contenido.performativa)
    mensaje.thread = thread_partida
    mensaje.body = contenido.cuerpo
    return mensaje


def construir_plantilla_partida(thread_partida: str) -> Template:
    """Plantilla que el jugador registrara al recibir el game-start.

    Filtra por thread (aisla esta partida de cualquier otra) y por
    ontology (descarta ruido del torneo). No filtra por sender para
    mantener la interoperabilidad entre agentes de distintos alumnos.
    """
    plantilla = Template()
    plantilla.thread = thread_partida
    plantilla.set_metadata("ontology", ONTOLOGIA)
    return plantilla


def imprimir_mensaje(titulo: str, mensaje: Message) -> None:
    """Vuelca el mensaje en un formato legible por stdout."""
    print(SEPARADOR)
    print(f"  {titulo}")
    print(SEPARADOR)
    print(f"  to        : {mensaje.to}")
    print(f"  sender    : {mensaje.sender}")
    print(f"  thread    : {mensaje.thread}")
    print("  metadata  :")
    for clave, valor in mensaje.metadata.items():
        print(f"      {clave:<15} = {valor}")
    print("  body (JSON):")
    cuerpo = json.loads(mensaje.body)
    for linea in json.dumps(cuerpo, indent=4, ensure_ascii=False).splitlines():
        print(f"      {linea}")
    print(SEPARADOR)


def imprimir_plantilla(plantilla: Template) -> None:
    """Vuelca la plantilla asociada al behaviour de partida."""
    print("  Template del behaviour de partida (lado jugador):")
    print(f"      thread       = {plantilla.thread}")
    print("      metadata:")
    for clave, valor in plantilla.metadata.items():
        print(f"          {clave:<15} = {valor}")


def principal() -> None:
    """Genera los dos game-start (para X y para O) y los muestra."""
    thread_partida = crear_thread_unico(JID_TABLERO, PREFIJO_THREAD_GAME)

    print()
    print(f"  Thread unico generado por el tablero: {thread_partida}")
    print()

    msg_x = construir_game_start(
        JID_JUGADOR_X, JID_JUGADOR_O, thread_partida,
    )
    imprimir_mensaje("game-start dirigido al jugador X", msg_x)
    print()

    msg_o = construir_game_start(
        JID_JUGADOR_O, JID_JUGADOR_X, thread_partida,
    )
    imprimir_mensaje("game-start dirigido al jugador O", msg_o)
    print()

    plantilla = construir_plantilla_partida(thread_partida)
    print(SEPARADOR)
    imprimir_plantilla(plantilla)
    print(SEPARADOR)
    print()

    cuerpo_x = json.loads(msg_x.body)
    invariante_ok = msg_x.thread == cuerpo_x["thread"]
    print(f"  Invariante msg.thread == body['thread']  -> {invariante_ok}")
    print()


if __name__ == "__main__":
    principal()
