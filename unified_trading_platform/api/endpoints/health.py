"""
Health check endpoints.
Monitors API availability and status.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class HealthStatus(BaseModel):
    """Health status response"""

    status: str = Field(..., description="Health status", examples=["ok"])


@router.get(
    "/ready",
    response_model=HealthStatus,
    summary="Readiness check",
    description="Check if the API is ready to accept requests",
    response_description="API readiness status",
    tags=["health"],
)
def ready():
    """
    Check API readiness.

    Returns:
        HealthStatus: Status indicating API is ready
    """
    return HealthStatus(status="ok")


@router.get(
    "/live",
    response_model=HealthStatus,
    summary="Liveness check",
    description="Check if the API is alive and running",
    response_description="API liveness status",
    tags=["health"],
)
def live():
    """
    Check API liveness.

    Returns:
        HealthStatus: Status indicating API is alive
    """
    return HealthStatus(status="ok")
