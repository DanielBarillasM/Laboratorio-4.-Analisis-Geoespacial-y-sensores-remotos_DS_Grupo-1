"""Reproduce las tablas y figuras del informe de avance (ejercicios 1--4).

Se conserva para poder regenerar exactamente lo que se entregó el 13 de agosto.
Sus resúmenes de CYA usan la media truncada a la escala 0--100, que satura en
varias fechas de Amatitlán; el análisis definitivo vive en ``analyze_full.py``.

Escribe sobre los mismos archivos que el pipeline final, así que exige ``--force``
para no revertir sin querer las tablas buenas.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lab4.analysis import (  # noqa: E402
    CYANO_DISPLAY_MAX,
    CYANO_HIGH_THRESHOLD,
    read_index_raster,
    summarize_index_raster,
)
from lab4.config import (  # noqa: E402
    FIGURES_DIR,
    RAW_DIR,
    TABLES_DIR,
    ensure_output_directories,
    load_observations,
)


COLORS = {"atitlan": "#167d9a", "amatitlan": "#d5793d"}
LABELS = {"atitlan": "Atitlán", "amatitlan": "Amatitlán"}


def date_from_name(path: Path) -> str:
    match = re.search(r"20\d{2}-\d{2}-\d{2}", path.name)
    if not match:
        raise ValueError(f"No se encontró fecha ISO en {path.name}")
    return match.group(0)


def audit_rasters(paths: list[Path]) -> pd.DataFrame:
    boundaries = gpd.read_file(ROOT / "config" / "lake_boundaries_osm.geojson").to_crs(32615)
    polygon_areas = dict(zip(boundaries["id"], boundaries.area))
    rows = []
    for path in paths:
        lake = path.parent.name
        with rasterio.open(path) as src:
            data = src.read(masked=True)
            if src.count != 3 or src.descriptions != ("NDVI", "NDWI", "CYA"):
                raise ValueError(f"Bandas inesperadas en {path}")
            valid = int(data[0].count())
            row = {
                "lago": lake,
                "fecha": date_from_name(path),
                "archivo": path.name,
                "crs": str(src.crs),
                "resolucion_m": float(src.res[0]),
                "pixeles_validos": valid,
                "cobertura_poligono_pct": min(
                    100.0, 100.0 * valid * abs(src.res[0] * src.res[1]) / polygon_areas[lake]
                ),
            }
            for index, name in enumerate(("ndvi", "ndwi", "cya")):
                values = data[index].compressed()
                row[f"{name}_min"] = float(values.min()) if values.size else np.nan
                row[f"{name}_max"] = float(values.max()) if values.size else np.nan
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["lago", "fecha"]).reset_index(drop=True)


def temporal_stats(paths: list[Path]) -> pd.DataFrame:
    frames = [
        summarize_index_raster(path, lake=path.parent.name, date=date_from_name(path))
        for path in paths
    ]
    return pd.concat(frames, ignore_index=True).sort_values(["lago", "fecha", "indice"])


def plot_temporal(cya: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    for lake, group in cya.groupby("lago"):
        group = group.sort_values("fecha")
        axes[0].plot(
            group["fecha"], group["media_truncada_0_100"], marker="o", linewidth=2.2,
            color=COLORS[lake], label=LABELS[lake],
        )
        axes[1].plot(
            group["fecha"], group["porcentaje_alto"], marker="o", linewidth=2.2,
            color=COLORS[lake], label=LABELS[lake],
        )
    axes[0].set_ylabel("CYA media, escala 0–100")
    axes[0].set_title("Evolución temporal del proxy de cianobacteria")
    axes[1].set_ylabel("Superficie válida con CYA ≥ 40 (%)")
    axes[1].set_xlabel("Fecha de adquisición")
    axes[1].set_ylim(-3, 103)
    for ax in axes:
        ax.grid(alpha=.22)
        ax.legend(frameon=False, ncol=2)
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.savefig(FIGURES_DIR / "serie_temporal_cya.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "serie_temporal_cya.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_selected_maps(paths: list[Path]) -> None:
    selected_dates = {
        "amatitlan": ["2025-01-28", "2025-04-15", "2026-04-13"],
        "atitlan": ["2025-01-18", "2025-07-17", "2026-04-13"],
    }
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    image = None
    for row, lake in enumerate(("amatitlan", "atitlan")):
        for col, observation_date in enumerate(selected_dates[lake]):
            path = next(p for p in paths if p.parent.name == lake and date_from_name(p) == observation_date)
            arrays, _ = read_index_raster(path)
            cya = np.clip(arrays["CYA"], 0, CYANO_DISPLAY_MAX)
            image = axes[row, col].imshow(cya, cmap="turbo", vmin=0, vmax=CYANO_DISPLAY_MAX)
            axes[row, col].set_title(f"{LABELS[lake]} · {observation_date}", fontweight="bold")
            axes[row, col].axis("off")
    fig.colorbar(image, ax=axes, shrink=.75, label="CYA (10³ células/ml; escala 0–100)")
    fig.suptitle("Distribución espacial en fechas representativas", fontsize=16, fontweight="bold")
    fig.savefig(FIGURES_DIR / "mapas_cya_seleccion.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "mapas_cya_seleccion.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Confirma que se quiere volver a las tablas del avance, con la media truncada.",
    )
    if not parser.parse_args().force:
        raise SystemExit(
            "Este script regenera las tablas del avance y sobrescribiría las del análisis "
            "final. Use `python scripts/analyze_full.py` para el análisis completo, "
            "o repita con --force si de verdad quiere reproducir el avance."
        )

    ensure_output_directories()
    paths = sorted(RAW_DIR.glob("*/*.tif"))
    if len(paths) != 22:
        raise RuntimeError(f"Se esperaban 22 GeoTIFF; se encontraron {len(paths)}")
    official = load_observations()
    expected = set(zip(official["lago"], official["fecha"].dt.strftime("%Y-%m-%d")))
    found = {(path.parent.name, date_from_name(path)) for path in paths}
    if found != expected:
        raise RuntimeError(f"Diferencia entre fechas oficiales y descargas: {expected ^ found}")

    audit = audit_rasters(paths)
    stats = temporal_stats(paths)
    audit.to_csv(TABLES_DIR / "control_calidad_rasters.csv", index=False)
    stats.to_csv(TABLES_DIR / "estadisticas_indices.csv", index=False)

    cya = stats.query("indice == 'CYA'").copy()
    cya["fecha"] = pd.to_datetime(cya["fecha"])
    cya.to_csv(TABLES_DIR / "serie_temporal_cya.csv", index=False)
    plot_temporal(cya)
    plot_selected_maps(paths)

    peaks = cya.loc[
        cya.groupby("lago")["media_truncada_0_100"].idxmax(),
        ["lago", "fecha", "media_truncada_0_100", "porcentaje_alto"],
    ]
    print(f"GeoTIFF auditados: {len(paths)}")
    print("Cobertura estimada por polígono (%):")
    print(audit.groupby("lago")["cobertura_poligono_pct"].agg(["min", "median", "max"]).round(2))
    print("Picos provisionales (CYA truncada a escala 0–100):")
    print(peaks.to_string(index=False))


if __name__ == "__main__":
    main()
