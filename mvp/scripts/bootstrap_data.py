"""Download NASA's published Peru annual CSVs and versioned geoBoundaries geometry.

No credentials, simulation or unverified URL patterns. File names come from NASA's
own index used by its country-download web app. Downloads are resumable per file.
"""
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    import truststore
    TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    TLS = ssl.create_default_context()
DATA = ROOT / 'data'
BASE = 'https://firms.modaps.eosdis.nasa.gov'

def get(url, target=None):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'NINA-Peru/0.1 research prototype'})
            with urllib.request.urlopen(req, timeout=90, context=TLS) as response:
                if target:
                    part = target.with_suffix(target.suffix + '.part')
                    with part.open('wb') as out:
                        while block := response.read(1024 * 1024): out.write(block)
                    part.replace(target)
                    return target.read_bytes()
                return response.read()
        except Exception:
            if attempt == 2: raise
            time.sleep(attempt + 1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-only', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    for name in ['raw', 'boundaries', 'processed']: (DATA / name).mkdir(parents=True, exist_ok=True)
    index_url = BASE + '/data/country/yearly_summary_files.txt'
    raw_index = get(index_url)
    (DATA / 'raw' / 'yearly_summary_files.txt').write_bytes(raw_index)
    entries = []
    for row in csv.DictReader(io.StringIO(raw_index.decode('utf-8-sig'))):
        name = row['filename']
        match = re.fullmatch(r'(modis|viirs-snpp|viirs-jpss1|viirs-jpss2|viirs-noaa20|viirs-noaa21)_(\d{4})_Peru\.csv', name)
        if not match: continue
        source, year = match.groups()
        entries.append({'filename': name, 'source': source, 'year': int(year), 'expected_bytes': int(row['size']),
                        'published_updated': row['updated'], 'url': f'{BASE}/data/country/{source}/{year}/{name}'})
    if not entries: raise RuntimeError('NASA index contains no Peru files; no guessed downloads will be attempted.')
    manifest = {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'index_url': index_url, 'synthetic': False,
                'total_expected_bytes': sum(x['expected_bytes'] for x in entries), 'files': entries}
    def save(): (DATA / 'inventory.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save()
    print(f"Inventory: {len(entries)} files, {manifest['total_expected_bytes']/1e6:.2f} MB", flush=True)
    if args.inventory_only: return
    def download(entry):
        path = DATA / 'raw' / entry['filename']
        payload = path.read_bytes() if path.exists() and path.stat().st_size == entry['expected_bytes'] else get(entry['url'], path)
        if len(payload) != entry['expected_bytes']: raise RuntimeError(f"Size mismatch: {entry['filename']}")
        if b'latitude' not in payload[:200].lower() or b'longitude' not in payload[:200].lower():
            raise RuntimeError('Not a FIRMS CSV: ' + entry['filename'])
        entry.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), status='downloaded')
        print('Downloaded ' + entry['filename'], flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(4,args.workers))) as pool:
        futures = {pool.submit(download, e): e for e in entries}
        for future in concurrent.futures.as_completed(futures):
            try: future.result()
            except Exception as error:
                futures[future].update(status='failed', error=str(error))
                print('FAILED ' + futures[future]['filename'] + ': ' + str(error), flush=True)
            save()
    metadata_url = 'https://www.geoboundaries.org/api/current/gbOpen/PER/ADM1/'
    metadata = json.loads(get(metadata_url))
    geometry = get(metadata['gjDownloadURL'])
    (DATA / 'boundaries' / 'departments.geojson').write_bytes(geometry)
    metadata.update(retrieved_at=manifest['retrieved_at'], metadata_url=metadata_url, sha256=hashlib.sha256(geometry).hexdigest())
    (DATA / 'boundaries' / 'provenance.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('Boundaries downloaded: ' + str(metadata['admUnitCount']), flush=True)
    if any(e.get('status') != 'downloaded' for e in entries): raise SystemExit('Some downloads failed. Re-run to resume.')

if __name__ == '__main__': main()
