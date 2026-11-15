"""Tests of the burned-area case study computations (synthetic arrays only, no network, no real data)."""

import math
from datetime import date

import numpy as np
import pytest
from rasterio.transform import Affine

from nina.io.burn_case import (
    AOI,
    REQUESTED_AOI,
    fill_unobserved,
    aoi_grid,
    anchored_patches,
    burned_hectares,
    chip_origins,
    classify,
    dnbr,
    firms_low_confidence,
    firms_windows,
    fmask_clear,
    fmask_reasons,
    mcd64_counts,
    modis_tile_of,
    nbr,
    overlap_stats,
    pixel_area_ha,
    robust_offset,
    sinusoidal_transform,
)

UTM30 = Affine(30.0, 0.0, 500_000.0, 0.0, -30.0, 6_800_000.0)


def test_nbr_and_dnbr_on_a_synthetic_burn():
    # Healthy vegetation: NIR 0.30, SWIR2 0.10 -> NBR 0.5. Burned: NIR 0.15, SWIR2 0.20 -> NBR -1/7.
    nir_pre = np.full((10, 10), 0.30, dtype=np.float32)
    swir_pre = np.full((10, 10), 0.10, dtype=np.float32)
    nir_post, swir_post = nir_pre.copy(), swir_pre.copy()
    nir_post[2:6, 2:7] = 0.15
    swir_post[2:6, 2:7] = 0.20
    pre, post = nbr(nir_pre, swir_pre), nbr(nir_post, swir_post)
    assert pre[0, 0] == pytest.approx(0.5)
    assert post[3, 3] == pytest.approx(-1 / 7)
    d = dnbr(pre, post)
    assert d[3, 3] == pytest.approx(0.5 + 1 / 7)
    assert d[0, 0] == pytest.approx(0.0)
    burned = classify(d, 0.27)
    assert burned.sum() == 20  # 4 x 5 burned block
    # 20 pixels of 30 m x 30 m = 1.8 ha
    assert pixel_area_ha(UTM30) == pytest.approx(0.09)
    assert burned_hectares(burned, UTM30) == pytest.approx(1.8)


def test_nbr_invalid_pixels_are_nan_not_zero():
    nir = np.array([[0.3, 0.0, 0.3]], dtype=np.float32)
    swir = np.array([[0.1, 0.1, 0.1]], dtype=np.float32)
    valid = np.array([[True, True, False]])
    out = nbr(nir, swir, valid)
    assert out[0, 0] == pytest.approx(0.5)
    assert math.isnan(out[0, 1]) and math.isnan(out[0, 2])
    assert not classify(dnbr(out, np.zeros_like(out)), 0.1)[0, 1:].any()


def test_fmask_bits():
    # bit1 cloud, bit3 shadow, bit4 snow, bit5 water, bits 6-7 aerosol (kept), 255 no data
    fmask = np.array([[0, 2, 8, 16], [32, 64 + 128, 255, 1]], dtype=np.uint8)
    clear = fmask_clear(fmask)
    assert clear.tolist() == [[True, False, False, False], [False, True, False, False]]
    reasons = fmask_reasons(fmask, np.ones_like(clear))
    assert reasons["cloud"] == 1 and reasons["snow_ice"] == 1 and reasons["water"] == 1
    assert reasons["no_data"] == 1 and reasons["cirrus"] == 1


def test_anchored_patches_keep_only_patches_touching_hotspots():
    mask = np.zeros((12, 12), dtype=bool)
    mask[1:4, 1:4] = True     # patch A, touches the anchor
    mask[8:11, 8:11] = True   # patch B, far from it
    mask[4, 4] = True         # diagonal neighbour of A: same patch with 8-connectivity
    anchor = np.zeros_like(mask)
    anchor[2, 2] = True
    kept = anchored_patches(mask, anchor)
    assert kept.sum() == 10 and not kept[8:11, 8:11].any()
    assert not anchored_patches(np.zeros_like(mask), anchor).any()


def test_fill_unobserved_only_adds_unobserved_pixels():
    burned = np.zeros((9, 9), dtype=bool)
    burned[2:7, 2:4] = True
    burned[2:7, 5:7] = True        # two burned stripes separated by column 4
    observed = np.ones_like(burned)
    observed[2:7, 4] = False       # the gap is unobserved (e.g. terrain shadow)
    filled = fill_unobserved(burned, observed, radius_px=1)
    added = filled & ~burned
    assert filled[3:6, 4].all() and not (added & observed).any() and added.sum() <= 5
    observed[:] = True             # an observed unburned gap is never filled
    assert (fill_unobserved(burned, observed, radius_px=1) == burned).all()


def test_overlap_and_offset():
    a = np.zeros((4, 4), dtype=bool)
    b = np.zeros((4, 4), dtype=bool)
    a[:, :2] = True
    b[:, 1:3] = True
    stats = overlap_stats(a, b, UTM30)
    assert stats["iou"] == pytest.approx(4 / 12, abs=1e-4)
    assert stats["intersection_ha"] == pytest.approx(0.36)
    assert stats["fraction_of_a_in_b"] == pytest.approx(0.5)
    assert overlap_stats(np.zeros_like(a), np.zeros_like(a), UTM30)["iou"] is None
    values = np.array([[0.02, 0.04, np.nan, 0.9]], dtype=np.float32)
    region = np.array([[True, True, True, False]])
    assert robust_offset(values, region) == pytest.approx(0.03)
    assert robust_offset(values, np.zeros_like(region)) is None


def test_grids_and_tiles():
    transform, (height, width) = aoi_grid(REQUESTED_AOI)
    assert transform.a == 30 and transform.c % 30 == 0 and transform.f % 30 == 0
    assert 2000 < height < 2500 and 2000 < width < 2500  # about 66 km x 68 km
    assert aoi_grid(AOI)[1][1] > width  # the analysis AOI extends the requested one to the west
    assert modis_tile_of(-67.4, -29.05) == (12, 11)
    t = sinusoidal_transform(12, 11)
    assert t.a == pytest.approx(463.3127, abs=1e-3)
    assert pixel_area_ha(t) == pytest.approx(21.4659, abs=1e-3)
    counts = mcd64_counts(np.array([[0, 205, -1], [-2, 210, 0]]), np.array([[True, True, True], [True, True, False]]))
    assert counts == {"pixels_in_aoi": 5, "burned": 2, "unburned": 1, "unmapped": 1, "water": 1}
    assert chip_origins(1000, 512, 448) == [0, 448, 488]
    assert chip_origins(300, 512, 448) == [0]


def test_firms_helpers():
    assert firms_windows(date(2026, 7, 27), date(2026, 8, 10)) == [
        (date(2026, 7, 27), 5), (date(2026, 8, 1), 5), (date(2026, 8, 6), 5)]
    assert firms_windows(date(2026, 7, 27), date(2026, 7, 28)) == [(date(2026, 7, 27), 2)]
    assert firms_low_confidence({"confidence": "l"}) and firms_low_confidence({"confidence": "29"})
    assert not firms_low_confidence({"confidence": "n"}) and not firms_low_confidence({"confidence": "48"})
