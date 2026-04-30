import pytest
from estrategia.estrategias import estrategia_reglas

def test_estrategia_devuelve_posicion_valida_en_vacio():
    tablero = ["", "", "", "", "", "", "", "", ""]
    mov = estrategia_reglas(tablero, "X")
    assert 0 <= mov <= 8
    assert tablero[mov] == ""

def test_estrategia_elige_unica_casilla_libre():
    tablero = ["X", "O", "X", "X", "O", "O", "O", "X", ""]
    mov = estrategia_reglas(tablero, "X")
    assert mov == 8

def test_estrategia_aprovecha_oportunidad_de_ganar():
    tablero = ["X", "X", "", "O", "O", "", "", "", ""]
    mov = estrategia_reglas(tablero, "X")
    assert mov == 2

def test_estrategia_bloquea_amenaza_rival():
    tablero = ["X", "", "", "O", "O", "", "", "", ""]
    mov = estrategia_reglas(tablero, "X")
    assert mov == 5

def test_estrategia_es_funcion_pura():
    tablero_original = ["X", "", "", "O", "O", "", "", "", ""]
    tablero_copia = list(tablero_original)
    estrategia_reglas(tablero_original, "X")
    assert tablero_original == tablero_copia

def test_estrategia_funciona_para_jugador_O():
    tablero = ["X", "X", "", "O", "O", "", "", "", ""]
    mov = estrategia_reglas(tablero, "O")
    assert mov == 5