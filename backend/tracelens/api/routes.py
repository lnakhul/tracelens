"""Management API routes available under /api."""

from fastapi import APIRouter

from tracelens.api.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["management"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Confirm that the local TraceLens management API is available."""

    return HealthResponse(status="ok")
