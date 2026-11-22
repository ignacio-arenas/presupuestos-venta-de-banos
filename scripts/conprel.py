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
from pathlib import Path

import requests

BASE = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL/Consulta"
ROOT = Path(__file__).resolve().parent.parent
CODBDGEL = "34023AA000"  # Venta de Baños (INE 34023)


def tabla(mdb: Path, nombre: str) -> list[dict]:
    out = subprocess.run(["mdb-export", str(mdb), nombre], capture_output=True, text=True, check=True).stdout
    return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in csv.DictReader(io.StringIO(out))]


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
        for t in tablas:
            filas = tabla(mdb, t)
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
        print(f"[+] {tipo} {anio}: id {ident}, {n}")

    destino = ROOT / "data" / "conprel"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{tipo.lower()}_{anio}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
