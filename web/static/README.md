# Carpeta `web/static/` — Recursos estáticos (CSS, JavaScript)

## Propósito

Aquí deben residir los ficheros CSS y JavaScript que la página HTML de
la ruta `/game` necesite. Estos ficheros se sirven como recursos
estáticos a través de aiohttp.

## Orientaciones

Para servir esta carpeta como estáticos, se registra en el setup del
servidor web del agente:

```python
app.router.add_static("/static", "web/static")
```

Y en la plantilla HTML se referencian con:

```html
<link rel="stylesheet" href="/static/estilos.css">
<script src="/static/juego.js"></script>
```

El JavaScript de actualización en tiempo real (consulta periódica o SSE)
puede residir aquí como fichero independiente o estar incrustado
directamente en la plantilla HTML. Ambas opciones son válidas.

Si usas consulta periódica, la función JavaScript debe consultar
`/game/state` cada pocos segundos y actualizar el DOM con los datos
recibidos. Si usas SSE (Server-Sent Events), necesitarás una ruta
adicional en el servidor del agente que emita eventos cuando el estado
cambie.
