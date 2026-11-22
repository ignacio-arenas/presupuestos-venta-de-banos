"""Exploración puntual de webs que el entorno de desarrollo no alcanza. Uso: python tools/explorar.py URL [patrón]"""
import re, sys
from urllib.parse import urljoin
import requests

url = sys.argv[1]
patron = sys.argv[2] if len(sys.argv) > 2 else r"\.(xlsx?|zip|csv|pdf)\b"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
print(r.status_code, r.url, len(r.text))
for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r.text, re.I | re.S):
    href, txt = m.group(1), re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
    if re.search(patron, href + " " + txt, re.I):
        print(f"{txt[:90]!r} -> {urljoin(r.url, href)}")
