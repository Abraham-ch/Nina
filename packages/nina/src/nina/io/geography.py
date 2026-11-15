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
import shapely.affinity
from pyproj import Geod
from scipy.spatial import cKDTree

from nina.config import H3_RES, STATIC_SOURCE_H3_RES, VOLCANO_BUFFER_KM

BATCH_SIZE = 50_000
VOLCANO_BUFFER_METERS = VOLCANO_BUFFER_KM * 1000
# 1: polígonos tal cual. 2: corte en el antimeridiano y ajuste a la costa (ADR 0005).
COUNTRY_METHOD = 2
# Tolerancia para centros de celda en tierra que caen fuera de la costa generalizada 1:110m.
COUNTRY_SNAP_DEGREES = 0.25
POLAR_LATITUDE = 89.9
HALF_TURN = 180.0


def split_antimeridian(geometry: Any) -> Any:
    """Corta en ±180° las partes que lo cruzan en lugar de cubrir una franja de todo el globo.

    Una parte con más de 180° de ancho (Rusia/Chukotka, Fiyi) se desenrolla sumando 360° a sus
    longitudes negativas, se recorta en 180° y la porción oriental se devuelve a [-180, 180].
    Las partes polares (Antártida) se dejan intactas.
    """
    parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    fixed = []
    offset = np.array([2 * HALF_TURN, 0.0])
    for part in parts:
        west, south, east, north = part.bounds
        if east - west <= HALF_TURN or south <= -POLAR_LATITUDE or north >= POLAR_LATITUDE:
            fixed.append(part)
            continue
        shifted = shapely.transform(part, lambda xy: np.where(xy[:, :1] < 0, xy + offset, xy))
        shifted = shapely.make_valid(shifted)
        inside = shifted.intersection(shapely.box(-HALF_TURN, -90, HALF_TURN, 90))
        beyond = shifted.intersection(shapely.box(HALF_TURN, -90, 3 * HALF_TURN, 90))
        fixed.append(shapely.union(inside, shapely.affinity.translate(beyond, xoff=-2 * HALF_TURN)))
    return shapely.union_all(fixed)


def country_layer(features: list[dict[str, Any]]) -> tuple[Any, shapely.STRtree]:
    """Nombres y árbol de países con el corte del antimeridiano aplicado."""
    names = np.array([f["properties"]["name"] for f in features], dtype=object)
    shapes = [split_antimeridian(shapely.geometry.shape(f["geometry"])) for f in features]
    return names, polygon_tree(shapes)


def assign_countries(points: Any, names: Any, tree: shapely.STRtree) -> Any:
    """País del centro de celda; los puntos costeros fuera del contorno 1:110m se ajustan al más
    cercano dentro de `COUNTRY_SNAP_DEGREES`. Lo que queda fuera sigue como `unassigned`."""
    countries = np.full(len(points), "unassigned", dtype=object)
    pi, gi = intersects(tree, points)
    countries[pi] = names[gi]
    missing = np.flatnonzero(countries == "unassigned")
    if len(missing):
        qi, gi = tree.query_nearest(points[missing], max_distance=COUNTRY_SNAP_DEGREES)
        _, first = np.unique(qi, return_index=True)
        countries[missing[qi[first]]] = names[gi[first]]
    return countries


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
    countries = country_features(workspace)
    country_names, country_tree = country_layer(countries)
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
        "country_names": country_names,
        "country_tree": country_tree,
        "volcano_coordinates": coordinates,
        "volcano_tree": cKDTree(sphere(coordinates[:, 1], coordinates[:, 0])),
        "geod": Geod(ellps="WGS84"),
    }


def country_features(workspace: Path) -> list[dict[str, Any]]:
    """Contornos nacionales de referencia (Natural Earth 1:110m derivado por la web)."""
    country_file = workspace / "web/public/assets/countries.geojson"
    return list(json.loads(country_file.read_text(encoding="utf-8"))["features"])


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
    pi, gi = intersects(layers["eco_tree"], parent_points)
    biomes[pi] = layers["eco_biomes"][gi]
    ecoregions[pi] = layers["eco_ids"][gi]
    countries = assign_countries(parent_points, layers["country_names"], layers["country_tree"])
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
    refresh = verify_geography_cache(connection, workspace, folder, destination)
    literal = "'" + str(destination).replace("'", "''") + "'"
    if destination.exists():
        connection.execute(
            f"CREATE OR REPLACE TABLE cells AS SELECT * FROM read_parquet({literal})"
        )
        if refresh:
            refresh_countries(connection, workspace)
            connection.execute(f"COPY cells TO {literal} (FORMAT PARQUET,COMPRESSION ZSTD)")
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


def refresh_countries(connection: duckdb.DuckDBPyConnection, workspace: Path) -> None:
    """Recalcula solo el país de las celdas en caché cuando cambia `COUNTRY_METHOD`.

    El resultado es idéntico al de una clasificación completa con el método vigente: el país
    depende únicamente del centro de la celda analítica y de los contornos nacionales.
    """
    names, tree = country_layer(country_features(workspace))
    parents = [str(row[0]) for row in connection.execute("SELECT DISTINCT cell FROM cells").fetchall()]
    lat_lon = np.array([h3.cell_to_latlng(cell) for cell in parents])
    countries = assign_countries(shapely.points(lat_lon[:, 1], lat_lon[:, 0]), names, tree)
    connection.register("country_frame", pd.DataFrame({"cell": parents, "country": countries}))
    connection.execute("""UPDATE cells SET country=f.country FROM country_frame f
        WHERE cells.cell=f.cell AND cells.country IS DISTINCT FROM f.country""")
    connection.unregister("country_frame")
    connection.execute("CHECKPOINT")
    print(json.dumps({"event": "countries_refreshed", "cells": len(parents)}), flush=True)


def verify_geography_cache(
    connection: duckdb.DuckDBPyConnection, workspace: Path, folder: Path, destination: Path
) -> bool:
    """Evita reutilizar máscaras calculadas con otra grilla, buffer o fuente.

    Devuelve `True` cuando el caché sirve pero su asignación de países usa un método anterior.
    """
    auxiliary = json.loads((workspace / "source/auxiliary-inputs.json").read_text(encoding="utf-8"))

    def signature(parameters: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "parameters": {
                key: parameters[key]
                for key in ["h3_resolution", "static_resolution", "volcano_buffer_km"]
            },
            "sources": [
                list(item)
                for item in sorted(
                    (s["file"], s["sha256"], s.get("derived_sha256")) for s in sources
                )
            ],
        }

    expected = signature(
        {
            "h3_resolution": H3_RES,
            "static_resolution": STATIC_SOURCE_H3_RES,
            "volcano_buffer_km": VOLCANO_BUFFER_KM,
        },
        auxiliary,
    )
    metadata = folder / "geography-cache.json"
    previous: dict[str, Any] | None = None
    previous_method = 1
    if metadata.exists():
        stored = json.loads(metadata.read_text(encoding="utf-8"))
        previous = json.loads(stored["signature"])
        previous_method = int(stored.get("country_method", 1))
    elif (folder / "prepared.json").exists():
        prepared = json.loads((folder / "prepared.json").read_text(encoding="utf-8"))
        previous = signature(prepared["filter_configuration"], prepared["auxiliaries"])
    refresh = False
    if previous != expected:
        destination.resolve().relative_to((workspace / "source/interim").resolve())
        destination.unlink(missing_ok=True)
        connection.execute("DROP TABLE IF EXISTS cells")
    else:
        refresh = previous_method != COUNTRY_METHOD and destination.exists()
    metadata.write_text(
        json.dumps(
            {"signature": json.dumps(expected, sort_keys=True), "country_method": COUNTRY_METHOD}
        ),
        encoding="utf-8",
    )
    return refresh
