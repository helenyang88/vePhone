from mua_platform.api import novnc


def test_novnc_proxy_view_sets_same_origin_session_cookie(authenticated_client, monkeypatch):
    sid = authenticated_client.app.state.novnc_proxy_store.create(
        base_url="http://agent.example.com:8910",
        viewer_url="http://agent.example.com:8910/novnc/view?sid=upstream",
        websocket_url="ws://agent.example.com:8910/novnc/ws?sid=upstream",
        expires_at=None,
    )

    async def fake_proxy_http_request(session, **_kwargs):
        session.cookie_header = "cua_novnc_session_http=upstream-cookie"
        return 200, [("Content-Type", "text/html")], b"<html>ok</html>"

    monkeypatch.setattr(novnc, "proxy_http_request", fake_proxy_http_request)

    response = authenticated_client.get(f"/novnc/view?sid={sid}")

    assert response.status_code == 200
    assert response.text == "<html>ok</html>"
    assert "cua_novnc_proxy_session=" in response.headers["set-cookie"]
    assert "Path=/novnc" in response.headers["set-cookie"]


def test_novnc_proxy_rejects_missing_session(authenticated_client):
    response = authenticated_client.post(
        "/novnc/resize",
        json={"width": 1280, "height": 720, "dpr": 1},
    )

    assert response.status_code == 401
    assert response.json() == {"success": False, "stderr": "invalid session"}
