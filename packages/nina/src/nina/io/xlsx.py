"""Minimal reader for simple .xlsx sheets (values only), without extra dependencies."""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group()
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def read_sheet(path: Path, sheet: int = 1) -> list[list[str | float | None]]:
    """Rows of the sheet as lists (missing cells are None; numbers as float, text as str)."""
    with zipfile.ZipFile(path) as archive:
        strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.iter(f"{{{NS['m']}}}t")) for item in root.findall("m:si", NS)]
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
    rows: list[list[str | float | None]] = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        values: dict[int, str | float | None] = {}
        for cell in row.findall("m:c", NS):
            value = cell.find("m:v", NS)
            inline = cell.find("m:is", NS)
            if value is None and inline is None:
                continue
            kind = cell.get("t")
            if kind == "s":
                content: str | float | None = strings[int(value.text)]
            elif kind == "inlineStr":
                content = "".join(t.text or "" for t in inline.iter(f"{{{NS['m']}}}t"))
            elif kind in ("str", "b", "e"):
                content = value.text
            else:
                content = float(value.text) if value.text not in (None, "") else None
            values[column_index(cell.get("r"))] = content
        index = int(row.get("r")) - 1
        while len(rows) < index:
            rows.append([])
        rows.append([values.get(i) for i in range(max(values) + 1)] if values else [])
    return rows
