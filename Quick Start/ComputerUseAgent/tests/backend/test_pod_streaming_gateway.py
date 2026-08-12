from mua_platform.pods.streaming import _session_result


def test_stream_session_accepts_top_level_novnc_response():
    response = {
        "ViewerUrl": "https://agent.example.com/novnc/view",
        "WebsocketUrl": "wss://agent.example.com/novnc/ws",
        "HttpViewerUrl": "http://agent.example.com/novnc/view",
        "WsWebsocketUrl": "ws://agent.example.com/novnc/ws",
        "ExpiresAt": 1786537700,
    }

    assert _session_result(response) == response


def test_stream_session_accepts_result_wrapped_novnc_response():
    result = {
        "ViewerUrl": "https://agent.example.com/novnc/view",
        "ExpiresAt": 1786537700,
    }

    assert _session_result({"Result": result}) == result
