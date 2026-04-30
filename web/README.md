# Carpeta `web/` — Interfaces web de los agentes

## Propósito

Aquí debe residir todo lo relacionado con las interfaces web que los
agentes exponen para visualizar su estado. Esto incluye los manejadores
HTTP (funciones que atienden las rutas), las plantillas HTML y los
recursos estáticos (CSS, JavaScript).

## Qué se espera encontrar

Interfaz web del Agente Tablero:

- **`/game`** — Página HTML que muestra la rejilla 3x3 visual, los
  nombres de los jugadores (X y O), un indicador del turno actual y un
  registro cronológico de movimientos.
- **`/game/state`** — Ruta JSON que devuelve el estado completo del
  juego con los campos: `tablero`, `jugadores`, `turno_actual`,
  `estado_partida`, `historial` y `ganador`.

Interfaz web del Agente Supervisor:

- **`/supervisor`** — Panel de monitorización en tiempo real para
  el profesor: informes de partida, clasificación de jugadores,
  ocupantes MUC y registro de eventos.
- **`/supervisor/api/state`** — API JSON con el estado en vivo de
  todas las salas monitorizadas.
- **`/supervisor/api/ejecuciones`** — API JSON para consultar
  ejecuciones históricas almacenadas en SQLite.

## Documentación de análisis y diseño

| Documento | Agente | Contenido |
|-----------|--------|-----------|
| [`WEB_SUPERVISOR.md`](WEB_SUPERVISOR.md) | Supervisor | Requisitos, diseño de la interfaz, interacciones del usuario, ciclo de consulta periódica, rutas HTTP, accesibilidad y temas |

## Subcarpetas

### `templates/`

Plantillas HTML para las interfaces web de los agentes. Pueden ser
ficheros HTML simples o plantillas Jinja2 (que aiohttp soporta de
forma nativa).

### `static/`

Ficheros CSS y JavaScript que las páginas HTML necesitan. Si la
actualización en tiempo real se implementa con consulta periódica,
el guion JavaScript que lo realiza debe residir aquí.

## Diagramas

Los diagramas SVG de las interfaces web se encuentran en el directorio
centralizado [`doc/svg/`](../doc/svg/) junto con los demás diagramas
del proyecto:

- [`layout-general.svg`](../doc/svg/layout-general.svg) — Layout: header + sidebar + main
- [`panel-informes.svg`](../doc/svg/panel-informes.svg) — Tarjetas de informe con filtros
- [`panel-ranking.svg`](../doc/svg/panel-ranking.svg) — Clasificación con barras de porcentaje
- [`modal-detalle.svg`](../doc/svg/modal-detalle.svg) — Modal de detalle de informe
- [`ciclo-polling.svg`](../doc/svg/ciclo-polling.svg) — Flujo de datos interfaz ↔ servidor
- [`interacciones-usuario.svg`](../doc/svg/interacciones-usuario.svg) — Mapa de las 6 interacciones
- [`temas-accesibilidad.svg`](../doc/svg/temas-accesibilidad.svg) — Paletas de color y tipografías

## Orientaciones de diseño

Los manejadores HTTP deben acceder al estado del agente a través de la
referencia `request.app["agente"]` (patrón habitual con aiohttp). Esto
permite que los tests creen un servidor de test con estado inyectado,
sin necesidad de un agente SPADE real.

La página HTML debe funcionar sin JavaScript como mínimo (representación
del lado del servidor con el estado actual). El JavaScript para
actualización en tiempo real (consulta periódica cada N segundos o
Server-Sent Events) mejora la experiencia pero no sustituye a la
representación inicial.

Las rutas JSON son las que los tests automatizados verifican con
mayor detalle. Asegúrate de que el JSON devuelto sea conforme a la
ontología y contenga todos los campos obligatorios.

## Recordatorio

- El servidor web se registra en el `setup()` del agente con
  `self.web.start()` y `self.web.app.router.add_get()`.
- El puerto web debe leerse de la configuración, no estar escrito
  directamente en el código.
- Las rutas deben devolver códigos HTTP correctos: 200 para éxito,
  404 para rutas inexistentes, nunca 500 por errores no controlados.
