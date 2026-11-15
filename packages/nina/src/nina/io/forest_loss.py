"""Annual tree-cover loss per H3 cell for Peru, from Hansen/UMD Global Forest Change.

Source: Hansen, M. C. et al. (2013), "High-Resolution Global Maps of 21st-Century Forest Cover
Change", Science 342: 850-853, updated yearly (GFC-<year>-v1.<n>, CC BY 4.0). The product ships as
10° x 10° GeoTIFF tiles of 40000 x 40000 pixels (1 arc-second, 0.00025°, about 30 m at the
equator), named after their north-west corner.

Definitions:

* Forest in 2000: ``treecover2000 >= FOREST_THRESHOLD`` (30 % canopy closure).
* Loss in year ``y``: ``lossyear == y - 2000`` (codes 1..N, N = last year of the version) on a
  forest pixel. Loss outside forest is ignored. Loss is "stand-replacement disturbance"; it is
  not deforestation (it includes fire, logging, plantation harvest and natural disturbance) and
  it is never netted against regrowth.
* Pixel area: exact area of the latitude/longitude quadrilateral on the WGS84 ellipsoid, one
  value per raster row (a pixel is ~0.077 ha at the equator and ~0.073 ha at 18° S).

Aggregation (two stages, so H3 is never evaluated per pixel):

1. Tiles are read in bands of whole rows (the files are LZW strips of one row; a tile is never
   loaded whole). Each band is reduced to a regular grid of ``GRID_PIXELS`` x ``GRID_PIXELS``
   pixel blocks (default 40 px = 0.01°, ~1.1 km): forest-2000 hectares and loss hectares per
   year.
2. Each block is assigned whole to the H3 resolution-7 cell that contains the block centre
   (``h3.latlng_to_cell``), and blocks are summed per cell.

Approximation: an H3 res-7 cell in Peru (~5.9 km², edge ~1.3 km) receives about five 0.01°
blocks, but depending on how the block lattice falls on the hexagon it can receive four to seven.
A block that straddles a hexagon edge is credited entirely to one side, so per-cell values are
blurred by up to one block width (~1 km) along cell boundaries. In fully forested lowlands the
ratio forest_2000_ha / cell area spans about 0.7-1.3 (5th-95th percentile) at 0.01°, 0.75-1.1
at 0.005° (``--grid-pixels 20``) and 0.75-1.04 at 0.0025°; the manifest records the spread
under ``diagnostics``. Every block goes to exactly one cell, so area is conserved: sums over
groups of cells (districts, departments, the country) are unaffected apart from the cells at
the edge of the group, and per-cell ratios such as loss / forest_2000 are much less affected
than absolute hectares.

Peru selection: the cells of the fire grid labelled ``country = 'Peru'`` (``grid_cells.parquet``
of a reviewed product) plus every res-7 cell whose centre lies inside the union of the
geoBoundaries ADM1 departments. Cells with no fire are kept, because forest loss is reported
for the territory, not only where fires were detected. Border cells are kept whole, so they may
include some pixels from neighbouring countries (and the fire grid, which used a 1:110m coastline
with snapping, adds a few cells just across the border).

Run from ``packages/nina``::

    uv run python -m nina.io.forest_loss --workspace ../.. --download
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import h3
import h3.api.basic_int as h3_int
import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
import shapely
from numpy.typing import NDArray
from rasterio.windows import Window

from nina.config import H3_RES
from nina.io.acquire import public_client
from nina.io.harmonization import log, read_json, write_json

HANSEN_BUCKET = "https://storage.googleapis.com/earthenginepartners-hansen"
DEFAULT_VERSION = "GFC-2024-v1.12"
LAYERS = ("treecover2000", "lossyear")
# North-west corners of the 10° tiles covering lat 0..-20, lon -90..-60.
PERU_TILES = ("00N_090W", "00N_080W", "00N_070W", "10S_090W", "10S_080W", "10S_070W")
TILE_DEGREES = 10.0
TILE_PIXELS = 40_000
FIRST_LOSS_YEAR = 2001
FOREST_THRESHOLD = 30
GRID_PIXELS = 20  # 0.005 deg: narrower per-cell spread than 0.01 deg at the same cost
BAND_ROWS = 400
SELECTION_MARGIN_DEGREES = 0.05
HECTARE_M2 = 10_000.0
WGS84_A = 6_378_137.0
WGS84_F = 1 / 298.257223563
MAX_ATTEMPTS = 4
CHUNK_BYTES = 1 << 20
HTTP_NOT_FOUND = 404
HTTP_PARTIAL = 206
VERSION_PATTERN = re.compile(r"^GFC-(\d{4})-v1\.(\d+)$")

GRID_CELLS = Path("source/review/e9f9a7a7a47bd640f9d27999/grid_cells.parquet")
DEPARTMENTS = Path("data/boundaries/departments.geojson")
AUXILIARY_DIR = Path("source/auxiliary/hansen")
OUTPUT_DIR = Path("source/context/forest_loss")
CITATION = (
    "Hansen, M. C., P. V. Potapov, R. Moore, M. Hancher, S. A. Turubanova, A. Tyukavina, "
    "D. Thau, S. V. Stehman, S. J. Goetz, T. R. Loveland, A. Kommareddy, A. Egorov, L. Chini, "
    "C. O. Justice, and J. R. G. Townshend. 2013. High-Resolution Global Maps of 21st-Century "
    "Forest Cover Change. Science 342 (15 November): 850-53. Data available on-line from: "
    "https://glad.earthengine.app/view/global-forest-change."
)


# --------------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------------


def last_loss_year(version: str) -> int:
    """Last loss year covered by a GFC version name, e.g. ``GFC-2024-v1.12`` -> 2024."""
    match = VERSION_PATTERN.match(version)
    if not match:
        raise ValueError(f"Unexpected GFC version name: {version}")
    return int(match.group(1))


def next_version(version: str) -> str:
    """Name of the following yearly release, e.g. ``GFC-2024-v1.12`` -> ``GFC-2025-v1.13``."""
    match = VERSION_PATTERN.match(version)
    if not match:
        raise ValueError(f"Unexpected GFC version name: {version}")
    return f"GFC-{int(match.group(1)) + 1}-v1.{int(match.group(2)) + 1}"


def tile_url(version: str, layer: str, tile: str) -> str:
    """Public URL of one GFC tile."""
    return f"{HANSEN_BUCKET}/{version}/Hansen_{version}_{layer}_{tile}.tif"


def tile_bounds(tile: str) -> tuple[float, float, float, float]:
    """``(west, south, east, north)`` of a tile named after its north-west corner."""
    match = re.fullmatch(r"(\d{2})([NS])_(\d{3})([EW])", tile)
    if not match:
        raise ValueError(f"Unexpected tile name: {tile}")
    north = float(match.group(1)) * (1 if match.group(2) == "N" else -1)
    west = float(match.group(3)) * (1 if match.group(4) == "E" else -1)
    return west, north - TILE_DEGREES, west + TILE_DEGREES, north


def decode_loss_year(code: NDArray[Any], last_year: int) -> NDArray[np.int32]:
    """Calendar year of loss for ``lossyear`` codes; 0 where there is no (valid) loss."""
    code = np.asarray(code).astype(np.int32)
    valid = (code >= 1) & (code <= last_year - 2000)
    return np.where(valid, code + 2000, 0).astype(np.int32)


def _authalic_term(latitude_deg: NDArray[np.float64]) -> NDArray[np.float64]:
    """Primitive of the ellipsoid area element in latitude (Snyder 1987, eq. 3-12)."""
    e2 = WGS84_F * (2 - WGS84_F)
    e = math.sqrt(e2)
    s = np.sin(np.radians(latitude_deg))
    return np.asarray(s / (1 - e2 * s * s) + np.log((1 + e * s) / (1 - e * s)) / (2 * e))


def quad_area_ha(
    north_deg: NDArray[np.float64] | float, south_deg: NDArray[np.float64] | float, dlon_deg: float
) -> NDArray[np.float64]:
    """Exact WGS84 area (ha) of quads bounded by two parallels and ``dlon_deg`` of longitude."""
    b2 = (WGS84_A * (1 - WGS84_F)) ** 2
    north = np.asarray(north_deg, dtype=np.float64)
    south = np.asarray(south_deg, dtype=np.float64)
    band = np.abs(_authalic_term(north) - _authalic_term(south))
    return np.asarray(b2 / 2 * math.radians(abs(dlon_deg)) * band / HECTARE_M2)


def row_pixel_area_ha(top_deg: float, pixel_deg: float, rows: int) -> NDArray[np.float64]:
    """Area (ha) of one pixel in each of ``rows`` rows that start at latitude ``top_deg``."""
    north = top_deg - pixel_deg * np.arange(rows, dtype=np.float64)
    return quad_area_ha(north, north - pixel_deg, pixel_deg)


def aggregate_window(
    treecover: NDArray[np.uint8],
    lossyear: NDArray[np.uint8],
    row_area_ha: NDArray[np.float64],
    *,
    grid_pixels: int = GRID_PIXELS,
    threshold: int = FOREST_THRESHOLD,
    n_years: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Reduce a band of pixels to grid blocks.

    Returns ``forest_ha`` with shape ``(block_rows, block_cols)`` and ``loss_ha`` with shape
    ``(block_rows, block_cols, n_years)``, where index ``k`` of the last axis is year
    ``2001 + k``. The band height and width must be multiples of ``grid_pixels``.
    """
    height, width = treecover.shape
    if height % grid_pixels or width % grid_pixels or lossyear.shape != treecover.shape:
        raise ValueError("Window shape must be a multiple of the grid block and match layers")
    block_rows, block_cols = height // grid_pixels, width // grid_pixels
    forest = treecover >= threshold
    per_row = np.count_nonzero(forest.reshape(height, block_cols, grid_pixels), axis=2)
    forest_ha = (per_row * row_area_ha[:, None]).reshape(block_rows, grid_pixels, block_cols)
    rows, cols = np.nonzero(forest & (lossyear >= 1) & (lossyear <= n_years))
    codes = lossyear[rows, cols].astype(np.int64)
    flat = ((rows // grid_pixels) * block_cols + cols // grid_pixels) * n_years + codes - 1
    loss = np.bincount(flat, weights=row_area_ha[rows], minlength=block_rows * block_cols * n_years)
    return forest_ha.sum(axis=1), loss.reshape(block_rows, block_cols, n_years)


@dataclass(frozen=True)
class BlockTable:
    """Sparse grid-block aggregates: blocks with forest, and loss rows ``(block, year, ha)``."""

    latitude: NDArray[np.float64]
    longitude: NDArray[np.float64]
    forest_ha: NDArray[np.float64]
    loss_block: NDArray[np.int64]
    loss_year: NDArray[np.int32]
    loss_ha: NDArray[np.float64]

    @staticmethod
    def concat(tables: list[BlockTable]) -> BlockTable:
        """Stack tables, re-indexing ``loss_block``."""
        offsets = np.cumsum([0] + [len(t.forest_ha) for t in tables])[:-1]
        return BlockTable(
            latitude=np.concatenate([t.latitude for t in tables]),
            longitude=np.concatenate([t.longitude for t in tables]),
            forest_ha=np.concatenate([t.forest_ha for t in tables]),
            loss_block=np.concatenate(
                [t.loss_block + o for t, o in zip(tables, offsets, strict=True)]
            ),
            loss_year=np.concatenate([t.loss_year for t in tables]),
            loss_ha=np.concatenate([t.loss_ha for t in tables]),
        )

    def select(self, keep: NDArray[np.bool_]) -> BlockTable:
        """Keep a subset of blocks (and their loss rows)."""
        new_index = np.cumsum(keep) - 1
        rows = keep[self.loss_block]
        return BlockTable(
            latitude=self.latitude[keep],
            longitude=self.longitude[keep],
            forest_ha=self.forest_ha[keep],
            loss_block=new_index[self.loss_block[rows]],
            loss_year=self.loss_year[rows],
            loss_ha=self.loss_ha[rows],
        )


def sparse_blocks(
    forest_ha: NDArray[np.float64],
    loss_ha: NDArray[np.float64],
    *,
    top_deg: float,
    left_deg: float,
    block_deg: float,
) -> BlockTable:
    """Block centres and non-zero values of a dense block grid whose corner is (top, left)."""
    rows, cols = np.nonzero(forest_ha > 0)
    index = np.full(forest_ha.shape, -1, dtype=np.int64)
    index[rows, cols] = np.arange(len(rows))
    loss_rows, loss_cols, years = np.nonzero(loss_ha > 0)
    return BlockTable(
        latitude=(top_deg - (rows + 0.5) * block_deg).astype(np.float64),
        longitude=(left_deg + (cols + 0.5) * block_deg).astype(np.float64),
        forest_ha=forest_ha[rows, cols],
        loss_block=index[loss_rows, loss_cols],
        loss_year=(years + FIRST_LOSS_YEAR).astype(np.int32),
        loss_ha=loss_ha[loss_rows, loss_cols, years],
    )


def cells_for_points(
    latitude: NDArray[np.float64], longitude: NDArray[np.float64], resolution: int = H3_RES
) -> NDArray[np.int64]:
    """H3 index (integer form) of each point."""
    return np.fromiter(
        (h3_int.latlng_to_cell(y, x, resolution) for y, x in zip(latitude, longitude, strict=True)),
        dtype=np.int64,
        count=len(latitude),
    )


def blocks_to_cells(blocks: BlockTable, resolution: int = H3_RES) -> tuple[pd.Series, pd.DataFrame]:
    """Sum block values per H3 cell: forest hectares per cell and loss rows ``cell, year``."""
    cells = cells_for_points(blocks.latitude, blocks.longitude, resolution)
    forest = pd.Series(blocks.forest_ha).groupby(cells).sum()
    loss = (
        pd.DataFrame(
            {"cell": cells[blocks.loss_block], "year": blocks.loss_year, "loss_ha": blocks.loss_ha}
        )
        .groupby(["cell", "year"], as_index=False)["loss_ha"]
        .sum()
    )
    return forest, loss


def select_cells(
    forest: pd.Series, loss: pd.DataFrame, universe: NDArray[np.int64]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Restrict to ``universe`` cells, as output tables with string cell ids.

    Every universe cell appears in the forest table (0 ha where no forest block was assigned);
    only loss rows with ``loss_ha > 0`` are kept.
    """
    universe = np.unique(universe)
    forest_table = pd.DataFrame(
        {"cell": universe, "forest_2000_ha": forest.reindex(universe, fill_value=0.0).to_numpy()}
    )
    loss_table = loss[loss["cell"].isin(universe) & (loss["loss_ha"] > 0)]
    loss_table = loss_table.sort_values(["cell", "year"]).reset_index(drop=True)
    for table in (forest_table, loss_table):
        table["cell"] = [h3.int_to_str(int(c)) for c in table["cell"]]
    return forest_table, loss_table


def totals_by_year(loss: pd.DataFrame, first: int, last: int) -> dict[str, float]:
    """Loss hectares per calendar year, including years with no loss."""
    by_year = loss.groupby("year")["loss_ha"].sum()
    return {str(y): round(float(by_year.get(y, 0.0)), 1) for y in range(first, last + 1)}


# --------------------------------------------------------------------------------------------
# I/O: download and verification
# --------------------------------------------------------------------------------------------


def relative(path: Path, workspace: Path) -> str:
    """Workspace-relative POSIX path for manifests."""
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def digests(path: Path) -> tuple[str, str]:
    """``(sha256 hex, md5 base64)`` of a file, read in blocks."""
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        while block := stream.read(8 * CHUNK_BYTES):
            sha.update(block)
            md5.update(block)
    return sha.hexdigest(), base64.b64encode(md5.digest()).decode()


def remote_metadata(client: httpx.Client, url: str) -> dict[str, Any] | None:
    """Size, MD5 and date of a bucket object, or ``None`` when it does not exist (HTTP 404)."""
    response = client.head(url)
    if response.status_code == HTTP_NOT_FOUND:
        return None
    response.raise_for_status()
    hashes: dict[str, str] = {}
    for value in response.headers.get_list("x-goog-hash"):
        for item in value.split(","):
            key, _, digest = item.strip().partition("=")
            hashes[key] = digest
    return {
        "bytes": int(response.headers["content-length"]),
        "md5": hashes.get("md5"),
        "last_modified": response.headers.get("last-modified"),
    }


def fetch(client: httpx.Client, url: str, path: Path, expected_bytes: int) -> None:
    """Download to ``<path>.part`` with HTTP Range resume, then rename atomically."""
    part = path.with_name(path.name + ".part")
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(MAX_ATTEMPTS):
        offset = part.stat().st_size if part.exists() else 0
        if offset > expected_bytes:
            part.unlink()
            offset = 0
        try:
            if offset < expected_bytes:
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    append = offset > 0 and response.status_code == HTTP_PARTIAL
                    with part.open("ab" if append else "wb") as stream:
                        for block in response.iter_bytes(CHUNK_BYTES):
                            stream.write(block)
            if part.stat().st_size == expected_bytes:
                part.replace(path)
                return
        except httpx.HTTPError as error:
            log("hansen_retry", file=path.name, attempt=attempt + 1, error=type(error).__name__)
        time.sleep(2 * (attempt + 1))
    raise ValueError(f"Could not download {path.name} after {MAX_ATTEMPTS} attempts")


def check_tile(path: Path, tile: str) -> None:
    """Fail unless the file is a single-band uint8 GeoTIFF with the tile's grid."""
    with rasterio.open(path) as source:
        bounds = source.bounds
        ok = (
            source.count == 1
            and source.dtypes[0] == "uint8"
            and source.width == source.height == TILE_PIXELS
            and np.allclose(
                [bounds.left, bounds.bottom, bounds.right, bounds.top], tile_bounds(tile), atol=1e-9
            )
        )
    if not ok:
        raise ValueError(f"{path.name} is not the expected {tile} GFC tile")


def newest_version(client: httpx.Client, version: str, probe_tile: str) -> str:
    """Latest consecutive yearly release found in the bucket, starting from ``version``."""
    newest = version
    candidate = next_version(version)
    while remote_metadata(client, tile_url(candidate, LAYERS[0], probe_tile)) is not None:
        newest, candidate = candidate, next_version(candidate)
    return newest


def acquire_tiles(workspace: Path, version: str, *, download: bool) -> dict[str, Any]:
    """Download (or verify) the Peru tiles; returns and stores the inputs manifest.

    Existing complete files are reused when their size and MD5 match the bucket; partial
    ``.part`` files are resumed. Objects listed by UMD but absent from the bucket are recorded as
    ``missing_upstream``. Without ``download`` the stored manifest is reused and only sizes and
    SHA-256 are checked.
    """
    folder = workspace / AUXILIARY_DIR / version
    manifest_path = folder / "inputs.json"
    if not download:
        if not manifest_path.exists():
            raise ValueError(f"No Hansen inputs at {relative(folder, workspace)}; use --download")
        manifest: dict[str, Any] = read_json(manifest_path)
        for item in manifest["files"]:
            if item["status"] == "missing_upstream":
                continue
            path = workspace / item["path"]
            if not path.exists() or path.stat().st_size != item["bytes"]:
                raise ValueError(f"{item['path']} is missing or incomplete; use --download")
            if digests(path)[0] != item["sha256"]:
                raise ValueError(f"{item['path']} does not match its recorded SHA-256")
        return manifest
    files = []
    with public_client() as client:
        for tile in PERU_TILES:
            for layer in LAYERS:
                url = tile_url(version, layer, tile)
                path = folder / f"Hansen_{version}_{layer}_{tile}.tif"
                entry: dict[str, Any] = {"tile": tile, "layer": layer, "url": url}
                remote = remote_metadata(client, url)
                if remote is None:
                    files.append({**entry, "status": "missing_upstream", "http_status": 404})
                    log("hansen_missing_upstream", tile=tile, layer=layer)
                    continue
                reused = path.exists() and path.stat().st_size == remote["bytes"]
                if not reused:
                    log("hansen_download", file=path.name, bytes=remote["bytes"])
                    fetch(client, url, path, remote["bytes"])
                sha256, md5 = digests(path)
                if remote["md5"] and md5 != remote["md5"]:
                    path.unlink()
                    raise ValueError(f"MD5 mismatch for {path.name}; deleted, run again")
                check_tile(path, tile)
                files.append(
                    {
                        **entry,
                        "path": relative(path, workspace),
                        "bytes": remote["bytes"],
                        "sha256": sha256,
                        "md5_base64": md5,
                        "last_modified": remote["last_modified"],
                        "status": "verified_existing" if reused else "downloaded",
                    }
                )
                log("hansen_verified", file=path.name, status=files[-1]["status"])
        newest = newest_version(client, version, PERU_TILES[1])
    manifest = {
        "version": version,
        "newest_version_in_bucket": newest,
        "checked_at": datetime.now(UTC).isoformat(),
        "tile_index": [f"{HANSEN_BUCKET}/{version}/{layer}.txt" for layer in LAYERS],
        "files": files,
    }
    write_json(manifest_path, manifest)
    return manifest


# --------------------------------------------------------------------------------------------
# I/O: raster aggregation and Peru selection
# --------------------------------------------------------------------------------------------


def aggregate_tile(
    treecover_path: Path,
    lossyear_path: Path,
    *,
    n_years: int,
    grid_pixels: int = GRID_PIXELS,
    band_rows: int = BAND_ROWS,
    threshold: int = FOREST_THRESHOLD,
) -> tuple[BlockTable, int]:
    """Stream one tile pair in row bands; returns blocks and the count of unknown loss codes."""
    if band_rows % grid_pixels:
        raise ValueError("band_rows must be a multiple of grid_pixels")
    tables, unknown_codes = [], 0
    with rasterio.open(treecover_path) as cover, rasterio.open(lossyear_path) as loss:
        if cover.transform != loss.transform or cover.shape != loss.shape:
            raise ValueError("treecover2000 and lossyear grids differ")
        transform = cover.transform
        pixel_deg = transform.a
        if not math.isclose(pixel_deg, -transform.e):
            raise ValueError("Pixels must be square in degrees")
        if cover.height % grid_pixels or cover.width % grid_pixels:
            raise ValueError("Tile size must be a multiple of grid_pixels")
        row_area = row_pixel_area_ha(transform.f, pixel_deg, cover.height)
        for top in range(0, cover.height, band_rows):
            height = min(band_rows, cover.height - top)
            window = Window(0, top, cover.width, height)
            treecover = cover.read(1, window=window)
            lossyear = loss.read(1, window=window)
            unknown_codes += int(np.count_nonzero(lossyear > n_years))
            forest_ha, loss_ha = aggregate_window(
                treecover,
                lossyear,
                row_area[top : top + height],
                grid_pixels=grid_pixels,
                threshold=threshold,
                n_years=n_years,
            )
            tables.append(
                sparse_blocks(
                    forest_ha,
                    loss_ha,
                    top_deg=transform.f - top * pixel_deg,
                    left_deg=transform.c,
                    block_deg=grid_pixels * pixel_deg,
                )
            )
    return BlockTable.concat(tables), unknown_codes


def peru_universe(workspace: Path, grid_cells: Path) -> tuple[NDArray[np.int64], dict[str, Any]]:
    """Fire-grid cells labelled Peru plus res-7 cells whose centre is inside the departments."""
    features = read_json(workspace / DEPARTMENTS)["features"]
    union = shapely.union_all([shapely.geometry.shape(f["geometry"]) for f in features])
    by_polygon = {h3.str_to_int(c) for c in h3.geo_to_cells(union, H3_RES)}
    with duckdb.connect() as connection:
        rows = connection.execute(
            "SELECT DISTINCT cell FROM read_parquet(?) WHERE country = 'Peru'", [str(grid_cells)]
        ).fetchall()
    by_fire_grid = {h3.str_to_int(row[0]) for row in rows}
    universe = np.fromiter(sorted(by_polygon | by_fire_grid), dtype=np.int64)
    summary = {
        "rule": "fire grid country='Peru' OR H3 res-7 centre inside union of ADM1 departments",
        "cells_total": len(universe),
        "cells_centre_in_departments": len(by_polygon),
        "cells_fire_grid_peru": len(by_fire_grid),
        "cells_fire_grid_only": len(by_fire_grid - by_polygon),
        "cells_departments_only": len(by_polygon - by_fire_grid),
    }
    return universe, {
        "summary": summary,
        "departments": union,
        "polygon_cells": by_polygon,
        "fire_cells": by_fire_grid,
    }


def write_parquet(table: pd.DataFrame, schema: pa.Schema, path: Path) -> dict[str, Any]:
    """Write a typed Parquet file atomically and describe it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    arrow = pa.Table.from_pandas(table, schema=schema, preserve_index=False)
    pq.write_table(arrow, temporary, compression="zstd")
    temporary.replace(path)
    return {
        "rows": len(table),
        "schema": {field.name: str(field.type) for field in schema},
        "sha256": digests(path)[0],
    }


def peru_tiles_blocks(
    workspace: Path,
    inputs: dict[str, Any],
    departments: Any,
    bbox: tuple[float, float, float, float],
    *,
    n_years: int,
    grid_pixels: int,
) -> tuple[BlockTable, dict[str, Any]]:
    """Aggregate every available tile pair and keep the blocks inside ``bbox`` (w, s, e, n)."""
    available = {(f["tile"], f["layer"]): f for f in inputs["files"]}
    tables: list[BlockTable] = []
    used: list[str] = []
    skipped: list[dict[str, str]] = []
    unknown_codes = 0
    band_rows = grid_pixels * max(1, BAND_ROWS // grid_pixels)
    for tile in PERU_TILES:
        footprint = shapely.box(*tile_bounds(tile))
        cover, loss = (available.get((tile, layer)) for layer in LAYERS)
        if cover is None or loss is None or "missing_upstream" in {cover["status"], loss["status"]}:
            if shapely.intersects(footprint, departments):
                raise ValueError(f"Tile {tile} overlaps Peru but a layer is missing upstream")
            skipped.append({"tile": tile, "reason": "layer missing upstream; no Peru land"})
            continue
        if not shapely.intersects(footprint, shapely.box(*bbox)):
            skipped.append({"tile": tile, "reason": "outside the Peru selection area"})
            continue
        blocks, unknown = aggregate_tile(
            workspace / cover["path"],
            workspace / loss["path"],
            n_years=n_years,
            grid_pixels=grid_pixels,
            band_rows=band_rows,
        )
        unknown_codes += unknown
        tables.append(blocks)
        used.append(tile)
        log("hansen_tile_done", tile=tile, blocks=len(blocks.forest_ha))
    west, south, east, north = bbox
    blocks = BlockTable.concat(tables)
    blocks = blocks.select(
        (blocks.latitude >= south)
        & (blocks.latitude <= north)
        & (blocks.longitude >= west)
        & (blocks.longitude <= east)
    )
    report = {
        "tiles_used": used,
        "tiles_skipped": skipped,
        "unknown_lossyear_pixels": unknown_codes,
    }
    return blocks, report


def diagnostics(
    forest_table: pd.DataFrame, loss_table: pd.DataFrame, fire_cells: set[int]
) -> dict[str, Any]:
    """Share of forest and loss in fire-grid cells, and the per-cell quantization spread."""
    fire = {h3.int_to_str(c) for c in fire_cells}
    in_fire_forest = forest_table["cell"].isin(fire)
    in_fire_loss = loss_table["cell"].isin(fire)
    forested = forest_table[forest_table["forest_2000_ha"] > 0]
    area_ha = np.array([h3.cell_area(c, "km^2") * 100 for c in forested["cell"]])
    ratio = forested["forest_2000_ha"].to_numpy() / area_ha
    quantiles = (5, 25, 50, 75, 95, 99)
    return {
        "forest_2000_share_in_fire_grid_cells": round(
            float(forest_table.loc[in_fire_forest, "forest_2000_ha"].sum())
            / float(forest_table["forest_2000_ha"].sum()),
            4,
        ),
        "loss_share_in_fire_grid_cells": round(
            float(loss_table.loc[in_fire_loss, "loss_ha"].sum())
            / float(loss_table["loss_ha"].sum()),
            4,
        ),
        "forest_2000_to_cell_area_ratio": {
            "note": "block quantization: values above 1 are an artefact of the grid step",
            "cells_with_forest": len(ratio),
            "cells_above_1": int(np.count_nonzero(ratio > 1)),
            "percentiles": {
                f"p{q}": round(float(v), 3)
                for q, v in zip(quantiles, np.percentile(ratio, quantiles), strict=True)
            },
        },
    }


def build(
    workspace: Path,
    version: str,
    *,
    download: bool,
    grid_cells: Path,
    grid_pixels: int = GRID_PIXELS,
) -> dict[str, Any]:
    """Acquire tiles, aggregate them and write the Peru forest-loss tables and manifest."""
    if TILE_PIXELS % grid_pixels:
        raise ValueError(f"grid_pixels must divide {TILE_PIXELS}")
    started = time.monotonic()
    last_year = last_loss_year(version)
    n_years = last_year - FIRST_LOSS_YEAR + 1
    grid_degrees = grid_pixels / 4000
    inputs = acquire_tiles(workspace, version, download=download)
    universe, selection = peru_universe(workspace, grid_cells)
    centres = np.array([h3_int.cell_to_latlng(int(c)) for c in universe])
    margin = SELECTION_MARGIN_DEGREES
    bbox = (
        float(centres[:, 1].min()) - margin,
        float(centres[:, 0].min()) - margin,
        float(centres[:, 1].max()) + margin,
        float(centres[:, 0].max()) + margin,
    )
    departments = selection["departments"]
    blocks, tile_report = peru_tiles_blocks(
        workspace, inputs, departments, bbox, n_years=n_years, grid_pixels=grid_pixels
    )
    forest, loss = blocks_to_cells(blocks)
    forest_table, loss_table = select_cells(forest, loss, universe)

    polygon_cells = np.fromiter(selection["polygon_cells"], dtype=np.int64)
    forest_poly, loss_poly = select_cells(forest, loss, polygon_cells)
    inside = shapely.contains_xy(departments, blocks.longitude, blocks.latitude)
    loss_inside = inside[blocks.loss_block]
    block_loss = pd.DataFrame(
        {"year": blocks.loss_year[loss_inside], "loss_ha": blocks.loss_ha[loss_inside]}
    )

    out = workspace / OUTPUT_DIR
    outputs = {
        "forest_loss_cell_year.parquet": write_parquet(
            loss_table,
            pa.schema([("cell", pa.string()), ("year", pa.int32()), ("loss_ha", pa.float64())]),
            out / "forest_loss_cell_year.parquet",
        ),
        "forest_2000_cell.parquet": write_parquet(
            forest_table,
            pa.schema([("cell", pa.string()), ("forest_2000_ha", pa.float64())]),
            out / "forest_2000_cell.parquet",
        ),
    }
    loss_by_year = totals_by_year(loss_table, FIRST_LOSS_YEAR, last_year)
    manifest = {
        "product": "forest_loss_peru_h3",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "name": "Hansen/UMD/Google/USGS/NASA Global Forest Change",
            "version": version,
            "newest_version_in_bucket": inputs.get("newest_version_in_bucket"),
            "landing_page": f"{HANSEN_BUCKET}/{version}/download.html",
            "license": "CC BY 4.0",
            "citation": CITATION,
            "files": inputs["files"],
        },
        "parameters": {
            "forest_rule": f"treecover2000 >= {FOREST_THRESHOLD}",
            "forest_threshold_pct": FOREST_THRESHOLD,
            "loss_rule": f"forest pixel AND lossyear in 1..{n_years} (year = 2000 + lossyear)",
            "loss_years": [FIRST_LOSS_YEAR, last_year],
            "pixel_degrees": 1 / 4000,
            "pixel_area": "exact WGS84 ellipsoid quad area, one value per raster row",
            "grid_degrees": grid_degrees,
            "grid_pixels": grid_pixels,
            "h3_resolution": H3_RES,
        },
        "method": (
            f"Tiles read in bands of whole rows; pixels reduced to {grid_degrees:g}-degree blocks "
            "(forest-2000 ha and loss ha per year); each block assigned whole to the H3 cell "
            "containing its centre (h3.latlng_to_cell) and summed per cell. Allocation along "
            "hexagon edges is blurred by up to one block; area is conserved. Border cells are "
            "kept whole."
        ),
        "cell_selection": selection["summary"],
        **tile_report,
        "outputs": outputs,
        "totals": {
            "scope": "all selected cells (fire-grid Peru + centre in departments)",
            "forest_2000_ha": round(float(forest_table["forest_2000_ha"].sum()), 1),
            "loss_ha_total": round(sum(loss_by_year.values()), 1),
            "loss_ha_by_year": loss_by_year,
        },
        "totals_centre_in_departments": {
            "scope": "only H3 cells whose centre is inside the geoBoundaries departments",
            "forest_2000_ha": round(float(forest_poly["forest_2000_ha"].sum()), 1),
            "loss_ha_by_year": totals_by_year(loss_poly, FIRST_LOSS_YEAR, last_year),
        },
        "totals_blocks_in_departments": {
            "scope": "grid blocks whose centre is inside the departments (no H3 step)",
            "forest_2000_ha": round(float(blocks.forest_ha[inside].sum()), 1),
            "loss_ha_by_year": totals_by_year(block_loss, FIRST_LOSS_YEAR, last_year),
        },
        "diagnostics": diagnostics(forest_table, loss_table, selection["fire_cells"]),
        "runtime_seconds": round(time.monotonic() - started, 1),
    }
    write_json(out / "manifest.json", manifest)
    log(
        "forest_loss_done",
        cells=len(forest_table),
        loss_rows=len(loss_table),
        seconds=manifest["runtime_seconds"],
    )
    return manifest


def main() -> None:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--download", action="store_true", help="download/verify the GFC tiles")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="GFC release name")
    parser.add_argument("--grid-cells", type=Path, default=None, help="fire grid_cells.parquet")
    parser.add_argument(
        "--grid-pixels", type=int, default=GRID_PIXELS, help="block size in pixels (20 = 0.005 deg, 40 = 0.01 deg)"
    )
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    build(
        workspace,
        args.version,
        download=args.download,
        grid_cells=args.grid_cells or workspace / GRID_CELLS,
        grid_pixels=args.grid_pixels,
    )


if __name__ == "__main__":
    main()
