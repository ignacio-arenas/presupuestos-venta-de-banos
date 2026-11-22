"""Convierte los PDFs de data/raw/<año>/ en site/data/presupuestos.json.

El texto de los PDFs del Ayuntamiento (generados con el programa de contabilidad
municipal) sale bastante desordenado, así que el parser se apoya en patrones
robustos (códigos de clasificación + importes) y luego CUADRA los resultados
contra los totales que el propio PDF imprime. Cualquier descuadre se guarda en
"avisos" y se muestra en la web en vez de ocultarse.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IMPORTE = r"\d{1,3}(?:\.\d{3})*,\d{2}"
RE_IMPORTE = re.compile(rf"(?<![\d.,]){IMPORTE}(?![\d,])")

# Clasificación económica (Orden EHA/3565/2008)
CAPITULOS_GASTOS = {
    "1": "Gastos de personal",
    "2": "Gastos corrientes en bienes y servicios",
    "3": "Gastos financieros",
    "4": "Transferencias corrientes",
    "5": "Fondo de contingencia",
    "6": "Inversiones reales",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}
CAPITULOS_INGRESOS = {
    "1": "Impuestos directos",
    "2": "Impuestos indirectos",
    "3": "Tasas, precios públicos y otros ingresos",
    "4": "Transferencias corrientes",
    "5": "Ingresos patrimoniales",
    "6": "Enajenación de inversiones reales",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}
# Clasificación por programas: áreas de gasto
AREAS = {
    "0": "Deuda pública",
    "1": "Servicios públicos básicos",
    "2": "Protección y promoción social",
    "3": "Bienes públicos de carácter preferente",
    "4": "Actuaciones de carácter económico",
    "9": "Actuaciones de carácter general",
}


def euros(txt: str) -> float:
    return round(float(txt.replace(".", "").replace(",", ".")), 2)


def limpiar(txt: str) -> str:
    txt = RE_IMPORTE.sub(" ", txt)
    txt = re.sub(r"\s+", " ", txt).strip(" .-")
    return txt[:1].upper() + txt[1:].lower() if txt.isupper() else txt


def cuadra(a: float, b: float) -> bool:
    return abs(a - b) < 0.05


# ---------------------------------------------------------------- GASTOS ----

RE_G_PARTIDA = re.compile(r"(?<!\d)(\d{3}) (\d{3}) (\d{3,5})(?!\d)")
RE_G_CAPITULO = re.compile(rf"CAP[ÍI]TULO\s*:\s*(\d)\b.*?({IMPORTE})\s*$")
RE_G_TOTAL_GP = re.compile(rf"TOTAL GR\. ?PROGRA\.?\s*(\d{{3}})\s+({IMPORTE})")
RE_G_GRUPO = re.compile(r"^(\d{3}) ([A-ZÁÉÍÓÚÑÜ][^\d]+)$")
RE_G_POLITICA = re.compile(r"^(\d{2}) ([A-ZÁÉÍÓÚÑÜ][^\d]+)$")


def parse_gastos(lineas: list[str]) -> dict:
    partidas, avisos = [], []
    nombres_gp: dict[str, str] = {}
    nombres_pol: dict[str, str] = {}
    cap_pdf: dict[str, float] = defaultdict(float)
    gp_pdf: dict[str, float] = {}

    for linea in lineas:
        linea = linea.strip()
        if m := RE_G_TOTAL_GP.search(linea):
            gp_pdf[m.group(1)] = euros(m.group(2))
            continue
        if m := RE_G_CAPITULO.search(linea):
            cap_pdf[m.group(1)] += euros(m.group(2))
            continue
        if m := RE_G_GRUPO.match(linea):
            nombres_gp[m.group(1)] = limpiar(m.group(2))
            continue
        if m := RE_G_POLITICA.match(linea):
            nombres_pol[m.group(1)] = limpiar(m.group(2))
            continue
        if linea.startswith("Concepto"):
            continue  # subtotal de concepto
        m = RE_G_PARTIDA.search(linea)
        importes = RE_IMPORTE.findall(linea)
        if not m or not importes:
            continue
        programa, concepto, subconcepto = m.groups()
        descripcion = limpiar(linea[: m.start()] + " " + linea[m.end():])
        partidas.append({
            "programa": programa,
            "economica": subconcepto,
            "capitulo": concepto[0],
            "descripcion": descripcion,
            "importe": euros(importes[0]),
        })

    por_cap: dict[str, float] = defaultdict(float)
    por_gp: dict[str, float] = defaultdict(float)
    for p in partidas:
        por_cap[p["capitulo"]] += p["importe"]
        por_gp[p["programa"]] += p["importe"]

    for cap, total in cap_pdf.items():
        if not cuadra(por_cap.get(cap, 0), total):
            avisos.append(f"Gastos cap. {cap}: partidas suman {por_cap.get(cap, 0):,.2f} € y el PDF dice {total:,.2f} €")
    for gp, total in gp_pdf.items():
        if not cuadra(por_gp.get(gp, 0), total):
            avisos.append(f"Gastos grupo {gp}: partidas suman {por_gp.get(gp, 0):,.2f} € y el PDF dice {total:,.2f} €")

    # Si hay totales impresos en el PDF, mandan ellos (son la fuente oficial).
    caps = cap_pdf or por_cap
    gps = gp_pdf or por_gp
    areas: dict[str, float] = defaultdict(float)
    for gp, v in gps.items():
        areas[gp[0]] += v

    return {
        "total": round(sum(caps.values()), 2),
        "capitulos": [{"codigo": c, "nombre": CAPITULOS_GASTOS.get(c, c), "importe": round(v, 2)} for c, v in sorted(caps.items())],
        "areas": [{"codigo": a, "nombre": AREAS.get(a, a), "importe": round(v, 2)} for a, v in sorted(areas.items())],
        "programas": [
            {"codigo": g, "nombre": nombres_gp.get(g) or nombres_pol.get(g[:2], g), "area": g[0], "importe": round(v, 2)}
            for g, v in sorted(gps.items(), key=lambda kv: -kv[1])
        ],
        "partidas": partidas,
        "avisos": avisos,
    }


# -------------------------------------------------------------- INGRESOS ----

# Filas de detalle: [cap] [art] concepto [subconcepto] descripción [importe]
RE_I_FILA = re.compile(rf"^(?:(\d) )?(?:(\d{{2}}) )?(\d{{3}})(?: (\d{{5}}))?\s+(.*)$")
RE_I_SUMAN = re.compile(r"Suman las Previsiones", re.I)


def parse_ingresos(lineas: list[str]) -> dict:
    conceptos: dict[str, dict] = {}
    subconceptos: dict[str, list] = defaultdict(list)
    avisos = []
    total_pdf = None

    for linea in lineas:
        linea = linea.strip()
        if RE_I_SUMAN.search(linea):
            valores = [euros(x) for x in RE_IMPORTE.findall(linea)]
            if valores:
                total_pdf = max(valores)  # la última página acumula el total
            continue
        m = RE_I_FILA.match(linea)
        if not m:
            continue
        _, _, concepto, sub, resto = m.groups()
        importes = RE_IMPORTE.findall(resto)
        fila = {
            "economica": sub or concepto,
            "capitulo": concepto[0],
            "descripcion": limpiar(resto),
            "importe": euros(importes[0]) if importes else None,
        }
        if sub:
            subconceptos[concepto].append(fila)
        else:
            conceptos[concepto] = fila

    # Hoja = subconceptos con importe si existen; si no, el concepto.
    partidas = []
    for c in sorted(set(conceptos) | set(subconceptos)):
        subs = [s for s in subconceptos.get(c, []) if s["importe"] is not None]
        if subs:
            partidas.extend(subs)
        elif c in conceptos and conceptos[c]["importe"] is not None:
            partidas.append(conceptos[c])

    por_cap: dict[str, float] = defaultdict(float)
    for p in partidas:
        por_cap[p["capitulo"]] += p["importe"]
    total = round(sum(por_cap.values()), 2)
    if total_pdf is not None and not cuadra(total, total_pdf):
        avisos.append(f"Ingresos: partidas suman {total:,.2f} € y el PDF dice {total_pdf:,.2f} €")

    return {
        "total": total,
        "total_pdf": total_pdf,
        "capitulos": [{"codigo": c, "nombre": CAPITULOS_INGRESOS.get(c, c), "importe": round(v, 2)} for c, v in sorted(por_cap.items())],
        "partidas": partidas,
        "avisos": avisos,
    }


# ------------------------------------------------------------------ main ----

def lineas_pdf(ruta: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(ruta) as pdf:
        return [l for page in pdf.pages for l in (page.extract_text() or "").splitlines()]


def main() -> int:
    salida = {"ejercicios": []}
    for carpeta in sorted((ROOT / "data" / "raw").glob("*")):
        anio = carpeta.name
        ej = {"anio": int(anio)}
        if (carpeta / "gastos.pdf").exists():
            ej["gastos"] = parse_gastos(lineas_pdf(carpeta / "gastos.pdf"))
        if (carpeta / "ingresos.pdf").exists():
            ej["ingresos"] = parse_ingresos(lineas_pdf(carpeta / "ingresos.pdf"))
        salida["ejercicios"].append(ej)
        for tipo in ("gastos", "ingresos"):
            if tipo in ej:
                d = ej[tipo]
                print(f"{anio} {tipo}: {len(d['partidas'])} partidas, total {d['total']:,.2f} €")
                for a in d["avisos"]:
                    print(f"  ⚠ {a}")

    destino = ROOT / "site" / "data"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "presupuestos.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if salida["ejercicios"] else 1


if __name__ == "__main__":
    sys.exit(main())
