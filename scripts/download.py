"""Descarga los PDFs de presupuestos listados en sources.json a data/raw/<año>/."""
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"User-Agent": "presupuestos-venta-de-banos (+https://github.com/ignacio-arenas/presupuestos-venta-de-banos)"}


def main() -> int:
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    errores = 0
    for anio, docs in sources["ejercicios"].items():
        destino = ROOT / "data" / "raw" / anio
        destino.mkdir(parents=True, exist_ok=True)
        for tipo, url in docs.items():
            fichero = destino / f"{tipo}.pdf"
            if fichero.exists():
                print(f"[=] {fichero.relative_to(ROOT)} ya existe")
                continue
            try:
                r = requests.get(url, headers=HEADERS, timeout=60)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    raise ValueError("la respuesta no es un PDF")
                fichero.write_bytes(r.content)
                print(f"[+] {fichero.relative_to(ROOT)} ({len(r.content) // 1024} KB)")
            except Exception as e:  # noqa: BLE001
                errores += 1
                print(f"[!] {anio}/{tipo}: {e}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
