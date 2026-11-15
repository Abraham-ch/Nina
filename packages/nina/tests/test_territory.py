"""Territorial context layers: districts, INDECI schema and fire events (small synthetic inputs)."""

from datetime import date, timedelta

import duckdb
import h3
import pandas as pd
import shapely
from nina.io.territory import (
    District,
    ascii_key,
    district_cells,
    fire_events,
    indeci_forest_fires,
    majority_district,
)


def test_ascii_key_joins_names_with_and_without_accents():
    assert ascii_key("  San Martín ") == ascii_key("SAN MARTIN") == "SAN MARTIN"


def test_every_cell_has_one_district_and_tiny_districts_get_a_cell():
    big = District("010101", "A", "A", "BIG", shapely.box(-75.2, -10.2, -75.0, -10.0))
    tiny = District("010102", "A", "A", "TINY", shapely.box(-74.5, -10.1, -74.499, -10.099))
    frame = district_cells([big, tiny])
    assert frame["cell"].is_unique
    assert set(frame["ubigeo"]) == {"010101", "010102"}
    assert (frame["ubigeo"] == "010101").sum() > 50  # ~0.2° square holds dozens of res-7 cells


def test_indeci_releases_are_mapped_to_one_schema(tmp_path):
    old = tmp_path / "old.csv"
    old.write_text(
        "CODIGO DE EMERGENCIA-SINPAD;FECHA  DE LA EMER;AÑO;COD. DISTRITO;DPTO.;PROV.;DIST.;PELIGRO;"
        "FALLECIDOS;DESAPARECIDOS;LESIONADOS;DAMNIFICADOS;AFECTADOS\n"
        "1;05/09/2024;2024;250101;UCAYALI;CORONEL PORTILLO;CALLERIA;INCENDIO FORESTAL;0;0;1;0;10\n"
        "3;07/10/24;2024;250101;UCAYALI;CORONEL PORTILLO;CALLERIA;INCENDIO FORESTAL;0;0;0;0;0\n"
        "2;06/09/2024;2024;250101;UCAYALI;CORONEL PORTILLO;CALLERIA;INCENDIO URB. E INDUST.;0;0;0;0;0\n",
        encoding="latin-1",
    )
    new = tmp_path / "new.csv"
    new.write_text(
        "CODIGO EMERGENCIA INPAD;FECHA DE EMERGENCIA;AÑO;COD_UBIGEO;DEP;PROV;DIST;PELIGRO;"
        "FALLECIDOS;DESAPARECIDOS;LESIONADOS;DAMNIFICADOS;AFECTADOS\n"
        "9;05/25/26;2026;10101;AMAZONAS;CHACHAPOYAS;CHACHAPOYAS;INCENDIOS FORESTALES;1;0;0;0;3\n",
        encoding="latin-1",
    )
    frame = indeci_forest_fires(duckdb.connect(), [old, new])
    assert list(frame["code"]) == ["1", "3", "9"]
    assert list(frame["day"].astype(str)) == ["2024-09-05", "2024-10-07", "2026-05-25"]  # dd/mm/yyyy, dd/mm/yy, mm/dd/yy
    assert list(frame["ubigeo"]) == ["250101", "250101", "010101"]  # zero-padded
    assert list(frame["year"]) == [2024, 2024, 2026] and frame["deaths"].tolist() == [0, 0, 1]


def test_fire_events_join_neighbours_within_two_days_and_split_otherwise():
    cell = h3.latlng_to_cell(-10.0, -75.0, 7)
    neighbour = next(iter(h3.grid_ring(cell, 1)))
    far = h3.latlng_to_cell(-12.0, -72.0, 7)
    start = date(2024, 9, 1)
    rows = [
        (cell, start), (cell, start + timedelta(days=2)),  # gap of 2 days: same event
        (neighbour, start + timedelta(days=3)),  # neighbour, 1 day later: same event
        (cell, start + timedelta(days=10)),  # 7 days later: new event
        (far, start),  # far away: new event
    ]
    frame = pd.DataFrame(rows, columns=["cell", "day"])
    frame["active_harmonized"] = 1.0
    frame["source_mix"] = "S-NPP"
    events, membership = fire_events(frame)
    assert len(events) == 3
    first = events.sort_values("cell_days", ascending=False).iloc[0]
    assert first["cell_days"] == 3 and first["cells"] == 2 and first["duration_days"] == 4
    assert set(events["era"]) == {"viirs"}
    assert len(membership) == len(frame)
    ubigeo = majority_district(membership, pd.DataFrame({"cell": [cell], "ubigeo": ["250101"]}))
    assert ubigeo.loc[first["event_id"]] == "250101"
