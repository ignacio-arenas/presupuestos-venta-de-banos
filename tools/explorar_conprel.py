"""Exploración: imprime la estructura de la web de CONPREL para localizar las descargas."""
import re
import requests
from urllib.parse import urljoin

BASE = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (presupuestos-venta-de-banos)"

def dump(url):
    r = s.get(url, timeout=60)
    print(f"\n===== {r.status_code} {r.url} ({len(r.text)} chars)")
    for m in re.finditer(r'<(a|form|iframe|input|select|option|button)\b[^>]*>', r.text, re.I):
        tag = m.group(0)
        if re.search(r'href|action|src|name|value|onclick', tag, re.I):
            print(tag[:300])
    for m in re.finditer(r'(?:url)\s*[:=]\s*["\']([^"\']+)', r.text, re.I):
        print("URL:", urljoin(r.url, m.group(1)))
    return r

r = dump(BASE)
links = set(urljoin(r.url, h) for h in re.findall(r'href=["\']([^"\'#]+)', r.text))
for l in sorted(links):
    if "CONPREL" in l and l != r.url and not l.endswith((".png", ".css", ".js", ".ico")):
        try:
            dump(l)
        except Exception as e:
            print("ERR", l, e)
