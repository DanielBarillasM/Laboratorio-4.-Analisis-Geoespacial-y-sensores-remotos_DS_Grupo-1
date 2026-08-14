# Laboratorio 4 — Análisis geoespacial y sensores remotos

Base reproducible para estudiar la presencia potencial de cianobacterias en los lagos de Atitlán y Amatitlán mediante Sentinel-2 L2A y Copernicus Data Space Ecosystem (CDSE).

## Estado

- Las 22 fechas oficiales están registradas y validadas en `config/observaciones.csv`.
- Las dos cajas envolventes publicadas en la guía están en `config/areas_estudio.geojson` y los contornos del espejo de agua, tomados de OpenStreetMap, en `config/lake_boundaries_osm.geojson`.
- El flujo openEO genera NDVI, NDWI y el proxy CYA de Se2WaQ a 20 m.
- Se aplican máscaras SCL de calidad/nubes y una máscara de agua provisional `NDWI >= 0`.
- Los 22 GeoTIFF oficiales fueron descargados y auditados: 11 por lago.
- Hay pruebas automáticas para fechas, contornos, fórmulas, estadísticos robustos, porcentajes de área, persistencia, correlaciones y manejo de NoData.
- Ningún archivo del repositorio contiene credenciales; la autenticación es por código de dispositivo.

> **Delimitación de los lagos.** El ejercicio 2 de la guía permite trabajar «usando las coordenadas o el geojson provisto». Aquí se usan ambas cosas de forma complementaria: las cajas envolventes de la guía acotan la consulta a Copernicus y los contornos de OpenStreetMap (relaciones [5781818](https://www.openstreetmap.org/relation/5781818) y [11018382](https://www.openstreetmap.org/relation/11018382), licencia ODbL 1.0) recortan el espejo de agua y sirven para calcular áreas. Se eligió OpenStreetMap por ser una fuente pública, citable y reproducible con `scripts/fetch_lake_boundaries.py`.

## Estructura

```text
config/       fechas y áreas de estudio
data/         rásteres y metadatos locales (ignorados por Git)
notebooks/    análisis narrativo en Jupyter
outputs/      figuras y tablas derivadas
reports/      informes reproducibles con pdflatex
scripts/      descarga segura, análisis y generación del notebook
src/lab4/     funciones reutilizables
tests/        validación de fórmulas, estadísticos y configuración
```

## Preparación

Desde la raíz del repositorio:

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/fetch_lake_boundaries.py
```

Con los GeoTIFF ya descargados, un solo comando reconstruye todas las tablas y
figuras de los ejercicios 4 a 8:

```powershell
python scripts/analyze_full.py
```

`scripts/analyze_downloads.py` se conserva únicamente para reproducir el informe
de avance. Escribe sobre los mismos archivos, así que exige `--force`.

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

### Índices

- **NDVI:** `(B08 - B04) / (B08 + B04)`.
- **NDWI:** `(B03 - B08) / (B03 + B08)`.
- **CYA:** `115530.31 * ((B03 * B04) / B02)^2.38`, después de convertir las bandas a reflectancia.

CYA es un proxy empírico de Se2WaQ expresado como estimación de `10^3 células/ml`. No es una medición de laboratorio ni un diagnóstico sanitario.

Fuentes metodológicas:

- [Documentación oficial de openEO en CDSE](https://documentation.dataspace.copernicus.eu/APIs/openEO/openEO.html)
- [Script Se2WaQ de Sentinel Hub](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/se2waq/)

### Tablas que genera `analyze_full.py`

| Archivo en `outputs/tables/` | Contenido |
| --- | --- |
| `control_calidad_rasters.csv` | Rejilla, cobertura válida y rango de cada índice por fecha |
| `estadisticas_indices.csv` | Media, mediana y percentiles de NDVI, NDWI y CYA |
| `serie_temporal_cya.csv` | Solo CYA: base del análisis temporal |
| `sensibilidad_umbral_cya.csv` | Extensión de la floración con umbrales 20, 40 y 60 |
| `correlaciones_indices.csv` | Pearson y Spearman de CYA con NDVI y NDWI, por fecha |
| `correlaciones_resumen.csv` | Resumen por lago de esas correlaciones |
| `comparacion_lagos.csv` | Comparación del ejercicio 7, incluidas las fechas críticas |
| `distribucion_estacional.csv` | Reparto entre época seca y lluviosa |
| `persistencia_resumen.csv` | Superficie que supera el umbral en 25 %, 50 % y 75 % de las fechas |

### Figuras

`serie_temporal_cya`, `mapas_cya_seleccion`, `mapas_cya_logaritmico`,
`mapas_diferencia_cya`, `persistencia_cya`, `distribuciones_cya`,
`dispersion_correlaciones` y `comparacion_lagos`, cada una en PNG y PDF, más los
mapas interactivos `mapa_interactivo_atitlan.html` y `mapa_interactivo_amatitlan.html`.

## Decisiones y limitaciones

Conviene leerlas antes de citar cualquier cifra.

- **La media truncada no resume la intensidad.** La rampa publicada de Se2WaQ
  termina en 100, pero en varias fechas de Amatitlán más de la mitad del espejo de
  agua la supera. Truncar convierte la media en un contador de saturación. Por eso
  la serie temporal usa mediana y percentiles sobre el valor crudo, y la media
  truncada se conserva como lectura complementaria junto a
  `porcentaje_saturado_100`.
- **El umbral de CYA alta es 40** porque es uno de los cortes de la rampa
  publicada, `scaleCya = [0, 10, 20, 40, 50, 100]`, no un límite sanitario. Todo se
  acompaña de sensibilidad con 20, 40 y 60.
- **La extensión se mide sobre el área del lago**, no sobre los píxeles válidos:
  la cobertura varía entre fechas y referirse solo a lo observado sobreestima la
  floración en las imágenes nubladas.
- **La máscara de agua `NDWI >= 0` elimina la nata superficial más densa**, que
  ópticamente se comporta como vegetación. Esto subestima la extensión e induce
  parte de la correlación negativa entre CYA y NDWI, lo que debe declararse al
  interpretar el ejercicio 6.
- **Los píxeles vecinos no son independientes.** Las correlaciones se reportan
  también sobre una submuestra espacial, y los valores de p deben leerse con
  cautela porque el tamaño de muestra es enorme por construcción.
- **CYA es un proxy empírico calibrado en otro embalse.** No confirma presencia de
  cianobacterias ni sustituye un muestreo de laboratorio.

## Informe

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/informe_avance.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/informe_avance.tex
```

El informe está escrito para lectores ambientales y separa claramente metodología, resultados pendientes y limitaciones.

## Resultados

El proxy CYA muestra señales altas y espacialmente extensas en Amatitlán durante abril de 2025 y marzo–junio de 2026. Atitlán presenta valores considerablemente menores y más localizados. Estas observaciones corresponden a un modelo empírico satelital y no constituyen confirmación biológica ni diagnóstico sanitario.

Las cifras definitivas de cada ejercicio están en `outputs/tables/`, se regeneran con `python scripts/analyze_full.py` y deben coincidir con las del notebook final y las del informe.
