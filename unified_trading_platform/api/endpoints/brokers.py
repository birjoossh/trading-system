"""
Broker management endpoints.
Handles broker connections, disconnections, and account information.
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from unified_trading_platform.runtime import get_trading_system
from ..models import (
    AddBrokerRequest,
    BrokerInfo,
    AccountInfo,
    SuccessResponse,
    ErrorResponse,
)
from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=List[BrokerInfo],
    summary="List all brokers",
    description="Get a list of all registered brokers and their connection status",
    response_description="List of broker information",
    responses={
        200: {
            "description": "Successfully retrieved broker list",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "name": "ib_paper",
                            "broker_type": "IBBroker",
                            "is_connected": True,
                            "host": "127.0.0.1",
                            "port": 7497,
                            "client_id": 1,
                        }
                    ]
                }
            },
        }
    },
)
def list_brokers():
    """
    Get list of all registered brokers.

    Returns:
        List[BrokerInfo]: List of all registered brokers with their connection status
    """
    ts = get_trading_system()
    brokers = []
    for name, broker in ts.brokers.items():
        brokers.append(
            BrokerInfo(
                name=name,
                broker_type=type(broker).__name__,
                is_connected=broker.is_connected,
                host=getattr(broker, "host", None),
                port=getattr(broker, "port", None),
                client_id=getattr(broker, "client_id", None),
            )
        )
    return brokers


@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a broker",
    description="Add and connect a new broker to the trading system",
    responses={
        201: {"description": "Broker added and connected successfully"},
        400: {"description": "Failed to add broker", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
def add_broker(req: AddBrokerRequest):
    """
    Add and connect a new broker.

    Args:
        req: Broker connection request with name, type, host, port, and client_id

    Returns:
        SuccessResponse: Success message if broker was added successfully

    Raises:
        HTTPException: 400 if broker connection failed, 500 for server errors
    """
    ts = get_trading_system()
    try:
        success = ts.add_broker(
            name=req.name,
            broker_type=req.broker_type,
            host=req.host,
            port=req.port,
            client_id=req.client_id,
            **(req.config or {}),
        )
        if success:
            return SuccessResponse(message=f"Broker '{req.name}' added and connected successfully")
        else:
            raise HTTPException(status_code=400, detail=f"Failed to add broker '{req.name}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{broker_name}",
    response_model=SuccessResponse,
    summary="Remove a broker",
    description="Remove and disconnect a broker from the trading system",
    responses={
        200: {"description": "Broker removed successfully"},
        400: {"description": "Failed to disconnect broker", "model": ErrorResponse},
        404: {"description": "Broker not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
def remove_broker(broker_name: str):
    """
    Remove and disconnect a broker.

    Args:
        broker_name: Name of the broker to remove

    Returns:
        SuccessResponse: Success message if broker was removed

    Raises:
        HTTPException: 400 if disconnection fails, 404 if broker not found, 500 for server errors
    """
    ts = get_trading_system()

    # Check if broker exists
    if broker_name not in ts.brokers:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Broker '{broker_name}' not found")

    try:
        # Get the broker instance
        broker = ts.brokers[broker_name]

        # Disconnect the broker if it's connected
        if hasattr(broker, "is_connected") and broker.is_connected:
            try:
                broker.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting broker {broker_name}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to disconnect broker: {str(e)}"
                )

        # Remove the broker from the trading system
        removed = ts.remove_broker(broker_name)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to remove broker {broker_name}"
            )

        logger.info(f"Successfully removed broker: {broker_name}")
        return SuccessResponse(success=True, message=f"Successfully removed broker: {broker_name}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error removing broker {broker_name}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/{broker_name}",
    response_model=BrokerInfo,
    summary="Get broker information",
    description="Get detailed information about a specific broker",
    responses={
        200: {"description": "Broker information retrieved successfully"},
        404: {"description": "Broker not found", "model": ErrorResponse},
    },
)
def get_broker_info(broker_name: str):
    """
    Get information about a specific broker.

    Args:
        broker_name: Name of the broker

    Returns:
        BrokerInfo: Detailed broker information

    Raises:
        HTTPException: 404 if broker not found
    """
    ts = get_trading_system()
    if broker_name not in ts.brokers:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_name}' not found")

    broker = ts.brokers[broker_name]
    return BrokerInfo(
        name=broker_name,
        broker_type=type(broker).__name__,  # fixme: fix this
        is_connected=broker.is_connected,
        host=getattr(broker, "host", None),
        port=getattr(broker, "port", None),
        client_id=getattr(broker, "client_id", None),
    )


@router.get(
    "/{broker_name}/account",
    response_model=AccountInfo,
    summary="Get account information",
    description="Get account information including balances, equity, and buying power for a broker",
    responses={
        200: {"description": "Account information retrieved successfully"},
        404: {"description": "Broker not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
def get_account_info(broker_name: str):
    """
    Get account information for a broker.

    Args:
        broker_name: Name of the broker

    Returns:
        AccountInfo: Account information including balances and equity

    Raises:
        HTTPException: 404 if broker not found, 500 for server errors
    """
    ts = get_trading_system()
    if broker_name not in ts.brokers:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_name}' not found")

    try:
        account_data = ts.get_account_info(broker_name)
        return AccountInfo(broker_name=broker_name, **account_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
