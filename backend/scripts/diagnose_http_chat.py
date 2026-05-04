"""Safe local HTTP diagnosis for health/chat on localhost and 127.0.0.1."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 10


CASES = [
    ("GET", "http://localhost:8000/api/v1/health", None),
    ("GET", "http://127.0.0.1:8000/api/v1/health", None),
    ("POST", "http://localhost:8000/api/v1/chat", {"message": "ola"}),
    ("POST", "http://127.0.0.1:8000/api/v1/chat", {"message": "ola"}),
]


def _sanitize_text(value: object, max_len: int = 200) -> str:
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _safe_body_summary(raw_body: str) -> str:
    try:
        payload = json.loads(raw_body)
    except Exception:
        return _sanitize_text(raw_body)

    parts: list[str] = []

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            trace_id = error.get("trace_id")
            if code is not None:
                parts.append(f"error.code={code}")
            if trace_id is not None:
                parts.append(f"trace_id={trace_id}")

        state = payload.get("state")
        if state is not None:
            parts.append(f"state={state}")

        trace_id = payload.get("trace_id")
        if trace_id is not None and not any(item.startswith("trace_id=") for item in parts):
            parts.append(f"trace_id={trace_id}")

        reply = payload.get("reply")
        if reply is not None:
            parts.append(f"reply={_sanitize_text(reply)}")

    if not parts:
        return _sanitize_text(raw_body)

    return " | ".join(parts)


def _call(method: str, url: str, body: dict | None) -> None:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, method=method, data=data, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            raw = response.read().decode("utf-8", errors="replace")
            print(f"url={url}")
            print(f"status={status}")
            print(f"summary={_safe_body_summary(raw)}")
            print("-")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        print(f"url={url}")
        print(f"status={exc.code}")
        print(f"summary={_safe_body_summary(raw)}")
        print("-")
    except Exception as exc:
        print(f"url={url}")
        print(f"status=ERROR")
        print(f"summary={type(exc).__name__}: {_sanitize_text(exc)}")
        print("-")


def main() -> int:
    for method, url, body in CASES:
        _call(method, url, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
