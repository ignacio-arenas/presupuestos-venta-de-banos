"""Exploración: descarga el Access de CONPREL y muestra su estructura y las filas de Venta de Baños."""
import io, re, subprocess, sys, zipfile
import requests

BASE = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (presupuestos-venta-de-banos)"
html = s.get(BASE, timeout=60).text
i = html.find("function DescargarFicheroAccess(")
print("===== FUNCION\n", html[i:i + 1500])
m = re.search(r"urlpagina\s*\+\s*'([^']+)'", html[i:i + 1500])
ruta = m.group(1) if m else "/Consulta/DescargaFichero?CCAA=&TipoDato="
print("RUTA:", ruta)

body = html[i:i + 1500]
expr = re.search(r"href\s*=\s*(.+?);", body, re.S).group(1)
print("EXPR:", expr)
# Construimos la URL sustituyendo variables en la expresión JS
partes = re.findall(r"'([^']*)'|(\w+)", expr)
url = ""
vals = {"urlpagina": BASE, "ejercicio": "2025", "tipoDato": "Presupuestos"}
for lit, var in partes:
    url += lit if lit or not var else vals.get(var, "")
print("URL:", url)
r = s.get(url, timeout=600)
print("STATUS", r.status_code, r.headers.get("content-type"), r.headers.get("content-disposition"), len(r.content))
z = zipfile.ZipFile(io.BytesIO(r.content))
for n in z.namelist():
    print("ZIP:", n, z.getinfo(n).file_size)
mdb = next(n for n in z.namelist() if n.lower().endswith((".mdb", ".accdb")))
open("/tmp/c.mdb", "wb").write(z.read(mdb))
subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "mdbtools"], check=True, stdout=subprocess.DEVNULL)
tablas = subprocess.run(["mdb-tables", "-1", "/tmp/c.mdb"], capture_output=True, text=True).stdout.split()
for t in tablas:
    csv = subprocess.run(["mdb-export", "/tmp/c.mdb", t], capture_output=True, text=True).stdout.splitlines()
    print(f"\n===== TABLA {t}: {len(csv)} filas\n" + "\n".join(csv[:3]))
    vb = [l for l in csv if re.search(r"34023|VENTA DE BA", l, re.I)]
    print(f"-- filas Venta de Baños: {len(vb)}")
    print("\n".join(vb[:8]))
