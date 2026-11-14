"""Pruebas de cuadre, precedencia espacial y producto común con fixtures pequeños."""

import csv
from dataclasses import asdict
from datetime import date

import duckdb
import h3
import pytest
import shapely
from nina.calibration import Coefficient
from nina.io.geography import intersects, polygon_tree
from nina.io.harmonization import (
    classify_rows,
    consolidate,
    file_digest,
    h3_index,
    normalize_input,
    read_json,
    reconcile_activity,
    validate_mask,
    write_json,
)
from nina.io.product import assemble, build_support, publish


def test_empty_archive_and_quality_accounting(tmp_path):
    path = tmp_path / "modis.csv"
    fields = [
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "satellite",
        "confidence",
        "version",
        "frp",
        "scan",
        "track",
        "type",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerow([-12, -70, "2000-10-31", "618", "T", "48", "61.03", 3, 2.5, 1.5, 0])
        writer.writerow([-12, -70, "2019-01-01", "0000", "A", "48", "61.03", 3, 2.5, 1.5, 0])
    cache = tmp_path / "cache"
    cache.mkdir()
    connection = duckdb.connect()
    connection.create_function("h3_index", h3_index)
    entry = {"path": str(path), "source": "modis", "sha256": file_digest(path)}
    report = normalize_input(connection, entry, cache)
    assert report["rows_read"] == report["accepted"] + sum(report["rejected"].values()) == 2
    assert report["rejected"] == {"pre_nov2000_quality": 1}
    row = connection.execute(
        "SELECT day,area_sum,low_confidence FROM read_parquet(?)", [report["parquet"]]
    ).fetchone()
    assert row == (date(2019, 1, 1), 3.75, False)
    path.write_text(",".join(fields) + "\n", encoding="utf-8")
    report = normalize_input(connection, {**entry, "sha256": file_digest(path)}, cache)
    assert report["rows_read"] == report["accepted"] == 0
    path.write_text(
        ",".join(fields) + "\n999,-70,2019-01-01,0000,A,48,61.03,3,1,1,0\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="1 %"):
        normalize_input(connection, {**entry, "sha256": file_digest(path)}, cache)
    connection.remove_function("h3_index")
    connection.close()


def test_deduplication_prefers_standard_deterministically(tmp_path):
    connection = duckdb.connect()
    path = tmp_path / "pixels.parquet"
    connection.execute(
        """COPY (SELECT 'same' pixel_id,'NRT' processing,'6.1NRT' version,
        false low_confidence,NULL::INTEGER fire_type,5 frp_sum,1 area_sum UNION ALL
        SELECT 'same','SP','61.03',false,0,4,1) TO ? (FORMAT PARQUET)""",
        [str(path)],
    )
    assert consolidate(connection, [{"parquet": str(path), "accepted": 2}]) == 1
    assert connection.execute("SELECT processing,fire_type FROM normalized").fetchall() == [
        ("SP", 0)
    ]
    connection.close()


def test_regional_standard_does_not_erase_foreign_nrt():
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE activity AS SELECT * FROM (VALUES
        ('Peru','Aqua',DATE '2025-09-01','NRT'),
        ('Brazil','Aqua',DATE '2025-09-01','NRT'),
        ('Peru','Aqua',DATE '2025-09-01','SP')) a(country,platform,day,processing)""")
    connection.execute("ALTER TABLE activity ADD COLUMN pixel_rows INTEGER DEFAULT 1")
    connection.execute("CREATE TABLE region_daily_counts AS SELECT * FROM activity")
    connection.execute(
        "CREATE TABLE global_standard_windows(platform VARCHAR,first_date DATE,last_date DATE)"
    )
    assert reconcile_activity(connection) == {"cell_days": 1, "pixel_rows": 1}
    assert connection.execute(
        "SELECT country,processing FROM activity ORDER BY country"
    ).fetchall() == [("Brazil", "NRT"), ("Peru", "SP")]
    connection.execute(
        "INSERT INTO global_standard_windows VALUES ('Aqua','2025-09-01','2025-09-01')"
    )
    assert reconcile_activity(connection) == {"cell_days": 1, "pixel_rows": 1}
    connection.close()


def test_prepared_polygon_retains_holes_and_boundaries():
    polygon = shapely.Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)], holes=[[(4, 4), (6, 4), (6, 6), (4, 6)]]
    )
    tree = polygon_tree([polygon])
    pairs = intersects(tree, shapely.points([1, 5, 4, 0, 12], [1, 5, 5, 5, 5]))
    assert set(pairs[0]) == {0, 2, 3}


def product_fixture(connection):
    cell = h3.latlng_to_cell(-12.0, -70.0, 7)
    connection.execute("""CREATE TABLE activity(cell VARCHAR,day DATE,platform VARCHAR,
        processing VARCHAR,country VARCHAR,biome INTEGER,pixel_rows INTEGER)""")
    connection.executemany(
        "INSERT INTO activity VALUES (?,?,?,?,?,?,?)",
        [
            (cell, "2011-01-05", "Terra", "SP", "Peru", 1, 10),
            (cell, "2011-01-05", "Aqua", "SP", "Peru", 1, 15),
            (cell, "2020-01-05", "S-NPP", "SP", "Peru", 1, 30),
        ],
    )
    connection.execute("""CREATE TABLE support AS SELECT * FROM (VALUES
        ('Peru',DATE '2011-01-05','terra_aqua',2,2,2,true,false,false),
        ('Peru',DATE '2020-01-05','reference',1,1,1,true,false,false))
        s(country,day,sampling,required_platforms,archive_platforms,valid_platforms,
          declared_archive,is_provisional,transition_day)""")
    connection.execute("CREATE TABLE grid_cells AS SELECT ? cell,'Peru' country,1 biome", [cell])
    coefficient = Coefficient("Peru", 1, 1, "terra_aqua", 2.5, 300, (2018, 2019, 2020), "biome")
    return {
        "coefficients": [asdict(coefficient)],
        "validation": {"terra_aqua": {"strata": [{"country": "Peru", "biome": 1, "passed": True}]}},
    }


def test_cells_count_once_weights_are_aggregates_and_hashes_reproduce(tmp_path):
    connection = duckdb.connect()
    model = product_fixture(connection)
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    hash_first = assemble(connection, first, model)
    assert connection.execute("""SELECT observed_active_cell_day,active_harmonized,pixel_rows
        FROM harmonized_cell_day ORDER BY day""").fetchall() == [(1, 2.5, 25), (1, 1.0, 30)]
    hash_second = assemble(connection, second, model)
    assert hash_first == hash_second
    connection.close()


def test_failed_gate_never_creates_a_published_pointer(tmp_path):
    folder = tmp_path / "source/interim/harmonization"
    write_json(folder / "model.json", {"id": "a" * 24, "publishable": False})
    with pytest.raises(ValueError, match="bloqueada"):
        publish(tmp_path)
    assert not (tmp_path / "source/harmonized/current.json").exists()
    assert read_json(folder / "model.json")["publishable"] is False


def test_sixteen_days_mask_and_false_removals_are_a_real_gate():
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE normalized(cell8 VARCHAR,day DATE,platform VARCHAR,
        processing VARCHAR,fire_type INTEGER,low_confidence BOOLEAN,n INTEGER)""")
    connection.executemany(
        "INSERT INTO normalized VALUES (?,?,?,?,?,?,?)",
        [
            (cell, date(2024, 1, day), "Aqua", "SP", 0, False, 1)
            for cell, days in [("persistent", 16), ("vegetation", 15)]
            for day in range(1, days + 1)
        ],
    )
    connection.execute(
        "INSERT INTO normalized VALUES ('persistent','2024-01-16','Aqua','SP',2,false,1)"
    )
    connection.executemany(
        "INSERT INTO normalized VALUES (?,?,?,?,?,?,?)",
        [("persistent", date(2024, 1, day), "S-NPP", "SP", None, False, 1) for day in range(1, 17)],
    )
    connection.execute("""CREATE TABLE cells AS SELECT cell8,cell8 AS cell,'Peru' country,
        1 biome,1 ecoregion,0.0 latitude,0.0 longitude,false urban,false water,false volcano
        FROM (VALUES ('persistent'),('vegetation')) c(cell8)""")
    classify_rows(connection)
    assert (
        connection.execute("SELECT count(*) FROM classified WHERE qa_reason IS NULL").fetchone()[0]
        == 15
    )
    mask = validate_mask(connection)
    assert mask["static_recall"] == 1
    assert mask["vegetation_rows_removed"] == 16
    assert not mask["passed"]  # No se convierte una máscara agresiva en una prueba exitosa.
    connection.close()


def test_archive_support_respects_regimes_official_scope_and_mission_end(tmp_path):
    lifecycle = {
        "terra": {"first_date": "2000-11-01", "last_date": None},
        "aqua": {"first_date": "2002-07-04", "last_date": None},
        "snpp": {"first_date": "2012-01-20", "last_date": "2026-11-02"},
        "noaa20": {"first_date": "2018-04-01", "last_date": None},
        "noaa21": {"first_date": "2024-01-17", "last_date": None},
    }
    write_json(
        tmp_path / "source/history-inputs.json",
        {
            "files": [
                {"country": "Peru", "source": "modis", "year": 2001},
                {"country": "Peru", "source": "viirs-snpp", "year": 2025},
            ]
        },
    )
    write_json(
        tmp_path / "data/global-import.json",
        {
            "files": [
                {
                    "source": source,
                    "spatial_scope": "world",
                    "processing": "NRT",
                    "first_date": "2026-11-02",
                    "last_date": "2026-11-03",
                    "coverage_basis": "observed_dates_only",
                }
                for source in ["viirs-snpp", "viirs-jpss1"]
            ]
        },
    )
    write_json(
        tmp_path / "web/public/assets/countries.geojson",
        {
            "features": [
                {"properties": {"name": country}}
                for country in ["Peru", "United States of America"]
            ]
        },
    )
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE quality AS SELECT * FROM (VALUES
        ('Terra',DATE '2001-03-01',true),('S-NPP',DATE '2025-02-01',true),
        ('S-NPP',DATE '2026-11-02',true),('NOAA-20',DATE '2026-11-03',true))
        q(platform,day,valid)""")
    connection.execute("""CREATE TABLE official_missing_dates AS SELECT '2026-11-03' AS day,
        'NOAA-20 (VIIRS)' satellite,'NRT' quality,'US_Canada_service' scope""")
    build_support(connection, tmp_path, {"sensor_lifecycle": lifecycle})
    assert connection.execute("""SELECT sampling,valid_platforms,declared_archive
        FROM support WHERE country='Peru' AND day='2001-03-01'""").fetchone() == (
        "terra_only",
        1,
        True,
    )
    assert connection.execute(
        "SELECT transition_day FROM support WHERE country='Peru' AND day='2026-11-02'"
    ).fetchone() == (True,)
    assert connection.execute("""SELECT country,sampling,valid_platforms FROM support
        WHERE country IN ('Peru','United States of America') AND day='2026-11-03'
        ORDER BY country""").fetchall() == [
        ("Peru", "noaa20", 1),
        ("United States of America", "noaa20", 0),
    ]
    connection.close()
