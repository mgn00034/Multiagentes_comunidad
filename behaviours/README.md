# Carpeta `behaviours/` — Comportamientos SPADE

## Propósito

Aquí deben residir los comportamientos que los agentes registran en
su `setup()`. Separar los comportamientos en módulos independientes
permite probarlos de forma aislada (sin infraestructura XMPP) siguiendo
la técnica descrita en la Guía de pruebas aisladas de comportamientos.

## Qué se espera encontrar

Comportamientos del Agente Tablero:

- La máquina de estados finita (FSM) que gestiona el protocolo de
  inscripción de jugadores (FIPA Request).
- La lógica del ciclo de turnos siguiendo el protocolo FIPA Contract Net
  (convocatoria, recepción de propuestas, validación, respuesta).
- El comportamiento que atiende las solicitudes `game-report` del
  Supervisor, separado de los protocolos de juego mediante filtrado con
  `Template` por `thread`.

Comportamientos del Agente Jugador:

- El comportamiento periódico de búsqueda de tableros en la sala MUC.
- El comportamiento de partida, creado dinámicamente al recibir la
  aceptación del tablero, que filtra mensajes por `thread` y gestiona el
  ciclo de juego hasta recibir `game-over`.

Comportamientos del Agente Supervisor:

- [`supervisor_behaviours.py`](supervisor_behaviours.py) — Contiene
  `MonitorizarMUCBehaviour` y `SolicitarInformeFSM`.

## Documentación de análisis y diseño

| Documento | Agente | Contenido |
|-----------|--------|-----------|
| [`BEHAVIOURS_SUPERVISOR.md`](BEHAVIOURS_SUPERVISOR.md) | Supervisor | Fichas técnicas de `MonitorizarMUCBehaviour`, `SolicitarInformeFSM` y `_on_presencia_muc` con diagramas, tabla de eventos del registro y excepciones |

## Orientaciones de diseño

Cada comportamiento debe recibir en su constructor (o vía `self.agent`) toda
la información que necesite del agente: estado del tablero, referencia a
la sala MUC, configuración, etc. Esto permite inyectar objetos simulados en las pruebas
aisladas.

Los comportamientos que procesan mensajes FIPA-ACL deben:

1. Validar siempre el cuerpo del mensaje con `validar_cuerpo()` de la
   ontología antes de actuar.
2. Responder con `not-understood` o `refuse` ante mensajes malformados,
   nunca silenciar el error.
3. Usar `Template` con `ontology="tictactoe"` y `thread` para filtrar
   los mensajes que les corresponden.

Para decidir qué tipo de comportamiento usar, recordad las tres preguntas del
análisis: cuántas veces se ejecuta (una, continua, periódica), si
involucra comunicación, y si tiene etapas con estados.

## Recordatorio

- Las FSM deben tener transiciones bien definidas para todos los casos,
  incluidos errores y tiempos de espera agotados.
- Nunca usar `break` para salir de bucles en comportamientos cíclicos: usar
  una variable de control booleana.
- Los comportamientos dinámicos del jugador se eliminan con `self.kill()`
  al finalizar la partida, nunca dejar comportamientos huérfanos.
