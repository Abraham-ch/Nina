"""Embed public geometry, imagery and a small real FIRMS sample in the concept."""
import base64
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
connection = duckdb.connect()
rows = connection.execute(
    """
    SELECT round(longitude, 5), round(latitude, 5), source
    FROM read_parquet(?)
    WHERE acquired >= '2025-09-01' AND acquired < '2025-10-01'
      AND ((source = 'modis' AND platform = 'Aqua') OR source = 'viirs-snpp')
    QUALIFY row_number() OVER (PARTITION BY source ORDER BY hash(id)) <= 100
    """,
    [str(ROOT.parent / 'data/processed/observations.parquet')],
).fetchall()
assets = {
    'world': json.loads((ROOT / 'world-110m.topojson').read_text(encoding='utf-8')),
    'image': 'data:image/jpeg;base64,' + base64.b64encode((ROOT / 'earth-gibs.jpg').read_bytes()).decode('ascii'),
    'regionImage': 'data:image/jpeg;base64,' + base64.b64encode((ROOT / 'peru-gibs.jpg').read_bytes()).decode('ascii'),
    'regionBounds': [-110, -55, -30, 20],
    'points': [{'lon': lon, 'lat': lat, 'source': source} for lon, lat, source in rows],
}
path = ROOT / 'nina-design-directions.html'
content = path.read_text(encoding='utf-8')
start = content.index('<script id="nina-concept-assets" type="application/json">')
start = content.index('>', start) + 1
end = content.index('</script>', start)
content = content[:start] + json.dumps(assets, separators=(',', ':')) + content[end:]
path.write_text(content, encoding='utf-8')
assert path.stat().st_size < 1_000_000
print(json.dumps({'bytes': path.stat().st_size, 'real_points': len(rows), 'period': '2025-09'}))
