"""Importa JSON/CSV mundiales FIRMS en una base local con memoria acotada."""
import argparse
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,default=ROOT/'source')
parser.add_argument('--data-dir',type=Path,help='Base de staging; no ejecutar contra una base con servidor activo')
parser.add_argument('--start-year',type=int,default=2025)
parser.add_argument('--end-year',type=int,default=2026)
args=parser.parse_args()
if args.data_dir: os.environ['NINA_DATA_DIR']=str(args.data_dir.resolve())
os.environ.setdefault('NINA_DUCKDB_MEMORY_LIMIT','1GB')
os.environ.setdefault('NINA_DUCKDB_THREADS','2')
from nina.global_ingest import run
run(args.input,args.start_year,args.end_year)
