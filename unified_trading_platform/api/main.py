"""
Unified Trading Platform API
A comprehensive API for algorithmic trading across multiple brokers.
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from unified_trading_platform.api.endpoints.health import router as health_router
from unified_trading_platform.api.endpoints.brokers import router as brokers_router
from unified_trading_platform.api.endpoints.data import router as data_router
from unified_trading_platform.api.endpoints.orders import router as orders_router
from unified_trading_platform.api.endpoints.strategies import (
    router as strategies_router,
)
from unified_trading_platform.trading_core.config.config import settings

# API metadata comes from config.yaml's `api` section
api_title = settings.get("api.title", "Unified Trading Platform API")
api_version = settings.get("api.version", "0.1.0")
api_description = settings.get("api.description", "")
api_terms = settings.get("api.terms_of_service", "")
api_contact = settings.get("api.contact", {})
api_license = settings.get("api.license", {})
openapi_url = settings.get("api.openapi_url", "/api/v1/openapi.json")
docs_url = settings.get("api.docs_url", "/docs")
redoc_url = settings.get("api.redoc_url", "/redoc")
logo_url = settings.get("api.logo_url", "")
tags_metadata = settings.get("api.tags", [])

app = FastAPI(
    title=api_title,
    description=api_description,
    version=api_version,
    terms_of_service=api_terms,
    contact=api_contact,
    license_info=api_license,
    tags_metadata=tags_metadata,
    openapi_url=openapi_url,
    docs_url=docs_url,
    redoc_url=redoc_url,
)

# Include routers with tags
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(brokers_router, prefix="/brokers", tags=["brokers"])
app.include_router(data_router, prefix="/data", tags=["data"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(strategies_router, prefix="/strategies", tags=["strategies"])


def custom_openapi():
    """Custom OpenAPI schema generation"""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Add logo from config
    if logo_url:
        openapi_schema["info"]["x-logo"] = {"url": logo_url}
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
