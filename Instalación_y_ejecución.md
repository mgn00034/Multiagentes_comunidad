# Sistema Multiagente: Tic-Tac-Toe (Nivel 1)

**Autor:** Mario Guijarro Navío  
**Asignatura:** Sistemas Multiagentes  
**Universidad de Jaén**

Este proyecto implementa un sistema multiagente completo en SPADE que juega al Tres en Raya, cumpliendo con todos los requisitos para la máxima calificación (Estrategia Nivel 4 con LLM, descubrimiento MUC nativo, interfaz web en tiempo real y concurrencia de partidas).

---

## 1. Requisitos Previos

Para ejecutar el sistema, necesitas tener instalado en tu máquina:

1. **Python 3.11 o superior** (Preferiblemente 3.12).
2. **Servidor XMPP**: 
   - Local: Prosody instalado o ejecutándose vía Docker.
   - Remoto: Acceso a `sinbad2.ujaen.es` (requiere red Eduroam o VPN de la UJA).
3. **Docker** *(Solo necesario para probar el LLM en local)*: Para levantar la infraestructura de Ollama.

---

## 2. Instalación

Abre una terminal en el directorio raíz del proyecto y ejecuta:

1. **Crear y activar un entorno virtual:**
   ```bash
   python -m venv .venv
   # En Windows:
   .venv\Scripts\activate
   # En Linux/Mac:
   source .venv/bin/activate
   ```

2. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 3. Configuración de Entornos (XMPP y LLM)

La configuración se gestiona íntegramente desde los archivos YAML en `config/`, **sin necesidad de tocar el código fuente**.

### Archivo `config/config.yaml`
Puedes alternar entre ejecutar el sistema en tu casa (local) o en la universidad modificando los campos `perfil_activo`:

* **Modo Local:** Pon `perfil_activo: local` en `xmpp` y en `llm`. 
* **Modo Universidad:** Pon `perfil_activo: servidor` en `xmpp` y en `llm`. El sistema se conectará automáticamente al servidor `sinbad2.ujaen.es:8022` y a la IA `sinbad2ia.ujaen.es`.

### Archivo `config/agents.yaml`
Define qué agentes se levantan al inicio. Para probar la Inteligencia Artificial, asegúrate de que un jugador tenga configurado el `nivel_estrategia: 4`.
*(Nota: El sistema está diseñado para que, si el LLM falla, da timeout o alucina, degrade automáticamente al Nivel 3 - Minimax invencible, garantizando que la partida nunca se cuelgue).*

---

## 4. Ejecución de la IA Local (Opcional)

Si utilizas el perfil `local` para el LLM, necesitas arrancar el contenedor de Ollama. Desde la raíz del proyecto (o donde tengas tu `docker-compose.yml`), ejecuta:

```bash
# 1. Levantar el contenedor de Ollama
docker compose up -d

# 2. Descargar el modelo ligero (3B parámetros)
docker exec ollama-local ollama pull llama3.2:3b
```

---

## 5. Ejecución del Sistema

Con el entorno virtual activado y el servidor XMPP encendido (o conectado a la VPN), arranca el enjambre de agentes:

```bash
python main.py
```

### Interfaz Web de Supervisión
Una vez arrancado, el Agente Tablero levantará un servidor web. Abre tu navegador y accede a:

**http://localhost:15000/game**

**Características de la web:**
* **Tiempo Real:** Actualización automática por *Polling* (1 petición/s) contra el endpoint ontológico `/game/state`.
* **Reproducción:** Controles inferiores para pausar el directo y navegar por los turnos históricos de la partida.
* **Modo Oscuro:** Botón superior derecho con persistencia de preferencia.
* **Historial Global:** Recuento total de partidas registradas.

---

## 6. Batería de Tests (Validación)

El proyecto incluye 5 baterías de pruebas (más de 90 tests) que cubren ontología, estrategias puras, lógicas aisladas de behaviours, concurrencia web HTTP y mensajería real XMPP E2E.

Para ejecutar la batería completa:
```bash
pytest tests/ -v
```

*Nota sobre `test_integracion.py`: Este test realiza conexiones reales. Si el servidor XMPP configurado no está disponible, el test hace un `SKIP` automático para evitar falsos negativos por falta de red.*