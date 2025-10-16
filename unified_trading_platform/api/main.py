from fastapi import FastAPI
from unified_trading_platform.api.endpoints.health import router as health_router
from unified_trading_platform.api.endpoints.brokers import router as brokers_router
from unified_trading_platform.api.endpoints.data import router as data_router
from unified_trading_platform.api.endpoints.orders import router as orders_router

app = FastAPI(title="Unified Trading Platform API", version="0.1.0")

app.include_router(health_router, prefix="/health", tags=["health"]) 
app.include_router(brokers_router, prefix="/brokers", tags=["brokers"]) 
app.include_router(data_router, prefix="/data", tags=["data"]) 
app.include_router(orders_router, prefix="/orders", tags=["orders"]) 




