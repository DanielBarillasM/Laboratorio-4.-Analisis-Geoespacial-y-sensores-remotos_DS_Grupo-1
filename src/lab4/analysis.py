"""Cálculos locales, control de calidad y resúmenes estadísticos."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import rasterio
from scipy import stats as scipy_stats


CYANO_HIGH_THRESHOLD = 40.0
"""Umbral de CYA alta, en 10^3 células/ml.

No es una decisión arbitraria del grupo: 40 es uno de los cortes de la rampa de
color publicada en el script Se2WaQ, ``scaleCya = [0, 10, 20, 40, 50, 100]``, y es
el punto donde esa rampa pasa a los tonos rojos. Tampoco es un límite sanitario.
Por eso todos los productos se acompañan de un análisis de sensibilidad con
:data:`CYANO_THRESHOLDS`.
"""

CYANO_THRESHOLDS = (20.0, 40.0, 60.0)
"""Umbrales para la sensibilidad: el corte usado y sus vecinos en la rampa."""

CYANO_DISPLAY_MAX = 100.0
"""Techo de la escala CYA publicada por Se2WaQ.

Sirve para *visualizar* con la misma rampa que el script original. No debe usarse
para resumir: en varias fechas de Amatitlán más de la mitad del espejo de agua
supera este valor, y al truncar, la media deja de medir intensidad y solo mide
qué proporción se saturó.
"""


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
    Fuente oficial verificada:
    https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/se2waq/
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


_PERCENTILES = (10, 25, 75, 90, 95, 99)


def trimmed_mean(values: np.ndarray, proportion: float = 0.1) -> float:
    """Media recortada: descarta una fracción en cada cola antes de promediar.

    Es la medida central que resiste tanto los cocientes disparados por
    reflectancia azul pequeña como la saturación de la escala publicada.
    """

    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return float("nan")
    if not 0 <= proportion < 0.5:
        raise ValueError(f"La proporción recortada debe estar en [0, 0.5); se recibió {proportion}")
    low, high = np.percentile(finite, [100 * proportion, 100 * (1 - proportion)])
    core = finite[(finite >= low) & (finite <= high)]
    return float(np.mean(core if core.size else finite))


def describe_values(values: np.ndarray) -> dict[str, float | int]:
    """Resume valores finitos sin convertir NoData en ceros."""

    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    keys = ["media", "mediana", "desviacion", *(f"p{p}" for p in _PERCENTILES), "minimo", "maximo"]
    if finite.size == 0:
        return {"n_pixeles": 0, **{key: np.nan for key in keys}}
    percentiles = np.percentile(finite, _PERCENTILES)
    return {
        "n_pixeles": int(finite.size),
        "media": float(np.mean(finite)),
        "mediana": float(np.median(finite)),
        "desviacion": float(np.std(finite)),
        **{f"p{p}": float(value) for p, value in zip(_PERCENTILES, percentiles)},
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
    lake_area_m2: float | None = None,
) -> pd.DataFrame:
    """Genera una fila larga por índice y métricas de extensión de floración.

    Para CYA las columnas centrales (``media``, ``mediana``, percentiles) se
    calculan sobre el valor **crudo**. La media truncada a la escala 0--100 se
    conserva aparte, en ``media_truncada_0_100``, acompañada siempre de
    ``porcentaje_saturado_100`` para que se vea cuándo deja de ser informativa.

    Si se indica ``lake_area_m2`` se añade ``porcentaje_area_alto``: la fracción
    del lago completo con CYA alta, que es lo que pide el ejercicio 8.1. Sin ese
    dato solo puede reportarse ``porcentaje_alto``, referido a los píxeles
    válidos de la fecha, que sobreestima cuando la cobertura es parcial.
    """

    arrays, profile = read_index_raster(path)
    pixel_area_m2 = abs(profile["transform"].a * profile["transform"].e)
    rows: list[dict[str, float | int | str]] = []
    for index_name, values in arrays.items():
        row: dict[str, float | int | str] = {
            "lago": lake,
            "fecha": date,
            "indice": index_name,
        }
        row.update(describe_values(values))
        if index_name == "CYA":
            finite = values[np.isfinite(values)]
            row["media_recortada_10"] = trimmed_mean(finite, 0.1)
            row["media_truncada_0_100"] = (
                float(np.mean(np.clip(finite, 0, CYANO_DISPLAY_MAX))) if finite.size else np.nan
            )
            row["porcentaje_saturado_100"] = (
                float(100 * np.mean(finite >= CYANO_DISPLAY_MAX)) if finite.size else np.nan
            )
            row["umbral_alto"] = high_threshold
            row["porcentaje_alto"] = (
                float(100 * np.mean(finite >= high_threshold)) if finite.size else np.nan
            )
            row["area_valida_km2"] = finite.size * pixel_area_m2 / 1e6
            if lake_area_m2:
                row["cobertura_valida_pct"] = 100 * finite.size * pixel_area_m2 / lake_area_m2
                row["porcentaje_area_alto"] = (
                    100 * float(np.sum(finite >= high_threshold)) * pixel_area_m2 / lake_area_m2
                )
        rows.append(row)
    return pd.DataFrame(rows)


def threshold_sensitivity(
    values: np.ndarray,
    *,
    lake: str,
    date: str,
    thresholds: Sequence[float] = CYANO_THRESHOLDS,
    pixel_area_m2: float,
    lake_area_m2: float | None = None,
) -> pd.DataFrame:
    """Repite la métrica de extensión con varios umbrales de CYA alta.

    Permite mostrar que la comparación entre lagos y fechas no depende de haber
    elegido 40 como corte.
    """

    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    rows = []
    for threshold in thresholds:
        above = int(np.sum(finite >= threshold)) if finite.size else 0
        row = {
            "lago": lake,
            "fecha": date,
            "umbral": float(threshold),
            "pixeles_sobre_umbral": above,
            "porcentaje_valido": 100 * above / finite.size if finite.size else np.nan,
            "area_sobre_umbral_km2": above * pixel_area_m2 / 1e6,
        }
        if lake_area_m2:
            row["porcentaje_area"] = 100 * above * pixel_area_m2 / lake_area_m2
        rows.append(row)
    return pd.DataFrame(rows)


CORRELATION_PAIRS = (("CYA", "NDVI"), ("CYA", "NDWI"))


def spatial_subsample_mask(shape: tuple[int, int], step: int) -> np.ndarray:
    """Rejilla regular que conserva un píxel de cada ``step`` en ambos ejes.

    Los píxeles vecinos de un lago no son observaciones independientes: comparten
    masa de agua, viento y sombra. Correlacionar cientos de miles de píxeles
    contiguos hace que cualquier valor de p resulte diminuto sin que eso indique
    una relación fuerte. Repetir la correlación sobre una submuestra separada en
    el espacio permite mostrar si el coeficiente se sostiene.
    """

    if step < 1:
        raise ValueError(f"El paso debe ser mayor o igual que 1; se recibió {step}")
    mask = np.zeros(shape, dtype=bool)
    mask[::step, ::step] = True
    return mask


def correlate_indices(
    arrays: Mapping[str, np.ndarray],
    *,
    lake: str,
    date: str,
    pairs: Sequence[tuple[str, str]] = CORRELATION_PAIRS,
    subsample_step: int | None = 5,
) -> pd.DataFrame:
    """Correlaciona CYA con NDVI y NDWI mediante Pearson y Spearman.

    Se reportan tres coeficientes por par. Pearson sobre el valor crudo de CYA es
    el más sensible a los cocientes extremos; Pearson sobre ``log10(CYA)`` mide la
    relación en la escala en que el índice varía realmente; Spearman solo usa el
    orden y no cambia al transformar. Además se repite todo sobre una submuestra
    espacial, cuyo tamaño se informa en ``n``.
    """

    rows: list[dict[str, object]] = []
    for first, second in pairs:
        base = np.isfinite(arrays[first]) & np.isfinite(arrays[second])
        muestras = {"completa": base}
        if subsample_step and subsample_step > 1:
            muestras["submuestra"] = base & spatial_subsample_mask(base.shape, subsample_step)
        for muestra, selection in muestras.items():
            x = np.asarray(arrays[first], dtype=np.float64)[selection]
            y = np.asarray(arrays[second], dtype=np.float64)[selection]
            positivos = x > 0
            variantes = {
                "pearson": (x, y),
                "pearson_log10": (np.log10(x[positivos]), y[positivos]),
                "spearman": (x, y),
            }
            for metodo, (a, b) in variantes.items():
                if a.size < 3 or np.all(a == a[0]) or np.all(b == b[0]):
                    coeficiente, p_valor = np.nan, np.nan
                elif metodo == "spearman":
                    coeficiente, p_valor = scipy_stats.spearmanr(a, b)
                else:
                    coeficiente, p_valor = scipy_stats.pearsonr(a, b)
                rows.append({
                    "lago": lake,
                    "fecha": date,
                    "par": f"{first}~{second}",
                    "metodo": metodo,
                    "muestra": muestra,
                    "n": int(a.size),
                    "coeficiente": float(coeficiente),
                    "p_valor": float(p_valor),
                })
    return pd.DataFrame(rows)


def stack_lake_rasters(
    paths: Sequence[tuple[str, Path]],
) -> tuple[list[str], dict[str, np.ndarray], Mapping]:
    """Apila las fechas de un lago comprobando que compartan la misma rejilla.

    Devuelve las fechas ordenadas, un diccionario índice -> cubo (fecha, y, x) y
    el perfil común. Los mapas de persistencia y de diferencia solo tienen sentido
    si cada píxel corresponde al mismo punto en todas las fechas.
    """

    ordenadas = sorted(paths, key=lambda item: item[0])
    fechas: list[str] = []
    por_indice: dict[str, list[np.ndarray]] = {"NDVI": [], "NDWI": [], "CYA": []}
    referencia: Mapping | None = None
    for date, path in ordenadas:
        arrays, profile = read_index_raster(path)
        if referencia is None:
            referencia = profile
        else:
            actual = (profile["width"], profile["height"], profile["transform"], profile["crs"])
            esperado = (
                referencia["width"], referencia["height"],
                referencia["transform"], referencia["crs"],
            )
            if actual != esperado:
                raise ValueError(
                    f"{path} no comparte rejilla con {ordenadas[0][1]}. "
                    "Vuelva a generar la serie del lago con la misma extensión y resolución."
                )
        fechas.append(date)
        for nombre, valores in arrays.items():
            por_indice[nombre].append(valores)
    if referencia is None:
        raise ValueError("No se recibió ninguna fecha para apilar")
    cubos = {nombre: np.stack(capas) for nombre, capas in por_indice.items()}
    return fechas, cubos, referencia


def persistence_fraction(
    cube: np.ndarray,
    threshold: float = CYANO_HIGH_THRESHOLD,
    *,
    min_observations: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Proporción de observaciones válidas en que cada píxel supera el umbral.

    El denominador es el número de fechas en que ese píxel fue observado, no el
    número total de fechas: así una orilla tapada por nubes la mitad del tiempo no
    aparece como zona sin floración. Los píxeles con menos de
    ``min_observations`` observaciones quedan como NaN.
    """

    valid = np.isfinite(cube)
    n_valid = valid.sum(axis=0)
    above = np.where(valid, cube >= threshold, False).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        fraction = np.where(n_valid >= max(1, min_observations), above / n_valid, np.nan)
    return fraction.astype(np.float32), n_valid.astype(np.int16)


def difference_map(later: np.ndarray, earlier: np.ndarray) -> np.ndarray:
    """Diferencia píxel a píxel entre dos fechas, con NaN donde falte cualquiera."""

    later = np.asarray(later, dtype=np.float32)
    earlier = np.asarray(earlier, dtype=np.float32)
    if later.shape != earlier.shape:
        raise ValueError(f"Formas incompatibles: {later.shape} y {earlier.shape}")
    return np.where(np.isfinite(later) & np.isfinite(earlier), later - earlier, np.nan)


def season_of(date: str) -> str:
    """Clasifica una fecha en la estación seca o lluviosa de Guatemala.

    En el altiplano y el valle central la temporada lluviosa va de mayo a octubre
    y la seca de noviembre a abril. Con once fechas irregulares por lago esta
    etiqueta sirve para explorar, no para afirmar un ciclo estacional.
    """

    month = int(str(date)[5:7])
    return "lluviosa" if 5 <= month <= 10 else "seca"
