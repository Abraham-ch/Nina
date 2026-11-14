"""Normalize published reference geometry for WGS84 queries; no invented outlines."""
import json
from pathlib import Path
import shapely

ROOT=Path(__file__).resolve().parent.parent
path=ROOT/'web/public/assets/countries.geojson'
data=json.loads(path.read_text(encoding='utf-8'))
repaired=[]

def coordinates(value):
    if isinstance(value,list) and len(value)>=2 and isinstance(value[0],(int,float)):
        return [max(-180,min(180,round(value[0],6))),max(-90,min(90,round(value[1],6))),*value[2:]]
    return [coordinates(item) for item in value]

for feature in data['features']:
    feature['geometry']['coordinates']=coordinates(feature['geometry']['coordinates'])
    geometry=shapely.geometry.shape(feature['geometry'])
    if not geometry.is_valid:
        geometry=shapely.make_valid(geometry)
        if geometry.geom_type=='GeometryCollection':
            geometry=shapely.union_all([g for g in geometry.geoms if g.geom_type in ['Polygon','MultiPolygon']])
        feature['geometry']=shapely.geometry.mapping(geometry)
        feature['properties']['geometry_repaired']=True
        repaired.append(feature['properties']['name'])
    assert geometry.geom_type in ['Polygon','MultiPolygon'] and geometry.is_valid and not geometry.is_empty
path.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
print(json.dumps({'countries':len(data['features']),'topology_repairs':repaired,'coordinate_precision':'6 decimal places; WGS84 bounds clamped'},ensure_ascii=False))
