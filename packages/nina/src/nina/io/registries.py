"""Registered fire incidents outside Peru, normalised to one point table per country.

Output: ``source/context/registries/<name>.parquet`` with ``record_id, day, year, latitude, longitude, size_ha``
(plus ``region_code`` for area registries) and ``<name>.json`` with the source, coverage and the minimum size
the report counts. Every input row is either kept or counted as excluded with a reason.

* usa_nifc: NIFC/WFIGS wildfire incident locations (IRWIN; wildfires only, from 2014 in practice).
* australia: Geoscience Australia bushfire polygons (Historic Boundaries v2.0 to 2020-06-30, Extents 2020-25),
  centroids; bushfires only (prescribed burns excluded).
* indonesia_bnpb: BNPB/DIBI forest and land fire records through the DesInventar export (to 2019), at the
  centroid of the regency; zones are the regency H3 cells.
* brazil_ibama_roi: IBAMA/Prevfogo fire occurrence records (federal brigades, 2015-2022), by municipality.
"""

from __future__ import annotations

import argparse
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

ACRE_HA = 0.40468564224
WFIGS_URL = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0"
AU_URLS = ["https://services-ap1.arcgis.com/ypkPEy1AmwPKGNNv/arcgis/rest/services/Bushfire_Boundaries_Historic_Dec_view/FeatureServer/0",
           "https://services-ap1.arcgis.com/ypkPEy1AmwPKGNNv/arcgis/rest/services/Historical_Bushfire_Extents_2020%E2%80%9325_View/FeatureServer"]
DESINVENTAR_URL = "https://www.desinventar.net/DesInventar/download/DI_export_idn.zip"


def log(step: str, **fields: Any) -> None:
    print(json.dumps({"step": step, **fields}, default=str), flush=True)


def epoch_days(values: pd.Series) -> pd.Series:
    return pd.to_datetime(pd.to_numeric(values, errors="coerce"), unit="ms", utc=True).dt.tz_localize(None).dt.normalize()


def finish(frame: pd.DataFrame, read: int, reasons: dict[str, int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = frame.assign(year=frame["day"].dt.year).sort_values("day").reset_index(drop=True)
    excluded = {k: int(v) for k, v in reasons.items() if v}
    assert read == len(frame) + sum(excluded.values()), (read, len(frame), excluded)
    return frame, {"rows_read": read, "records": int(len(frame)), "excluded": excluded,
                   "coverage": [str(frame["day"].min())[:10], str(frame["day"].max())[:10]]}


def usa_nifc(raw: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = pd.read_csv(raw / "wfigs_wf.csv")
    read = len(data)
    data["day"] = epoch_days(data["FireDiscoveryDateTime"])
    no_point = data["x"].isna() | data["y"].isna() | ~data["y"].between(15, 75) | ~data["x"].between(-180, -60)
    no_date = data["day"].isna() & ~no_point
    keep = data[~no_point & ~no_date]
    frame = pd.DataFrame({"record_id": keep["UniqueFireIdentifier"].fillna(keep["OBJECTID"].astype(str)),
                          "day": keep["day"], "latitude": keep["y"], "longitude": keep["x"],
                          "size_ha": pd.to_numeric(keep["IncidentSize"], errors="coerce") * ACRE_HA,
                          "region_code": keep["POOState"]})
    frame, summary = finish(frame, read, {"no_point": int(no_point.sum()), "no_date": int(no_date.sum())})
    return frame, {"name": "usa_nifc", "source_name": "NIFC/WFIGS wildfire incident locations (IRWIN)",
                   "url": WFIGS_URL, "license": "US Government public data (NIFC disclaimer)",
                   "kind": "point of origin of reported wildfires (WF); prescribed fires excluded",
                   "min_size_ha": 40.0, "size_note": "the report counts incidents of at least 40 ha (about 100 acres)",
                   "note": "IRWIN records start in 2014; 2012-2013 are not in the registry", **summary}


def australia(raw: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    parts = []
    for name in ["historic_v2_2012_2020.csv", "extents_2020_25_layer3.csv", "extents_2020_25_layer0.csv"]:
        path = raw / name
        if path.exists():
            parts.append(pd.read_csv(path).assign(source_file=name))
    data = pd.concat(parts, ignore_index=True)
    read = len(data)
    data["day"] = epoch_days(data["ignition_date"])
    no_point = data["x"].isna() | data["y"].isna()
    no_date = data["day"].isna() & ~no_point
    keep = data[~no_point & ~no_date]
    duplicate = keep.duplicated(subset=["fire_id", "day"], keep="first") & keep["fire_id"].notna()
    keep = keep[~duplicate]
    frame = pd.DataFrame({"record_id": keep["fire_id"].fillna(keep["source_file"] + ":" + keep["OBJECTID"].astype(str)),
                          "day": keep["day"], "latitude": keep["y"], "longitude": keep["x"],
                          "size_ha": pd.to_numeric(keep["area_ha"], errors="coerce"), "region_code": keep["state"]})
    frame, summary = finish(frame, read, {"no_point": int(no_point.sum()), "no_date": int(no_date.sum()),
                                          "duplicate": int(duplicate.sum())})
    return frame, {"name": "australia", "source_name": "Geoscience Australia mapped bushfires",
                   "url": AU_URLS, "license": "CC BY 4.0",
                   "kind": "centroid of mapped bushfire boundaries (prescribed burns and unknown types excluded)",
                   "min_size_ha": 0.0, "note": "Historic Boundaries v2.0 to 2020-06-30 (no Northern Territory), "
                   "Bushfire Extents 2020-25 afterwards (all states)", **summary}


def indonesia_bnpb(raw: Path) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    archive_path = raw / "DI_export_idn.zip"
    rows, read_all = [], 0
    with zipfile.ZipFile(archive_path) as archive:
        section = None
        with archive.open("DI_export_idn.xml") as handle:
            for event, element in ET.iterparse(handle, events=("start", "end")):
                if event == "start" and element.tag in ("fichas", "lev0", "lev1", "lev2", "regiones", "extension"):
                    section = element.tag
                if event == "end" and element.tag == "TR":
                    if section == "fichas":
                        read_all += 1
                        record = {child.tag: (child.text or "").strip() for child in element}
                        if record.get("evento", "").upper() == "KEBAKARAN HUTAN DAN LAHAN":
                            rows.append(record)
                    element.clear()
    data = pd.DataFrame(rows)
    read = len(data)
    day = pd.to_datetime(dict(year=pd.to_numeric(data["fechano"], errors="coerce"),
                              month=pd.to_numeric(data["fechames"], errors="coerce").clip(1, 12),
                              day=pd.to_numeric(data["fechadia"], errors="coerce").clip(1, 31)), errors="coerce")
    data["day"] = day
    regions = gpd.read_file(f"zip://{archive_path.as_posix()}!id1.shp")
    regions = regions.set_crs(4326) if regions.crs is None else regions.to_crs(4326)  # the export ships no .prj (degrees)
    code_column = next(c for c in regions.columns if c.lower() in ("kode_kab", "lev1_cod", "id1", "code"))
    regions["region_code"] = pd.to_numeric(regions[code_column], errors="coerce").astype("Int64").astype(str)
    centroids = regions.geometry.representative_point()
    lookup = pd.DataFrame({"region_code": regions["region_code"], "latitude": centroids.y, "longitude": centroids.x})
    data["region_code"] = data["level1"].astype(str)
    no_date = data["day"].isna()
    unknown_region = ~data["region_code"].isin(set(lookup["region_code"])) & ~no_date
    keep = data[~no_date & ~unknown_region].drop(columns=["latitude", "longitude"], errors="ignore").merge(
        lookup, on="region_code", how="left")  # record coordinates are mostly empty: use the regency point
    frame = pd.DataFrame({"record_id": keep.get("serial", pd.Series(range(len(keep)))).astype(str),
                          "day": keep["day"], "latitude": keep["latitude"], "longitude": keep["longitude"],
                          "size_ha": pd.to_numeric(keep.get("nhectareas"), errors="coerce").replace(0, np.nan),
                          "region_code": keep["region_code"]})
    frame["record_id"] = frame["record_id"].where(frame["record_id"] != "", None).fillna(
        pd.Series([f"idn-{i}" for i in range(len(frame))]))
    frame, summary = finish(frame, read, {"no_date": int(no_date.sum()), "unknown_region": int(unknown_region.sum())})
    used = set(frame["region_code"])
    zone_rows = []
    for code, geometry in zip(regions["region_code"], regions.geometry, strict=True):
        if code not in used or geometry is None:
            continue
        cells = h3.geo_to_cells(geometry.__geo_interface__, 7) or {h3.latlng_to_cell(geometry.representative_point().y,
                                                                                    geometry.representative_point().x, 7)}
        zone_rows += [(code, cell) for cell in cells]
    zones = pd.DataFrame(zone_rows, columns=["key", "cell"])
    manifest = {"name": "indonesia_bnpb", "source_name": "BNPB/DIBI forest and land fire records (DesInventar export)",
                "url": DESINVENTAR_URL, "license": "CC BY (UNDRR DesInventar, via HDX)",
                "kind": "disaster records by regency (kabupaten), placed at the regency's representative point",
                "min_size_ha": 0.0, "records_in_export": read_all,
                "note": "the export ends in 2019 and under-records large seasons (2015: 46 records)", **summary}
    return frame, manifest, zones


UF_CODES = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
            24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
            41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
ROI_URL = "https://dadosabertos.ibama.gov.br/dados/SISFOGO/ROI.csv"


def fold(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(plain.upper().replace("-", " ").replace("'", " ").split())


def brazil_ibama_roi(raw: Path) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    """IBAMA/Prevfogo fire occurrence records (one fire per SEQ), placed at their municipality."""
    columns = ["SEQ OCORRENCIA INCENDIO", "UF", "MUNICIPIO", "DATA/HORA INICIO FOGO", "QTD AREA ATINGIDA"]
    data = pd.read_csv(raw / "ROI.csv", sep=";", dtype=str, encoding="utf-8", encoding_errors="replace", usecols=columns)
    rows_read = len(data)
    data = data.drop_duplicates("SEQ OCORRENCIA INCENDIO")
    item_rows = rows_read - len(data)
    read = len(data)
    data["day"] = pd.to_datetime(data["DATA/HORA INICIO FOGO"], dayfirst=True, errors="coerce").dt.normalize()
    bad_date = data["day"].isna() | ~data["day"].dt.year.between(2012, 2026)
    municipalities = pd.read_csv(raw / "municipios.csv", dtype={"codigo_ibge": str})
    municipalities["uf"] = municipalities["codigo_uf"].map(UF_CODES)
    municipalities["key"] = municipalities["uf"] + "|" + municipalities["nome"].map(fold)
    lookup = municipalities.drop_duplicates("key").set_index("key")
    data["key"] = data["UF"].str.strip().str.upper() + "|" + data["MUNICIPIO"].map(fold)
    unknown = ~data["key"].isin(lookup.index) & ~bad_date
    keep = data[~bad_date & ~unknown].copy()
    keep = keep.join(lookup[["codigo_ibge", "latitude", "longitude"]], on="key")
    area = pd.to_numeric(keep["QTD AREA ATINGIDA"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                         errors="coerce")
    frame = pd.DataFrame({"record_id": "roi-" + keep["SEQ OCORRENCIA INCENDIO"].astype(str), "day": keep["day"],
                          "latitude": keep["latitude"], "longitude": keep["longitude"], "size_ha": area,
                          "region_code": keep["codigo_ibge"]})
    frame, summary = finish(frame, read, {"invalid_date": int(bad_date.sum()), "unknown_municipality": int(unknown.sum())})
    polygons = gpd.read_file(raw / "geojs-100-mun.json")
    polygons["region_code"] = polygons["id"].astype(str)
    used = set(frame["region_code"])
    zone_rows = []
    for code, geometry in zip(polygons["region_code"], polygons.geometry, strict=True):
        if code in used and geometry is not None:
            cells = h3.geo_to_cells(geometry.__geo_interface__, 7)
            zone_rows += [(code, cell) for cell in cells]
    zones = pd.DataFrame(zone_rows, columns=["key", "cell"])
    missing = used - set(zones["key"])
    for code in missing:  # municipalities created after 2010: their representative point
        row = frame[frame["region_code"] == code].iloc[0]
        zones.loc[len(zones)] = [code, h3.latlng_to_cell(row["latitude"], row["longitude"], 7)]
    manifest = {"name": "brazil_ibama_roi", "source_name": "IBAMA/Prevfogo fire occurrence records (SISFOGO ROI)",
                "url": ROI_URL, "license": "Creative Commons Attribution (dadosabertos.ibama.gov.br)",
                "kind": "fires attended by federal brigades (not civil-defence emergencies), by municipality",
                "min_size_ha": 0.0, "rows_in_file": rows_read, "item_rows_collapsed": item_rows,
                "municipalities_without_2010_polygon": len(missing),
                "note": "S2iD civil-defence records could not be retrieved automatically (portal blocks scripted access); "
                        "this registry covers federal brigade operations, mostly 2016-2020", **summary}
    return frame, manifest, zones


def write(context: Path, frame: pd.DataFrame, manifest: dict[str, Any], zones: pd.DataFrame | None = None) -> None:
    folder = context / "registries"
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(folder / f"{manifest['name']}.parquet", index=False)
    if zones is not None:
        zones.to_parquet(folder / f"{manifest['name']}_zones.parquet", index=False)
    manifest = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), **manifest}
    (folder / f"{manifest['name']}.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    log("registry", name=manifest["name"], records=manifest["records"], excluded=manifest["excluded"],
        coverage=manifest["coverage"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("names", nargs="+", choices=["usa_nifc", "australia", "indonesia_bnpb", "brazil_ibama_roi"])
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    downloads = workspace / "source/downloads/validation"
    context = workspace / "source/context"
    for name in args.names:
        if name == "usa_nifc":
            write(context, *usa_nifc(downloads / "usa_wfigs"))
        elif name == "australia":
            write(context, *australia(downloads / "australia_bushfires"))
        elif name == "brazil_ibama_roi":
            write(context, *brazil_ibama_roi(downloads / "brazil_ibama_roi"))
        else:
            frame, manifest, zones = indonesia_bnpb(downloads / "indonesia_desinventar")
            write(context, frame, manifest, zones)


if __name__ == "__main__":
    main()
