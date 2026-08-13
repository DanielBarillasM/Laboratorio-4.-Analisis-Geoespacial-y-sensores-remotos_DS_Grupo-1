# Laboratorio 4 — Análisis geoespacial y sensores remotos

Base reproducible para estudiar la presencia potencial de cianobacterias en los lagos de Atitlán y Amatitlán mediante Sentinel-2 L2A y Copernicus Data Space Ecosystem (CDSE).

## Estado del avance

- Las 22 fechas oficiales están registradas y validadas en `config/observaciones.csv`.
- Las dos cajas envolventes oficiales están en `config/areas_estudio.geojson` y los contornos provisionales de OpenStreetMap en `config/lake_boundaries_osm.geojson`.
- El flujo openEO genera NDVI, NDWI y el proxy CYA de Se2WaQ a 20 m.
- Se aplican máscaras SCL de calidad/nubes y una máscara de agua provisional `NDWI >= 0`.
- Los 22 GeoTIFF oficiales fueron descargados y auditados: 11 por lago.
- Hay pruebas automáticas para fechas, contornos y fórmulas.
- El notebook ejecutado, las tablas, las figuras y el informe PDF contienen resultados preliminares y no contienen credenciales.

> Los contornos de OpenStreetMap permiten una máscara reproducible, pero deben sustituirse por los GeoJSON oficiales mencionados en la guía cuando estén disponibles.

## Estructura

```text
config/       fechas y áreas de estudio
data/         rásteres y metadatos locales (ignorados por Git)
notebooks/    análisis narrativo en Jupyter
outputs/      figuras y tablas derivadas
reports/      informe reproducible con pdflatex
scripts/      descarga segura y generación del notebook
src/lab4/     funciones reutilizables
tests/        validación de fórmulas y configuración
```

## Preparación

Desde la raíz del repositorio:

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/fetch_lake_boundaries.py
python scripts/build_notebook.py
python scripts/analyze_downloads.py
```

## Descargar desde Copernicus

Primero puede validarse la gráfica sin autenticación ni consumo de procesamiento:

```powershell
python scripts/download_cdse.py --lake all
```

Prueba controlada de una fecha:

```powershell
python scripts/download_cdse.py --lake amatitlan --limit 1 --submit
```

Serie completa de ambos lagos:

```powershell
python scripts/download_cdse.py --lake all --submit
```

El programa muestra un código y una dirección oficial de CDSE para autorizar la sesión. No solicita, imprime ni guarda la contraseña. Los trabajos y GeoTIFF se almacenan bajo `data/`, una ruta excluida de Git.

## Productos

- **NDVI:** `(B08 - B04) / (B08 + B04)`.
- **NDWI:** `(B03 - B08) / (B03 + B08)`.
- **CYA:** `115530.31 * ((B03 * B04) / B02)^2.38`, después de convertir las bandas a reflectancia.

CYA es un proxy empírico de Se2WaQ expresado como estimación de `10^3 células/ml`. No es una medición de laboratorio ni un diagnóstico sanitario.

Fuentes metodológicas:

- [Documentación oficial de openEO en CDSE](https://documentation.dataspace.copernicus.eu/APIs/openEO/openEO.html)
- [Script Se2WaQ de Sentinel Hub](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/se2waq/)

## Informe

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/informe_avance.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/informe_avance.tex
```

El informe está escrito para lectores ambientales y separa claramente metodología, resultados pendientes y limitaciones.

## Resultados preliminares

El proxy CYA muestra señales altas y espacialmente extensas en Amatitlán durante abril de 2025 y marzo–junio de 2026. Atitlán presenta valores considerablemente menores y más localizados. Estas observaciones corresponden a un modelo empírico satelital y no constituyen confirmación biológica ni diagnóstico sanitario.

Los resúmenes comparativos limitan CYA al intervalo publicado de 0–100 porque reflectancias azules muy pequeñas pueden producir cocientes extremos. Los GeoTIFF crudos se conservan localmente para trazabilidad. El umbral exploratorio `CYA >= 40` debe validarse mediante sensibilidad y evidencia de campo antes de emplearse en conclusiones ambientales firmes.
