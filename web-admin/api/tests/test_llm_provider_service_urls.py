from services.llm_provider_service import LlmProviderService


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
