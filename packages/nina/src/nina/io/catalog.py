"""Instantáneas verificables de disponibilidad y huecos publicados por FIRMS."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import duckdb
import httpx
import truststore
from dotenv import load_dotenv

BASE = "https://firms.modaps.eosdis.nasa.gov"


def observed_coverage(workspace: Path, expected_hash: str, expected_rows: int) -> dict[str, Any]:
    """Recupera el ámbito del Parquet observado, sin guardar URLs autenticadas."""
    target = workspace / "source/interim/observed_batch_coverage.json"
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if (
            previous["parquet_sha256"] == expected_hash
            and previous["observations"] == expected_rows
        ):
            return cast(dict[str, Any], previous)
    fields = [
        "id",
        "source",
        "processing",
        "coverage_start",
        "coverage_end",
        "coverage_basis",
        "spatial_scope",
        "sha256",
        "filename",
    ]
    try:
        connection = duckdb.connect(str(workspace / "data/nina.duckdb"), read_only=True)
    except duckdb.IOException:
        try:
            response = httpx.get("http://127.0.0.1:8000/api/status", timeout=120)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise ValueError(
                "Abre NINA localmente para recuperar el ámbito de los lotes observados"
            ) from None
    else:
        try:
            count = connection.execute("SELECT count(*) FROM observations").fetchall()[0][0]
            rows = connection.execute(
                "SELECT " + ",".join(fields) + " FROM batches ORDER BY id"
            ).fetchall()
            data = {
                "observations": count,
                "batches": [dict(zip(fields, row, strict=True)) for row in rows],
            }
        finally:
            connection.close()
    if data["observations"] != expected_rows:
        raise ValueError(
            "El Parquet y la base observada difieren; exporta nuevamente la instantánea"
        )
    result = {
        "parquet_sha256": expected_hash,
        "observations": expected_rows,
        "batches": [
            {key: item.get(key) for key in fields}
            for item in sorted(data["batches"], key=lambda row: row["id"])
        ],
        "authenticated_urls_stored": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def snapshot_catalog(workspace: Path) -> dict[str, Any]:
    """Consulta con credencial local; nunca guarda una URL que contenga la clave."""
    load_dotenv(workspace / ".env")
    key = os.getenv("FIRMS_MAP_KEY")
    if not key:
        raise ValueError("Falta configurar FIRMS_MAP_KEY localmente")
    folder = workspace / "source/interim"
    folder.mkdir(parents=True, exist_ok=True)
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        with httpx.Client(verify=context, timeout=90) as client:
            response = client.get(f"{BASE}/api/data_availability/csv/{key}/all")
            response.raise_for_status()
            records = list(csv.DictReader(io.StringIO(response.text)))
            if not records or not {"data_id", "min_date", "max_date"} <= set(records[0]):
                raise ValueError("Respuesta de disponibilidad inválida")
            allowed = [{k: row[k] for k in ["data_id", "min_date", "max_date"]} for row in records]
            missing_url = f"{BASE}/usfs/api/missing_data/?action=fetch_data"
            missing = client.get(missing_url, headers={"X-Requested-With": "XMLHttpRequest"})
            missing.raise_for_status()
            payload = missing.json()
    except (httpx.HTTPError, ValueError):
        raise ValueError("No fue posible consultar los metadatos públicos FIRMS") from None
    availability_path = folder / "data_availability_0.2.0.csv"
    with availability_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["data_id", "min_date", "max_date"])
        writer.writeheader()
        writer.writerows(allowed)
    if not payload.get("success"):
        raise ValueError("La tabla oficial de fechas faltantes no devolvió datos")
    html = str(payload.get("html", ""))
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [
            re.sub(r"<[^>]+>", "", item).strip()
            for item in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        ]
        for offset, quality in [(0, "SP"), (2, "NRT")]:
            if len(cells) > offset + 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[offset]):
                rows.append(
                    {
                        "day": cells[offset],
                        "satellite": cells[offset + 1],
                        "quality": quality,
                        "scope": "US_Canada_service",
                    }
                )
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "availability": allowed,
        "missing_dates": rows,
        "missing_source": missing_url,
        "missing_scope_note": "No se extrapola una tabla regional a otras regiones.",
        "transactions_requested": 1,
        "secrets_stored": False,
    }
    (folder / "firms_catalog_0.2.0.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    return result
