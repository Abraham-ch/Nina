import calendar
import hashlib
import json
import statistics
from datetime import date, datetime, timedelta
from typing import Literal
import shapely
from pydantic import BaseModel, Field, model_validator
from .store import database, rows, boundaries, now, code_revision,atomic_read
from .config import DATA

class Selection(BaseModel):
    scope: Literal['PER','world','custom'] = 'PER'
    area_label: str = Field(default='',max_length=100)
    department: str = 'all'
    source: Literal['modis','viirs-snpp','viirs-jpss1','viirs-jpss2'] = 'modis'
    platform: Literal['all','Aqua','Terra'] = 'Aqua'
    year_start: int = Field(default=2018,ge=2000,le=2100)
    year_end: int = Field(default=2025,ge=2000,le=2100)
    selected_year: int = Field(default=2025,ge=2000,le=2100)
    selected_month: int = Field(default=9,ge=1,le=12)
    metric: Literal['observed','experimental'] = 'observed'
    daynight: Literal['all','D','N'] = 'all'
    fire_type: Literal['all','vegetation'] = 'all'
    geometry: dict | None = None

    @model_validator(mode='after')
    def valid(self):
        if self.year_start>self.year_end or not self.year_start<=self.selected_year<=self.year_end: raise ValueError('El año seleccionado debe estar dentro del rango')
        if self.department!='all' and self.department not in {f['properties']['id'] for f in boundaries()['features']}: raise ValueError('Departamento desconocido')
        if self.scope!='PER' and self.department!='all': raise ValueError('Las divisiones regionales corresponden al archivo peruano')
        if self.scope=='custom' and not self.geometry: raise ValueError('Selecciona una geometría para esta área')
        if self.geometry:
            try:
                g=shapely.geometry.shape(self.geometry)
                if g.geom_type not in ['Polygon','MultiPolygon'] or not g.is_valid or g.is_empty or len(json.dumps(self.geometry))>100000: raise ValueError()
                w,s,e,n=g.bounds
                if not(-180<=w<e<=180 and -90<=s<n<=90): raise ValueError()
                if self.scope=='PER' and not(-82<=w<e<=-68 and -19<=s<n<=1): raise ValueError()
            except Exception: raise ValueError('Polígono inválido; utiliza coordenadas geográficas WGS84')
        return self

def filters(s, start=None, end=None, source=None, platform=None):
    clauses=['source=?'];args=[source or s.source]
    if s.scope=='PER': clauses.append("(department IS NOT NULL OR batch_id IN (SELECT id FROM batches WHERE spatial_scope='PER'))")
    plat=platform if platform is not None else s.platform
    if (source or s.source)=='modis' and plat!='all': clauses.append('platform=?');args.append(plat)
    if s.department!='all': clauses.append('department=?');args.append(s.department)
    if start: clauses.append('acquired>=?');args.append(start)
    if end: clauses.append('acquired<?');args.append(end)
    if s.daynight!='all': clauses.append('daynight=?');args.append(s.daynight)
    if s.fire_type=='vegetation': clauses.append('fire_type=0')
    if s.geometry:
        w,south,e,n=shapely.geometry.shape(s.geometry).bounds
        clauses.append('longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?');args.extend([w,e,south,n])
    return ' AND '.join(clauses),args

def selected_rows(s,start=None,end=None,source=None,platform=None):
    where,args=filters(s,start,end,source,platform)
    with database() as c: result=rows(c,'SELECT * FROM observations WHERE '+where,args)
    if s.geometry:
        g=shapely.geometry.shape(s.geometry)
        if result:
            keep=shapely.covers(g,shapely.points([r['longitude'] for r in result],[r['latitude'] for r in result]))
            result=[r for r,k in zip(result,keep) if k]
    return result

def month_dates(year,month):
    start=date(year,month,1)
    end=date(year+1,1,1) if month==12 else date(year,month+1,1)
    return start,end

def name(s):
    if s.scope=='world': return 'El planeta'
    if s.scope=='custom': return s.area_label or 'Área personalizada'
    department=next((f['properties']['name'] for f in boundaries()['features'] if f['properties']['id']==s.department),'Perú completo')
    return department+(' · polígono personalizado' if s.geometry else '')


def spatial_coverage(batch,s):
    if batch['spatial_scope']=='world': return True
    if batch['spatial_scope']=='PER': return s.scope=='PER'
    if not batch.get('spatial_geometry'): return False
    geometry=shapely.geometry.shape(json.loads(batch['spatial_geometry']))
    if s.geometry: return bool(geometry.covers(shapely.geometry.shape(s.geometry)))
    if s.scope=='world': return False
    features=boundaries()['features']
    chosen=[shapely.geometry.shape(f['geometry']) for f in features if s.department=='all' or f['properties']['id']==s.department]
    return bool(chosen and geometry.covers(shapely.union_all(chosen)))

@atomic_read
def analyze(s):
    start=date(max(2000,s.year_start-10),1,1);end=date(s.year_end+1,1,1)
    grouped={}
    if not s.geometry:
        where,args=filters(s,start,end)
        with database() as c:
            for r in rows(c,'SELECT year(acquired) AS y,month(acquired) AS m,count(*) AS n FROM observations WHERE '+where+' GROUP BY y,m',args): grouped[(r['y'],r['m'])]=r['n']
    else:
        for r in selected_rows(s,start,end):
            k=(r['acquired'].year,r['acquired'].month)
            grouped[k]=grouped.get(k,0)+1
    with database() as c:
        coverage=rows(c,'SELECT coverage_start,coverage_end,coverage_basis,spatial_scope,spatial_geometry FROM batches WHERE source=?',[s.source])
        revision=c.execute('SELECT md5(string_agg(id,\',\' ORDER BY id)) FROM batches').fetchone()[0]
    coverage=[x for x in coverage if spatial_coverage(x,s)]
    def available(y,m):
        a,b=month_dates(y,m)
        if s.source=='modis' and s.platform=='Aqua' and a<date(2002,8,1): return False
        cursor=a
        for x in sorted((x for x in coverage if x['coverage_start'] and x['coverage_end']),key=lambda x:x['coverage_start']):
            if x['coverage_start']>cursor: continue
            cursor=max(cursor,x['coverage_end']+timedelta(days=1))
            if cursor>=b: return True
        return False
    def partial(y,m):
        a,b=month_dates(y,m)
        return any(x['coverage_start'] and x['coverage_end'] and x['coverage_start']<b and x['coverage_end']>=a for x in coverage)
    model=None
    if s.metric=='experimental':
        path=DATA/'models'/'benchmark.json'
        if path.exists(): model=json.loads(path.read_text()).get('models',{}).get(s.source)
    def value(y,m):
        if not available(y,m): return grouped.get((y,m),0) if s.metric=='observed' and (partial(y,m) or (y,m) in grouped) else None
        raw=grouped.get((y,m),0)
        if s.metric=='observed': return raw
        if not model or s.scope!='PER' or not 2018<=y<=2025 or s.geometry or s.department=='all' or s.fire_type!='all' or s.daynight!='all': return None
        import math
        x=[1,math.log1p(raw),math.sin(2*math.pi*m/12),math.cos(2*math.pi*m/12)]
        return round(math.exp(min(20,sum(a*b for a,b in zip(x,model['coefficients'])))),2)
    months=[]
    for y in range(s.year_start,s.year_end+1):
        for m in range(1,13):
            v=value(y,m)
            historical=[value(yy,m) for yy in range(max(2000,y-10),y) if available(yy,m)]
            historical=[x for x in historical if x is not None]
            median=statistics.median(historical) if len(historical)>=5 else None
            anomaly=100*(v/median-1) if available(y,m) and v is not None and median is not None and median>0 else None
            months.append({'year':y,'month':m,'value':v,'observed':grouped.get((y,m),0) if available(y,m) else grouped.get((y,m)),
                'historical_median':median,'historical_n':len(historical),'anomaly_percent':anomaly,
                'status':('archive_observed' if available(y,m) else 'partial_archive') if v is not None and s.metric=='observed' else 'experimental' if v is not None else 'unavailable',
                'coverage_percent':None,'interval':None})
    selected=next(x for x in months if x['year']==s.selected_year and x['month']==s.selected_month)
    snapshot={'selection':s.model_dump(),'data_revision':revision,'software_revision':code_revision(),'model_version':model.get('model_id',model.get('version')) if model else None}
    analysis_id=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()[:24]
    selected_start,selected_end=month_dates(s.selected_year,s.selected_month)
    result={'id':analysis_id,'created_at':now(),'selection':s.model_dump(),'area_name':name(s),'data_revision':revision,'software_revision':code_revision(),
        'months':months,'selected':selected,
        'archive_windows':[{'start':str(x['coverage_start']),'end':str(x['coverage_end']),'basis':x['coverage_basis'],'scope':x['spatial_scope']} for x in coverage if x['coverage_start']],
        'harmonization_status':'exploratory_peru' if s.metric=='experimental' else 'observed_not_harmonized',
        'synthetic':False,'metric_label':'Detecciones observadas' if s.metric=='observed' else 'Estimación exploratoria equivalente a Aqua',
        'limitations':['Son píxeles detectados, no incendios individuales ni superficie quemada.',
            'Cobertura de cielo y oportunidades válidas todavía no reconstruidas; un cero del archivo no prueba ausencia de fuego.',
            'Las anomalías de conteos brutos son descriptivas y no están corregidas por cambios de observación.',
            *(['Modelo experimental ajustado a conteos mensuales, sin corrección de exposición. No es una armonización científica validada.'] if s.metric=='experimental' else [])],
        'references':['https://firms.modaps.eosdis.nasa.gov/country/' if s.scope=='PER' else 'https://firms.modaps.eosdis.nasa.gov/api/area/','https://www.earthdata.nasa.gov/data/tools/firms/faq']}
    with database() as c:
        c.execute('INSERT OR IGNORE INTO analyses VALUES (?,?,?,?)',[analysis_id,json.dumps(s.model_dump()),json.dumps(result),now()])
    return result

def get_analysis(identifier):
    with database() as c: row=c.execute('SELECT result FROM analyses WHERE id=?',[identifier]).fetchone()
    if not row: return None
    return json.loads(row[0])

def points_for_analysis(result, limit=10000):
    s=Selection(**result['selection']);a,b=month_dates(s.selected_year,s.selected_month)
    records=selected_rows(s,a,b)
    # Deterministic sample, independent of acquisition ordering; export still contains all rows.
    records.sort(key=lambda r:r['id'])
    step=max(1,(len(records)+limit-1)//limit)
    features=[{'type':'Feature','geometry':{'type':'Point','coordinates':[r['longitude'],r['latitude']]},'properties':{'id':r['id'],'source':r['source'],'platform':r['platform'],'date':str(r['acquired']),'frp':r['frp'],'confidence':r['confidence'],'daynight':r['daynight'],'scan':r['scan'],'track':r['track']}} for r in records[::step]]
    return {'type':'FeatureCollection','features':features,'total':len(records),'shown':len(features),'sampling':'deterministic','synthetic':False}
