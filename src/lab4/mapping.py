"""Elementos cartográficos: extensión, escala, norte y reproyección a WGS84."""

from __future__ import annotations

from typing import Mapping

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from rasterio.warp import Resampling, calculate_default_transform, reproject


def raster_extent(profile: Mapping) -> tuple[float, float, float, float]:
    """Extensión en coordenadas del mapa para ``imshow``: (izq, der, abajo, arriba)."""

    left, bottom, right, top = profile["bounds"]
    return (left, right, bottom, top)


def add_scale_bar(ax: Axes, length_m: float = 2000, *, color: str = "#19313b") -> None:
    """Dibuja una barra de escala en metros sobre ejes en coordenadas proyectadas."""

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    ancho = x1 - x0
    alto = y1 - y0
    inicio_x = x0 + 0.06 * ancho
    inicio_y = y0 + 0.07 * alto
    grosor = 0.012 * alto

    ax.add_patch(Rectangle((inicio_x, inicio_y), length_m, grosor,
                           facecolor=color, edgecolor=color, zorder=6))
    ax.add_patch(Rectangle((inicio_x + length_m / 2, inicio_y), length_m / 2, grosor,
                           facecolor="white", edgecolor=color, zorder=7))
    etiqueta = f"{length_m/1000:g} km" if length_m >= 1000 else f"{length_m:g} m"
    # El desplazamiento se expresa en puntos y no en unidades del mapa: así la
    # etiqueta se separa igual de la barra en lagos de tamaños muy distintos.
    ax.annotate(
        etiqueta, xy=(inicio_x + length_m / 2, inicio_y + grosor),
        xytext=(0, 4), textcoords="offset points",
        ha="center", va="bottom", fontsize=7.5, color=color, zorder=8,
        bbox={"boxstyle": "square,pad=0.15", "facecolor": "white",
              "edgecolor": "none", "alpha": .75},
    )


def add_north_arrow(ax: Axes, *, color: str = "#19313b") -> None:
    """Flecha de norte en la esquina superior derecha, en coordenadas de ejes."""

    ax.annotate(
        "N", xy=(0.94, 0.94), xytext=(0.94, 0.82), xycoords="axes fraction",
        ha="center", va="center", fontsize=9, fontweight="bold", color=color,
        arrowprops={"arrowstyle": "-|>", "color": color, "linewidth": 1.4}, zorder=8,
    )


def format_map_axes(ax: Axes, profile: Mapping, *, scale_length_m: float = 2000) -> None:
    """Deja los ejes con coordenadas legibles, escala y norte."""

    ax.set_xlabel("Este UTM 15N (km)", fontsize=8)
    ax.set_ylabel("Norte UTM 15N (km)", fontsize=8)
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value/1000:.0f}")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value/1000:.0f}")
    ax.tick_params(labelsize=7)
    add_scale_bar(ax, scale_length_m)
    add_north_arrow(ax)


def to_wgs84(values: np.ndarray, profile: Mapping) -> tuple[np.ndarray, list[float]]:
    """Reproyecta un arreglo a EPSG:4326 y devuelve sus límites para folium.

    Folium coloca las imágenes sobre una malla de latitud y longitud, así que no
    basta con convertir las esquinas del ráster UTM: hay que remuestrear.
    """

    destino_crs = "EPSG:4326"
    transform, width, height = calculate_default_transform(
        profile["crs"], destino_crs, profile["width"], profile["height"], *profile["bounds"]
    )
    destino = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=np.asarray(values, dtype=np.float32),
        destination=destino,
        src_transform=profile["transform"],
        src_crs=profile["crs"],
        dst_transform=transform,
        dst_crs=destino_crs,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    oeste, norte = transform * (0, 0)
    este, sur = transform * (width, height)
    return destino, [[sur, oeste], [norte, este]]
