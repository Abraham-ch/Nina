"""Tests of the NASA POWER climate-context layer (no network)."""

import json
import math

import httpx
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
import shapely
from nina.io import climate
from nina.io.climate import (
    add_anomalies,
    assign_points,
    climatology_scores,
    department_key,
    department_means,
    download_points,
    grid_points,
    load_cache,
    parse_power_record,
    point_values,
    saturation_vapour_pressure_kpa,
    select_points,
    vapour_pressure_deficit_kpa,
)


def fake_power_payload(
    precip: float = 3.0, t2m: float = 25.0, rh: float = 60.0, version: str = "v9.9.9"
) -> dict:
    """Minimal POWER monthly JSON: every month of 2001-2025 plus the ANN (month 13) key."""
    keys = [f"{y}{m:02d}" for y in range(2001, 2026) for m in range(1, 14)]
    return {
        "type": "Feature",
        "header": {
            "api": {"version": version, "name": "POWER Monthly and Annual API"},
            "sources": ["MERRA2"],
            "fill_value": -999.0,
            "time_standard": "LST",
        },
        "parameters": {"PRECTOTCORR": {"units": "mm/day"}},
        "properties": {
            "parameter": {
                "PRECTOTCORR": dict.fromkeys(keys, precip),
                "T2M": dict.fromkeys(keys, t2m),
                "T2M_MAX": dict.fromkeys(keys, t2m + 8),
                "RH2M": dict.fromkeys(keys, rh),
            }
        },
    }


def record_for(payload: dict, lat: float = -9.0, lon: float = -75.0) -> dict:
    """Cache-shaped record wrapping a payload."""
    return {
        "cache_schema": climate.CACHE_SCHEMA,
        "request": {"url": climate.POWER_URL, "params": climate.request_params(lat, lon)},
        "retrieved_at": "2026-11-14T00:00:00+00:00",
        "api": payload["header"]["api"],
        "response": payload,
    }


def test_vpd_tetens_matches_hand_computation():
    # e_s(25 C) = 0.6108 * exp(17.27 * 25 / 262.3) = 0.6108 * exp(1.646016) = 3.16777 kPa
    # (FAO-56 Annex 2, Table 2.3, lists 3.168 kPa). VPD at RH 60 % = 0.4 * e_s = 1.26711 kPa.
    assert saturation_vapour_pressure_kpa(25.0) == pytest.approx(3.16777, abs=1e-4)
    assert vapour_pressure_deficit_kpa(25.0, 60.0) == pytest.approx(1.26711, abs=1e-4)
    assert saturation_vapour_pressure_kpa(0.0) == pytest.approx(0.6108)
    assert vapour_pressure_deficit_kpa(30.0, 100.0) == pytest.approx(0.0)
    # Supersaturated RH from reanalysis rounding is clipped, never a negative VPD.
    assert vapour_pressure_deficit_kpa(10.0, 101.0) == pytest.approx(0.0)
    np.testing.assert_allclose(
        vapour_pressure_deficit_kpa(np.array([25.0, 0.0]), np.array([60.0, 50.0])),
        [1.26711, 0.3054],
        atol=1e-4,
    )


def test_department_key_is_ascii_uppercase():
    assert department_key("San Martín") == "SAN MARTIN"
    assert department_key("  Apurímac ") == "APURIMAC"
    assert department_key("Municipalidad  Metropolitana de Lima") == (
        "MUNICIPALIDAD METROPOLITANA DE LIMA"
    )


def test_climatology_scores_z_and_percentile():
    years = pd.Series(range(2001, 2026))
    values = pd.Series([float(y - 2000) for y in years])  # 1..25; reference 2002-2024 = 2..24
    z, pct = climatology_scores(values, years, (2002, 2024))
    sd = math.sqrt(46.0)  # sample variance of 23 consecutive integers = 23 * 24 / 12
    assert z.iloc[0] == pytest.approx((1 - 13) / sd)
    assert z.iloc[12] == pytest.approx(0.0)
    assert pct.iloc[0] == pytest.approx(0.0)  # below every reference year
    assert pct.iloc[-1] == pytest.approx(100.0)  # above every reference year
    assert pct.iloc[12] == pytest.approx(100 * (11 + 0.5) / 23)  # 13: 11 below, 1 tie
    constant = pd.Series([5.0] * 25)
    z_const, pct_const = climatology_scores(constant, years, (2002, 2024))
    assert z_const.isna().all()
    assert pct_const.eq(50.0).all()


def test_add_anomalies_and_drought_flag():
    years = list(range(2001, 2026))
    frame = pd.DataFrame(
        {
            "department": "Test",
            "year": years,
            "month": 8,
            "precip_mm": [float(y - 2000) for y in years],
            "vpd_kpa": [float(2026 - y) / 10 for y in years],  # dry years are high-VPD years
        }
    )
    other = frame.assign(department="Flat", precip_mm=10.0)  # sd = 0 -> undefined
    result = add_anomalies(pd.concat([frame, other], ignore_index=True), (2002, 2024))
    test = result.loc[result["department"] == "Test"].set_index("year")
    assert test.at[2001, "precip_z"] == pytest.approx(-12 / math.sqrt(46.0))
    assert test.at[2001, "vpd_z"] == pytest.approx(12 / math.sqrt(46.0))
    assert bool(test.at[2001, "drought"]) is True
    assert bool(test.at[2013, "drought"]) is False
    assert test.at[2025, "precip_percentile"] == pytest.approx(100.0)
    flat = result.loc[result["department"] == "Flat"]
    assert flat["precip_z"].isna().all()
    assert flat["drought"].isna().all()  # undefined, not "no drought"


def test_department_average_with_synthetic_polygons():
    departments = {
        "Square": shapely.box(-76.0, -10.0, -75.0, -9.0),
        "Tiny": shapely.box(-73.2, -9.6, -73.1, -9.4),  # no grid point inside
    }
    grid = grid_points((-77.0, -11.0, -72.0, -8.0), 0.5)
    points = select_points(grid, departments, buffer_deg=0.5)
    assert points["department"].eq("Square").sum() == 9  # 3 x 3 points, boundary included
    assert points["lon"].max() == -73.0  # -72.5 is 0.6 deg from Tiny: dropped
    assignment = assign_points(points, departments, radius_deg=0.5)
    tiny = assignment.loc[assignment["department"] == "Tiny"]
    assert tiny["method"].eq("nearest").all()
    # Only land points (inside some polygon) are candidates; the nearest Square point is 1.9 deg
    # away (beyond the 0.5 deg radius), so the single nearest one is used.
    assert tiny["point_id"].tolist() == ["lat-09.50_lon-075.00"]

    rows = []
    for row in points.loc[points["department"].notna()].itertuples(index=False):
        # Value = longitude offset; the two westernmost-column points share one source cell.
        cell = "shared" if row.lon == -76.0 else row.point_id
        rows.append(
            {
                "point_id": row.point_id,
                "source_cell": cell,
                "year": 2005,
                "month": 8,
                "precip_mm": 100.0 + (row.lon + 76.0) * 10,
                "t2m_c": 20.0,
                "t2m_max_c": 30.0,
                "rh_pct": 50.0,
                "vpd_kpa": 1.0,
            }
        )
    values = pd.DataFrame(rows)
    means = department_means(values, assignment).set_index("department")
    # Square: one "shared" cell at lon -76 (100), 3 cells at -75.5 (105) and 3 at -75 (110).
    assert means.at["Square", "precip_mm"] == pytest.approx((100 + 3 * 105 + 3 * 110) / 7)
    assert means.at["Square", "n_points"] == 9
    assert means.at["Square", "n_cells"] == 7
    assert means.at["Tiny", "precip_mm"] == pytest.approx(110.0)
    assert means.at["Tiny", "n_points"] == 1


def test_parse_record_drops_annual_and_fill_and_converts_units():
    payload = fake_power_payload(precip=2.0)
    payload["properties"]["parameter"]["RH2M"]["200502"] = -999.0
    raw = parse_power_record(record_for(payload))
    assert len(raw) == 25 * 12
    assert raw["month"].between(1, 12).all()
    assert math.isnan(raw.loc[(raw["year"] == 2005) & (raw["month"] == 2), "RH2M"].item())
    values = point_values({"p": record_for(payload)}).set_index(["year", "month"])
    assert values.at[(2004, 2), "precip_mm"] == pytest.approx(2.0 * 29)  # leap year
    assert values.at[(2005, 2), "precip_mm"] == pytest.approx(2.0 * 28)
    assert math.isnan(values.at[(2005, 2), "vpd_kpa"])


def test_download_uses_cache_and_retries(monkeypatch, tmp_path):
    calls: list[httpx.Request] = []
    responses = iter([httpx.Response(429, headers={"Retry-After": "7"})])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        queued = next(responses, None)
        return queued or httpx.Response(200, json=fake_power_payload())

    sleeps: list[float] = []
    monkeypatch.setattr(
        climate, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(climate.time, "sleep", sleeps.append)
    points = pd.DataFrame({"lat": [-9.0, -9.5], "lon": [-75.0, -75.0]})
    points.insert(0, "point_id", [climate.point_id(lat, -75.0) for lat in points["lat"]])

    first = download_points(points, tmp_path, delay_s=0.25)
    assert first == {"downloaded": 2, "cached": 0}
    assert len(calls) == 3  # one 429 retry + two successes
    assert sleeps == [7.0, 0.25, 0.25]  # Retry-After honoured, then a polite pause per request
    assert calls[0].url.params["parameters"] == "PRECTOTCORR,T2M,T2M_MAX,RH2M"
    assert calls[0].url.params["community"] == "AG"
    cached = json.loads(climate.cache_path(tmp_path, -9.0, -75.0).read_text(encoding="utf-8"))
    assert cached["api"]["version"] == "v9.9.9"
    assert cached["retrieved_at"]
    assert cached["request"]["params"]["start"] == 2001

    second = download_points(points, tmp_path, delay_s=0.25)
    assert second == {"downloaded": 0, "cached": 2}
    assert len(calls) == 3  # no new request

    records, missing = load_cache(points, tmp_path)
    assert missing == [] and set(records) == set(points["point_id"])

    # A cache entry made with another query is not reused.
    stale = climate.cache_path(tmp_path, -9.5, -75.0)
    entry = json.loads(stale.read_text(encoding="utf-8"))
    entry["request"]["params"]["end"] = 2020
    stale.write_text(json.dumps(entry), encoding="utf-8")
    assert download_points(points, tmp_path, delay_s=0) == {"downloaded": 1, "cached": 1}
    assert len(calls) == 4


def test_invalid_request_is_not_retried(monkeypatch, tmp_path):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(422, json={"messages": ["bad parameter"]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="HTTP 422"):
        climate.fetch_point(client, -9.0, -75.0, tmp_path, sleep=lambda _: None)
    assert len(calls) == 1
    assert not list(tmp_path.iterdir())


def test_build_writes_schema_and_manifest(monkeypatch, tmp_path):
    boundaries = tmp_path / climate.BOUNDARIES
    boundaries.parent.mkdir(parents=True)
    polygon = shapely.geometry.mapping(shapely.box(-75.2, -9.2, -74.8, -8.8))
    collection = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"shapeName": "Ñuño"}, "geometry": polygon}],
    }
    boundaries.write_text(json.dumps(collection), encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = fake_power_payload()
        for key in payload["properties"]["parameter"]["PRECTOTCORR"]:
            payload["properties"]["parameter"]["PRECTOTCORR"][key] = int(key[:4]) - 2000.0
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        climate, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(climate.time, "sleep", lambda _: None)
    with pytest.raises(SystemExit):
        climate.build(tmp_path, download=False)  # empty cache and no --download
    manifest = climate.build(tmp_path, download=True)

    table = pq.read_table(tmp_path / climate.OUTPUT_DIR / climate.OUTPUT_FILE)
    assert table.schema.equals(climate.OUTPUT_SCHEMA)
    frame = table.to_pandas()
    assert len(frame) == 25 * 12
    assert set(frame["department_key"]) == {"NUNO"}
    assert frame["n_points"].eq(1).all()
    assert frame.loc[frame["year"] == 2001, "precip_z"].lt(-1).all()
    assert manifest["grid"]["kept_points"] == 9
    assert manifest["departments"][0]["method"] == "inside"
    assert manifest["climatology_years"] == [2002, 2024]
    written = json.loads((tmp_path / climate.OUTPUT_DIR / "manifest.json").read_text("utf-8"))
    assert written["outputs"]["rows"] == 300
    assert written["source"]["api_versions"] == ["v9.9.9"]
