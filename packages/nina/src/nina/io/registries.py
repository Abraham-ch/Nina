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
* canada_cnfdb: Canadian National Fire Database agency fire points (provinces, territories, Parks Canada);
  prescribed burns excluded.
* portugal_icnf: ICNF/SGIF national rural fire records at the ignition point (mainland Portugal).
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


def retrieved(path: Path) -> str:
    """Download date of a source file (its modification time, UTC)."""
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat()


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


NFDB_URL = "https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_pnt/current_version/NFDB_point_txt.zip"
NFDB_CAUSES = {"H": "human", "N": "natural", "U": "unknown"}
CANADA_BOX = (41.0, 84.0, -142.0, -52.0)  # lat_min, lat_max, lon_min, lon_max


def canada_cnfdb(raw: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """CNFDB agency fire points (one row per fire), dated by the report date; prescribed burns excluded."""
    with zipfile.ZipFile(raw / "NFDB_point_txt.zip") as archive:
        member = next(n for n in archive.namelist() if n.lower().endswith(".txt"))
        with archive.open(member) as handle:
            data = pd.read_csv(handle, dtype=str, encoding="utf-8-sig", encoding_errors="replace", keep_default_na=False)
    read = len(data)
    text = {c: data[c].str.strip() for c in ("NFDBFIREID", "SRC_AGENCY", "FIRE_TYPE", "PRESCRIBED", "CAUSE")}
    latitude = pd.to_numeric(data["LATITUDE"], errors="coerce")
    longitude = pd.to_numeric(data["LONGITUDE"], errors="coerce")
    reported = pd.to_datetime(data["REP_DATE"].str[:10], format="%Y-%m-%d", errors="coerce")
    year = pd.to_numeric(data["YEAR"], errors="coerce")
    declared = pd.to_datetime(dict(year=year, month=pd.to_numeric(data["MONTH"], errors="coerce"),
                                   day=pd.to_numeric(data["DAY"], errors="coerce")), errors="coerce")
    # The report date is the fire date; where its year contradicts the agency's YEAR (a typed year), or it is
    # missing, the agency's YEAR/MONTH/DAY is used instead.
    use_declared = declared.notna() & (reported.isna() | (reported.dt.year != year))
    data["day"] = reported.where(~use_declared, declared)
    prescribed = text["PRESCRIBED"].str.upper().isin({"PB", "1", "YES", "Y"}) | \
        text["FIRE_TYPE"].str.upper().isin({"PB", "PRESCRIBED BURN"})
    lat_min, lat_max, lon_min, lon_max = CANADA_BOX
    no_point = ~prescribed & ~(latitude.between(lat_min, lat_max) & longitude.between(lon_min, lon_max))
    no_date = ~prescribed & ~no_point & data["day"].isna()
    data = data.assign(record_key=text["NFDBFIREID"], latitude=latitude, longitude=longitude,
                       region_code=text["SRC_AGENCY"], cause=text["CAUSE"].map(NFDB_CAUSES).fillna(text["CAUSE"]))
    keep = data[~prescribed & ~no_point & ~no_date]
    duplicate = keep.duplicated(subset=["record_key", "day", "latitude", "longitude", "SIZE_HA"], keep="first")
    keep = keep[~duplicate]
    # Some agencies reuse a fire number within a year for different fires: keep both, with a unique id.
    repeat = keep.groupby("record_key").cumcount()
    record_id = keep["record_key"].where(repeat == 0, keep["record_key"] + "#" + repeat.astype(str))
    size = pd.to_numeric(keep["SIZE_HA"], errors="coerce")
    frame = pd.DataFrame({"record_id": record_id, "day": keep["day"], "latitude": keep["latitude"],
                          "longitude": keep["longitude"], "size_ha": size.where(size >= 0),
                          "region_code": keep["region_code"], "cause": keep["cause"]})
    frame, summary = finish(frame, read, {"prescribed_burn": int(prescribed.sum()), "no_point": int(no_point.sum()),
                                          "no_date": int(no_date.sum()), "duplicate": int(duplicate.sum())})
    return frame, {"name": "canada_cnfdb", "source_name": "Canadian National Fire Database (CNFDB), agency fire points",
                   "url": NFDB_URL, "license": "Open Government Licence - Canada (source: Natural Resources Canada, "
                   "Canadian Forest Service, must be acknowledged)",
                   "kind": "point of origin of fires reported by provincial, territorial and Parks Canada agencies; "
                           "prescribed burns excluded",
                   "region_code": "reporting agency (province or territory code; PC = Parks Canada)",
                   "min_size_ha": 40.0, "size_note": "the report counts fires of at least 40 ha (about 100 acres); "
                   "agencies record many spot fires under 1 ha",
                   "release": member, "retrieved": retrieved(raw / "NFDB_point_txt.zip"),
                   "dated_by_year_month_day": int(use_declared[keep.index].sum()),
                   "repeated_fire_numbers": int((repeat > 0).sum()),
                   "note": "coverage and completeness vary by agency and year; the current version ends with the last "
                           "season the agencies have submitted", **summary}


SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ICNF_URL = "https://www.icnf.pt/florestas/gfr/gfrgestaoinformacao/estatisticas"
ICNF_FILES = {"12-Registos-Incendios-SGIF-2001-2010.zip": "https://www.icnf.pt/api/file/doc/6f1861934bbc866f",
              "13-Registos-Incendios-SGIF-2011-2020.zip": "https://www.icnf.pt/api/file/doc/c77d0e2c5bb91f1c",
              "RegistoIncendiosSGIF-2021-2025.zip": "https://www.icnf.pt/api/file/doc/8b2adaf3ea9b42ab"}
ICNF_CAUSES = {"Negligente": "negligent", "Intencional": "intentional", "Natural": "natural",
               "Desconhecida": "unknown", "Reacendimento": "rekindle"}
ICNF_COLUMNS = ["Codigo_SGIF", "Ano", "Mes", "Dia", "DataHoraAlerta", "AreaTotal_ha", "DTCCFR", "Latitude", "Longitude",
                "TipoCausa"]
PORTUGAL_BOX = (36.8, 42.2, -9.6, -6.1)  # mainland Portugal (the SGIF area)


def xlsx_columns(workbook: zipfile.ZipFile, columns: list[str]) -> pd.DataFrame:
    """Named columns of the first sheet of an .xlsx, as text, streamed (an SGIF sheet is tens of MB of XML)."""
    from nina.io.xlsx import column_index

    strings = ["".join(t.text or "" for t in item.iter(f"{SHEET_NS}t"))
               for item in ET.fromstring(workbook.read("xl/sharedStrings.xml")).findall(f"{SHEET_NS}si")]
    positions: list[int] | None = None
    rows: list[list[str | None]] = []
    with workbook.open("xl/worksheets/sheet1.xml") as handle:
        for _, element in ET.iterparse(handle):
            if element.tag != f"{SHEET_NS}row":
                continue
            values: dict[int, str] = {}
            for cell in element.iter(f"{SHEET_NS}c"):
                value, kind = cell.find(f"{SHEET_NS}v"), cell.get("t")
                if kind == "inlineStr":
                    values[column_index(cell.get("r"))] = "".join(t.text or "" for t in cell.iter(f"{SHEET_NS}t"))
                elif value is not None and value.text is not None:
                    values[column_index(cell.get("r"))] = strings[int(value.text)] if kind == "s" else value.text
            element.clear()
            if positions is None:
                header = {name.strip(): index for index, name in values.items()}
                missing = [c for c in columns if c not in header]
                if missing:
                    raise ValueError(f"columns {missing} not in the sheet header {sorted(header)}")
                positions = [header[c] for c in columns]
            elif values:
                rows.append([values.get(i) for i in positions])
    return pd.DataFrame(rows, columns=columns)


def portugal_icnf(raw: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """ICNF/SGIF national rural fire records (one row per fire), at the ignition point, dated by the alert date."""
    parts, files = [], {}
    for path in sorted(raw.glob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            member = next(n for n in archive.namelist() if n.lower().endswith(".xlsx"))
            with archive.open(member) as handle, zipfile.ZipFile(handle) as workbook:
                part = xlsx_columns(workbook, ICNF_COLUMNS)
        parts.append(part.assign(source_file=path.name))
        files[path.name] = {"url": ICNF_FILES.get(path.name), "rows": int(len(part)), "retrieved": retrieved(path)}
    data = pd.concat(parts, ignore_index=True)
    read = len(data)
    latitude = pd.to_numeric(data["Latitude"], errors="coerce")
    longitude = pd.to_numeric(data["Longitude"], errors="coerce")
    # Ano/Mes/Dia is the (local) calendar date of the alert; the alert timestamp is the fallback.
    declared = pd.to_datetime(dict(year=pd.to_numeric(data["Ano"], errors="coerce"),
                                   month=pd.to_numeric(data["Mes"], errors="coerce"),
                                   day=pd.to_numeric(data["Dia"], errors="coerce")), errors="coerce")
    alert = pd.to_datetime(pd.to_numeric(data["DataHoraAlerta"], errors="coerce"), unit="D", origin="1899-12-30")
    data["day"] = declared.fillna(alert.dt.normalize())
    lat_min, lat_max, lon_min, lon_max = PORTUGAL_BOX
    no_point = ~(latitude.between(lat_min, lat_max) & longitude.between(lon_min, lon_max))
    no_date = ~no_point & data["day"].isna()
    data = data.assign(latitude=latitude, longitude=longitude, code=data["Codigo_SGIF"].str.strip())
    keep = data[~no_point & ~no_date]
    duplicate = keep["code"].notna() & keep.duplicated(subset=["code"], keep="first")
    keep = keep[~duplicate]
    record_id = keep["code"].fillna(pd.Series([f"pt-{i}" for i in keep.index], index=keep.index))
    parish_code = pd.to_numeric(keep["DTCCFR"], errors="coerce")
    parish = parish_code.astype("Int64").astype(str).str.zfill(6).where(parish_code.notna())
    area = pd.to_numeric(keep["AreaTotal_ha"], errors="coerce")
    frame = pd.DataFrame({"record_id": record_id, "day": keep["day"], "latitude": keep["latitude"],
                          "longitude": keep["longitude"], "size_ha": area.where(area >= 0),
                          "region_code": parish,
                          "cause": keep["TipoCausa"].str.strip().map(ICNF_CAUSES)})
    frame, summary = finish(frame, read, {"no_point": int(no_point.sum()), "no_date": int(no_date.sum()),
                                          "duplicate": int(duplicate.sum())})
    expected = set(ICNF_FILES) - set(files)
    note = "the SGIF records every rural fire attended in mainland Portugal (most under 1 ha); dates are local"
    if expected:
        note += (f"; not downloaded: {', '.join(sorted(expected))} (the ICNF file service ended each transfer "
                 "after 300 s, before these 62-87 MB archives were complete)")
    return frame, {"name": "portugal_icnf", "source_name": "ICNF national rural fire database (SGIF), individual records",
                   "url": ICNF_URL, "files": files,
                   "license": "ICNF terms (icnf.pt/avisoslegais): free to copy and use for personal or educational "
                              "purposes, citing the source; not for profit",
                   "kind": "ignition point of rural fires (forest, shrub and agricultural), including rekindles",
                   "region_code": "INE code of the parish (freguesia) of the ignition point; the first two digits are "
                                  "the district",
                   "min_size_ha": 40.0, "size_note": "the report counts fires of at least 40 ha (about 100 acres)",
                   "note": note, **summary}


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
    parser.add_argument("names", nargs="+", choices=["usa_nifc", "australia", "indonesia_bnpb", "brazil_ibama_roi",
                                                     "canada_cnfdb", "portugal_icnf"])
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
        elif name == "canada_cnfdb":
            write(context, *canada_cnfdb(downloads / "canada_cnfdb"))
        elif name == "portugal_icnf":
            write(context, *portugal_icnf(downloads / "portugal_icnf"))
        else:
            frame, manifest, zones = indonesia_bnpb(downloads / "indonesia_desinventar")
            write(context, frame, manifest, zones)


if __name__ == "__main__":
    main()
