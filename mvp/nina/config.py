import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATA = (ROOT / os.getenv('NINA_DATA_DIR', 'data')).resolve()
for directory in ['raw', 'processed', 'jobs', 'models', 'exports', 'boundaries', 'catalog', 'tiles']:
    (DATA / directory).mkdir(parents=True, exist_ok=True)
FIRMS = 'https://firms.modaps.eosdis.nasa.gov'
SOURCES = {'modis': 'MODIS', 'viirs-snpp': 'VIIRS S-NPP', 'viirs-jpss1': 'VIIRS NOAA-20', 'viirs-jpss2': 'VIIRS NOAA-21'}
