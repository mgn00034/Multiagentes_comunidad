"""Script de diagnóstico para detectar agentes en salas MUC.

Se conecta al servidor XMPP configurado en config/config.yaml,
descubre las salas MUC disponibles y lista los ocupantes de cada una.
Usa SPADE (la misma librería que los agentes del sistema) para
garantizar compatibilidad con la configuración del servidor.

Uso:
    python diagnostico_muc.py
"""

import asyncio
import logging
import sys

import slixmpp
import ssl
from slixmpp.exceptions import IqError, IqTimeout
import yaml

# ── Configuración de logging ────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s — %(message)s",
)
logger = logging.getLogger("diagnostico_muc")
logger.setLevel(logging.INFO)


async def diagnosticar_muc(host, puerto, dominio, servicio_muc, password):
    """Se conecta al servidor XMPP y lista las salas MUC con sus ocupantes."""

    jid_diagnostico = f"diagnostico_muc@{dominio}"
    cliente = slixmpp.ClientXMPP(jid_diagnostico, password)

    # ── Desactivar verificación TLS (igual que SPADE) ───────────
    cliente.ssl_context.check_hostname = False
    cliente.ssl_context.verify_mode = ssl.CERT_NONE

    # Plugins necesarios
    cliente.register_plugin("xep_0030")  # Service Discovery
    cliente.register_plugin("xep_0045")  # MUC
    cliente.register_plugin("xep_0077")  # In-Band Registration
    cliente.register_plugin("xep_0199")  # Ping

    # Auto-registro
    async def al_registrar(evento):
        resp = cliente.Iq()
        resp["type"] = "set"
        resp["register"]["username"] = cliente.boundjid.user
        resp["register"]["password"] = password
        try:
            await resp.send()
        except (IqError, IqTimeout):
            pass

    cliente.add_event_handler("register", al_registrar)

    # Evento para esperar la sesión
    sesion_lista = asyncio.Event()

    async def al_iniciar_sesion(evento):
        cliente.send_presence()
        await cliente.get_roster()
        sesion_lista.set()

    cliente.add_event_handler("session_start", al_iniciar_sesion)

    # Colector de presencias MUC recibidas
    presencias_recibidas = {}

    def al_recibir_presencia(presencia):
        """Captura todas las presencias MUC que llegan."""
        jid_from = str(presencia["from"])
        tipo = presencia["type"]
        # Solo nos interesan presencias de salas MUC (contienen @conference)
        if "conference" in jid_from:
            sala_jid = str(presencia["from"].bare)
            nick = str(presencia["from"].resource) if presencia["from"].resource else ""
            if sala_jid not in presencias_recibidas:
                presencias_recibidas[sala_jid] = []
            if nick and nick != "diagnostico_temp" and tipo != "unavailable":
                # Intentar extraer el JID real del item MUC
                jid_real = ""
                try:
                    item_muc = presencia["muc"]["item"]
                    if item_muc["jid"]:
                        jid_real = str(item_muc["jid"])
                except Exception:
                    pass
                presencias_recibidas[sala_jid].append({
                    "nick": nick,
                    "jid_real": jid_real,
                    "tipo": tipo,
                    "show": str(presencia.get("show", "")),
                    "status": str(presencia.get("status", "")),
                })

    cliente.add_event_handler("presence", al_recibir_presencia)

    print(f"\nConectando a {host}:{puerto} (JID: {jid_diagnostico})...")
    cliente.connect(host=host, port=puerto)

    try:
        await asyncio.wait_for(sesion_lista.wait(), timeout=15)
    except asyncio.TimeoutError:
        print("ERROR: Timeout al conectar con el servidor XMPP.")
        cliente.disconnect()
        return

    logger.info("Sesión XMPP iniciada correctamente")

    # ── Paso 1: Descubrir salas MUC ─────────────────────────────
    print("\n" + "=" * 70)
    print(f"  DIAGNÓSTICO MUC — {servicio_muc}")
    print("=" * 70)

    salas_encontradas = []
    try:
        resultado_disco = await cliente["xep_0030"].get_items(
            jid=servicio_muc,
        )
        items = resultado_disco["disco_items"]["items"]
        for item in items:
            jid_sala = str(item[0])
            nombre = item[2] if item[2] else jid_sala
            salas_encontradas.append({
                "jid": jid_sala,
                "nombre": nombre,
            })
    except Exception as error:
        print(f"\nERROR descubriendo salas: {error}")
        cliente.disconnect()
        return

    print(f"\nSalas encontradas: {len(salas_encontradas)}")
    print("-" * 70)

    if not salas_encontradas:
        print("  (ninguna sala MUC encontrada)")
        cliente.disconnect()
        return

    for sala in salas_encontradas:
        print(f"  - {sala['jid']}  ({sala['nombre']})")

    # ── Paso 2: Unirse a todas las salas y recoger presencias ───
    print(f"\nUniéndose a {len(salas_encontradas)} sala(s)...")

    nick_temp = "diagnostico_temp"
    for sala in salas_encontradas:
        jid_sala = sala["jid"]
        try:
            # Enviar presencia de join manualmente (sin esperar)
            stanza = cliente.make_presence(
                pto=f"{jid_sala}/{nick_temp}",
            )
            x_elem = slixmpp.xmlstream.ET.SubElement(
                stanza.xml,
                "{http://jabber.org/protocol/muc}x",
            )
            # Solicitar 0 líneas de historia
            hist = slixmpp.xmlstream.ET.SubElement(x_elem, "history")
            hist.set("maxchars", "0")
            stanza.send()
            logger.info("  Join enviado a %s", jid_sala)
        except Exception as error:
            logger.warning("  Error al enviar join a %s: %s", jid_sala, error)

    # Esperar para recibir todas las presencias de respuesta
    print("Esperando presencias (5 segundos)...")
    await asyncio.sleep(5)

    # ── Paso 3: Recopilar ocupantes únicos por sala ───────────────
    ocupantes_por_sala = {}
    for sala in salas_encontradas:
        jid_sala = sala["jid"]
        ocupantes = presencias_recibidas.get(jid_sala, [])

        nicks_vistos = set()
        ocupantes_unicos = []
        for occ in ocupantes:
            if occ["nick"] not in nicks_vistos:
                nicks_vistos.add(occ["nick"])
                ocupantes_unicos.append(occ)

        if ocupantes_unicos:
            ocupantes_por_sala[jid_sala] = ocupantes_unicos

    # ── Paso 4: Construir tabla única con todas las salas ──────
    # Preparar todas las filas: (sala, nick, jid)
    todas_las_filas = []
    for sala in salas_encontradas:
        jid_sala = sala["jid"]
        ocupantes = ocupantes_por_sala.get(jid_sala, [])
        if not ocupantes:
            continue

        nombre_sala = jid_sala.split("@")[0]
        for occ in ocupantes:
            nick = occ["nick"]
            jid_real = occ.get("jid_real", "")
            jid_bare = jid_real.split("/")[0] if "/" in jid_real else jid_real
            todas_las_filas.append((nombre_sala, nick, jid_bare))

    total_agentes = len(todas_las_filas)

    if todas_las_filas:
        # Calcular anchos de columna
        cabeceras = ("Sala", "Nick", "JID")
        anchos = [len(c) for c in cabeceras]
        for fila in todas_las_filas:
            for i, celda in enumerate(fila):
                if len(celda) > anchos[i]:
                    anchos[i] = len(celda)

        # Imprimir tabla
        print()
        linea_sep = "+" + "+".join("-" * (a + 2) for a in anchos) + "+"
        print(linea_sep)
        fila_cab = "|" + "|".join(
            f" {cabeceras[i]:<{anchos[i]}} " for i in range(len(cabeceras))
        ) + "|"
        print(fila_cab)
        print(linea_sep)

        sala_anterior = ""
        for fila in todas_las_filas:
            # Mostrar nombre de sala solo en la primera fila del grupo
            sala_mostrar = fila[0] if fila[0] != sala_anterior else ""
            sala_anterior = fila[0]
            fila_str = "|" + "|".join(
                f" {celda:<{anchos[i]}} "
                for i, celda in enumerate((sala_mostrar, fila[1], fila[2]))
            ) + "|"
            print(fila_str)

            # Separador entre salas
            siguiente_idx = todas_las_filas.index(fila) + 1
            es_ultima = siguiente_idx >= len(todas_las_filas)
            cambia_sala = (
                not es_ultima
                and todas_las_filas[siguiente_idx][0] != fila[0]
            )
            if cambia_sala:
                print(linea_sep)

        print(linea_sep)

    # ── Salas sin ocupantes ─────────────────────────────────────
    salas_vacias = [
        s["jid"] for s in salas_encontradas
        if s["jid"] not in ocupantes_por_sala
    ]

    # ── Resumen final ───────────────────────────────────────────
    print()
    print("=" * 70)
    print("  RESUMEN")
    print("=" * 70)
    print(f"  Salas totales:       {len(salas_encontradas)}")
    print(f"  Salas con agentes:   {len(ocupantes_por_sala)}")
    print(f"  Salas vacías:        {len(salas_vacias)}")
    print(f"  Total de ocupantes:  {total_agentes}")

    if salas_vacias:
        print(f"\n  Salas vacías:")
        for jid_s in salas_vacias:
            nombre_s = jid_s.split("@")[0]
            print(f"    - {nombre_s}")

    print("=" * 70 + "\n")

    # Salir de las salas y desconectar
    for sala in salas_encontradas:
        try:
            stanza = cliente.make_presence(
                pto=f"{sala['jid']}/{nick_temp}",
                ptype="unavailable",
            )
            stanza.send()
        except Exception:
            pass

    await asyncio.sleep(1)
    cliente.disconnect()


def main():
    """Punto de entrada: lee la configuración y lanza el diagnóstico."""

    ruta_config = "config/config.yaml"
    try:
        with open(ruta_config, encoding="utf-8") as fichero:
            config_completa = yaml.safe_load(fichero)
    except FileNotFoundError:
        print(f"ERROR: No se encontró {ruta_config}")
        sys.exit(1)

    seccion_xmpp = config_completa.get("xmpp", {})
    perfil_activo = seccion_xmpp.get("perfil_activo", "local")
    perfil = seccion_xmpp.get("perfiles", {}).get(perfil_activo, {})

    host = perfil.get("host", "localhost")
    puerto = perfil.get("puerto", 5222)
    dominio = perfil.get("dominio", "localhost")
    servicio_muc = perfil.get(
        "servicio_muc", f"conference.{dominio}",
    )
    password = perfil.get("password_defecto", "secret")

    print(f"Perfil XMPP activo: {perfil_activo}")
    print(f"Servidor: {host}:{puerto}")
    print(f"Servicio MUC: {servicio_muc}")

    asyncio.run(diagnosticar_muc(host, puerto, dominio, servicio_muc, password))


if __name__ == "__main__":
    main()
