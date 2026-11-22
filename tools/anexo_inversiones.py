"""Descarga un anexo de inversiones (PDF) y guarda su texto para revisarlo. Uso: python tools/anexo_inversiones.py URL salida.txt"""
import io, sys
import pdfplumber, requests
r = requests.get(sys.argv[1], headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
r.raise_for_status()
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    txt = "\n\n".join(f"--- página {i + 1} ---\n" + (p.extract_text() or "") for i, p in enumerate(pdf.pages))
open(sys.argv[2], "w", encoding="utf-8").write(txt)
print(txt[:20000])
