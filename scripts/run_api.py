from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


if __name__ == "__main__":
    # Prefer API_MODULE=api.main:app for Streamlit /ask; use api.app:app for Cognito /api.
    uvicorn.run(
        os.getenv("API_MODULE", "api.main:app"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "0").lower() in {"1", "true", "yes"},
    )
