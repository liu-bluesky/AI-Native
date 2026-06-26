import pytest

from services.providers.llm_provider_service import LlmProviderConnectionTestError, LlmProviderService


def test_llm_provider_service_supports_bigmodel_openai_compatible_base_url():
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    assert LlmProviderService._build_chat_completion_url(base_url) == (
        "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    )
    assert LlmProviderService._build_models_url(base_url) == (
        "https://open.bigmodel.cn/api/paas/v4/models"
    )
    assert LlmProviderService._build_responses_url(base_url) == (
        "https://open.bigmodel.cn/api/paas/v4/responses"
    )
    assert LlmProviderService._build_images_generation_url(base_url) == (
        "https://open.bigmodel.cn/api/paas/v4/images/generations"
    )
    assert LlmProviderService._build_videos_generation_url(base_url) == (
        "https://open.bigmodel.cn/api/paas/v4/videos/generations"
    )
    assert LlmProviderService._build_async_result_url(base_url, "req-123") == (
        "https://open.bigmodel.cn/api/paas/v4/async-result/req-123"
    )


def test_llm_provider_service_normalizes_ollama_root_base_url_to_v1():
    base_url = "http://localhost:11434"

    assert LlmProviderService._build_models_url(base_url) == "http://localhost:11434/v1/models"
    assert LlmProviderService._build_chat_completion_url(base_url) == (
        "http://localhost:11434/v1/chat/completions"
    )


def test_llm_provider_service_keeps_ollama_v1_base_url_unchanged():
    base_url = "http://127.0.0.1:11434/v1"

    assert LlmProviderService._build_models_url(base_url) == "http://127.0.0.1:11434/v1/models"
    assert LlmProviderService._build_chat_completion_url(base_url) == (
        "http://127.0.0.1:11434/v1/chat/completions"
    )


def test_llm_provider_service_extracts_model_names_from_openai_models_payload():
    payload = {
        "data": [
            {"id": "gemma4"},
            {"id": "qwen3:8b"},
            {"id": "gemma4"},
            {"id": ""},
        ]
    }

    assert LlmProviderService._extract_model_names_from_models_payload(payload) == [
        "gemma4",
        "qwen3:8b",
    ]


def test_llm_provider_service_extracts_model_names_from_models_key_payload():
    payload = {
        "models": [
            "llama3.2",
            {"name": "deepseek-r1"},
            {"model": "gemma3"},
            {"name": "llama3.2"},
            None,
        ]
    }

    assert LlmProviderService._extract_model_names_from_models_payload(payload) == [
        "llama3.2",
        "deepseek-r1",
        "gemma3",
    ]


def test_llm_provider_service_discovers_models_with_ollama_root_url(monkeypatch):
    captured = {}

    def fake_request_json(method, endpoint, headers, *, body=None, timeout=30):
        captured.update(
            {
                "method": method,
                "endpoint": endpoint,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        return {"data": [{"id": "gemma4"}, {"id": "qwen3:8b"}]}

    monkeypatch.setattr(LlmProviderService, "_request_json", staticmethod(fake_request_json))

    service = LlmProviderService.__new__(LlmProviderService)

    result = service.discover_models(
        {
            "provider_type": "openai-compatible",
            "base_url": "http://localhost:11434",
            "api_key": "",
            "extra_headers": {"X-Debug": "1"},
        }
    )

    assert result == {
        "models": ["gemma4", "qwen3:8b"],
        "models_url": "http://localhost:11434/v1/models",
        "count": 2,
    }
    assert captured["method"] == "GET"
    assert captured["endpoint"] == "http://localhost:11434/v1/models"
    assert captured["headers"]["X-Debug"] == "1"
    assert "Authorization" not in captured["headers"]
    assert captured["body"] is None
    assert captured["timeout"] == 20


def test_llm_provider_service_resolves_desktop_runtime_model_from_model_config():
    provider = {
        "default_model": "",
        "models": [],
        "model_configs": [{"model": "solver-v2", "model_type": "text_generation"}],
    }

    assert LlmProviderService.resolve_provider_model_name(provider) == "solver-v2"


@pytest.mark.asyncio
async def test_llm_provider_service_does_not_cap_high_max_tokens(monkeypatch):
    captured = {}
    service = object.__new__(LlmProviderService)
    provider = {
        "id": "provider-1",
        "name": "Provider 1",
        "provider_type": "openai-compatible",
        "base_url": "https://gateway.example.com/v1",
        "enabled": True,
        "default_model": "deepseek-v4-flash",
        "models": [],
    }
    service.get_provider_raw = lambda *args, **kwargs: provider

    def fake_request_json(method, endpoint, headers, *, body=None, timeout=30):
        captured["body"] = body
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(LlmProviderService, "_request_json", staticmethod(fake_request_json))

    await service.chat_completion(
        "provider-1",
        "deepseek-v4-flash",
        [{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=12000,
        timeout=30,
    )

    assert captured["body"]["max_tokens"] == 12000


def test_llm_provider_service_extracts_reasoning_content_from_sse_chunk():
    payload = {
        "choices": [
            {
                "delta": {
                    "role": "assistant",
                    "reasoning_content": "用户的问题是在确认接口是否可用。",
                }
            }
        ]
    }

    assert LlmProviderService._extract_content(payload) == "用户的问题是在确认接口是否可用。"


def test_llm_provider_service_parses_sse_reasoning_stream_as_text():
    raw = "\n".join(
        [
            'data: {"choices":[{"delta":{"role":"assistant","reasoning_content":"先检查配置。"}}]}',
            'data: {"choices":[{"delta":{"role":"assistant","reasoning_content":"接口已连通。"}}]}',
            "data: [DONE]",
        ]
    )

    assert LlmProviderService._parse_sse_content(raw) == "先检查配置。接口已连通。"


def test_llm_provider_service_parses_sse_usage_only_chunk_into_payload():
    raw = "\n".join(
        [
            'data: {"id":"","object":"chat.completion.chunk","created":0,"model":"gpt-5.5","choices":[],"usage":{"prompt_tokens":856,"completion_tokens":0,"total_tokens":856}}',
            "data: [DONE]",
        ]
    )

    payload = LlmProviderService._parse_sse_response_payload(raw)

    assert payload == {
        "usage": {
            "input_tokens": 856,
            "output_tokens": 0,
            "total_tokens": 856,
        },
        "model": "gpt-5.5",
    }
    assert LlmProviderService._parse_sse_content(raw) == ""


def test_llm_provider_service_request_json_handles_sse_usage_only_payload(monkeypatch):
    class FakeResponse:
        status_code = 200

        def __init__(self, text):
            self.text = text
            self.headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self):
            self.trust_env = False

        def request(self, *args, **kwargs):
            raw = "\n".join(
                [
                    'data: {"id":"","object":"chat.completion.chunk","created":0,"model":"gpt-5.5","choices":[],"usage":{"prompt_tokens":856,"completion_tokens":0,"total_tokens":856}}',
                    "data: [DONE]",
                ]
            )
            return FakeResponse(raw)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("services.providers.llm_provider_service.requests.Session", FakeSession)

    payload = LlmProviderService._request_json("POST", "https://example.com", {}, body={"test": 1})

    assert payload == {
        "usage": {
            "input_tokens": 856,
            "output_tokens": 0,
            "total_tokens": 856,
        },
        "model": "gpt-5.5",
    }


def test_llm_provider_service_normalizes_usage_only_stream_chunk():
    payload = {
        "id": "resp-usage",
        "model": "glm-test",
        "choices": [],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        },
    }

    assert LlmProviderService._stream_chunk_to_result(
        payload,
        provider_id="provider-1",
        model_name="fallback-model",
    ) == {
        "usage": {
            "input_tokens": 12,
            "output_tokens": 8,
            "total_tokens": 20,
        },
        "provider_id": "provider-1",
        "model_name": "glm-test",
    }


def test_llm_provider_service_extracts_image_artifacts_from_payload():
    payload = {
        "data": [
            {
                "url": "https://cdn.example.com/generated/image-1.png",
            }
        ]
    }

    artifacts = LlmProviderService._extract_image_artifacts_from_payload(
        payload,
        provider_id="lmp-zhipu",
        model_name="glm-image",
    )

    assert artifacts == [
        {
            "asset_type": "image",
            "title": "glm-image 图片 1",
            "preview_url": "https://cdn.example.com/generated/image-1.png",
            "content_url": "https://cdn.example.com/generated/image-1.png",
            "mime_type": "",
            "metadata": {
                "provider_id": "lmp-zhipu",
                "model_name": "glm-image",
            },
        }
    ]


def test_llm_provider_service_extracts_video_artifacts_from_payload():
    payload = {
        "video_result": [
            {
                "url": "https://cdn.example.com/generated/video-1.mp4",
                "cover_image_url": "https://cdn.example.com/generated/video-1-cover.png",
            }
        ]
    }

    artifacts = LlmProviderService._extract_video_artifacts_from_payload(
        payload,
        provider_id="lmp-zhipu",
        model_name="cogvideox-3",
    )

    assert artifacts == [
        {
            "asset_type": "video",
            "title": "cogvideox-3 视频 1",
            "preview_url": "https://cdn.example.com/generated/video-1-cover.png",
            "content_url": "https://cdn.example.com/generated/video-1.mp4",
            "mime_type": "video/mp4",
            "metadata": {
                "provider_id": "lmp-zhipu",
                "model_name": "cogvideox-3",
            },
        }
    ]


def test_llm_provider_service_summarizes_html_gateway_errors():
    raw = """
    <!DOCTYPE html>
    <html>
      <head><title>502 Bad Gateway</title></head>
      <body>gateway error</body>
    </html>
    """

    summary, diagnostic = LlmProviderService._summarize_http_error_response(
        raw,
        content_type="text/html; charset=utf-8",
    )

    assert summary == "upstream returned an HTML error page (502 Bad Gateway)"
    assert "gateway error" in diagnostic


def test_llm_provider_service_summarizes_json_errors():
    summary, diagnostic = LlmProviderService._summarize_http_error_response(
        '{"error":{"message":"missing required scope(s): im:message.send_as_user"}}',
        content_type="application/json",
    )

    assert summary == "missing required scope(s): im:message.send_as_user"
    assert "missing required scope" in diagnostic


def test_llm_provider_service_test_connection_uses_model_config_model_alias():
    service = object.__new__(LlmProviderService)
    provider = {
        "id": "provider-1",
        "name": "Provider 1",
        "provider_type": "openai-compatible",
        "base_url": "https://gateway.example.com/v1",
        "enabled": True,
        "default_model": "",
        "models": [],
        "model_configs": [{"model": "solver-v2", "model_type": "text_generation"}],
    }
    captured = {}

    service.get_provider_raw = lambda *args, **kwargs: provider

    def _fake_call_chat_completion_sse(**kwargs):
        captured["model_name"] = kwargs["model_name"]
        return {"choices": [{"message": {"content": "ok"}}]}

    service._call_chat_completion_sse = _fake_call_chat_completion_sse

    result = service.test_provider_connection("provider-1")

    assert captured["model_name"] == "solver-v2"
    assert result["reachable"] is True
    assert result["model_tested"] == "solver-v2"
    assert result["completion_url"] == "https://gateway.example.com/v1/chat/completions"
    assert result["request_urls"] == [
        "https://gateway.example.com/v1/models",
        "https://gateway.example.com/v1/chat/completions",
    ]


def test_llm_provider_service_test_connection_normalizes_ollama_root_urls():
    service = object.__new__(LlmProviderService)
    provider = {
        "id": "ollama-provider",
        "name": "Ollama",
        "provider_type": "openai-compatible",
        "base_url": "http://localhost:11434",
        "enabled": True,
        "default_model": "Gemma4",
        "models": [],
        "model_configs": [{"name": "Gemma4", "model_type": "text_generation"}],
    }
    captured = {}

    service.get_provider_raw = lambda *args, **kwargs: provider

    def _fake_call_chat_completion_sse(**kwargs):
        captured["model_name"] = kwargs["model_name"]
        return {"choices": [{"message": {"content": "ok"}}]}

    service._call_chat_completion_sse = _fake_call_chat_completion_sse

    result = service.test_provider_connection("ollama-provider")

    assert captured["model_name"] == "Gemma4"
    assert result["reachable"] is True
    assert result["completion_url"] == "http://localhost:11434/v1/chat/completions"
    assert result["request_urls"] == [
        "http://localhost:11434/v1/models",
        "http://localhost:11434/v1/chat/completions",
    ]


def test_llm_provider_service_test_connection_rejects_empty_model_content():
    service = object.__new__(LlmProviderService)
    provider = {
        "id": "provider-1",
        "name": "Provider 1",
        "provider_type": "openai-compatible",
        "base_url": "http://127.0.0.1:11434/v1",
        "enabled": True,
        "default_model": "gemma4",
        "models": [],
        "model_configs": [{"name": "gemma4", "model_type": "text_generation"}],
    }
    service.get_provider_raw = lambda *args, **kwargs: provider
    service._call_chat_completion_sse = lambda **kwargs: {
        "model": "gemma4",
        "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 0, "total_tokens": 8},
    }

    with pytest.raises(LlmProviderConnectionTestError) as exc_info:
        service.test_provider_connection("provider-1")

    result = exc_info.value.result
    assert result["reachable"] is False
    assert result["model_tested"] == "gemma4"
    assert "model returned empty content" in result["message"]
    assert "output_tokens" in result["message"]


def test_llm_provider_service_test_connection_returns_addresses_when_model_missing():
    service = object.__new__(LlmProviderService)
    provider = {
        "id": "provider-1",
        "name": "Provider 1",
        "provider_type": "openai-compatible",
        "base_url": "https://gateway.example.com/v1",
        "enabled": True,
        "default_model": "",
        "models": [],
        "model_configs": [],
    }
    service.get_provider_raw = lambda *args, **kwargs: provider
    service._call_chat_completion_sse = lambda **kwargs: pytest.fail("empty model should not be sent")

    with pytest.raises(LlmProviderConnectionTestError) as exc_info:
        service.test_provider_connection("provider-1")

    result = exc_info.value.result
    assert result["reachable"] is False
    assert result["model_tested"] == ""
    assert "未指定测试模型" in result["message"]
    assert result["completion_url"] == "https://gateway.example.com/v1/chat/completions"
    assert result["request_urls"] == [
        "https://gateway.example.com/v1/models",
        "https://gateway.example.com/v1/chat/completions",
    ]
