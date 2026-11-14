"""Genera web/public/assets/landing-peru.json: contorno del Perú y detecciones reales semanales para la portada.

Usa un solo observador (VIIRS NOAA-20) para no mezclar sensores. Agrega por semana UTC (lunes) y celda de 0,1°.
Las semanas fuera de la cobertura del lote no se rellenan con ceros. Lee la base en modo solo lectura.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import shapely

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from nina.config import DATA  # noqa: E402

CELL = 0.1


def outline():
    features = json.loads((DATA / 'boundaries' / 'departments.geojson').read_text(encoding='utf-8'))['features']
    names = {f['properties']['shapeID']: f['properties']['shapeName'] for f in features}
    shapes = {f['properties']['shapeID']: shapely.geometry.shape(f['geometry']) for f in features}
    country = shapely.union_all([shapely.geometry.shape(f['geometry']) for f in features]).simplify(0.01)
    polygons = list(country.geoms) if country.geom_type == 'MultiPolygon' else [country]
    rings = [[[round(x, 3), round(y, 3)] for x, y in p.exterior.coords] for p in polygons if p.area > 0.001]
    return rings, [round(v, 3) for v in country.bounds], names, shapes


def rings_of(shape, tolerance=0.02):
    """Anillos exteriores simplificados (para dibujar contornos en la portada)."""
    shape = shape.simplify(tolerance)
    polygons = list(shape.geoms) if shape.geom_type == 'MultiPolygon' else [shape]
    return [[[round(x, 3), round(y, 3)] for x, y in p.exterior.coords] for p in polygons if p.area > 0.001]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='viirs-jpss1')
    parser.add_argument('--out', type=Path, default=ROOT / 'web' / 'public' / 'assets' / 'landing-peru.json')
    args = parser.parse_args()
    rings, bounds, names, shapes = outline()
    con = duckdb.connect(str(DATA / 'nina.duckdb'), read_only=True)
    where = 'source = ? AND department IS NOT NULL'
    platform, first, last, total = con.execute(
        f'SELECT any_value(platform), min(acquired)::DATE, max(acquired)::DATE, count(*) FROM observations WHERE {where}',
        [args.source]).fetchone()
    if not total:
        raise SystemExit(f'No hay detecciones de {args.source} en Perú en {DATA / "nina.duckdb"}')
    rows = con.execute(f'''
        SELECT date_trunc('week', acquired)::DATE AS week,
               CAST(round(longitude / {CELL}) AS INTEGER) AS i, CAST(round(latitude / {CELL}) AS INTEGER) AS j,
               count(*) AS n, round(sum(coalesce(frp, 0)), 1) AS frp
        FROM observations WHERE {where} GROUP BY ALL ORDER BY week, n DESC''', [args.source]).fetchall()
    departments = [{'name': names.get(d, d), 'count': n, 'outline': rings_of(shapes[d]) if i < 3 and d in shapes else None}
                   for i, (d, n) in enumerate(con.execute(
        f'SELECT department, count(*) FROM observations WHERE {where} GROUP BY 1 ORDER BY 2 DESC', [args.source]).fetchall())]
    daynight = dict(con.execute(
        f'SELECT daynight, count(*) FROM observations WHERE {where} GROUP BY 1', [args.source]).fetchall())
    weeks = {}
    for week, i, j, n, frp in rows:
        weeks.setdefault(week.isoformat(), []).append([i, j, n, frp])
    # Todas las semanas de la cobertura; las extremas son parciales (no comparables con las completas).
    start = con.execute("SELECT date_trunc('week', ?::DATE)::DATE", [first]).fetchone()[0]
    series = con.execute("SELECT range::DATE FROM range(?::DATE, ?::DATE + 1, INTERVAL 7 DAY)", [start, last]).fetchall()
    output = []
    for (week,) in series:
        cells = weeks.get(week.isoformat(), [])
        output.append({'week': week.isoformat(), 'count': sum(c[2] for c in cells), 'frp': round(sum(c[3] for c in cells), 1),
                       'partial': week < first or (week.toordinal() + 6) > last.toordinal(), 'cells': cells})
    peak = max(output, key=lambda w: w['count'])
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': args.source, 'platform': platform, 'first_date': first.isoformat(), 'last_date': last.isoformat(),
        'detections': total, 'cell_degrees': CELL, 'bounds': bounds, 'outline': rings,
        'peak_week': peak['week'], 'peak_count': peak['count'], 'departments': departments,
        'night': daynight.get('N', 0), 'weeks': output,
        'note': 'Detecciones de focos activos NASA FIRMS (píxeles térmicos, no incendios individuales). Semana UTC desde el lunes.',
    }
    args.out.write_text(json.dumps(payload, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'out': str(args.out), 'bytes': args.out.stat().st_size, 'weeks': len(output), 'detections': total,
                      'peak_week': peak['week'], 'peak_count': peak['count']}))


if __name__ == '__main__':
    main()
