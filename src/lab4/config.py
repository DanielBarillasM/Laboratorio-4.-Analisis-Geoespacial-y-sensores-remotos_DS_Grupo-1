"""Configuración única de áreas, fechas y rutas del estudio."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "cdse"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"


@dataclass(frozen=True)
class StudyArea:
    """Caja oficial suministrada en la guía del laboratorio."""

    key: str
    name: str
    west: float
    east: float
    south: float
    north: float

    @property
    def extent(self) -> dict[str, float | str]:
        return {
            "west": self.west,
            "east": self.east,
            "south": self.south,
            "north": self.north,
            "crs": "EPSG:4326",
        }


AREAS = {
    "atitlan": StudyArea(
        key="atitlan",
        name="Lago de Atitlán",
        west=-91.326256,
        east=-91.071510,
        south=14.594800,
        north=14.750979,
    ),
    "amatitlan": StudyArea(
        key="amatitlan",
        name="Lago de Amatitlán",
        west=-90.638065,
        east=-90.512924,
        south=14.412347,
        north=14.493799,
    ),
}


def load_observations() -> pd.DataFrame:
    """Carga las 22 observaciones oficiales y valida su estructura mínima."""

    observations = pd.read_csv(CONFIG_DIR / "observaciones.csv", parse_dates=["fecha"])
    expected = {"lago", "fecha", "nubosidad_pct", "satelite"}
    missing = expected.difference(observations.columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
    counts = observations.groupby("lago").size().to_dict()
    if counts != {"amatitlan": 11, "atitlan": 11}:
        raise ValueError(f"Se esperaban 11 fechas por lago; se obtuvo {counts}")
    return observations.sort_values(["lago", "fecha"]).reset_index(drop=True)


def load_lake_geometry(lake: str) -> dict:
    """Devuelve un FeatureCollection de un lago para `filter_spatial` de openEO."""

    if lake not in AREAS:
        raise KeyError(f"Lago desconocido: {lake}. Opciones: {sorted(AREAS)}")
    path = CONFIG_DIR / "lake_boundaries_osm.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Ejecute `python scripts/fetch_lake_boundaries.py`."
        )
    collection = json.loads(path.read_text(encoding="utf-8-sig"))
    features = [f for f in collection["features"] if f["properties"].get("id") == lake]
    if len(features) != 1:
        raise ValueError(f"Se esperaba un contorno para {lake}; se encontraron {len(features)}")
    return {"type": "FeatureCollection", "features": features}


def ensure_output_directories() -> None:
    """Crea únicamente directorios locales ignorados o destinados a resultados."""

    for directory in (RAW_DIR, PROCESSED_DIR, FIGURES_DIR, TABLES_DIR):
        directory.mkdir(parents=True, exist_ok=True)
