"""토큰 사용량·비용 누적 집계 — 모든 Claude 호출을 감싸 usage를 모은다.

make_client()로 만든 클라이언트의 messages.create() 응답 usage가 전역 meter에
자동 누적된다. 서버 기동 이후 누적값을 대시보드 우측에 표시한다.
"""

import threading

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M,
    PRICE_CACHE_WRITE_PER_M, PRICE_CACHE_READ_PER_M,
)


class TokenMeter:
    def __init__(self):
        self._lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_write_tokens = 0
        self.cache_read_tokens = 0
        self.calls = 0

    def add(self, usage) -> None:
        if usage is None:
            return
        with self._lock:
            self.calls += 1
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
            self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
            self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens + self.output_tokens
                + self.cache_write_tokens + self.cache_read_tokens)

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * PRICE_INPUT_PER_M
            + self.output_tokens / 1_000_000 * PRICE_OUTPUT_PER_M
            + self.cache_write_tokens / 1_000_000 * PRICE_CACHE_WRITE_PER_M
            + self.cache_read_tokens / 1_000_000 * PRICE_CACHE_READ_PER_M
        )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_write_tokens": self.cache_write_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "total_tokens": self.total_tokens,
                "cost_usd": round(self.cost_usd, 4),
            }


# 전역 누적 미터 (서버 프로세스 생애 동안 누적)
meter = TokenMeter()


class _MeteredMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *args, **kwargs):
        resp = self._inner.create(*args, **kwargs)
        try:
            meter.add(getattr(resp, "usage", None))
        except Exception:
            pass
        return resp

    def __getattr__(self, name):
        return getattr(self._inner, name)


class MeteredAnthropic:
    """anthropic.Anthropic 래퍼 — messages.create 응답 usage를 전역 meter에 누적."""
    def __init__(self, **kwargs):
        self._client = anthropic.Anthropic(**kwargs)
        self.messages = _MeteredMessages(self._client.messages)

    def __getattr__(self, name):
        return getattr(self._client, name)


def make_client(api_key: str | None = None) -> MeteredAnthropic:
    return MeteredAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
