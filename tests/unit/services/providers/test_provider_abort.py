"""Unit tests for provider abort() mechanisms and timeout configuration."""

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.services.providers import openai_compatible_provider as ocp_module
from ollama_llm_bench.backend.services.providers import openai_embedding_provider as oep_module
from ollama_llm_bench.backend.services.providers.openai_compatible_provider import (
    _HTTP_READ_TIMEOUT_S,
    OpenAICompatibleProvider,
)
from ollama_llm_bench.backend.services.providers.openai_embedding_provider import OpenAIEmbeddingProvider

# ---------------------------------------------------------------------------
# OpenAICompatibleProvider — abort + timeout
# ---------------------------------------------------------------------------


def _make_openai_provider(mocker: MockerFixture) -> tuple[OpenAICompatibleProvider, object]:
    mock_cls = mocker.patch(f"{ocp_module.__name__}.openai.OpenAI")
    mock_client = mock_cls.return_value
    provider = OpenAICompatibleProvider(
        provider_id="test",
        provider_type="openai_compatible",
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        name_parser=ModelNameParser(),
    )
    return provider, mock_client


def test_openai_compatible_read_timeout_is_120() -> None:
    assert _HTTP_READ_TIMEOUT_S == 120.0


def test_openai_compatible_abort_closes_client(mocker: MockerFixture) -> None:
    provider, mock_client = _make_openai_provider(mocker)

    provider.abort()

    mock_client.close.assert_called_once()  # type: ignore[attr-defined]


def test_openai_compatible_abort_does_not_raise_on_close_error(mocker: MockerFixture) -> None:
    provider, mock_client = _make_openai_provider(mocker)
    mock_client.close.side_effect = RuntimeError("transport gone")  # type: ignore[attr-defined]

    # abort() must swallow the exception
    provider.abort()


# ---------------------------------------------------------------------------
# OpenAIEmbeddingProvider — abort
# ---------------------------------------------------------------------------


def test_embedding_provider_abort_closes_client(mocker: MockerFixture) -> None:
    mock_cls = mocker.patch(f"{oep_module.__name__}.openai.OpenAI")
    mock_client = mock_cls.return_value
    provider = OpenAIEmbeddingProvider(
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        model="bge-m3",
    )

    provider.abort()

    mock_client.close.assert_called_once()


def test_embedding_provider_abort_does_not_raise_on_close_error(mocker: MockerFixture) -> None:
    mock_cls = mocker.patch(f"{oep_module.__name__}.openai.OpenAI")
    mock_client = mock_cls.return_value
    mock_client.close.side_effect = RuntimeError("transport gone")
    provider = OpenAIEmbeddingProvider(
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        model="bge-m3",
    )

    # abort() must swallow the exception
    provider.abort()
