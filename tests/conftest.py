import pathlib
import sys

# repo root on sys.path so `ingest` imports without packaging
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
