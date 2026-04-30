import logging
from datetime import datetime
from validacion.informe_alumno import (
    crear_partida_observada,
    crear_informe_alumno,
    serializar_informe_alumno
)


def generar_informe_automatico(partidas_brutas, equipo, puesto, hora_inicio, dominio_servidor="sinbad2.ujaen.es",
                               ruta_salida="informe_integracion.json"):
    """
    Transforma el historial de partidas al formato oficial y lo guarda.
    """
    logging.info(f"📊 Procesando {len(partidas_brutas)} partidas para el informe...")
    partidas_formateadas = []

    for p in partidas_brutas:
        try:
            ganador = p.get("winner")
            if ganador in [None, "None", ""]: ganador = None

            resultado = p.get("result", "aborted")
            razon = p.get("reason")
            if resultado != "aborted":
                razon = None
            elif razon not in ["invalid", "timeout", "both-timeout"]:
                razon = "timeout"  # Valor por defecto seguro

            jugadores = {s: j.split('@')[0] + f"@{dominio_servidor}"
                         for s, j in p.get("players", {}).items()}

            tablero_jid = f"tablero_{puesto}@{dominio_servidor}"

            partida_obs = crear_partida_observada(
                tablero_jid=tablero_jid,
                resultado=resultado,
                ganador_ficha=ganador,
                jugadores=jugadores,
                turnos=len(p.get("history", [])),
                tablero_final=p.get("tablero"),
                timestamp=datetime.now().strftime("%H:%M:%S"),
                razon=razon
            )
            partidas_formateadas.append(partida_obs)
        except Exception as e:
            logging.error(f"⚠️ Error formateando partida: {e}")

    agentes_desplegados = [
        {"jid": f"tablero_{puesto}@{dominio_servidor}", "rol": "tablero"},
        {"jid": f"judador_{puesto}_mgn00034_01@{dominio_servidor}", "rol": "jugador"},
        {"jid": f"judador_{puesto}_mgn00034_02@{dominio_servidor}", "rol": "jugador"}
    ]

    informe = crear_informe_alumno(
        equipo=equipo,
        puesto=puesto,
        timestamp_inicio=hora_inicio,
        timestamp_fin=datetime.now().isoformat(),
        agentes_desplegados=agentes_desplegados,
        partidas_observadas=partidas_formateadas
    )

    try:
        serializar_informe_alumno(informe, ruta_salida)
        logging.info(f"✅ ¡Archivo '{ruta_salida}' creado con éxito!")
    except ValueError as e:
        logging.error(f"❌ El informe no es válido según el esquema: {e}")
    except Exception as e:
        logging.error(f"❌ Error inesperado al escribir el archivo: {e}")