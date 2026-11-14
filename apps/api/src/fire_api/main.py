"""Punto de entrada FastAPI."""

from fastapi import APIRouter, FastAPI
from nina.config import HARMONIZATION_VERSION

app = FastAPI(title="Nina API", version=HARMONIZATION_VERSION)
v1 = APIRouter(prefix="/api/v1")


@v1.get("/meta")
def meta() -> dict[str, str]:
    """Versión del dataset armonizado. Cobertura, huecos y cita llegan con la BD."""
    return {"harmonization_version": HARMONIZATION_VERSION}


app.include_router(v1)
