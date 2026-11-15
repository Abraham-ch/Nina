"""Consultas mundiales con memoria acotada y recorte exacto, sobre fixtures."""
import hashlib
from datetime import date,datetime

import pytest

from nina import analytics,store


@pytest.fixture()
def isolated_database(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    monkeypatch.setattr(analytics,'DATA',tmp_path)
    store.boundaries.cache_clear()
    store.initialize()
    yield tmp_path
    store.boundaries.cache_clear()


def add_rows(coordinates,month=9,platform='Aqua'):
    values=[]
    for index,(longitude,latitude) in enumerate(coordinates):
        identifier=hashlib.sha256(f'{platform}:{month}:{longitude}:{latitude}:{index}'.encode()).hexdigest()[:32]
        values.append((identifier,'modis',platform,datetime(2026,month,3,1,0),
                       latitude,longitude,5.0,'90','61.03','SP','N',0,None,'fixture',1.0,1.0))
    with store.database() as connection:
        connection.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',values)
    return values


def selection(**kwargs):
    return analytics.Selection(scope='world',year_start=2026,year_end=2026,
                               selected_year=2026,selected_month=9,**kwargs)


def test_world_sample_is_limited_stable_and_keeps_full_total(isolated_database,monkeypatch):
    values=add_rows([(x-60,15) for x in range(120)])
    add_rows([(150,20)],platform='Terra')
    add_rows([(140,25)],month=8)
    # El camino mundial debe utilizar SQL acotado, no la función que devuelve todo.
    monkeypatch.setattr(analytics,'selected_rows',lambda *a,**k:pytest.fail('Carga completa en memoria'))
    result={'selection':selection().model_dump()}
    first=analytics.points_for_analysis(result,limit=7)
    second=analytics.points_for_analysis(result,limit=7)
    assert first==second
    assert first['total']==120 and first['shown']==7
    assert [p['properties']['id'] for p in first['features']]==sorted(v[0] for v in values)[:7]
    assert len(list(analytics.iter_selected_rows(selection(),date(2026,9,1),date(2026,10,1),chunk_size=11)))==120


def test_polygon_hole_boundary_and_monthly_counts_agree(isolated_database,monkeypatch):
    polygon={'type':'Polygon','coordinates':[
        [[0,0],[10,0],[10,10],[0,10],[0,0]],
        [[4,4],[4,6],[6,6],[6,4],[4,4]],
    ]}
    # Interiores, borde exterior, interior del hueco, borde del hueco y exterior.
    add_rows([(1,1),(2,2),(0,5),(5,5),(4,5),(12,5)])
    add_rows([(3,3)],month=8)
    chosen=analytics.Selection(**{**selection().model_dump(),'scope':'custom','geometry':polygon})
    monkeypatch.setattr(analytics,'selected_rows',lambda *a,**k:pytest.fail('Carga completa en memoria'))
    analysis=analytics.analyze(chosen)
    sample=analytics.points_for_analysis(analysis,limit=2)
    exported=list(analytics.iter_selected_rows(chosen,date(2026,9,1),date(2026,10,1),chunk_size=2))
    assert analysis['selected']['value']==4
    assert analysis['selected']['status']=='partial_archive'
    assert sample['total']==4 and sample['shown']==2
    assert {(r['longitude'],r['latitude']) for r in exported}=={(1,1),(2,2),(0,5),(4,5)}
    assert next(m for m in analysis['months'] if m['month']==8)['value']==1
    assert analysis['selected']['historical_median'] is None


def test_empty_world_selection_and_invalid_sample_limit(isolated_database):
    result={'selection':selection().model_dump()}
    assert analytics.points_for_analysis(result)['features']==[]
    assert analytics.points_for_analysis(result)['total']==0
    with pytest.raises(ValueError,match='positive'):
        analytics.points_for_analysis(result,limit=0)


def test_spatial_chunks_never_exceed_requested_size(isolated_database):
    add_rows([(x/10,1) for x in range(25)])
    chosen=analytics.Selection(**{**selection().model_dump(),'scope':'custom',
        'geometry':{'type':'Polygon','coordinates':[[[0,0],[3,0],[3,2],[0,2],[0,0]]]}})
    chunks=list(analytics._selected_chunks(chosen,chunk_size=4))
    assert sum(map(len,chunks))==25
    assert max(map(len,chunks))<=4


def test_observed_dates_do_not_claim_complete_month_or_empty_area_zero(isolated_database):
    add_rows([(1,1)])
    with store.database() as connection:
        connection.execute('''INSERT INTO batches
            (id,source,coverage_start,coverage_end,coverage_basis,spatial_scope)
            VALUES ('fixture','modis','2026-09-01','2026-09-30','observed_dates_only','world')''')
    observed=analytics.analyze(selection())
    assert observed['selected']['value']==1
    assert observed['selected']['status']=='partial_archive'
    assert observed['selected']['anomaly_percent'] is None
    empty=analytics.Selection(**{**selection().model_dump(),'scope':'custom',
        'geometry':{'type':'Polygon','coordinates':[[[30,30],[31,30],[31,31],[30,31],[30,30]]]}})
    assert analytics.analyze(empty)['selected']['value'] is None


def test_global_calendar_does_not_fill_earlier_months_with_peru_only(isolated_database):
    add_rows([(-70,-10)],month=1)
    add_rows([(140,-30)],month=9)
    with store.database() as connection:
        connection.execute('''INSERT INTO batches
            (id,source,coverage_start,coverage_end,coverage_basis,spatial_scope)
            VALUES ('world-later','modis','2026-09-01','2026-09-30','observed_dates_only','world')''')
    result=analytics.analyze(selection())
    assert result['selected']['value']==1
    january=next(month for month in result['months'] if month['month']==1)
    assert january['value'] is None and january['status']=='unavailable'
