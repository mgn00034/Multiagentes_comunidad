# Análisis y Diseño — Agente Organizador de Torneos

**Proyecto:** Tic-Tac-Toe Multiagente

**Asignatura:** Sistemas Multiagente — Universidad de Jaén

**Rama:** `feature/agente-supervisor`

---

## 1. Propósito

El Agente Organizador es un agente SPADE auxiliar cuya única
responsabilidad es **crear y mantener activas** las salas MUC
necesarias para los torneos definidos por el profesor. Al unirse como
ocupante de cada sala, garantiza dos cosas:

1. La sala se crea automáticamente en Prosody cuando el primer
   ocupante se une (comportamiento estándar de MUC).
2. La sala permanece activa mientras el organizador esté conectado,
   evitando que el servidor XMPP la elimine por inactividad.

Este agente implementa la **opción C** de gestión de torneos.
Está **desactivado por defecto** (`activo: false` en `agents.yaml`).

---

## 2. Contexto: opciones de gestión de salas

El sistema ofrece tres formas de gestionar las salas MUC donde se
desarrollan las partidas:

| Opción | Mecanismo | Ventaja |
|--------|-----------|---------|
| **A** — Sin torneos | Se usa la sala por defecto (`tictactoe`) | Simplicidad; sin configuración adicional |
| **B** — Desde el lanzador | `supervisor_main.py --torneos` o `main.py` crean las salas | Configuración mínima; el profesor solo ejecuta una orden |
| **C** — Agente Organizador | Un agente dedicado crea las salas y las mantiene activas | Salas persistentes; extensible con lógica de torneo autónoma |

El organizador solo es necesario cuando se elige la opción C.
**No debe activarse simultáneamente con la opción B** para evitar
conflictos en la creación de salas.

---

## 3. Arquitectura

El organizador es un agente ligero sin comportamientos periódicos
ni máquinas de estados. Toda su lógica se ejecuta una única vez
en `setup()`:

```
┌──────────────────────────────────────────┐
│         AgenteOrganizador                │
│                                          │
│  setup()                                 │
│    ├── Leer ruta_torneos de parámetros   │
│    ├── _cargar_torneos(ruta)             │
│    │     └── yaml.safe_load()            │
│    └── Para cada torneo:                 │
│          ├── Construir JID de sala       │
│          ├── presence.subscribe(jid)     │
│          └── Registrar en salas_creadas  │
│                                          │
│  (mantiene presencia durante ejecución)  │
└──────────────────────────────────────────┘
```

### Relación con el Agente Supervisor

El supervisor descubre las salas creadas por el organizador de forma
automática mediante XEP-0030 (Service Discovery). No existe
comunicación directa entre ambos agentes: la coordinación se produce
a nivel del servidor XMPP.

```
AgenteOrganizador                Servidor XMPP (Prosody)
    │                                    │
    │── subscribe(sala@conference)──────►│  Crea sala MUC
    │                                    │
    │                                    │
AgenteSupervisor                         │
    │── disco#items(conference)─────────►│
    │◄── lista de salas ────────────────│  Descubre la sala
    │── subscribe(sala@conference)──────►│  Se une como observador
```

---

## 4. Ficheros del sistema

| Fichero | Responsabilidad |
|---------|-----------------|
| `agentes/agente_organizador.py` | Clase `AgenteOrganizador(Agent)` — lectura de torneos y creación de salas |
| `config/torneos.yaml` | Definición de torneos con salas, tableros y jugadores |
| `config/agents.yaml` | Entrada del organizador con `activo: false` por defecto |

---

## 5. Estado interno del agente

| Atributo | Tipo | Descripción |
|----------|------|-------------|
| `salas_creadas` | `list[dict]` | Lista de salas MUC creadas con su nombre, JID, descripción, tableros y jugadores asignados |
| `config_xmpp` | `dict` | Configuración del perfil XMPP activo (inyectada por el lanzador) |
| `config_parametros` | `dict` | Parámetros específicos del agente, incluyendo `ruta_torneos` |

---

## 6. Método `setup()` — Inicialización

El organizador no registra comportamientos. Toda su lógica se ejecuta
en `setup()`, que realiza los siguientes pasos:

1. **Obtener el servicio MUC** del perfil XMPP activo
   (`conference.{dominio}`).
2. **Obtener la ruta al fichero de torneos** desde los parámetros del
   agente (`ruta_torneos`, por defecto `config/torneos.yaml`).
3. **Cargar la lista de torneos** llamando a `_cargar_torneos()`.
4. **Para cada torneo**: construir el JID de la sala
   (`{nombre_sala}@{servicio_muc}`), suscribirse a la presencia de
   la sala con `self.presence.subscribe()` y registrar la sala en
   `salas_creadas`.

### Método `_cargar_torneos(ruta)` — Lectura de configuración

| Campo | Descripción |
|-------|-------------|
| **Entrada** | Ruta al fichero YAML (ej: `config/torneos.yaml`) |
| **Salida** | Lista de diccionarios con la definición de cada torneo |
| **Formato aceptado** | Acepta tanto un diccionario con clave `"torneos"` como una lista directa de torneos |
| **Gestión de errores** | Si el fichero no existe (`FileNotFoundError`) o no es YAML válido (`YAMLError`), registra un aviso en el registro y devuelve lista vacía |

---

## 7. Configuración

### 7.1 Parámetros del agente (`agents.yaml`)

```yaml
- nombre: organizador
  clase: AgenteOrganizador
  modulo: agentes.agente_organizador
  nivel: 1
  descripcion: "Organizador de torneos — crea salas MUC"
  parametros:
    ruta_torneos: config/torneos.yaml
  activo: false    # ← cambiar a true para activarlo
```

### 7.2 Formato de torneos (`config/torneos.yaml`)

```yaml
torneos:
  - nombre: torneo_primavera
    sala: torneo_primavera
    descripcion: "Torneo de primavera — todos los alumnos"
    tableros:
      - tablero_mesa1
      - tablero_mesa2
    jugadores:
      - jugador_ana
      - jugador_luis
```

Cada torneo genera una sala MUC con el nombre indicado en `sala`.
Los campos `tableros` y `jugadores` son **informativos** en modo
distribuido: cada alumno configura su agente de forma independiente.

### 7.3 Formatos de torneo habituales

**Torneo único** — Todos los alumnos en la misma sala:

```yaml
torneos:
  - nombre: torneo_clase
    sala: torneo_clase
    descripcion: "Torneo de toda la clase"
```

**Fase de grupos + final** — Salas separadas por grupo, con una
sala final para los ganadores:

```yaml
torneos:
  - nombre: grupo_a
    sala: grupo_a
    descripcion: "Fase de grupos — Grupo A"

  - nombre: grupo_b
    sala: grupo_b
    descripcion: "Fase de grupos — Grupo B"

  - nombre: final
    sala: final_torneo
    descripcion: "Final — ganadores de cada grupo"
```

---

## 8. Activación y uso

### 8.1 Activar el organizador

1. Editar `config/agents.yaml` y cambiar `activo: true` en la
   entrada del organizador.
2. Verificar que `config/torneos.yaml` contiene los torneos deseados.
3. **Desactivar la opción B** si estaba en uso (no crear salas
   desde `main.py` con `--torneos` simultáneamente).

### 8.2 Flujo de ejecución

1. El organizador arranca como cualquier otro agente SPADE.
2. Lee `torneos.yaml` y se une a cada sala (creándola si no existe).
3. Se mantiene como ocupante de las salas durante toda la ejecución.
4. Los alumnos conectan sus agentes a las salas.
5. El supervisor descubre las salas vía XEP-0030 y las monitoriza.

### 8.3 ¿Cuándo usar el organizador?

| Escenario | ¿Usar organizador? |
|-----------|-------------------|
| Pruebas rápidas sin torneos | No — usar sala por defecto |
| Torneo distribuido en clase | Opcional — la opción B es más sencilla |
| Torneos prolongados (varias horas) | Sí — mantiene las salas activas |
| Futuras ampliaciones con lógica de torneo | Sí — extensible |

---

## 9. Limitaciones conocidas

1. **Sin comportamientos activos.** El organizador no tiene
   comportamientos periódicos ni reactivos: solo se ejecuta en
   `setup()` y permanece conectado. No gestiona emparejamientos,
   fases ni clasificaciones.

2. **Creación por suscripción.** Las salas se crean mediante
   `presence.subscribe()` en lugar de `muc.join()`. Esto funciona
   con Prosody pero podría no ser compatible con todos los servidores
   XMPP.

3. **Sin verificación de existencia.** El organizador no comprueba
   si la sala ya existe antes de suscribirse. Si la sala ya fue
   creada (por la opción B o por una ejecución anterior), la
   suscripción es redundante pero no causa errores.

---

## 10. Extensiones futuras

El organizador está diseñado como punto de partida para que los
alumnos implementen lógica de torneo más avanzada:

- **Emparejamientos automáticos:** asignar jugadores a tableros
  de forma dinámica según un bracket de torneo.
- **Fases eliminatorias:** gestionar rondas y transiciones entre
  grupos y finales.
- **Clasificaciones en tiempo real:** calcular y publicar
  clasificaciones a medida que se reciben resultados.
- **Notificaciones:** enviar mensajes a los jugadores cuando les
  toca jugar o cuando cambia de fase el torneo.
