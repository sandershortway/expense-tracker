from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class AppError(Exception):
    """A business error with a machine-readable code and a message."""

    status_code = 400

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Response body for every application error."""

    error: ErrorDetail


async def _handle_app_error(
    request: Request, error: Exception
) -> JSONResponse:
    assert isinstance(error, AppError)
    body = ErrorResponse(
        error=ErrorDetail(code=error.code, message=error.message)
    )
    return JSONResponse(
        status_code=error.status_code, content=body.model_dump()
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
