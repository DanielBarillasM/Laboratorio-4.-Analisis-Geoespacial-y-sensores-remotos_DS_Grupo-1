"""Genera todas las tablas y figuras de los ejercicios 4 a 8.

Uso normal, con los 22 GeoTIFF ya descargados bajo ``data/raw/cdse``:

    python scripts/analyze_full.py

El script no interpreta resultados: produce las tablas y figuras sobre las que se
escriben el notebook final y el informe. Imprime al final un resumen para que la
persona que redacta trabaje con cifras verificadas y no de memoria.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import folium
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm, TwoSlopeNorm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lab4.analysis import (  # noqa: E402
    CYANO_DISPLAY_MAX,
    CYANO_HIGH_THRESHOLD,
    CYANO_THRESHOLDS,
    correlate_indices,
    difference_map,
    persistence_fraction,
    read_index_raster,
    season_of,
    stack_lake_rasters,
    summarize_index_raster,
    threshold_sensitivity,
)
from lab4.config import (  # noqa: E402
    AREAS,
    CONFIG_DIR,
    FIGURES_DIR,
    RAW_DIR,
    TABLES_DIR,
    ensure_output_directories,
    load_observations,
)
from lab4.mapping import format_map_axes, raster_extent, to_wgs84  # noqa: E402

COLORS = {"atitlan": "#167d9a", "amatitlan": "#d5793d"}
LABELS = {"atitlan": "Atitlán", "amatitlan": "Amatitlán"}
CYA_UNIT = "CYA (10³ células/ml)"

# Una fecha se considera crítica cuando la floración deja de ser un punto aislado
# y cubre una décima parte del lago. Es un corte declarado, no un límite sanitario.
CRITICAL_AREA_PCT = 10.0

# Un píxel debe haberse observado en al menos la mitad de las once fechas para
# llamarlo persistente. Así una única observación despejada no produce 100 %.
MIN_PERSISTENCE_OBSERVATIONS = 6

# Fechas que no deben elegirse para mapas representativos. Permanecen en las
# series y tablas, acompañadas por una observación de calidad explícita.
VISUAL_QUALITY_NOTES = {
    ("amatitlan", "2026-04-28"): "Cobertura válida inferior a 80 %.",
    ("atitlan", "2025-01-18"): "Cobertura válida de 43.21 %; patrón espacial incompleto.",
    ("atitlan", "2025-07-17"): (
        "Discontinuidad rectangular compatible con límite de tesela; no interpretar "
        "el parche occidental como estructura natural."
    ),
    ("atitlan", "2026-02-12"): "Cobertura válida inferior a 80 %.",
}


def date_from_name(path: Path) -> str:
    match = re.search(r"20\d{2}-\d{2}-\d{2}", path.name)
    if not match:
        raise ValueError(f"No se encontró fecha ISO en {path.name}")
    return match.group(0)


def collect_rasters(raw_dir: Path) -> dict[str, list[tuple[str, Path]]]:
    """Agrupa los GeoTIFF por lago, ordenados por fecha."""

    por_lago: dict[str, list[tuple[str, Path]]] = {}
    for path in sorted(raw_dir.glob("*/*.tif")):
        por_lago.setdefault(path.parent.name, []).append((date_from_name(path), path))
    for lago in por_lago:
        por_lago[lago].sort()
    return por_lago


def lake_areas(crs) -> dict[str, float]:
    """Área del espejo de agua de cada lago, en m², según los contornos usados."""

    contornos = gpd.read_file(CONFIG_DIR / "lake_boundaries_osm.geojson").to_crs(crs)
    return dict(zip(contornos["id"], contornos.area))


def lake_outline(crs, lake: str) -> gpd.GeoDataFrame:
    contornos = gpd.read_file(CONFIG_DIR / "lake_boundaries_osm.geojson").to_crs(crs)
    return contornos[contornos["id"] == lake]


# --------------------------------------------------------------------------- #
# Tablas
# --------------------------------------------------------------------------- #

def audit_rasters(
    por_lago: dict[str, list[tuple[str, Path]]], areas: dict[str, float]
) -> pd.DataFrame:
    """Control de calidad: rejilla, cobertura efectiva y rango de cada índice.

    La cobertura se reporta sin recortarla a 100 %: si un ráster excede el área
    del contorno, eso mismo es un aviso de que la máscara o el polígono no
    coinciden, y esconderlo detrás de un mínimo lo volvería invisible.
    """

    filas = []
    for lago, entradas in por_lago.items():
        for fecha, path in entradas:
            arrays, profile = read_index_raster(path)
            pixel_area = abs(profile["transform"].a * profile["transform"].e)
            validos = int(np.isfinite(arrays["CYA"]).sum())
            fila = {
                "lago": lago,
                "fecha": fecha,
                "archivo": path.name,
                "crs": str(profile["crs"]),
                "resolucion_m": abs(profile["transform"].a),
                "pixeles_validos": validos,
                "cobertura_poligono_pct": 100 * validos * pixel_area / areas[lago],
            }
            for nombre, valores in arrays.items():
                finitos = valores[np.isfinite(valores)]
                fila[f"{nombre.lower()}_min"] = float(finitos.min()) if finitos.size else np.nan
                fila[f"{nombre.lower()}_max"] = float(finitos.max()) if finitos.size else np.nan
            filas.append(fila)
    return pd.DataFrame(filas).sort_values(["lago", "fecha"]).reset_index(drop=True)


def visual_quality_table(control_calidad: pd.DataFrame) -> pd.DataFrame:
    """Registra la revisión visual de las 22 fechas sin borrar observaciones."""

    tabla = control_calidad[["lago", "fecha", "cobertura_poligono_pct"]].copy()
    claves = list(zip(tabla["lago"], tabla["fecha"]))
    tabla["apta_mapa_representativo"] = [clave not in VISUAL_QUALITY_NOTES for clave in claves]
    tabla["observacion_visual"] = [
        VISUAL_QUALITY_NOTES.get(clave, "Sin incidencia dominante en el atlas de control.")
        for clave in claves
    ]
    return tabla


def build_statistics(
    por_lago: dict[str, list[tuple[str, Path]]], areas: dict[str, float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estadísticos por índice y sensibilidad del umbral, para cada fecha."""

    estadisticas, sensibilidad = [], []
    for lago, entradas in por_lago.items():
        for fecha, path in entradas:
            estadisticas.append(summarize_index_raster(
                path, lake=lago, date=fecha, lake_area_m2=areas[lago],
            ))
            arrays, profile = read_index_raster(path)
            pixel_area = abs(profile["transform"].a * profile["transform"].e)
            sensibilidad.append(threshold_sensitivity(
                arrays["CYA"], lake=lago, date=fecha, thresholds=CYANO_THRESHOLDS,
                pixel_area_m2=pixel_area, lake_area_m2=areas[lago],
            ))
    return (
        pd.concat(estadisticas, ignore_index=True).sort_values(["lago", "fecha", "indice"]),
        pd.concat(sensibilidad, ignore_index=True).sort_values(["lago", "fecha", "umbral"]),
    )


def build_correlations(por_lago: dict[str, list[tuple[str, Path]]]) -> pd.DataFrame:
    """Correlaciones de CYA con NDVI y NDWI, fecha por fecha."""

    tablas = []
    for lago, entradas in por_lago.items():
        for fecha, path in entradas:
            arrays, _ = read_index_raster(path)
            tablas.append(correlate_indices(arrays, lake=lago, date=fecha))
    return pd.concat(tablas, ignore_index=True)


def summarize_correlations(correlaciones: pd.DataFrame) -> pd.DataFrame:
    """Resume por lago: mediana del coeficiente y en cuántas fechas es negativo."""

    filas = []
    for (lago, par, metodo), grupo in correlaciones.query("muestra == 'completa'").groupby(
        ["lago", "par", "metodo"]
    ):
        coeficientes = grupo["coeficiente"].dropna()
        filas.append({
            "lago": lago,
            "par": par,
            "metodo": metodo,
            "fechas": int(coeficientes.size),
            "coeficiente_mediano": float(coeficientes.median()) if coeficientes.size else np.nan,
            "coeficiente_min": float(coeficientes.min()) if coeficientes.size else np.nan,
            "coeficiente_max": float(coeficientes.max()) if coeficientes.size else np.nan,
            "fechas_negativas": int((coeficientes < 0).sum()),
            "n_pixeles_mediano": float(grupo["n"].median()),
        })
    return pd.DataFrame(filas).sort_values(["lago", "par", "metodo"])


def compare_lakes(cya: pd.DataFrame) -> pd.DataFrame:
    """Comparación del ejercicio 7 sobre estadísticos robustos, no truncados."""

    filas = []
    for lago, grupo in cya.groupby("lago"):
        criticas = grupo[grupo["porcentaje_area_alto"] >= CRITICAL_AREA_PCT]
        filas.append({
            "lago": lago,
            "fechas": int(len(grupo)),
            "mediana_tipica": float(grupo["mediana"].median()),
            "mediana_maxima": float(grupo["mediana"].max()),
            "p90_tipico": float(grupo["p90"].median()),
            "p99_maximo": float(grupo["p99"].max()),
            "area_alta_mediana_pct": float(grupo["porcentaje_area_alto"].median()),
            "area_alta_maxima_pct": float(grupo["porcentaje_area_alto"].max()),
            "fechas_criticas": int(len(criticas)),
            "fechas_criticas_lista": ", ".join(sorted(criticas["fecha"])),
            "cobertura_minima_pct": float(grupo["cobertura_valida_pct"].min()),
            "saturacion_maxima_pct": float(grupo["porcentaje_saturado_100"].max()),
        })
    return pd.DataFrame(filas)


def seasonal_table(cya: pd.DataFrame) -> pd.DataFrame:
    """Reparto por estación. Con once fechas irregulares solo permite explorar."""

    con_estacion = cya.assign(estacion=cya["fecha"].map(season_of))
    resumen = con_estacion.groupby(["lago", "estacion"]).agg(
        fechas=("fecha", "size"),
        mediana_tipica=("mediana", "median"),
        area_alta_mediana_pct=("porcentaje_area_alto", "median"),
        area_alta_maxima_pct=("porcentaje_area_alto", "max"),
    ).reset_index()
    return resumen


def persistence_table(
    por_lago: dict[str, list[tuple[str, Path]]], areas: dict[str, float]
) -> tuple[pd.DataFrame, dict[str, tuple[np.ndarray, np.ndarray, dict]]]:
    """Mapas de persistencia y su resumen por lago."""

    filas, mapas = [], {}
    for lago, entradas in por_lago.items():
        fechas, cubos, profile = stack_lake_rasters(entradas)
        fraccion, n_valid = persistence_fraction(
            cubos["CYA"],
            CYANO_HIGH_THRESHOLD,
            min_observations=MIN_PERSISTENCE_OBSERVATIONS,
        )
        mapas[lago] = (fraccion, n_valid, profile)
        pixel_area = abs(profile["transform"].a * profile["transform"].e)
        observados = np.isfinite(fraccion)
        for corte in (0.25, 0.50, 0.75):
            encima = int(np.sum(fraccion[observados] >= corte))
            filas.append({
                "lago": lago,
                "fechas_apiladas": len(fechas),
                "min_observaciones_validas": MIN_PERSISTENCE_OBSERVATIONS,
                "corte_persistencia": corte,
                "pixeles": encima,
                "area_km2": encima * pixel_area / 1e6,
                "porcentaje_area_lago": 100 * encima * pixel_area / areas[lago],
            })
    return pd.DataFrame(filas), mapas


def spatial_zone_tables(
    por_lago: dict[str, list[tuple[str, Path]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resume CYA por cuadrantes para sustentar la interpretación espacial.

    Los cuadrantes se definen respecto del centro de la rejilla de cada lago. No
    sustituyen una zonificación hidrológica; sirven como referencia reproducible
    para describir norte/sur y este/oeste sin depender solo de la vista del mapa.
    """

    filas = []
    for lago, entradas in por_lago.items():
        for fecha, path in entradas:
            arrays, profile = read_index_raster(path)
            valores = arrays["CYA"]
            alto, ancho = valores.shape
            transform = profile["transform"]
            columnas = np.arange(ancho)
            renglones = np.arange(alto)
            xs = transform.c + (columnas + 0.5) * transform.a
            ys = transform.f + (renglones + 0.5) * transform.e
            centro_x = (xs.min() + xs.max()) / 2
            centro_y = (ys.min() + ys.max()) / 2
            oeste = xs < centro_x
            norte = ys >= centro_y
            zonas = {
                "noroeste": norte[:, None] & oeste[None, :],
                "noreste": norte[:, None] & ~oeste[None, :],
                "suroeste": ~norte[:, None] & oeste[None, :],
                "sureste": ~norte[:, None] & ~oeste[None, :],
            }
            for zona, mascara in zonas.items():
                muestra = valores[mascara & np.isfinite(valores)]
                filas.append({
                    "lago": lago,
                    "fecha": fecha,
                    "zona": zona,
                    "n_pixeles_validos": int(muestra.size),
                    "mediana_cya": float(np.median(muestra)) if muestra.size else np.nan,
                    "p90_cya": float(np.percentile(muestra, 90)) if muestra.size else np.nan,
                    "porcentaje_alto": (
                        float(100 * np.mean(muestra >= CYANO_HIGH_THRESHOLD))
                        if muestra.size else np.nan
                    ),
                })
    por_fecha = pd.DataFrame(filas).sort_values(["lago", "fecha", "zona"])
    resumen = por_fecha.groupby(["lago", "zona"]).agg(
        fechas=("fecha", "size"),
        mediana_cya_tipica=("mediana_cya", "median"),
        p90_cya_tipico=("p90_cya", "median"),
        porcentaje_alto_mediano=("porcentaje_alto", "median"),
        porcentaje_alto_maximo=("porcentaje_alto", "max"),
    ).reset_index()
    return por_fecha, resumen


# --------------------------------------------------------------------------- #
# Figuras
# --------------------------------------------------------------------------- #

def plot_temporal(cya: pd.DataFrame) -> None:
    """Serie temporal de media, estadísticos robustos y extensión sobre el lago."""

    datos = cya.assign(fecha=pd.to_datetime(cya["fecha"]))
    fig, axes = plt.subplots(3, 1, figsize=(11, 11), sharex=True, constrained_layout=True)
    for lago, grupo in datos.groupby("lago"):
        grupo = grupo.sort_values("fecha")
        estilo = {"marker": "o", "linewidth": 2.2, "color": COLORS[lago]}
        axes[0].plot(
            grupo["fecha"], grupo["media"],
            **estilo, label=f"{LABELS[lago]} · media aritmética",
        )
        axes[0].plot(
            grupo["fecha"], grupo["mediana"],
            color=COLORS[lago], marker="s", linewidth=1.6, linestyle="--",
            alpha=.82, label=f"{LABELS[lago]} · mediana",
        )
        axes[1].plot(grupo["fecha"], grupo["p90"], **estilo, label=LABELS[lago])
        axes[2].plot(
            grupo["fecha"], grupo["porcentaje_area_alto"],
            **estilo, label=LABELS[lago],
        )

    axes[0].set(ylabel=f"Media y mediana · {CYA_UNIT}", yscale="log")
    axes[0].set_title("Promedio aritmético de CYA por lago y fecha, con mediana robusta")
    axes[1].set(ylabel=f"Percentil 90 · {CYA_UNIT}", yscale="log")
    axes[1].set_title("Cola alta de la distribución")
    axes[2].set(ylabel="Área del lago con CYA ≥ 40 (%)", xlabel="Fecha de adquisición")
    axes[2].set_title("Extensión de la señal sobre el área total del lago")
    axes[2].axhline(CRITICAL_AREA_PCT, color="#8d5a12", linestyle="--", linewidth=1,
                    label=f"Fecha crítica ({CRITICAL_AREA_PCT:g} % del lago)")
    axes[2].set_ylim(-3, 103)
    for ax in axes:
        ax.grid(alpha=.22)
        ax.legend(frameon=False, ncol=3, fontsize=8)
    axes[2].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    save(fig, "serie_temporal_cya")


def plot_selected_maps(
    por_lago: dict[str, list[tuple[str, Path]]], seleccion: dict[str, list[str]]
) -> None:
    """Mapas georreferenciados con contorno, escala, norte y rampa Se2WaQ."""

    fig, axes = plt.subplots(2, 3, figsize=(15, 9.5), constrained_layout=True)
    imagen = None
    for fila, lago in enumerate(("amatitlan", "atitlan")):
        rutas = dict(por_lago[lago])
        for columna, fecha in enumerate(seleccion[lago]):
            ax = axes[fila, columna]
            arrays, profile = read_index_raster(rutas[fecha])
            imagen = ax.imshow(
                np.clip(arrays["CYA"], 0, CYANO_DISPLAY_MAX), cmap="turbo",
                vmin=0, vmax=CYANO_DISPLAY_MAX, extent=raster_extent(profile),
            )
            lake_outline(profile["crs"], lago).boundary.plot(
                ax=ax, edgecolor="#19313b", linewidth=.9, zorder=5
            )
            ax.set_title(f"{LABELS[lago]} · {fecha}", fontweight="bold", fontsize=10)
            format_map_axes(ax, profile, scale_length_m=2000 if lago == "amatitlan" else 5000)
    fig.colorbar(imagen, ax=axes, shrink=.7, extend="max",
                 label=f"{CYA_UNIT}, rampa publicada 0–100")
    fig.suptitle("Distribución espacial en fechas representativas", fontsize=15, fontweight="bold")
    save(fig, "mapas_cya_seleccion")


def plot_log_maps(
    por_lago: dict[str, list[tuple[str, Path]]], seleccion: dict[str, list[str]]
) -> None:
    """Los mismos mapas en escala logarítmica, donde la rampa 0–100 se satura."""

    fig, axes = plt.subplots(2, 3, figsize=(15, 9.5), constrained_layout=True)
    norma = LogNorm(vmin=0.1, vmax=1000)
    imagen = None
    for fila, lago in enumerate(("amatitlan", "atitlan")):
        rutas = dict(por_lago[lago])
        for columna, fecha in enumerate(seleccion[lago]):
            ax = axes[fila, columna]
            arrays, profile = read_index_raster(rutas[fecha])
            valores = np.where(arrays["CYA"] > 0, arrays["CYA"], np.nan)
            imagen = ax.imshow(valores, cmap="magma", norm=norma, extent=raster_extent(profile))
            lake_outline(profile["crs"], lago).boundary.plot(
                ax=ax, edgecolor="#dddddd", linewidth=.9, zorder=5
            )
            ax.set_title(f"{LABELS[lago]} · {fecha}", fontweight="bold", fontsize=10)
            format_map_axes(ax, profile, scale_length_m=2000 if lago == "amatitlan" else 5000)
    fig.colorbar(imagen, ax=axes, shrink=.7, extend="both", label=f"{CYA_UNIT}, escala logarítmica")
    fig.suptitle("La misma señal sin truncar: estructura interna de cada lago",
                 fontsize=15, fontweight="bold")
    save(fig, "mapas_cya_logaritmico")


def plot_difference_maps(
    por_lago: dict[str, list[tuple[str, Path]]], comparaciones: dict[str, tuple[str, str]]
) -> None:
    """Mapa de diferencia entre dos fechas por lago (ejercicios 5.2 y 8.3)."""

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), constrained_layout=True)
    for ax, (lago, (antes, despues)) in zip(axes, comparaciones.items()):
        rutas = dict(por_lago[lago])
        previo, profile = read_index_raster(rutas[antes])
        posterior, _ = read_index_raster(rutas[despues])
        diferencia = difference_map(
            np.clip(posterior["CYA"], 0, CYANO_DISPLAY_MAX),
            np.clip(previo["CYA"], 0, CYANO_DISPLAY_MAX),
        )
        limite = float(np.nanmax(np.abs(diferencia))) or 1.0
        imagen = ax.imshow(diferencia, cmap="RdBu_r", extent=raster_extent(profile),
                           norm=TwoSlopeNorm(vcenter=0, vmin=-limite, vmax=limite))
        lake_outline(profile["crs"], lago).boundary.plot(
            ax=ax, edgecolor="#19313b", linewidth=.9, zorder=5
        )
        ax.set_title(f"{LABELS[lago]}: {despues} menos {antes}", fontweight="bold", fontsize=11)
        format_map_axes(ax, profile, scale_length_m=2000 if lago == "amatitlan" else 5000)
        fig.colorbar(imagen, ax=ax, shrink=.8, label="Cambio en CYA (escala 0–100)")
    fig.suptitle("Mapas de diferencia entre fechas", fontsize=15, fontweight="bold")
    save(fig, "mapas_diferencia_cya")


def plot_persistence(mapas: dict[str, tuple[np.ndarray, np.ndarray, dict]]) -> None:
    """Proporción de observaciones válidas en que cada píxel supera el umbral."""

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), constrained_layout=True)
    imagen = None
    for ax, (lago, (fraccion, _, profile)) in zip(axes, mapas.items()):
        imagen = ax.imshow(fraccion, cmap="YlOrRd", vmin=0, vmax=1,
                           extent=raster_extent(profile))
        lake_outline(profile["crs"], lago).boundary.plot(
            ax=ax, edgecolor="#19313b", linewidth=.9, zorder=5
        )
        ax.set_title(LABELS[lago], fontweight="bold", fontsize=11)
        format_map_axes(ax, profile, scale_length_m=2000 if lago == "amatitlan" else 5000)
    fig.colorbar(imagen, ax=axes, shrink=.8,
                 label="Fracción de observaciones válidas con CYA ≥ 40")
    fig.suptitle("Zonas persistentes de acumulación", fontsize=15, fontweight="bold")
    save(fig, "persistencia_cya")


def plot_all_dates(por_lago: dict[str, list[tuple[str, Path]]]) -> None:
    """Atlas de control visual con las once fechas oficiales de cada lago."""

    for lago, entradas in por_lago.items():
        fig, axes = plt.subplots(3, 4, figsize=(15, 11), constrained_layout=True)
        imagen = None
        for ax, (fecha, path) in zip(axes.flat, entradas):
            arrays, profile = read_index_raster(path)
            imagen = ax.imshow(
                np.clip(arrays["CYA"], 0, CYANO_DISPLAY_MAX),
                cmap="turbo", vmin=0, vmax=CYANO_DISPLAY_MAX,
                extent=raster_extent(profile),
            )
            lake_outline(profile["crs"], lago).boundary.plot(
                ax=ax, edgecolor="#19313b", linewidth=.55, zorder=5
            )
            ax.set_title(fecha, fontsize=9, fontweight="bold")
            ax.set_xticks([])
            ax.set_yticks([])
        for ax in axes.flat[len(entradas):]:
            ax.axis("off")
        fig.colorbar(imagen, ax=axes, shrink=.72, extend="max", label=f"{CYA_UNIT}, escala 0–100")
        fig.suptitle(
            f"Atlas temporal de CYA · {LABELS[lago]}", fontsize=16, fontweight="bold"
        )
        save(fig, f"atlas_cya_{lago}")


def plot_distributions(por_lago: dict[str, list[tuple[str, Path]]]) -> None:
    """Cajas por fecha en escala logarítmica (ejercicio 8.3)."""

    fig, axes = plt.subplots(2, 1, figsize=(12, 9), constrained_layout=True)
    for ax, lago in zip(axes, ("amatitlan", "atitlan")):
        muestras, etiquetas = [], []
        for fecha, path in por_lago[lago]:
            arrays, _ = read_index_raster(path)
            valores = arrays["CYA"][np.isfinite(arrays["CYA"])]
            valores = valores[valores > 0]
            if valores.size > 20000:  # muestreo solo para que el dibujo sea manejable
                valores = np.random.default_rng(0).choice(valores, 20000, replace=False)
            muestras.append(valores)
            etiquetas.append(fecha)
        caja = ax.boxplot(muestras, tick_labels=etiquetas, showfliers=False, patch_artist=True)
        for parche in caja["boxes"]:
            parche.set(facecolor=COLORS[lago], alpha=.45, edgecolor=COLORS[lago])
        for mediana in caja["medians"]:
            mediana.set(color="#19313b", linewidth=1.4)
        ax.axhline(CYANO_HIGH_THRESHOLD, color="#8d5a12", linestyle="--", linewidth=1,
                   label=f"Umbral de CYA alta ({CYANO_HIGH_THRESHOLD:g})")
        ax.set(yscale="log", ylabel=CYA_UNIT, title=LABELS[lago])
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.grid(alpha=.22, axis="y")
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Distribución de valores por fecha", fontsize=15, fontweight="bold")
    save(fig, "distribuciones_cya")


def plot_correlation_scatter(por_lago: dict[str, list[tuple[str, Path]]],
                             seleccion: dict[str, list[str]]) -> None:
    """Dispersión de CYA contra NDVI y NDWI en fechas representativas."""

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    generador = np.random.default_rng(0)
    for fila, lago in enumerate(("amatitlan", "atitlan")):
        rutas = dict(por_lago[lago])
        for columna, otro in enumerate(("NDVI", "NDWI")):
            ax = axes[fila, columna]
            for fecha in seleccion[lago]:
                arrays, _ = read_index_raster(rutas[fecha])
                valido = np.isfinite(arrays["CYA"]) & np.isfinite(arrays[otro]) & (arrays["CYA"] > 0)
                x = arrays[otro][valido]
                y = arrays["CYA"][valido]
                if x.size > 4000:
                    indices = generador.choice(x.size, 4000, replace=False)
                    x, y = x[indices], y[indices]
                ax.scatter(x, y, s=3, alpha=.25, label=fecha)
            ax.axhline(CYANO_HIGH_THRESHOLD, color="#8d5a12", linestyle="--", linewidth=1)
            ax.set(yscale="log", xlabel=otro, ylabel=CYA_UNIT,
                   title=f"{LABELS[lago]} · CYA frente a {otro}")
            ax.grid(alpha=.22)
            ax.legend(frameon=False, fontsize=7, markerscale=3)
    fig.suptitle("Relación entre el proxy de cianobacteria y los índices espectrales",
                 fontsize=15, fontweight="bold")
    save(fig, "dispersion_correlaciones")


def plot_lake_comparison(comparacion: pd.DataFrame, cya: pd.DataFrame) -> None:
    """Resumen visual del ejercicio 7."""

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), constrained_layout=True)
    lagos = comparacion["lago"].tolist()
    colores = [COLORS[lago] for lago in lagos]
    etiquetas = [LABELS[lago] for lago in lagos]

    axes[0].bar(etiquetas, comparacion["mediana_tipica"], color=colores)
    axes[0].set(ylabel=CYA_UNIT, title="Mediana típica del lago", yscale="log")

    axes[1].bar(etiquetas, comparacion["area_alta_maxima_pct"], color=colores, alpha=.55,
                label="Máximo")
    axes[1].bar(etiquetas, comparacion["area_alta_mediana_pct"], color=colores, label="Mediana")
    axes[1].set(ylabel="Área del lago con CYA ≥ 40 (%)", title="Extensión de la señal")
    axes[1].legend(frameon=False, fontsize=8)

    axes[2].bar(etiquetas, comparacion["fechas_criticas"], color=colores)
    axes[2].set(ylabel="Número de fechas", title=f"Fechas con ≥ {CRITICAL_AREA_PCT:g} % del lago")
    axes[2].set_ylim(0, max(1, int(cya.groupby("lago").size().max())))

    for ax in axes:
        ax.grid(alpha=.22, axis="y")
    fig.suptitle("Comparación entre los dos lagos", fontsize=15, fontweight="bold")
    save(fig, "comparacion_lagos")


def build_interactive_maps(
    por_lago: dict[str, list[tuple[str, Path]]], seleccion: dict[str, list[str]]
) -> list[Path]:
    """Mapa folium por lago con una capa por fecha sobre el mapa base."""

    salidas = []
    for lago, fechas in seleccion.items():
        rutas = dict(por_lago[lago])
        area = AREAS[lago]
        centro = [(area.south + area.north) / 2, (area.west + area.east) / 2]
        mapa = folium.Map(location=centro, zoom_start=12, tiles="OpenStreetMap")
        for fecha in fechas:
            arrays, profile = read_index_raster(rutas[fecha])
            valores, limites = to_wgs84(np.clip(arrays["CYA"], 0, CYANO_DISPLAY_MAX), profile)
            normalizado = np.clip(valores / CYANO_DISPLAY_MAX, 0, 1)
            coloreado = plt.get_cmap("turbo")(normalizado)
            coloreado[..., 3] = np.where(np.isfinite(valores), 0.75, 0.0)
            folium.raster_layers.ImageOverlay(
                image=coloreado, bounds=limites, name=f"CYA {fecha}", opacity=1.0,
            ).add_to(mapa)
        contorno = lake_outline("EPSG:4326", lago)
        folium.GeoJson(
            contorno.to_json(), name="Contorno del lago",
            style_function=lambda _: {"color": "#19313b", "weight": 2, "fillOpacity": 0},
        ).add_to(mapa)
        folium.LayerControl(collapsed=False).add_to(mapa)
        salida = FIGURES_DIR / f"mapa_interactivo_{lago}.html"
        mapa.save(str(salida))
        salidas.append(salida)
    return salidas


def save(fig, nombre: str) -> None:
    fig.savefig(FIGURES_DIR / f"{nombre}.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIGURES_DIR / f"{nombre}.pdf", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #

def choose_dates(cya: pd.DataFrame, lago: str, cuantas: int = 3) -> list[str]:
    """Elige fechas representativas: la más baja, la mediana y la más alta.

    Elegirlas a partir de los datos evita que la selección quede fijada a mano y
    deje de tener sentido cuando cambien las estadísticas.
    """

    excluidas = {fecha for (nombre, fecha) in VISUAL_QUALITY_NOTES if nombre == lago}
    grupo = cya[(cya["lago"] == lago) & ~cya["fecha"].isin(excluidas)].sort_values(
        "porcentaje_area_alto"
    )
    if len(grupo) <= cuantas:
        return sorted(grupo["fecha"])
    indices = [0, len(grupo) // 2, len(grupo) - 1][:cuantas]
    return sorted(grupo.iloc[indices]["fecha"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR,
                        help="Carpeta con subcarpetas por lago y los GeoTIFF dentro.")
    parser.add_argument("--tables-dir", type=Path, default=TABLES_DIR,
                        help="Destino de las tablas; útil para pruebas de humo.")
    parser.add_argument("--figures-dir", type=Path, default=FIGURES_DIR,
                        help="Destino de las figuras; útil para pruebas de humo.")
    parser.add_argument("--skip-check", action="store_true",
                        help="No exigir que estén las 22 fechas oficiales.")
    return parser.parse_args()


def main() -> int:
    global TABLES_DIR, FIGURES_DIR

    args = parse_args()
    ensure_output_directories()
    TABLES_DIR, FIGURES_DIR = args.tables_dir, args.figures_dir
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    por_lago = collect_rasters(args.raw_dir)
    total = sum(len(v) for v in por_lago.values())
    if not total:
        raise SystemExit(
            f"No se encontró ningún GeoTIFF en {args.raw_dir}. "
            "Ejecute antes: python scripts/download_cdse.py --lake all --submit"
        )
    if not args.skip_check:
        oficiales = load_observations()
        esperado = set(zip(oficiales["lago"], oficiales["fecha"].dt.strftime("%Y-%m-%d")))
        encontrado = {(lago, fecha) for lago, e in por_lago.items() for fecha, _ in e}
        if encontrado != esperado:
            raise SystemExit(f"Diferencia con las fechas oficiales: {esperado ^ encontrado}")

    primer_perfil = read_index_raster(next(iter(por_lago.values()))[0][1])[1]
    areas = lake_areas(primer_perfil["crs"])

    control_calidad = audit_rasters(por_lago, areas)
    revision_visual = visual_quality_table(control_calidad)
    estadisticas, sensibilidad = build_statistics(por_lago, areas)
    cya = estadisticas.query("indice == 'CYA'").reset_index(drop=True)
    correlaciones = build_correlations(por_lago)
    resumen_correlaciones = summarize_correlations(correlaciones)
    comparacion = compare_lakes(cya)
    estacional = seasonal_table(cya)
    persistencia, mapas_persistencia = persistence_table(por_lago, areas)
    zonas_fecha, zonas_resumen = spatial_zone_tables(por_lago)

    for nombre, tabla in {
        "control_calidad_rasters": control_calidad,
        "revision_visual_rasters": revision_visual,
        "estadisticas_indices": estadisticas,
        "serie_temporal_cya": cya,
        "sensibilidad_umbral_cya": sensibilidad,
        "correlaciones_indices": correlaciones,
        "correlaciones_resumen": resumen_correlaciones,
        "comparacion_lagos": comparacion,
        "distribucion_estacional": estacional,
        "persistencia_resumen": persistencia,
        "zonas_espaciales_fecha": zonas_fecha,
        "zonas_espaciales_resumen": zonas_resumen,
    }.items():
        tabla.to_csv(TABLES_DIR / f"{nombre}.csv", index=False, lineterminator="\n")

    seleccion = {lago: choose_dates(cya, lago) for lago in por_lago}
    comparaciones = {
        lago: (fechas[0], fechas[-1]) for lago, fechas in seleccion.items() if len(fechas) >= 2
    }

    plot_temporal(cya)
    plot_selected_maps(por_lago, seleccion)
    plot_log_maps(por_lago, seleccion)
    if comparaciones:
        plot_difference_maps(por_lago, comparaciones)
    plot_persistence(mapas_persistencia)
    plot_all_dates(por_lago)
    plot_distributions(por_lago)
    plot_correlation_scatter(por_lago, seleccion)
    plot_lake_comparison(comparacion, cya)
    interactivos = build_interactive_maps(por_lago, seleccion)

    print(f"GeoTIFF procesados: {total}")
    print(f"Mapas interactivos: {', '.join(p.name for p in interactivos)}")
    print("\nCobertura válida sobre el contorno del lago (%):")
    print(control_calidad.groupby("lago")["cobertura_poligono_pct"]
          .agg(["min", "median", "max"]).round(2).to_string())
    parciales = control_calidad[control_calidad["cobertura_poligono_pct"] < 80]
    if not parciales.empty:
        print("Fechas con cobertura parcial (< 80 %), a marcar en el informe:")
        print(parciales[["lago", "fecha", "cobertura_poligono_pct"]]
              .round(2).to_string(index=False))
    print("\nComparación entre lagos (ejercicio 7):")
    print(comparacion.drop(columns=["fechas_criticas_lista"]).round(2).to_string(index=False))
    print("\nFechas críticas:")
    for _, fila in comparacion.iterrows():
        print(f"  {LABELS[fila['lago']]}: {fila['fechas_criticas_lista'] or 'ninguna'}")
    print("\nCorrelaciones medianas por lago (muestra completa):")
    print(resumen_correlaciones.round(3).to_string(index=False))
    print("\nSensibilidad del umbral, porcentaje del área del lago:")
    pivote = sensibilidad.pivot_table(
        index=["lago", "fecha"], columns="umbral", values="porcentaje_area"
    ).round(2)
    print(pivote.to_string())
    print("\nPersistencia:")
    print(persistencia.round(2).to_string(index=False))
    print("\nReparto estacional (exploratorio, pocas fechas):")
    print(estacional.round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
