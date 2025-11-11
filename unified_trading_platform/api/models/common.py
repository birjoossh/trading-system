"""
Common models for API responses.
Provides standard error and success response formats.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ErrorResponse(BaseModel):
    """Standard error response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Broker not found",
                "detail": "The requested broker 'interactive_brokers' does not exist",
                "timestamp": "2024-01-01T12:00:00",
            }
        }
    )

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Timestamp of the error"
    )


class SuccessResponse(BaseModel):
    """Standard success response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "timestamp": "2024-01-01T12:00:00",
            }
        }
    )

    success: bool = Field(True, description="Whether the operation was successful")
    message: Optional[str] = Field(
        None, description="Optional message describing the result"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Timestamp of the response"
    )
