"""Reproducible evidence for NINA's Peru case (docs/PROBLEM.md).

Reads only the harmonized product (published, or the experimental draft) plus two national/regional
references, and writes one JSON with every figure quoted in the problem statement:

- the 2012 sensor break, raw versus harmonized (September means);
- September 2024 against the record (rank, anomaly, and a retrospective 14-day replay);
- detected (NINA) versus reported (INDECI emergencies), by year and by department;
- agreement with INPE's single-satellite series (an independent cross-sensor check);
- a hindcast of "early season predicts September", to show what NINA does *not* claim.

Usage (from the repository root, server environment):
    .venv/Scripts/python.exe scripts/evidence/peru_case.py

Inputs (not versioned, see docs/DATA_SOURCES.md §7):
    source/downloads/national/indeci/BD_2003-2025_EMERGENCIAS.csv
    source/downloads/national/inpe/peru.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import shapely
from scipy.stats import pearsonr, spearmanr
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
WINDOW_DAYS = 14  # trailing window for the replay (>= 8 days, sampling-bias rule)
DECLARATION = dt.date(2024, 9, 18)  # DS 097-2024-PCM, El Peruano, 18 Sep 2024
DECLARED_DEPARTMENTS = ["Amazonas", "San Martín", "Ucayali"]


def product_folder() -> tuple[Path, dict]:
    for root in [ROOT / "source/harmonized", ROOT / "source/review"]:
        pointer = root / "current.json"
        if pointer.exists():
            manifest = json.loads(pointer.read_text(encoding="utf-8"))
            return root / manifest["id"], manifest
    raise SystemExit("No harmonized product in source/harmonized or source/review")


def norm(name: str | None) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().upper().strip()
    return "LIMA" if text.startswith("LIMA") or text == "MUNICIPALIDAD METROPOLITANA DE LIMA" else text


def department_activity(con: duckdb.DuckDBPyConnection, folder: Path) -> None:
    """Table `d`: Peru cell-days with their department (cell centre in geoBoundaries ADM1)."""
    features = json.loads((ROOT / "data/boundaries/departments.geojson").read_text(encoding="utf-8"))[
        "features"
    ]
    names = [f["properties"]["shapeName"] for f in features]
    tree = shapely.STRtree([shape(f["geometry"]) for f in features])
    cells = con.execute(
        f"SELECT cell,latitude,longitude FROM '{folder / 'grid_cells.parquet'}' WHERE country='Peru'"
    ).fetchall()
    pi, gi = tree.query(shapely.points([c[2] for c in cells], [c[1] for c in cells]), predicate="within")
    con.execute("CREATE TABLE cd(cell VARCHAR,dept VARCHAR)")
    con.executemany("INSERT INTO cd VALUES (?,?)", [(cells[p][0], names[g]) for p, g in zip(pi, gi)])
    con.execute(f"""CREATE TABLE d AS SELECT h.day,coalesce(cd.dept,'unassigned') dept,
        h.active_harmonized v,h.observed_active_cell_day obs,h.pixel_rows px,h.source_mix
        FROM '{folder / 'harmonized_cell_day.parquet'}' h LEFT JOIN cd USING(cell)
        WHERE h.country='Peru'""")


def break_2012(con) -> dict:
    rows = con.execute("""SELECT year(day) y,sum(v),sum(obs),sum(px) FROM d WHERE month(day)=9
        AND year(day) BETWEEN 2003 AND 2023 GROUP BY 1""").fetchall()
    era = lambda lo, hi, i: statistics.mean(r[i] for r in rows if lo <= r[0] <= hi and r[i])  # noqa: E731
    return {
        "september_mean_ratio_2012_2023_vs_2003_2011": {
            "raw_pixels": era(2012, 2023, 3) / era(2003, 2011, 3),
            "raw_cell_days": era(2012, 2023, 2) / era(2003, 2011, 2),
            "harmonized": era(2012, 2023, 1) / era(2003, 2011, 1),
        }
    }


def september_2024(con) -> dict:
    sept = dict(con.execute("SELECT year(day),sum(v) FROM d WHERE month(day)=9 GROUP BY 1").fetchall())
    years = [y for y in range(2003, 2024) if sept.get(y)]
    snpp = [sept[y] for y in years if y >= 2012]
    value = sept[2024]
    return {
        "value": value,
        "rank_2003_2025": 1 + sum(sept[y] > value for y in range(2003, 2026) if sept.get(y)),
        "years_compared": len([y for y in range(2003, 2026) if sept.get(y)]),
        "anomaly_vs_median_2003_2023": 100 * (value / statistics.median([sept[y] for y in years]) - 1),
        "anomaly_vs_median_snpp_only_2012_2023": 100 * (value / statistics.median(snpp) - 1),
        "previous_record": max((sept[y], y) for y in years),
    }


def replay(con, where: str, label: str) -> dict:
    """Trailing 14-day activity, Jul–Oct 2024, against the same window in 2003–2023."""
    daily = dict(con.execute(f"SELECT day,sum(v) FROM d WHERE {where} GROUP BY 1").fetchall())

    def series(year):
        start = dt.date(year, 7, 1)
        return np.array([daily.get(start + dt.timedelta(i), 0.0) or 0.0 for i in range(123)])

    kernel = np.ones(WINDOW_DAYS)
    history = np.array([np.convolve(series(y), kernel)[:123] for y in range(2003, 2024)])
    target = np.convolve(series(2024), kernel)[:123]
    days = [dt.date(2024, 7, 1) + dt.timedelta(i) for i in range(123)]
    p50, p90, top = np.percentile(history, 50, 0), np.percentile(history, 90, 0), history.max(0)
    index = days.index(DECLARATION)

    def run_start(condition):
        if not condition[index]:
            return None
        j = index
        while j > WINDOW_DAYS and condition[j - 1]:
            j -= 1
        return days[j].isoformat()

    return {
        "label": label,
        "on_declaration_day": {
            "window_activity": float(target[index]),
            "median": float(p50[index]),
            "p90": float(p90[index]),
            "previous_max": float(top[index]),
            "ratio_to_median": float(target[index] / p50[index]) if p50[index] else None,
        },
        "above_p90_continuously_since": run_start(target > p90),
        "above_previous_max_continuously_since": run_start(target > top),
    }


def department_records(con) -> list[dict]:
    rows = con.execute("""WITH m AS (SELECT dept,year(day) y,sum(v) v FROM d WHERE month(day)=9
        AND year(day) BETWEEN 2003 AND 2024 GROUP BY 1,2) SELECT dept,
        max(v) FILTER(WHERE y=2024),median(v) FILTER(WHERE y<2024),max(v) FILTER(WHERE y<2024)
        FROM m WHERE dept<>'unassigned' GROUP BY 1 ORDER BY 2 DESC NULLS LAST""").fetchall()
    return [
        {
            "department": dept,
            "september_2024": v,
            "median_2003_2023": med,
            "anomaly_percent": 100 * (v / med - 1) if v and med else None,
            "record": bool(v and top and v > top),
        }
        for dept, v, med, top in rows
        if v
    ]


def detected_vs_reported(con, indeci: Path) -> dict:
    con.execute(f"""CREATE TABLE e AS SELECT try_cast("AÑO" AS INT) y,"DPTO." dpto FROM read_csv('{indeci}',
        delim=';',header=true,encoding='latin-1',all_varchar=true,ignore_errors=true)
        WHERE upper(trim("PELIGRO"))='INCENDIO FORESTAL'""")
    reported = dict(con.execute("SELECT y,count(*) FROM e GROUP BY 1").fetchall())
    detected = dict(con.execute("SELECT year(day),sum(v) FROM d GROUP BY 1").fetchall())
    years = list(range(2003, 2026))
    mean = lambda src, lo, hi: statistics.mean(src.get(y, 0) or 0 for y in range(lo, hi + 1))  # noqa: E731
    rep_dep, det_dep = defaultdict(int), defaultdict(float)
    for dpto, n in con.execute("SELECT dpto,count(*) FROM e WHERE y=2024 GROUP BY 1").fetchall():
        rep_dep[norm(dpto)] += n
    for dept, v in con.execute("SELECT dept,sum(v) FROM d WHERE year(day)=2024 GROUP BY 1").fetchall():
        if dept != "unassigned":
            det_dep[norm(dept)] += v or 0.0
    total_r, total_d = sum(rep_dep.values()), sum(det_dep.values())
    return {
        "by_year": [{"year": y, "reported": reported.get(y, 0), "detected": detected.get(y)} for y in years],
        "reported_growth_2019_2023_vs_2003_2007": mean(reported, 2019, 2023) / mean(reported, 2003, 2007),
        "detected_growth_2019_2023_vs_2003_2007": mean(detected, 2019, 2023) / mean(detected, 2003, 2007),
        "departments_2024": sorted(
            (
                {
                    "department": k,
                    "detected_share": det_dep.get(k, 0) / total_d,
                    "reported_share": rep_dep.get(k, 0) / total_r,
                    "reported": rep_dep.get(k, 0),
                }
                for k in set(rep_dep) | set(det_dep)
            ),
            key=lambda r: -r["detected_share"],
        ),
    }


def inpe_agreement(con, inpe: Path) -> dict:
    series = defaultdict(float)
    for row in json.loads(inpe.read_text(encoding="utf-8"))["historico_mensal"]:
        for month, value in row["meses"].items():
            if value is not None:
                series[(row["ano"], int(month))] += value
    nina = {(int(y), int(m)): v for y, m, v in con.execute(
        "SELECT year(day),month(day),sum(v) FROM d GROUP BY 1,2").fetchall()}
    annual = lambda src, y: sum(v or 0 for (yy, _), v in src.items() if yy == y)  # noqa: E731
    years = list(range(2003, 2026))
    a, b = [annual(series, y) for y in years], [annual(nina, y) for y in years]
    late = [i for i, y in enumerate(years) if y >= 2012]
    september = lambda src: sorted(years, key=lambda y: -(src.get((y, 9)) or 0))[:3]  # noqa: E731
    return {
        "inpe_reference_satellite": "MODIS Aqua afternoon pass (since 2002-07-04)",
        "annual_pearson_2012_2025": float(pearsonr([a[i] for i in late], [b[i] for i in late]).statistic),
        "annual_spearman_2012_2025": float(spearmanr([a[i] for i in late], [b[i] for i in late]).statistic),
        "annual_pearson_2003_2025": float(pearsonr(a, b).statistic),
        "top_years_inpe": sorted(years, key=lambda y: -a[years.index(y)])[:4],
        "top_years_nina": sorted(years, key=lambda y: -b[years.index(y)])[:4],
        "top_septembers_inpe": september(series),
        "top_septembers_nina": september(nina),
        "nina_to_inpe_ratio_2003_2011": statistics.mean(b[i] / a[i] for i in range(len(years)) if years[i] <= 2011),
        "nina_to_inpe_ratio_2012_2025": statistics.mean(b[i] / a[i] for i in late),
    }


def prediction_hindcast(con) -> dict:
    """Does Jul–Aug activity above its past median anticipate an above-median September?"""
    rows = con.execute("""SELECT dept,year(day) y,sum(v) FILTER(WHERE month(day) IN (7,8)),
        sum(v) FILTER(WHERE month(day)=9) FROM d WHERE year(day) BETWEEN 2003 AND 2025
        AND dept<>'unassigned' GROUP BY 1,2""").fetchall()
    by = defaultdict(dict)
    for dept, y, early, sept in rows:
        by[dept][y] = (early or 0.0, sept or 0.0)
    national = defaultdict(lambda: [0.0, 0.0])
    for values in by.values():
        for y, (e, s) in values.items():
            national[y][0] += e
            national[y][1] += s

    def score(values):
        years, hits, n = sorted(values), 0, 0
        for i, y in enumerate(years[5:], start=5):
            prev = years[:i]
            forecast = values[y][0] > statistics.median(values[p][0] for p in prev)
            outcome = values[y][1] > statistics.median(values[p][1] for p in prev)
            hits += forecast == outcome
            n += 1
        return hits, n

    pooled = [score(v) for v in by.values() if len(v) >= 15 and statistics.median(x[1] for x in v.values()) >= 100]
    nh, nn = score({y: tuple(v) for y, v in national.items()})
    return {
        "national_hit_rate": nh / nn,
        "department_hit_rate": sum(h for h, _ in pooled) / sum(n for _, n in pooled),
        "chance_level": 0.5,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--indeci", type=Path, default=ROOT / "source/downloads/national/indeci/BD_2003-2025_EMERGENCIAS.csv")
    parser.add_argument("--inpe", type=Path, default=ROOT / "source/downloads/national/inpe/peru.json")
    args = parser.parse_args()
    folder, manifest = product_folder()
    con = duckdb.connect()
    department_activity(con, folder)
    three = ",".join("'" + d + "'" for d in DECLARED_DEPARTMENTS)
    result = {
        "dataset_id": manifest["id"],
        "method_version": manifest["method_version"],
        "validation_status": manifest["status"],
        "unit": "equivalent_VIIRS_active_cell_days",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **break_2012(con),
        "september_2024": september_2024(con),
        "replay_2024": [replay(con, "true", "Peru")]
        + [replay(con, f"dept='{d}'", d) for d in DECLARED_DEPARTMENTS]
        + [replay(con, f"dept IN ({three})", "Declared departments")],
        "department_records_september_2024": department_records(con),
        "prediction_hindcast": prediction_hindcast(con),
    }
    if args.indeci.exists():
        result["detected_vs_reported"] = detected_vs_reported(con, args.indeci)
    if args.inpe.exists():
        result["inpe_agreement"] = inpe_agreement(con, args.inpe)
    out = ROOT / "data/reports" / f"peru_evidence_{manifest['id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    landing = ROOT / "web/public/assets/peru-evidence.json"
    landing.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"written": [str(out), str(landing)]}))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
