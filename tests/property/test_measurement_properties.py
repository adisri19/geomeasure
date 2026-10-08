"""Property-based invariant tests using Hypothesis for geometric and measurement invariants."""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from shapely.affinity import scale, translate
from shapely.geometry import LineString, MultiLineString, box

from app.services.measurement_service import MeasurementService


@given(
    x=st.floats(min_value=73.0, max_value=74.0),
    y=st.floats(min_value=19.0, max_value=20.0),
    w=st.floats(min_value=0.001, max_value=0.05),
    h=st.floats(min_value=0.001, max_value=0.05),
)
@settings(max_examples=25)
def test_property_polygon_area_non_negative(x: float, y: float, w: float, h: float) -> None:
    poly = box(x, y, x + w, y + h)
    res = MeasurementService.measure_feature(poly, "EPSG:4326")
    assert res.status == "OK"
    assert res.area_m2 is not None
    assert res.area_m2 > 0.0


@given(
    scale_factor=st.floats(min_value=1.1, max_value=5.0),
)
@settings(max_examples=15)
def test_property_area_scaling_invariant(scale_factor: float) -> None:
    # Small parcel in UTM Zone 43N
    base_poly = box(580000.0, 2210000.0, 580100.0, 2210100.0)  # 10,000 m2
    scaled_poly = scale(
        base_poly, xfact=scale_factor, yfact=scale_factor, origin=(580000.0, 2210000.0)
    )

    base_res = MeasurementService.measure_feature(base_poly, "EPSG:32643")
    scaled_res = MeasurementService.measure_feature(scaled_poly, "EPSG:32643")

    assert base_res.area_m2 is not None
    assert scaled_res.area_m2 is not None

    expected_ratio = scale_factor * scale_factor
    actual_ratio = scaled_res.area_m2 / base_res.area_m2
    assert pytest.approx(actual_ratio, rel=1e-3) == expected_ratio


@given(
    dx=st.floats(min_value=10.0, max_value=500.0),
    dy=st.floats(min_value=10.0, max_value=500.0),
)
@settings(max_examples=15)
def test_property_translation_invariance(dx: float, dy: float) -> None:
    base_poly = box(580000.0, 2210000.0, 580200.0, 2210200.0)
    shifted_poly = translate(base_poly, xoff=dx, yoff=dy)

    res1 = MeasurementService.measure_feature(base_poly, "EPSG:32643")
    res2 = MeasurementService.measure_feature(shifted_poly, "EPSG:32643")

    assert res1.area_m2 is not None
    assert res2.area_m2 is not None
    assert pytest.approx(res1.area_m2, rel=1e-5) == res2.area_m2


def test_property_multilinestring_sum_equals_parts() -> None:
    l1 = LineString([(580000.0, 2210000.0), (580200.0, 2210000.0)])
    l2 = LineString([(580300.0, 2210000.0), (580600.0, 2210000.0)])
    ml = MultiLineString([l1, l2])

    res_l1 = MeasurementService.measure_feature(l1, "EPSG:32643")
    res_l2 = MeasurementService.measure_feature(l2, "EPSG:32643")
    res_ml = MeasurementService.measure_feature(ml, "EPSG:32643")

    assert res_l1.length_m is not None
    assert res_l2.length_m is not None
    assert res_ml.length_m is not None

    assert pytest.approx(res_ml.length_m, rel=1e-5) == (res_l1.length_m + res_l2.length_m)
