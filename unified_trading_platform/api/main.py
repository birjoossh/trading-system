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
from unified_trading_platform.api.config import load_config, get_config_value

# Load configuration from YAML file
config = load_config()

# Get API metadata from config
api_title = get_config_value("api.title", "Unified Trading Platform API")
api_version = get_config_value("api.version", "0.1.0")
api_description = get_config_value("api.description", "")
api_terms = get_config_value("api.terms_of_service", "")
api_contact = get_config_value("api.contact", {})
api_license = get_config_value("api.license", {})
openapi_url = get_config_value("api.openapi_url", "/api/v1/openapi.json")
docs_url = get_config_value("api.docs_url", "/docs")
redoc_url = get_config_value("api.redoc_url", "/redoc")
logo_url = get_config_value("api.logo_url", "")

# Get tags metadata from config
tags_metadata = get_config_value("tags", [])

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
