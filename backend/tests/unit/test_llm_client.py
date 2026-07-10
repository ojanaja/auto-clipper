from types import SimpleNamespace

import pytest

from pipeline.llm_client import AnthropicLLMClient, GeminiLLMClient, make_llm_client


@pytest.fixture
def fake_anthropic(mocker):
    client = mocker.MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="text", text='[{"start": 0}]'),
        ]
    )
    mocker.patch("pipeline.llm_client.anthropic.Anthropic", return_value=client)
    return client


def test_complete_sends_prompt_and_returns_text(fake_anthropic):
    llm = AnthropicLLMClient()
    result = llm.complete("cari momen menarik")

    assert result == '[{"start": 0}]'
    kwargs = fake_anthropic.messages.create.call_args.kwargs
    assert kwargs["messages"] == [{"role": "user", "content": "cari momen menarik"}]
    assert kwargs["model"] == "claude-opus-4-8"


def test_complete_custom_model(fake_anthropic):
    llm = AnthropicLLMClient(model="claude-haiku-4-5")
    llm.complete("prompt")
    assert fake_anthropic.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5"


def test_complete_no_text_block_raises(fake_anthropic):
    fake_anthropic.messages.create.return_value = SimpleNamespace(content=[])
    with pytest.raises(ValueError):
        AnthropicLLMClient().complete("prompt")


# --- GeminiLLMClient ---

GEMINI_RESPONSE = {
    "candidates": [
        {"content": {"parts": [{"text": '[{"start": 0, "end": 5}]'}]}}
    ]
}


@pytest.fixture
def fake_httpx(mocker):
    response = mocker.MagicMock()
    response.status_code = 200
    response.json.return_value = GEMINI_RESPONSE
    post = mocker.patch("pipeline.llm_client.httpx.post", return_value=response)
    return post, response


def test_gemini_complete_sends_prompt_and_returns_text(fake_httpx):
    post, _ = fake_httpx
    llm = GeminiLLMClient(api_key="test-key")

    result = llm.complete("cari momen")

    assert result == '[{"start": 0, "end": 5}]'
    url = post.call_args.args[0]
    assert "generativelanguage.googleapis.com" in url
    assert "gemini" in url
    body = post.call_args.kwargs["json"]
    assert body["contents"][0]["parts"][0]["text"] == "cari momen"
    # Key dikirim via header, bukan query string (tidak bocor di log URL).
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "test-key"


def test_gemini_http_error_raises(fake_httpx):
    _, response = fake_httpx
    response.status_code = 429
    response.text = "quota exceeded"
    with pytest.raises(RuntimeError):
        GeminiLLMClient(api_key="k").complete("prompt")


def test_gemini_empty_candidates_raises(fake_httpx):
    _, response = fake_httpx
    response.json.return_value = {"candidates": []}
    with pytest.raises(ValueError):
        GeminiLLMClient(api_key="k").complete("prompt")


# --- make_llm_client ---


def test_factory_defaults_to_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(make_llm_client(), GeminiLLMClient)


def test_factory_anthropic(monkeypatch, mocker):
    mocker.patch("pipeline.llm_client.anthropic.Anthropic")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert isinstance(make_llm_client(), AnthropicLLMClient)


def test_factory_gemini_without_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(RuntimeError):
        make_llm_client()


def test_factory_uses_config_overrides(monkeypatch, mocker):
    mocker.patch("pipeline.llm_client.anthropic.Anthropic")
    llm = make_llm_client(
        provider="anthropic",
        anthropic_api_key="cfg-key",
        model="claude-sonnet-4",
    )
    assert isinstance(llm, AnthropicLLMClient)
    assert llm._model == "claude-sonnet-4"


def test_factory_gemini_config_key_overrides_env(monkeypatch, fake_httpx):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    post, _ = fake_httpx
    llm = make_llm_client(provider="gemini", gemini_api_key="cfg-key", model="gemini-pro")
    assert isinstance(llm, GeminiLLMClient)
    assert llm._model == "gemini-pro"
    llm.complete("x")
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "cfg-key"
