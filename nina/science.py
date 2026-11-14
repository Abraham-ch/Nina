"""Exploratory count calibration, deliberately kept apart from validated harmonization.

It trains on matched archive months, NOT on valid satellite opportunities. It is
useful as a reproducible baseline but cannot infer coverage or true fire counts.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
import numpy as np
from scipy.optimize import minimize
from .store import database, rows, now
from .config import DATA

def train():
    with database() as c:
        monthly=rows(c,"""SELECT department,year(acquired) AS year,month(acquired) AS month,source,platform,count(*) AS n
            FROM observations WHERE department IS NOT NULL AND processing='SP' AND year(acquired) BETWEEN 2018 AND 2025
            GROUP BY department,year(acquired),month(acquired),source,platform""")
    groups={}
    for r in monthly:
        k=(r['department'],r['year'],r['month'])
        g=groups.setdefault(k,{})
        if r['source']=='modis' and r['platform']=='Aqua': g['target']=r['n']
        elif r['source']!='modis': g[r['source']]=r['n']
    models={}
    for source in ['viirs-snpp','viirs-jpss1','viirs-jpss2']:
        samples=[(k,v[source],v.get('target',0)) for k,v in groups.items() if source in v and k[1]>=2018]
        if len(samples)<100: continue
        def held(region): return int(hashlib.sha256(region.encode()).hexdigest()[:8],16)%5==0
        training=[s for s in samples if s[0][1]<=2022 and not held(s[0][0])]
        validation=[s for s in samples if s[0][1]==2023 and not held(s[0][0])]
        test=[s for s in samples if s[0][1]>=2024]
        if min(len(training),len(validation),len(test))<20: continue
        def matrix(samples): return np.array([[1,math.log1p(x),math.sin(2*math.pi*k[2]/12),math.cos(2*math.pi*k[2]/12)] for k,x,y in samples]),np.array([y for k,x,y in samples],float)
        X,y=matrix(training);V,vy=matrix(validation);T,ty=matrix(test)
        ratio=sum(y)/sum(s[1] for s in training)
        candidates=[]
        for penalty in [.001,.1,1.0]:
            def objective(beta):
                eta=np.clip(X@beta,-20,20);mu=np.exp(eta)
                return float(np.mean(mu-y*eta)+penalty*np.sum(beta[1:]**2)), X.T@(mu-y)/len(y)+np.r_[0,2*penalty*beta[1:]]
            fit=minimize(objective,np.array([math.log(max(ratio,1e-5)),1,0,0]),jac=True,method='L-BFGS-B')
            pred=np.exp(np.clip(V@fit.x,-20,20));candidates.append((np.mean(abs(pred-vy)),fit.x,penalty))
        _,beta,penalty=min(candidates,key=lambda x:x[0]);pred=np.exp(np.clip(T@beta,-20,20));base=np.array([s[1]*ratio for s in test])
        heldmask=np.array([held(s[0][0]) for s in test])
        def metrics(p,t): return {'mae':round(float(np.mean(abs(p-t))),3),'bias':round(float(np.mean(p-t)),3),'n':len(t)}
        models[source]={'version':'exploratory-count-v1','source':source,'reference':'MODIS Aqua SP',
            'coefficients':beta.tolist(),'scale_ratio':ratio,'penalty':penalty,'training_n':len(training),'validation_n':len(validation),
            'test':metrics(pred,ty),'baseline_test':metrics(base,ty),'geographic_holdout_test':metrics(pred[heldmask],ty[heldmask]) if heldmask.any() else None,
            'training_years':'2018–2022 excluding reserved regions','validation_years':'2023','test_years':'2024–2025',
            'status':'experimental_without_observation_opportunities','interval':None,
            'limitations':['Only archive-positive months are available for matching; no claim of valid no-fire opportunities.',
                'Clouds, overpass opportunities and observation geometry are not controlled.',
                'Not approved for operational fire-response decisions or unbiased trend inference.']}
    result={'created_at':now(),'models':models,'scientific_harmonization_status':'pending_L2_opportunities','synthetic':False}
    with database() as c: revision=c.execute("SELECT md5(string_agg(id,',' ORDER BY id)) FROM batches").fetchone()[0]
    for model in models.values():
        model['training_data_revision']=revision
        model['model_id']=hashlib.sha256(json.dumps({'data':revision,'coefficients':model['coefficients'],'method':model['version']},sort_keys=True).encode()).hexdigest()[:24]
    (DATA/'models'/'benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__': print(json.dumps(train(),indent=2))


def substitution_experiment(source='viirs-snpp',department=None):
    """Reveal held-out archive counts; this is not an opportunity-corrected test."""
    from .store import boundaries
    path=DATA/'models'/'benchmark.json'
    models=json.loads(path.read_text()).get('models',{}) if path.exists() else {}
    model=models.get(source)
    regions=boundaries()['features']
    if not model: return {'available':False,'reason':'No hay un modelo exploratorio entrenado para este instrumento','samples':[]}
    if department is None:
        department=next((f['properties']['id'] for f in regions if 'Madre' in f['properties']['name']),regions[0]['properties']['id'] if regions else '')
    region=next((f for f in regions if f['properties']['id']==department),None)
    if not region: return {'available':False,'reason':'Selecciona una región del caso de validación Perú','samples':[]}
    with database() as c:
        records=rows(c,"""SELECT year(acquired) AS year,month(acquired) AS month,source,platform,count(*) AS count
            FROM observations WHERE department=? AND processing='SP' AND year(acquired) BETWEEN 2024 AND 2025
            AND ((source='modis' AND platform='Aqua') OR source=?) GROUP BY year,month,source,platform""",[department,source])
    pairs={}
    for record in records:
        key=(record['year'],record['month']);pair=pairs.setdefault(key,{})
        pair['reference' if record['source']=='modis' else 'input']=record['count']
    samples=[]
    for (year,month),pair in sorted(pairs.items()):
        if 'input' not in pair or 'reference' not in pair: continue
        raw=pair['input'];x=[1,math.log1p(raw),math.sin(2*math.pi*month/12),math.cos(2*math.pi*month/12)]
        predicted=math.exp(max(-20,min(20,sum(a*b for a,b in zip(x,model['coefficients'])))))
        samples.append({'year':year,'month':month,'input':raw,'reference':pair['reference'],'estimate':round(predicted,2),
                        'baseline':round(raw*model['scale_ratio'],2),'absolute_error':round(abs(predicted-pair['reference']),2)})
    return {'available':bool(samples),'source':source,'department':department,'area_name':region['properties']['name'],
            'model_id':model.get('model_id'),'training_years':model['training_years'],'test_years':'2024–2025',
            'training_data_revision':model.get('training_data_revision'),
            'region_reserved':int(hashlib.sha256(department.encode()).hexdigest()[:8],16)%5==0,
            'samples':samples,'synthetic':False,'status':'exploratory_archive_count_test',
            'limitations':model['limitations'],
            'mae':round(sum(s['absolute_error'] for s in samples)/len(samples),3) if samples else None}
