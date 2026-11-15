"""Validation of the territorial context layers against independent records.

* Fire events against registered fire emergencies or incidents (INDECI for Peru; point registries
  such as NIFC/WFIGS for other countries): how many registered records coincide with a detected
  event in the same place within a few days, compared with the same place and date shifted by one
  year (chance level, which keeps location and season).
* Forest loss and climate are compared with other sources in their own functions.

Outputs go to ``source/context/validation/`` as JSON; the server and the report read them.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import h3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .territory import EVENT_GAP_DAYS, fire_events, product_folder

VIIRS_START = date(2012, 1, 20)
WINDOWS = (1, 3, 7)  # days around the registered date
THRESHOLDS = (1, 3, 5, 10)  # minimum active cell-days of the matching event
SIGNIFICANT = 5
SHIFT = 365  # chance level: same place, same season, one year earlier and later


def log(message: str, **fields: Any) -> None:
    print(json.dumps({"step": message, **fields}, default=str), flush=True)


def ring_zone(pairs: pd.DataFrame, rings: int) -> pd.DataFrame:
    """Expand (key, cell) pairs to the cells within ``rings`` H3 rings."""
    rows = [(key, neighbour) for key, cell in pairs[["key", "cell"]].itertuples(index=False)
            for neighbour in h3.grid_disk(cell, rings)]
    return pd.DataFrame(rows, columns=["key", "cell"]).drop_duplicates()


def rate(values: pd.Series, total: int) -> float | None:
    return round(float(values.sum()) / total, 4) if total else None


def detection(connection: duckdb.DuckDBPyConnection, before: int, after: int, shift: int = 0) -> pd.DataFrame:
    """For each registered record: size (cell-days) of the largest event touching its zone in the window."""
    return connection.execute(
        f"""SELECT r.record_id, max(m.size) AS size
        FROM reg r LEFT JOIN zone z USING(key)
        LEFT JOIN member m ON m.cell = z.cell
            AND m.day BETWEEN r.day + INTERVAL ({shift - before}) DAY AND r.day + INTERVAL ({shift + after}) DAY
        GROUP BY 1"""
    ).df()


def registered_share(connection: duckdb.DuckDBPyConnection, margin: int, shift: int = 0) -> tuple[int, float]:
    """Share of significant events with a registered record in their zone between start - margin and end + margin."""
    frame = connection.execute(
        f"""WITH hits AS (
            SELECT DISTINCT e.event_id FROM sig e JOIN member m USING(event_id) JOIN zone z ON z.cell = m.cell
            JOIN reg r ON r.key = z.key
                AND r.day BETWEEN e.start_day + INTERVAL ({shift - margin}) DAY
                              AND e.end_day + INTERVAL ({shift + margin}) DAY)
        SELECT (SELECT count(*) FROM sig), (SELECT count(*) FROM hits)"""
    ).fetchall()[0]
    return int(frame[0]), round(frame[1] / frame[0], 4) if frame[0] else 0.0


def match_summary(connection: duckdb.DuckDBPyConnection, before: int, after: int) -> dict[str, Any]:
    total = connection.execute("SELECT count(*) FROM reg").fetchall()[0][0]
    observed = detection(connection, before, after)
    chance = [detection(connection, before, after, shift) for shift in (-SHIFT, SHIFT)]
    rows = []
    for k in THRESHOLDS:
        rows.append({
            "min_event_cell_days": k,
            "rate": rate(observed["size"].fillna(0) >= k, total),
            "chance_rate": round(float(np.mean([rate(c["size"].fillna(0) >= k, total) for c in chance])), 4),
        })
    return {"window_days": [-before, after], "records": int(total), "by_event_size": rows,
            "sizes": observed}


def setup(connection: duckdb.DuckDBPyConnection, registry: pd.DataFrame, zone: pd.DataFrame,
          members: pd.DataFrame, events: pd.DataFrame) -> None:
    connection.register("reg_frame", registry[["record_id", "day", "key"]])
    connection.execute("CREATE OR REPLACE TEMP TABLE reg AS SELECT record_id, day::DATE AS day, key FROM reg_frame")
    connection.register("zone_frame", zone)
    connection.execute("CREATE OR REPLACE TEMP TABLE zone AS SELECT * FROM zone_frame")
    connection.register("member_frame", members)
    connection.execute("CREATE OR REPLACE TEMP TABLE member AS SELECT event_id, cell, day::DATE AS day, size FROM member_frame")
    connection.register("events_frame", events)
    connection.execute("""CREATE OR REPLACE TEMP TABLE sig AS
        SELECT event_id, start_day::DATE AS start_day, end_day::DATE AS end_day FROM events_frame""")


def peru_events(context: Path, workspace: Path) -> dict[str, Any]:
    """Fire events against INDECI forest-fire emergencies, Peru, VIIRS era."""
    connection = duckdb.connect()
    p = context.as_posix()
    emergencies = connection.execute(
        f"""SELECT code AS record_id, day::DATE AS day, ubigeo AS key, year, substr(ubigeo, 1, 2) AS department_code,
            department FROM read_parquet('{p}/indeci/forest_fire_emergencies.parquet')
        WHERE NOT date_imputed AND day >= DATE '{VIIRS_START}'"""
    ).df()
    cells = connection.execute(f"SELECT ubigeo AS key, cell FROM read_parquet('{p}/districts/cell_district.parquet')").df()
    known = set(cells["key"])
    unmatched = int((~emergencies["key"].isin(known)).sum())
    registry = emergencies[emergencies["key"].isin(known)].reset_index(drop=True)
    zone = ring_zone(cells, 1)
    last = registry["day"].max()
    events = connection.execute(
        f"""SELECT event_id, start_day, end_day, cell_days, ubigeo FROM read_parquet('{p}/events/fire_events.parquet')
        WHERE country = 'Peru' AND era = 'viirs' AND start_day >= DATE '{VIIRS_START}'"""
    ).df()
    members = connection.execute(
        f"""SELECT m.event_id, m.cell, m.day, e.cell_days AS size
        FROM read_parquet('{p}/events/event_cell_days.parquet') m
        JOIN read_parquet('{p}/events/fire_events.parquet') e USING(event_id)
        WHERE e.country = 'Peru' AND e.era = 'viirs' AND m.day >= DATE '{VIIRS_START}'"""
    ).df()
    significant = events[(events["cell_days"] >= SIGNIFICANT) & (pd.to_datetime(events["end_day"]) <= pd.Timestamp(last))]
    setup(connection, registry, zone, members, significant)
    log("peru registry", records=len(registry), unmatched=unmatched, events=len(events), significant=len(significant))

    windows = [match_summary(connection, w, w) for w in WINDOWS]
    main = next(w for w in windows if w["window_days"] == [-3, 3])
    sizes = main.pop("sizes")
    for w in windows:
        w.pop("sizes", None)
    registry = registry.merge(sizes, on="record_id", how="left")
    registry["hit"] = registry["size"].fillna(0) >= 1
    chance = detection(connection, 3, 3, SHIFT).rename(columns={"size": "chance_size"})
    registry = registry.merge(chance, on="record_id", how="left")
    registry["chance_hit"] = registry["chance_size"].fillna(0) >= 1
    by_year = (registry.groupby("year").agg(records=("hit", "size"), rate=("hit", "mean"), chance_rate=("chance_hit", "mean"))
               .round(4).reset_index().to_dict("records"))
    names = (registry[~registry["department"].str.contains("\ufffd", na=False)]
             .groupby("department_code")["department"].agg(lambda s: s.mode().iat[0]))
    by_department = (registry.groupby("department_code").agg(records=("hit", "size"), rate=("hit", "mean"),
                                                             chance_rate=("chance_hit", "mean"))
                     .round(4).reset_index().sort_values("records", ascending=False))
    by_department["department"] = by_department["department_code"].map(names)
    by_department = by_department.to_dict("records")
    share = registered_share(connection, 3)
    share_chance = np.mean([registered_share(connection, 3, s)[1] for s in (-SHIFT, SHIFT)])

    # Department-year agreement of counts (significant events vs emergencies).
    events_dy = significant.assign(year=pd.to_datetime(significant["start_day"]).dt.year,
                                   department_code=significant["ubigeo"].str[:2]).dropna(subset=["department_code"])
    a = events_dy.groupby(["department_code", "year"]).size().rename("events")
    b = registry.groupby(["department_code", "year"]).size().rename("emergencies")
    joined = pd.concat([a, b], axis=1).fillna(0)
    joined = joined[joined.index.get_level_values("year") <= pd.Timestamp(last).year - 1]  # complete years only
    rho, p_value = spearmanr(joined["events"], joined["emergencies"])
    department_totals = joined.groupby(level="department_code").sum()
    rho_departments, p_departments = spearmanr(department_totals["events"], department_totals["emergencies"])

    # Sensitivity of the clustering gap (VIIRS era cell-days).
    folder, _ = product_folder(workspace)
    cell_days = connection.execute(
        f"""SELECT cell, day, active_harmonized, source_mix FROM read_parquet('{(folder / 'harmonized_cell_day.parquet').as_posix()}')
        WHERE country = 'Peru' AND day >= DATE '{VIIRS_START}'"""
    ).df()
    sensitivity = []
    for gap in (1, EVENT_GAP_DAYS, 3):
        gap_events, gap_members = fire_events(cell_days, gap_days=gap)
        gap_members = gap_members.merge(gap_events[["event_id", "cell_days"]], on="event_id").rename(columns={"cell_days": "size"})
        gap_sig = gap_events[(gap_events["cell_days"] >= SIGNIFICANT) & (pd.to_datetime(gap_events["end_day"]) <= pd.Timestamp(last))]
        setup(connection, registry, zone, gap_members, gap_sig)
        found = detection(connection, 3, 3)
        events_n, registered = registered_share(connection, 3)
        sensitivity.append({"gap_days": gap, "events": len(gap_events), "significant_events": events_n,
                            "detection_rate_significant": rate(found["size"].fillna(0) >= SIGNIFICANT, len(registry)),
                            "registered_share_of_significant": registered})
        log("gap", **sensitivity[-1])

    sizes_main = {row["min_event_cell_days"]: row for row in main["by_event_size"]}
    headline = {
        "registry": "INDECI", "period": [str(registry["day"].min())[:10], str(pd.Timestamp(last).date())],
        "records": int(len(registry)), "window_days": [-3, 3],
        "rate": sizes_main[1]["rate"], "chance_rate": sizes_main[1]["chance_rate"],
        "rate_significant": sizes_main[SIGNIFICANT]["rate"], "chance_rate_significant": sizes_main[SIGNIFICANT]["chance_rate"],
        "registered_share": share[1], "chance_share": round(float(share_chance), 4),
        "department_total_spearman": round(float(rho_departments), 3),
    }
    return {
        "headline": headline,
        "registry": "INDECI/SINPAD forest-fire emergencies (official records with damage assessment)",
        "period": [str(registry["day"].min())[:10], str(pd.Timestamp(last).date())],
        "records_used": int(len(registry)),
        "excluded": {"unmatched_ubigeo": unmatched, "note": "districts created after the boundary layer"},
        "zone": "district cells plus a one-cell border (about 2.5 km)",
        "events": "harmonized VIIRS-era fire events (same or neighbouring H3 cell, gap of at most "
                  f"{EVENT_GAP_DAYS} days); significant = at least {SIGNIFICANT} active cell-days",
        "chance_level": "same district and date shifted by one year (earlier and later, averaged): keeps place and season",
        "detection": windows,
        "detection_main": main,
        "by_year": by_year,
        "by_department": by_department,
        "registered_share_of_significant_events": {"events": share[0], "window_days": [-3, 3], "share": share[1],
                                                   "chance_share": round(float(share_chance), 4)},
        "department_year_spearman": {"pairs": int(len(joined)), "rho": round(float(rho), 3), "p_value": float(p_value)},
        "department_total_spearman": {"departments": int(len(department_totals)), "rho": round(float(rho_departments), 3),
                                      "p_value": float(p_departments)},
        "gap_sensitivity": sensitivity,
    }


SIZE_CLASSES_HA = ((0, 40), (40, 400), (400, 4000), (4000, None))  # ~100, 1,000 and 10,000 acres


def point_registry_events(context: Path, country: str, name: str, label: str, before: int = 2, after: int = 7,
                          rings: int = 2) -> dict[str, Any]:
    """Fire events against a point registry (registries/<name>.parquet: record_id, day, latitude, longitude,
    size_ha). The zone of a record is its H3 cell plus ``rings`` rings (2 rings: about 5 km)."""
    connection = duckdb.connect()
    p = context.as_posix()
    last_event = connection.execute(
        f"SELECT max(end_day)::DATE FROM read_parquet('{p}/events/fire_events.parquet') WHERE country = ?", [country]
    ).fetchall()[0][0]
    registry = connection.execute(
        f"""SELECT record_id, day::DATE AS day, latitude, longitude, size_ha, year(day) AS year
        FROM read_parquet('{p}/registries/{name}.parquet')
        WHERE day >= DATE '{VIIRS_START}' AND day <= ? AND latitude IS NOT NULL AND longitude IS NOT NULL""",
        [last_event],
    ).df()
    zones_path = context / "registries" / f"{name}_zones.parquet"
    if zones_path.exists():
        # Area registry (records by administrative unit): the zone is every cell of the unit plus one ring.
        codes = connection.execute(f"SELECT record_id, region_code FROM read_parquet('{p}/registries/{name}.parquet')").df()
        registry = registry.merge(codes, on="record_id", how="left")
        registry["key"] = registry["region_code"].astype(str)
        zone = ring_zone(pd.read_parquet(zones_path), 1)
        zone_text = "all cells of the administrative unit plus one ring (about 2.5 km)"
    else:
        registry["key"] = registry["record_id"].astype(str)
        registry["cell"] = [h3.latlng_to_cell(lat, lon, 7) for lat, lon in zip(registry["latitude"], registry["longitude"],
                                                                                strict=True)]
        zone = ring_zone(registry[["key", "cell"]], rings)
        zone_text = f"record cell plus {rings} H3 rings (about {2.5 * rings:.0f} km)"
    events = connection.execute(
        f"""SELECT event_id, start_day, end_day, cell_days FROM read_parquet('{p}/events/fire_events.parquet')
        WHERE country = ? AND era = 'viirs' AND start_day >= DATE '{VIIRS_START}'""", [country]).df()
    members = connection.execute(
        f"""SELECT m.event_id, m.cell, m.day, e.cell_days AS size
        FROM read_parquet('{p}/events/event_cell_days.parquet') m
        JOIN read_parquet('{p}/events/fire_events.parquet') e USING(event_id)
        WHERE e.country = ? AND e.era = 'viirs' AND m.day >= DATE '{VIIRS_START}'""", [country]).df()
    first_record = registry["day"].min()
    significant = events[(events["cell_days"] >= SIGNIFICANT) & (pd.to_datetime(events["start_day"]) >= pd.Timestamp(first_record))]
    setup(connection, registry, zone, members, significant)
    log("registry", country=country, records=len(registry), events=len(events), significant=len(significant))

    observed = detection(connection, before, after).rename(columns={"size": "found"})
    chance = [detection(connection, before, after, s).rename(columns={"size": f"chance{i}"})
              for i, s in enumerate((-SHIFT, SHIFT))]
    frame = registry.merge(observed, on="record_id", how="left")
    for c in chance:
        frame = frame.merge(c, on="record_id", how="left")
    frame["hit"] = frame["found"].fillna(0) >= 1
    frame["chance_hit"] = ((frame["chance0"].fillna(0) >= 1).astype(float) + (frame["chance1"].fillna(0) >= 1)) / 2
    classes = []
    for low, high in SIZE_CLASSES_HA:
        part = frame[(frame["size_ha"] >= low) & ((frame["size_ha"] < high) if high else True)]
        classes.append({"size_ha": [low, high], "records": int(len(part)),
                        "rate": rate(part["hit"], len(part)), "chance_rate": rate(part["chance_hit"], len(part))})
    known_size = frame["size_ha"].notna().mean() >= 0.5
    sized = frame[frame["size_ha"] >= 400] if known_size else frame
    by_year = (sized.groupby("year")
               .agg(records=("hit", "size"), rate=("hit", "mean"), chance_rate=("chance_hit", "mean"))
               .round(4).reset_index().to_dict("records"))
    share = registered_share(connection, max(before, after))
    share_chance = np.mean([registered_share(connection, max(before, after), s)[1] for s in (-SHIFT, SHIFT)])
    period = [str(frame["day"].min())[:10], str(frame["day"].max())[:10]]
    return {
        "headline": {
            "registry": label, "period": period, "records": int(len(sized)), "window_days": [-before, after],
            "rate": rate(sized["hit"], len(sized)), "chance_rate": rate(sized["chance_hit"], len(sized)),
            "rate_all_sizes": rate(frame["hit"], len(frame)), "records_all_sizes": int(len(frame)),
            "registered_share": share[1], "chance_share": round(float(share_chance), 4),
            "note": ("records of at least 400 ha (about 1,000 acres); smaller fires are often below satellite detection"
                     if known_size else "all records (the registry gives no fire size)"),
        },
        "registry": label, "country": country, "period": period, "records_used": int(len(frame)),
        "zone": zone_text,
        "window_days": [-before, after],
        "chance_level": "same place and date shifted by one year (earlier and later, averaged)",
        "by_size": classes if known_size else [], "by_year": by_year,
        "registered_share_of_significant_events": {"events": share[0], "share": share[1],
                                                   "chance_share": round(float(share_chance), 4)},
    }



def fold_name(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


def department_names(context: Path) -> dict[str, str]:
    """INEI department code -> folded department name."""
    data = json.loads((context / "districts/peru_districts.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["ubigeo"][:2]: fold_name(f["properties"]["department"]) for f in data["features"]}


def forest_geobosques(context: Path, workbook: Path) -> dict[str, Any]:
    """Hansen/UMD tree-cover loss by department against MINAM Geobosques humid-Amazon-forest loss, 2001-2024."""
    from .xlsx import read_sheet

    rows = read_sheet(workbook)
    header_index = next(i for i, r in enumerate(rows) if 2001.0 in r)
    year_columns = {int(v): j for j, v in enumerate(rows[header_index]) if isinstance(v, float) and 2001 <= v <= 2024}
    geobosques: dict[str, dict[int, float]] = {}
    for row in rows[header_index + 1:]:
        if len(row) < 3 or not isinstance(row[1], str) or not row[1].strip():
            continue
        name = fold_name(row[1])
        if name.startswith(("TOTAL", "FUENTE")):
            break
        values = {y: float(row[j]) for y, j in year_columns.items() if j < len(row) and isinstance(row[j], float)}
        if len(values) == len(year_columns):
            geobosques[name] = values
    names = department_names(context)
    codes = {name: code for code, name in names.items()}
    connection = duckdb.connect()
    p = context.as_posix()
    hansen = connection.execute(
        f"""SELECT substr(d.ubigeo, 1, 2) AS code, l.year, sum(l.loss_ha) AS loss
        FROM read_parquet('{p}/forest_loss/forest_loss_cell_year.parquet') l
        JOIN read_parquet('{p}/districts/cell_district.parquet') d USING(cell)
        WHERE l.year BETWEEN 2001 AND 2024 GROUP BY 1, 2"""
    ).df()
    table = hansen.pivot(index="year", columns="code", values="loss").fillna(0.0)
    years = sorted(year_columns)
    national_g = np.array([sum(v[y] for v in geobosques.values()) for y in years])
    national_h = np.array([table.loc[y].sum() if y in table.index else 0.0 for y in years])
    rho, p_value = spearmanr(national_h, national_g)
    periods = {}
    for label, low, high in (("2001-2011", 2001, 2011), ("2012-2024", 2012, 2024)):
        mask = [(low <= y <= high) for y in years]
        r_period, _ = spearmanr(national_h[mask], national_g[mask])
        periods[label] = round(float(r_period), 3)
    departments = []
    for name, values in geobosques.items():
        code = codes.get(name)
        if not code or code not in table.columns:
            continue
        g = np.array([values[y] for y in years])
        h = np.array([table.loc[y, code] if y in table.index else 0.0 for y in years])
        if g.sum() < 10_000:  # departments with little humid Amazon forest loss
            continue
        r_department, _ = spearmanr(h, g)
        departments.append({"department_code": code, "department": name, "rho": round(float(r_department), 3),
                            "ratio": round(float(h.sum() / g.sum()), 2), "geobosques_ha": round(float(g.sum())),
                            "hansen_ha": round(float(h.sum()))})
    totals_rho, _ = spearmanr([d["hansen_ha"] for d in departments], [d["geobosques_ha"] for d in departments])
    headline = {"source": "MINAM Geobosques", "period": [years[0], years[-1]], "rho": round(float(rho), 3),
                "ratio": round(float(national_h.sum() / national_g.sum()), 2), "departments": len(departments),
                "department_rho": round(float(np.median([d["rho"] for d in departments])), 3),
                "spatial_rho": round(float(totals_rho), 3),
                "rho_2001_2011": periods["2001-2011"], "rho_2012_2024": periods["2012-2024"]}
    log("forest", **headline)
    return {"headline": headline,
            "comparison": "annual loss: Hansen/UMD (all tree cover with canopy of at least 30 % in 2000, stand-replacing "
                          "disturbance) aggregated to INEI departments, against Geobosques (humid Amazon forest only)",
            "national": {"years": years, "hansen_ha": [round(float(v)) for v in national_h],
                         "geobosques_ha": [round(float(v)) for v in national_g], "spearman": round(float(rho), 3),
                         "p_value": float(p_value), "spearman_by_period": periods},
            "by_department": sorted(departments, key=lambda d: -d["geobosques_ha"]),
            "source_file": workbook.name}


CHIRPS_COG = "https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/cogs/chirps-v2.0.{year}.{month:02d}.cog"
PERU_BOUNDS = (-81.5, -18.5, -68.5, 0.2)
DRY_MONTH_MM = 10.0


def chirps_month(year: int, month: int, cache: Path) -> tuple[np.ndarray, Any]:
    """Peru window of a CHIRPS v2.0 monthly COG (read over HTTP ranges, cached as .npy)."""
    import rasterio
    from rasterio.windows import from_bounds

    target = cache / f"chirps_{year}_{month:02d}.npy"
    meta = cache / "window.json"
    if target.exists() and meta.exists():
        return np.load(target), json.loads(meta.read_text())
    url = "/vsicurl/" + CHIRPS_COG.format(year=year, month=month)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT="nina/1.0",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".cog", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(url) as dataset:
            window = from_bounds(*PERU_BOUNDS, dataset.transform).round_offsets().round_lengths()
            data = dataset.read(1, window=window).astype("float32")
            transform = dataset.window_transform(window)
    np.save(target, data)
    if not meta.exists():
        meta.write_text(json.dumps({"transform": list(transform)[:6], "shape": list(data.shape)}))
    return data, json.loads(meta.read_text())


def climate_chirps(context: Path, cache: Path, first_year: int = 2002, last_year: int = 2025) -> dict[str, Any]:
    """NASA POWER precipitation anomalies and drought flag against CHIRPS v2.0, by Peruvian department."""
    from concurrent.futures import ThreadPoolExecutor

    import geopandas as gpd
    from affine import Affine
    from rasterio.features import rasterize

    cache.mkdir(parents=True, exist_ok=True)
    months = [(y, m) for y in range(first_year, last_year + 1) for m in range(1, 13)]
    chirps_month(*months[0], cache)  # writes the window metadata once
    with ThreadPoolExecutor(max_workers=2) as pool:  # the CHIRPS server throttles parallel range requests
        arrays = dict(zip(months, pool.map(lambda ym: chirps_month(ym[0], ym[1], cache)[0], months), strict=True))
    meta = json.loads((cache / "window.json").read_text())
    districts = gpd.read_file(context / "districts/peru_districts.geojson")
    districts["code"] = districts["ubigeo"].str[:2]
    departments = districts.dissolve(by="code").reset_index()
    labels = rasterize([(geometry, index + 1) for index, geometry in enumerate(departments.geometry)],
                       out_shape=tuple(meta["shape"]), transform=Affine(*meta["transform"]), fill=0, dtype="int32",
                       all_touched=False)
    names = department_names(context)
    rows = []
    for (year, month), data in arrays.items():
        valid = (data >= 0) & (labels > 0)
        sums = np.bincount(labels[valid], weights=data[valid], minlength=len(departments) + 1)
        counts = np.bincount(labels[valid], minlength=len(departments) + 1)
        for index, code in enumerate(departments["code"]):
            if counts[index + 1]:
                rows.append({"code": code, "year": year, "month": month, "chirps_mm": sums[index + 1] / counts[index + 1]})
    chirps = pd.DataFrame(rows)
    aliases = {"CALLAO": "EL CALLAO"}
    chirps["department_key"] = chirps["code"].map(lambda c: aliases.get(names[c], names[c]))
    climatology = chirps[chirps["year"].between(2002, 2024)].groupby(["department_key", "month"])["chirps_mm"].agg(["mean", "std"])
    chirps = chirps.join(climatology, on=["department_key", "month"])
    chirps["chirps_z"] = (chirps["chirps_mm"] - chirps["mean"]) / chirps["std"].replace(0, np.nan)
    # Rainfall percentile of each month among the 2002-2024 values of the same calendar month (0 = driest).
    reference = chirps[chirps["year"].between(2002, 2024)]
    chirps["chirps_percentile"] = [
        100.0 * float((reference.loc[(reference["department_key"] == k) & (reference["month"] == m), "chirps_mm"] < v).mean())
        for k, m, v in zip(chirps["department_key"], chirps["month"], chirps["chirps_mm"], strict=True)]
    layer = chirps[["department_key", "code", "year", "month", "chirps_mm", "chirps_z", "chirps_percentile"]]
    layer.to_parquet(context / "climate/chirps_department_month.parquet", index=False)
    power = duckdb.connect().execute(
        f"""SELECT department_key, year, month, precip_mm::DOUBLE AS power_mm, precip_z::DOUBLE AS power_z,
            vpd_z::DOUBLE AS vpd_z FROM read_parquet('{(context / "climate/climate_department_month.parquet").as_posix()}')
        WHERE year BETWEEN {first_year} AND {last_year}"""
    ).df()
    normal = power[power["year"].between(2002, 2024)].groupby(["department_key", "month"])["power_mm"].mean().rename("normal_mm")
    joined = chirps.merge(power, on=["department_key", "year", "month"]).join(normal, on=["department_key", "month"])
    applicable = joined[(joined["normal_mm"] >= DRY_MONTH_MM) & joined["chirps_z"].notna() & joined["power_z"].notna()].copy()
    by_department = []
    for key, part in applicable.groupby("department_key"):
        if len(part) < 60:
            continue
        r = float(np.corrcoef(part["chirps_z"], part["power_z"])[0, 1])
        code = part["code"].iat[0]
        by_department.append({"department_code": code, "department": key, "r": round(r, 3), "months": int(len(part))})
    applicable["drought_power"] = (applicable["power_z"] <= -1) & (applicable["vpd_z"] >= 1)
    applicable["drought_chirps"] = (applicable["chirps_z"] <= -1) & (applicable["vpd_z"] >= 1)
    agreement = float((applicable["drought_power"] == applicable["drought_chirps"]).mean())
    flagged = applicable[applicable["drought_power"]]
    confirmed = float((flagged["chirps_z"] <= -0.5).mean()) if len(flagged) else None
    pooled = float(np.corrcoef(applicable["chirps_z"], applicable["power_z"])[0, 1])
    headline = {"source": "CHIRPS v2.0", "period": [first_year, last_year],
                "r": round(float(np.median([d["r"] for d in by_department])), 3), "pooled_r": round(pooled, 3),
                "departments": len(by_department), "agreement": round(agreement, 4),
                "power_drought_months": int(len(flagged)),
                "confirmed_share": round(confirmed, 4) if confirmed is not None else None}
    log("climate", **headline)
    return {"headline": headline,
            "comparison": "monthly precipitation anomaly (z against 2002-2024, same calendar month) by INEI department: "
                          "NASA POWER (MERRA-2) against CHIRPS v2.0 (satellite and gauges, 0.05 degree); months with "
                          f"under {DRY_MONTH_MM:.0f} mm of normal rainfall excluded, as in the drought flag",
            "drought_rule": "precipitation z <= -1 and vapour-pressure deficit z >= +1 (VPD from NASA POWER in both)",
            "confirmed_rule": "share of POWER drought months where CHIRPS also gives z <= -0.5",
            "by_department": sorted(by_department, key=lambda d: d["r"]),
            "pisco": "PISCO (SENAMHI) was not used: its public series ends in 2016 (stable) or February 2019, and the "
                     "public FTP server showed signs of tampering on 2026-11-15."}

def write(context: Path, name: str, payload: dict[str, Any]) -> Path:
    folder = context / "validation"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    payload = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), **payload}
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--context", type=Path, default=None, help="context folder (default source/context)")
    parser.add_argument("--part", choices=["events-peru", "events-registry", "forest", "climate"], default="events-peru")
    parser.add_argument("--country", default="United States of America")
    parser.add_argument("--registry", default="usa_nifc", help="registries/<name>.parquet")
    parser.add_argument("--label", default="NIFC/WFIGS wildfire incidents")
    parser.add_argument("--before", type=int, default=2)
    parser.add_argument("--after", type=int, default=7)
    parser.add_argument("--rings", type=int, default=2)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    context = (args.context or workspace / "source/context").resolve()
    if args.part == "events-peru":
        result = peru_events(context, workspace)
        path = write(context, "events_peru_indeci", result)
        summary = {k: result[k] for k in ("detection_main", "registered_share_of_significant_events",
                                          "department_year_spearman", "department_total_spearman")}
        print(json.dumps(summary, indent=1, default=str))
        print(f"written {path}")
    elif args.part == "events-registry":
        result = point_registry_events(context, args.country, args.registry, args.label, args.before, args.after,
                                       args.rings)
        path = write(context, f"events_{args.registry}", result)
        print(json.dumps({k: result[k] for k in ("headline", "by_size")}, indent=1, default=str))
        print(f"written {path}")
    elif args.part == "forest":
        workbook = workspace / "source/downloads/validation/geobosques/Bosque_y_Perdida_de_Bosque_por_Departamentos_al_2025.xlsx"
        result = forest_geobosques(context, workbook)
        path = write(context, "forest_peru_geobosques", result)
        print(json.dumps({"headline": result["headline"], "by_department": result["by_department"]}, indent=1))
        print(f"written {path}")
    elif args.part == "climate":
        result = climate_chirps(context, workspace / "source/downloads/validation/chirps_peru")
        path = write(context, "climate_peru_chirps", result)
        print(json.dumps({"headline": result["headline"], "by_department": result["by_department"]}, indent=1))
        print(f"written {path}")


if __name__ == "__main__":
    main()
