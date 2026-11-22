"""Genera alertas (indicios, no pruebas) a partir de data/contratos/*.json -> site/data/alertas.json.

Indicadores:
  FRACCIONAMIENTO  Varios contratos menores al mismo adjudicatario, del mismo tipo, en un plazo
                   corto y con objeto parecido, que juntos superan el límite del contrato menor.
  DUPLICADO        Dos contratos casi idénticos (mismo adjudicatario, fecha y objeto, importe ±1 %):
                   puede ser una publicación duplicada o un error; hay que revisarlo.
  UMBRAL           Contrato menor por encima del 90 % del límite legal.
  CONCENTRACION    Un adjudicatario acumula una parte grande de los contratos menores del año.
  OFERTA_UNICA     Licitación adjudicada con una sola oferta.
  SOBRE_LIMITE     Contrato menor que supera el límite legal.

Límites del contrato menor (art. 118 LCSP, sin IVA): obras 40.000 €; servicios y suministros 15.000 €.
"""
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMITE = {"obras": 40000.0, "otros": 15000.0}
VENTANA_DIAS = 90
VACIAS = set("""de del la las el los en y a para con por al un una sito sita c calle n o
contrato tiene objeto ejecucion obra obras servicio servicios suministro suministros prestacion
venta banos palencia municipio municipal ayuntamiento definida memoria tecnica elaborada""".split())


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def nombre_empresa(t: str) -> str:
    t = norm(t)
    t = re.sub(r"\b(s ?l ?u?|s ?a ?u?|slu|sau|sl|sa|sociedad limitada|sociedad anonima)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def palabras(t: str) -> set[str]:
    return {w for w in norm(t).split() if len(w) > 3 and w not in VACIAS}


def parecido(a: str, b: str) -> float:
    pa, pb = palabras(a), palabras(b)
    return len(pa & pb) / max(1, min(len(pa), len(pb)))


def fecha(c):
    f = c.get("fecha_adjudicacion") or (c.get("actualizado") or "")[:10]
    try:
        return date.fromisoformat(f[:10])
    except ValueError:
        return None


def limite(c):
    return LIMITE["obras"] if str(c.get("tipo") or "").startswith("3") else LIMITE["otros"]  # 3, 31, 32...: obras


def alerta(tipo, titulo, detalle, contratos, gravedad):
    return {"tipo": tipo, "titulo": titulo, "detalle": detalle, "gravedad": gravedad,
            "contratos": [{k: c.get(k) for k in ("expediente", "titulo", "adjudicatario", "importe_adjudicado_sin_iva",
                                                    "fecha_adjudicacion", "enlace", "feed", "ofertas_recibidas")} for c in contratos]}


def analizar(contratos: list[dict]) -> list[dict]:
    out = []
    menores = [c for c in contratos if c["feed"] == "menor" and c.get("importe_adjudicado_sin_iva") and c.get("adjudicatario")]

    # DUPLICADO y FRACCIONAMIENTO: agrupar por adjudicatario
    por_emp = defaultdict(list)
    for c in menores:
        por_emp[nombre_empresa(c["adjudicatario"])].append(c)
    vistos, duplicados = set(), set()
    for emp, cs in por_emp.items():
        cs.sort(key=lambda c: fecha(c) or date.min)
        for i, a in enumerate(cs):
            for b in cs[i + 1:]:
                fa, fb = fecha(a), fecha(b)
                if fa and fb and fa == fb and abs(a["importe_adjudicado_sin_iva"] - b["importe_adjudicado_sin_iva"]) <= 0.01 * a["importe_adjudicado_sin_iva"] and parecido(a["titulo"], b["titulo"]) > 0.7:
                    out.append(alerta("DUPLICADO", f"Dos contratos casi idénticos el mismo día ({a['adjudicatario']})",
                                      "Mismo adjudicatario, misma fecha, mismo objeto e importe casi igual. Puede ser una publicación duplicada; si fueran dos contratos reales, juntos superarían el límite del contrato menor.",
                                      [a, b], "media"))
                    vistos |= {id(a), id(b)}
                    duplicados.add(id(b))
        # Fraccionamiento: grupos de objeto parecido en una ventana de tiempo
        for i, a in enumerate(cs):
            grupo = [a] + [b for b in cs[i + 1:] if id(b) not in vistos and b.get("tipo") == a.get("tipo")
                           and fecha(a) and fecha(b) and (fecha(b) - fecha(a)).days <= VENTANA_DIAS and parecido(a["titulo"], b["titulo"]) >= 0.5]
            total = sum(c["importe_adjudicado_sin_iva"] for c in grupo)
            if len(grupo) > 1 and total > limite(a) and id(a) not in vistos:
                out.append(alerta("FRACCIONAMIENTO", f"{len(grupo)} contratos menores parecidos a {a['adjudicatario']} suman {total:,.0f} €".replace(",", "."),
                                  f"En menos de {VENTANA_DIAS} días, con objeto similar. Juntos superan el límite del contrato menor ({limite(a):,.0f} € sin IVA).".replace(",", "."),
                                  grupo, "alta"))
                vistos |= {id(c) for c in grupo}

    for c in menores:
        imp, lim = c["importe_adjudicado_sin_iva"], limite(c)
        if imp > lim:
            out.append(alerta("SOBRE_LIMITE", f"Contrato menor por encima del límite: {imp:,.0f} €".replace(",", "."),
                              f"El límite del contrato menor para este tipo es {lim:,.0f} € sin IVA. Puede deberse a un error de registro del importe.".replace(",", "."), [c], "alta"))
        elif imp >= 0.9 * lim:
            out.append(alerta("UMBRAL", f"Contrato menor justo por debajo del límite ({imp:,.0f} €)".replace(",", "."),
                              f"Está por encima del 90 % del límite ({lim:,.0f} € sin IVA).".replace(",", "."), [c], "baja"))

    # Concentración: sin contar dos veces los posibles duplicados
    unicos = {emp: [c for c in cs if id(c) not in duplicados] for emp, cs in por_emp.items()}
    total_menores = sum(c["importe_adjudicado_sin_iva"] for cs in unicos.values() for c in cs)
    for emp, cs in unicos.items():
        suma = sum(c["importe_adjudicado_sin_iva"] for c in cs)
        if len(cs) >= 3 and total_menores and suma / total_menores >= 0.15:
            out.append(alerta("CONCENTRACION", f"{cs[0]['adjudicatario'].strip(' ,')}: {len(cs)} contratos menores, {round(suma / total_menores * 100)} % del total",
                              f"Suma {suma:,.0f} € de {total_menores:,.0f} € adjudicados por contrato menor en el año.".replace(",", "."), cs, "media"))

    for c in contratos:
        if c["feed"] == "licitacion" and c.get("ofertas_recibidas") == 1:
            out.append(alerta("OFERTA_UNICA", f"Licitación con una sola oferta: {c['titulo'][:80]}",
                              "Solo se presentó una empresa. No es irregular por sí mismo, pero reduce la competencia.", [c], "baja"))
    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted(out, key=lambda a: orden[a["gravedad"]])


def main() -> int:
    salida = {"anios": []}
    for f in sorted((ROOT / "data" / "contratos").glob("*.json")):
        contratos = json.loads(f.read_text(encoding="utf-8"))
        al = analizar(contratos)
        menores = [c for c in contratos if c["feed"] == "menor"]
        salida["anios"].append({"anio": int(f.stem), "n_contratos": len(contratos), "n_menores": len(menores),
                                "importe_menores": round(sum(c.get("importe_adjudicado_sin_iva") or 0 for c in menores), 2),
                                "alertas": al})
        print(f"{f.stem}: {len(contratos)} contratos, {len(al)} alertas")
        for a in al:
            print(f"  [{a['gravedad']}] {a['tipo']}: {a['titulo']}")
    destino = ROOT / "site" / "data"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "alertas.json").write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
