from services.providers.llm_provider_service import LlmProviderService


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
