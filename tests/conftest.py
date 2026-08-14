"""Rásteres sintéticos para probar el análisis sin depender de las descargas."""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


PIXEL_M = 20.0
SHAPE = (10, 10)


def write_index_raster(path, ndvi, ndwi, cya):
    """Escribe un GeoTIFF de tres bandas con la misma estructura que openEO."""

    profile = {
        "driver": "GTiff",
        "height": SHAPE[0],
        "width": SHAPE[1],
        "count": 3,
        "dtype": "float32",
        "crs": "EPSG:32615",
        "transform": from_origin(700000, 1630000, PIXEL_M, PIXEL_M),
        "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as dst:
        for band, values in enumerate((ndvi, ndwi, cya), start=1):
            dst.write(np.asarray(values, dtype=np.float32), band)
        dst.descriptions = ("NDVI", "NDWI", "CYA")
    return path


@pytest.fixture
def pixel_area_m2():
    return PIXEL_M * PIXEL_M


@pytest.fixture
def lake_area_m2():
    """Área de un lago sintético: el doble de la rejilla, así la cobertura es 50 %."""

    return 2 * SHAPE[0] * SHAPE[1] * PIXEL_M * PIXEL_M


@pytest.fixture
def saturated_raster(tmp_path):
    """Imita una fecha de Amatitlán: la mitad del agua por encima de la escala.

    Cincuenta píxeles valen 500 (muy por encima del techo de 100) y cincuenta
    valen 5. La media cruda es 252.5 y la truncada 52.5, una diferencia que la
    serie temporal debe poder mostrar.
    """

    cya = np.full(SHAPE, 5.0, dtype=np.float32)
    cya[:5, :] = 500.0
    ndwi = np.full(SHAPE, 0.4, dtype=np.float32)
    ndvi = np.full(SHAPE, -0.2, dtype=np.float32)
    return write_index_raster(tmp_path / "openEO_2026-04-13Z.tif", ndvi, ndwi, cya)


@pytest.fixture
def partial_raster(tmp_path):
    """Imita una fecha con nubes: la mitad de la rejilla es NoData."""

    cya = np.full(SHAPE, 60.0, dtype=np.float32)
    cya[5:, :] = np.nan
    ndwi = np.where(np.isnan(cya), np.nan, 0.3).astype(np.float32)
    ndvi = np.where(np.isnan(cya), np.nan, -0.1).astype(np.float32)
    return write_index_raster(tmp_path / "openEO_2026-02-07Z.tif", ndvi, ndwi, cya)
