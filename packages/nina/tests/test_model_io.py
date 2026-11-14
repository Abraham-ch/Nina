"""Separación de fuentes, días comparables y metadatos oficiales."""

import duckdb
import httpx
import pytest
from nina.io import catalog
from nina.io.model import monthly_pairs
from nina.io.static_sources import build_catalog


def test_monthly_pairs_combine_terra_aqua_once_and_exclude_nrt_partial_days():
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE quality AS SELECT * FROM (VALUES
        ('Terra',DATE '2020-08-15',true,true),('Aqua',DATE '2020-08-15',true,true),
        ('S-NPP',DATE '2020-08-15',true,true),('Terra',DATE '2020-08-17',true,true),
        ('Aqua',DATE '2020-08-17',false,true),('S-NPP',DATE '2020-08-17',true,true))
        q(platform,day,valid,standard)""")
    connection.execute("""CREATE TABLE official_missing_dates AS SELECT '2020-08-15' AS day,
        'Aqua (MODIS)' satellite,'SP' quality,'US_Canada_service' scope""")
    connection.execute("""CREATE TABLE activity AS SELECT * FROM (VALUES
        ('cell1',DATE '2020-08-15','Peru',1,'SP','Terra'),
        ('cell1',DATE '2020-08-15','Peru',1,'SP','Aqua'),
        ('cell1',DATE '2020-08-15','Peru',1,'SP','S-NPP'),
        ('cell2',DATE '2020-08-15','Peru',1,'SP','S-NPP'),
        ('cell3',DATE '2020-08-15','Peru',1,'NRT','Aqua'),
        ('cell4',DATE '2020-08-17','Peru',1,'SP','Terra'),
        ('cell4',DATE '2020-08-17','Peru',1,'SP','S-NPP'),
        ('cell5',DATE '2020-08-15','United States of America',1,'SP','Terra'),
        ('cell5',DATE '2020-08-15','United States of America',1,'SP','Aqua'),
        ('cell5',DATE '2020-08-15','United States of America',1,'SP','S-NPP'))
        a(cell,day,country,biome,processing,platform)""")
    pairs = monthly_pairs(connection, "terra_aqua")
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.country == "Peru" and pair.source_count == 1 and pair.reference_count == 2
    assert pair.active_cells == 2 and not pair.eligible
    connection.close()


def test_catalog_preserves_official_scope_and_never_persists_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "fixture-private-key")
    original_client = httpx.Client

    def handler(request):
        if "data_availability" in request.url.path:
            return httpx.Response(
                200, text="data_id,min_date,max_date\nVIIRS_NOAA20_SP,2018-04-01,2026-07-31\n"
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "html": "<tr><td>2020-08-17</td><td>Aqua (MODIS)</td>"
                "<td>2020-08-18</td><td>NOAA-20 (VIIRS)</td></tr>",
            },
        )

    monkeypatch.setattr(
        catalog.httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler)),
    )
    result = catalog.snapshot_catalog(tmp_path)
    assert len(result["missing_dates"]) == 2
    assert {row["scope"] for row in result["missing_dates"]} == {"US_Canada_service"}
    assert {row["quality"] for row in result["missing_dates"]} == {"SP", "NRT"}
    assert result["availability"][0]["data_id"] == "VIIRS_NOAA20_SP"
    assert all(
        "fixture-private-key" not in path.read_text(encoding="utf-8")
        for path in (tmp_path / "source/interim").iterdir()
    )


def test_catalog_failure_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "fixture-private-key")
    original_client = httpx.Client
    monkeypatch.setattr(
        catalog.httpx,
        "Client",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        ),
    )
    with pytest.raises(ValueError) as error:
        catalog.snapshot_catalog(tmp_path)
    assert "fixture-private-key" not in str(error.value)
    assert "http" not in str(error.value)


def test_static_prior_never_learns_the_labels_it_is_evaluated_on():
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE normalized(cell8 VARCHAR,day DATE,platform VARCHAR,
        processing VARCHAR,fire_type INTEGER,low_confidence BOOLEAN)""")
    connection.execute("""CREATE TABLE cells AS SELECT * FROM (VALUES
        ('historical_train','Peru'),('historical_test','Peru'),
        ('global_train','France'),('global_test','France'),
        ('reference','Peru')) c(cell8,country)""")
    connection.execute("""INSERT INTO normalized VALUES
        ('reference','2026-07-31','S-NPP','SP',NULL,false),
        ('historical_train','2023-01-01','Aqua','SP',2,false),
        ('historical_train','2023-01-02','Aqua','SP',2,false),
        ('historical_test','2024-01-01','Aqua','SP',2,false),
        ('historical_test','2024-01-02','Aqua','SP',2,false),
        ('global_train','2026-04-01','Aqua','SP',2,false),
        ('global_train','2026-04-02','Aqua','SP',2,false),
        ('global_test','2026-07-01','Aqua','SP',2,false),
        ('global_test','2026-07-02','Aqua','SP',2,false)""")
    metadata = build_catalog(connection)
    assert metadata["global_cutoff"] == "2026-04-30"
    assert metadata["global_test_end"] == "2026-07-31"
    assert {r[0] for r in connection.execute("SELECT cell8 FROM static_catalog").fetchall()} == {
        "historical_train",
        "global_train",
    }
    connection.close()


def test_zero_activity_month_is_preserved_when_archive_support_exists():
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE quality AS SELECT platform,day::DATE AS day,
        true AS valid,true AS standard FROM (VALUES ('Terra'),('Aqua'),('S-NPP')) p(platform),
        generate_series(DATE '2019-08-01',DATE '2019-09-30',INTERVAL 1 DAY) d(day)""")
    connection.execute(
        "CREATE TABLE official_missing_dates(day DATE,satellite VARCHAR,"
        "quality VARCHAR,scope VARCHAR)"
    )
    connection.execute("""CREATE TABLE activity AS SELECT 'cell' AS cell,DATE '2019-08-01' AS day,
        'Peru' AS country,1 AS biome,'SP' AS processing,platform
        FROM (VALUES ('Terra'),('Aqua'),('S-NPP')) p(platform)""")
    pairs = monthly_pairs(connection, "terra_aqua")
    quiet = next(p for p in pairs if p.month == 9)
    assert quiet.source_count == quiet.reference_count == quiet.active_cells == 0
    assert quiet.eligible
    connection.close()
