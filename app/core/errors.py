from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorDetail, ErrorResponse

HTTP_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 422: "validation_error",
    500: "internal_error", 501: "not_implemented",
}


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(request: Request, status_code: int, code: str, message: str, headers=None):
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message), trace_id=request.state.trace_id
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def application_error(request: Request, exc: APIError):
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed"
        return error_response(
            request, exc.status_code, HTTP_CODES.get(exc.status_code, "http_error"), message, exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never echo raw inputs: a failed request may contain passwords or tokens.
        return error_response(request, 422, "validation_error", "Request validation failed")
