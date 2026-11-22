"""Exploración: localiza el código JS que construye las URLs de descarga de CONPREL."""
import re
import requests
from urllib.parse import urljoin

BASE = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (presupuestos-venta-de-banos)"
r = s.get(BASE, timeout=60)
html = r.text

# Scripts en línea
for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I):
    body = m.group(1)
    if re.search(r"Descargar|Fichero|Access|ajax|location|window\.open|\.zip", body, re.I):
        print("===== INLINE SCRIPT\n", body[:6000])

# Scripts externos propios
for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', html, re.I):
    url = urljoin(r.url, src)
    if "hacienda" not in url:
        continue
    js = s.get(url, timeout=60).text
    for fn in re.finditer(r"function\s+(Descargar\w*|Seleccionar\w*)\s*\([^)]*\)\s*\{", js):
        start = fn.start()
        print(f"===== {url} :: {fn.group(1)}\n", js[start:start + 2500])
    for u in set(re.findall(r"['\"]([^'\"]*(?:Descarg|Fichero|\.zip|\.mdb)[^'\"]*)['\"]", js)):
        print("STR:", u)
