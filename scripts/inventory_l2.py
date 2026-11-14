"""Inventory NASA CMR public metadata for L2 fire and geolocation over Peru.

Does not download protected science files. Granule samples are bounded; sizes of
samples are not presented as the total. Search-after enables resumable enumeration.
"""
import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from bootstrap_data import get,DATA

PRODUCTS={'MOD14':'061','MYD14':'061','VNP14IMG':'002','VJ114IMG':'002','VJ214IMG':'002',
          'VNP03MODLL':'002','VJ103MODLL':'002','VJ203MODLL':'002'}

def inventory(start,end,page_size=5):
    results=[]
    for short_name,version in PRODUCTS.items():
        params=urllib.parse.urlencode({'short_name':short_name,'version':version,'page_size':10})
        try:
            collections=json.loads(get('https://cmr.earthdata.nasa.gov/search/collections.json?'+params))['feed']['entry']
            for col in collections:
                if col.get('data_center') not in ['LPCLOUD','LAADS']: continue
                query=urllib.parse.urlencode({'collection_concept_id':col['id'],'bounding_box':'-81.5,-18.5,-68.5,0.1',
                    'temporal':start+'T00:00:00Z,'+end+'T23:59:59Z','page_size':page_size,'sort_key':'start_date'})
                url='https://cmr.earthdata.nasa.gov/search/granules.json?'+query
                feed=json.loads(get(url))['feed']
                entries=feed.get('entry',[])
                granules=[{'id':g['id'],'title':g['title'],'time_start':g.get('time_start'),
                    'granule_size_mb':g.get('granule_size'),'links':[l['href'] for l in g.get('links',[]) if l.get('rel','').endswith('/data#')]} for g in entries]
                results.append({'short_name':short_name,'version':version,'collection_id':col['id'],'query':url,'sample':granules,
                    'total_bytes':None,'complete_inventory':False})
                print(short_name+': '+str(len(granules))+' granules sampled',flush=True);break
            else: results.append({'short_name':short_name,'status':'collection_not_found'})
        except Exception as e:
            results.append({'short_name':short_name,'status':'failed','error':str(e)[:200]})
    output={'scope':'PER','bbox':[-81.5,-18.5,-68.5,.1],'period':[start,end],'complete_inventory':False,'products':results}
    (DATA/'l2-inventory.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--start',default='2024-09-01');parser.add_argument('--end',default='2024-09-30')
    args=parser.parse_args();inventory(args.start,args.end)
