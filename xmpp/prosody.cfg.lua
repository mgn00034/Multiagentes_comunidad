-- =============================================================================
-- Prosody XMPP — Configuración local para Tic-Tac-Toe Multiagente
-- =============================================================================
-- Este fichero configura un servidor Prosody XMPP para desarrollo local.
-- Se monta automáticamente en el contenedor Docker definido en
-- docker-compose.yml. NO es necesario modificarlo salvo que se quiera
-- ajustar algún comportamiento avanzado.
--
-- Características habilitadas:
--   - Registro automático de cuentas (registro dentro de banda): los agentes
--     pueden crear sus propias cuentas al conectarse por primera vez.
--   - Salas MUC (Multi-User Chat) en conference.localhost: permite el
--     descubrimiento entre agentes mediante salas compartidas.
--   - Sin cifrado TLS obligatorio: simplifica el desarrollo local.

-- ─── Administradores ─────────────────────────────────────────────────────────
-- En desarrollo local no se necesitan cuentas de administrador.
admins = {}

-- ─── Módulos globales ────────────────────────────────────────────────────────
-- Estos módulos se cargan para todos los hosts virtuales.
modules_enabled = {
    -- Módulos base de Prosody
    "roster";           -- Gestión de listas de contactos
    "saslauth";         -- Autenticación SASL
    "disco";            -- Descubrimiento de servicios (XEP-0030)
    "posix";            -- Integración con sistemas POSIX (señales, PID)
    "register";         -- Registro de cuentas desde el cliente (dentro de banda)
    "ping";             -- Respuesta a pings XMPP (XEP-0199)
    "pep";              -- Eventos personales (XEP-0163)
    "version";          -- Información de versión del servidor
    "uptime";           -- Tiempo de actividad del servidor
    "time";             -- Hora del servidor
    "presence";         -- Gestión de presencia
}

-- ─── Registro automático de cuentas ──────────────────────────────────────────
-- Permite que los agentes creen sus cuentas al conectarse.
-- En un servidor de producción esto debería estar deshabilitado.
allow_registration = true

-- ─── Seguridad ───────────────────────────────────────────────────────────────
-- Para desarrollo local se desactiva el cifrado obligatorio.
-- En el servidor de la asignatura (sinbad2.ujaen.es) el cifrado sí está activo.
c2s_require_encryption = false
s2s_require_encryption = false
allow_unencrypted_plain_auth = true

-- ─── Autenticación ───────────────────────────────────────────────────────────
-- Se usa autenticación interna en texto plano (adecuada para desarrollo local).
authentication = "internal_plain"

-- ─── Almacenamiento ──────────────────────────────────────────────────────────
-- Almacenamiento interno por defecto (ficheros en /var/lib/prosody).
storage = "internal"

-- ─── Interfaz de escucha ─────────────────────────────────────────────────────
-- Escuchar en todas las interfaces para que sea accesible desde la máquina
-- anfitriona de Docker.
interfaces = { "*" }

-- ─── Servidor virtual: localhost ─────────────────────────────────────────────
-- Este es el dominio XMPP que usan los agentes en el perfil local.
VirtualHost "localhost"

-- ─── Componente MUC: conference.localhost ────────────────────────────────────
-- Salas de chat multiusuario (Multi-User Chat) para el descubrimiento
-- entre agentes.
Component "conference.localhost" "muc"
    modules_enabled = {}

    -- Cualquier usuario puede crear salas (los agentes las crean al unirse)
    restrict_room_creation = false

    -- Desactivar el bloqueo de salas recién creadas. Sin esto, Prosody
    -- deja la sala en estado "locked" hasta que el dueño envíe el
    -- formulario de configuración (cosa que SPADE no hace), impidiendo
    -- que otros agentes se unan y que la sala aparezca en disco#items.
    muc_room_locking = false

    -- Las salas son públicas (descubribles mediante disco#items)
    muc_room_default_public = true

    -- Las salas persisten entre reinicios del servidor
    muc_room_default_persistent = true

    -- Las salas están abiertas a cualquier usuario (no requieren invitación)
    muc_room_default_members_only = false

    -- Sin moderación: todos los participantes pueden enviar mensajes
    muc_room_default_moderated = false

    -- Los usuarios pueden cambiar el asunto de la sala
    muc_room_default_changesubject = true

    -- Historial breve al unirse (últimos 10 mensajes)
    muc_room_default_history_length = 10
