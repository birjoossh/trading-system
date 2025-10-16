from fastapi import APIRouter
from pydantic import BaseModel
from unified_trading_platform.runtime import get_trading_system

router = APIRouter()

class AddBrokerRequest(BaseModel):
    name: str
    broker_type: str
    host: str = "127.0.0.1"
    port: int = 7498
    client_id: int = 1

@router.get("")
def list_brokers():
    ts = get_trading_system()
    return {"brokers": list(ts.brokers.keys())}

@router.post("")
def add_broker(req: AddBrokerRequest):
    ts = get_trading_system()
    ok = ts.add_broker(
        name=req.name,
        broker_type=req.broker_type,
        host=req.host,
        port=req.port,
        client_id=req.client_id,
    )
    return {"success": ok}



