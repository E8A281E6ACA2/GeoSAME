from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .env import first_env, load_env, redact


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    timeout: int = 120

    def redacted(self) -> dict[str, str | int]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": redact(self.base_url, keep=12),
            "api_key": redact(self.api_key),
            "timeout": self.timeout,
        }


@dataclass(frozen=True)
class ChatResult:
    content: str
    requested_model: str
    resolved_model: str | None
    provider: str
    endpoint_family: str
    response_id: str | None
    response_created: int | str | None
    requested_at: str
    completed_at: str
    finish_reason: str | None
    usage: dict[str, Any] | None
    retry_count: int
    latency_ms: int
    parameters: dict[str, Any]
    request_id: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "provider": self.provider,
            "endpoint_family": self.endpoint_family,
            "response_id": self.response_id,
            "request_id": self.request_id,
            "response_created": self.response_created,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "retry_count": self.retry_count,
            "latency_ms": self.latency_ms,
            "parameters": self.parameters,
        }


def load_llm_config(model: str | None = None) -> LLMConfig:
    load_env()
    provider = first_env("GEOSYNQ_LLM_PROVIDER", "LLM_PROVIDER", default="openai_compatible") or "openai_compatible"
    selected_model = model or first_env("GEOSYNQ_LLM_MODEL", "OPENAI_MODEL", "MODEL_NAME", default="")
    base_url = first_env("GEOSYNQ_LLM_BASE_URL", "OPENAI_BASE_URL", "API_BASE_URL", "BASE_URL", "URL")
    api_key = first_env("GEOSYNQ_LLM_API_KEY", "OPENAI_API_KEY", "API_KEY", "KEY")
    timeout_text = first_env("GEOSYNQ_LLM_TIMEOUT", "LLM_TIMEOUT", default="120") or "120"

    missing = []
    if not selected_model:
        missing.append("GEOSYNQ_LLM_MODEL")
    if not base_url:
        missing.append("GEOSYNQ_LLM_BASE_URL")
    if not api_key:
        missing.append("GEOSYNQ_LLM_API_KEY")
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing model endpoint configuration: {joined}. See .env.example.")

    return LLMConfig(
        provider=provider,
        model=selected_model or "unspecified",
        base_url=base_url,
        api_key=api_key,
        timeout=int(timeout_text),
    )


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return "".join(parts)
    raise TypeError(f"unsupported message content: {type(content).__name__}")


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig | None = None, model: str | None = None):
        self.config = config or load_llm_config(model=model)
        self.max_retries = 4

    def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int = 1200,
        extra_body: dict[str, Any] | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if extra_body:
            payload.update(extra_body)

        parameters = {key: value for key, value in payload.items() if key != "messages"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        requested_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        raw = ""
        response_headers: dict[str, str] = {}
        retry_count = 0
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                _chat_completions_url(self.config.base_url),
                data=body,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                    raw = response.read().decode("utf-8")
                    response_headers = {key.lower(): value for key, value in response.headers.items()}
                retry_count = attempt
                break
            except urllib.error.HTTPError as exc:
                error_text = exc.read().decode("utf-8", errors="replace")
                is_retryable = exc.code == 429 or 500 <= exc.code < 600
                if attempt >= self.max_retries or not is_retryable:
                    raise RuntimeError(f"模型接口 HTTP {exc.code}: {error_text[:1000]}") from exc
                time.sleep(min(2**attempt, 20))
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"模型接口连接失败：{exc}") from exc
                time.sleep(min(2**attempt, 20))

        completed_at = datetime.now(timezone.utc).isoformat()
        latency_ms = round((time.perf_counter() - started) * 1000)
        data = json.loads(raw)
        try:
            choice = data["choices"][0]
            content = _content_as_text(choice["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型接口返回格式异常：{raw[:1000]}") from exc

        return ChatResult(
            content=content,
            requested_model=self.config.model,
            resolved_model=str(data.get("model")) if data.get("model") is not None else None,
            provider=self.config.provider,
            endpoint_family="chat_completions",
            response_id=str(data.get("id")) if data.get("id") is not None else None,
            response_created=data.get("created"),
            requested_at=requested_at,
            completed_at=completed_at,
            finish_reason=str(choice.get("finish_reason")) if choice.get("finish_reason") is not None else None,
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
            retry_count=retry_count,
            latency_ms=latency_ms,
            parameters=parameters,
            request_id=response_headers.get("x-request-id") or response_headers.get("request-id"),
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int = 1200,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        return self.chat_with_metadata(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            extra_body=extra_body,
        ).content


def make_messages(user_prompt: str, system_prompt: str | None = None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return messages

