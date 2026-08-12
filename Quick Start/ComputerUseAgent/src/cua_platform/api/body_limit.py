from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse

from cua_platform.api.errors import error_detail

ASGIApp = Callable[[dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]], Awaitable[None]]


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(scope, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, _replay(message), send)
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(scope, send)
                return
            if not message.get("more_body", False):
                break

        await self.app(scope, _replay_body(bytes(body)), send)

    @staticmethod
    async def _reject(scope: dict, send) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": error_detail(
                    "request_too_large",
                    "Request body is too large",
                )
            },
        )
        await response(scope, _empty_receive, send)


def _content_length(scope: dict) -> int | None:
    for name, value in scope.get("headers", ()):
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _replay_body(body: bytes):
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _replay(message: dict):
    async def receive() -> dict:
        return message

    return receive


async def _empty_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}
