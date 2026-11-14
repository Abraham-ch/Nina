"""Vuelca openapi.json para generar los tipos TS: python -m fire_api.export_openapi <ruta>."""

import json
import sys
from pathlib import Path

from fire_api.main import app

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
