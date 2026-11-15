"""Adquisición pública reanudable del histórico de validación y sus auxiliares."""

from __future__ import annotations

import argparse
import csv
import io
import ssl
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import truststore

from nina.io.harmonization import file_digest, log, read_json, write_json

BASE = "https://firms.modaps.eosdis.nasa.gov"
# Calibration countries (FIRMS file names). The first five are the 0.4.0 set; the rest were added in 0.5.0
# by fire weight, fire regime (biome) not yet covered, region and availability of an independent registry
# (ADR 0006). Together they hold about 61 % of the bytes of the 2000-2025 FIRMS country archive.
CORE_COUNTRIES = {"Brazil", "Australia", "Indonesia", "United_States", "Peru"}
ADDED_COUNTRIES = {
    # Approved first: largest fire country, two boreal regions, cropland burning, a public registry
    "Democratic_Republic_of_the_Congo", "Russian_Federation", "India", "Canada", "Mexico",
    # South and Central America: Peru's neighbours, Chaco, Llanos, Pampas/steppe, Mediterranean Chile
    "Bolivia", "Colombia", "Ecuador", "Chile", "Argentina", "Paraguay", "Venezuela", "Honduras",
    # Africa: southern miombo, northern Sudanian savanna and gas flares, highlands, island grasslands, fynbos
    "Zambia", "Nigeria", "Ethiopia", "Madagascar", "South_Africa",
    # Asia: cropland and industrial sources, mainland South-East Asia, Eurasian steppe, boreal-steppe edge
    "China", "Myanmar", "Kazakhstan", "Mongolia",
    # Mediterranean Europe and Anatolia
    "Portugal", "Spain", "Greece", "Turkey",
}
COUNTRIES = CORE_COUNTRIES | ADDED_COUNTRIES
SOURCES = {"modis", "viirs-snpp", "viirs-jpss1"}
FIRST_YEAR, LAST_YEAR = 2000, 2025
MAX_ATTEMPTS = 3
FILENAME_PARTS = 3
AUXILIARIES: list[dict[str, Any]] = [
    {
        "name": "Natural Earth countries via world-atlas",
        "file": "world-110m.topojson",
        "url": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json",
        "version": "world-atlas 2.0.2 / 110m",
        "license": "Public Domain (Natural Earth)",
        "used_in": ["HAR-01", "AUX-01"],
    },
    {
        "name": "RESOLVE Ecoregions 2017",
        "file": "ecoregions2017.zip",
        "url": "https://storage.googleapis.com/teow2016/Ecoregions2017.zip",
        "version": "2017",
        "license": "CC-BY-4.0",
        "used_in": ["HAR-01"],
    },
    {
        "name": "GHSL Urban Centres",
        "file": "ghsl-urban-2015.zip",
        "url": "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
        "GHS_STAT_UCDB2015MT_GLOBE_R2019A/V1-2/GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.zip",
        "version": "R2019A V1.2 epoch 2015",
        "license": "CC-BY-4.0",
        "used_in": ["TYPE-02", "TYPE-05", "AUX-03"],
    },
    {
        "name": "GSHHG land and inland water",
        "file": "gshhg.zip",
        "url": "https://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip",
        "version": "2.3.7 intermediate resolution",
        "license": "LGPL-3.0",
        "used_in": ["TYPE-02", "TYPE-05"],
    },
    {
        "name": "Smithsonian GVP Holocene volcanoes",
        "file": "volcanoes.geojson",
        "url": "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS"
        "&version=1.0.0&request=GetFeature&typeName=GVP-VOTW%3ASmithsonian_VOTW_Holocene_Volcanoes"
        "&outputFormat=application%2Fjson&maxFeatures=5000",
        "version": "VOTW5-2026.5.4",
        "license": "Smithsonian GVP Terms of Use; attribution",
        "used_in": ["TYPE-02", "TYPE-05"],
    },
]


def public_client() -> httpx.Client:
    """Certificados del sistema; sin credenciales ni desactivar TLS."""
    return httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=240, follow_redirects=True
    )


def download(path: Path, entry: dict[str, Any], expected_hash: str | None = None) -> dict[str, Any]:
    """Verifica tamaño, contenido y SHA-256; una descarga parcial nunca es válida."""
    path.parent.mkdir(parents=True, exist_ok=True)
    reusable = path.exists() and (
        not entry.get("expected_bytes") or path.stat().st_size == entry["expected_bytes"]
    )
    if reusable and expected_hash:
        reusable = file_digest(path) == expected_hash
    if not reusable:
        for attempt in range(MAX_ATTEMPTS):
            try:
                part = path.with_suffix(path.suffix + ".part")
                with public_client() as client, client.stream("GET", entry["url"]) as response:
                    response.raise_for_status()
                    with part.open("wb") as stream:
                        for block in response.iter_bytes():
                            stream.write(block)
                if entry.get("expected_bytes") and part.stat().st_size != entry["expected_bytes"]:
                    raise ValueError("El tamaño no coincide con el índice NASA")
                part.replace(path)
                break
            except (httpx.HTTPError, ValueError):
                if attempt + 1 == MAX_ATTEMPTS:
                    raise ValueError(f"No se pudo descargar {path.name}") from None
                time.sleep(attempt + 1)
    validate_content(path)
    return {
        **entry,
        "path": str(path),
        "sha256": file_digest(path),
        "bytes": path.stat().st_size,
        "status": "downloaded",
    }


def validate_content(path: Path) -> None:
    """Rechaza respuestas HTML y archivos truncados aunque el HTTP sea exitoso."""
    if path.suffix == ".csv":
        with path.open("rb") as stream:
            header = stream.read(1000)
        if b"latitude" not in header or b"longitude" not in header:
            raise ValueError(f"Cabecera inválida: {path.name}")
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"ZIP corrupto: {path.name}")
    elif path.suffix == ".topojson":
        if read_json(path).get("type") != "Topology":
            raise ValueError(f"TopoJSON inválido: {path.name}")
    elif not read_json(path).get("features"):
        raise ValueError(f"GeoJSON vacío: {path.name}")


def history_plan(workspace: Path) -> list[dict[str, Any]]:
    """Selecciona exclusivamente las cinco áreas y los años documentados."""
    index_file = workspace / "source/yearly_summary_files.txt"
    if not index_file.exists():
        with public_client() as client:
            response = client.get(BASE + "/data/country/yearly_summary_files.txt")
            response.raise_for_status()
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(response.text, encoding="utf-8")
    entries = []
    for row in csv.DictReader(io.StringIO(index_file.read_text(encoding="utf-8"))):
        pieces = row["filename"].split("_", 2)
        if len(pieces) != FILENAME_PARTS:
            continue
        source, year, country_file = pieces
        country = country_file.removesuffix(".csv")
        if (
            source not in SOURCES
            or country not in COUNTRIES
            or not FIRST_YEAR <= int(year) <= LAST_YEAR
        ):
            continue
        entries.append(
            {
                "filename": row["filename"],
                "source": source,
                "year": int(year),
                "country": country,
                "expected_bytes": int(row["size"]),
                "published_updated": row["updated"],
                "url": f"{BASE}/data/country/{source}/{year}/{row['filename']}",
            }
        )
    return entries


def acquire(workspace: Path) -> None:
    """Conserva manifiestos y reusa originales existentes verificados."""
    entries = history_plan(workspace)
    manifest_file = workspace / "source/history-inputs.json"
    previous = read_json(manifest_file) if manifest_file.exists() else {"files": []}
    hashes = {item["filename"]: item.get("sha256") for item in previous["files"]}

    def get_history(entry: dict[str, Any]) -> dict[str, Any]:
        legacy = workspace / "data/raw" / entry["filename"]
        path = legacy if legacy.exists() else workspace / "source/raw/history" / entry["filename"]
        result = download(path, entry, hashes.get(entry["filename"]))
        log("verified_history", file=entry["filename"])
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(get_history, entries))
    write_json(
        manifest_file,
        {
            "created_at": datetime.now(UTC).isoformat(),
            "status": "complete",
            "files": files,
            "synthetic": False,
        },
    )
    auxiliary_file = workspace / "source/auxiliary-inputs.json"
    old_aux = read_json(auxiliary_file) if auxiliary_file.exists() else []
    aux_hashes = {item["file"]: item.get("sha256") for item in old_aux}
    auxiliary = []
    for entry in AUXILIARIES:
        result = download(
            workspace / "source/auxiliary" / entry["file"], entry, aux_hashes.get(entry["file"])
        )
        result["download_date"] = datetime.now(UTC).isoformat()
        if entry["file"] == "world-110m.topojson":
            bundled = workspace / "design/world-110m.topojson"
            # Compare content, not bytes: a git checkout on Windows may change the line endings of the bundled copy.
            downloaded = workspace / "source/auxiliary" / entry["file"]
            if read_json(bundled) != read_json(downloaded):
                raise ValueError("La cartografía no coincide con el original versionado")
            result["derived_asset"] = "web/public/assets/countries.geojson"
            result["derived_sha256"] = file_digest(workspace / result["derived_asset"])
            result["transform"] = (
                "topojson-client; WGS84 round/clamp 6 decimals; Shapely make_valid"
            )
        auxiliary.append(result)
    write_json(auxiliary_file, auxiliary)
    log("acquisition_complete", files=len(files), bytes=sum(item["bytes"] for item in files))


def main() -> None:
    """Sin --download, muestra el volumen del plan y no descarga los originales."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    entries = history_plan(workspace)
    log(
        "plan",
        files=len(entries),
        bytes=sum(e["expected_bytes"] for e in entries),
        first_year=FIRST_YEAR,
        last_year=LAST_YEAR,
        countries=sorted(COUNTRIES),
    )
    if args.download:
        acquire(workspace)


if __name__ == "__main__":
    main()
