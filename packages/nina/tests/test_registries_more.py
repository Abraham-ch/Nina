"""Registry normalisation for Canada (CNFDB) and Portugal (ICNF/SGIF), on tiny synthetic downloads."""

import io
import zipfile

import pandas as pd

from nina.io.registries import canada_cnfdb, portugal_icnf, write

NFDB_COLUMNS = ["NFDBFIREID", "SRC_AGENCY", "NAT_PARK", "FIRE_ID", "FIRENAME", "LATITUDE", "LONGITUDE", "YEAR", "MONTH",
                "DAY", "REP_DATE", "ATTK_DATE", "OUT_DATE", "SIZE_HA", "CAUSE", "CAUSE2", "FIRE_TYPE", "RESPONSE",
                "PROTZONE", "PRESCRIBED", "MORE_INFO", "CFS_NOTE1", "CFS_NOTE2", "ACQ_DATE"]


def nfdb_row(fire_id, lat, lon, year, month, day, rep_date, size, cause="N", fire_type="Wildfire", prescribed=" "):
    values = {c: " " for c in NFDB_COLUMNS}
    values.update(NFDBFIREID=fire_id, SRC_AGENCY=fire_id[:2], LATITUDE=lat, LONGITUDE=lon, YEAR=year, MONTH=month,
                  DAY=day, REP_DATE=rep_date, SIZE_HA=size, CAUSE=cause, FIRE_TYPE=fire_type, PRESCRIBED=prescribed)
    return values


def write_nfdb(folder, rows):
    folder.mkdir(parents=True)
    text = pd.DataFrame(rows, columns=NFDB_COLUMNS).to_csv(index=False, lineterminator="\r\n")
    with zipfile.ZipFile(folder / "NFDB_point_txt.zip", "w") as archive:
        archive.writestr("NFDB_point_20260811.txt", "﻿" + text)
        archive.writestr("NFDB_point_20260811.txt.xml", "<metadata/>")


def test_canada_cnfdb_keeps_dated_points_and_accounts_for_every_row(tmp_path):
    raw = tmp_path / "canada_cnfdb"
    write_nfdb(raw, [
        nfdb_row("AB-2020-A1", "55.1", "-115.2", "2020", "7", "3", "2020-07-03 0:00:00", "1200.5", cause="H"),
        nfdb_row("AB-2020-A1", "55.1", "-115.2", "2020", "7", "3", "2020-07-03 0:00:00", "1200.5", cause="H"),  # repeat
        nfdb_row("AB-2020-A2", "56.0", "-116.0", "2020", "8", "1", "2020-08-01 0:00:00", "3.0"),
        nfdb_row("AB-2020-A2", "50.0", "-114.0", "2020", "9", "9", "2020-09-09 0:00:00", "0.1"),  # reused number
        nfdb_row("ON-2025-T8", "49.0", "-89.0", "2025", "6", "21", "2024-06-21 0:00:00", "45"),  # typed year
        nfdb_row("BC-2021-P1", "50.5", "-120.5", "2021", "4", "2", "2021-04-02 0:00:00", "12", prescribed="PB"),
        nfdb_row("BC-2021-P2", "50.5", "-120.5", "2021", "4", "3", "2021-04-03 0:00:00", "8", fire_type="PB"),
        nfdb_row("MB-2003-X1", "-98.0", "55.0", "2003", "5", "5", "2003-05-05 0:00:00", "2"),  # swapped lat/lon
        nfdb_row("MB-2003-X2", "54.0", "-98.0", "-999", "0", "0", "", "2"),  # no date at all
        nfdb_row("MB-2003-X3", "54.0", "-98.0", "2003", "5", "6", "", "7", cause="U"),  # date from YEAR/MONTH/DAY
    ])

    frame, manifest = canada_cnfdb(raw)

    assert manifest["rows_read"] == 10
    assert manifest["excluded"] == {"prescribed_burn": 2, "no_point": 1, "no_date": 1, "duplicate": 1}
    assert manifest["records"] == len(frame) == 5
    assert manifest["min_size_ha"] == 40.0 and manifest["license"].startswith("Open Government Licence - Canada")
    assert frame["record_id"].is_unique and {"AB-2020-A2", "AB-2020-A2#1"} <= set(frame["record_id"])
    typed = frame.set_index("record_id").loc["ON-2025-T8"]
    assert typed["day"] == pd.Timestamp("2025-06-21") and typed["year"] == 2025  # agency YEAR wins over a typed year
    assert frame.set_index("record_id").loc["MB-2003-X3", "day"] == pd.Timestamp("2003-05-06")
    assert manifest["dated_by_year_month_day"] == 2
    first = frame.set_index("record_id").loc["AB-2020-A1"]
    assert (first["latitude"], first["longitude"], first["size_ha"]) == (55.1, -115.2, 1200.5)
    assert first["region_code"] == "AB" and first["cause"] == "human"
    assert manifest["coverage"] == ["2003-05-06", "2025-06-21"]

    context = tmp_path / "context"
    write(context, frame, manifest)
    stored = pd.read_parquet(context / "registries/canada_cnfdb.parquet")
    assert {"record_id", "day", "year", "latitude", "longitude", "size_ha"} <= set(stored.columns)
    assert (context / "registries/canada_cnfdb.json").exists()


SGIF_HEADER = ["Codigo_SGIF", "Codigo_ANEPC", "Ano", "Mes", "Dia", "Hora", "AreaTotal_ha", "DataHoraAlerta", "DTCCFR",
               "Distrito", "Latitude", "Longitude", "X_ETRS89", "TipoCausa"]


def cell_ref(column, row):
    letters = ""
    column += 1
    while column:
        column, rest = divmod(column - 1, 26)
        letters = chr(65 + rest) + letters
    return f"{letters}{row}"


def write_sgif(path, member, rows):
    """A minimal SGIF export: a zip holding one .xlsx with shared strings (text) and plain numeric cells."""
    strings: list[str] = []
    sheet_rows = []
    for r, values in enumerate([SGIF_HEADER] + rows, start=1):
        cells = []
        for c, value in enumerate(values):
            if value is None:
                continue
            if isinstance(value, str):
                strings.append(value)
                cells.append(f'<c r="{cell_ref(c, r)}" t="s"><v>{len(strings) - 1}</v></c>')
            else:
                cells.append(f'<c r="{cell_ref(c, r)}"><v>{value}</v></c>')
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    shared = f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"
    sheet = f'<worksheet {ns}><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/sharedStrings.xml", shared)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet)
    with zipfile.ZipFile(path, "w") as archive:  # stored, as ICNF ships it
        archive.writestr(member, buffer.getvalue())


def test_portugal_icnf_reads_sgif_workbooks_and_accounts_for_every_row(tmp_path):
    raw = tmp_path / "portugal_icnf"
    raw.mkdir()
    write_sgif(raw / "RegistoIncendiosSGIF-2021-2025.zip", "Registos_Incendios_SGIF_2021_2025.xlsx", [
        ["BL3212", "2021010001353", 2021, 1, 5, 15, 0.0123, 44201.642361, 10402, "Aveiro", 40.967, -8.145, -991.1,
         "Negligente"],
        ["BL3212", "2021010001353", 2021, 1, 5, 15, 0.0123, 44201.642361, 10402, "Aveiro", 40.967, -8.145, -991.1,
         "Negligente"],  # the same fire listed twice
        ["MD0001", None, 2022, 8, 10, 12, 3.0, 44783.5, 310101, "Funchal", 28.9, -16.9, None, "Intencional"],  # off-mainland
        ["VR0002", None, None, None, None, None, 150.5, 44203.589583, 171220, "Vila Real", 41.708, -7.274, 71357.1,
         "Intencional"],  # date from the alert timestamp
        ["VR0003", None, None, None, None, None, 1.0, None, 171220, "Vila Real", 41.7, -7.3, None, "Natural"],  # no date
    ])
    write_sgif(raw / "13-Registos-Incendios-SGIF-2011-2020.zip", "Registos_Incendios_SGIF_2011_2020.xlsx", [
        ["LX0100", None, 2017, 10, 15, 3, 25000.0, None, None, "Coimbra", 40.2, -8.4, None, None],
    ])

    frame, manifest = portugal_icnf(raw)

    assert manifest["rows_read"] == 6
    assert manifest["excluded"] == {"no_point": 1, "no_date": 1, "duplicate": 1}
    assert manifest["records"] == len(frame) == 3
    assert set(manifest["files"]) == {"RegistoIncendiosSGIF-2021-2025.zip", "13-Registos-Incendios-SGIF-2011-2020.zip"}
    assert "12-Registos-Incendios-SGIF-2001-2010.zip" in manifest["note"]  # the missing archive is declared
    records = frame.set_index("record_id")
    assert records.loc["BL3212", "day"] == pd.Timestamp("2021-01-05") and records.loc["BL3212", "region_code"] == "010402"
    assert records.loc["BL3212", "cause"] == "negligent"
    assert records.loc["VR0002", "day"] == pd.Timestamp("2021-01-07") and records.loc["VR0002", "size_ha"] == 150.5
    old = records.loc["LX0100"]
    assert old["year"] == 2017 and pd.isna(old["region_code"]) and pd.isna(old["cause"])
    assert manifest["coverage"] == ["2017-10-15", "2021-01-07"] and manifest["min_size_ha"] == 40.0
