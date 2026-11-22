"""Descarga un PDF (p. ej. anexo de inversiones) y guarda su texto; si es escaneado, aplica OCR.
Uso: python tools/anexo_inversiones.py URL salida.txt   (OCR requiere tesseract-ocr-spa y poppler-utils)"""
import io, subprocess, sys, tempfile
from pathlib import Path
import pdfplumber, requests

r = requests.get(sys.argv[1], headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
r.raise_for_status()
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    paginas = [p.extract_text() or "" for p in pdf.pages]
if sum(len(p) for p in paginas) < 200 * len(paginas):  # casi sin texto: escaneado
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "doc.pdf").write_bytes(r.content)
        subprocess.run(["pdftoppm", "-r", "300", "-png", "doc.pdf", "p"], cwd=tmp, check=True)
        paginas = [subprocess.run(["tesseract", str(img), "-", "-l", "spa", "--psm", "6"], capture_output=True, text=True).stdout
                   for img in sorted(Path(tmp).glob("p-*.png"))]
txt = "\n\n".join(f"--- página {i + 1} ---\n{p}" for i, p in enumerate(paginas))
open(sys.argv[2], "w", encoding="utf-8").write(txt)
print(txt[:20000])
