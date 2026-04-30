# Carpeta `persistencia/` — Capas de persistencia de los agentes

## Propósito

Aquí deben residir las clases que proporcionan persistencia de datos
a los agentes del sistema. Separar la persistencia en módulos
independientes permite probarla de forma aislada (con bases de datos
temporales) sin necesidad de arrancar agentes SPADE ni servidores XMPP.

## Qué se espera encontrar

Persistencia del Agente Supervisor:

- [`almacen_supervisor.py`](almacen_supervisor.py) — Clase
  `AlmacenSupervisor` que gestiona una base de datos SQLite con
  ejecuciones, informes de partida y eventos del log.

## Documentación de análisis y diseño

| Documento | Agente | Contenido |
|-----------|--------|-----------|
| [`PERSISTENCIA_SUPERVISOR.md`](PERSISTENCIA_SUPERVISOR.md) | Supervisor | Esquema relacional (3 tablas), ciclo de vida, flujo de datos, API de métodos, decisiones de diseño y pruebas |

## Diagramas

Los diagramas SVG de la capa de persistencia se encuentran en
[`doc/svg/`](../doc/svg/):

- [`persistencia-esquema.svg`](../doc/svg/persistencia-esquema.svg) — Esquema relacional de las 3 tablas con claves foráneas
- [`persistencia-ciclo-vida.svg`](../doc/svg/persistencia-ciclo-vida.svg) — Ciclo de vida de una ejecución (init → crear → operar → finalizar → cerrar)
- [`persistencia-flujo-datos.svg`](../doc/svg/persistencia-flujo-datos.svg) — Flujo de escritura (agente → SQLite) y lectura (panel web → SQLite)

## Orientaciones de diseño

Cada clase de persistencia debe:

1. Recibir la ruta de la base de datos como parámetro del constructor
   (nunca escrita directamente en el código).
2. Crear el directorio intermedio automáticamente si no existe.
3. Utilizar `CREATE TABLE IF NOT EXISTS` para ser idempotente.
4. Ejecutar `COMMIT` tras cada escritura para garantizar durabilidad.
5. Usar parámetros posicionales (`?`) en todas las consultas SQL
   para prevenir inyección.
6. Almacenar datos estructurados como JSON en columnas TEXT cuando
   la estructura pueda evolucionar.

## Recordatorio

- La ruta de la base de datos debe leerse de la configuración
  (`agents.yaml` o argumentos de línea de órdenes), no del código.
- El directorio `data/` está en `.gitignore`: los ficheros `.db`
  no se suben al repositorio.
- Las pruebas deben usar ficheros SQLite temporales que se eliminen
  al finalizar cada prueba.
