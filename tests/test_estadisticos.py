"""Pruebas de los estadísticos que sostienen los ejercicios 4 a 8."""

from __future__ import annotations

import numpy as np
import pytest

from lab4.analysis import (
    CYANO_HIGH_THRESHOLD,
    correlate_indices,
    difference_map,
    persistence_fraction,
    season_of,
    spatial_subsample_mask,
    stack_lake_rasters,
    summarize_index_raster,
    threshold_sensitivity,
    trimmed_mean,
)

from conftest import SHAPE, write_index_raster


def test_la_media_cruda_no_queda_truncada_por_la_escala(saturated_raster):
    """La media publicada debe distinguir 500 de 100; la truncada no puede."""

    stats = summarize_index_raster(saturated_raster, lake="amatitlan", date="2026-04-13")
    cya = stats.query("indice == 'CYA'").iloc[0]

    assert cya["media"] == pytest.approx(252.5)
    assert cya["media_truncada_0_100"] == pytest.approx(52.5)
    assert cya["porcentaje_saturado_100"] == pytest.approx(50.0)
    assert cya["maximo"] == pytest.approx(500.0)


def test_la_mediana_saturada_delata_el_problema(saturated_raster):
    """Con la escala truncada la mediana se pega al techo y pierde información."""

    arrays_stats = summarize_index_raster(saturated_raster, lake="amatitlan", date="2026-04-13")
    cruda = arrays_stats.query("indice == 'CYA'").iloc[0]["mediana"]
    truncada = np.median(np.clip([500.0] * 50 + [5.0] * 50, 0, 100))

    assert cruda == pytest.approx(252.5)  # promedio de los dos valores centrales
    assert truncada == pytest.approx(52.5)


def test_media_recortada_ignora_las_colas():
    valores = np.array([1.0, 2.0, 3.0, 4.0, 1000.0])
    assert trimmed_mean(valores, 0.2) == pytest.approx(3.0)
    assert trimmed_mean(valores, 0.0) == pytest.approx(202.0)


def test_media_recortada_rechaza_proporciones_invalidas():
    with pytest.raises(ValueError, match="proporción recortada"):
        trimmed_mean(np.arange(10.0), 0.5)


def test_porcentaje_sobre_area_del_lago_difiere_del_porcentaje_valido(
    partial_raster, lake_area_m2
):
    """Con media rejilla nublada, el 100 % del agua vista es el 25 % del lago."""

    stats = summarize_index_raster(
        partial_raster, lake="amatitlan", date="2026-02-07", lake_area_m2=lake_area_m2
    )
    cya = stats.query("indice == 'CYA'").iloc[0]

    assert cya["porcentaje_alto"] == pytest.approx(100.0)
    assert cya["cobertura_valida_pct"] == pytest.approx(25.0)
    assert cya["porcentaje_area_alto"] == pytest.approx(25.0)


def test_nodata_no_se_cuenta_como_cero(partial_raster):
    """Los píxeles enmascarados quedan fuera del conteo, no valen 0."""

    stats = summarize_index_raster(partial_raster, lake="amatitlan", date="2026-02-07")
    cya = stats.query("indice == 'CYA'").iloc[0]

    assert cya["n_pixeles"] == SHAPE[0] * SHAPE[1] // 2
    assert cya["media"] == pytest.approx(60.0)
    assert cya["minimo"] == pytest.approx(60.0)


def test_sensibilidad_del_umbral_es_monotona(pixel_area_m2, lake_area_m2):
    valores = np.array([10.0, 30.0, 50.0, 70.0, np.nan])
    tabla = threshold_sensitivity(
        valores, lake="atitlan", date="2026-04-13",
        pixel_area_m2=pixel_area_m2, lake_area_m2=lake_area_m2,
    )

    porcentajes = tabla.set_index("umbral")["porcentaje_valido"]
    assert porcentajes[20.0] == pytest.approx(75.0)
    assert porcentajes[40.0] == pytest.approx(50.0)
    assert porcentajes[60.0] == pytest.approx(25.0)
    assert tabla["porcentaje_valido"].is_monotonic_decreasing


def test_persistencia_usa_observaciones_validas_como_denominador():
    """Una fecha nublada no debe contar como fecha sin floración."""

    cube = np.array([
        [[100.0, 100.0]],
        [[100.0, np.nan]],
        [[0.0, np.nan]],
    ], dtype=np.float32)

    fraccion, n_valid = persistence_fraction(cube, CYANO_HIGH_THRESHOLD)

    np.testing.assert_allclose(fraccion[0], [2 / 3, 1.0])
    np.testing.assert_array_equal(n_valid[0], [3, 1])


def test_persistencia_marca_pixeles_sin_observaciones():
    cube = np.full((3, 1, 1), np.nan, dtype=np.float32)
    fraccion, n_valid = persistence_fraction(cube)

    assert np.isnan(fraccion[0, 0])
    assert n_valid[0, 0] == 0


def test_mapa_de_diferencia_propaga_nodata():
    later = np.array([[10.0, np.nan]], dtype=np.float32)
    earlier = np.array([[4.0, 1.0]], dtype=np.float32)

    resultado = difference_map(later, earlier)

    assert resultado[0, 0] == pytest.approx(6.0)
    assert np.isnan(resultado[0, 1])


def test_correlacion_reporta_pearson_spearman_y_tamano_de_muestra():
    """Con una relación monótona pero curva, Spearman debe superar a Pearson."""

    x = np.linspace(1, 10, 100).reshape(10, 10)
    arrays = {"CYA": x**3, "NDVI": x, "NDWI": -x}

    tabla = correlate_indices(arrays, lake="atitlan", date="2026-04-13", subsample_step=None)
    completa = tabla.query("muestra == 'completa'").set_index(["par", "metodo"])["coeficiente"]

    assert completa[("CYA~NDVI", "spearman")] == pytest.approx(1.0)
    assert completa[("CYA~NDVI", "pearson")] < completa[("CYA~NDVI", "spearman")]
    assert completa[("CYA~NDWI", "spearman")] == pytest.approx(-1.0)
    assert set(tabla["n"]) == {100}


def test_correlacion_submuestreada_reduce_el_numero_de_observaciones():
    x = np.linspace(1, 10, 100).reshape(10, 10)
    arrays = {"CYA": x, "NDVI": x, "NDWI": -x}

    tabla = correlate_indices(arrays, lake="atitlan", date="2026-04-13", subsample_step=5)

    assert tabla.query("muestra == 'completa'")["n"].max() == 100
    assert tabla.query("muestra == 'submuestra'")["n"].max() == 4


def test_correlacion_ignora_pixeles_sin_datos():
    arrays = {
        "CYA": np.array([[1.0, 2.0, np.nan]]),
        "NDVI": np.array([[1.0, 2.0, 3.0]]),
        "NDWI": np.array([[1.0, np.nan, 3.0]]),
    }

    tabla = correlate_indices(arrays, lake="atitlan", date="2026-04-13", subsample_step=None)

    assert tabla.query("par == 'CYA~NDVI'")["n"].max() == 2
    assert tabla.query("par == 'CYA~NDWI'")["n"].max() == 1


def test_submuestra_espacial_toma_una_rejilla_regular():
    mask = spatial_subsample_mask((10, 10), 5)
    assert mask.sum() == 4
    assert mask[0, 0] and mask[5, 5]
    assert not mask[1, 1]


def test_apilado_rechaza_rejillas_incompatibles(tmp_path):
    buena = write_index_raster(
        tmp_path / "openEO_2026-01-01Z.tif",
        np.zeros(SHAPE), np.zeros(SHAPE), np.ones(SHAPE),
    )
    import rasterio
    from rasterio.transform import from_origin

    otra = tmp_path / "openEO_2026-02-01Z.tif"
    with rasterio.open(
        otra, "w", driver="GTiff", height=5, width=5, count=3, dtype="float32",
        crs="EPSG:32615", transform=from_origin(700000, 1630000, 20, 20), nodata=np.nan,
    ) as dst:
        for band in (1, 2, 3):
            dst.write(np.ones((5, 5), dtype=np.float32), band)

    with pytest.raises(ValueError, match="no comparte rejilla"):
        stack_lake_rasters([("2026-01-01", buena), ("2026-02-01", otra)])


def test_apilado_ordena_por_fecha(tmp_path):
    rutas = []
    for fecha, valor in (("2026-04-13", 3.0), ("2025-01-28", 1.0), ("2026-01-08", 2.0)):
        rutas.append((fecha, write_index_raster(
            tmp_path / f"openEO_{fecha}Z.tif",
            np.zeros(SHAPE), np.zeros(SHAPE), np.full(SHAPE, valor),
        )))

    fechas, cubos, perfil = stack_lake_rasters(rutas)

    assert fechas == ["2025-01-28", "2026-01-08", "2026-04-13"]
    np.testing.assert_allclose(cubos["CYA"][:, 0, 0], [1.0, 2.0, 3.0])
    assert cubos["CYA"].shape == (3, *SHAPE)
    assert perfil["crs"].to_string() == "EPSG:32615"


@pytest.mark.parametrize(
    "fecha, estacion",
    [("2026-01-08", "seca"), ("2026-04-28", "seca"), ("2025-05-13", "lluviosa"),
     ("2025-07-17", "lluviosa"), ("2025-11-24", "seca")],
)
def test_estacion_de_guatemala(fecha, estacion):
    assert season_of(fecha) == estacion
