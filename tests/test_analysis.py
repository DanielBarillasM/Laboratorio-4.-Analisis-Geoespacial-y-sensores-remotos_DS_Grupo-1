import numpy as np

from lab4.analysis import cyano_se2waq, describe_values, ndvi, ndwi
from lab4.config import load_lake_geometry, load_observations


def test_official_dates_have_eleven_observations_per_lake():
    observations = load_observations()
    assert observations.groupby("lago").size().to_dict() == {
        "amatitlan": 11,
        "atitlan": 11,
    }


def test_each_lake_has_one_provisional_polygon():
    for lake in ("atitlan", "amatitlan"):
        geometry = load_lake_geometry(lake)
        assert geometry["type"] == "FeatureCollection"
        assert len(geometry["features"]) == 1
        assert geometry["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}


def test_normalized_differences_and_zero_denominator():
    nir = np.array([0.4, 0.0], dtype=np.float32)
    red = np.array([0.2, 0.0], dtype=np.float32)
    green = np.array([0.3, 0.0], dtype=np.float32)
    np.testing.assert_allclose(ndvi(nir, red)[0], 1 / 3, rtol=1e-6)
    np.testing.assert_allclose(ndwi(green, nir)[0], -1 / 7, rtol=1e-6)
    assert np.isnan(ndvi(nir, red)[1])


def test_se2waq_formula_uses_reflectance_and_masks_invalid_blue():
    blue = np.array([0.05, 0.0], dtype=np.float32)
    green = np.array([0.04, 0.04], dtype=np.float32)
    red = np.array([0.03, 0.03], dtype=np.float32)
    expected = 115_530.31 * ((0.04 * 0.03) / 0.05) ** 2.38
    result = cyano_se2waq(blue, green, red)
    np.testing.assert_allclose(result[0], expected, rtol=1e-5)
    assert np.isnan(result[1])


def test_describe_values_ignores_nan():
    summary = describe_values(np.array([1.0, 2.0, np.nan]))
    assert summary["n_pixeles"] == 2
    assert summary["media"] == 1.5
