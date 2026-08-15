# Datos locales del laboratorio

Los GeoTIFF generados por Copernicus Data Space Ecosystem no se distribuyen en
el repositorio ni en el ZIP porque son productos derivados reproducibles y
aumentarían innecesariamente el tamaño de la entrega. Las tablas, figuras,
mapas, notebook ejecutado e informe final sí están versionados.

## Estructura esperada

Después de la descarga deben existir exactamente 22 GeoTIFF, 11 por lago:

```text
data/raw/cdse/
├── amatitlan/
│   └── openEO_YYYY-MM-DDZ.tif
└── atitlan/
    └── openEO_YYYY-MM-DDZ.tif
```

Cada archivo contiene tres bandas derivadas en este orden: `NDVI`, `NDWI` y
`CYA`. Las fechas esperadas están definidas en `config/observaciones.csv`.

## Reconstrucción desde CDSE

Desde la raíz del proyecto:

```powershell
python -m pip install -r requirements.txt
python scripts/download_cdse.py --lake all
python scripts/download_cdse.py --lake all --submit
python scripts/analyze_full.py
```

El primer comando de descarga valida la gráfica de procesamiento sin crear
trabajos. El segundo solicita autenticación oficial mediante código de
dispositivo, procesa las 22 fechas y guarda los resultados bajo
`data/raw/cdse/`. Ninguna contraseña se solicita o almacena en el repositorio.

`analyze_full.py` verifica el número de archivos y las fechas antes de regenerar
los productos de `outputs/tables/` y `outputs/figures/`.
