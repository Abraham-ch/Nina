import heapq
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
    if s.scope=='world':
        # Si existen archivos mundiales, no completar sus meses anteriores o sus
        # huecos con el archivo regional peruano. Las filas globales sin fechas
        # declaradas siguen siendo observaciones válidas del lote importado.
        clauses.append("""(NOT EXISTS(SELECT 1 FROM batches wb WHERE wb.spatial_scope='world' AND wb.source=observations.source)
            OR batch_id IN (SELECT id FROM batches wb WHERE wb.spatial_scope='world' AND wb.source=observations.source)
            OR EXISTS(SELECT 1 FROM batches wb WHERE wb.spatial_scope='world' AND wb.source=observations.source
                AND observations.acquired::DATE BETWEEN wb.coverage_start AND wb.coverage_end))""")
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

OBSERVATION_COLUMNS = (
    'id','source','platform','acquired','latitude','longitude','frp','confidence',
    'version','processing','daynight','fire_type','department','batch_id','scan','track',
)
POINT_COLUMNS = (
    'id','source','platform','acquired','latitude','longitude','frp','confidence',
    'daynight','scan','track',
)


def _selected_chunks(s,start=None,end=None,source=None,platform=None,
                     columns=OBSERVATION_COLUMNS,chunk_size=8192):
    """Lee bloques acotados y aplica el polígono exacto, incluyendo sus bordes.

    El consumidor debe agotar o cerrar el generador en el mismo hilo, porque
    la conexión mantiene el bloqueo de la revisión mientras está abierta.
    """
    if chunk_size<1: raise ValueError('El tamaño de bloque debe ser positivo')
    if not columns or any(column not in OBSERVATION_COLUMNS for column in columns):
        raise ValueError('Columnas de observación inválidas')
    where,args=filters(s,start,end,source,platform)
    geometry=shapely.geometry.shape(s.geometry) if s.geometry else None
    if geometry is not None:
        shapely.prepare(geometry)
        latitude_index=columns.index('latitude');longitude_index=columns.index('longitude')
    with database() as connection:
        cursor=connection.execute('SELECT '+','.join(columns)+' FROM observations WHERE '+where,args)
        while chunk:=cursor.fetchmany(chunk_size):
            if geometry is not None:
                keep=shapely.covers(geometry,shapely.points(
                    [row[longitude_index] for row in chunk],
                    [row[latitude_index] for row in chunk],
                ))
                chunk=[row for row,inside in zip(chunk,keep) if inside]
            if chunk: yield chunk


def iter_selected_rows(s,start=None,end=None,source=None,platform=None,chunk_size=8192):
    """Itera todas las detecciones seleccionadas sin cargarlas juntas en memoria.

    Para una exportación HTTP, consumir en un hilo hasta un archivo temporal
    y servir ese archivo. No trasladar este generador abierto entre hilos.
    """
    for chunk in _selected_chunks(s,start,end,source,platform,chunk_size=chunk_size):
        for row in chunk: yield dict(zip(OBSERVATION_COLUMNS,row))


def selected_rows(s,start=None,end=None,source=None,platform=None):
    """Compatibilidad para consultas pequeñas; exportaciones usan el iterador."""
    return list(iter_selected_rows(s,start,end,source,platform))

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
        for chunk in _selected_chunks(s,start,end,columns=('acquired','latitude','longitude')):
            for acquired,_,_ in chunk:
                k=(acquired.year,acquired.month)
                grouped[k]=grouped.get(k,0)+1
    with database() as c:
        coverage=rows(c,'SELECT coverage_start,coverage_end,coverage_basis,spatial_scope,spatial_geometry FROM batches WHERE source=?',[s.source])
        revision=c.execute('SELECT md5(string_agg(id,\',\' ORDER BY id)) FROM batches').fetchone()[0]
    coverage=[x for x in coverage if spatial_coverage(x,s)]
    def available(y,m):
        a,b=month_dates(y,m)
        if s.source=='modis' and s.platform=='Aqua' and a<date(2002,8,1): return False
        cursor=a
        for x in sorted((x for x in coverage if x['coverage_start'] and x['coverage_end']
                         and x['coverage_basis']!='observed_dates_only'),key=lambda x:x['coverage_start']):
            if x['coverage_start']>cursor: continue
            cursor=max(cursor,x['coverage_end']+timedelta(days=1))
            if cursor>=b: return True
        return False
    def partial(y,m,declared_only=False):
        a,b=month_dates(y,m)
        return any(x['coverage_start'] and x['coverage_end'] and x['coverage_start']<b and x['coverage_end']>=a
                   and (not declared_only or x['coverage_basis']!='observed_dates_only') for x in coverage)
    model=None
    if s.metric=='experimental':
        path=DATA/'models'/'benchmark.json'
        if path.exists(): model=json.loads(path.read_text()).get('models',{}).get(s.source)
    def value(y,m):
        if not available(y,m):
            # Las fechas mínima/máxima de registros no prueban integridad del archivo
            # ni permiten inventar ceros para otras áreas dentro de esa ventana.
            return grouped.get((y,m),0) if s.metric=='observed' and (partial(y,m,declared_only=True) or (y,m) in grouped) else None
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
        c.execute('INSERT OR IGNORE INTO analyses(id,selection,result,created_at) VALUES (?,?,?,?)',[analysis_id,json.dumps(s.model_dump()),json.dumps(result),now()])
    return result

def get_analysis(identifier):
    with database() as c: row=c.execute('SELECT result FROM analyses WHERE id=?',[identifier]).fetchone()
    if not row: return None
    return json.loads(row[0])

@atomic_read
def points_for_analysis(result, limit=10000):
    """Muestra acotada por hash estable; total calculado antes del muestreo."""
    if limit<1: raise ValueError('El límite de puntos debe ser positivo')
    s=Selection(**result['selection']);a,b=month_dates(s.selected_year,s.selected_month)
    if not s.geometry:
        where,args=filters(s,a,b)
        with database() as connection:
            total=connection.execute('SELECT count(*) FROM observations WHERE '+where,args).fetchone()[0]
            records=rows(connection,'SELECT '+','.join(POINT_COLUMNS)+
                         ' FROM observations WHERE '+where+' ORDER BY id LIMIT ?',[*args,limit])
    else:
        total=0
        def candidates():
            nonlocal total
            for chunk in _selected_chunks(s,a,b,columns=POINT_COLUMNS):
                total+=len(chunk)
                for row in chunk: yield row
        # nsmallest mantiene como máximo limit candidatos, no todo el país.
        sample=heapq.nsmallest(limit,candidates(),key=lambda row:row[0])
        records=[dict(zip(POINT_COLUMNS,row)) for row in sample]
    features=[{'type':'Feature','geometry':{'type':'Point','coordinates':[r['longitude'],r['latitude']]},'properties':{'id':r['id'],'source':r['source'],'platform':r['platform'],'date':str(r['acquired']),'frp':r['frp'],'confidence':r['confidence'],'daynight':r['daynight'],'scan':r['scan'],'track':r['track']}} for r in records]
    return {'type':'FeatureCollection','features':features,'total':total,'shown':len(features),'sampling':'deterministic','synthetic':False}
