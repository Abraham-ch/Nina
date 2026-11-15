"""Territorial report: sections, abstention when a layer is missing, and the printable document."""

import calendar
import hashlib
import json
from datetime import date

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nina import harmonized, reports

POLYGON = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    folder = artifacts / ("b" * 24)
    folder.mkdir(parents=True)
    assets = tmp_path / "web/public/assets"
    assets.mkdir(parents=True)
    (assets / "countries.geojson").write_text(
        json.dumps({"features": [{"type": "Feature", "properties": {"name": "Peru"}, "geometry": POLYGON}]}),
        encoding="utf-8",
    )
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE grid_cells AS SELECT 'cell1' cell,'Peru' country,1 biome,
        1.0 latitude,1.0 longitude UNION ALL SELECT 'cell2','Peru',1,5.0,5.0""")
    connection.execute("""CREATE TABLE harmonized_cell_day(cell VARCHAR,day DATE,country VARCHAR,
        biome INTEGER,active_harmonized DOUBLE,observed_active_cell_day INTEGER,source_mix VARCHAR,
        is_provisional BOOLEAN,coefficient_fallback VARCHAR,calibration_validated BOOLEAN,pixel_rows DOUBLE)""")
    connection.executemany(
        "INSERT INTO harmonized_cell_day VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [("cell1", date(y, 9, 10), "Peru", 1, (y - 2010) * 10.0, 1, "S-NPP", False, "reference", True, 2.0)
         for y in range(2012, 2026)],
    )
    connection.execute("""CREATE TABLE support(country VARCHAR,day DATE,valid_platforms INTEGER,
        required_platforms INTEGER,declared_archive BOOLEAN,is_provisional BOOLEAN,transition_day BOOLEAN)""")
    connection.executemany(
        "INSERT INTO support VALUES (?,?,?,?,?,?,?)",
        [("Peru", date(y, m, d), 1, 1, True, False, False)
         for y in range(2012, 2026) for m in range(7, 11) for d in range(1, calendar.monthrange(y, m)[1] + 1)],
    )
    for table in ["harmonized_cell_day", "support", "grid_cells"]:
        connection.execute(f"COPY {table} TO ? (FORMAT PARQUET)", [str(folder / f"{table}.parquet")])
    manifest = {
        "id": "b" * 24, "status": "published", "gates": {"fixture": True}, "method_version": "test",
        "references": ["https://example.org/FIRMS"], "legal": "FIRMS citation. NASA does not endorse NINA.",
        "hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.parquet")},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (artifacts / "current.json").write_text(json.dumps(manifest), encoding="utf-8")

    context = tmp_path / "context"
    for sub in ["districts", "indeci", "events", "forest_loss"]:
        (context / sub).mkdir(parents=True)
    (context / "districts/peru_districts.geojson").write_text(json.dumps({"features": [
        {"type": "Feature", "geometry": POLYGON, "properties": {
            "ubigeo": "250101", "department": "UCAYALI", "province": "CORONEL PORTILLO", "district": "CALLERIA"}}]}),
        encoding="utf-8")
    connection.execute("COPY (SELECT 'cell1' cell, '250101' ubigeo UNION ALL SELECT 'cell2', '250101') TO ? (FORMAT PARQUET)",
                       [str(context / "districts/cell_district.parquet")])
    connection.execute("""COPY (SELECT 'E'||y code, make_date(y, 9, 12) AS day, y AS year, 9 AS month, '250101' ubigeo
        FROM range(2012, 2026) t(y) UNION ALL SELECT 'X', DATE '2025-09-13', 2025, 9, '250199') TO ? (FORMAT PARQUET)""",
                       [str(context / "indeci/forest_fire_emergencies.parquet")])
    connection.execute("""COPY (SELECT y - 2012 AS event_id, 'Peru' country, make_date(y, 9, 10) start_day,
        make_date(y, 9, 12) end_day, 6 cell_days, 2 cells, 'viirs' era, '250101' ubigeo FROM range(2012, 2026) t(y))
        TO ? (FORMAT PARQUET)""", [str(context / "events/fire_events.parquet")])
    connection.execute("""COPY (SELECT y - 2012 AS event_id, 'cell1' cell, make_date(y, 9, 10) AS day
        FROM range(2012, 2026) t(y)) TO ? (FORMAT PARQUET)""", [str(context / "events/event_cell_days.parquet")])
    connection.execute("""COPY (SELECT 'cell1' cell, y AS year, 100.0 AS loss_ha FROM range(2012, 2025) t(y)
        UNION ALL SELECT 'cell2', 2024, 50.0) TO ? (FORMAT PARQUET)""", [str(context / "forest_loss/forest_loss_cell_year.parquet")])
    connection.close()

    monkeypatch.setattr(harmonized, "ARTIFACTS", artifacts)
    monkeypatch.setattr(harmonized, "REVIEW_ARTIFACTS", tmp_path / "review")
    monkeypatch.setattr(harmonized, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(harmonized, "DATA", tmp_path / "data")
    monkeypatch.setattr(harmonized, "ROOT", tmp_path)
    monkeypatch.setattr(reports, "CONTEXT", context)
    monkeypatch.setattr(reports, "DATA", tmp_path / "data")
    reports.districts.cache_clear()
    app = FastAPI()
    app.include_router(harmonized.router)
    app.include_router(reports.router)
    with TestClient(app) as test_client:
        yield test_client, context
    reports.districts.cache_clear()
    harmonized.verify_files.cache_clear()


def test_department_report_combines_all_sections(client):
    test_client, _ = client
    response = test_client.post("/api/reports/territorial", json={"ubigeo": "25", "year": 2025, "month": 9})
    assert response.status_code == 200
    report = response.json()
    assert report["territory"]["name"] == "Ucayali" and report["territory"]["type"] == "department"
    sections = report["sections"]
    assert sections["current"]["month"]["value"] == 150 and sections["current"]["month"]["rank"] == 1
    assert sections["history"]["trend_harmonized"]["direction"] == "increase"
    assert sections["history"]["trend_raw_pixels"]["direction"] == "no_trend"  # raw pixels are flat here
    events = sections["events"]["selected_year"]
    assert events == {"year": 2025, "events": 1, "significant_events": 1, "emergencies": 2}  # prefix '25' keeps '250199'
    assert all(row["code"].startswith("25") for row in sections["events"]["top_subdivisions"])
    forest = {row["year"]: row for row in sections["forest"]["by_year"]}
    assert forest[2024]["loss_ha"] == 150 and forest[2024]["loss_ha_with_fire"] == 100  # cell2 never burned
    assert sections["climate"]["status"] == "not_available"
    assert any("rank 1 of 14" in line for line in report["summary"])


def test_missing_layers_abstain_instead_of_reporting_zero(client):
    test_client, context = client
    for path in (context / "events").iterdir():
        path.unlink()
    (context / "forest_loss/forest_loss_cell_year.parquet").unlink()
    report = test_client.post("/api/reports/territorial", json={"ubigeo": "250101", "year": 2025, "month": 9}).json()
    assert report["sections"]["events"]["status"] == "not_available"
    assert report["sections"]["forest"]["status"] == "not_available"
    assert report["sections"]["current"]["status"] == "available"


def test_document_is_printable_cites_firms_and_formats_spanish_numbers(client):
    test_client, _ = client
    report = test_client.post(
        "/api/reports/territorial", json={"ubigeo": "25", "year": 2025, "month": 9, "language": "es"}
    ).json()
    assert any("celdas-día" in line for line in report["summary"])
    document = test_client.get(f"/api/reports/territorial/{report['id']}/document")
    assert document.status_code == 200 and "<svg" in document.text
    assert "FIRMS citation" in document.text and "Informe técnico territorial" in document.text
    assert test_client.get("/api/reports/territorial/" + "z" * 24).status_code == 404
    assert reports.format_number(20909.5, "es", 1) == "20 909,5"
    assert reports.format_number(20909.5, "en", 1) == "20,909.5"


def test_unknown_ubigeo_is_rejected(client):
    test_client, _ = client
    assert test_client.post("/api/reports/territorial", json={"ubigeo": "99", "year": 2025, "month": 9}).status_code == 422
    assert test_client.post("/api/reports/territorial", json={"ubigeo": "2", "year": 2025, "month": 9}).status_code == 422
