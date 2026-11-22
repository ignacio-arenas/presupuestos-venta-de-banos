"""Resume data/conprel/*.json (extraídos con conprel.py) en site/data/hacienda.json.

Campos de las liquidaciones (tb_economica):
  imported = créditos / previsiones definitivas (presupuesto tras modificaciones)
  importer = obligaciones / derechos reconocidos netos (lo realmente gastado / ingresado)
  importel = pagos / recaudación líquida

Si existe site/data/presupuestos.json (extraído de los PDFs del Ayuntamiento),
compara sus totales con los de Hacienda como control de calidad.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "conprel"

AREAS = {
    "0": "Deuda pública",
    "1": "Servicios públicos básicos",
    "2": "Protección y promoción social",
    "3": "Bienes públicos de carácter preferente",
    "4": "Actuaciones de carácter económico",
    "9": "Actuaciones de carácter general",
}
CAPS = {
    "G": {"1": "Gastos de personal", "2": "Bienes corrientes y servicios", "3": "Gastos financieros",
          "4": "Transferencias corrientes", "5": "Fondo de contingencia", "6": "Inversiones reales",
          "7": "Transferencias de capital", "8": "Activos financieros", "9": "Pasivos financieros"},
    "I": {"1": "Impuestos directos", "2": "Impuestos indirectos", "3": "Tasas, precios públicos y otros ingresos",
          "4": "Transferencias corrientes", "5": "Ingresos patrimoniales", "6": "Enajenación de inversiones reales",
          "7": "Transferencias de capital", "8": "Activos financieros", "9": "Pasivos financieros"},
}


def cargar(tipo: str, anio: int):
    f = SRC / f"{tipo}_{anio}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def bonito(txt: str) -> str:
    txt = re.sub(r"^CAP\.\s*[IVX]+\s*", "", txt.strip())
    return txt[:1].upper() + txt[1:].lower() if txt.isupper() else txt


def hojas(codigos: set[str]) -> set[str]:
    """Códigos sin hijos (el nivel más detallado disponible en cada rama)."""
    return {c for c in codigos if not any(o != c and o.startswith(c) for o in codigos)}


def r2(x: float) -> float:
    return round(x, 2)


def resumir(anio: int, p: dict | None, l: dict | None) -> dict:
    base = p or l
    nom_eco = {(r["tipreig"], r["cdcta"]): bonito(r["nombre"]) for r in base["codigos"]["tb_cuentasEconomica"]}
    nom_prog = {r["cdfgr"]: bonito(r["nombre"]) for r in base["codigos"]["tb_cuentasProgramas"]}
    fila = {"anio": anio, "poblacion": int(base["ente"]["poblacion"])}

    # ---- Clasificación económica: inicial (presupuesto) + definitivo/ejecutado (liquidación)
    eco: dict[tuple, dict] = defaultdict(dict)
    for r in (p["tablas"]["tb_economica"] if p else []):
        eco[(r["tipreig"], r["cdcta"])]["inicial"] = float(r["importe"])
    for r in (l["tablas"]["tb_economica"] if l else []):
        d = eco[(r["tipreig"], r["cdcta"])]
        d["definitivo"], d["ejecutado"], d["pagado"] = float(r["imported"]), float(r["importer"]), float(r["importel"])

    for tip, clave in (("G", "gastos"), ("I", "ingresos")):
        cods = {c for t, c in eco if t == tip}
        caps = sorted(c for c in cods if len(c) == 1)
        fila[clave] = {
            "capitulos": [{"codigo": c, "nombre": CAPS[tip].get(c, c), **{k: r2(v) for k, v in eco[(tip, c)].items()}} for c in caps],
            "partidas": sorted(
                ({"codigo": c, "nombre": nom_eco.get((tip, c), c), "capitulo": c[0], **{k: r2(v) for k, v in eco[(tip, c)].items()}}
                 for c in hojas(cods)),
                key=lambda x: x["codigo"],
            ),
        }
        for k in ("inicial", "definitivo", "ejecutado"):
            vals = [x[k] for x in fila[clave]["capitulos"] if k in x]
            if vals:
                fila[clave][f"total_{k}"] = r2(sum(vals))

    # ---- Clasificación por programas (área = 1 dígito, grupo de programa = 3 dígitos)
    def programas(datos, nivel):
        out = defaultdict(float)
        for r in datos["tablas"].get("tb_funcional", []) if datos else []:
            if len(r["cdfgr"]) == nivel:
                out[r["cdfgr"]] += float(r["importe"])
        return out

    for nivel, clave, nombres in ((1, "areas", AREAS), (3, "programas", nom_prog)):
        ini, eje = programas(p, nivel), programas(l, nivel)
        fila[clave] = sorted(
            ({"codigo": c, "nombre": nombres.get(c, c), **({"inicial": r2(ini[c])} if c in ini else {}), **({"ejecutado": r2(eje[c])} if c in eje else {})}
             for c in set(ini) | set(eje)),
            key=lambda x: x["codigo"],
        )
    fila["tiene_presupuesto"], fila["tiene_liquidacion"] = bool(p), bool(l)
    for datos, base in ((l, "gasto real"), (p, "presupuesto inicial")):
        if datos and datos.get("comparativa"):
            fila["comparativa"] = {"base": base, **datos["comparativa"]}
            break
    if l and l["tablas"].get("tb_remanente"):
        fila["remanente"] = remanente(anio, l["tablas"]["tb_remanente"])
    return fila


def remanente(anio: int, filas: list[dict]) -> dict:
    """Remanente de tesorería al cierre del ejercicio (tb_remanente, códigos cdrmte)."""
    v = {r["cdrmte"]: float(r["importe"]) for r in filas}
    g = lambda c: r2(v.get(c, 0.0))  # noqa: E731
    out = {
        "fondos_liquidos": g("011"),
        "pendiente_cobro": g("012"),
        "pendiente_pago": g("013"),
        "partidas_pendientes": g("2"),
        "total": g("01"),
        "dudoso_cobro": g("02"),
        "financiacion_afectada": g("03"),
        "gastos_generales": g("0"),
        "obligaciones_pendientes_aplicar": r2(v.get("04", 0.0) + v.get("05", 0.0)),
        "gastos_generales_ajustado": g("1") if "1" in v else g("0"),
    }
    # Comprobaciones de la propia estructura del estado de remanente
    calc_total = out["fondos_liquidos"] + out["pendiente_cobro"] - out["pendiente_pago"] + out["partidas_pendientes"]
    calc_gg = out["total"] - out["dudoso_cobro"] - out["financiacion_afectada"]
    for nombre, calc, real in (("total", calc_total, out["total"]), ("gastos generales", calc_gg, out["gastos_generales"])):
        if abs(calc - real) > 1:
            print(f"  ⚠ Remanente {anio} {nombre}: calculado {calc:,.2f} vs Hacienda {real:,.2f}")
    return out


def control_pdf(salida: dict) -> None:
    f = ROOT / "site" / "data" / "presupuestos.json"
    if not f.exists():
        return
    for ej in json.loads(f.read_text(encoding="utf-8"))["ejercicios"]:
        h = next((a for a in salida["anios"] if a["anio"] == ej["anio"]), None)
        if not h:
            continue
        for tipo in ("gastos", "ingresos"):
            pdf = ej.get(tipo, {}).get("total_pdf") or ej.get(tipo, {}).get("total")
            hac = h[tipo].get("total_inicial")
            if pdf is None or hac is None:
                continue
            estado = "OK" if abs(pdf - hac) < 0.05 else "DESCUADRE"
            print(f"Control PDF vs Hacienda {ej['anio']} {tipo}: {pdf:,.2f} / {hac:,.2f} -> {estado}")


def main() -> int:
    anios = sorted({int(f.stem.split("_")[1]) for f in SRC.glob("*.json")})
    salida = {"fuente": "Ministerio de Hacienda, CONPREL", "anios": []}
    for a in anios:
        p, l = cargar("presupuestos", a), cargar("liquidaciones", a)
        if p or l:
            salida["anios"].append(resumir(a, p, l))
            print(a, "presupuesto" if p else "-", "liquidación" if l else "-")
    # Deuda: flujos anuales de la liquidación (capítulos 3 y 9) + deuda viva publicada por Hacienda
    for a in salida["anios"]:
        if a["tiene_liquidacion"]:
            cg = {c["codigo"]: c for c in a["gastos"]["capitulos"]}
            ci = {c["codigo"]: c for c in a["ingresos"]["capitulos"]}
            a["deuda"] = {
                "amortizacion": cg.get("9", {}).get("ejecutado", 0.0),
                "prestamos_recibidos": ci.get("9", {}).get("ejecutado", 0.0),
                "intereses": cg.get("3", {}).get("ejecutado", 0.0),
            }
    dv = ROOT / "data" / "deuda_viva.json"
    if dv.exists():
        viva = json.loads(dv.read_text(encoding="utf-8"))
        salida["deuda_viva"] = viva["datos"]
        for d in viva["datos"]:
            a = next((x for x in salida["anios"] if x["anio"] == d["anio"]), None)
            if a is not None:
                a.setdefault("deuda", {})["viva"] = d["deuda"]
    control_pdf(salida)
    destino = ROOT / "site" / "data"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "hacienda.json").write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
