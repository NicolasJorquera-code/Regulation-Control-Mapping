"""Tests for controlnexus.core.transport."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from controlnexus.core.transport import AsyncTransportClient, build_client_from_env
from controlnexus.exceptions import ExternalServiceException


# -- AsyncTransportClient -------------------------------------------------------


@pytest.fixture
def client():
    return AsyncTransportClient(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=1,
    )


class TestCandidateUrls:
    def test_generates_v1_and_plain(self, client):
        urls = client._candidate_urls()
        assert urls == [
            "https://api.example.com/v1/chat/completions",
            "https://api.example.com/chat/completions",
        ]

    def test_strips_trailing_slash(self):
        c = AsyncTransportClient(api_key="k", base_url="https://api.example.com/", model="m")
        urls = c._candidate_urls()
        assert urls[0] == "https://api.example.com/v1/chat/completions"

    def test_working_url_first(self, client):
        client._working_url = "https://api.example.com/chat/completions"
        urls = client._candidate_urls()
        assert urls[0] == "https://api.example.com/chat/completions"
        assert len(urls) == 2


class TestChatCompletion:
    async def test_success_returns_json(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http

        result = await client.chat_completion([{"role": "user", "content": "hi"}])
        assert result == {"choices": [{"message": {"content": "ok"}}]}
        assert client._working_url is not None

    async def test_caches_working_url(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http

        await client.chat_completion([{"role": "user", "content": "hi"}])
        assert client._working_url == "https://api.example.com/v1/chat/completions"

    async def test_404_tries_next_url(self, client):
        resp_404 = MagicMock()
        resp_404.status_code = 404

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {"choices": []}
        resp_ok.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[resp_404, resp_ok])
        client._client = mock_http

        result = await client.chat_completion([{"role": "user", "content": "hi"}])
        assert result == {"choices": []}
        assert client._working_url == "https://api.example.com/chat/completions"

    async def test_401_raises_immediately(self, client):
        resp_401 = MagicMock()
        resp_401.status_code = 401

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=resp_401)
        client._client = mock_http

        with pytest.raises(ExternalServiceException, match="Authentication failure"):
            await client.chat_completion([{"role": "user", "content": "hi"}])

    async def test_all_urls_exhausted_raises(self, client):
        resp_404 = MagicMock()
        resp_404.status_code = 404

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=resp_404)
        client._client = mock_http

        with pytest.raises(ExternalServiceException, match="exhausted"):
            await client.chat_completion([{"role": "user", "content": "hi"}])

    async def test_request_error_raises_after_retries(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("fail"))
        client._client = mock_http

        with pytest.raises(ExternalServiceException, match="exhausted"):
            await client.chat_completion([{"role": "user", "content": "hi"}])

    async def test_close(self, client):
        mock_http = AsyncMock()
        client._client = mock_http
        await client.close()
        mock_http.aclose.assert_awaited_once()
        assert client._client is None


# -- build_client_from_env ------------------------------------------------------


@patch("controlnexus.core.transport.load_dotenv")
class TestBuildClientFromEnv:
    @patch.dict(
        os.environ,
        {
            "ICA_API_KEY": "ica-key",
            "ICA_BASE_URL": "https://ica.example.com",
            "ICA_MODEL_ID": "ica-model",
        },
        clear=True,
    )
    def test_ica_provider(self, _mock_dotenv):
        c = build_client_from_env()
        assert c is not None
        assert c.api_key == "ica-key"
        assert c.base_url == "https://ica.example.com"
        assert c.model == "ica-model"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "oai-key"}, clear=True)
    def test_openai_provider(self, _mock_dotenv):
        c = build_client_from_env()
        assert c is not None
        assert c.api_key == "oai-key"
        assert c.model == "gpt-4o"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ant-key"}, clear=True)
    def test_anthropic_provider(self, _mock_dotenv):
        c = build_client_from_env()
        assert c is not None
        assert c.api_key == "ant-key"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_credentials_returns_none(self, _mock_dotenv):
        c = build_client_from_env()
        assert c is None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=True)
    def test_model_override(self, _mock_dotenv):
        c = build_client_from_env(model_override="custom-model")
        assert c is not None
        assert c.model == "custom-model"

    @patch.dict(
        os.environ,
        {
            "ICA_API_KEY": "ica",
            "ICA_BASE_URL": "https://ica.example.com",
            "ICA_MODEL_ID": "m",
            "OPENAI_API_KEY": "oai",
        },
        clear=True,
    )
    def test_ica_takes_priority_over_openai(self, _mock_dotenv):
        c = build_client_from_env()
        assert c is not None
        assert c.api_key == "ica"
