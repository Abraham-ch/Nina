"""Exporta el contrato de la API local sin iniciar el servidor."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nina.main import app


if __name__ == '__main__':
    schema = app.openapi()
    schema['servers'] = [
        {'url': 'http://127.0.0.1:8000', 'description': 'Servidor local de desarrollo'}
    ]
    output = ROOT / 'openapi.json'
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'OpenAPI exportado: {output}')
