"""Bounded FIRMS acquisition and public imagery. Credentials stay on the server."""
import csv
import hashlib
import io
import json
import os
import ssl
import uuid
import calendar
from datetime import date, datetime, timedelta, timezone

import httpx
import shapely
import truststore

from .config import DATA, FIRMS
from .ingest import ingest_file

PRODUCTS = {
    'MODIS_NRT': 'modis', 'MODIS_SP': 'modis',
    'VIIRS_NOAA20_NRT': 'viirs-jpss1', 'VIIRS_NOAA20_SP': 'viirs-jpss1',
    'VIIRS_NOAA21_NRT': 'viirs-jpss2', 'VIIRS_NOAA21_SP': 'viirs-jpss2',
    'VIIRS_SNPP_SP': 'viirs-snpp',
}


def nasa_client(timeout=90):
    return httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=timeout,
                        headers={'User-Agent': 'NINA-local/0.2 (NASA Space Apps research)'})


def availability(refresh=False):
    cache=DATA/'catalog'/'firms-availability.json'
    if cache.exists() and not refresh:
        age=datetime.now(timezone.utc).timestamp()-cache.stat().st_mtime
        if age<3600: return json.loads(cache.read_text(encoding='utf-8'))
    key=os.getenv('FIRMS_MAP_KEY')
    if not key: return {'products': [], 'configured': False, 'checked_at': None}
    with nasa_client() as client:
        response=client.get(f'{FIRMS}/api/data_availability/csv/{key}/all')
        response.raise_for_status()
    records=list(csv.DictReader(io.StringIO(response.text)))
    if not records or not {'data_id','min_date','max_date'}<=set(records[0]):
        raise ValueError('FIRMS no devolvió un catálogo de disponibilidad válido')
    products=[]
    for record in records:
        if record['data_id'] in PRODUCTS:
            products.append({'product':record['data_id'],'source':PRODUCTS[record['data_id']],
                             'start':date.fromisoformat(record['min_date']).isoformat(),
                             'end':date.fromisoformat(record['max_date']).isoformat()})
    result={'products':products,'configured':True,'checked_at':datetime.now(timezone.utc).isoformat(),
            'reference':'https://firms.modaps.eosdis.nasa.gov/api/data_availability/'}
    cache.parent.mkdir(parents=True,exist_ok=True)
    cache.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def acquire(products,start=None,days=1,scope='world',geometry=None):
    key=os.getenv('FIRMS_MAP_KEY')
    if not key: raise ValueError('Configura FIRMS_MAP_KEY en .env y reinicia el servidor')
    if not 1<=days<=5 or not 1<=len(products)<=3 or any(p not in PRODUCTS for p in products):
        raise ValueError('Selecciona de uno a tres productos y entre uno y cinco días')
    catalog={p['product']:p for p in availability()['products']}
    if any(p not in catalog for p in products): raise ValueError('Uno de los productos no figura disponible en FIRMS')
    start=date.fromisoformat(start) if isinstance(start,str) else start
    start=start or min(date.fromisoformat(catalog[p]['end']) for p in products)-timedelta(days=days-1)
    end=start+timedelta(days=days-1)
    for product in products:
        item=catalog[product]
        if start<date.fromisoformat(item['start']) or end>date.fromisoformat(item['end']):
            raise ValueError(f"{product}: período disponible {item['start']} a {item['end']}")
    if scope=='world': area='world'
    elif scope=='PER': area='-81.5,-18.5,-68.5,0.1'
    elif scope=='custom' and geometry:
        bounds=shapely.geometry.shape(geometry).bounds
        area=','.join(f'{v:.5f}' for v in bounds)
        # FIRMS queries bounding boxes; exact polygon filtering happens during analysis.
        geometry=shapely.geometry.mapping(shapely.box(*bounds))
    else: raise ValueError('Área de adquisición inválida')
    results=[]
    for product in products:
        destination=DATA/'raw'/f'firms_{product}_{start}_{uuid.uuid4().hex[:8]}.csv'
        try:
            with nasa_client(180) as client, client.stream('GET',f'{FIRMS}/api/area/csv/{key}/{product}/{area}/{days}/{start}') as response:
                response.raise_for_status()
                size=0
                with destination.open('wb') as out:
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>200_000_000: raise ValueError('La consulta supera 200 MB; reduce el área o período')
                        out.write(chunk)
            with destination.open(encoding='utf-8-sig') as source:
                if 'latitude' not in source.readline().lower(): raise ValueError('FIRMS no devolvió CSV; revisa la clave y el límite de consultas')
            result=ingest_file(destination,PRODUCTS[product],'NASA FIRMS Area API (MAP_KEY omitted)',
                               start,end,'api_requested_window',spatial_scope=scope,spatial_geometry=geometry)
            results.append({'product':product,'start':str(start),'end':str(end),**result})
        except Exception:
            # An incomplete transfer is never recorded as an available window.
            if destination.exists() and not any(r.get('filename')==destination.name for r in results):
                destination.unlink(missing_ok=True)
            raise
    return {'scope':scope,'start':str(start),'end':str(end),'files':results,'synthetic':False}


def imagery_tile(z,x,y):
    if not 0<=z<=8 or not 0<=x<2**(z+1) or not 0<=y<2**z:
        raise ValueError('Tesela fuera de rango')
    folder=DATA/'tiles'/'blue-marble'/str(z)/str(x)
    path=folder/f'{y}.jpg'
    if path.exists(): return path
    span=180/(2**z)
    west=-180+x*span; north=90-y*span
    params={'SERVICE':'WMS','REQUEST':'GetMap','VERSION':'1.1.1','LAYERS':'BlueMarble_NextGeneration',
            'STYLES':'','FORMAT':'image/jpeg','WIDTH':512,'HEIGHT':512,'SRS':'EPSG:4326',
            'BBOX':f'{west},{north-span},{west+span},{north}'}
    with nasa_client(40) as client:
        response=client.get('https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi',params=params)
        response.raise_for_status()
    if not response.content.startswith(b'\xff\xd8') or len(response.content)>4_000_000:
        raise ValueError('GIBS no devolvió una imagen válida')
    folder.mkdir(parents=True,exist_ok=True)
    temporary=folder/f'{y}.{uuid.uuid4().hex}.tmp'
    temporary.write_bytes(response.content);temporary.replace(path)
    return path


def acquire_month(product,year,month,scope,geometry=None,on_progress=None):
    """Fetch a selected month in provider-supported windows, preserving partial state."""
    info=next((p for p in availability()['products'] if p['product']==product),None)
    if not info: raise ValueError('Producto no disponible')
    first=date(year,month,1);last=date(year,month,calendar.monthrange(year,month)[1])
    start=max(first,date.fromisoformat(info['start']))
    end=min(last,date.fromisoformat(info['end']))
    if start>end: raise ValueError(f"El producto no cubre ese mes: {info['start']} a {info['end']}")
    cursor=start;files=[];total=(end-start).days+1
    while cursor<=end:
        days=min(5,(end-cursor).days+1)
        result=acquire([product],cursor,days,scope,geometry)
        files.extend(result['files']);cursor+=timedelta(days=days)
        if on_progress: on_progress(min(.95,(cursor-start).days/total),f'{product}: {(cursor-start).days}/{total} días del mes incorporados')
    return {'scope':scope,'product':product,'start':str(start),'end':str(end),'files':files,
            'full_calendar_month':start==first and end==last,'synthetic':False}
