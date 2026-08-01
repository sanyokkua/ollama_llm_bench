"""Tests proving STORY-021-AC-1 and STORY-021-AC-2: the corrected ``LLMClient`` chat surface.

Source of truth: ``docs/stories/story-021-llmclient-chat-cancellation-token-parameter.md``;
``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client``;
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken``;
``docs/adr/0005-llmclient-chat-takes-mandatory-cancellation-token.md``.

STORY-021-AC-1 is proven by introspecting ``LLMClient.chat``/``chat_stream`` directly with
``inspect.signature`` — no subprocess needed, matching the project's existing Protocol-shape
test pattern (see ``backend/events/tests/test_protocols.py``).

STORY-021-AC-2 is proven with a real ``mypy --strict`` fixture pair: a pre-correction stub
(``chat``/``chat_stream`` with no ``token`` parameter — the shape STORY-017 originally shipped)
and a corrected stub (keyword-only ``token: CancellationToken``), each written to ``tmp_path``
and checked against the actual, current ``LLMClient`` Protocol via a real ``mypy`` subprocess
invocation. This is a genuine static-type assertion, not a simulation of one — it fails the
moment the Protocol regresses to accept a tokenless client.
"""

import inspect
from pathlib import Path
import subprocess
import sys

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_registry.protocols import LLMClient

_REPO_ROOT = Path(__file__).resolve().parents[5]

_CONFORMING_STUB = """\
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    ModelName,
    ProviderHealth,
)
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, LLMClient


class ConformingClient:
    def list_models(self) -> tuple[ModelName, ...]:
        return ()

    def probe_health(self) -> ProviderHealth:
        raise NotImplementedError

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        raise NotImplementedError

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        raise NotImplementedError

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        raise NotImplementedError

    def embed(self, text: str) -> tuple[float, ...]:
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        return False

    def supports_reasoning_effort(self) -> bool:
        return False

    def supports_thinking(self) -> bool:
        return False

    def supports_embedding(self) -> bool:
        return False

    def supports_discovery(self) -> bool:
        return False

    def close(self) -> None:
        return None


def accepts_llm_client(client: LLMClient) -> None:
    pass


accepts_llm_client(ConformingClient())
"""

_PRE_CORRECTION_STUB = '''\
from ollama_llm_bench.backend.domain import (
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    ModelName,
    ProviderHealth,
)
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, LLMClient


class PreCorrectionClient:
    """A pre-STORY-021 ``LLMClient`` shape: ``chat``/``chat_stream`` take no token."""

    def list_models(self) -> tuple[ModelName, ...]:
        return ()

    def probe_health(self) -> ProviderHealth:
        raise NotImplementedError

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        raise NotImplementedError

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def chat_stream(self, request: ChatRequest) -> ChatStream:
        raise NotImplementedError

    def embed(self, text: str) -> tuple[float, ...]:
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        return False

    def supports_reasoning_effort(self) -> bool:
        return False

    def supports_thinking(self) -> bool:
        return False

    def close(self) -> None:
        return None


def accepts_llm_client(client: LLMClient) -> None:
    pass


accepts_llm_client(PreCorrectionClient())
'''


def _run_mypy_strict(target: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the project's own pinned ``mypy --strict`` against a single fixture file.

    Runs ``mypy`` as a module of the *current* interpreter (``sys.executable``)
    rather than shelling out to ``uv run`` — this is the same interpreter and
    environment pytest itself is running under, so it always resolves the
    project's pinned ``mypy`` with no dependency on ``uv`` being importable as
    a module inside the active virtualenv.
    """
    return subprocess.run(  # noqa: S603  # fixed argv, no shell, trusted fixture path
        [sys.executable, "-m", "mypy", "--strict", str(target)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
        timeout=120,
    )


def test_chat_methods_require_keyword_only_cancellation_token() -> None:
    """Proves: STORY-021-AC-1

    Given the canonical ``LLMClient`` Protocol on
    ``backend/provider_registry/protocols.py``, when its ``chat`` and
    ``chat_stream`` signatures are inspected, then each declares a
    keyword-only parameter ``token`` annotated ``CancellationToken`` with no
    default value, and ``request: ChatRequest`` remains the sole positional
    parameter.
    """
    # Arrange / Act
    chat_signature = inspect.signature(LLMClient.chat)
    chat_stream_signature = inspect.signature(LLMClient.chat_stream)

    # Assert
    assert list(chat_signature.parameters) == ["self", "request", "token"]
    assert chat_signature.parameters["token"].kind == inspect.Parameter.KEYWORD_ONLY
    assert chat_signature.parameters["token"].default is inspect.Parameter.empty
    assert chat_signature.parameters["token"].annotation is CancellationToken
    assert chat_signature.parameters["request"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert list(chat_stream_signature.parameters) == ["self", "request", "token"]
    assert chat_stream_signature.parameters["token"].kind == inspect.Parameter.KEYWORD_ONLY
    assert chat_stream_signature.parameters["token"].default is inspect.Parameter.empty
    assert chat_stream_signature.parameters["token"].annotation is CancellationToken


def test_missing_token_fails_protocol_and_present_token_satisfies(tmp_path: Path) -> None:
    """Proves: STORY-021-AC-2

    Given a class whose ``chat``/``chat_stream`` omit the ``token`` parameter
    (the pre-correction signature), when it is type-checked against the
    corrected ``LLMClient`` Protocol under ``mypy --strict``, then it is
    rejected as not structurally satisfying the Protocol; and given a class
    whose ``chat``/``chat_stream`` include the keyword-only
    ``token: CancellationToken``, then it is accepted.
    """
    # Arrange
    conforming_file = tmp_path / "conforming_client_probe.py"
    conforming_file.write_text(_CONFORMING_STUB, encoding="utf-8")
    pre_correction_file = tmp_path / "pre_correction_client_probe.py"
    pre_correction_file.write_text(_PRE_CORRECTION_STUB, encoding="utf-8")

    # Act
    conforming_result = _run_mypy_strict(conforming_file)
    pre_correction_result = _run_mypy_strict(pre_correction_file)

    # Assert
    assert conforming_result.returncode == 0, conforming_result.stdout + conforming_result.stderr
    assert pre_correction_result.returncode != 0
    assert "arg-type" in pre_correction_result.stdout
    assert "chat" in pre_correction_result.stdout
