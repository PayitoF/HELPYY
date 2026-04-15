"""Unit tests for LLM providers — Ollama and Bedrock, fully mocked."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.llm.provider import ToolDefinition, ToolCallResult
from backend.llm.ollama_provider import OllamaProvider
from backend.llm.bedrock_provider import BedrockProvider

_FAKE_REQUEST = httpx.Request("POST", "http://localhost:11434/api/chat")


def _ok_response(body: dict) -> httpx.Response:
    """Create an httpx.Response(200) that supports raise_for_status()."""
    return httpx.Response(200, json=body, request=_FAKE_REQUEST)


def _err_response(status: int = 500) -> httpx.Response:
    return httpx.Response(status, text="error", request=_FAKE_REQUEST)


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

SAMPLE_MESSAGES = [
    {"role": "system", "content": "Eres un asistente."},
    {"role": "user", "content": "Hola, ¿cómo estás?"},
]

SAMPLE_TOOLS = [
    ToolDefinition(
        name="check_score",
        description="Check credit score for a user",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
            },
            "required": ["user_id"],
        },
    ),
]


# =======================================================================
# OLLAMA PROVIDER
# =======================================================================


class TestOllamaGenerate:
    """Test OllamaProvider.generate()."""

    @pytest.mark.asyncio
    async def test_returns_content(self):
        provider = OllamaProvider()
        mock_response = _ok_response({
            "message": {"role": "assistant", "content": "¡Hola! Estoy bien."},
            "done": True,
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await provider.generate(SAMPLE_MESSAGES)
        assert result == "¡Hola! Estoy bien."

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        provider = OllamaProvider()
        mock_response = _ok_response(
            {"message": {"role": "assistant", "content": "ok"}, "done": True},
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await provider.generate(SAMPLE_MESSAGES, temperature=0.5)
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["model"] == provider.model
            assert payload["stream"] is False
            assert payload["options"]["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_includes_tools_in_payload(self):
        provider = OllamaProvider()
        mock_response = _ok_response(
            {"message": {"role": "assistant", "content": "ok"}, "done": True},
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await provider.generate(SAMPLE_MESSAGES, tools=SAMPLE_TOOLS)
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert "tools" in payload
            assert payload["tools"][0]["function"]["name"] == "check_score"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        provider = OllamaProvider()
        ok = _ok_response(
            {"message": {"role": "assistant", "content": "ok"}, "done": True},
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.HTTPStatusError("err", request=_FAKE_REQUEST, response=_err_response())
            return ok

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=side_effect):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider.generate(SAMPLE_MESSAGES)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        provider = OllamaProvider()

        async def always_fail(*args, **kwargs):
            raise httpx.HTTPStatusError("err", request=_FAKE_REQUEST, response=_err_response())

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=always_fail):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ConnectionError, match="failed after 3 attempts"):
                    await provider.generate(SAMPLE_MESSAGES)


class TestOllamaStream:
    """Test OllamaProvider.generate_stream()."""

    @pytest.mark.asyncio
    async def test_yields_tokens(self):
        provider = OllamaProvider()
        lines = [
            json.dumps({"message": {"content": "Hola"}, "done": False}),
            json.dumps({"message": {"content": " mundo"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()

        async def fake_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = fake_lines

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
            tokens = []
            async for t in provider.generate_stream(SAMPLE_MESSAGES):
                tokens.append(t)

        assert tokens == ["Hola", " mundo"]


class TestOllamaToolCalling:
    """Test OllamaProvider.generate_with_tools()."""

    @pytest.mark.asyncio
    async def test_native_tool_call(self):
        """When Ollama returns tool_calls natively."""
        provider = OllamaProvider()
        mock_response = _ok_response({
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "check_score",
                            "arguments": {"user_id": "u123"},
                        }
                    }
                ],
            },
            "done": True,
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await provider.generate_with_tools(SAMPLE_MESSAGES, SAMPLE_TOOLS)
        assert isinstance(result, ToolCallResult)
        assert result.tool_name == "check_score"
        assert result.arguments == {"user_id": "u123"}

    @pytest.mark.asyncio
    async def test_text_fallback_tool_parse(self):
        """When the model embeds a tool call in text."""
        provider = OllamaProvider()
        text_with_json = 'I will check the score. {"name": "check_score", "arguments": {"user_id": "u456"}}'
        mock_response = _ok_response({
            "message": {"role": "assistant", "content": text_with_json},
            "done": True,
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await provider.generate_with_tools(SAMPLE_MESSAGES, SAMPLE_TOOLS)
        assert isinstance(result, ToolCallResult)
        assert result.tool_name == "check_score"

    @pytest.mark.asyncio
    async def test_no_tool_call_returns_text(self):
        """When the model just responds with text."""
        provider = OllamaProvider()
        mock_response = _ok_response({
            "message": {"role": "assistant", "content": "No puedo ayudarte con eso."},
            "done": True,
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await provider.generate_with_tools(SAMPLE_MESSAGES, SAMPLE_TOOLS)
        assert isinstance(result, str)
        assert "No puedo" in result


# =======================================================================
# BEDROCK PROVIDER
# =======================================================================


class TestBedrockGenerate:
    """Test BedrockProvider.generate()."""

    @pytest.mark.asyncio
    async def test_returns_content(self):
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse.return_value = {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "¡Hola!"}],
                    }
                }
            }
            provider = BedrockProvider()
            result = await provider.generate(SAMPLE_MESSAGES)
        assert result == "¡Hola!"

    @pytest.mark.asyncio
    async def test_sends_system_separately(self):
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse.return_value = {
                "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}
            }
            provider = BedrockProvider()
            await provider.generate(SAMPLE_MESSAGES, temperature=0.3)

            call_kwargs = mock_client.converse.call_args.kwargs
            assert "system" in call_kwargs
            assert call_kwargs["system"][0]["text"] == "Eres un asistente."
            assert call_kwargs["inferenceConfig"]["temperature"] == 0.3
            # Only the user message should be in messages (system extracted)
            assert len(call_kwargs["messages"]) == 1
            assert call_kwargs["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_retries_on_throttle(self):
        from botocore.exceptions import ClientError

        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            call_count = 0

            def side_effect(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ClientError(
                        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                        "Converse",
                    )
                return {
                    "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}
                }

            mock_client.converse.side_effect = side_effect
            provider = BedrockProvider()

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider.generate(SAMPLE_MESSAGES)

        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_non_throttle_errors(self):
        from botocore.exceptions import ClientError

        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse.side_effect = ClientError(
                {"Error": {"Code": "ValidationException", "Message": "bad request"}},
                "Converse",
            )
            provider = BedrockProvider()
            with pytest.raises(ClientError):
                await provider.generate(SAMPLE_MESSAGES)


class TestBedrockStream:
    """Test BedrockProvider.generate_stream()."""

    @pytest.mark.asyncio
    async def test_yields_tokens(self):
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse_stream.return_value = {
                "stream": [
                    {"contentBlockDelta": {"delta": {"text": "Hola"}}},
                    {"contentBlockDelta": {"delta": {"text": " mundo"}}},
                    {"messageStop": {"stopReason": "end_turn"}},
                ]
            }
            provider = BedrockProvider()
            tokens = []
            async for t in provider.generate_stream(SAMPLE_MESSAGES):
                tokens.append(t)

        assert tokens == ["Hola", " mundo"]


class TestBedrockToolCalling:
    """Test BedrockProvider.generate_with_tools()."""

    @pytest.mark.asyncio
    async def test_tool_use_response(self):
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse.return_value = {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "t1",
                                    "name": "check_score",
                                    "input": {"user_id": "u789"},
                                }
                            }
                        ],
                    }
                }
            }
            provider = BedrockProvider()
            result = await provider.generate_with_tools(SAMPLE_MESSAGES, SAMPLE_TOOLS)

        assert isinstance(result, ToolCallResult)
        assert result.tool_name == "check_score"
        assert result.arguments == {"user_id": "u789"}

    @pytest.mark.asyncio
    async def test_text_response_when_no_tool(self):
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse.return_value = {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "No necesito herramientas."}],
                    }
                }
            }
            provider = BedrockProvider()
            result = await provider.generate_with_tools(SAMPLE_MESSAGES, SAMPLE_TOOLS)

        assert isinstance(result, str)
        assert "No necesito" in result

    @pytest.mark.asyncio
    async def test_tools_sent_in_payload(self):
        with patch("boto3.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.converse.return_value = {
                "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}
            }
            provider = BedrockProvider()
            await provider.generate_with_tools(SAMPLE_MESSAGES, SAMPLE_TOOLS)

            call_kwargs = mock_client.converse.call_args.kwargs
            assert "toolConfig" in call_kwargs
            tool_spec = call_kwargs["toolConfig"]["tools"][0]["toolSpec"]
            assert tool_spec["name"] == "check_score"


# =======================================================================
# CONFIG FACTORY
# =======================================================================


class TestConfig:
    """Test get_llm_provider factory."""

    def test_local_returns_ollama(self):
        with patch.dict("os.environ", {"LLM_PROVIDER": "local"}):
            from backend.llm.config import get_llm_provider

            p = get_llm_provider()
            assert isinstance(p, OllamaProvider)

    def test_bedrock_returns_bedrock(self):
        with patch("boto3.Session"):
            with patch.dict("os.environ", {"LLM_PROVIDER": "bedrock"}):
                from backend.llm.config import get_llm_provider

                p = get_llm_provider()
                assert isinstance(p, BedrockProvider)

    def test_invalid_raises(self):
        with patch.dict("os.environ", {"LLM_PROVIDER": "gpt"}):
            from backend.llm.config import get_llm_provider

            with pytest.raises(ValueError, match="gpt"):
                get_llm_provider()
