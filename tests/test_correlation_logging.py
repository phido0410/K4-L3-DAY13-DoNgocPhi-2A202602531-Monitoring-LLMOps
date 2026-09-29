from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.logging_config import get_logger
from app.main import app

CHAT_BODY = {
    "user_id": "student-01",
    "session_id": "session-01",
    "feature": "qa",
    "message": "Explain observability",
}


def _post_chats(headers_list: list[dict[str, str]]) -> list[httpx.Response]:
    async def send() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return [await client.post("/chat", json=CHAT_BODY, headers=h) for h in headers_list]

    return asyncio.run(send())


def _read_logs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_generates_correlation_id_and_returns_headers(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    (response,) = _post_chats([{}])

    correlation_id = response.headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", correlation_id)
    assert response.json()["correlation_id"] == correlation_id
    assert int(response.headers["x-response-time-ms"]) >= 0

    api_logs = [rec for rec in _read_logs(log_path) if rec.get("service") == "api"]
    assert {rec["event"] for rec in api_logs} == {"request_received", "response_sent"}
    for rec in api_logs:
        assert rec["correlation_id"] == correlation_id
        assert rec["session_id"] == "session-01"
        assert rec["feature"] == "qa"
        assert rec["model"]
        assert rec["env"]
        assert rec["user_id_hash"] != "student-01"


def test_accepts_valid_incoming_id_and_rejects_invalid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    valid, invalid = _post_chats([{"x-request-id": "req-1a2b3c4d"}, {"x-request-id": "bad id"}])

    assert valid.headers["x-request-id"] == "req-1a2b3c4d"
    assert re.fullmatch(r"req-[0-9a-f]{8}", invalid.headers["x-request-id"])


def test_context_does_not_leak_between_requests(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    first, second = _post_chats([{}, {}])

    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    ids_per_event = [rec["correlation_id"] for rec in _read_logs(log_path) if rec.get("service") == "api"]
    assert ids_per_event == [first.headers["x-request-id"]] * 2 + [second.headers["x-request-id"]] * 2


def test_log_pipeline_scrubs_pii_before_writing_file(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    get_logger().info(
        "pii_probe",
        service="test",
        payload={"detail": "a@b.com 0987654321 079203001234 4111 1111 1111 1111"},
    )

    raw = log_path.read_text(encoding="utf-8")
    for secret in ("a@b.com", "0987654321", "079203001234", "4111 1111 1111 1111"):
        assert secret not in raw
    assert "REDACTED_CCCD" in raw
