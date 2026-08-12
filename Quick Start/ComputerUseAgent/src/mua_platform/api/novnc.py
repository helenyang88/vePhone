from urllib.parse import urlparse

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import Response

from mua_platform.novnc_proxy import NoVncProxyStore, proxy_http_request, relay_websocket

router = APIRouter(prefix="/novnc")
_COOKIE_NAME = "cua_novnc_proxy_session"
_HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "set-cookie",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def create_proxy_session(
    store: NoVncProxyStore,
    *,
    viewer_url: object,
    websocket_url: object,
    expires_at: object,
) -> str | None:
    if not isinstance(viewer_url, str) or not viewer_url:
        return None
    parsed = urlparse(viewer_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if websocket_url is not None and not isinstance(websocket_url, str):
        websocket_url = None
    return store.create(
        base_url=f"{parsed.scheme}://{parsed.netloc}",
        viewer_url=viewer_url,
        websocket_url=websocket_url,
        expires_at=expires_at if isinstance(expires_at, int) else None,
    )


@router.get("/view")
async def view(request: Request, sid: str) -> Response:
    store: NoVncProxyStore = request.app.state.novnc_proxy_store
    session = store.get(sid)
    if session is None:
        return Response(
            b'{"success": false, "stderr": "invalid session"}',
            status_code=401,
            media_type="application/json",
        )
    status, headers, content = await proxy_http_request(
        session,
        method="GET",
        path="view",
        query=urlparse(session.viewer_url).query,
        body=b"",
        content_type=None,
    )
    response = _proxy_response(status, headers, content)
    response.set_cookie(
        _COOKIE_NAME,
        sid,
        httponly=True,
        max_age=max(60, (session.expires_at or 0) - int(__import__("time").time())) if session.expires_at else None,
        path="/novnc",
        samesite="lax",
    )
    return response


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_path(path: str, request: Request) -> Response:
    store: NoVncProxyStore = request.app.state.novnc_proxy_store
    session = store.get(request.cookies.get(_COOKIE_NAME))
    if session is None:
        return Response(
            b'{"success": false, "stderr": "invalid session"}',
            status_code=401,
            media_type="application/json",
        )
    status, headers, content = await proxy_http_request(
        session,
        method=request.method,
        path=path,
        query=request.url.query,
        body=await request.body(),
        content_type=request.headers.get("content-type"),
    )
    return _proxy_response(status, headers, content)


@router.websocket("/ws")
async def websocket_proxy(websocket: WebSocket) -> None:
    store: NoVncProxyStore = websocket.app.state.novnc_proxy_store
    session = store.get(websocket.cookies.get(_COOKIE_NAME))
    if session is None:
        await websocket.close(code=1008)
        return
    await relay_websocket(websocket, session)


def _proxy_response(status: int, headers: list[tuple[str, str]], content: bytes) -> Response:
    response_headers = {
        name: value
        for name, value in headers
        if name.lower() not in _HOP_BY_HOP_HEADERS
    }
    return Response(content, status_code=status, headers=response_headers)
