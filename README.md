# Presupuestos de Venta de Baños

Convierte los PDFs de presupuestos que publica el [Ayuntamiento de Venta de Baños](https://ventadebanos.es/ayuntamiento/presupuestos-generales/) en una web con gráficos y un buscador de partidas.

## Cómo funciona

**Fuente principal: [CONPREL](https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL) (Ministerio de Hacienda)**, con presupuestos y liquidaciones de todos los municipios desde 2002.

1. **`scripts/conprel.py`** descarga la base de datos Access nacional de cada año y guarda solo las filas de Venta de Baños en `data/conprel/` (workflow *Datos de Hacienda*, el día 2 de cada mes).
2. **`scripts/hacienda.py`** lo resume en `site/data/hacienda.json`: presupuesto inicial, definitivo y gasto real por capítulo, área, programa y partida.
3. **`site/index.html`** es la web estática (Chart.js).

**Control de calidad:** `scripts/download.py` + `scripts/parse.py` leen los PDFs del Ayuntamiento y `hacienda.py` compara sus totales con los de Hacienda (ver el log de *Descargar, procesar y publicar*).

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

- [x] Presupuestos 2015–2026 y liquidaciones 2015–2025 (Hacienda)
- [x] Presupuestado vs. gastado por capítulo, área, programa y partida
- [x] Control cruzado con el PDF de 2025 (cuadra al céntimo)
- [x] Remanente de tesorería 2015–2025
- [ ] Deuda viva
- [ ] Comparación con municipios similares
