"""Schema definitions for standard error envelope responses."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Encapsulated error details."""

    code: str = Field(
        ..., description="Machine-readable domain error code", examples=["UNSUPPORTED_FILE_TYPE"]
    )
    message: str = Field(
        ...,
        description="Human-readable description of the error",
        examples=["Unsupported file type"],
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Contextual parameters or validation fields"
    )
    request_id: str = Field(
        ..., description="Traceability request identifier", examples=["req-7b8d4c9a"]
    )


class ErrorResponse(BaseModel):
    """Standardized top-level API error envelope."""

    error: ErrorDetail
