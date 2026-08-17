"""Pydantic schemas for TraceLens management endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned when the local management API is ready."""

    status: str
