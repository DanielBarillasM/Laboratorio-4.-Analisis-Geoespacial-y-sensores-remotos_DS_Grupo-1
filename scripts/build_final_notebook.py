"""Construye el notebook final narrativo a partir de resultados reproducibles."""

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks" / "02_laboratorio_completo.ipynb"
nb = nbf.v4.new_notebook()
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.13"},
}


def md(source: str):
    return nbf.v4.new_markdown_cell(source.strip())


def code(source: str):
    return nbf.v4.new_code_cell(source.strip())


nb["cells"] = [
    code(r'''
from pathlib import Path
import pandas as pd
import geopandas as gpd
from IPython.display import HTML, display

ROOT = Path.cwd()
if not (ROOT / "outputs").exists():
    ROOT = ROOT.parent
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"

display(HTML("""
<style>
:root{--navy:#123047;--lake:#167d9a;--aqua:#47b8a6;--sand:#f4ead5;--ink:#304a55;--orange:#d5793d}
.jp-Notebook{background:#f7fafb}.jp-Cell{max-width:1180px;margin:auto}
.hero{background:linear-gradient(125deg,#0c2a3c,#167d9a 62%,#47b8a6);color:white;padding:34px 38px;border-radius:20px;box-shadow:0 14px 35px #1230472b;margin:12px 0 24px}
.hero h1{font-size:2.35rem;margin:0 0 8px}.hero p{font-size:1.08rem;margin:4px 0;opacity:.94}
.section{background:white;border-left:7px solid var(--lake);padding:18px 24px;border-radius:14px;margin:26px 0 12px;box-shadow:0 6px 20px #12304712}
.section h2{color:var(--navy);margin:0 0 4px}.callout{padding:15px 18px;border-radius:12px;background:#eaf7f6;border:1px solid #9edbd2;color:var(--ink);margin:14px 0}
.warning{background:#fff5e7;border-color:#efbd79}.finding{background:#eef4fb;border-color:#9dbed4}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px;margin:14px 0}.metric{background:white;border-radius:12px;padding:15px;border-top:4px solid var(--aqua);box-shadow:0 5px 16px #12304712}.metric b{display:block;font-size:1.45rem;color:var(--navy)}
.exercise{display:inline-block;padding:5px 10px;margin:3px;border-radius:999px;background:#dff4f1;color:#123047;font-weight:650}.caption{color:#56717d;font-size:.92rem;margin-top:5px}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.two img,.full-img{width:100%;border-radius:14px;border:1px solid #d6e2e7;background:white}.footer{padding:20px;border-radius:14px;background:#123047;color:white;margin-top:28px}@media(max-width:800px){.two{grid-template-columns:1fr}}
</style>
"""))
'''),
    md(r'''
<div class="hero">
  <h1>Los lagos vistos desde Sentinel‑2</h1>
  <p><strong>Laboratorio 4 · Análisis geoespacial y sensores remotos</strong></p>
  <p>Proxy de cianobacterias, NDVI y NDWI en Atitlán y Amatitlán · Grupo 1</p>
</div>

<span class="exercise">E1 · API</span><span class="exercise">E2 · rásteres mínimos</span>
<span class="exercise">E3 · índices</span><span class="exercise">E4 · tiempo</span>
<span class="exercise">E5 · espacio</span><span class="exercise">E6 · correlación</span>
<span class="exercise">E7 · comparación</span><span class="exercise">E8 · exploración</span>

Este notebook comunica resultados para una audiencia ambiental. El proxy **CYA no sustituye un muestreo de campo ni confirma toxicidad**; describe la respuesta del modelo empírico Se2WaQ sobre imágenes Sentinel‑2 L2A.
'''),
    code(r'''
names = [
    "control_calidad_rasters", "revision_visual_rasters", "estadisticas_indices",
    "serie_temporal_cya", "sensibilidad_umbral_cya", "correlaciones_indices",
    "correlaciones_resumen", "comparacion_lagos", "distribucion_estacional",
    "persistencia_resumen", "zonas_espaciales_fecha", "zonas_espaciales_resumen",
]
tables = {name: pd.read_csv(TABLES / f"{name}.csv") for name in names}
cya = tables["serie_temporal_cya"]
comparison = tables["comparacion_lagos"]

amat = comparison.query("lago == 'amatitlan'").iloc[0]
atit = comparison.query("lago == 'atitlan'").iloc[0]
display(HTML(f"""
<div class="metric-grid">
 <div class="metric"><b>22</b>fechas oficiales procesadas</div>
 <div class="metric"><b>{int(amat.fechas_criticas)}</b>fechas críticas en Amatitlán</div>
 <div class="metric"><b>{int(atit.fechas_criticas)}</b>fechas críticas en Atitlán</div>
 <div class="metric"><b>{amat.area_alta_maxima_pct:.1f}%</b>máxima extensión alta en Amatitlán</div>
</div>
"""))
'''),
    md(r'''
<div class="section"><h2>1–3 · Datos, conexión e índices</h2><p>Del área oficial al producto mínimo reproducible.</p></div>

Se consultó `SENTINEL2_L2A` mediante openEO en Copernicus Data Space Ecosystem. Los GeoJSON proporcionados por el curso contienen las mismas cajas rectangulares de la guía; los contornos de OpenStreetMap delinean la orilla para el recorte fino y el cálculo de superficies.

Solo se solicitaron **B02, B03, B04, B08 y SCL**. El backend produjo NDVI, NDWI y CYA a 20 m. La separación agua–fondo `NDWI ≥ 0` reproduce el script Se2WaQ; SCL elimina nubes, cirros, sombras, nieve, saturación y ausencia de datos.

\[
NDVI=\frac{B08-B04}{B08+B04},\qquad NDWI=\frac{B03-B08}{B03+B08}
\]
\[
CYA=115530.31\left(\frac{B03\,B04}{B02}\right)^{2.38}
\]
'''),
    code(r'''
course = []
for lake, filename in {"Atitlán":"Lago_Atitlan.geojson", "Amatitlán":"Lago_Amatitlan.geojson"}.items():
    gdf = gpd.read_file(ROOT / "config" / filename)
    course.append({"lago":lake, "archivo":filename, "crs":str(gdf.crs),
                   "geometría":gdf.geometry.iloc[0].geom_type,
                   "área_caja_km²":gdf.to_crs(32615).area.iloc[0]/1e6})
display(pd.DataFrame(course).style.hide(axis="index").format({"área_caja_km²":"{:.1f}"}))
display(HTML("<div class='callout'><strong>Lectura:</strong> los archivos del curso son extensiones de consulta, no polígonos de costa. Por eso no se usan como denominador del porcentaje del lago.</div>"))
'''),
    md(r'''
<div class="section"><h2>4 · Evolución temporal</h2><p>Intensidad, cola alta y extensión por fecha.</p></div>

La rampa visual publicada por Se2WaQ termina en 100, pero el modelo genera valores mayores. Para no ocultar diferencias se usan la **mediana cruda** y el **percentil 90** en escala logarítmica. El corte `CYA ≥ 40` es exploratorio y no sanitario.
'''),
    code(r'''
peaks = []
for lake, group in cya.groupby("lago"):
    row = group.loc[group["mediana"].idxmax()]
    peaks.append({"lago":lake, "fecha_pico":row.fecha, "mediana_CYA":row.mediana,
                  "p90":row.p90, "área_CYA40_pct":row.porcentaje_area_alto})
display(pd.DataFrame(peaks).style.hide(axis="index").format({"mediana_CYA":"{:.2f}","p90":"{:.2f}","área_CYA40_pct":"{:.2f}%"}))
display(HTML("<img class='full-img' src='../outputs/figures/serie_temporal_cya.png'><p class='caption'>Figura 1. Las líneas unen únicamente fechas muestreadas; no representan observaciones continuas.</p>"))
'''),
    md(r'''
<div class="callout finding"><strong>Hallazgo temporal.</strong> Amatitlán alterna períodos bajos con señales generalizadas en abril de 2025 y marzo–junio de 2026. Su máximo robusto ocurre el 13 de abril de 2026. Atitlán permanece mucho más bajo y localizado; también alcanza su mayor mediana el 13 de abril de 2026, sin llegar a una fecha crítica de 10 % del lago.</div>
'''),
    md(r'''
<div class="section"><h2>5 · Distribución espacial</h2><p>Fechas representativas, diferencias y zonas persistentes.</p></div>
'''),
    code(r'''
display(HTML("""
<img class='full-img' src='../outputs/figures/mapas_cya_seleccion.png'>
<div class='two'>
 <div><img src='../outputs/figures/mapas_diferencia_cya.png'><p class='caption'>Cambio entre dos fechas comparables.</p></div>
 <div><img src='../outputs/figures/persistencia_cya.png'><p class='caption'>Fracción de al menos seis observaciones válidas con CYA ≥ 40.</p></div>
</div>
"""))
zones = tables["zonas_espaciales_resumen"].copy()
display(zones.style.hide(axis="index").format({
    "mediana_cya_tipica":"{:.2f}", "p90_cya_tipico":"{:.2f}",
    "porcentaje_alto_mediano":"{:.2f}%", "porcentaje_alto_maximo":"{:.2f}%"}))
'''),
    md(r'''
<div class="callout finding"><strong>Lectura espacial.</strong> En Amatitlán la señal alta aparece en ambos lóbulos y persiste ampliamente; el cuadrante noroeste presenta la mayor mediana típica. En Atitlán predominan valores bajos, con focos esporádicos hacia sectores occidentales y surorientales. Una discontinuidad rectangular del 17‑07‑2025 se trata como artefacto de tesela y no como forma natural.</div>
'''),
    md(r'''
<div class="section"><h2>6 · Relación con NDVI y NDWI</h2><p>Correlación no implica causalidad.</p></div>
'''),
    code(r'''
spearman = tables["correlaciones_resumen"].query("metodo == 'spearman'").copy()
display(spearman[["lago","par","fechas","coeficiente_mediano","coeficiente_min","coeficiente_max","fechas_negativas"]]
        .style.hide(axis="index").format({"coeficiente_mediano":"{:.3f}","coeficiente_min":"{:.3f}","coeficiente_max":"{:.3f}"}))
display(HTML("<img class='full-img' src='../outputs/figures/dispersion_correlaciones.png'>"))
'''),
    md(r'''
La asociación CYA–NDVI es débil a moderada y cambia de signo entre fechas. CYA–NDWI es generalmente negativa, especialmente en Atitlán. Parte de esta relación es matemática y metodológica: CYA y NDWI comparten bandas y el análisis conserva `NDWI ≥ 0`. Los valores de *p* no se interpretan como prueba independiente porque los píxeles vecinos están autocorrelacionados.
'''),
    md(r'''
<div class="section"><h2>7 · Comparación entre lagos</h2><p>Intensidad, frecuencia y contexto ambiental.</p></div>
'''),
    code(r'''
display(comparison.drop(columns=["fechas_criticas_lista"]).style.hide(axis="index").format(precision=2))
display(HTML("<img class='full-img' src='../outputs/figures/comparacion_lagos.png'>"))
display(HTML(f"<div class='callout finding'><strong>Contraste central:</strong> Amatitlán tuvo {int(amat.fechas_criticas)} fechas críticas y una extensión máxima de {amat.area_alta_maxima_pct:.1f}%; Atitlán tuvo {int(atit.fechas_criticas)} y un máximo de {atit.area_alta_maxima_pct:.1f}%.</div>"))
'''),
    md(r'''
El contraste es compatible con presiones ambientales diferentes, pero el satélite no demuestra su causa. AMSA describe al lago Amatitlán como un sistema sometido a contaminación continua y aportes de la cuenca urbana; estudios sobre Atitlán documentan cargas de aguas residuales, escorrentía agrícola y episodios históricos de floración, aunque su gran volumen y profundidad producen otra dinámica. Estas fuentes contextualizan, no sustituyen, la evidencia espectral.
'''),
    md(r'''
<div class="section"><h2>8 · Exploración adicional</h2><p>Sensibilidad, distribuciones, persistencia y estación.</p></div>
'''),
    code(r'''
display(HTML("<div class='two'><img src='../outputs/figures/distribuciones_cya.png'><img src='../outputs/figures/mapas_cya_logaritmico.png'></div>"))
display(HTML("<h3>Sensibilidad al umbral</h3>"))
sens = tables["sensibilidad_umbral_cya"]
display(sens.groupby(["lago","umbral"])["porcentaje_area"].median().unstack().style.format("{:.2f}%"))
display(HTML("<h3>Exploración estacional</h3>"))
display(tables["distribucion_estacional"].style.hide(axis="index").format(precision=2))
'''),
    md(r'''
<div class="callout warning"><strong>No hay evidencia suficiente para una estacionalidad concluyente.</strong> Amatitlán solo posee una observación clasificada como lluviosa y las fechas son irregulares. En Atitlán las tres fechas lluviosas muestran una señal algo mayor, pero una de ellas contiene el artefacto del 17‑07‑2025.</div>

<div class="section"><h2>Control de calidad y límites</h2><p>Qué puede y qué no puede concluirse.</p></div>
'''),
    code(r'''
review = tables["revision_visual_rasters"]
display(review.query("apta_mapa_representativo == False").style.hide(axis="index").format({"cobertura_poligono_pct":"{:.2f}%"}))
display(HTML("""
<div class='callout warning'>
<strong>Limitaciones principales:</strong> CYA es un modelo calibrado fuera de Guatemala; la rampa 0–100 se satura; la máscara Se2WaQ puede excluir superficies ópticamente semejantes a vegetación; hay cobertura parcial en tres fechas; no existen mediciones de campo simultáneas; y la muestra temporal no es regular.
</div>
"""))
'''),
    md(r'''
<div class="section"><h2>Conclusiones</h2><p>Respuesta integrada a los ejercicios 1–8.</p></div>

1. El flujo openEO obtuvo únicamente las bandas necesarias y produjo los tres índices para las 22 fechas oficiales.
2. Amatitlán exhibió señales CYA mucho más intensas, extensas y persistentes que Atitlán; seis fechas superaron el criterio exploratorio de 10 % del lago.
3. Atitlán mantuvo señales bajas y localizadas; ningún evento superó el criterio de fecha crítica.
4. Las asociaciones con NDVI y NDWI varían por fecha y están condicionadas por bandas compartidas, máscara acuática y autocorrelación espacial.
5. Los patrones son indicadores para priorizar inspección y muestreo. No confirman células, especies, toxinas ni riesgo sanitario.

<div class="footer"><strong>Producto reproducible:</strong> las tablas y figuras se regeneran con <code>python scripts/analyze_full.py</code>. Los mapas interactivos están en <code>outputs/figures/mapa_interactivo_*.html</code>.</div>

### Referencias esenciales

- Pereira, N. S. A. (2020). *Se2WaQ – Sentinel‑2 Water Quality Script*.
- Potes et al. (2018). *Use of Sentinel‑2 MSI for water quality monitoring at Alqueva reservoir*.
- AMSCLAE (2024). *Informe anual de investigación y calidad ambiental*.
- AMSA (2022–2030). *Plan Estratégico Institucional*.
- Weisman et al. (2018). *Effects of nutrient limitations and watershed inputs on community respiration in Lake Atitlán*.
'''),
]

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUTPUT)
print(f"Notebook construido: {OUTPUT}")
