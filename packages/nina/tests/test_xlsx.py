"""Minimal .xlsx reader: shared strings, numbers, gaps between cells and empty rows."""

import zipfile

from nina.io.xlsx import read_sheet

SHEET = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="2"><c r="B2" t="s"><v>0</v></c><c r="D2"><v>2001</v></c></row>
<row r="3"><c r="B3" t="s"><v>1</v></c><c r="D3"><v>3030.3</v></c></row>
</sheetData></worksheet>"""
STRINGS = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>DEPARTAMENTO</t></si><si><t>AMAZONAS</t></si></sst>"""


def test_values_keep_their_columns_and_rows(tmp_path):
    path = tmp_path / "book.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", SHEET)
        archive.writestr("xl/sharedStrings.xml", STRINGS)
    rows = read_sheet(path)
    assert rows[0] == []  # row 1 is absent
    assert rows[1] == [None, "DEPARTAMENTO", None, 2001.0]
    assert rows[2] == [None, "AMAZONAS", None, 3030.3]
