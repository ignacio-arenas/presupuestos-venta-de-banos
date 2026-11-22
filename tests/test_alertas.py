import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from alertas import analizar  # noqa: E402


def c(titulo, emp, imp, f, tipo="3", feed="menor", **kw):
    return {"titulo": titulo, "adjudicatario": emp, "importe_adjudicado_sin_iva": imp, "fecha_adjudicacion": f, "tipo": tipo, "feed": feed, **kw}


def tipos(al):
    return sorted(a["tipo"] for a in al)


def test_duplicado():
    al = analizar([c("sustitución del pavimento del parque infantil Pza España", "CONSTRUCCIONES CASTAÑEDA S.L", 32966.66, "2022-06-10"),
                   c("sustitución del pavimento del parque infantil Pza España", "CONSTRUCCIONES CASTAÑEDA S.L,", 32966.96, "2022-06-10")])
    assert "DUPLICADO" in tipos(al) and "FRACCIONAMIENTO" not in tipos(al)


def test_fraccionamiento():
    al = analizar([c("renovación acerado calle Mayor tramo 1", "Obras X SL", 25000, "2022-03-01"),
                   c("renovación acerado calle Mayor tramo 2", "OBRAS X, S.L.", 24000, "2022-04-15")])
    assert tipos(al) == ["FRACCIONAMIENTO"]


def test_sin_alertas_y_umbral():
    assert analizar([c("pintura colegio", "A", 5000, "2022-01-01", tipo="2")]) == []
    assert tipos(analizar([c("auditoría", "B", 14500, "2022-01-01", tipo="2")])) == ["UMBRAL"]


def test_oferta_unica():
    assert tipos(analizar([c("gestión bar", None, None, None, feed="licitacion", ofertas_recibidas=1)])) == ["OFERTA_UNICA"]


def test_no_fracciona_por_frases_hechas():
    al = analizar([c("El contrato tiene por objeto la ejecución de la obra de urbanización de la C/Las Eras.", "U SL", 28900, "2022-12-14"),
                   c("El contrato tiene por objeto la ejecución de la obra de derribo parcial del edificio Gaseosas", "U SL", 13500, "2022-12-29")])
    assert "FRACCIONAMIENTO" not in tipos(al)
