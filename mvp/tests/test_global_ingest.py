"""La importación mundial conserva fuentes, audita descartes y respeta revisiones."""
import csv
import json

import pytest

from nina import global_ingest,store


@pytest.fixture()
def data_dir(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    monkeypatch.setattr(global_ingest,'DATA',tmp_path)
    (tmp_path/'processed').mkdir()
    store.boundaries.cache_clear()
    global_ingest.prepare_bulk_table()
    yield tmp_path
    store.boundaries.cache_clear()


def row(latitude=-30,longitude=140,day='2026-01-03',**values):
    return dict(latitude=latitude,longitude=longitude,acq_date=day,acq_time='0618',
                satellite='Aqua',confidence='90',daynight='D',version='61.03',
                type='0',frp=12,scan=1,track=1,instrument='MODIS',**values)


def write_json(path,records):
    path.write_text(json.dumps(records),encoding='utf-8')
    return path


def test_world_retention_deduplication_and_repeat_are_audited(data_dir):
    records=[row(),row(latitude=40,longitude=-120),row(latitude=22,longitude=78),row()]
    path=write_json(data_dir/'fire_archive_M-C61_fixture.json',records)
    report=global_ingest.import_global_file(path,progress=lambda _:None)
    assert report['rows_read']==4 and report['rows_loaded']==3
    assert report['qa_reasons']['duplicate']==1
    assert report['coverage_basis']=='observed_dates_only'
    assert global_ingest.import_global_file(path,progress=lambda _:None)==report
    with store.database() as c:
        assert c.execute('SELECT count(*) FROM observations').fetchone()[0]==3
        assert c.execute("SELECT spatial_scope FROM batches").fetchone()[0]=='world'


def test_standard_replaces_nrt_only_on_its_actual_platform_days(data_dir):
    first=write_json(data_dir/'fire_nrt_M-C61_first.json',[row(),row(day='2026-01-02')])
    global_ingest.import_global_file(first,progress=lambda _:None)
    standard=write_json(data_dir/'fire_archive_M-C61_fixture.json',[
        row(day='2026-01-01'),row(longitude=141),
    ])
    report=global_ingest.import_global_file(standard,progress=lambda _:None)
    assert report['existing_provisional_rows_replaced']==1
    second=write_json(data_dir/'fire_nrt_M-C61_second.json',[
        row(longitude=142),row(day='2026-01-02',longitude=142),
    ])
    incoming=global_ingest.import_global_file(second,progress=lambda _:None)
    assert incoming['qa_reasons']['superseded_by_standard']==1
    assert incoming['rows_loaded']==1
    with store.database() as c:
        assert c.execute("SELECT count(*) FROM observations WHERE processing='NRT'").fetchone()[0]==2


def test_recent_csv_optional_columns_and_outside_period(data_dir):
    path=data_dir/'MODIS_C6_1_Global_7d.csv'
    records=[row(),row(day='2024-01-01')]
    for record in records:
        record.pop('instrument');record.pop('type')
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    result=global_ingest.import_global_file(path,progress=lambda _:None)
    assert result['rows_loaded']==1 and result['rejected']==0
    assert result['qa_reasons']['outside_period']==1


def test_invalid_rows_fail_with_a_persisted_reason(data_dir):
    path=write_json(data_dir/'fire_archive_M-C61_bad.json',[row(latitude=100)])
    with pytest.raises(ValueError,match='1%'):
        global_ingest.import_global_file(path,progress=lambda _:None)
    report=json.loads(next((data_dir/'processed').glob('*.json')).read_text())
    assert report['qa_reasons']=={'invalid_coordinates':1}
    with store.database() as c:
        assert c.execute('SELECT count(*) FROM observations').fetchone()[0]==0
