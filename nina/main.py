import csv
import hashlib
import io
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
import httpx
import ssl
import truststore
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel,Field
from .config import ROOT, DATA, RAW, FIRMS, SOURCES
from .auth import Login, Register, attach, audit_entries, clear_session, detach
from .auth import downloads_for, downloads_last_hour, max_downloads_per_hour, max_export_rows, optional
from .auth import record_audit, record_download, require
from .auth import login as login_user, register as register_user
from .store import initialize,database,rows,boundaries,status,now,code_revision,atomic_read
from .analytics import Selection,analyze,get_analysis,points_for_analysis,selected_rows,iter_selected_rows,month_dates
from .ingest import ingest_file
from .assistant import respond
from .science import train
from .remote import availability,acquire,acquire_month,imagery_tile,PRODUCTS

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='nina-job')
@asynccontextmanager
async def lifespan(app):
    global POOL
    if POOL._shutdown: POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='nina-job')
    initialize()
    with database() as c: c.execute("UPDATE jobs SET status='interrupted',message='Proceso reiniciado; vuelve a ejecutar el trabajo.' WHERE status IN ('queued','running')")
    yield
    POOL.shutdown(wait=False,cancel_futures=True)

app=FastAPI(title='NINA · Fire atlas',version='0.3.0',lifespan=lifespan)

# Las rutas con `require()` rechazan por rol; se documentan aquí porque FastAPI
# solo añade 401/403 automáticamente cuando el medio es un esquema Security.
PROTEGIDO={401:{'description':'Authentication required'},403:{'description':'The current role does not allow this operation'}}

@app.middleware('http')
async def local_origin(request: Request,call_next):
    if request.method in ['POST','PUT','PATCH','DELETE']:
        origin=request.headers.get('origin')
        if origin and origin not in ['http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:8001','http://localhost:8001','http://127.0.0.1:5173','http://localhost:5173']:
            return Response('Origen no permitido',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    return response

def existing(identifier):
    result=get_analysis(identifier)
    if not result: raise HTTPException(404,'Analysis not found')
    with database() as c: revision=c.execute("SELECT md5(string_agg(id,',' ORDER BY id)) FROM batches").fetchone()[0]
    if result['data_revision']!=revision or result.get('software_revision')!=code_revision(): raise HTTPException(409,'The data or the software changed. Generate the analysis again before exportar o preguntar.')
    return result

def set_job(identifier,state,progress,message,result=None):
    with database() as c:
        c.execute('UPDATE jobs SET status=?,progress=?,message=?,result=?,updated_at=? WHERE id=?',[state,progress,message,json.dumps(result) if result is not None else None,now(),identifier])

def submit(kind,function,with_progress=False):
    identifier=uuid.uuid4().hex
    with database() as c: c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',[identifier,kind,'queued',0,'En cola',None,now()])
    def work():
        try:
            set_job(identifier,'running',.1,'Procesando')
            result=function(lambda p,m:set_job(identifier,'running',p,m)) if with_progress else function()
            set_job(identifier,'complete',1,'Completado',result)
        except Exception as error:
            # Never expose a provider URL which might include the MAP_KEY.
            message='Error de acceso o servicio externo' if isinstance(error,httpx.HTTPError) else str(error)[:400]
            set_job(identifier,'failed',1,message)
    POOL.submit(work)
    return {'id':identifier,'status':'queued'}

@app.post('/api/auth/register')
def register(payload:Register,request:Request,response:Response):
    """T1: registro. El primer usuario queda siempre como `admin`."""
    user,token=register_user(payload);attach(response,token,secure=request.url.scheme=='https');return user

@app.post('/api/auth/login')
def login(payload:Login,request:Request,response:Response):
    user,token=login_user(payload);attach(response,token,secure=request.url.scheme=='https');return user

@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    clear_session(request);detach(response);return {'status':'ok'}

@app.get('/api/auth/me')
def me(user:dict=Depends(require())):
    return user

@app.get('/api/downloads',responses=PROTEGIDO)
def downloads(user:dict=Depends(require('analista','admin'))):
    """T1: the user's own download history ("My downloads"). Each user only sees their own."""
    return downloads_for(user['id'])

@app.get('/api/audit',responses=PROTEGIDO)
def audit(user:dict=Depends(require('admin'))):
    """T1: who imported, synced or trained, and when. Visible only to `admin`."""
    return audit_entries()

@app.get('/api/health')
def health(): return {'status':'ok','version':'0.3.0','scope':'world','firms_key_configured':bool(os.getenv('FIRMS_MAP_KEY')),'earthdata_configured':bool(os.getenv('EARTHDATA_USERNAME')),'llm_configured':bool(os.getenv('NINA_LLM_BASE_URL') and os.getenv('NINA_LLM_API_KEY') and os.getenv('NINA_LLM_MODEL'))}

@app.get('/api/catalog')
def catalog():
    try: return availability()
    except Exception:
        path=DATA/'catalog'/'firms-availability.json'
        if path.exists(): return {**json.loads(path.read_text()),'stale':True}
        return {'products':[],'configured':bool(os.getenv('FIRMS_MAP_KEY')),'checked_at':None,'message':'No se pudo verificar la disponibilidad FIRMS'}

@app.get('/api/places')
def places():
    path=ROOT/'web'/'public'/'assets'/'countries.geojson'
    if not path.exists(): path=ROOT/'web'/'dist'/'assets'/'countries.geojson'
    if not path.exists(): return {'type':'FeatureCollection','features':[]}
    return json.loads(path.read_text(encoding='utf-8'))

@app.get('/api/imagery/blue-marble/{z}/{x}/{y}.jpg')
def imagery(z:int,x:int,y:int):
    try: path=imagery_tile(z,x,y)
    except ValueError: raise HTTPException(404,'Tile not available')
    except Exception: raise HTTPException(503,'NASA GIBS imagery temporarily unavailable')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'public, max-age=604800'})

@app.get('/api/status')
def data_status(): return status()

@app.get('/api/regions')
def regions():
    path=DATA/'boundaries'/'provenance.json'
    return {'geojson':boundaries(),'provenance':json.loads(path.read_text()) if path.exists() else None}

@app.post('/api/analyses')
def create_analysis(selection:Selection,user:dict|None=Depends(optional())):
    return analyze(selection,created_by=user['id'] if user else None)

@app.get('/api/analyses/{identifier}')
def analysis(identifier:str): return existing(identifier)

@app.get('/api/analyses/{identifier}/points')
@atomic_read
def points(identifier:str): return points_for_analysis(existing(identifier))

@app.get('/api/analyses/{identifier}/comparison')
@atomic_read
def comparison(identifier:str,viirs:Literal['viirs-snpp','viirs-jpss1','viirs-jpss2']='viirs-snpp'):
    result=existing(identifier);selection=Selection(**result['selection'])
    layers=[]
    for source,platform in [('modis','Aqua'),(viirs,'all')]:
        chosen=Selection(**{**selection.model_dump(),'source':source,'platform':platform,'metric':'observed'})
        other=analyze(chosen)
        layers.append({'source':source,'platform':platform,'selected':other['selected'],
                       'points':points_for_analysis(other,limit=8000),'analysis_id':other['id']})
    return {'layers':layers,'synthetic':False,'harmonized':False,
            'note':'Raw counts for the same period and area. The overpasses are not simultaneous; their differences do not prove a real change in fire.'}

@app.get('/api/analyses/{identifier}/evidence')
@atomic_read
def evidence(identifier:str):
    result=existing(identifier)
    with database() as c: batches=rows(c,'SELECT filename,source,sha256,bytes,rows_loaded,rejected,url,imported_at,coverage_start,coverage_end,coverage_basis,processing,spatial_scope,spatial_geometry FROM batches ORDER BY source,coverage_start')
    scope=result['selection'].get('scope','PER')
    geometry_provenance=json.loads((DATA/'boundaries'/'provenance.json').read_text()) if scope=='PER' and (DATA/'boundaries'/'provenance.json').exists() else {'crs':'WGS84 / EPSG:4326','selection':'world' if scope=='world' else 'GeoJSON of the selection; countries use Natural Earth 110m','reference':'https://www.naturalearthdata.com/about/terms-of-use/','license':'Public Domain (Natural Earth)'}
    return {'analysis':result,'batches':batches,'software_version':'0.3.0','synthetic':False,'geometry_provenance':geometry_provenance}

def csv_output(data):
    out=io.StringIO(newline='');writer=csv.writer(out)
    for row in data:
        writer.writerow([("'"+str(x)) if isinstance(x,str) and x.startswith(('=','+','-','@')) else '' if x is None else x for x in row])
    return '\ufeff'+out.getvalue()

@app.get('/api/analyses/{identifier}/exports/{kind}',responses=PROTEGIDO)
@atomic_read
def export(identifier:str,kind:Literal['series','detections','manifest','report'],user:dict=Depends(require('analista','admin'))):
    result=existing(identifier);s=Selection(**result['selection'])
    tope_filas=max_export_rows()
    if downloads_last_hour(user['id'])>=max_downloads_per_hour():
        tope=max_downloads_per_hour()
        raise HTTPException(429,f'You reached the maximum of {tope} downloads per hour. Come back later or ask for a higher limit.')
    def guardar(count):
        record_download(user['id'],identifier,kind,count,result['selection'],result.get('data_revision'))
    def demas_filas():
        return HTTPException(413,f'The export exceeds the maximum of {tope_filas} rows. Shorten the period or ask for a higher limit.')
    filas=0
    if kind=='series':
        filas=len(result['months'])
        if filas>tope_filas: raise demas_filas()
        columns=list(result['months'][0]);payload=csv_output([columns]+[[r[k] for k in columns] for r in result['months']]);mime='text/csv';suffix='csv'
    elif kind=='detections':
        a,b=month_dates(s.selected_year,s.selected_month)
        columns=['id','source','platform','acquired','latitude','longitude','frp','confidence','version','processing','daynight','fire_type','department','batch_id','scan','track']
        path=DATA/'exports'/f'{identifier}-{uuid.uuid4().hex}.csv'
        path.parent.mkdir(parents=True,exist_ok=True)
        filas=0
        try:
            with path.open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(columns)
                for record in iter_selected_rows(s,a,b):
                    if filas>=tope_filas: raise demas_filas()
                    writer.writerow([("'"+str(x)) if isinstance(x,str) and x.startswith(('=','+','-','@')) else '' if x is None else x for x in (record[k] for k in columns)])
                    filas+=1
        except Exception:
            path.unlink(missing_ok=True)
            raise
        guardar(filas)
        return FileResponse(path,media_type='text/csv;charset=utf-8',filename=f'NINA_{identifier}_detections.csv',
                            background=BackgroundTask(path.unlink,missing_ok=True))
    elif kind=='manifest':
        from fastapi.encoders import jsonable_encoder
        payload=json.dumps(jsonable_encoder(evidence(identifier)),ensure_ascii=False,indent=2);mime='application/json';suffix='json'
    else:
        answer=respond(result,'prepare a report')['answer']
        payload='NINA · Observations report\n\n'+answer+'\n\n'+'\n'.join(result['limitations'])+'\n\nAnalysis: '+identifier+'\nSources:\n'+'\n'.join(result['references']);mime='text/plain';suffix='txt'
    guardar(filas)
    return Response(payload,media_type=mime+';charset=utf-8',headers={'Content-Disposition':f'attachment; filename="NINA_{identifier}_{kind}.{suffix}"'})

class Question(BaseModel):
    analysis_id:str
    question:str=Field(min_length=1,max_length=600)
    role:Literal['gestion','ciencia','comunicacion']='gestion'
@app.post('/api/assistant')
def assistant(q:Question): return respond(existing(q.analysis_id),q.question,q.role)

@app.get('/api/models')
def models():
    path=DATA/'models'/'benchmark.json'
    return json.loads(path.read_text()) if path.exists() else {'models':{},'scientific_harmonization_status':'pending_L2_opportunities'}

@app.post('/api/models/train',responses=PROTEGIDO)
def train_model(user:dict=Depends(require('admin'))):
    record_audit(user,'train','modelos','queued')
    return submit('exploratory_model',train)

@app.get('/api/jobs')
def jobs():
    with database() as c: return rows(c,'SELECT * FROM jobs ORDER BY updated_at DESC LIMIT 30')

@app.get('/api/jobs/{identifier}')
def job(identifier:str):
    with database() as c: found=rows(c,'SELECT * FROM jobs WHERE id=?',[identifier])
    if not found: raise HTTPException(404,'Job not found')
    return found[0]

@app.post('/api/import',responses=PROTEGIDO)
async def upload(file:UploadFile=File(...),source:Literal['modis','viirs-snpp','viirs-jpss1','viirs-jpss2']=Form(...),coverage_start:date|None=Form(None),coverage_end:date|None=Form(None),spatial_scope:Literal['PER','world','custom']=Form('PER'),spatial_geometry:str|None=Form(None),user:dict=Depends(require('admin'))):
    if coverage_start and coverage_end and coverage_start>coverage_end: raise HTTPException(422,'Invalid coverage range')
    try:
        geometry=json.loads(spatial_geometry) if spatial_geometry else None
        Selection(scope=spatial_scope,geometry=geometry)
    except (ValueError,TypeError): raise HTTPException(422,'Invalid file geometry')
    path=RAW/('upload_'+uuid.uuid4().hex+'.csv');size=0
    try:
        with path.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>200_000_000: raise HTTPException(413,'Maximum 200 MB per file')
                out.write(chunk)
    except Exception:
        path.unlink(missing_ok=True);raise
    finally: await file.close()
    record_audit(user,'import',file.filename,'queued')
    return submit('import_csv',lambda:ingest_file(path,source,'local_upload',coverage_start,coverage_end,'user_declared' if coverage_start and coverage_end else 'unknown',spatial_scope=spatial_scope,spatial_geometry=geometry,created_by=user['id']))

class Sync(BaseModel):
    source:Literal['MODIS_NRT','VIIRS_NOAA20_NRT','VIIRS_NOAA21_NRT']='VIIRS_NOAA20_NRT'
    start:date
    days:int=Field(default=1,ge=1,le=5)

@app.post('/api/sync',responses=PROTEGIDO)
def sync(body:Sync,user:dict=Depends(require('admin'))):
    key=os.getenv('FIRMS_MAP_KEY')
    if not key: raise HTTPException(409,'Set FIRMS_MAP_KEY in .env and restart the server to enable recent data.')
    record_audit(user,'sync',body.source,'queued')
    return submit('sync_nrt',lambda:acquire([body.source],body.start,body.days,'PER'))

class Acquisition(BaseModel):
    products:list[Literal['MODIS_NRT','MODIS_SP','VIIRS_NOAA20_NRT','VIIRS_NOAA20_SP','VIIRS_NOAA21_NRT','VIIRS_NOAA21_SP','VIIRS_SNPP_SP']]=Field(default=['MODIS_NRT','VIIRS_NOAA20_NRT','VIIRS_NOAA21_NRT'],min_length=1,max_length=3)
    start:date|None=None
    days:int=Field(default=1,ge=1,le=5)
    scope:Literal['world','PER','custom']='world'
    geometry:dict|None=None

@app.post('/api/acquisitions',responses=PROTEGIDO)
def acquisition(body:Acquisition,user:dict=Depends(require('admin'))):
    if not os.getenv('FIRMS_MAP_KEY'): raise HTTPException(409,'Set FIRMS_MAP_KEY in .env and restart the server')
    try: Selection(scope=body.scope,geometry=body.geometry)
    except ValueError as error: raise HTTPException(422,'Invalid geometry or scope')
    record_audit(user,'acquire',f'{len(body.products)} productos','queued')
    return submit('acquire_'+body.scope,lambda:acquire(body.products,body.start,body.days,body.scope,body.geometry))

@app.get('/api/experiments/substitution')
def substitution(source:Literal['viirs-snpp','viirs-jpss1']='viirs-snpp',department:str|None=None):
    from .science import substitution_experiment
    return substitution_experiment(source,department)

class ArchiveMonth(BaseModel):
    product:Literal['MODIS_NRT','MODIS_SP','VIIRS_NOAA20_NRT','VIIRS_NOAA20_SP','VIIRS_NOAA21_NRT','VIIRS_NOAA21_SP','VIIRS_SNPP_SP']
    year:int=Field(ge=2000,le=2100)
    month:int=Field(ge=1,le=12)
    scope:Literal['world','PER','custom']='custom'
    geometry:dict|None=None

@app.post('/api/acquisitions/month',responses=PROTEGIDO)
def archive_month(body:ArchiveMonth,user:dict=Depends(require('admin'))):
    if not os.getenv('FIRMS_MAP_KEY'): raise HTTPException(409,'Set FIRMS_MAP_KEY in .env and restart the server')
    try: Selection(scope=body.scope,geometry=body.geometry)
    except ValueError: raise HTTPException(422,'Invalid geometry or scope')
    record_audit(user,'acquire_month',f'{body.product} {body.year}-{body.month:02d}','queued')
    return submit('archive_month',lambda progress:acquire_month(body.product,body.year,body.month,body.scope,body.geometry,progress),with_progress=True)

from .harmonized import router as harmonized_router
app.include_router(harmonized_router)
from .reports import router as reports_router
app.include_router(reports_router)
from .analyst import router as analyst_router
app.include_router(analyst_router)

dist=ROOT/'web'/'dist'
if dist.exists(): app.mount('/',StaticFiles(directory=str(dist),html=True),name='web')
