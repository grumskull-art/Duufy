import re

from fastapi.responses import JSONResponse


def _to_screaming_snake(code: str) -> str:
    if not code:
        return "ERROR"
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", code)
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_")
    return normalized.upper() if normalized else "ERROR"


def api_error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": _to_screaming_snake(code), "message": message}},
    )


def item_not_found(message: str = "Item not found") -> JSONResponse:
    return api_error("ITEM_NOT_FOUND", message, 404)


def invalid_request(message: str = "Invalid request") -> JSONResponse:
    return api_error("INVALID_REQUEST", message, 400)


def conflict(message: str = "Conflict") -> JSONResponse:
    return api_error("CONFLICT", message, 409)


def internal_error(message: str = "Internal Server Error") -> JSONResponse:
    return api_error("INTERNAL_ERROR", message, 500)
