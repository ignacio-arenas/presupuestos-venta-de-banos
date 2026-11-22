"""Extrae de CONPREL (Ministerio de Hacienda) los datos de un municipio.

Uso: python scripts/conprel.py <Presupuestos|Liquidaciones> <año> [codbdgel]

Descarga la base de datos Access nacional del año, localiza el municipio en
tb_inventario y guarda en data/conprel/<tipo>_<año>.json todas las filas de
cualquier tabla que le pertenezcan, más las tablas de códigos (nombres de
cuentas económicas y de programas). Requiere mdbtools (mdb-tables, mdb-export).
"""
import csv
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

import requests

BASE = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL/Consulta"
ROOT = Path(__file__).resolve().parent.parent
CODBDGEL = "34023AA000"  # Venta de Baños (INE 34023)


def tabla(mdb: Path, nombre: str) -> list[dict]:
    out = subprocess.run(["mdb-export", str(mdb), nombre], capture_output=True, text=True, check=True).stdout
    return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in csv.DictReader(io.StringIO(out))]

CYL = {"05", "09", "24", "34", "37", "40", "42", "47", "49"}  # provincias de Castilla y León
RANGO = (5000, 10000)            # municipios "parecidos" por población
RANGO_PROVINCIA = (2000, 20000)  # municipios de la provincia que se listan uno a uno


def indicadores(datos: dict, tipo: str) -> dict[str, dict]:
    """Indicadores por ayuntamiento (importes absolutos) a partir de las tablas nacionales."""
    campo = "importe" if tipo == "Presupuestos" else "importer"
    ind: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in datos.get("tb_economica", []):
        c = r["cdcta"]
        if len(c) == 1:
            pre = "g" if r["tipreig"] == "G" else "i"
            ind[r["id"]][f"{pre}{c}"] += float(r[campo] or 0)
            ind[r["id"]][f"{pre}_total"] += float(r[campo] or 0)
    for r in datos.get("tb_funcional", []):
        if len(r["cdfgr"]) == 1:
            ind[r["id"]][f"a{r['cdfgr']}"] += float(r["importe"] or 0)
    rem = defaultdict(dict)
    for r in datos.get("tb_remanente", []):
        rem[r["id"]][r["cdrmte"]] = float(r["importe"] or 0)
    for i, v in rem.items():
        ind[i]["remanente"] = v.get("1", v.get("0", 0.0))
    return ind


def mediana(xs: list[float]) -> float | None:
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def comparativa(datos: dict, tipo: str, codbdgel: str) -> dict:
    ind = indicadores(datos, tipo)
    aytos = [e for e in datos["tb_inventario"]
             if e.get("codbdgel", "")[5:7] == "AA" and int(e.get("poblacion") or 0) > 0 and ind.get(e["id"], {}).get("g_total")]
    per = lambda e: {k: round(v / int(e["poblacion"]), 2) for k, v in ind[e["id"]].items()}  # noqa: E731
    prov = codbdgel[:2]

    def grupo(filtro):
        sel = [per(e) for e in aytos if RANGO[0] <= int(e["poblacion"]) <= RANGO[1] and filtro(e)]
        claves = {k for x in sel for k in x}
        return {"n": len(sel), "mediana": {k: round(mediana([x[k] for x in sel if k in x]), 2) for k in sorted(claves)}}

    return {
        "unidad": "euros por habitante",
        "rango": RANGO,
        "grupos": {
            "espana": grupo(lambda e: True),
            "cyl": grupo(lambda e: e["codbdgel"][:2] in CYL),
        },
        "provincia": sorted(
            ({"codigo": e["codbdgel"], "nombre": e["nombreente"].strip(), "poblacion": int(e["poblacion"]), **per(e)}
             for e in aytos if e["codbdgel"][:2] == prov and (RANGO_PROVINCIA[0] <= int(e["poblacion"]) <= RANGO_PROVINCIA[1] or e["codbdgel"] == codbdgel)),
            key=lambda x: -x["poblacion"]),
    }


def main(tipo: str, anio: str, codbdgel: str = CODBDGEL) -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (presupuestos-venta-de-banos)"
    params = {"CCAA": "", "TipoDato": tipo, "Ejercicio": anio, "TipoPublicacion": "Access"}
    existe = s.post(f"{BASE}/ExisteFichero", data=params, timeout=60).json()
    if not existe.get("success"):
        print(f"[=] {tipo} {anio}: no publicado")
        return 0
    r = s.get(f"{BASE}/DescargaFichero", params=params, timeout=1200)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    nombre = next(n for n in z.namelist() if n.lower().endswith((".mdb", ".accdb")))

    with tempfile.TemporaryDirectory() as tmp:
        mdb = Path(tmp) / Path(nombre).name
        mdb.write_bytes(z.read(nombre))
        tablas = subprocess.run(["mdb-tables", "-1", str(mdb)], capture_output=True, text=True, check=True).stdout.split()

        inv_tabla = next(t for t in tablas if t.lower() == "tb_inventario")
        ente = next((f for f in tabla(mdb, inv_tabla) if f.get("codbdgel", "").startswith(codbdgel[:5]) and f.get("codbdgel") == codbdgel), None)
        if not ente:
            print(f"[!] {tipo} {anio}: {codbdgel} no encontrado", file=sys.stderr)
            return 1
        ident = ente["id"]

        salida = {"fuente": f"CONPREL {tipo} {anio}", "fichero": nombre, "ente": ente, "tablas": {}, "codigos": {}}
        datos = {t.lower(): tabla(mdb, t) for t in tablas}
        salida["comparativa"] = comparativa(datos, tipo, codbdgel)
        for t in tablas:
            filas = datos[t.lower()]
            if not filas:
                continue
            if "id" in filas[0]:
                if t == inv_tabla:
                    continue
                propias = [f for f in filas if f["id"] == ident]
                if propias:
                    salida["tablas"][t] = propias
            elif len(filas) < 5000:  # tablas de códigos y nombres
                salida["codigos"][t] = filas
        n = {t: len(v) for t, v in salida["tablas"].items()}
        c = salida["comparativa"]
        print(f"[+] {tipo} {anio}: id {ident}, {n}; comparativa: {len(c['provincia'])} municipios de la provincia, "
              f"{c['grupos']['espana']['n']} en España y {c['grupos']['cyl']['n']} en CyL de {c['rango'][0]}-{c['rango'][1]} hab.")

    destino = ROOT / "data" / "conprel"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{tipo.lower()}_{anio}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
