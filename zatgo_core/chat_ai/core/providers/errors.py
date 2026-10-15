"""Provider errors with user-safe messages.

Technical detail (HTTP body, endpoint) goes to the backend log only; `message`
is what the chat UI may show.
"""

from __future__ import annotations


class ProviderError(RuntimeError):
	def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = False, detail: str = ""):
		super().__init__(message)
		self.message = message
		self.code = code
		self.retryable = retryable
		self.detail = detail


def from_http_status(status: int, body: str = "") -> ProviderError:
	if status in (401, 403):
		return ProviderError(
			"The AI provider rejected the configured API key. Ask an administrator to check Chat AI Settings.",
			code="auth", detail=body,
		)
	if status == 404:
		return ProviderError(
			"The selected model or endpoint was not found. Ask an administrator to check Chat AI Settings.",
			code="model_unavailable", detail=body,
		)
	if status == 408 or status == 504:
		return ProviderError("The AI provider timed out. Please retry.", code="timeout", retryable=True, detail=body)
	if status == 429:
		return ProviderError(
			"The AI provider is rate limiting requests. Please retry shortly.",
			code="rate_limited", retryable=True, detail=body,
		)
	if status >= 500:
		return ProviderError(
			"The AI provider is temporarily unavailable. Please retry.",
			code="provider_unavailable", retryable=True, detail=body,
		)
	return ProviderError("The AI provider could not process this request.", code="bad_request", detail=body)


def from_exception(exc: Exception) -> ProviderError:
	"""Map urllib/socket failures (no HTTP response) to a ProviderError."""
	import socket

	if isinstance(exc, ProviderError):
		return exc
	if isinstance(exc, (socket.timeout, TimeoutError)):
		return ProviderError("The AI provider timed out. Please retry.", code="timeout", retryable=True, detail=str(exc))
	return ProviderError(
		"Could not reach the AI provider. Please check the network and retry.",
		code="network", retryable=True, detail=str(exc),
	)
