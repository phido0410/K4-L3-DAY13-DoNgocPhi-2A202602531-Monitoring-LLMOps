from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

CORRELATION_ID_PATTERN = re.compile(r"req-[0-9a-f]{8}")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Xóa context của request trước để metadata không rò sang request này
        clear_contextvars()

        # Chỉ nhận x-request-id đúng format req-<8-hex>; sai format thì sinh ID mới
        incoming = request.headers.get("x-request-id", "")
        if CORRELATION_ID_PATTERN.fullmatch(incoming):
            correlation_id = incoming
        else:
            correlation_id = f"req-{uuid.uuid4().hex[:8]}"

        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)

        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = str(int((time.perf_counter() - start) * 1000))

        return response
