#!/usr/bin/env python3
"""ChatAction OpenAPI + ADB single-step demo.

Credentials are read only from VOLC_ACCESSKEY and VOLC_SECRETKEY. They are
never accepted as CLI arguments and are never persisted in artifacts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import ssl
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


API_HOST = "open.volcengineapi.com"
API_ACTION = "ChatAction"
API_VERSION = "2023-08-01"
API_SERVICE = "ipaas"
API_REGION = "cn-north-1"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_ACTIONS = {"tap", "swipe", "longPress", "type", "none"}
SAFE_TYPE_TEXT = re.compile(r"^[A-Za-z0-9 .,_@+\-]{1,256}$")


class DemoError(RuntimeError):
    """Expected demo failure with an actionable message."""


class OpenAPIError(DemoError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        request_id: str = "",
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.http_status = http_status


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    mime: str


@dataclass(frozen=True)
class SuggestedAction:
    run_id: str
    action: str
    params: dict[str, Any]
    request_id: str
    thread_id: str = ""


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hmac_sha256(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def canonical_query(params: Mapping[str, Any]) -> str:
    pairs: list[tuple[str, str]] = []
    for key in sorted(params):
        value = params[key]
        values = value if isinstance(value, (list, tuple)) else [value]
        pairs.extend((str(key), str(item)) for item in values)
    return "&".join(
        f"{urllib.parse.quote(key, safe='-_.~')}="
        f"{urllib.parse.quote(value, safe='-_.~')}"
        for key, value in pairs
    )


class VolcengineSigner:
    """Minimal Volcengine OpenAPI HMAC-SHA256 signer."""

    def __init__(self, access_key: str, secret_key: str) -> None:
        if not access_key or not secret_key:
            raise DemoError("VOLC_ACCESSKEY and VOLC_SECRETKEY must both be set")
        self._access_key = access_key
        self._secret_key = secret_key

    def sign(
        self,
        method: str,
        query: Mapping[str, Any],
        body: bytes,
        *,
        now: datetime | None = None,
    ) -> tuple[str, dict[str, str]]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        x_date = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        short_date = x_date[:8]
        payload_hash = _sha256_hex(body)
        normalized_query = canonical_query(query)
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_headers = "\n".join(
            (
                "content-type:application/json",
                f"host:{API_HOST}",
                f"x-content-sha256:{payload_hash}",
                f"x-date:{x_date}",
            )
        )
        canonical_request = "\n".join(
            (
                method.upper(),
                "/",
                normalized_query,
                canonical_headers,
                "",
                signed_headers,
                payload_hash,
            )
        )
        scope = f"{short_date}/{API_REGION}/{API_SERVICE}/request"
        string_to_sign = "\n".join(
            (
                "HMAC-SHA256",
                x_date,
                scope,
                _sha256_hex(canonical_request.encode("utf-8")),
            )
        )
        key_date = _hmac_sha256(self._secret_key.encode("utf-8"), short_date)
        key_region = _hmac_sha256(key_date, API_REGION)
        key_service = _hmac_sha256(key_region, API_SERVICE)
        key_signing = _hmac_sha256(key_service, "request")
        signature = _hmac_sha256(key_signing, string_to_sign).hex()
        authorization = (
            f"HMAC-SHA256 Credential={self._access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        url = f"https://{API_HOST}/?{normalized_query}"
        return url, {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": API_HOST,
            "X-Content-Sha256": payload_hash,
            "X-Date": x_date,
        }


def inspect_image(image: bytes) -> ImageInfo:
    if len(image) > MAX_IMAGE_BYTES:
        raise DemoError(f"image is {len(image)} bytes, exceeding the 5 MiB demo limit")
    if image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) >= 24:
        width, height = struct.unpack(">II", image[16:24])
        if width < 1 or height < 1:
            raise DemoError("image dimensions must be positive")
        return ImageInfo(width=width, height=height, mime="image/png")
    if image.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 <= len(image):
            if image[offset] != 0xFF:
                offset += 1
                continue
            marker = image[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(image):
                break
            segment_length = struct.unpack(">H", image[offset : offset + 2])[0]
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            } and offset + 7 <= len(image):
                height, width = struct.unpack(">HH", image[offset + 3 : offset + 7])
                if width < 1 or height < 1:
                    break
                return ImageInfo(width=width, height=height, mime="image/jpeg")
            if segment_length < 2:
                break
            offset += segment_length
    raise DemoError("only valid PNG and JPEG images are supported")


def _json_body(response_body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenAPIError("server returned a non-JSON response") from exc
    if not isinstance(value, dict):
        raise OpenAPIError("server returned a JSON value that is not an object")
    return value


def _verified_urlopen(request: urllib.request.Request, *, timeout: float) -> Any:
    """Use certifi when available; never disable TLS verification."""
    try:
        import certifi  # type: ignore[import-not-found]

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def parse_action_response(
    payload: Mapping[str, Any], image: ImageInfo
) -> SuggestedAction:
    metadata = payload.get("ResponseMetadata")
    if not isinstance(metadata, Mapping):
        raise OpenAPIError("response is missing ResponseMetadata")
    request_id = str(metadata.get("RequestId") or "")
    error = metadata.get("Error")
    if isinstance(error, Mapping):
        code = str(error.get("Code") or error.get("CodeN") or "OpenAPIError")
        message = str(error.get("Message") or code)
        raise OpenAPIError(message, code=code, request_id=request_id)

    result = payload.get("Result")
    if not isinstance(result, Mapping):
        raise OpenAPIError(
            "successful response is missing Result", request_id=request_id
        )

    # Public examples use lower-case fields directly under Result. Some service
    # deployments wrap the action in Result.data and use RunId/ThreadId.
    nested = result.get("data")
    action_data = nested if isinstance(nested, Mapping) else result
    run_id = str(
        action_data.get("run_id")
        or action_data.get("RunId")
        or result.get("run_id")
        or result.get("RunId")
        or ""
    )
    thread_id = str(result.get("thread_id") or result.get("ThreadId") or "")
    action = action_data.get("action")
    params = action_data.get("params")

    if not run_id:
        raise OpenAPIError("Result.run_id is empty", request_id=request_id)
    if action not in ALLOWED_ACTIONS:
        raise OpenAPIError(
            f"unsupported Result.action: {action!r}", request_id=request_id
        )
    if not isinstance(params, dict):
        raise OpenAPIError("Result.params must be an object", request_id=request_id)
    _validate_action_params(str(action), params, image)
    return SuggestedAction(
        run_id=run_id,
        action=str(action),
        params=dict(params),
        request_id=request_id,
        thread_id=thread_id,
    )


def _require_int(params: Mapping[str, Any], name: str) -> int:
    value = params.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenAPIError(f"action params.{name} must be an integer")
    return value


def _validate_coordinate(value: int, limit: int, name: str) -> None:
    if not 0 <= value < limit:
        raise OpenAPIError(f"action params.{name}={value} is outside [0, {limit})")


def _validate_action_params(
    action: str, params: Mapping[str, Any], image: ImageInfo
) -> None:
    if action == "none":
        if params:
            raise OpenAPIError("none action must have empty params")
        return
    if action == "tap":
        _validate_coordinate(_require_int(params, "x"), image.width, "x")
        _validate_coordinate(_require_int(params, "y"), image.height, "y")
        return
    if action == "swipe":
        for name, limit in (
            ("x1", image.width),
            ("y1", image.height),
            ("x2", image.width),
            ("y2", image.height),
        ):
            _validate_coordinate(_require_int(params, name), limit, name)
        duration = _require_int(params, "durationMs")
        if not 1 <= duration <= 60_000:
            raise OpenAPIError("swipe durationMs must be in [1, 60000]")
        return
    if action == "longPress":
        _validate_coordinate(_require_int(params, "x"), image.width, "x")
        _validate_coordinate(_require_int(params, "y"), image.height, "y")
        duration = _require_int(params, "durationMs")
        if not 1 <= duration <= 60_000:
            raise OpenAPIError("longPress durationMs must be in [1, 60000]")
        return
    if action == "type":
        text = params.get("text")
        if not isinstance(text, str) or not text:
            raise OpenAPIError("type action requires non-empty params.text")


class ChatActionClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        timeout: float = 90.0,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self._signer = VolcengineSigner(access_key, secret_key)
        self._timeout = timeout
        self._urlopen = urlopen or _verified_urlopen

    def suggest(
        self, prompt: str, image: bytes, image_info: ImageInfo
    ) -> tuple[SuggestedAction, dict[str, Any]]:
        if not prompt.strip():
            raise DemoError("prompt must not be empty")
        request_payload = {
            "UserPrompt": prompt,
            "ImageBase64": base64.b64encode(image).decode("ascii"),
            "ImageMime": image_info.mime,
        }
        body = json.dumps(
            request_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        query = {"Action": API_ACTION, "Version": API_VERSION}
        url, headers = self._signer.sign("POST", query, body)
        request = urllib.request.Request(
            url=url, data=body, headers=headers, method="POST"
        )
        try:
            with self._urlopen(request, timeout=self._timeout) as response:
                payload = _json_body(response.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = _json_body(raw)
            except OpenAPIError:
                raise OpenAPIError(
                    f"HTTP {exc.code} with a non-JSON response",
                    http_status=exc.code,
                ) from exc
            try:
                parse_action_response(payload, image_info)
            except OpenAPIError as parsed:
                parsed.http_status = exc.code
                raise parsed from exc
            raise OpenAPIError(f"HTTP {exc.code}", http_status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise OpenAPIError(f"network request failed: {exc.reason}") from exc
        return parse_action_response(payload, image_info), payload


class AdbDevice:
    def __init__(
        self,
        serial: str,
        *,
        adb_key: str | None = None,
        adb_path: str = "adb",
    ) -> None:
        if not serial:
            raise DemoError("ADB serial is required for capture or execution")
        self.serial = serial
        self.adb_key = adb_key
        self.adb_path = adb_path

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.adb_key:
            env["ADB_VENDOR_KEYS"] = self.adb_key
        return env

    def _run(self, args: Sequence[str], *, timeout: float = 30.0) -> bytes:
        command = [self.adb_path, "-s", self.serial, *args]
        try:
            completed = subprocess.run(
                command,
                env=self._env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DemoError(f"ADB executable not found: {self.adb_path}") from exc
        except subprocess.TimeoutExpired as exc:
            raise DemoError(f"ADB command timed out: {' '.join(args)}") from exc
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise DemoError(f"ADB command failed: {error or completed.returncode}")
        return completed.stdout

    def connect(self) -> None:
        if ":" in self.serial:
            completed = subprocess.run(
                [self.adb_path, "connect", self.serial],
                env=self._env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0:
                message = completed.stderr.decode("utf-8", errors="replace").strip()
                raise DemoError(f"ADB connect failed: {message}")
        state = self._run(["get-state"]).decode("utf-8", errors="replace").strip()
        if state != "device":
            raise DemoError(f"ADB device is not ready: state={state!r}")

    def press_home(self) -> None:
        self._run(["shell", "input", "keyevent", "HOME"])

    def screenshot(self) -> bytes:
        image = self._run(["exec-out", "screencap", "-p"])
        inspect_image(image)
        return image

    def execute(self, suggested: SuggestedAction) -> bool:
        action = suggested.action
        params = suggested.params
        if action == "none":
            return False
        if action == "tap":
            args = ["shell", "input", "tap", str(params["x"]), str(params["y"])]
        elif action == "swipe":
            args = [
                "shell",
                "input",
                "swipe",
                str(params["x1"]),
                str(params["y1"]),
                str(params["x2"]),
                str(params["y2"]),
                str(params["durationMs"]),
            ]
        elif action == "longPress":
            args = [
                "shell",
                "input",
                "swipe",
                str(params["x"]),
                str(params["y"]),
                str(params["x"]),
                str(params["y"]),
                str(params["durationMs"]),
            ]
        elif action == "type":
            text = str(params["text"])
            if not SAFE_TYPE_TEXT.fullmatch(text):
                raise DemoError(
                    "refusing to execute type: text must be 1-256 safe ASCII characters"
                )
            args = ["shell", "input", "text", text.replace(" ", "%s")]
        else:
            raise DemoError(f"unsupported action: {action}")
        self._run(args)
        return True


def _artifact_directory(value: str | None) -> Path:
    if value:
        path = Path(value)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path(__file__).resolve().parent / "artifacts" / timestamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture an Android screenshot and request one ChatAction suggestion."
    )
    parser.add_argument("--prompt", required=True, help="Natural-language UI goal")
    parser.add_argument("--serial", default=os.getenv("ADB_SERIAL", ""))
    parser.add_argument("--adb-key", default=os.getenv("ADB_VENDOR_KEYS"))
    parser.add_argument("--adb-path", default=os.getenv("ADB", "adb"))
    parser.add_argument("--image", help="Use a local PNG/JPEG instead of ADB capture")
    parser.add_argument("--home", action="store_true", help="Press HOME before capture")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the validated suggestion on the ADB device",
    )
    parser.add_argument("--output-dir", help="Artifact directory")
    parser.add_argument("--timeout", type=float, default=90.0)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    access_key = os.getenv("VOLC_ACCESSKEY", "")
    secret_key = os.getenv("VOLC_SECRETKEY", "")
    if not access_key or not secret_key:
        raise DemoError("set VOLC_ACCESSKEY and VOLC_SECRETKEY in the environment")

    device: AdbDevice | None = None
    if not args.image or args.execute:
        device = AdbDevice(args.serial, adb_key=args.adb_key, adb_path=args.adb_path)
        device.connect()

    if args.image:
        image = Path(args.image).read_bytes()
    else:
        assert device is not None
        if args.home:
            device.press_home()
            time.sleep(0.8)
        image = device.screenshot()

    image_info = inspect_image(image)
    output_dir = _artifact_directory(args.output_dir)
    before_suffix = ".png" if image_info.mime == "image/png" else ".jpg"
    before_path = output_dir / f"before{before_suffix}"
    before_path.write_bytes(image)

    started_at = time.monotonic()
    client = ChatActionClient(access_key, secret_key, timeout=args.timeout)
    suggested, raw_payload = client.suggest(args.prompt, image, image_info)
    latency_ms = round((time.monotonic() - started_at) * 1000)

    executed = False
    after_path: Path | None = None
    if args.execute:
        assert device is not None
        executed = device.execute(suggested)
        if executed:
            time.sleep(0.8)
            after = device.screenshot()
            after_path = output_dir / "after.png"
            after_path.write_bytes(after)

    report = {
        "ok": True,
        "api": {
            "action": API_ACTION,
            "version": API_VERSION,
            "service": API_SERVICE,
            "region": API_REGION,
            "request_id": suggested.request_id,
            "latency_ms": latency_ms,
        },
        "input": {
            "prompt": args.prompt,
            "image_mime": image_info.mime,
            "image_width": image_info.width,
            "image_height": image_info.height,
            "image_bytes": len(image),
        },
        "result": {
            "run_id": suggested.run_id,
            "thread_id": suggested.thread_id or None,
            "action": suggested.action,
            "params": suggested.params,
            "executed": executed,
        },
        "artifacts": {
            "before": str(before_path.resolve()),
            "after": str(after_path.resolve()) if after_path else None,
        },
    }
    # The request body, image Base64, Authorization header, AK and SK are never
    # persisted. Only the provider response and a sanitized report are saved.
    (output_dir / "provider_response.json").write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = run(args)
    except OpenAPIError as exc:
        error = {
            "ok": False,
            "error": "openapi_error",
            "code": exc.code or None,
            "message": str(exc),
            "request_id": exc.request_id or None,
            "http_status": exc.http_status,
        }
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 4
    except (DemoError, OSError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": "demo_error", "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
