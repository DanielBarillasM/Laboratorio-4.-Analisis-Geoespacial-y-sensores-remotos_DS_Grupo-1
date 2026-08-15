"""Construcción de cubos openEO para Copernicus Data Space Ecosystem.

Colección: Sentinel-2 L2A. El proxy de cianobacteria (CYA) se calcula con la
fórmula del script oficial Se2WaQ de Sentinel Hub —
https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/se2waq/ —
implementada en ``lab4.analysis.cyano_se2waq``. Las bandas B02/B03/B04 se
convierten a reflectancia (``REFLECTANCE_SCALE``) antes de aplicarla, tal como
exige el evalscript original.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

import openeo
from openeo.rest.connection import Connection
from openeo.rest.datacube import DataCube

from .config import AREAS, StudyArea, load_course_geometry, load_lake_geometry


OPENEO_URL = "https://openeo.dataspace.copernicus.eu"
COLLECTION = "SENTINEL2_L2A"
REFLECTANCE_SCALE = 0.0001
SPECTRAL_BANDS = ["B02", "B03", "B04", "B08"]
INVALID_SCL_CLASSES = [0, 1, 3, 8, 9, 10, 11]


def connect_cdse() -> Connection:
    """Abre una conexión todavía no autenticada al backend oficial."""

    return openeo.connect(OPENEO_URL)


def authenticate_cdse(
    connection: Connection,
    *,
    max_poll_time: float = 900,
) -> Connection:
    """Autentica mediante código de dispositivo sin recibir ni guardar contraseñas."""

    return connection.authenticate_oidc_device(
        store_refresh_token=False,
        max_poll_time=max_poll_time,
    )


def _as_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def one_day_extent(value: str | date | datetime) -> list[str]:
    """Intervalo semiabierto de un día para seleccionar una adquisición oficial."""

    start = _as_date(value)
    return [start.isoformat(), (start + timedelta(days=1)).isoformat()]


def _invalid_scl_mask(scl: DataCube) -> DataCube:
    scl_values = scl.band("SCL")
    invalid = scl_values == INVALID_SCL_CLASSES[0]
    for scl_class in INVALID_SCL_CLASSES[1:]:
        invalid = invalid | (scl_values == scl_class)
    return invalid


def build_daily_indices_cube(
    connection: Connection,
    area: StudyArea,
    observation_date: str | date | datetime,
    *,
    resolution: float = 20,
) -> DataCube:
    """Construye NDVI, NDWI y CYA para una fecha sin descargar bandas crudas.

    La separación agua-fondo reproduce la decisión de Se2WaQ: NDWI >= 0.
    También excluye clases SCL inválidas/nubosas y reflectancia azul no positiva.
    """

    temporal_extent = one_day_extent(observation_date)
    data = connection.load_collection(
        COLLECTION,
        spatial_extent=area.extent,
        temporal_extent=temporal_extent,
        bands=[*SPECTRAL_BANDS, "SCL"],
        max_cloud_cover=100,
    ).filter_spatial(load_course_geometry(area.key)).filter_spatial(
        load_lake_geometry(area.key)
    ).resample_spatial(
        resolution=resolution, method="near"
    )

    blue = data.band("B02") * REFLECTANCE_SCALE
    green = data.band("B03") * REFLECTANCE_SCALE
    red = data.band("B04") * REFLECTANCE_SCALE
    nir = data.band("B08") * REFLECTANCE_SCALE

    ndvi_values = (nir - red) / (nir + red)
    ndwi_values = (green - nir) / (green + nir)
    cya_values = 115_530.31 * (((green * red) / blue) ** 2.38)

    nonpositive_reflectance = (blue <= 0) | (green <= 0) | (red <= 0) | (nir <= 0)
    invalid = _invalid_scl_mask(data) | nonpositive_reflectance | (ndwi_values < 0)
    ndvi_cube = ndvi_values.mask(invalid).add_dimension("bands", "NDVI", type="bands")
    ndwi_cube = ndwi_values.mask(invalid).add_dimension("bands", "NDWI", type="bands")
    cya_cube = cya_values.mask(invalid).add_dimension("bands", "CYA", type="bands")
    return ndvi_cube.merge_cubes(ndwi_cube).merge_cubes(cya_cube)


def build_lake_timeseries_cube(
    connection: Connection,
    lake: str,
    dates: Iterable[str | date | datetime],
    *,
    resolution: float = 20,
) -> DataCube:
    """Concatena únicamente las fechas oficiales de un lago."""

    if lake not in AREAS:
        raise KeyError(f"Lago desconocido: {lake}. Opciones: {sorted(AREAS)}")
    cubes = [
        build_daily_indices_cube(connection, AREAS[lake], value, resolution=resolution)
        for value in dates
    ]
    if not cubes:
        raise ValueError("La lista de fechas está vacía")
    merged = cubes[0]
    for cube in cubes[1:]:
        merged = merged.merge_cubes(cube, overlap_resolver="max")
    return merged
