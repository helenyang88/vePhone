import base64
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from chat_action_demo import (
    AdbDevice,
    ChatActionClient,
    DemoError,
    ImageInfo,
    OpenAPIError,
    SuggestedAction,
    VolcengineSigner,
    canonical_query,
    inspect_image,
    parse_action_response,
)


PNG_2X3 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x02\x00\x00\x00\x03"
    b"\x08\x06\x00\x00\x00"
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload


class ChatActionDemoTests(unittest.TestCase):
    def test_canonical_query_is_sorted_and_encoded(self):
        self.assertEqual(
            canonical_query({"Version": "2023-08-01", "Action": "Chat Action"}),
            "Action=Chat%20Action&Version=2023-08-01",
        )

    def test_signer_headers_do_not_expose_secret(self):
        signer = VolcengineSigner("test-ak", "do-not-leak")
        url, headers = signer.sign(
            "POST",
            {"Action": "ChatAction", "Version": "2023-08-01"},
            b"{}",
            now=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(
            url,
            "https://open.volcengineapi.com/?Action=ChatAction&Version=2023-08-01",
        )
        self.assertEqual(headers["X-Date"], "20260630T000000Z")
        self.assertIn(
            "Credential=test-ak/20260630/cn-north-1/ipaas/request",
            headers["Authorization"],
        )
        self.assertNotIn("do-not-leak", json.dumps(headers))

    def test_inspect_png(self):
        self.assertEqual(inspect_image(PNG_2X3), ImageInfo(2, 3, "image/png"))

    def test_validate_tap_and_reject_out_of_bounds(self):
        valid = {
            "ResponseMetadata": {"RequestId": "req"},
            "Result": {
                "run_id": "123",
                "action": "tap",
                "params": {"x": 1, "y": 2},
            },
        }
        self.assertEqual(
            parse_action_response(valid, ImageInfo(2, 3, "image/png")).action,
            "tap",
        )
        valid["Result"]["params"]["x"] = 2
        with self.assertRaisesRegex(OpenAPIError, "outside"):
            parse_action_response(valid, ImageInfo(2, 3, "image/png"))

    def test_current_nested_result_is_supported(self):
        payload = {
            "ResponseMetadata": {"RequestId": "req-live"},
            "Result": {
                "RunId": "123456789012345678",
                "ThreadId": "223456789012345678",
                "data": {
                    "RunId": "123456789012345678",
                    "action": "tap",
                    "params": {"x": 1, "y": 2},
                },
            },
        }
        result = parse_action_response(payload, ImageInfo(2, 3, "image/png"))
        self.assertEqual(result.run_id, "123456789012345678")
        self.assertEqual(result.thread_id, "223456789012345678")
        self.assertEqual(result.action, "tap")

    def test_openapi_error_is_preserved(self):
        payload = {
            "ResponseMetadata": {
                "RequestId": "req-1",
                "Error": {"Code": "AccessDenied", "Message": "denied"},
            }
        }
        with self.assertRaises(OpenAPIError) as caught:
            parse_action_response(payload, ImageInfo(2, 3, "image/png"))
        self.assertEqual(caught.exception.code, "AccessDenied")
        self.assertEqual(caught.exception.request_id, "req-1")

    def test_client_sends_pure_base64(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["body"] = json.loads(request.data)
            seen["timeout"] = timeout
            return FakeResponse(
                {
                    "ResponseMetadata": {"RequestId": "req-2"},
                    "Result": {
                        "run_id": "123456789012345678",
                        "action": "none",
                        "params": {},
                    },
                }
            )

        client = ChatActionClient("ak", "sk", timeout=7, urlopen=fake_urlopen)
        result, _ = client.suggest("inspect", PNG_2X3, inspect_image(PNG_2X3))
        self.assertEqual(result.action, "none")
        self.assertEqual(seen["timeout"], 7)
        self.assertEqual(
            seen["body"]["ImageBase64"], base64.b64encode(PNG_2X3).decode()
        )
        self.assertFalse(seen["body"]["ImageBase64"].startswith("data:"))

    def test_adb_action_mapping_and_safe_type_guard(self):
        device = AdbDevice("serial")
        with mock.patch.object(device, "_run", return_value=b"") as run:
            device.execute(SuggestedAction("1", "tap", {"x": 10, "y": 20}, "req"))
            run.assert_called_once_with(["shell", "input", "tap", "10", "20"])
        with mock.patch.object(device, "_run", return_value=b"") as run:
            device.execute(
                SuggestedAction(
                    "2",
                    "swipe",
                    {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "durationMs": 500},
                    "req",
                )
            )
            run.assert_called_once_with(
                ["shell", "input", "swipe", "1", "2", "3", "4", "500"]
            )
        with mock.patch.object(device, "_run", return_value=b"") as run:
            device.execute(
                SuggestedAction(
                    "3",
                    "longPress",
                    {"x": 10, "y": 20, "durationMs": 1000},
                    "req",
                )
            )
            run.assert_called_once_with(
                ["shell", "input", "swipe", "10", "20", "10", "20", "1000"]
            )
        with mock.patch.object(device, "_run", return_value=b"") as run:
            device.execute(SuggestedAction("4", "type", {"text": "Hello World"}, "req"))
            run.assert_called_once_with(["shell", "input", "text", "Hello%sWorld"])
        self.assertFalse(device.execute(SuggestedAction("5", "none", {}, "req")))
        with self.assertRaises(DemoError):
            device.execute(
                SuggestedAction("6", "type", {"text": "bad; rm -rf /"}, "req")
            )


if __name__ == "__main__":
    unittest.main()
