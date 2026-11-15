"""Tests for the Hansen forest-loss aggregation, with tiny synthetic GeoTIFFs."""

import math

import h3
import h3.api.basic_int as h3_int
import httpx
import numpy as np
import pytest
import rasterio
from pyproj import Geod
from rasterio.transform import from_origin

from nina.io.forest_loss import (
    BlockTable,
    aggregate_tile,
    aggregate_window,
    blocks_to_cells,
    decode_loss_year,
    fetch,
    last_loss_year,
    next_version,
    quad_area_ha,
    row_pixel_area_ha,
    select_cells,
    tile_bounds,
    tile_url,
)

PIXEL = 0.00025


def write_tif(path, array, *, west=-75.0, north=-10.0, pixel=PIXEL):
    """Single-band uint8 GeoTIFF in EPSG:4326, stored as one-row strips like the GFC tiles."""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=array.shape[1],
        height=array.shape[0],
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(west, north, pixel, pixel),
        compress="lzw",
    ) as target:
        target.write(array.astype(np.uint8), 1)
    return path


def direct_totals(treecover, lossyear, north, grid, n_years, pixel=PIXEL):
    """Pixel-by-pixel reference: forest ha per block and loss ha per (block, year)."""
    rows, cols = treecover.shape
    forest = np.zeros((rows // grid, cols // grid))
    loss = np.zeros((rows // grid, cols // grid, n_years))
    for r in range(rows):
        top = north - r * pixel
        area = quad_area_ha(top, top - pixel, pixel).item()
        for c in range(cols):
            if treecover[r, c] >= 30:
                forest[r // grid, c // grid] += area
                if 1 <= lossyear[r, c] <= n_years:
                    loss[r // grid, c // grid, lossyear[r, c] - 1] += area
    return forest, loss


def test_version_and_tile_names():
    assert last_loss_year("GFC-2024-v1.12") == 2024
    assert next_version("GFC-2024-v1.12") == "GFC-2025-v1.13"
    assert tile_bounds("00N_090W") == (-90.0, -10.0, -80.0, 0.0)
    assert tile_bounds("10S_070W") == (-70.0, -20.0, -60.0, -10.0)
    assert tile_url("GFC-2024-v1.12", "lossyear", "10S_080W").endswith(
        "/GFC-2024-v1.12/Hansen_GFC-2024-v1.12_lossyear_10S_080W.tif"
    )
    with pytest.raises(ValueError):
        last_loss_year("GFC-latest")


def test_loss_year_decoding():
    codes = np.array([0, 1, 12, 24, 25, 255], dtype=np.uint8)
    assert decode_loss_year(codes, 2024).tolist() == [0, 2001, 2012, 2024, 0, 0]
    assert decode_loss_year(codes, 2025).tolist() == [0, 2001, 2012, 2024, 2025, 0]


@pytest.mark.parametrize("latitude", [0.0, -5.0, -10.0, -18.3, -60.0])
def test_pixel_area_matches_geodesic_area(latitude):
    north, south = latitude + PIXEL, latitude
    lons = [-75.0, -75.0 + PIXEL, -75.0 + PIXEL, -75.0]
    lats = [south, south, north, north]
    geodesic = abs(Geod(ellps="WGS84").polygon_area_perimeter(lons, lats)[0]) / 1e4
    assert quad_area_ha(north, south, PIXEL).item() == pytest.approx(geodesic, rel=1e-6)


def test_pixel_area_shrinks_with_latitude():
    equator = row_pixel_area_ha(PIXEL, PIXEL, 1).item()
    south = row_pixel_area_ha(-18.0 + PIXEL, PIXEL, 1).item()
    assert equator == pytest.approx(0.0769, abs=1e-4)  # ~27.8 m x 27.6 m
    assert south / equator == pytest.approx(math.cos(math.radians(18.0)), rel=5e-3)
    rows = row_pixel_area_ha(-10.0, PIXEL, 4000)
    assert np.all(np.diff(rows) < 0)  # moving south from 10° S, pixels get smaller


def test_threshold_keeps_30_percent_and_drops_loss_outside_forest():
    treecover = np.array([[29, 30, 31, 100]], dtype=np.uint8).repeat(4, axis=0)
    lossyear = np.full((4, 4), 5, dtype=np.uint8)
    area = np.ones(4)
    forest, loss = aggregate_window(treecover, lossyear, area, grid_pixels=4, n_years=24)
    assert forest.tolist() == [[12.0]]  # 3 forest columns x 4 rows x 1 ha
    assert loss[0, 0, 4] == 12.0  # year 2005, only on forest pixels
    assert loss.sum() == 12.0


def test_aggregate_window_ignores_unknown_codes():
    treecover = np.full((4, 4), 80, dtype=np.uint8)
    lossyear = np.array([[0, 1, 24, 25]] * 4, dtype=np.uint8)
    _, loss = aggregate_window(treecover, lossyear, np.ones(4), grid_pixels=4, n_years=24)
    assert loss[0, 0, 0] == loss[0, 0, 23] == 4.0
    assert loss.sum() == 8.0


@pytest.mark.parametrize("band_rows", [8, 16, 24])
def test_tile_aggregation_equals_direct_computation(tmp_path, band_rows):
    rng = np.random.default_rng(7)
    north, west, grid, n_years = -10.0, -75.0, 8, 24
    treecover = rng.integers(0, 101, size=(24, 32), dtype=np.uint8)
    lossyear = np.where(rng.random((24, 32)) < 0.4, rng.integers(1, 27, (24, 32)), 0)
    cover = write_tif(tmp_path / "treecover2000.tif", treecover, west=west, north=north)
    loss = write_tif(tmp_path / "lossyear.tif", lossyear, west=west, north=north)

    blocks, unknown = aggregate_tile(
        cover, loss, n_years=n_years, grid_pixels=grid, band_rows=band_rows
    )

    forest_ref, loss_ref = direct_totals(treecover, lossyear, north, grid, n_years)
    assert unknown == int(np.count_nonzero(lossyear > n_years))
    rows = np.rint((north - blocks.latitude) / (grid * PIXEL) - 0.5).astype(int)
    cols = np.rint((blocks.longitude - west) / (grid * PIXEL) - 0.5).astype(int)
    np.testing.assert_allclose(blocks.forest_ha, forest_ref[rows, cols], rtol=1e-12)
    assert len(blocks.forest_ha) == np.count_nonzero(forest_ref)
    rebuilt = np.zeros_like(loss_ref)
    rebuilt[rows[blocks.loss_block], cols[blocks.loss_block], blocks.loss_year - 2001] = (
        blocks.loss_ha
    )
    np.testing.assert_allclose(rebuilt, loss_ref, rtol=1e-12)


def test_blocks_are_summed_per_h3_cell():
    lat, lon = -9.5, -74.5
    cell = h3_int.latlng_to_cell(lat, lon, 7)
    other = h3_int.latlng_to_cell(lat + 0.1, lon, 7)
    blocks = BlockTable(
        latitude=np.array([lat, lat + 0.0005, lat + 0.1]),
        longitude=np.array([lon, lon + 0.0005, lon]),
        forest_ha=np.array([100.0, 50.0, 70.0]),
        loss_block=np.array([0, 1, 1, 2]),
        loss_year=np.array([2005, 2005, 2010, 2005], dtype=np.int32),
        loss_ha=np.array([1.0, 2.0, 3.0, 4.0]),
    )
    assert h3_int.latlng_to_cell(lat + 0.0005, lon + 0.0005, 7) == cell
    forest, loss = blocks_to_cells(blocks)
    assert forest[cell] == 150.0 and forest[other] == 70.0
    rows = {(c, y): v for c, y, v in loss.itertuples(index=False)}
    assert rows == {(cell, 2005): 3.0, (cell, 2010): 3.0, (other, 2005): 4.0}

    empty = h3_int.latlng_to_cell(lat - 0.2, lon, 7)
    forest_table, loss_table = select_cells(forest, loss, np.array([cell, empty]))
    assert forest_table.to_dict("records") == [
        {"cell": h3.int_to_str(c), "forest_2000_ha": v}
        for c, v in sorted([(cell, 150.0), (empty, 0.0)])
    ]
    assert set(loss_table["cell"]) == {h3.int_to_str(cell)}
    assert loss_table["year"].tolist() == [2005, 2010]


def test_block_table_select_reindexes_loss():
    blocks = BlockTable(
        latitude=np.array([0.0, 1.0, 2.0]),
        longitude=np.zeros(3),
        forest_ha=np.ones(3),
        loss_block=np.array([0, 2, 2]),
        loss_year=np.array([2001, 2002, 2003], dtype=np.int32),
        loss_ha=np.array([1.0, 2.0, 3.0]),
    )
    kept = blocks.select(np.array([False, True, True]))
    assert kept.latitude.tolist() == [1.0, 2.0]
    assert kept.loss_block.tolist() == [1, 1]
    assert kept.loss_year.tolist() == [2002, 2003]


def test_fetch_resumes_partial_download(tmp_path):
    payload = bytes(range(256)) * 40
    seen = []

    def handler(request):
        seen.append(request.headers.get("range"))
        start = int(request.headers["range"].split("=")[1].rstrip("-")) if seen[-1] else 0
        status = 206 if start else 200
        return httpx.Response(status, content=payload[start:])

    target = tmp_path / "tile.tif"
    (tmp_path / "tile.tif.part").write_bytes(payload[:1000])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetch(client, "https://example.test/tile.tif", target, len(payload))
    assert target.read_bytes() == payload
    assert seen == ["bytes=1000-"]
    assert not (tmp_path / "tile.tif.part").exists()
