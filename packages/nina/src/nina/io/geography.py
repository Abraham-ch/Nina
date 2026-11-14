"""Clasificación geográfica por bloques y polígonos preparados en memoria."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import shapely
from pyproj import Geod
from scipy.spatial import cKDTree

from nina.config import H3_RES, STATIC_SOURCE_H3_RES, VOLCANO_BUFFER_KM

BATCH_SIZE = 50_000
VOLCANO_BUFFER_METERS = VOLCANO_BUFFER_KM * 1000


def polygon_tree(geometries: Any) -> shapely.STRtree:
    """Prepara los polígonos, evitando repetir millones de vértices por punto."""
    array = np.asarray(geometries, dtype=object).copy()
    invalid = ~shapely.is_valid(array)
    array[invalid] = shapely.make_valid(array[invalid])
    shapely.prepare(array)
    return shapely.STRtree(array)


def intersects(tree: shapely.STRtree, points: Any) -> Any:
    """Primero cajas; después predicado con el polígono preparado a la izquierda."""
    pi, gi = tree.query(points)
    keep = shapely.intersects(tree.geometries[gi], points[pi])
    return np.array([pi[keep], gi[keep]])


def load_layers(workspace: Path) -> dict[str, Any]:
    """Lee cada capa auxiliar una sola vez."""
    aux = workspace / "source/auxiliary"
    eco = gpd.read_file(f"zip://{aux / 'ecoregions2017.zip'}")
    urban_file = "GHS_STAT_UCDB2015MT_GLOBE_R2019A/GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.gpkg"
    urban = gpd.read_file(f"zip://{aux / 'ghsl-urban-2015.zip'}!{urban_file}").to_crs(4326)
    land = [
        polygon_tree(
            gpd.read_file(
                f"zip://{aux / 'gshhg.zip'}!GSHHS_shp/i/GSHHS_i_L{level}.shp",
                columns=["geometry"],
            ).geometry.values
        )
        for level in [1, 2, 3, 4]
    ]
    country_file = workspace / "web/public/assets/countries.geojson"
    countries = json.loads(country_file.read_text(encoding="utf-8"))["features"]
    volcanoes = json.loads((aux / "volcanoes.geojson").read_text(encoding="utf-8"))["features"]
    coordinates = np.array([f["geometry"]["coordinates"] for f in volcanoes])
    return {
        "eco": eco,
        "eco_biomes": eco["BIOME_NUM"].to_numpy(dtype=int),
        "eco_ids": eco["ECO_ID"].to_numpy(dtype=int),
        "eco_tree": polygon_tree(eco.geometry.values),
        "urban_tree": polygon_tree(urban.geometry.values),
        "land": land,
        "countries": countries,
        "country_names": np.array([f["properties"]["name"] for f in countries], dtype=object),
        "country_tree": polygon_tree([shapely.geometry.shape(f["geometry"]) for f in countries]),
        "volcano_coordinates": coordinates,
        "volcano_tree": cKDTree(sphere(coordinates[:, 1], coordinates[:, 0])),
        "geod": Geod(ellps="WGS84"),
    }


def sphere(latitude: Any, longitude: Any) -> Any:
    """Coordenadas de esfera unitaria para búsqueda del volcán más cercano."""
    lat, lon = np.radians(latitude), np.radians(longitude)
    return np.c_[np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]


def classify(ids: list[str], layers: dict[str, Any]) -> pd.DataFrame:
    """Máscara en res. 8; país y bioma del centro de la unidad analítica res. 7."""
    lat_lon = np.array([h3.cell_to_latlng(cell) for cell in ids])
    lat, lon = lat_lon[:, 0], lat_lon[:, 1]
    points = shapely.points(lon, lat)
    parents = [str(h3.cell_to_parent(cell, H3_RES)) for cell in ids]
    parent_lat_lon = np.array([h3.cell_to_latlng(cell) for cell in parents])
    parent_points = shapely.points(parent_lat_lon[:, 1], parent_lat_lon[:, 0])
    biomes, ecoregions = np.zeros(len(ids), dtype=int), np.zeros(len(ids), dtype=int)
    countries = np.full(len(ids), "unassigned", dtype=object)
    pi, gi = intersects(layers["eco_tree"], parent_points)
    biomes[pi] = layers["eco_biomes"][gi]
    ecoregions[pi] = layers["eco_ids"][gi]
    pi, gi = intersects(layers["country_tree"], parent_points)
    countries[pi] = layers["country_names"][gi]
    urban = np.zeros(len(ids), dtype=bool)
    urban[intersects(layers["urban_tree"], points)[0]] = True
    land = []
    for tree in layers["land"]:
        flags = np.zeros(len(ids), dtype=bool)
        flags[intersects(tree, points)[0]] = True
        land.append(flags)
    _, nearest = layers["volcano_tree"].query(sphere(lat, lon))
    coordinates = layers["volcano_coordinates"][nearest]
    _, _, meters = layers["geod"].inv(lon, lat, coordinates[:, 0], coordinates[:, 1])
    return pd.DataFrame(
        {
            "cell8": ids,
            "cell": parents,
            "latitude": lat,
            "longitude": lon,
            "country": countries,
            "biome": biomes,
            "ecoregion": ecoregions,
            "urban": urban,
            "water": (~land[0] | land[1]) & ~land[2] | land[3],
            "volcano": meters <= VOLCANO_BUFFER_METERS,
        }
    )


def cell_geography(connection: duckdb.DuckDBPyConnection, workspace: Path, folder: Path) -> None:
    """Reanuda por celda tras una interrupción; publica el caché al terminar."""
    destination = folder / "cell_geography.parquet"
    verify_geography_cache(connection, workspace, folder, destination)
    literal = "'" + str(destination).replace("'", "''") + "'"
    if destination.exists():
        connection.execute(
            f"CREATE OR REPLACE TABLE cells AS SELECT * FROM read_parquet({literal})"
        )
    connection.execute("""CREATE TABLE IF NOT EXISTS cells(cell8 VARCHAR,cell VARCHAR,
        latitude DOUBLE,longitude DOUBLE,country VARCHAR,biome INTEGER,ecoregion INTEGER,
        urban BOOLEAN,water BOOLEAN,volcano BOOLEAN)""")
    reader = connection.cursor()
    reader.execute("""SELECT DISTINCT cell8 FROM normalized n
        WHERE NOT EXISTS(SELECT 1 FROM cells c WHERE c.cell8=n.cell8) ORDER BY cell8""")
    first = reader.fetchmany(BATCH_SIZE)
    if first:
        print('{"event":"loading_auxiliary_geometries"}', flush=True)
        layers = load_layers(workspace)
        print('{"event":"auxiliary_geometries_ready"}', flush=True)
        chunk = first
        while chunk:
            frame = classify([str(row[0]) for row in chunk], layers)
            connection.register("geo_batch", frame)
            connection.execute("INSERT INTO cells SELECT * FROM geo_batch")
            connection.unregister("geo_batch")
            connection.execute("CHECKPOINT")
            print(json.dumps({"event": "geography_batch", "cells": len(chunk)}), flush=True)
            chunk = reader.fetchmany(BATCH_SIZE)
    reader.close()
    connection.execute(f"COPY cells TO {literal} (FORMAT PARQUET,COMPRESSION ZSTD)")


def verify_geography_cache(
    connection: duckdb.DuckDBPyConnection, workspace: Path, folder: Path, destination: Path
) -> None:
    """Evita reutilizar máscaras calculadas con otra grilla, buffer o fuente."""
    auxiliary = json.loads((workspace / "source/auxiliary-inputs.json").read_text(encoding="utf-8"))

    def signature(parameters: dict[str, Any], sources: list[dict[str, Any]]) -> str:
        return json.dumps(
            {
                "parameters": {
                    key: parameters[key]
                    for key in ["h3_resolution", "static_resolution", "volcano_buffer_km"]
                },
                "sources": sorted(
                    (s["file"], s["sha256"], s.get("derived_sha256")) for s in sources
                ),
            },
            sort_keys=True,
        )

    expected = signature(
        {
            "h3_resolution": H3_RES,
            "static_resolution": STATIC_SOURCE_H3_RES,
            "volcano_buffer_km": VOLCANO_BUFFER_KM,
        },
        auxiliary,
    )
    metadata = folder / "geography-cache.json"
    previous = None
    if metadata.exists():
        previous = json.loads(metadata.read_text(encoding="utf-8"))["signature"]
    elif (folder / "prepared.json").exists():
        prepared = json.loads((folder / "prepared.json").read_text(encoding="utf-8"))
        previous = signature(prepared["filter_configuration"], prepared["auxiliaries"])
    if previous != expected:
        destination.resolve().relative_to((workspace / "source/interim").resolve())
        destination.unlink(missing_ok=True)
        connection.execute("DROP TABLE IF EXISTS cells")
    metadata.write_text(json.dumps({"signature": expected}), encoding="utf-8")
