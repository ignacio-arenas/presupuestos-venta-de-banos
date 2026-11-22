# Presupuestos de Venta de Baños

Convierte los PDFs de presupuestos que publica el [Ayuntamiento de Venta de Baños](https://ventadebanos.es/ayuntamiento/presupuestos-generales/) en una web con gráficos y un buscador de partidas.

## Cómo funciona

1. **`scripts/download.py`** descarga los PDFs listados en `sources.json` a `data/raw/<año>/`.
2. **`scripts/parse.py`** extrae las partidas con `pdfplumber` y comprueba que cuadran con los totales que imprime el propio PDF (por capítulo y por grupo de programa). Si algo no cuadra, lo anota en `avisos` y la web lo enseña.
3. **`site/index.html`** es una página estática (Chart.js) que lee `site/data/presupuestos.json`.
4. **GitHub Actions** (`.github/workflows/publicar.yml`) hace todo lo anterior en cada push, el día 1 de cada mes y a mano, y lo publica en GitHub Pages.

## Puesta en marcha

En GitHub: **Settings → Pages → Source: GitHub Actions**. Después, en la pestaña Actions, lanza "Descargar, procesar y publicar".

En local:

```bash
pip install -r requirements.txt
python scripts/download.py && python scripts/parse.py
python -m http.server -d site
```

## Añadir un año

Añade sus URLs en `sources.json`. Ojo: el formato de los PDFs de 2022 (BOP) es distinto al de 2025 y necesitará su propio parser.

## Estado

- [x] 2025: gastos (clasificación por programas y económica) e ingresos
- [ ] Validar el parser contra los PDFs reales (revisar los avisos en el log de Actions)
- [ ] 2022 y años anteriores
- [ ] Comparativa entre años
