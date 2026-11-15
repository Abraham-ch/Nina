"""Burned-area case study: Chilecito fire, Famatina range (La Rioja, Argentina), late July 2026.

This is the example shown in the NASA Space Apps 2026 challenge "Harmonization of MODIS and VIIRS hotspots"
(CONAE emergency activation ACT#356). The module measures the burned area with three independent methods and compares
them, so that the hotspots NINA harmonizes can be checked against what actually burned:

1. ``hls``: dNBR from Harmonized Landsat Sentinel-2 (HLS v2.0, 30 m). NBR = (NIR - SWIR2) / (NIR + SWIR2) on a
   pre-fire and a post-fire scene, clouds/shadow/snow/water masked with Fmask, dNBR = NBR_pre - NBR_post minus an
   offset (median dNBR of pixels far from any hotspot), thresholded at 0.10 (low severity and above) and 0.27
   (moderate-low severity and above; Key & Benson 2006). Burned patches are kept only when they touch a buffer
   around the FIRMS hotspots of the event window ("hotspot-anchored"), which removes unrelated change.
2. ``mcd64a1``: MODIS MCD64A1 collection 6.1 burned area (500 m, monthly), July and August 2026. Needs ``pyhdf``
   (HDF4), which is not part of the packages/nina environment; run that step with an interpreter that has it.
3. ``prithvi``: optional out-of-domain test of IBM/NASA Prithvi-EO-2.0-300M-BurnScars (fine-tuned on US burn scars)
   on the post-fire HLS scene. Needs torch and terratorch (never installed in the repository environments).

``firms`` downloads the hotspots of the event window from the FIRMS area API (standard data take precedence over
NRT for the same sensor and day). Credentials (EARTHDATA_USERNAME / EARTHDATA_PASSWORD, FIRMS_MAP_KEY) are read from
the workspace ``.env`` or the environment and are never printed, logged or written to disk.

Outputs go to ``source/context/burn_case/`` and downloads to ``source/downloads/burn_case/`` (both gitignored).
Every step updates ``summary.json`` in place.

Usage (from packages/nina):
    .venv/Scripts/python.exe -m nina.io.burn_case --workspace ../..                      # firms + hls
    <python with pyhdf> -m nina.io.burn_case --workspace ../.. --steps mcd64a1
    <python with torch+terratorch> -m nina.io.burn_case --workspace ../.. --steps prithvi
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import ssl
import time
import warnings
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import numpy as np
import rasterio
import shapely
import truststore
from pyproj import Transformer
from rasterio import features
from rasterio.transform import Affine, rowcol
from rasterio.warp import Resampling, reproject
from scipy import ndimage

# --------------------------------------------------------------------------------------------------------------
# Case definition
# --------------------------------------------------------------------------------------------------------------

# west, south, east, north (EPSG:4326). The requested AOI (around Guanchin, Famatina range) cuts the western part
# of the fire: 145 nominal/high-confidence hotspots of 29-31 July lie between -67.78 and -67.75. The analysis AOI is
# therefore extended 0.15 deg to the west (still inside HLS tiles T19JFJ/T19JFH); areas are also reported clipped
# to the requested AOI.
REQUESTED_AOI = (-67.75, -29.35, -67.05, -28.75)
AOI = (-67.90, -29.35, -67.05, -28.75)
WORK_CRS = "EPSG:32719"  # UTM 19S, native CRS of the HLS tiles T19JFJ / T19JFH
RESOLUTION = 30.0
TILES = ("T19JFJ", "T19JFH")
EVENT_START = date(2026, 7, 27)
EVENT_END = date(2026, 8, 10)
DEFAULT_PRE = "2026-07-14"
DEFAULT_POST = "2026-08-07"
DEFAULT_SENSITIVITY_POSTS = ("2026-08-23",)

THRESHOLDS = {"low": 0.10, "moderate": 0.27}  # dNBR classes of Key & Benson (2006), FIREMON
HOTSPOT_BUFFER_M = 1000.0  # anchoring buffer around hotspot centres (VIIRS 375 m and MODIS 1 km pixels)
OFFSET_EXCLUSION_M = 5000.0  # pixels farther than this from any hotspot define the dNBR offset
FMASK_REJECT_BITS = 0b0011_1111  # HLS v2.0 Fmask: cirrus, cloud, adjacent, shadow, snow/ice, water
FMASK_WATER_BIT = 1 << 5
FMASK_BITS = {"cirrus": 0, "cloud": 1, "adjacent_cloud_shadow": 2, "cloud_shadow": 3, "snow_ice": 4, "water": 5}
# In this AOI the Fmask "water" bit marks deep terrain shadow on steep slopes (winter sun; median NIR 0.02), not
# water bodies. The shadow-included variant accepts those pixels when both NIR and SWIR2 reach this reflectance.
MIN_SHADOW_REFLECTANCE = 0.01
GAP_FILL_RADIUS_PX = 3  # closing radius (90 m) used to fill unobserved pixels enclosed by burned patches
HLS_FILL = -9999
HLS_SCALE = 1e-4

BANDS = {  # common name -> HLS band file suffix
    "HLSL30": {"blue": "B02", "green": "B03", "red": "B04", "nir": "B05", "swir1": "B06", "swir2": "B07",
               "fmask": "Fmask"},
    "HLSS30": {"blue": "B02", "green": "B03", "red": "B04", "nir": "B8A", "swir1": "B11", "swir2": "B12",
               "fmask": "Fmask"},
}

# MODIS sinusoidal grid (MODLAND)
SINU_CRS = "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"
SINU_TILE_M = 1111950.5196666666
SINU_X0 = -20015109.354
SINU_Y0 = 10007554.677
MCD64_SIZE = 2400

FIRMS = "https://firms.modaps.eosdis.nasa.gov"
FIRMS_PRODUCTS = {  # family -> (standard product, NRT product)
    "MODIS": ("MODIS_SP", "MODIS_NRT"),
    "VIIRS_SNPP": ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
    "VIIRS_NOAA20": ("VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
    "VIIRS_NOAA21": ("VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"),
}
FIRMS_MAX_DAYS = 5
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
URS_HOST = "urs.earthdata.nasa.gov"
USER_AGENT = "nina-pipeline"

LICENSES = {
    "HLS": "NASA LP DAAC, HLS v2.0 (HLSL30/HLSS30); NASA open data policy, no restrictions on reuse",
    "MCD64A1": "NASA LP DAAC, MCD64A1 collection 6.1; NASA open data policy, no restrictions on reuse",
    "FIRMS": "NASA FIRMS (LANCE / UMD standard products); NASA open data policy, cite FIRMS",
    "Prithvi": "Apache-2.0 (IBM / NASA, ibm-nasa-geospatial/Prithvi-EO-2.0-300M-BurnScars)",
}
FIRMS_CITATION = ("NASA FIRMS: MODIS Collection 6.1 and VIIRS 375 m Collection 2 active fire products, "
                  "https://firms.modaps.eosdis.nasa.gov/ (disclaimer: https://www.earthdata.nasa.gov/data/tools/firms/faq)")

# USGS dNBR severity palette (lower bound, RGB); values below the first bound are enhanced regrowth.
DNBR_PALETTE = [(-np.inf, (122, 135, 55)), (-0.25, (172, 190, 77)), (-0.10, (10, 224, 66)), (0.10, (255, 247, 11)),
                (0.27, (255, 175, 56)), (0.44, (255, 100, 27)), (0.66, (164, 31, 214))]
MASKED_RGB = (128, 128, 128)


# --------------------------------------------------------------------------------------------------------------
# Pure computations (covered by tests/test_burn_case.py)
# --------------------------------------------------------------------------------------------------------------

def fmask_clear(fmask: np.ndarray, nodata: int = 255, reject_bits: int = FMASK_REJECT_BITS) -> np.ndarray:
    """True where the HLS Fmask reports clear land (no cirrus, cloud, adjacency, shadow, snow/ice or water)."""
    fmask = np.asarray(fmask)
    return (fmask != nodata) & ((fmask.astype(np.uint16) & reject_bits) == 0)


def disk(radius: int) -> np.ndarray:
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    return (xx * xx + yy * yy) <= radius * radius


def fill_unobserved(burned: np.ndarray, observed: np.ndarray, radius_px: int = GAP_FILL_RADIUS_PX) -> np.ndarray:
    """Add unobserved pixels that a morphological closing of ``burned`` encloses (observed pixels never change)."""
    pad = radius_px + 1
    closed = ndimage.binary_closing(np.pad(burned, pad), structure=disk(radius_px))[pad:-pad, pad:-pad]
    return burned | (closed & ~observed)


def fmask_reasons(fmask: np.ndarray, region: np.ndarray, nodata: int = 255) -> dict[str, int]:
    """Count pixels of ``region`` flagged by each Fmask bit (a pixel can carry several flags)."""
    fmask = np.asarray(fmask).astype(np.uint16)
    inside = region & (fmask != nodata)
    counts = {name: int((((fmask >> bit) & 1).astype(bool) & inside).sum()) for name, bit in FMASK_BITS.items()}
    counts["no_data"] = int((region & (fmask == nodata)).sum())
    return counts


def nbr(nir: np.ndarray, swir2: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    """Normalized Burn Ratio from scaled or unscaled reflectance; NaN where invalid or the denominator is 0."""
    nir = np.asarray(nir, dtype=np.float32)
    swir2 = np.asarray(swir2, dtype=np.float32)
    total = nir + swir2
    ok = (total > 0) & np.isfinite(total) & (nir > 0) & (swir2 > 0)
    if valid is not None:
        ok &= valid
    out = np.full(nir.shape, np.nan, dtype=np.float32)
    np.divide(nir - swir2, total, out=out, where=ok)
    return out


def dnbr(pre_nbr: np.ndarray, post_nbr: np.ndarray) -> np.ndarray:
    """Differenced NBR (pre minus post); positive values mean vegetation loss. NaN propagates."""
    return (np.asarray(pre_nbr, dtype=np.float32) - np.asarray(post_nbr, dtype=np.float32)).astype(np.float32)


def pixel_area_ha(transform: Affine) -> float:
    """Area of one pixel in hectares for a projected (metre) grid."""
    return abs(transform.a * transform.e - transform.b * transform.d) / 10_000.0


def classify(values: np.ndarray, threshold: float) -> np.ndarray:
    """Boolean burned mask: finite values at or above the threshold."""
    values = np.asarray(values)
    return np.isfinite(values) & (values >= threshold)


def anchored_patches(mask: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """Keep the 8-connected patches of ``mask`` that touch ``anchor`` (e.g. a buffer around hotspots)."""
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if count == 0:
        return np.zeros(mask.shape, dtype=bool)
    keep = np.unique(labels[anchor & mask])
    keep = keep[keep > 0]
    return np.isin(labels, keep)


def burned_hectares(mask: np.ndarray, transform: Affine) -> float:
    """Burned area in hectares of a boolean mask on a projected grid."""
    return float(np.count_nonzero(mask) * pixel_area_ha(transform))


def overlap_stats(a: np.ndarray, b: np.ndarray, transform: Affine) -> dict[str, float | None]:
    """Agreement between two boolean masks on the same grid: areas, intersection, IoU and mutual fractions."""
    inter = np.count_nonzero(a & b)
    union = np.count_nonzero(a | b)
    na, nb = np.count_nonzero(a), np.count_nonzero(b)
    px = pixel_area_ha(transform)
    return {
        "area_a_ha": round(na * px, 2), "area_b_ha": round(nb * px, 2), "intersection_ha": round(inter * px, 2),
        "iou": round(inter / union, 4) if union else None,
        "fraction_of_a_in_b": round(inter / na, 4) if na else None,
        "fraction_of_b_in_a": round(inter / nb, 4) if nb else None,
        "area_ratio_b_over_a": round(nb / na, 4) if na else None,
    }


def robust_offset(values: np.ndarray, region: np.ndarray) -> float | None:
    """Median dNBR of a reference (presumed unburned) region; None if it has no finite pixels."""
    sample = values[region & np.isfinite(values)]
    return float(np.median(sample)) if sample.size else None


def aoi_grid(aoi: tuple[float, float, float, float], crs: str = WORK_CRS,
             resolution: float = RESOLUTION) -> tuple[Affine, tuple[int, int]]:
    """A north-up grid in ``crs`` that covers the geographic AOI, snapped to multiples of ``resolution``."""
    box = shapely.segmentize(shapely.box(*aoi), 0.01)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = to_utm.transform(*np.asarray(box.exterior.coords).T)
    x0 = np.floor(min(xs) / resolution) * resolution
    x1 = np.ceil(max(xs) / resolution) * resolution
    y0 = np.floor(min(ys) / resolution) * resolution
    y1 = np.ceil(max(ys) / resolution) * resolution
    width = int(round((x1 - x0) / resolution))
    height = int(round((y1 - y0) / resolution))
    return Affine(resolution, 0.0, x0, 0.0, -resolution, y1), (height, width)


def sinusoidal_transform(h: int, v: int, size: int = MCD64_SIZE) -> Affine:
    """Geotransform of MODIS sinusoidal tile hHHvVV for a grid of ``size`` x ``size`` pixels."""
    pixel = SINU_TILE_M / size
    return Affine(pixel, 0.0, SINU_X0 + h * SINU_TILE_M, 0.0, -pixel, SINU_Y0 - v * SINU_TILE_M)


def modis_tile_of(lon: float, lat: float) -> tuple[int, int]:
    """MODIS sinusoidal tile (h, v) containing a geographic point."""
    x, y = Transformer.from_crs("EPSG:4326", SINU_CRS, always_xy=True).transform(lon, lat)
    return int((x - SINU_X0) // SINU_TILE_M), int((SINU_Y0 - y) // SINU_TILE_M)


def mcd64_counts(burn_date: np.ndarray, inside: np.ndarray) -> dict[str, int]:
    """Classify MCD64A1 'Burn Date' pixels inside a region: burned (1-366), unburned (0), unmapped (-1), water (-2)."""
    values = burn_date[inside]
    return {"pixels_in_aoi": int(values.size), "burned": int(((values >= 1) & (values <= 366)).sum()),
            "unburned": int((values == 0).sum()), "unmapped": int((values == -1).sum()),
            "water": int((values == -2).sum())}


def doy_to_date(year: int, doy: int) -> str:
    return (date(year, 1, 1) + timedelta(days=int(doy) - 1)).isoformat()


def firms_windows(start: date, end: date, max_days: int = FIRMS_MAX_DAYS) -> list[tuple[date, int]]:
    """Split an inclusive date range into (start, day_range) requests accepted by the FIRMS area API."""
    out, cursor = [], start
    while cursor <= end:
        days = min(max_days, (end - cursor).days + 1)
        out.append((cursor, days))
        cursor += timedelta(days=days)
    return out


def firms_low_confidence(row: dict) -> bool:
    """FIRMS low-confidence detections (VIIRS 'l', MODIS < 30), excluded as in NINA's QA (AGENTS.md section 9.2)."""
    value = str(row.get("confidence", "")).strip().lower()
    if value in {"l", "low"}:
        return True
    if value in {"n", "h", "nominal", "high"}:
        return False
    try:
        return int(float(value)) < 30
    except ValueError:
        return False


# --------------------------------------------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------------------------------------------

def _secrets(workspace: Path) -> dict[str, str]:
    """Read credentials from the environment, falling back to the workspace .env (values are never printed)."""
    from dotenv import dotenv_values

    file_values = dotenv_values(workspace / ".env") if (workspace / ".env").exists() else {}
    keys = ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD", "FIRMS_MAP_KEY")
    return {k: v for k in keys if (v := os.environ.get(k) or file_values.get(k))}


def _redact(text: str, secrets: dict[str, str]) -> str:
    for value in secrets.values():
        if value:
            text = text.replace(value, "***")
    return text


def _client(timeout: float = 300.0, follow_redirects: bool = True) -> httpx.Client:
    return httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=timeout,
                        follow_redirects=follow_redirects, headers={"User-Agent": USER_AGENT})


CMR_CACHE: Path | None = None  # set by main(): CMR answers are cached so reruns work offline and reproducibly


def cmr_granules(short_name: str, version: str, start: str, end: str,
                 bbox: tuple[float, float, float, float] = AOI) -> list[dict]:
    """Granules of a CMR collection intersecting ``bbox`` between two ISO instants (no login needed)."""
    params = {"short_name": short_name, "version": version, "bounding_box": ",".join(map(str, bbox)),
              "temporal": f"{start},{end}", "page_size": 200}
    cache = None
    if CMR_CACHE is not None:
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{short_name}_{version}_{start}_{end}_{params['bounding_box']}")
        cache = CMR_CACHE / f"{name}.json"
    if cache is not None and cache.exists():
        feed = json.loads(cache.read_text(encoding="utf-8"))
    else:
        with _client(60) as client:
            response = client.get(CMR, params=params)
            response.raise_for_status()
        feed = response.json()
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(feed), encoding="utf-8")
    out = []
    for entry in feed["feed"]["entry"]:
        links = [link["href"] for link in entry.get("links", []) if link.get("href", "").startswith("https://")
                 and "/lp-prod-protected/" in link["href"]]
        cloud = entry.get("cloud_cover")
        out.append({"id": entry["title"], "time_start": entry["time_start"],
                    "cloud_cover": float(cloud) if cloud not in (None, "") else None, "links": links})
    return out


class TransientError(RuntimeError):
    """A server-side error worth retrying (HTTP 429/5xx)."""


class EarthdataDownloader:
    """Download NASA Earthdata (LP DAAC) files.

    Redirects are followed by hand so that HTTP basic credentials are sent only to urs.earthdata.nasa.gov over
    HTTPS; the session cookie set by the data server is then reused for later files. Nothing is written to a
    .netrc file and credentials never appear in URLs, logs or exceptions.
    """

    def __init__(self, username: str, password: str):
        self._auth = httpx.BasicAuth(username, password)
        self._client = _client(600, follow_redirects=False)

    def close(self) -> None:
        self._client.close()

    def fetch(self, url: str, target: Path, attempts: int = 5) -> Path:
        """Download ``url`` to ``target`` (skipped if present), retrying transient server and network errors."""
        if target.exists() and target.stat().st_size > 0:
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, attempts + 1):
            try:
                return self._fetch_once(url, target)
            except (TransientError, httpx.TransportError):
                if attempt == attempts:
                    raise
                time.sleep(5 * attempt)
        raise AssertionError("unreachable")

    def _fetch_once(self, url: str, target: Path) -> Path:
        current = url
        for _ in range(12):
            parsed = urlparse(current)
            if parsed.scheme != "https":
                raise RuntimeError(f"refusing non-HTTPS redirect while downloading {target.name}")
            auth = self._auth if parsed.hostname == URS_HOST else None
            request = self._client.build_request("GET", current)
            response = self._client.send(request, auth=auth, stream=True)
            try:
                if response.is_redirect:
                    current = urljoin(current, response.headers["location"])
                    continue
                if response.status_code != 200:
                    error = TransientError if response.status_code in {429, 500, 502, 503, 504} else RuntimeError
                    raise error(f"HTTP {response.status_code} downloading {target.name} "
                                f"(last host {parsed.hostname})")
                part = target.with_suffix(target.suffix + ".part")
                with part.open("wb") as stream:
                    for block in response.iter_bytes(1 << 20):
                        stream.write(block)
                part.replace(target)
                return target
            finally:
                response.close()
        raise RuntimeError(f"too many redirects downloading {target.name}")


def update_summary(folder: Path, section: str, payload: dict) -> dict:
    """Merge one section into summary.json (read-modify-write) and return the whole summary."""
    path = folder / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    summary.setdefault("case", {
        "name": "Chilecito / Famatina fire, La Rioja, Argentina, late July 2026",
        "reference": "NASA Space Apps 2026 challenge video example; CONAE emergency activation ACT#356",
        "requested_aoi_wgs84": {"west": REQUESTED_AOI[0], "south": REQUESTED_AOI[1], "east": REQUESTED_AOI[2],
                                "north": REQUESTED_AOI[3]},
        "analysis_aoi_wgs84": {"west": AOI[0], "south": AOI[1], "east": AOI[2], "north": AOI[3]},
        "work_crs": WORK_CRS, "event_window": [EVENT_START.isoformat(), EVENT_END.isoformat()],
    })
    summary.setdefault("licences", LICENSES)
    summary["firms_citation"] = FIRMS_CITATION
    summary[section] = payload
    summary["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def write_geotiff(path: Path, data: np.ndarray, transform: Affine, crs: str, nodata=None) -> None:
    data = data if data.ndim == 3 else data[None]
    profile = {"driver": "GTiff", "height": data.shape[1], "width": data.shape[2], "count": data.shape[0],
               "dtype": data.dtype, "crs": crs, "transform": transform, "nodata": nodata, "compress": "deflate",
               "tiled": True, "blockxsize": 256, "blockysize": 256}
    if data.dtype == np.float32:
        profile["predictor"] = 3
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


def write_png(path: Path, rgb: np.ndarray) -> None:
    """Write a (3, H, W) uint8 array as PNG through GDAL (no plotting library needed)."""
    with warnings.catch_warnings(), rasterio.Env(GDAL_PAM_ENABLED="NO"):
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        with rasterio.open(path, "w", driver="PNG", height=rgb.shape[1], width=rgb.shape[2], count=3,
                           dtype="uint8") as dst:
            dst.write(rgb)


def mosaic(paths: list[Path], transform: Affine, shape: tuple[int, int], crs: str, nodata,
           dtype) -> np.ndarray:
    """Nearest-neighbour mosaic of several rasters onto one grid; earlier files win where they have data.

    HLS tiles of different MGRS rows are offset by 10 m from each other, so every tile is resampled (nearest)
    to the AOI grid rather than stitched.
    """
    out = np.full(shape, nodata, dtype=dtype)
    for path in paths:
        with rasterio.open(path) as src:
            temp = np.full(shape, nodata, dtype=dtype)
            reproject(rasterio.band(src, 1), temp, src_nodata=src.nodata if src.nodata is not None else nodata,
                      dst_transform=transform, dst_crs=crs, dst_nodata=nodata, resampling=Resampling.nearest)
        fill = (out == nodata) & (temp != nodata)
        out[fill] = temp[fill]
    return out


# --------------------------------------------------------------------------------------------------------------
# Step: FIRMS hotspots
# --------------------------------------------------------------------------------------------------------------

def step_firms(workspace: Path, out: Path, downloads: Path) -> dict:
    """Hotspots of the event window inside the AOI; standard (SP) data take precedence over NRT per sensor/day."""
    secrets = _secrets(workspace)
    key = secrets.get("FIRMS_MAP_KEY")
    if not key:
        return {"status": "skipped", "reason": "FIRMS_MAP_KEY not configured"}
    folder = downloads / "firms"
    folder.mkdir(parents=True, exist_ok=True)
    area = ",".join(f"{v:.4f}" for v in AOI)
    try:
        with _client(120) as client:
            response = client.get(f"{FIRMS}/api/data_availability/csv/{key}/all")
            if response.status_code != 200:
                raise RuntimeError(f"data_availability HTTP {response.status_code}")
            availability = {r["data_id"]: (date.fromisoformat(r["min_date"]), date.fromisoformat(r["max_date"]))
                            for r in csv.DictReader(io.StringIO(response.text))}
            rows, requests_log = [], []
            for family, (sp, nrt) in FIRMS_PRODUCTS.items():
                for product in (sp, nrt):
                    if product not in availability:
                        continue
                    lo, hi = availability[product]
                    start, end = max(EVENT_START, lo), min(EVENT_END, hi)
                    if start > end:
                        continue
                    for first, days in firms_windows(start, end):
                        cache = folder / f"{product}_{area.replace(',', '_')}_{first.isoformat()}_{days}d.csv"
                        if not cache.exists():
                            r = client.get(f"{FIRMS}/api/area/csv/{key}/{product}/{area}/{days}/{first.isoformat()}")
                            if r.status_code != 200 or "latitude" not in r.text[:200].lower():
                                raise RuntimeError(f"FIRMS {product} {first} HTTP {r.status_code} (no CSV returned)")
                            cache.write_text(r.text, encoding="utf-8")
                            time.sleep(0.5)
                        records = list(csv.DictReader(io.StringIO(cache.read_text(encoding="utf-8-sig"))))
                        requests_log.append({"product": product, "start": first.isoformat(), "days": days,
                                             "rows": len(records)})
                        for record in records:
                            record["product"], record["family"] = product, family
                            rows.append(record)
    except Exception as exc:  # never leak the key through an exception message
        return {"status": "failed", "reason": _redact(f"{type(exc).__name__}: {exc}", secrets)}

    # Precedence: for each family and day covered by its standard product, drop NRT rows.
    kept, superseded = [], 0
    for row in rows:
        family = row["family"]
        sp = FIRMS_PRODUCTS[family][0]
        day = date.fromisoformat(row["acq_date"])
        if row["product"].endswith("_NRT") and sp in availability and \
                availability[sp][0] <= day <= availability[sp][1]:
            superseded += 1
            continue
        kept.append(row)
    low = [r for r in kept if firms_low_confidence(r)]
    non_veg = [r for r in kept if str(r.get("type", "")).strip() in {"1", "2", "3"}]
    good = [r for r in kept if not firms_low_confidence(r) and str(r.get("type", "")).strip() not in {"1", "2", "3"}]
    good = [r for r in good if AOI[0] <= float(r["longitude"]) <= AOI[2] and AOI[1] <= float(r["latitude"]) <= AOI[3]]

    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r["longitude"]),
                                                                               float(r["latitude"])]},
              "properties": {k: r.get(k) for k in ("acq_date", "acq_time", "satellite", "instrument", "confidence",
                                                   "frp", "daynight", "type", "version", "product")}}
             for r in good]
    (out / "hotspots.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                                          encoding="utf-8")
    by_day = Counter(r["acq_date"] for r in good)
    return {
        "status": "ok", "window": [EVENT_START.isoformat(), EVENT_END.isoformat()],
        "products_used": sorted({r["product"] for r in good}),
        "availability": {p: [lo.isoformat(), hi.isoformat()] for p, (lo, hi) in availability.items()
                         if p in {x for pair in FIRMS_PRODUCTS.values() for x in pair}},
        "requests": requests_log, "rows_downloaded": len(rows), "superseded_by_standard": superseded,
        "low_confidence_excluded": len(low), "non_vegetation_type_excluded": len(non_veg),
        "hotspots_used": len(good), "by_product": dict(Counter(r["product"] for r in good)),
        "by_day": dict(sorted(by_day.items())),
        "first_day": min(by_day) if by_day else None, "last_day": max(by_day) if by_day else None,
        "geojson": str((out / "hotspots.geojson").relative_to(workspace)).replace("\\", "/"),
    }


def load_hotspots(out: Path) -> list[dict]:
    path = out / "hotspots.geojson"
    if not path.exists():
        return []
    return [{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1], **f["properties"]}
            for f in json.loads(path.read_text(encoding="utf-8"))["features"]]


def hotspot_buffer(points: list[dict], radius_m: float, transform: Affine, shape: tuple[int, int],
                   crs: str = WORK_CRS) -> np.ndarray:
    """Rasterize the union of circular buffers around hotspot centres onto the work grid."""
    if not points:
        return np.zeros(shape, dtype=bool)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = to_utm.transform([p["lon"] for p in points], [p["lat"] for p in points])
    zone = shapely.union_all(shapely.buffer(shapely.points(np.c_[xs, ys]), radius_m))
    return features.rasterize([(zone, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)


# --------------------------------------------------------------------------------------------------------------
# Step: HLS dNBR
# --------------------------------------------------------------------------------------------------------------

LOCAL_HLS: Path | None = None  # set by main(): folder with already downloaded HLS granules


def local_granules(short_name: str, day: str) -> list[dict]:
    """Granules of ``day`` already on disk, with the LP DAAC URLs they were downloaded from (offline fallback)."""
    if LOCAL_HLS is None or not LOCAL_HLS.exists():
        return []
    doy = date.fromisoformat(day).timetuple().tm_yday
    prefix = f"HLS.{short_name[3:]}."
    out = []
    for folder in sorted(LOCAL_HLS.glob(f"{prefix}*.{date.fromisoformat(day).year}{doy:03d}T*")):
        base = f"https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/{short_name}.020/{folder.name}/"
        out.append({"id": folder.name, "time_start": day, "cloud_cover": None, "source": "local files (CMR unreachable)",
                    "links": [base + f.name for f in folder.glob("*.tif")]})
    return out


def find_scene(day: str, collections: tuple[str, ...] = ("HLSL30", "HLSS30")) -> dict:
    """HLS granules of both tiles on a given UTC day (first collection with complete tile coverage wins).

    If CMR cannot be reached and nothing is cached, granules already downloaded under ``LOCAL_HLS`` are used (their
    cloud cover is then unknown and reported as null).
    """
    for short in collections:
        try:
            granules = cmr_granules(short, "2.0", f"{day}T00:00:00Z", f"{day}T23:59:59Z")
        except httpx.TransportError:
            granules = local_granules(short, day)
        by_tile = {t: g for g in granules for t in TILES if f".{t}." in g["id"]}
        if all(t in by_tile for t in TILES):
            return {"collection": short, "date": day, "granules": [by_tile[t] for t in TILES]}
    raise RuntimeError(f"no HLS scene with tiles {TILES} on {day}")


def fetch_scene(scene: dict, bands: list[str], downloader: EarthdataDownloader, downloads: Path) -> dict[str, list]:
    """Download the requested bands of every granule of a scene; returns band -> list of local paths."""
    names = BANDS[scene["collection"]]
    out: dict[str, list[Path]] = {b: [] for b in bands}
    for granule in scene["granules"]:
        folder = downloads / "hls" / granule["id"]
        for band in bands:
            suffix = f".{names[band]}.tif"
            url = next((u for u in granule["links"] if u.endswith(suffix)), None)
            if url is None:
                raise RuntimeError(f"{granule['id']} has no {suffix} link in CMR")
            out[band].append(downloader.fetch(url, folder / Path(urlparse(url).path).name))
    return out


def load_scene(paths: dict[str, list], transform: Affine, shape: tuple[int, int]) -> dict[str, np.ndarray]:
    arrays = {}
    for band, files in paths.items():
        if band == "fmask":
            arrays[band] = mosaic(files, transform, shape, WORK_CRS, 255, np.uint8)
        else:
            arrays[band] = mosaic(files, transform, shape, WORK_CRS, HLS_FILL, np.int16)
    return arrays


def scene_nbr(arrays: dict[str, np.ndarray], include_shadow: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """NBR of a scene and its validity mask.

    Standard variant: every Fmask flag in FMASK_REJECT_BITS is rejected. Shadow-included variant: the "water" bit is
    ignored where both NIR and SWIR2 reach MIN_SHADOW_REFLECTANCE (deep terrain shadow, not water, in this AOI).
    """
    fm = arrays["fmask"]
    has_data = (arrays["nir"] != HLS_FILL) & (arrays["swir2"] != HLS_FILL)
    if include_shadow:
        clear = fmask_clear(fm, reject_bits=FMASK_REJECT_BITS & ~FMASK_WATER_BIT)
        water = (fm != 255) & ((fm & FMASK_WATER_BIT) > 0)
        signal = (arrays["nir"] * HLS_SCALE >= MIN_SHADOW_REFLECTANCE) &                  (arrays["swir2"] * HLS_SCALE >= MIN_SHADOW_REFLECTANCE)
        clear &= ~water | signal
    else:
        clear = fmask_clear(fm)
    valid = clear & has_data
    return nbr(arrays["nir"] * HLS_SCALE, arrays["swir2"] * HLS_SCALE, valid), valid


def evaluate_dnbr(pre_nbr: np.ndarray, post_nbr: np.ndarray, anchor: np.ndarray, reference: np.ndarray,
                  transform: Affine, requested: np.ndarray | None = None) -> dict:
    """dNBR, offset, burned masks and areas for one pre/post pair.

    ``anchor`` is the hotspot buffer, ``reference`` the presumed-unburned region used for the offset and
    ``requested`` the requested-AOI mask (areas are also reported clipped to it).
    """
    raw = dnbr(pre_nbr, post_nbr)
    observed = np.isfinite(raw)
    offset = robust_offset(raw, reference)
    corrected = raw - np.float32(offset or 0.0)
    result = {"offset": round(offset, 4) if offset is not None else None, "areas_ha": {}, "masks": {},
              "observed": observed}
    for name, threshold in THRESHOLDS.items():
        mask = classify(corrected, threshold)
        kept = anchored_patches(mask, anchor)
        filled = fill_unobserved(kept, observed)
        result["masks"][name] = kept
        result["masks"][f"{name}_gap_filled"] = filled
        areas = {
            "threshold": threshold,
            "hotspot_anchored": round(burned_hectares(kept, transform), 1),
            "hotspot_anchored_gap_filled": round(burned_hectares(filled, transform), 1),
            "hotspot_anchored_no_offset": round(burned_hectares(anchored_patches(classify(raw, threshold), anchor),
                                                                transform), 1),
            "whole_aoi_not_anchored": round(burned_hectares(mask, transform), 1),
            "inside_hotspot_buffer_only": round(burned_hectares(mask & anchor, transform), 1),
            "patches_kept": int(ndimage.label(kept, structure=np.ones((3, 3), dtype=bool))[1]),
        }
        if requested is not None:
            areas["hotspot_anchored_in_requested_aoi"] = round(burned_hectares(kept & requested, transform), 1)
            areas["hotspot_anchored_gap_filled_in_requested_aoi"] = round(burned_hectares(filled & requested,
                                                                                          transform), 1)
        result["areas_ha"][name] = areas
    result["dnbr"] = corrected
    return result


def colour_dnbr(values: np.ndarray) -> np.ndarray:
    rgb = np.empty((3, *values.shape), dtype=np.uint8)
    rgb[:] = np.array(MASKED_RGB, dtype=np.uint8)[:, None, None]
    finite = np.isfinite(values)
    for lower, colour in DNBR_PALETTE:
        sel = finite & (values >= lower)
        for i in range(3):
            rgb[i][sel] = colour[i]
    return rgb


def true_colour(arrays: dict[str, np.ndarray]) -> np.ndarray:
    """Stretched true-colour composite (reflectance 0-0.30, gamma 1/1.6); no-data black."""
    bands = []
    for name in ("red", "green", "blue"):
        band = arrays[name].astype(np.float32) * HLS_SCALE
        band = np.clip(band / 0.30, 0, 1) ** (1 / 1.6)
        band[arrays[name] == HLS_FILL] = 0
        bands.append((band * 255).astype(np.uint8))
    return np.stack(bands)


def draw_overlay(rgb: np.ndarray, outlines: list[tuple[np.ndarray, tuple[int, int, int]]],
                 points: list[tuple[int, int]], point_rgb=(255, 0, 0), radius: int = 2) -> np.ndarray:
    """Draw mask outlines (2 px) and hotspot markers (filled squares with a black edge) on an RGB array."""
    rgb = rgb.copy()
    for mask, colour in outlines:
        edge = mask & ~ndimage.binary_erosion(mask)
        edge = ndimage.binary_dilation(edge)
        for i in range(3):
            rgb[i][edge] = colour[i]
    h, w = rgb.shape[1:]
    for r, c in points:
        r0, r1, c0, c1 = max(r - radius - 1, 0), min(r + radius + 2, h), max(c - radius - 1, 0), min(c + radius + 2, w)
        rgb[:, r0:r1, c0:c1] = 0
        r0, r1, c0, c1 = max(r - radius, 0), min(r + radius + 1, h), max(c - radius, 0), min(c + radius + 1, w)
        for i in range(3):
            rgb[i, r0:r1, c0:c1] = point_rgb[i]
    return rgb


VARIANT_NOTES = {
    "moderate_gap_filled": "standard masking plus unobserved pixels enclosed by a 90 m closing (envelope)",
    "moderate_shadow_included": "Fmask water bit (deep terrain shadow) not rejected; noisier",
}


def mask_to_geojson(masks: dict[str, np.ndarray], transform: Affine, pixel_ha: float, crs: str = WORK_CRS,
                    simplify_m: float = 15.0) -> dict:
    """Vectorize burned masks to EPSG:4326 polygons (simplified by half a pixel); area attributes come from pixels."""
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    feats = []
    for name, mask in masks.items():
        polys = [shapely.geometry.shape(geom) for geom, value in
                 features.shapes(mask.astype(np.uint8), mask=mask, transform=transform) if value == 1]
        if not polys:
            continue
        merged = shapely.simplify(shapely.union_all(polys), simplify_m, preserve_topology=True)
        merged = shapely.transform(merged, lambda xy: np.c_[to_wgs.transform(xy[:, 0], xy[:, 1])])
        feats.append({"type": "Feature", "geometry": shapely.geometry.mapping(merged),
                      "properties": {"class": name, "dnbr_threshold": THRESHOLDS[name.split("_")[0]],
                                     "variant": VARIANT_NOTES.get(name, "standard Fmask masking, observed pixels"),
                                     "area_ha_from_pixels": round(float(mask.sum() * pixel_ha), 1),
                                     "method": "HLS dNBR (offset-corrected), hotspot-anchored patches",
                                     "crs_note": "areas computed on the 30 m UTM 19S grid, not on this geometry"}})
    return {"type": "FeatureCollection", "features": feats}


MASK_BANDS = ("low", "moderate", "moderate_shadow_included", "moderate_gap_filled", "low_shadow_included",
              "low_gap_filled")


def aoi_mask(aoi: tuple[float, float, float, float], transform: Affine, shape: tuple[int, int],
             crs: str = WORK_CRS) -> np.ndarray:
    """Rasterize a geographic box onto the work grid."""
    box = shapely.segmentize(shapely.box(*aoi), 0.01)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    box = shapely.transform(box, lambda xy: np.c_[to_utm.transform(xy[:, 0], xy[:, 1])])
    return features.rasterize([(box, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)


def step_hls(workspace: Path, out: Path, downloads: Path, pre_day: str, post_day: str,
             sensitivity_posts: tuple[str, ...]) -> dict:
    t0 = time.perf_counter()
    secrets = _secrets(workspace)
    if not {"EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"} <= secrets.keys():
        return {"status": "skipped", "reason": "EARTHDATA_USERNAME / EARTHDATA_PASSWORD not configured"}
    transform, shape = aoi_grid(AOI)
    px_ha = pixel_area_ha(transform)
    downloader = EarthdataDownloader(secrets["EARTHDATA_USERNAME"], secrets["EARTHDATA_PASSWORD"])
    try:
        pre = find_scene(pre_day)
        post = find_scene(post_day)
        pre_arr = load_scene(fetch_scene(pre, ["nir", "swir2", "fmask"], downloader, downloads), transform, shape)
        post_arr = load_scene(fetch_scene(post, ["blue", "green", "red", "nir", "swir1", "swir2", "fmask"],
                                          downloader, downloads), transform, shape)
        extra = []
        for day in sensitivity_posts:
            try:
                scene = find_scene(day)
                extra.append((scene, load_scene(fetch_scene(scene, ["nir", "swir2", "fmask"], downloader, downloads),
                                                transform, shape)))
            except Exception as exc:  # a sensitivity scene must not break the main result
                extra.append(({"date": day, "error": _redact(str(exc), secrets)}, None))
    except Exception as exc:
        return {"status": "failed", "reason": _redact(f"{type(exc).__name__}: {exc}", secrets)}
    finally:
        downloader.close()
    t_download = time.perf_counter() - t0

    points = load_hotspots(out)
    anchor = hotspot_buffer(points, HOTSPOT_BUFFER_M, transform, shape)
    far = ~hotspot_buffer(points, OFFSET_EXCLUSION_M, transform, shape)
    if not points:
        anchor = np.ones(shape, dtype=bool)  # without hotspots no anchoring is possible
    requested = aoi_mask(REQUESTED_AOI, transform, shape)
    in_tiles = (pre_arr["fmask"] != 255) & (post_arr["fmask"] != 255)

    pre_nbr, pre_valid = scene_nbr(pre_arr)
    post_nbr, post_valid = scene_nbr(post_arr)
    main = evaluate_dnbr(pre_nbr, post_nbr, anchor, far, transform, requested)
    pre_nbr_s, _ = scene_nbr(pre_arr, include_shadow=True)
    post_nbr_s, _ = scene_nbr(post_arr, include_shadow=True)
    shadow = evaluate_dnbr(pre_nbr_s, post_nbr_s, anchor, far, transform, requested)
    both_valid = main["observed"]

    # Products: dNBR (standard Fmask masking) and the burned masks of every variant.
    write_geotiff(out / "dnbr.tif", main["dnbr"], transform, WORK_CRS, nodata=np.nan)
    write_geotiff(out / "dnbr_shadow_included.tif", shadow["dnbr"], transform, WORK_CRS, nodata=np.nan)
    bands = {"low": (main["masks"]["low"], main["observed"]),
             "moderate": (main["masks"]["moderate"], main["observed"]),
             "moderate_shadow_included": (shadow["masks"]["moderate"], shadow["observed"]),
             "moderate_gap_filled": (main["masks"]["moderate_gap_filled"], main["observed"]),
             "low_shadow_included": (shadow["masks"]["low"], shadow["observed"]),
             "low_gap_filled": (main["masks"]["low_gap_filled"], main["observed"])}
    stack = np.zeros((len(MASK_BANDS), *shape), dtype=np.uint8)
    for i, name in enumerate(MASK_BANDS):
        mask, observed = bands[name]
        stack[i] = mask
        stack[i][~mask & ~observed] = 255
    write_geotiff(out / "burned_mask.tif", stack, transform, WORK_CRS, nodata=255)
    perimeter = mask_to_geojson({"low": main["masks"]["low"], "moderate": main["masks"]["moderate"],
                                 "moderate_gap_filled": main["masks"]["moderate_gap_filled"],
                                 "moderate_shadow_included": shadow["masks"]["moderate"]}, transform, px_ha)
    (out / "burned_perimeter.geojson").write_text(json.dumps(perimeter), encoding="utf-8")

    to_utm = Transformer.from_crs("EPSG:4326", WORK_CRS, always_xy=True)
    rows_cols = []
    for p in points:
        r, c = rowcol(transform, *to_utm.transform(p["lon"], p["lat"]))
        if 0 <= r < shape[0] and 0 <= c < shape[1]:
            rows_cols.append((int(r), int(c)))
    requested_edge = requested & ~ndimage.binary_erosion(requested)
    outlines = [(requested_edge, (255, 255, 255)), (main["masks"]["low"], (0, 255, 255)),
                (main["masks"]["moderate"], (255, 255, 0))]
    rgb = draw_overlay(true_colour(post_arr), outlines, rows_cols)
    write_png(out / "post_truecolour_overview.png", rgb)
    sev = draw_overlay(colour_dnbr(main["dnbr"]), [(requested_edge, (255, 255, 255)),
                                                   (main["masks"]["moderate"], (0, 0, 0))], rows_cols,
                       point_rgb=(255, 255, 255))
    write_png(out / "dnbr_classes_overview.png", sev)
    figures = ["post_truecolour_overview.png", "dnbr_classes_overview.png"]
    core = main["masks"]["moderate"]
    if core.any():
        rr, cc = np.nonzero(core)
        margin = int(2500 / RESOLUTION)
        r0, r1 = int(np.percentile(rr, 0.5)) - margin, int(np.percentile(rr, 99.5)) + margin
        c0, c1 = int(np.percentile(cc, 0.5)) - margin, int(np.percentile(cc, 99.5)) + margin
        r0, c0, r1, c1 = max(r0, 0), max(c0, 0), min(r1, shape[0]), min(c1, shape[1])
        write_png(out / "post_truecolour_zoom.png", rgb[:, r0:r1, c0:c1])
        write_png(out / "dnbr_classes_zoom.png", sev[:, r0:r1, c0:c1])
        figures += ["post_truecolour_zoom.png", "dnbr_classes_zoom.png"]
    edge = np.zeros(shape, dtype=bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    edge |= in_tiles & ~ndimage.binary_erosion(in_tiles)
    touches_edge = bool((main["masks"]["low"] & ndimage.binary_dilation(edge, iterations=2)).any())

    buffer_px = int(anchor.sum())
    sensitivity = []
    for scene, arrays in extra:
        if arrays is None:
            sensitivity.append(scene)
            continue
        alt_nbr, _ = scene_nbr(arrays)
        alt = evaluate_dnbr(pre_nbr, alt_nbr, anchor, far, transform, requested)
        sensitivity.append({"post_scene": _scene_meta(scene), "variant": "fmask_standard", "offset": alt["offset"],
                            "areas_ha": alt["areas_ha"],
                            "valid_fraction_in_hotspot_buffer": round(float((alt["observed"] & anchor).sum())
                                                                      / max(buffer_px, 1), 4),
                            "overlap_with_main_moderate": overlap_stats(main["masks"]["moderate"],
                                                                        alt["masks"]["moderate"], transform)})
    d_inside = main["dnbr"][anchor & both_valid]
    m, s = main["areas_ha"], shadow["areas_ha"]
    water_pre = anchor & (pre_arr["fmask"] != 255) & ((pre_arr["fmask"] & FMASK_WATER_BIT) > 0)
    water_nir_median = round(float(np.median(pre_arr["nir"][water_pre]) * HLS_SCALE), 4) if water_pre.any() else None
    return {
        "status": "ok",
        "pre_scene": _scene_meta(pre), "post_scene": _scene_meta(post),
        "aoi": {"requested_wgs84": list(REQUESTED_AOI), "analysis_wgs84": list(AOI),
                "why_extended": "145 nominal/high-confidence hotspots of 29-31 Jul 2026 lie west of the requested "
                                "AOI edge (down to -67.78); the analysis AOI adds 0.15 deg to the west"},
        "grid": {"crs": WORK_CRS, "resolution_m": RESOLUTION, "shape": list(shape), "pixel_area_ha": px_ha,
                 "transform": list(transform)[:6]},
        "method": {
            "nbr": "(NIR - SWIR2) / (NIR + SWIR2), HLS surface reflectance x 1e-4",
            "bands": {"HLSL30": "B05 (NIR) / B07 (SWIR2)", "HLSS30": "B8A (NIR narrow) / B12 (SWIR2)"},
            "fmask_rejected": list(FMASK_BITS), "dnbr": "NBR_pre - NBR_post - offset",
            "offset": f"median raw dNBR of observed pixels farther than {OFFSET_EXCLUSION_M:.0f} m from any hotspot",
            "thresholds": THRESHOLDS, "threshold_source": "Key & Benson (2006), FIREMON Landscape Assessment",
            "anchoring": f"8-connected burned patches touching a {HOTSPOT_BUFFER_M:.0f} m buffer around the FIRMS "
                         f"hotspots of {EVENT_START}..{EVENT_END} (nominal/high confidence)",
            "variants": {
                "fmask_standard": "all Fmask flags rejected; counts only pixels observed on both dates (lower bound)",
                "terrain_shadow_included": "Fmask water bit ignored where NIR and SWIR2 >= "
                                           f"{MIN_SHADOW_REFLECTANCE} on both dates (deep terrain shadow; noisier)",
                "gap_filled": f"fmask_standard plus unobserved pixels enclosed by a {GAP_FILL_RADIUS_PX}-pixel "
                              "(90 m) morphological closing of the burned patches (envelope, upper estimate)",
            },
            "resampling": "both MGRS tiles resampled (nearest) onto one 30 m UTM 19S grid snapped to the AOI",
        },
        "hotspots_used_for_anchoring": len(points),
        "valid_fraction": {
            "aoi_pre": round(float(pre_valid.mean()), 4), "aoi_post": round(float(post_valid.mean()), 4),
            "aoi_both": round(float(both_valid.mean()), 4),
            "hotspot_buffer_both": round(float((both_valid & anchor).sum()) / max(buffer_px, 1), 4),
            "hotspot_buffer_both_shadow_included": round(float((shadow["observed"] & anchor).sum())
                                                         / max(buffer_px, 1), 4),
        },
        "masked_in_hotspot_buffer": {"pre": fmask_reasons(pre_arr["fmask"], anchor),
                                     "post": fmask_reasons(post_arr["fmask"], anchor),
                                     "buffer_pixels": buffer_px,
                                     "note": "the Fmask water bit here marks deep terrain shadow on steep slopes",
                                     "nir_median_of_water_flagged_pre": water_nir_median},
        "dnbr_offset": {"fmask_standard": main["offset"], "terrain_shadow_included": shadow["offset"]},
        "dnbr_stats_in_hotspot_buffer": ({"median": round(float(np.median(d_inside)), 4),
                                          "p90": round(float(np.percentile(d_inside, 90)), 4),
                                          "max": round(float(d_inside.max()), 4)} if d_inside.size else None),
        "headline_ha": {
            name: {"observed_only_lower_bound": m[name]["hotspot_anchored"],
                   "terrain_shadow_included": s[name]["hotspot_anchored"],
                   "gap_filled_envelope": m[name]["hotspot_anchored_gap_filled"],
                   "observed_only_in_requested_aoi": m[name]["hotspot_anchored_in_requested_aoi"]}
            for name in THRESHOLDS},
        "areas_ha": {"fmask_standard": m, "terrain_shadow_included": s},
        "shadow_vs_standard_moderate": overlap_stats(main["masks"]["moderate"], shadow["masks"]["moderate"],
                                                     transform),
        "burned_patch_touches_analysis_aoi_or_tile_edge": touches_edge,
        "sensitivity_other_post_dates": sensitivity,
        "products": {"dnbr_geotiff": _rel(out / "dnbr.tif", workspace),
                     "dnbr_shadow_included_geotiff": _rel(out / "dnbr_shadow_included.tif", workspace),
                     "burned_mask_geotiff": _rel(out / "burned_mask.tif", workspace),
                     "burned_mask_bands": {str(i + 1): n for i, n in enumerate(MASK_BANDS)},
                     "burned_mask_values": "1 burned, 0 observed unburned, 255 not observed",
                     "perimeter_geojson": _rel(out / "burned_perimeter.geojson", workspace),
                     "figures": [_rel(out / f, workspace) for f in figures],
                     "figure_legend": "true colour: post-fire HLS L30 (2026-08-07); cyan outline = dNBR >= 0.10 "
                                      "patches, yellow outline = dNBR >= 0.27 patches (standard Fmask variant), "
                                      "white line = requested AOI, red squares = FIRMS hotspots 27 Jul-10 Aug. "
                                      "dNBR classes: USGS palette (green unburned, yellow low, orange moderate, "
                                      "red-orange moderate-high, purple high, grey not observed); black outline = "
                                      "dNBR >= 0.27, white squares = hotspots"},
        "software": software_versions("numpy", "rasterio", "scipy", "shapely", "pyproj"),
        "timings_s": {"download_and_mosaic": round(t_download, 1), "total": round(time.perf_counter() - t0, 1)},
    }


def _scene_meta(scene: dict) -> dict:
    return {"collection": scene["collection"], "date": scene["date"],
            "granules": [{"id": g["id"], "cloud_cover_pct": g["cloud_cover"]} for g in scene["granules"]]}


def _rel(path: Path, workspace: Path) -> str:
    return str(path.relative_to(workspace)).replace("\\", "/")


# --------------------------------------------------------------------------------------------------------------
# Step: MODIS MCD64A1
# --------------------------------------------------------------------------------------------------------------

def read_mcd64a1(path: Path) -> dict[str, np.ndarray]:
    """Read MCD64A1 HDF4 layers with pyhdf (imported lazily; it is not a packages/nina dependency)."""
    from pyhdf.SD import SD, SDC

    sd = SD(str(path), SDC.READ)
    try:
        return {name: sd.select(name).get() for name in ("Burn Date", "Burn Date Uncertainty", "QA",
                                                          "First Day", "Last Day")}
    finally:
        sd.end()


def step_mcd64a1(workspace: Path, out: Path, downloads: Path) -> dict:
    t0 = time.perf_counter()
    secrets = _secrets(workspace)
    if not {"EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"} <= secrets.keys():
        return {"status": "skipped", "reason": "Earthdata credentials not configured"}
    try:
        import pyhdf.SD  # noqa: F401
    except ImportError:
        return {"status": "skipped", "reason": "pyhdf (HDF4 reader) not installed in this interpreter; the "
                                               "rasterio wheel has no HDF4 driver"}
    h, v = modis_tile_of((AOI[0] + AOI[2]) / 2, (AOI[1] + AOI[3]) / 2)
    corners = {modis_tile_of(x, y) for x in AOI[::2] for y in AOI[1::2]}
    tile = f"h{h:02d}v{v:02d}"
    granules = [g for g in cmr_granules("MCD64A1", "061", "2026-07-01T00:00:00Z", "2026-08-31T23:59:59Z")
                if f".{tile}." in g["id"]]
    downloader = EarthdataDownloader(secrets["EARTHDATA_USERNAME"], secrets["EARTHDATA_PASSWORD"])
    try:
        files = []
        for g in sorted(granules, key=lambda g: g["time_start"]):
            url = next(u for u in g["links"] if u.endswith(".hdf"))
            files.append((g, downloader.fetch(url, downloads / "mcd64a1" / g["id"] / Path(urlparse(url).path).name)))
    except Exception as exc:
        return {"status": "failed", "reason": _redact(f"{type(exc).__name__}: {exc}", secrets)}
    finally:
        downloader.close()

    sinu = sinusoidal_transform(h, v)
    rows, cols = np.mgrid[0:MCD64_SIZE, 0:MCD64_SIZE]
    xs, ys = sinu * (cols + 0.5, rows + 0.5)
    lon, lat = Transformer.from_crs(SINU_CRS, "EPSG:4326", always_xy=True).transform(xs, ys)
    inside = (lon >= AOI[0]) & (lon <= AOI[2]) & (lat >= AOI[1]) & (lat <= AOI[3])
    sinu_px_ha = pixel_area_ha(sinu)

    months, union = [], np.zeros((MCD64_SIZE, MCD64_SIZE), dtype=bool)
    burn_doy = np.zeros((MCD64_SIZE, MCD64_SIZE), dtype=np.int16)
    for g, path in files:
        layers = read_mcd64a1(path)
        bd = layers["Burn Date"].astype(np.int16)
        counts = mcd64_counts(bd, inside)
        burned = inside & (bd >= 1) & (bd <= 366)
        union |= burned
        burn_doy[burned] = bd[burned]
        year = int(g["id"].split(".")[1][1:5])
        hist = Counter(int(d) for d in bd[burned])
        unc = layers["Burn Date Uncertainty"][burned]
        months.append({"granule": g["id"], "month_start": g["time_start"][:10], **counts,
                       "burned_ha": round(counts["burned"] * sinu_px_ha, 1),
                       "burn_dates": {doy_to_date(year, d): n for d, n in sorted(hist.items())},
                       "burn_date_uncertainty_days_median": float(np.median(unc)) if unc.size else None})

    result = {"status": "ok", "tile": tile, "tiles_touching_aoi": sorted(f"h{a:02d}v{b:02d}" for a, b in corners),
              "pixel_size_m": round(SINU_TILE_M / MCD64_SIZE, 3), "pixel_area_ha": round(sinu_px_ha, 3),
              "months": months, "burned_pixels_jul_aug": int(union.sum()),
              "burned_ha_jul_aug": round(float(union.sum() * sinu_px_ha), 1)}

    # Compare with the HLS dNBR masks on the 30 m grid (nearest-neighbour resampling of the 500 m pixels).
    mask_path = out / "burned_mask.tif"
    if mask_path.exists():
        with rasterio.open(mask_path) as src:
            masks, transform, shape = src.read(), src.transform, (src.height, src.width)
        mcd = np.zeros(shape, dtype=np.uint8)
        reproject(union.astype(np.uint8), mcd, src_transform=sinu, src_crs=SINU_CRS, dst_transform=transform,
                  dst_crs=WORK_CRS, resampling=Resampling.nearest)
        mcd = mcd.astype(bool)
        valid = masks[0] != 255
        doy_fine = np.zeros(shape, dtype=np.int16)
        reproject(burn_doy, doy_fine, src_transform=sinu, src_crs=SINU_CRS, dst_transform=transform,
                  dst_crs=WORK_CRS, resampling=Resampling.nearest)
        write_geotiff(out / "mcd64a1_burn_doy_30m.tif", doy_fine, transform, WORK_CRS, nodata=0)
        points = load_hotspots(out)
        anchor = hotspot_buffer(points, HOTSPOT_BUFFER_M, transform, shape) if points else np.ones(shape, bool)
        mcd_anchored = anchored_patches(mcd, anchor)
        comparison = {}
        for band, name in enumerate(MASK_BANDS):
            hls = masks[band] == 1
            comparison[f"dnbr_{name}_vs_mcd64a1"] = {
                "a": f"HLS dNBR burned mask '{name}' (hotspot-anchored)", "b": "MCD64A1 Jul+Aug 2026 (500 m)",
                **overlap_stats(hls, mcd, transform)}
        comparison["mcd64a1_area_on_30m_grid_ha"] = round(burned_hectares(mcd, transform), 1)
        comparison["mcd64a1_hotspot_anchored_area_on_30m_grid_ha"] = round(burned_hectares(mcd_anchored, transform), 1)
        comparison["mcd64a1_in_requested_aoi_on_30m_grid_ha"] = round(
            burned_hectares(mcd & aoi_mask(REQUESTED_AOI, transform, shape), transform), 1)
        comparison["mcd64a1_burned_area_without_valid_dnbr_ha"] = round(burned_hectares(mcd & ~valid, transform), 1)
        comparison["note"] = ("MCD64A1 pixels are 21.5 ha; the comparison resamples them (nearest) to the 30 m dNBR "
                              "grid, so edge effects of up to half a 500 m pixel are expected")
        result["comparison_with_dnbr"] = comparison
    result["software"] = software_versions("pyhdf", "numpy", "rasterio")
    result["timings_s"] = {"total": round(time.perf_counter() - t0, 1)}
    return result


# --------------------------------------------------------------------------------------------------------------
# Step: Prithvi-EO-2.0-300M-BurnScars (optional, out-of-domain test)
# --------------------------------------------------------------------------------------------------------------

PRITHVI_REPO = "ibm-nasa-geospatial/Prithvi-EO-2.0-300M-BurnScars"


def chip_origins(length: int, chip: int, stride: int) -> list[int]:
    """Start offsets of chips that cover ``length`` pixels with the given stride (last chip flush with the end)."""
    if length <= chip:
        return [0]
    starts = list(range(0, length - chip + 1, stride))
    if starts[-1] != length - chip:
        starts.append(length - chip)
    return starts


def step_prithvi(workspace: Path, out: Path, downloads: Path, post_day: str) -> dict:
    """Run the BurnScars model on the post-fire scene in 512 x 512 chips and compare with dNBR.

    Imports torch / terratorch / yaml lazily. The checkpoint is loaded with ``weights_only=True`` so that no
    pickled code from the download is executed.
    """
    t0 = time.perf_counter()
    try:
        import torch
        import yaml
        from terratorch.tasks import SemanticSegmentationTask
    except ImportError as exc:
        return {"status": "skipped", "reason": f"missing dependency: {exc}"}
    model_dir = downloads / "prithvi"
    checkpoint = model_dir / "Prithvi_EO_V2_300M_BurnScars.pt"
    config_path = model_dir / "burn_scars_config.yaml"
    if not checkpoint.exists() or not config_path.exists():
        return {"status": "skipped", "reason": f"model files not found in {_rel(model_dir, workspace)}"}
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_cfg = config["data"]["init_args"]
    means = np.array(data_cfg["means"], dtype=np.float32)
    stds = np.array(data_cfg["stds"], dtype=np.float32)
    model_args = config["model"]["init_args"]["model_args"]
    model_args = {**model_args, "backbone_pretrained": False}
    task = SemanticSegmentationTask(model_args=model_args, model_factory=config["model"]["init_args"]["model_factory"])
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    state = state.get("state_dict", state)
    missing, unexpected = task.load_state_dict(state, strict=False)
    task.eval()

    transform, shape = aoi_grid(AOI)
    secrets = _secrets(workspace)
    downloader = EarthdataDownloader(secrets["EARTHDATA_USERNAME"], secrets["EARTHDATA_PASSWORD"])
    try:
        scene = find_scene(post_day)
        arrays = load_scene(fetch_scene(scene, ["blue", "green", "red", "nir", "swir1", "swir2", "fmask"],
                                        downloader, downloads), transform, shape)
    finally:
        downloader.close()
    order = ["blue", "green", "red", "nir", "swir1", "swir2"]
    stack = np.stack([arrays[b].astype(np.float32) for b in order])
    nodata = (stack == HLS_FILL).any(axis=0)
    # The training means/stds are reflectance in 0-1 (HLS DN x 1e-4); no-data is replaced by 0 reflectance as in
    # the training data module (no_data_replace: 0).
    reflectance = stack * HLS_SCALE
    reflectance[:, nodata] = 0.0
    norm = ((reflectance - means[:, None, None]) / stds[:, None, None]).astype(np.float32)

    chip, stride = 512, 448
    votes = np.zeros(shape, dtype=np.float32)
    weight = np.zeros(shape, dtype=np.float32)
    with torch.no_grad():
        for r in chip_origins(shape[0], chip, stride):
            for c in chip_origins(shape[1], chip, stride):
                window = norm[:, r:r + chip, c:c + chip]
                ph, pw = chip - window.shape[1], chip - window.shape[2]
                tensor = torch.from_numpy(np.pad(window, ((0, 0), (0, ph), (0, pw))))[None]
                output = task.model(tensor)
                logits = output.output if hasattr(output, "output") else output
                prob = torch.softmax(logits, dim=1)[0, 1].numpy()[:window.shape[1], :window.shape[2]]
                votes[r:r + chip, c:c + chip] += prob
                weight[r:r + chip, c:c + chip] += 1
    prob = votes / np.maximum(weight, 1)
    burned = (prob >= 0.5) & ~nodata
    write_geotiff(out / "prithvi_burn_probability.tif", np.where(nodata, np.nan, prob).astype(np.float32),
                  transform, WORK_CRS, nodata=np.nan)
    result = {"status": "ok", "model": PRITHVI_REPO, "post_scene": _scene_meta(scene),
              "input_bands": order, "normalisation": "config means/stds", "chip": chip, "stride": stride,
              "threshold_probability": 0.5, "missing_keys": len(missing), "unexpected_keys": len(unexpected),
              "burned_ha_whole_aoi": round(burned_hectares(burned, transform), 1)}
    # Where do the model's burned pixels fall according to the post-fire Fmask?
    fm = arrays["fmask"].astype(np.uint16)
    has_fmask = arrays["fmask"] != 255
    flags = {"clear": fmask_clear(arrays["fmask"]), "water_bit_terrain_shadow": (fm & FMASK_WATER_BIT) > 0,
             "cloud_adjacent_or_cloud_shadow": (fm & 0b1110) > 0, "snow_ice": (fm & 0b1_0000) > 0}
    result["burned_ha_whole_aoi_by_post_fmask"] = {k: round(burned_hectares(burned & v & has_fmask, transform), 1)
                                                   for k, v in flags.items()}

    # Positive control: the US example chip shipped with the model (its label is not distributed).
    example = next(iter(sorted((model_dir / "examples").glob("*.tif"))), None) if (model_dir / "examples").exists()         else None
    if example is not None:
        with rasterio.open(example) as src:
            img = src.read().astype(np.float32)
        refl = img / 10_000 if img.mean() > 1 else img.copy()
        refl[img == HLS_FILL] = 0.0
        x = torch.from_numpy(((refl - means[:, None, None]) / stds[:, None, None]).astype(np.float32))[None]
        with torch.no_grad():
            output = task.model(x)
        logits = output.output if hasattr(output, "output") else output
        example_prob = torch.softmax(logits, dim=1)[0, 1].numpy()
        result["positive_control"] = {
            "file": example.name, "burned_fraction": round(float((example_prob >= 0.5).mean()), 4),
            "note": "bundled US example (HLS S30, 2018); no label is distributed with it, so this only shows that the "
                    "loaded weights respond to a known burn-scar scene"}

    mask_path = out / "burned_mask.tif"
    if mask_path.exists():
        with rasterio.open(mask_path) as src:
            masks = src.read()
        points = load_hotspots(out)
        anchor = hotspot_buffer(points, HOTSPOT_BUFFER_M, transform, shape) if points else np.ones(shape, bool)
        anchored = anchored_patches(burned, anchor)
        result["burned_ha_hotspot_anchored"] = round(burned_hectares(anchored, transform), 1)
        for band, name in enumerate(MASK_BANDS):
            hls = masks[band] == 1
            result[f"vs_dnbr_{name}_whole_aoi"] = overlap_stats(hls, burned, transform)
            result[f"vs_dnbr_{name}_hotspot_anchored"] = overlap_stats(hls, anchored, transform)
        # Figure: Prithvi burned mask (magenta) and dNBR >= 0.27 (yellow) on the post-fire true colour.
        moderate = masks[1] == 1
        rgb = draw_overlay(true_colour(arrays), [(burned, (255, 0, 255)), (moderate, (255, 255, 0))], [])
        write_png(out / "prithvi_vs_dnbr_overview.png", rgb)
        figures = ["prithvi_vs_dnbr_overview.png"]
        if moderate.any():
            rr, cc = np.nonzero(moderate)
            margin = int(2500 / RESOLUTION)
            r0 = max(int(np.percentile(rr, 0.5)) - margin, 0)
            r1 = min(int(np.percentile(rr, 99.5)) + margin, shape[0])
            c0 = max(int(np.percentile(cc, 0.5)) - margin, 0)
            c1 = min(int(np.percentile(cc, 99.5)) + margin, shape[1])
            write_png(out / "prithvi_vs_dnbr_zoom.png", rgb[:, r0:r1, c0:c1])
            figures.append("prithvi_vs_dnbr_zoom.png")
        result["figures"] = [_rel(out / f, workspace) for f in figures]
        result["figure_legend"] = "magenta = Prithvi burned (p >= 0.5), yellow = HLS dNBR >= 0.27 (hotspot-anchored)"
    result["probability_geotiff"] = _rel(out / "prithvi_burn_probability.tif", workspace)
    result["caveat"] = ("Out-of-domain test: the model was fine-tuned on burn scars in the United States (HLS 2018-2021);"
                        " the Famatina range (arid Monte/Puna shrubland, winter, steep terrain) is outside that domain."
                        " Not a reference measurement.")
    result["software"] = software_versions("torch", "terratorch", "numpy", "rasterio")
    result["timings_s"] = {"total": round(time.perf_counter() - t0, 1)}
    return result


# --------------------------------------------------------------------------------------------------------------
# Step: overview (reads the other sections of summary.json; no network)
# --------------------------------------------------------------------------------------------------------------

def software_versions(*names: str) -> dict[str, str | None]:
    from importlib import metadata

    out = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def step_overview(workspace: Path, out: Path) -> dict:
    """Comparison table, failures and caveats assembled from the sections already in summary.json."""
    path = out / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hls, mcd, pri, firms = (summary.get(k, {}) for k in ("hls", "mcd64a1", "prithvi", "firms"))
    table = []
    if hls.get("status") == "ok":
        for name, threshold in THRESHOLDS.items():
            head = hls["headline_ha"][name]
            table += [
                {"method": f"HLS dNBR >= {threshold}, observed pixels only (lower bound)", "ha":
                    head["observed_only_lower_bound"]},
                {"method": f"HLS dNBR >= {threshold}, unobserved gaps inside the burned envelope filled", "ha":
                    head["gap_filled_envelope"]},
                {"method": f"HLS dNBR >= {threshold}, terrain-shadow pixels included (noisier)", "ha":
                    head["terrain_shadow_included"]},
                {"method": f"HLS dNBR >= {threshold}, observed only, clipped to the requested AOI", "ha":
                    head["observed_only_in_requested_aoi"]},
            ]
    if mcd.get("status") == "ok":
        table.append({"method": "MODIS MCD64A1 Jul+Aug 2026, all burned 500 m pixels in the analysis AOI",
                      "ha": mcd["burned_ha_jul_aug"], "pixels": mcd["burned_pixels_jul_aug"]})
        cmp_ = mcd.get("comparison_with_dnbr", {})
        if cmp_:
            table.append({"method": "MODIS MCD64A1 Jul+Aug 2026, patches touching the hotspot buffer (30 m grid)",
                          "ha": cmp_["mcd64a1_hotspot_anchored_area_on_30m_grid_ha"]})
            table.append({"method": "MODIS MCD64A1 Jul+Aug 2026, inside the requested AOI (30 m grid)",
                          "ha": cmp_["mcd64a1_in_requested_aoi_on_30m_grid_ha"]})
    if pri.get("status") == "ok":
        table.append({"method": "Prithvi-EO-2.0-300M-BurnScars (out-of-domain), whole analysis AOI",
                      "ha": pri["burned_ha_whole_aoi"]})
        if "burned_ha_hotspot_anchored" in pri:
            table.append({"method": "Prithvi-EO-2.0-300M-BurnScars (out-of-domain), hotspot-anchored patches",
                          "ha": pri["burned_ha_hotspot_anchored"]})

    agreement = {}
    if mcd.get("comparison_with_dnbr"):
        c = mcd["comparison_with_dnbr"]
        agreement["mcd64a1_vs_dnbr"] = {k.replace("_vs_mcd64a1", ""): {m: v[m] for m in (
            "iou", "fraction_of_a_in_b", "fraction_of_b_in_a", "area_ratio_b_over_a")}
            for k, v in c.items() if k.endswith("_vs_mcd64a1")}
        agreement["mcd64a1_vs_dnbr_note"] = ("a = HLS dNBR mask, b = MCD64A1; fraction_of_a_in_b = share of the dNBR "
                                             "burned area inside MCD64A1 burned pixels")
    if pri.get("status") == "ok":
        agreement["prithvi_anchored_vs_dnbr"] = {k.replace("vs_dnbr_", "").replace("_hotspot_anchored", ""): {
            m: v[m] for m in ("iou", "fraction_of_a_in_b", "fraction_of_b_in_a", "area_ratio_b_over_a")}
            for k, v in pri.items() if k.startswith("vs_dnbr_") and k.endswith("_hotspot_anchored")}
    if hls.get("sensitivity_other_post_dates"):
        alt = hls["sensitivity_other_post_dates"][0]
        if "areas_ha" in alt:
            agreement["post_date_sensitivity"] = {
                "alternative_post": alt["post_scene"]["date"],
                "moderate_observed_ha": alt["areas_ha"]["moderate"]["hotspot_anchored"],
                "low_observed_ha": alt["areas_ha"]["low"]["hotspot_anchored"],
                "iou_moderate_with_main": alt["overlap_with_main_moderate"]["iou"]}

    caveats = []
    if hls.get("status") == "ok":
        vf = hls["valid_fraction"]
        caveats += [
            f"Only {vf['hotspot_buffer_both']:.0%} of the 1 km hotspot buffer is observed on both HLS dates with "
            "standard Fmask masking; almost all of the rest is flagged 'water' by Fmask, which here is deep terrain "
            "shadow on steep slopes under the low winter sun (median pre-fire NIR reflectance of those pixels "
            f"{hls['masked_in_hotspot_buffer'].get('nir_median_of_water_flagged_pre')}), not water. The "
            "observed-only areas are therefore lower bounds.",
            "dNBR thresholds come from forest and shrubland calibrations (Key & Benson 2006); this is sparse arid "
            "Monte/Puna vegetation with low pre-fire NBR, so dNBR values are compressed and the area roughly doubles "
            f"between >= 0.27 and >= 0.10 ({hls['headline_ha']['moderate']['observed_only_lower_bound']} vs "
            f"{hls['headline_ha']['low']['observed_only_lower_bound']} ha). Quote a range, not a single number.",
            f"The dNBR offset (median dNBR far from hotspots) is small ({hls['dnbr_offset']['fmask_standard']}), so "
            "the phenology/illumination change between 14 Jul and 7 Aug is not driving the result.",
            "The requested AOI (west edge -67.75) cuts the western part of the fire; the analysis AOI extends to "
            "-67.90. Areas clipped to the requested AOI are also given.",
            "Burned patches are kept only if they touch a 1 km buffer of nominal/high-confidence FIRMS hotspots of "
            "27 Jul-10 Aug; burned ground never detected by FIRMS (e.g. under smoke or between overpasses) can be "
            "missed, and unrelated change touching the buffer is included.",
            "No field perimeter or official CONAE figure was available to validate any of these numbers.",
        ]
    if mcd.get("status") == "ok":
        last = firms.get("last_day")
        late = {d: n for m in mcd["months"] for d, n in m["burn_dates"].items()
                if last and date.fromisoformat(d) > date.fromisoformat(last) + timedelta(days=7)}
        caveats.append("MCD64A1 maps 500 m (21.5 ha) cells as wholly burned, so it includes unburned patches and "
                       "shadowed slopes inside burned cells; its area is expected to exceed the 30 m dNBR area."
                       + (f" {sum(late.values())} MCD64A1 pixels have burn dates more than a week after the last "
                          f"FIRMS hotspot ({last}): {late}; they may belong to other events." if late else ""))
    if pri.get("status") == "ok":
        by_flag = pri.get("burned_ha_whole_aoi_by_post_fmask", {})
        caveats.append(f"Prithvi BurnScars was fine-tuned on US burn scars. Here it labels {pri['burned_ha_whole_aoi']} "
                       f"ha of the analysis AOI as burned ({by_flag.get('clear')} ha on Fmask-clear pixels, "
                       f"{by_flag.get('water_bit_terrain_shadow')} ha on terrain shadow, "
                       f"{by_flag.get('cloud_adjacent_or_cloud_shadow')} ha on clouds and their shadows, "
                       f"{by_flag.get('snow_ice')} ha on snow): smooth blobs over unburned mountain slopes, irrigated "
                       "fields and cloud/snow areas, some with straight chip edges. It does cover almost all of the "
                       "dNBR burned area (high recall, low precision) and is reported only as an out-of-domain test.")
    failures = [
        "The rasterio wheel in packages/nina/.venv has no HDF4 driver, so MCD64A1 was read with pyhdf in the scratch "
        "environment (python -m nina.io.burn_case --steps mcd64a1 with that interpreter).",
        "LP DAAC returned one transient HTTP 502; downloads retry 429/5xx and network errors.",
        "Local DNS stopped resolving NASA hosts for about 20 minutes; CMR answers are now cached under "
        "source/downloads/burn_case/cmr and already-downloaded granules are reused offline.",
        "Prithvi and MCD64A1 need torch/terratorch and pyhdf, which are not packages/nina dependencies; they ran in a "
        "separate scratch virtual environment.",
    ]
    figures = list(hls.get("products", {}).get("figures", [])) + list(pri.get("figures", []))
    return {
        "status": "ok",
        "burned_area_ha": table,
        "agreement": agreement,
        "caveats": caveats,
        "failures_and_workarounds": failures,
        "figures": figures,
        "figure_legends": {"hls": hls.get("products", {}).get("figure_legend"), "prithvi": pri.get("figure_legend")},
        "step_timings_s": {k: summary.get(k, {}).get("timings_s") for k in ("firms", "hls", "mcd64a1", "prithvi")},
        "software": {k: summary.get(k, {}).get("software") for k in ("hls", "mcd64a1", "prithvi")},
        "hotspots": {k: firms.get(k) for k in ("hotspots_used", "first_day", "last_day", "by_product")},
    }


# --------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, default=Path("../.."))
    parser.add_argument("--steps", default="firms,hls,mcd64a1,overview",
                        help="comma list of firms,hls,mcd64a1,prithvi,overview")
    parser.add_argument("--pre", default=DEFAULT_PRE, help="pre-fire HLS date (YYYY-MM-DD)")
    parser.add_argument("--post", default=DEFAULT_POST, help="post-fire HLS date (YYYY-MM-DD)")
    parser.add_argument("--sensitivity-posts", default=",".join(DEFAULT_SENSITIVITY_POSTS),
                        help="extra post-fire dates for a sensitivity check (comma list, may be empty)")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    out = workspace / "source/context/burn_case"
    downloads = workspace / "source/downloads/burn_case"
    out.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    global CMR_CACHE, LOCAL_HLS
    CMR_CACHE = downloads / "cmr"
    LOCAL_HLS = downloads / "hls"
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    for step in steps:
        started = time.perf_counter()
        if step == "firms":
            payload = step_firms(workspace, out, downloads)
        elif step == "hls":
            extra = tuple(d for d in args.sensitivity_posts.split(",") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
            payload = step_hls(workspace, out, downloads, args.pre, args.post, extra)
        elif step == "mcd64a1":
            payload = step_mcd64a1(workspace, out, downloads)
        elif step == "prithvi":
            payload = step_prithvi(workspace, out, downloads, args.post)
        elif step == "overview":
            payload = step_overview(workspace, out)
        else:
            raise SystemExit(f"unknown step {step!r}")
        payload.setdefault("timings_s", {})["wall"] = round(time.perf_counter() - started, 1)
        previous = json.loads((out / "summary.json").read_text(encoding="utf-8")).get(step, {})             if (out / "summary.json").exists() else {}
        if payload.get("status") == "skipped" and previous.get("status") == "ok":
            # e.g. mcd64a1 run from an interpreter without pyhdf: keep the earlier successful result.
            print(f"[{step}] skipped ({payload.get('reason')}); keeping the previous result")
            continue
        update_summary(out, step, payload)
        print(f"[{step}] {payload.get('status')}" + (f": {payload['reason']}" if payload.get("reason") else ""))


if __name__ == "__main__":
    main()
