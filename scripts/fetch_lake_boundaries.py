"""Obtiene los contornos del espejo de agua desde OpenStreetMap/Nominatim.

La guía del laboratorio permite delimitar cada lago con las coordenadas provistas o
con un GeoJSON. Aquí se usan las cajas envolventes de la guía para consultar
Copernicus y estos contornos de OpenStreetMap para recortar el espejo de agua y
calcular áreas, de modo que el recorte sea reproducible por cualquier integrante.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "config" / "lake_boundaries_osm.geojson"
RELATIONS = {5781818: "atitlan", 11018382: "amatitlan"}

response = requests.get(
    "https://nominatim.openstreetmap.org/lookup",
    params={
        "osm_ids": ",".join(f"R{relation}" for relation in RELATIONS),
        "format": "geojson",
        "polygon_geojson": 1,
    },
    headers={"User-Agent": "UVG-CC3084-Lab4/0.1 (academic project)"},
    timeout=60,
)
response.raise_for_status()
payload = response.json()
features = []
for feature in payload["features"]:
    relation = int(feature["properties"]["osm_id"])
    if relation not in RELATIONS:
        continue
    key = RELATIONS[relation]
    features.append(
        {
            "type": "Feature",
            "properties": {
                "id": key,
                "nombre": f"Lago de {key.capitalize()}",
                "fuente": "OpenStreetMap contributors via Nominatim",
                "licencia": "ODbL 1.0",
                "osm_relation_id": relation,
                "uso": "recorte_del_espejo_de_agua_y_calculo_de_area",
            },
            "geometry": feature["geometry"],
        }
    )
if {feature["properties"]["id"] for feature in features} != set(RELATIONS.values()):
    raise RuntimeError("Nominatim no devolvió ambos contornos esperados")

collection = {
    "type": "FeatureCollection",
    "name": "contornos_lagos_osm",
    "licence": payload.get("licence"),
    "features": sorted(features, key=lambda feature: feature["properties"]["id"]),
}
OUTPUT.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUTPUT)
