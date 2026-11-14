"""Acquire a bounded, verified global FIRMS snapshot (three products, one day)."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from nina.remote import availability, acquire

if __name__=='__main__':
    try:
        catalog=availability(refresh=True)
        print(json.dumps(catalog,ensure_ascii=False),flush=True)
        result=acquire(['MODIS_NRT','VIIRS_NOAA20_NRT','VIIRS_NOAA21_NRT'])
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    except Exception as error:
        # Never print exceptions containing authenticated provider URLs.
        import httpx
        print('FIRMS: error de acceso o servicio' if isinstance(error,httpx.HTTPError) else str(error),file=sys.stderr)
        sys.exit(1)
