-- Prosody XMPP Server — Docker (Prácticas SMA, UJA)
-- Configuración con TLS (certificados autofirmados)
-- Puerto principal: 5222 (c2s con STARTTLS)

-- =============================================
-- MÓDULOS HABILITADOS
-- =============================================
modules_enabled = {
    "roster";       -- Lista de contactos
    "saslauth";     -- Autenticación
    "tls";          -- Soporte STARTTLS
    "disco";        -- Descubrimiento de servicios
    "carbons";      -- Sincronización multi-cliente
    "pep";          -- Publicación de presencia
    "private";      -- Almacén XML privado
    "version";      -- Info de versión del servidor
    "uptime";       -- Tiempo de actividad
    "time";         -- Hora del servidor
    "ping";         -- Respuesta a pings XMPP
    "register";     -- Registro in-band (IBR)
    "admin_adhoc";  -- Administración vía cliente
    "posix";        -- Funcionalidad POSIX
}

-- =============================================
-- CERTIFICADOS TLS (autofirmados)
-- Permiten que STARTTLS funcione, necesario
-- para que SPADE/slixmpp pueda autenticarse
-- =============================================
ssl = {
    certificate = "/etc/prosody/certs/prosody.crt";
    key = "/etc/prosody/certs/prosody.key";
}

-- =============================================
-- INTERFACES DE RED
-- =============================================
-- Escuchar en todas las interfaces para que
-- los compañeros del grupo puedan conectarse
c2s_interfaces = { "*" }
http_interfaces = { "*" }

-- =============================================
-- PUERTOS ADICIONALES DESHABILITADOS
-- Solo necesitamos 5222 (c2s con STARTTLS)
-- =============================================
https_ports = {}            -- No necesitamos HTTPS (5281)
c2s_direct_tls_ports = {}   -- No necesitamos Direct TLS (5223)
legacy_ssl_ports = {}       -- No necesitamos Legacy SSL
s2s_direct_tls_ports = {}   -- No necesitamos S2S Direct TLS

-- =============================================
-- REGISTRO AUTOMÁTICO DE AGENTES
-- =============================================
allow_registration = true
min_seconds_between_registrations = 0

-- =============================================
-- SEGURIDAD
-- =============================================
c2s_require_encryption = false    -- No forzar TLS (pero se usa)
s2s_require_encryption = false
s2s_secure_auth = false
authentication = "internal_hashed"

-- =============================================
-- DOMINIO VIRTUAL PARA AGENTES
-- Usar la IP pública del equipo servidor
-- para que los agentes lo localicen en red
-- =============================================
VirtualHost "localhost"  -- ¡Cambiar por tu IP pública real!

-- =============================================
-- COMPONENTE MUC (Multi-User Chat — XEP-0045)
-- Necesario para descubrimiento de servicios
-- mediante salas compartidas (alternativa al DF)
-- El subdominio DEBE ser conference.<VirtualHost>
-- =============================================
Component "conference.localhost" "muc"  -- ¡Cambiar por tu IP pública!
    restrict_room_creation = false         -- cualquier agente puede crear salas
    muc_room_locking = false               -- evita bloqueo al crear salas nuevas
    muc_room_default_public_jids = true   -- JIDs reales visibles (resolución de JID)

-- Logs a consola (visibles con docker compose logs)
log = {
    { levels = { min = "info" }, to = "console" };
}