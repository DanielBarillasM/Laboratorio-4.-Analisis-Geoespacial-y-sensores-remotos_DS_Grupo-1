# `data/` — rásteres y metadatos locales (no versionados)

Esta carpeta está excluida de Git (`.gitignore`) porque los 22 GeoTIFF oficiales
(11 por lago) pesan varios GB en conjunto y no son un entregable solicitado por
el PDF del laboratorio. Lo que **sí** está versionado en el repositorio son los
productos derivados: tablas (`outputs/tables/`), figuras (`outputs/figures/`),
el notebook ejecutado (`notebooks/02_laboratorio_completo.ipynb`) y el informe
final (`reports/informe_final.pdf`).

## Estructura esperada

```text
data/
├── jobs/        # metadatos de los trabajos openEO enviados a CDSE (JSON)
├── processed/   # NDVI, NDWI y CYA recortados y enmascarados por fecha/lago
└── raw/         # GeoTIFF originales descargados de Sentinel-2 L2A (CDSE)
```

Cada subcarpeta contiene únicamente un `.gitkeep` en este repositorio; se llena
al ejecutar los comandos de descarga.

## Cómo reconstruir `data/raw/`

1. Instalar el proyecto y correr las pruebas (no requieren datos descargados):

   ```powershell
   python -m pip install -e ".[test]"
   python -m pytest -q
   ```

2. Descargar los contornos finos de OpenStreetMap usados para el recorte:

   ```powershell
   python scripts/fetch_lake_boundaries.py
   ```

3. Autenticarse en Copernicus Data Space Ecosystem (CDSE) mediante código de
   dispositivo — el programa **no** solicita ni guarda contraseñas:

   ```powershell
   python scripts/authenticate_cdse.py
   ```

4. Validar la gráfica de procesamiento openEO sin consumir cuota (dry run):

   ```powershell
   python scripts/download_cdse.py --lake all
   ```

5. Prueba controlada de una sola fecha, antes de lanzar todo:

   ```powershell
   python scripts/download_cdse.py --lake amatitlan --limit 1 --submit
   ```

6. Descarga completa de las 22 fechas oficiales (ambos lagos):

   ```powershell
   python scripts/download_cdse.py --lake all --submit
   ```

   Los GeoTIFF quedan en `data/raw/`, y los metadatos de cada trabajo en
   `data/jobs/`. Si una sesión se interrumpe, `scripts/recover_cdse_jobs.py`
   recupera los trabajos ya enviados sin volver a consumir procesamiento.

## Cómo reconstruir tablas y figuras

Con `data/raw/` ya poblado:

```powershell
python scripts/analyze_full.py
```

Esto regenera todo lo que hay en `outputs/tables/` y `outputs/figures/`
(ejercicios 4 a 8). Las cifras resultantes deben coincidir con las que ya están
versionadas en el repositorio y con las citadas en `reports/informe_final.pdf`.

## Nota sobre reproducibilidad

Sin `data/raw/`, el notebook y `analyze_full.py` no pueden ejecutarse de punta
a punta porque dependen de los GeoTIFF descargados. Sin embargo, todos los
resultados derivados (tablas, figuras, notebook ejecutado e informe) sí están
versionados, por lo que la evaluación y lectura del laboratorio no requieren
volver a descargar nada — solo es necesario si se desea reproducir el cómputo
desde cero.
