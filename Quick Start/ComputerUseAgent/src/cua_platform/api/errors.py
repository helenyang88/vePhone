from uuid import uuid4

from fastapi import HTTPException


def error_detail(
    code: str,
    message: str,
    details: dict | None = None,
) -> dict:
    return {
        "code": code,
        "message": message,
        "request_id": f"req_{uuid4().hex}",
        "details": details or {},
    }


def api_error(
    status: int,
    code: str,
    message: str,
    details: dict | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=error_detail(code, message, details),
        headers=headers,
    )
