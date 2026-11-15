"""Contrato completo del producto común con un artefacto pequeño y verificable."""

import calendar
import csv
import hashlib
import io
import json
import zipfile
from datetime import date

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nina import harmonized


@pytest.fixture()
def published_artifact(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    identifier = "a" * 24
    folder = artifacts / identifier
    folder.mkdir(parents=True)
    assets = tmp_path / "web/public/assets"
    assets.mkdir(parents=True)

    def feature(name, west):
        return {
            "type": "Feature",
            "properties": {"name": name},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[west, 0], [west + 10, 0], [west + 10, 10], [west, 10], [west, 0]]
                ],
            },
        }

    (assets / "countries.geojson").write_text(
        json.dumps({"features": [feature("Peru", 0), feature("Brazil", 20)]}), encoding="utf-8"
    )
    monkeypatch.setattr(harmonized, "ARTIFACTS", artifacts)
    monkeypatch.setattr(harmonized, "REVIEW_ARTIFACTS", tmp_path / "review")
    monkeypatch.setenv("NINA_EXPERIMENTAL_HARMONIZATION", "false")
    monkeypatch.setattr(harmonized, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(harmonized, "DATA", tmp_path / "data")
    monkeypatch.setattr(harmonized, "ROOT", tmp_path)
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE grid_cells AS SELECT 'cell1' cell,'Peru' country,
        1 biome,1.0 latitude,1.0 longitude UNION ALL SELECT 'cell2','Peru',1,5.0,5.0""")
    connection.execute("""CREATE TABLE harmonized_cell_day(cell VARCHAR,day DATE,country VARCHAR,
        biome INTEGER,active_harmonized DOUBLE,observed_active_cell_day INTEGER,source_mix VARCHAR,
        is_provisional BOOLEAN,coefficient_fallback VARCHAR,calibration_validated BOOLEAN)""")
    connection.execute("""CREATE TABLE support(country VARCHAR,day DATE,valid_platforms INTEGER,
        required_platforms INTEGER,declared_archive BOOLEAN,is_provisional BOOLEAN,transition_day BOOLEAN)""")
    connection.executemany(
        "INSERT INTO harmonized_cell_day VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "cell1",
                date(year, 2, 1),
                "Peru",
                1,
                (year - 2018) * 10,
                1,
                "S-NPP",
                False,
                "reference",
                True,
            )
            for year in range(2019, 2026)
        ],
    )
    # 198 días: seis referencias históricas y el mes de consulta.
    connection.executemany(
        "INSERT INTO support VALUES (?,?,?,?,?,?,?)",
        [
            ("Peru", date(year, 2, day), 1, 1, True, False, False)
            for year in range(2019, 2026)
            for day in range(1, calendar.monthrange(year, 2)[1] + 1)
        ],
    )
    # March: complete in 2019–2024; 2025 is in progress (days 1–10, day 4 without valid support).
    connection.executemany(
        "INSERT INTO support VALUES (?,?,?,?,?,?,?)",
        [
            ("Peru", date(year, 3, day), 0 if (year, day) == (2025, 4) else 1, 1, True, False, False)
            for year in range(2019, 2026)
            for day in range(1, (11 if year == 2025 else 32))
        ],
    )
    connection.executemany(
        "INSERT INTO harmonized_cell_day VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("cell1", date(year, 3, 3), "Peru", 1, (year - 2018) * 2, 1, "S-NPP", False, "reference", True)
            for year in range(2019, 2026)
        ],
    )
    for table in ["harmonized_cell_day", "support", "grid_cells"]:
        connection.execute(
            f"COPY {table} TO ? (FORMAT PARQUET)", [str(folder / f"{table}.parquet")]
        )
    connection.close()
    manifest = {
        "id": identifier,
        "status": "published",
        "gates": {"fixture": True},
        "method_version": "test",
        "references": ["https://example.org/FIRMS"],
        "legal": "NASA no avala NINA. Fuente: FIRMS.",
        "hashes": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.glob("*.parquet")
        },
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (artifacts / "current.json").write_text(json.dumps(manifest), encoding="utf-8")
    app = FastAPI()
    app.include_router(harmonized.router)
    with TestClient(app) as client:
        yield client, folder
    harmonized.verify_files.cache_clear()


def request(**changes):
    return {
        "country": "Peru",
        "year_start": 2019,
        "year_end": 2025,
        "selected_year": 2025,
        "selected_month": 2,
        **changes,
    }


def test_calendar_exports_assistant_and_points_use_one_published_revision(published_artifact):
    client, _ = published_artifact
    response = client.post("/api/harmonized/analyses", json=request())
    assert response.status_code == 200
    result = response.json()
    selected = result["selected"]
    assert selected["value"] == 70
    assert selected["historical_median"] == 35
    assert selected["anomaly_percent"] == 100
    identifier = result["id"]
    points = client.get(f"/api/harmonized/analyses/{identifier}/points").json()
    assert points["total"] == points["shown"] == 1
    assert points["representation"] == "H3_cell_centers"
    assert points["features"][0]["properties"]["activity"] == selected["value"]
    series = client.get(f"/api/harmonized/analyses/{identifier}/exports/series")
    rows = list(csv.DictReader(io.StringIO(series.content.decode("utf-8-sig"))))
    row = next(row for row in rows if row["year"] == "2025" and row["month"] == "2")
    assert float(row["value"]) == selected["value"] and row["legal"]
    package = client.get(f"/api/harmonized/analyses/{identifier}/exports/package")
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert set(archive.namelist()) == {"series.csv", "cells.csv", "manifest.json", "README.md"}
        cells = list(csv.DictReader(io.StringIO(archive.read("cells.csv").decode("utf-8-sig"))))
        assert len(cells) == 1 and float(cells[0]["active_harmonized"]) == 70
        assert float(cells[0]["latitude"]) == float(cells[0]["longitude"]) == 1
        assert cells[0]["representation"] == "H3_cell_center"
        assert cells[0]["sampling_bias_warning"] == "True"
    answer = client.post(
        "/api/harmonized/assistant",
        json={"analysis_id": identifier, "question": "How does it compare with other years?"},
    ).json()
    assert answer["facts"] == selected and answer["dataset_id"] == result["dataset_id"]
    assert not answer["external_llm_used"]


def test_missing_global_regions_are_not_zero_or_a_world_total(published_artifact):
    client, _ = published_artifact
    result = client.post("/api/harmonized/analyses", json=request(country="world")).json()
    assert result["selected"]["value"] is None
    assert result["selected"]["observed_activity"] == 70
    assert result["selected"]["status"] == "incomplete_coverage"
    assert result["selected"]["anomaly_percent"] is None
    missing = next(m for m in result["months"] if m["year"] == 2025 and m["month"] == 1)
    assert missing["value"] is None and missing["data_gap"]


def test_exact_polygon_hole_and_bad_requests(published_artifact):
    client, _ = published_artifact
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[0.5, 0.5], [2, 0.5], [2, 2], [0.5, 2], [0.5, 0.5]],
        ],
    }
    result = client.post("/api/harmonized/analyses", json=request(geometry=geometry)).json()
    assert result["selected"]["value"] == 0
    assert client.get(f"/api/harmonized/analyses/{result['id']}/points").json()["total"] == 0
    assert (
        client.post("/api/harmonized/analyses", json=request(country="invented")).status_code == 422
    )
    assert client.post("/api/harmonized/analyses", json=request(year_start=2026)).status_code == 422
    assert client.get("/api/harmonized/analyses/not-a-hash").status_code == 404


def test_integrity_failure_is_not_served(published_artifact):
    client, folder = published_artifact
    path = folder / "harmonized_cell_day.parquet"
    path.write_bytes(path.read_bytes() + b"changed")
    assert client.post("/api/harmonized/analyses", json=request()).status_code == 503


def test_failed_scientific_gate_is_visible_and_blocks_analysis(published_artifact):
    client, _ = published_artifact
    (harmonized.ARTIFACTS / "current.json").unlink()
    harmonized.REPORTS.mkdir()
    (harmonized.REPORTS / "status.json").write_text(
        json.dumps({"status": "candidate_failed_validation", "gates": {"static_mask": False}}),
        encoding="utf-8",
    )
    response = client.post("/api/harmonized/analyses", json=request())
    assert response.status_code == 409
    assert response.json()["detail"]["readiness"]["gates"] == {"static_mask": False}
    assert not client.get("/api/harmonization").json()["available"]


def test_experimental_draft_requires_explicit_activation_and_keeps_failed_gates(published_artifact):
    client, folder = published_artifact
    (harmonized.ARTIFACTS / "current.json").unlink()
    destination = harmonized.REVIEW_ARTIFACTS / folder.name
    destination.mkdir(parents=True)
    for path in folder.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(
        status="experimental_candidate",
        gates={"static_mask": False},
        scientifically_validated=False,
    )
    (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (harmonized.REVIEW_ARTIFACTS / "current.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    assert client.post("/api/harmonized/analyses", json=request()).status_code == 409
    assert client.get("/api/harmonization").json()["activation_required"]
    import os

    previous = os.environ["NINA_EXPERIMENTAL_HARMONIZATION"]
    try:
        os.environ["NINA_EXPERIMENTAL_HARMONIZATION"] = "true"
        response = client.post("/api/harmonized/analyses", json=request())
        assert response.status_code == 200
        data = response.json()
        assert data["validation_status"] == "experimental" and not data["scientifically_validated"]
        assert data["provenance"]["gates"] == {"static_mask": False}
    finally:
        os.environ["NINA_EXPERIMENTAL_HARMONIZATION"] = previous


def test_current_year_gets_an_anomaly_but_never_enters_the_baseline(published_artifact):
    client, folder = published_artifact
    # Snapshot in 2025: February 2025 is compared with 2019–2024 but is not one of their references.
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["as_of_date"] = "2025-03-01"
    for path in [folder / "manifest.json", harmonized.ARTIFACTS / "current.json"]:
        path.write_text(json.dumps(manifest), encoding="utf-8")
    result = client.post("/api/harmonized/analyses", json=request()).json()
    selected = result["selected"]
    assert not selected["eligible_for_climatology"]
    assert selected["anomaly_percent"] == 100 and selected["rank"] == 1 and selected["rank_of"] == 7
    february_2024 = next(m for m in result["months"] if (m["year"], m["month"]) == (2024, 2))
    assert february_2024["historical_n"] == 5  # 2019–2023; 2025 is not a reference year


def test_border_slivers_of_generalized_outlines_do_not_blank_a_polygon(published_artifact):
    client, _ = published_artifact
    # Touches Brazil's outline (west edge 20°) but holds only Peruvian cells.
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [21, 0], [21, 10], [0, 10], [0, 0]]]}
    result = client.post(
        "/api/harmonized/analyses", json=request(country="world", geometry=geometry)
    ).json()
    assert result["excluded_border_countries"] == ["Brazil"]
    assert result["selected"]["value"] == 70


def test_assistant_answers_in_both_languages(published_artifact):
    client, _ = published_artifact
    identifier = client.post("/api/harmonized/analyses", json=request()).json()["id"]
    english = client.post(
        "/api/harmonized/assistant", json={"analysis_id": identifier, "question": "Is it normal?"}
    ).json()["answer"]
    spanish = client.post(
        "/api/harmonized/assistant",
        json={"analysis_id": identifier, "question": "¿Es normal?", "language": "es"},
    ).json()["answer"]
    assert "median" in english and "+100.0 %" in english and "mediana" in spanish


def test_month_in_progress_is_compared_with_the_same_valid_days(published_artifact):
    client, _ = published_artifact
    result = client.post("/api/harmonized/analyses", json=request(selected_month=3)).json()
    assert result["selected"]["value"] is None  # the whole month is not comparable yet
    current = result["month_to_date"]
    assert current["through_day"] == 10 and current["valid_days"] == 9  # day 4 skipped, not zero
    assert current["value"] == 14 and current["historical_median"] == 7
    assert current["anomaly_percent"] == 100 and not current["sampling_bias_warning"]


def test_stored_analysis_and_points_are_reused_and_a_failed_write_leaves_no_temporary(
    published_artifact, monkeypatch
):
    client, _ = published_artifact
    first = client.post("/api/harmonized/analyses", json=request()).json()
    points = client.get(f"/api/harmonized/analyses/{first['id']}/points").json()
    cache = harmonized.DATA / "jobs/harmonized"
    assert (cache / f"{first['id']}.json").exists()
    assert (cache / f"{first['id']}_points_5000.json").exists()
    # The second request reads the stored copy: the same answer without touching the product.
    monkeypatch.setattr(harmonized, "selection_database", None)
    assert client.post("/api/harmonized/analyses", json=request()).json() == first
    assert client.get(f"/api/harmonized/analyses/{first['id']}/points").json() == points
    # A replace that fails (Windows: the target is open in another request) keeps the old copy, no orphan file.
    target = cache / "busy.json"
    target.write_text("{}", encoding="utf-8")

    def busy(self, other):
        raise PermissionError("in use")

    monkeypatch.setattr(harmonized.Path, "replace", busy)
    harmonized.store_json(target, {"value": 1})
    assert target.read_text(encoding="utf-8") == "{}"
    assert not list(cache.glob("*.tmp"))


def test_heavy_queries_take_turns_and_reuse_the_result_of_the_one_they_waited_for(published_artifact):
    import threading

    client, _ = published_artifact
    entered = threading.Event()
    results = []
    harmonized.HEAVY_QUERY.acquire()  # another planet query is running
    try:
        worker = threading.Thread(
            target=lambda: (entered.set(), results.append(client.post("/api/harmonized/analyses", json=request())))
        )
        worker.start()
        entered.wait(5)
        worker.join(0.5)
        assert worker.is_alive() and not results  # waiting for its turn, not running in parallel
    finally:
        harmonized.HEAVY_QUERY.release()
    worker.join(30)
    assert results and results[0].status_code == 200
