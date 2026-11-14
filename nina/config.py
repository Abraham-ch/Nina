import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATA = (ROOT / os.getenv('NINA_DATA_DIR', 'data')).resolve()
# Originales: estáticos del equipo en source/; lo descargado por API o subido, en source/downloads/.
# Subcarpeta aparte para que scripts/import_global.py (que lee source/*.json|csv como ámbito mundial) no lo reimporte.
SOURCE = (ROOT / os.getenv('NINA_SOURCE_DIR', 'source')).resolve()
RAW = SOURCE / 'downloads'
RAW.mkdir(parents=True, exist_ok=True)
for directory in ['processed', 'jobs', 'models', 'exports', 'boundaries', 'catalog', 'tiles']:
    (DATA / directory).mkdir(parents=True, exist_ok=True)
FIRMS = 'https://firms.modaps.eosdis.nasa.gov'
SOURCES = {'modis': 'MODIS', 'viirs-snpp': 'VIIRS S-NPP', 'viirs-jpss1': 'VIIRS NOAA-20', 'viirs-jpss2': 'VIIRS NOAA-21'}
