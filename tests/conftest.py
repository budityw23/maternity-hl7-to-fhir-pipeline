import sys
from pathlib import Path

FASTAPI_ROOT = Path(__file__).resolve().parents[1] / "fastapi"
sys.path.insert(0, str(FASTAPI_ROOT))
