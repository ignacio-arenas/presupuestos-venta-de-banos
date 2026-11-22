"""Resume data/conprel/*.json (extraídos con conprel.py) en site/data/hacienda.json.

Campos de las liquidaciones (tb_economica):
  imported = créditos / previsiones definitivas (presupuesto tras modificaciones)
  importer = obligaciones / derechos reconocidos netos (lo realmente gastado / ingresado)
  importel = pagos / recaudación líquida
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "conprel"


def cargar(tipo: str, anio: int):
    f = SRC / f"{tipo}_{anio}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def por_capitulo(filas, tip, campo):
    return {r["cdcta"]: round(float(r[campo]), 2) for r in filas if r["tipreig"] == tip and len(r["cdcta"]) == 1}


def por_area(filas, campo="importe"):
    out = defaultdict(float)
    for r in filas:
        if len(r["cdfgr"]) == 1:  # área de gasto
            out[r["cdfgr"]] += float(r[campo])
    return {k: round(v, 2) for k, v in out.items()}


def main() -> int:
    anios = sorted({int(f.stem.split("_")[1]) for f in SRC.glob("*.json")})
    salida = {"fuente": "Ministerio de Hacienda, CONPREL", "anios": []}
    for a in anios:
        p, l = cargar("presupuestos", a), cargar("liquidaciones", a)
        fila = {"anio": a}
        if p:
            e = p["tablas"]["tb_economica"]
            fila["poblacion"] = int(p["ente"]["poblacion"])
            fila["presupuesto"] = {
                "gastos": por_capitulo(e, "G", "importe"),
                "ingresos": por_capitulo(e, "I", "importe"),
                "areas": por_area(p["tablas"].get("tb_funcional", [])),
            }
        if l:
            e = l["tablas"]["tb_economica"]
            fila.setdefault("poblacion", int(l["ente"]["poblacion"]))
            fila["liquidacion"] = {
                "gastos_definitivo": por_capitulo(e, "G", "imported"),
                "gastos_ejecutado": por_capitulo(e, "G", "importer"),
                "gastos_pagado": por_capitulo(e, "G", "importel"),
                "ingresos_definitivo": por_capitulo(e, "I", "imported"),
                "ingresos_reconocido": por_capitulo(e, "I", "importer"),
                "ingresos_recaudado": por_capitulo(e, "I", "importel"),
                "areas_ejecutado": por_area(l["tablas"].get("tb_funcional", [])),
            }
        salida["anios"].append(fila)
        print(a, "presupuesto" if p else "-", "liquidación" if l else "-")

    destino = ROOT / "site" / "data"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "hacienda.json").write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
