# Carpeta `web/templates/` — Plantillas HTML

## Propósito

Aquí deben residir las plantillas HTML que el servidor web del Agente
Tablero representa al atender la ruta `/game`.

## Orientaciones

Puedes usar HTML simple (la función manejadora construye el HTML como
cadena) o plantillas Jinja2 (que aiohttp soporta de forma nativa con
`aiohttp_jinja2`). La segunda opción es más limpia cuando la página tiene
cierta complejidad.

La plantilla de la página de juego debe contener como mínimo:

- Una rejilla de 3x3 celdas con clases CSS identificables (`celda`,
  `cell` o `casilla`), o una tabla HTML con `<td>`.
- Los nombres o JIDs de los jugadores X y O.
- Un indicador visible del turno actual.
- Una sección con id o clase `historial` (o `history`, `movimientos`)
  que muestre el registro cronológico de movimientos.
- Un guion que consulte periódicamente `/game/state` para actualizar
  la página, o bien un mecanismo SSE (Server-Sent Events).

Estos elementos son los que los tests de `tests/test_web_endpoints.py`
buscan con BeautifulSoup, así que su presencia es verificable
automáticamente.
