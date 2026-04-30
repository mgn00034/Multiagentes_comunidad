"""Fixtures globales compartidas por toda la suite de tests.

Este conftest se aplica a todos los tests del proyecto y se encarga
de la higiene mínima necesaria para que la ejecución sea reproducible
incluso si una sesión anterior fue interrumpida de forma brusca.
"""
import os
import pytest

# Ruta del fichero SQLite usado por los tests de integración del
# supervisor.  Debe coincidir con la constante
# ``RUTA_DB_INTEGRACION`` definida en test_integracion_supervisor.py.
_RUTA_DB_INTEGRACION = "data/integracion.db"

@pytest.fixture(scope="session", autouse=True)
def limpiar_db_integracion_al_inicio():
    """Elimina residuos de la BD de integración antes de cada sesión.

    Si una ejecución previa fue interrumpida (por ejemplo con SIGKILL
    o al cerrar el terminal), SQLite puede dejar un fichero
    ``*.db-journal`` con una transacción a medias que bloquea toda
    escritura posterior hasta su eliminación.  Este fixture garantiza
    que la sesión arranca siempre desde un estado limpio, evitando
    fallos en cascada como ``database is locked``.

    La limpieza solo afecta a los ficheros de tests de integración;
    las bases de datos de producción (``data/supervisor.db``) no se
    tocan.
    """
    for sufijo in ("", "-journal", "-wal", "-shm"):
        fichero = _RUTA_DB_INTEGRACION + sufijo
        if os.path.exists(fichero):
            try:
                os.remove(fichero)
            except OSError:
                pass
    yield



@pytest.fixture
def datos_prueba():
    """Proporciona los datos básicos para aislar los tests del entorno real."""
    return {
        "dominio": "localhost",
        "sala_muc": "tictactoe@conference.localhost",
        "jugador1_nombre": "test_jugador1",
        "jugador2_nombre": "test_jugador2",
        "tablero_nombre": "test_tablero1",
        "puerto_web": 10099
    }

@pytest.fixture
def configuracion_agentes():
    """Simula una carga de agents.yaml para el test de integración."""
    return [
        {
            "nombre": "test_tablero1",
            "clase": "AgenteTablero",
            "modulo": "agentes.agente_tablero",
            "parametros": {}
        },
        {
            "nombre": "test_jugador1",
            "clase": "AgenteJugador",
            "modulo": "agentes.agente_jugador",
            "parametros": {}
        },
        {
            "nombre": "test_jugador2",
            "clase": "AgenteJugador",
            "modulo": "agentes.agente_jugador",
            "parametros": {}
        }
    ]