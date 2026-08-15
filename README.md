# Laboratorio 4 — Análisis geoespacial y sensores remotos

Base reproducible para estudiar la presencia potencial de cianobacterias en los lagos de Atitlán y Amatitlán mediante Sentinel-2 L2A y Copernicus Data Space Ecosystem (CDSE).

## Estado

- Las 22 fechas oficiales están registradas y validadas en `config/observaciones.csv`.
- Los GeoJSON entregados por el curso están en `config/Lago_Atitlan.geojson` y `config/Lago_Amatitlan.geojson`; contienen las mismas cajas envolventes publicadas como coordenadas en la guía.
- Los contornos finos del espejo de agua, tomados de OpenStreetMap, están en `config/lake_boundaries_osm.geojson` y se usan únicamente para el recorte y el cálculo de área.
- El flujo openEO genera NDVI, NDWI y el proxy CYA de Se2WaQ a 20 m.
- Se aplican máscaras SCL de calidad/nubes y la separación agua-fondo `NDWI >= 0` del script Se2WaQ.
- Los 22 GeoTIFF oficiales fueron descargados y auditados: 11 por lago.
- Hay pruebas automáticas para fechas, contornos, fórmulas, estadísticos robustos, porcentajes de área, persistencia, correlaciones y manejo de NoData.
- Ningún archivo del repositorio contiene credenciales; la autenticación es por código de dispositivo.

> **Delimitación de los lagos.** El ejercicio 2 permite usar las coordenadas o el GeoJSON provisto. Los archivos entregados por el curso reproducen exactamente las cajas rectangulares de esas coordenadas: se usan como extensión oficial de consulta. Como no delinean la orilla, los contornos de OpenStreetMap (relaciones [5781818](https://www.openstreetmap.org/relation/5781818) y [11018382](https://www.openstreetmap.org/relation/11018382), licencia ODbL 1.0) realizan el recorte fino del espejo de agua y el cálculo de superficies.

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
python -m pip install -r requirements.txt
python -m pytest -q
python scripts/fetch_lake_boundaries.py
```

La instalación anterior es compatible con `pip`; las dependencias canónicas
están declaradas en `pyproject.toml` y bloqueadas en `uv.lock`. Quien utilice
`uv` puede ejecutar `uv sync --extra test`.

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

### Disponibilidad de los datos ráster

Los 22 GeoTIFF no se incluyen en GitHub ni en el ZIP porque son productos
derivados reproducibles y aumentarían innecesariamente el tamaño de la entrega.
Las fechas, geometrías, scripts, tablas, figuras y resultados finales sí están
versionados. [`data/README.md`](data/README.md) documenta la estructura esperada
y los comandos exactos para volver a descargar y reconstruir el análisis.

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
| `revision_visual_rasters.csv` | Auditoría visual, cobertura y advertencias por escena |
| `estadisticas_indices.csv` | Media, mediana y percentiles de NDVI, NDWI y CYA |
| `serie_temporal_cya.csv` | Solo CYA: base del análisis temporal |
| `sensibilidad_umbral_cya.csv` | Extensión de la floración con umbrales 20, 40 y 60 |
| `correlaciones_indices.csv` | Pearson y Spearman de CYA con NDVI y NDWI, por fecha |
| `correlaciones_resumen.csv` | Resumen por lago de esas correlaciones |
| `comparacion_lagos.csv` | Comparación del ejercicio 7, incluidas las fechas críticas |
| `distribucion_estacional.csv` | Reparto entre época seca y lluviosa |
| `persistencia_resumen.csv` | Superficie que supera el umbral en 25 %, 50 % y 75 % de las fechas |
| `zonas_espaciales_fecha.csv` | Intensidad de CYA por cuadrante, lago y fecha |
| `zonas_espaciales_resumen.csv` | Síntesis de zonas recurrentes por lago |

### Figuras

`serie_temporal_cya`, `mapas_cya_seleccion`, `mapas_cya_logaritmico`,
`mapas_diferencia_cya`, `persistencia_cya`, `distribuciones_cya`,
`dispersion_correlaciones` y `comparacion_lagos`, cada una en PNG y PDF, más los
atlas de las 11 fechas de cada lago (`atlas_cya_*`) y los mapas interactivos
`mapa_interactivo_atitlan.html` y `mapa_interactivo_amatitlan.html`.

## Decisiones y limitaciones

Conviene leerlas antes de citar cualquier cifra.

- **La media truncada no resume la intensidad.** La rampa publicada de Se2WaQ
  termina en 100, pero en varias fechas de Amatitlán más de la mitad del espejo de
  agua la supera. Truncar convierte la media en un contador de saturación. Por eso
  la serie temporal muestra la media aritmética exigida por la guía junto con la
  mediana y percentiles sobre el valor crudo; la media truncada se conserva como
  lectura complementaria junto a `porcentaje_saturado_100`.
- **El umbral de CYA alta es 40** porque es uno de los cortes de la rampa
  publicada, `scaleCya = [0, 10, 20, 40, 50, 100]`, no un límite sanitario. Todo se
  acompaña de sensibilidad con 20, 40 y 60.
- **La extensión se mide sobre el área del lago**, no sobre los píxeles válidos:
  la cobertura varía entre fechas y referirse solo a lo observado sobreestima la
  floración en las imágenes nubladas.
- **La máscara de agua `NDWI >= 0` reproduce el criterio del script Se2WaQ.**
  Puede excluir superficies ópticamente semejantes a vegetación, incluidas natas
  muy densas; por ello las correlaciones y extensiones se interpretan como las
  observadas bajo el criterio del modelo, no como cobertura biológica absoluta.
- **La persistencia exige al menos seis fechas válidas por píxel.** Esto evita
  llamar persistente a una zona observada solamente una o dos veces.
- **Los píxeles vecinos no son independientes.** Las correlaciones se reportan
  también sobre una submuestra espacial, y los valores de p deben leerse con
  cautela porque el tamaño de muestra es enorme por construcción.
- **CYA es un proxy empírico calibrado en otro embalse.** No confirma presencia de
  cianobacterias ni sustituye un muestreo de laboratorio.

## Informe

```powershell
python scripts/build_final_notebook.py
jupyter nbconvert --to notebook --execute --inplace notebooks/02_laboratorio_completo.ipynb
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/informe_final.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/informe_final.tex
```

El notebook ejecutado reúne los ejercicios 1 a 8 y el informe final está escrito
para lectores ambientales. Ambos separan resultados, interpretación y
limitaciones del proxy satelital.

## Resultados

El proxy CYA muestra señales altas y espacialmente extensas en Amatitlán durante abril de 2025 y marzo–junio de 2026. Atitlán presenta valores considerablemente menores y más localizados. Estas observaciones corresponden a un modelo empírico satelital y no constituyen confirmación biológica ni diagnóstico sanitario.

Las cifras definitivas de cada ejercicio están en `outputs/tables/`, se regeneran con `python scripts/analyze_full.py` y deben coincidir con las del notebook final y las del informe.
