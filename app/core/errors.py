"""Domain exception hierarchy and global FastAPI exception handlers."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.constants import ErrorCode
from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class AppException(Exception):
    """Base application exception carrying HTTP status and domain error code."""

    def __init__(
        self,
        message: str,
        code: ErrorCode | str = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if isinstance(code, str) else code.value
        self.status_code = status_code
        self.details = details or {}


class FileRequiredException(AppException):
    def __init__(
        self, message: str = "A file must be uploaded", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.FILE_REQUIRED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class EmptyFileException(AppException):
    def __init__(
        self, message: str = "Uploaded file cannot be empty", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EMPTY_FILE,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class UnsupportedFileTypeException(AppException):
    def __init__(
        self,
        message: str = "Unsupported file type. Accepted formats are .zip (Shapefile) and .kml",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.UNSUPPORTED_FILE_TYPE,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            details=details,
        )


class ContentTypeMismatchException(AppException):
    def __init__(
        self,
        message: str = "File extension does not match content byte signature",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.CONTENT_TYPE_MISMATCH,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            details=details,
        )


class FileTooLargeException(AppException):
    def __init__(
        self,
        message: str = "Uploaded file exceeds maximum permitted size",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.FILE_TOO_LARGE,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details=details,
        )


class InvalidArchiveException(AppException):
    def __init__(
        self,
        message: str = "Corrupted or password-protected archive",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.INVALID_ARCHIVE,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class UnsafeArchiveException(AppException):
    def __init__(
        self,
        message: str = "Archive contains unsafe entries (potential zip-slip or zip-bomb)",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.UNSAFE_ARCHIVE,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class ShapefileNotFoundException(AppException):
    def __init__(
        self,
        message: str = "No .shp file found inside archive",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.SHAPEFILE_NOT_FOUND,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class ShapefileMissingComponentsException(AppException):
    def __init__(
        self,
        message: str = "Shapefile is missing required companion components (.shx, .dbf)",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.SHAPEFILE_MISSING_COMPONENTS,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class InvalidKmlException(AppException):
    def __init__(
        self,
        message: str = "Malformed KML document or disallowed XML entities",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.INVALID_KML,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class NoFeaturesException(AppException):
    def __init__(
        self,
        message: str = "The uploaded geospatial file contains zero features",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.NO_FEATURES,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class CrsUndefinedException(AppException):
    def __init__(
        self,
        message: str = "CRS is undefined and coordinates exceed geographic bounds [-180, 180], [-90, 90]",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.CRS_UNDEFINED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class FileNotFoundException(AppException):
    def __init__(
        self,
        file_id: str,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message=message or f"Uploaded file with id '{file_id}' not found",
            code=ErrorCode.FILE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details={"file_id": file_id},
        )


class FileNotReadyException(AppException):
    def __init__(
        self,
        file_id: str,
        current_status: str,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message=message
            or f"File '{file_id}' is currently {current_status}. Measurements are not ready yet",
            code=ErrorCode.FILE_NOT_READY,
            status_code=status.HTTP_409_CONFLICT,
            details={"file_id": file_id, "status": current_status},
        )


class ProcessingFailedException(AppException):
    def __init__(
        self,
        file_id: str,
        reason: str | None = None,
    ) -> None:
        super().__init__(
            message=f"File processing failed: {reason or 'Unknown error'}",
            code=ErrorCode.PROCESSING_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"file_id": file_id, "error": reason},
        )


class InternalException(AppException):
    def __init__(
        self,
        message: str = "An internal processing error occurred",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Format standard API error envelope JSON response."""
    req_id = request_id or request_id_ctx.get()
    envelope = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": req_id,
        }
    }
    return JSONResponse(status_code=status_code, content=envelope)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach standard error handlers to the FastAPI app instance."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        logger.warning("Application domain error: [%s] %s", exc.code, exc.message)
        return build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("Request validation failed: %s", exc.errors())
        # Clean errors for json serialization
        clean_errors = []
        for err in exc.errors():
            clean_errors.append(
                {
                    "loc": [str(loc_item) for loc_item in err.get("loc", [])],
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=ErrorCode.VALIDATION_ERROR.value,
            message="Request parameters or body failed schema validation",
            details={"errors": clean_errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            404: ErrorCode.FILE_NOT_FOUND.value,
            413: ErrorCode.FILE_TOO_LARGE.value,
            415: ErrorCode.UNSUPPORTED_FILE_TYPE.value,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR.value)
        return build_error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            details={},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        req_id = request_id_ctx.get()
        logger.exception("Unhandled server exception occurred: %s (request_id=%s)", exc, req_id)
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR.value,
            message="An unexpected internal server error occurred",
            details={},
            request_id=req_id,
        )
