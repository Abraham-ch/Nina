"""Fixtures compartidos de la suite.

`client` deja la base DuckDB aislada en `tmp_path` y arranca el servidor en modo anónimo:
quien necesita sesión la crea explícitamente en su test. `tests/test_nina.py` define su
propia variante autenticada y ésta la sombrea en ese módulo.
"""

import json

import pytest
from fastapi.testclient import TestClient

from nina import analytics, config, ingest, main, remote, science, store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for key in ['NINA_LLM_BASE_URL', 'NINA_LLM_API_KEY', 'NINA_LLM_MODEL']:
        monkeypatch.delenv(key, raising=False)
    for name in ['raw', 'processed', 'models', 'boundaries', 'jobs', 'exports']:
        (tmp_path / name).mkdir()
    for module in [config, store, analytics, ingest, science, main, remote]:
        monkeypatch.setattr(module, 'DATA', tmp_path)
    for module in [config, ingest, main, remote]:
        monkeypatch.setattr(module, 'RAW', tmp_path / 'raw')
    country = {
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'properties': {'shapeID': 'test-region', 'shapeName': 'Región de prueba'},
            'geometry': {'type': 'Polygon', 'coordinates': [[[-78, -12], [-72, -12], [-72, -7], [-78, -7], [-78, -12]]]},
        }],
    }
    (tmp_path / 'boundaries' / 'departments.geojson').write_text(json.dumps(country))
    store.boundaries.cache_clear()
    with TestClient(main.app) as c:
        yield c, tmp_path
    store.boundaries.cache_clear()
