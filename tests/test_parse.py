"""Tests con líneas reales (tal y como salen del PDF de gastos 2025)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from parse import parse_gastos, parse_ingresos  # noqa: E402

GASTOS = """\
ÁREA DE GASTO : 0 DEUDA PÚBLICA.
01 DEUDA PÚBLICA.
011 DEUDA PÚBLICA.
011 310 31001 INTERESES DE PRESTAMOS CON ENTIDADES DE CREDITO 27.006,79
011 310 31002 INTERESES PRESTAMO ENTIDAD PUBLICA
Concepto 27.006,79 310 Intereses
Gastos de formalización, modificación y cancelación 011 311 311 9.000,00
Concepto 311 Gastos de formalización, modificación y cancelación 9.000,00
CAPÍTULO : 3 GASTOS FINANCIEROS 36.006,79
011 911 911 Amortización de préstamos a largo plazo de entes del sector
Amortización de préstamos a largo plazo de entes de fuera de 011 913 913 127.931,16
127.931,16 Amortización de préstamos y de ARTÍCULO 91
CAPÍTULO : 9 PASIVOS FINANCIEROS 127.931,16
TOTAL GR. PROGRA. 011 163.937,95
13 SEGURIDAD Y MOVILIDAD CIUDADANA.
132 SEGURIDAD Y ORDEN PÚBLICO.
Sueldos del Grupo C1 132 120 12003 62.328,96
Trienios 132 120 12006 760,32
CAPÍTULO : 1 GASTOS DE PERSONAL 63.089,28
TOTAL GR. PROGRA. 132 63.089,28
""".splitlines()


def test_gastos():
    g = parse_gastos(GASTOS)
    assert g["avisos"] == []
    assert len(g["partidas"]) == 5
    assert g["total"] == 227027.23
    caps = {c["codigo"]: c["importe"] for c in g["capitulos"]}
    assert caps == {"1": 63089.28, "3": 36006.79, "9": 127931.16}
    progs = {p["codigo"]: p for p in g["programas"]}
    assert progs["132"]["nombre"] == "Seguridad y orden público"
    assert progs["011"]["importe"] == 163937.95
    sueldos = next(p for p in g["partidas"] if p["economica"] == "12003")
    assert sueldos["descripcion"] == "Sueldos del Grupo C1"


def test_gastos_descuadre_genera_aviso():
    g = parse_gastos(GASTOS[:-1] + ["TOTAL GR. PROGRA. 132 99.999,99"])
    assert any("grupo 132" in a for a in g["avisos"])


def test_ingresos():
    lineas = [
        "1 11 112 IMPUESTO SOBRE BIENES INMUEBLES. NATURALEZA RÚSTICA 150.000,00",
        "113 IMPUESTO SOBRE BIENES INMUEBLES. NATURALEZA URBANA",
        "113 00 Urbana",  # no es fila válida (subconcepto de 5 dígitos)
        "11300 X",
        "3 34 343 34300 PABELLON POLIDEPORTIVO",
        "343 34301 PISCINAS 20.000,00",
        "343 34302 CULTURALES 5.000,00",
        "Suman las Previsiones 175.000,00 175.000,00",
    ]
    i = parse_ingresos(lineas)
    caps = {c["codigo"]: c["importe"] for c in i["capitulos"]}
    assert caps == {"1": 150000.0, "3": 25000.0}
    assert i["avisos"] == []
