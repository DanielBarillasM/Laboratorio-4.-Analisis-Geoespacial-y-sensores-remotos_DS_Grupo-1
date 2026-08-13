"""Cálculos locales, control de calidad y resúmenes estadísticos."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
import rasterio


CYANO_HIGH_THRESHOLD = 40.0
"""Umbral exploratorio basado en la escala visual de Se2WaQ (10^3 células/ml)."""

CYANO_DISPLAY_MAX = 100.0
"""Límite superior de la escala CYA publicada por Se2WaQ."""


def _safe_normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denominator = a + b
    result = np.full(np.broadcast_shapes(a.shape, b.shape), np.nan, dtype=np.float32)
    np.divide(a - b, denominator, out=result, where=denominator != 0)
    return result


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Índice de vegetación: (B08 - B04) / (B08 + B04)."""

    return _safe_normalized_difference(nir, red)


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Índice de agua de McFeeters: (B03 - B08) / (B03 + B08)."""

    return _safe_normalized_difference(green, nir)


def cyano_se2waq(blue: np.ndarray, green: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Proxy Se2WaQ de cianobacteria en 10^3 células/ml usando reflectancia 0--1.

    Fórmula de Potes et al. (2018), publicada en el script Se2WaQ de Sentinel Hub.
    Se marca como inválido todo píxel cuya reflectancia azul sea no positiva.
    """

    blue = np.asarray(blue, dtype=np.float32)
    green = np.asarray(green, dtype=np.float32)
    red = np.asarray(red, dtype=np.float32)
    ratio = np.full(np.broadcast_shapes(blue.shape, green.shape, red.shape), np.nan, dtype=np.float32)
    np.divide(green * red, blue, out=ratio, where=blue > 0)
    with np.errstate(invalid="ignore", over="ignore"):
        result = 115_530.31 * np.power(ratio, 2.38)
    return result.astype(np.float32)


def describe_values(values: np.ndarray) -> dict[str, float | int]:
    """Resume valores finitos sin convertir NoData en ceros."""

    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {
            "n_pixeles": 0,
            "media": np.nan,
            "mediana": np.nan,
            "desviacion": np.nan,
            "p90": np.nan,
            "minimo": np.nan,
            "maximo": np.nan,
        }
    return {
        "n_pixeles": int(finite.size),
        "media": float(np.mean(finite)),
        "mediana": float(np.median(finite)),
        "desviacion": float(np.std(finite)),
        "p90": float(np.percentile(finite, 90)),
        "minimo": float(np.min(finite)),
        "maximo": float(np.max(finite)),
    }


def read_index_raster(path: str | Path) -> tuple[dict[str, np.ndarray], Mapping]:
    """Lee un GeoTIFF de tres bandas en el orden NDVI, NDWI y CYA."""

    path = Path(path)
    with rasterio.open(path) as src:
        if src.count < 3:
            raise ValueError(f"{path} contiene {src.count} bandas; se esperaban al menos 3")
        masked = src.read([1, 2, 3], masked=True).astype(np.float32)
        arrays = {
            "NDVI": masked[0].filled(np.nan),
            "NDWI": masked[1].filled(np.nan),
            "CYA": masked[2].filled(np.nan),
        }
        profile = src.profile.copy()
        profile["bounds"] = tuple(src.bounds)
        profile["descriptions"] = src.descriptions
    return arrays, profile


def summarize_index_raster(
    path: str | Path,
    *,
    lake: str,
    date: str,
    high_threshold: float = CYANO_HIGH_THRESHOLD,
) -> pd.DataFrame:
    """Genera una fila larga por índice y una métrica de extensión de floración."""

    arrays, _ = read_index_raster(path)
    rows: list[dict[str, float | int | str]] = []
    for index_name, values in arrays.items():
        raw_values = values
        if index_name == "CYA":
            # La escala visual publicada por Se2WaQ termina en 100. El ráster
            # crudo se conserva, pero el resumen principal evita que cocientes
            # inestables por reflectancia azul pequeña dominen la media.
            values = np.clip(values, 0, CYANO_DISPLAY_MAX)
        row: dict[str, float | int | str] = {
            "lago": lake,
            "fecha": date,
            "indice": index_name,
        }
        row.update(describe_values(values))
        if index_name == "CYA":
            finite = raw_values[np.isfinite(raw_values)]
            row["porcentaje_alto"] = (
                float(100 * np.mean(finite >= high_threshold)) if finite.size else np.nan
            )
            row["umbral_alto"] = high_threshold
            row["porcentaje_saturado_100"] = (
                float(100 * np.mean(finite >= CYANO_DISPLAY_MAX)) if finite.size else np.nan
            )
            row["maximo_crudo"] = float(np.max(finite)) if finite.size else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
