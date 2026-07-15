"""Retry classification and bounded backoff for agent runtime failures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    reason: str
    signature: str


class RuntimeRetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = 2,
        base_delay_seconds: float = 0.25,
        max_delay_seconds: float = 2.0,
    ):
        self.max_attempts = max(0, int(max_attempts))
        self.base_delay_seconds = max(0.0, float(base_delay_seconds))
        self.max_delay_seconds = max(self.base_delay_seconds, float(max_delay_seconds))

    def classify_llm_error(self, error: dict[str, Any] | None) -> RetryDecision:
        payload = dict(error or {})
        message = self._message(payload)
        normalized = message.lower()
        explicit_retryable = payload.get("retryable")
        if isinstance(explicit_retryable, bool):
            retryable = explicit_retryable
        else:
            retryable = self._matches_retryable_error(normalized)
        reason = self._reason(normalized, retryable=retryable)
        signature_source = f"{reason}:{normalized[:500]}"
        signature = hashlib.sha1(signature_source.encode("utf-8")).hexdigest()[:16]
        return RetryDecision(retryable=retryable, reason=reason, signature=signature)

    def delay_seconds(self, attempt: int) -> float:
        normalized_attempt = max(1, int(attempt))
        delay = self.base_delay_seconds * (2 ** (normalized_attempt - 1))
        return min(self.max_delay_seconds, delay)

    def _matches_retryable_error(self, message: str) -> bool:
        retryable_markers = (
            "timeout",
            "timed out",
            "rate limit",
            "too many requests",
            "connection reset",
            "connection refused",
            "connection aborted",
            "temporarily unavailable",
            "temporary failure",
            "failed to resolve",
            "name or service not known",
            "nodename nor servname provided",
            "dns",
            "http 429",
            "status 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "status 500",
            "status 502",
            "status 503",
            "status 504",
        )
        return any(marker in message for marker in retryable_markers)

    def _reason(self, message: str, *, retryable: bool) -> str:
        if not retryable:
            return "llm_error_terminal"
        if "429" in message or "rate limit" in message or "too many requests" in message:
            return "llm_rate_limited"
        if "timeout" in message or "timed out" in message:
            return "llm_timeout"
        if any(marker in message for marker in ("resolve", "dns", "name or service", "nodename")):
            return "llm_network_resolution_error"
        return "llm_transient_error"

    def _message(self, payload: dict[str, Any]) -> str:
        for key in ("message", "error_message", "detail", "raw_error", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "model service request failed"


__all__ = ["RetryDecision", "RuntimeRetryPolicy"]
