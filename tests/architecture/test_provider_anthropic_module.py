"""Architecture test: ``backend/provider_anthropic/`` imports no Qt, no
``asyncio``, and no sibling provider adapter, and no ``anthropic``/``httpx``
exception type ever escapes any public method (STORY-019).

Source of truth: ``docs/stories/story-019-anthropic-provider-adapter.md``
Definition of Done ("An architecture test confirms ``backend/provider_anthropic/``
imports no Qt, no ``asyncio``, and no sibling provider adapter, and that no
``anthropic`` SDK exception type escapes any public method");
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§11 (concurrency stack: stdlib + Qt only). Mirrors
``tests/architecture/test_provider_openai_compatible_module.py`` (STORY-018)
for the import-boundary AST checks, and adds the genuinely new DoD-mandated
proof: a dynamic, wire-stub-backed sweep of ``AnthropicClient``'s public
surface against every ``anthropic``/``httpx`` failure category, asserting the
raised exception is always an ``AppError`` (this project's own error-taxonomy
root, see ``backend/errors/__init__.py``) and never a raw
``anthropic.*``/``httpx.*`` type. This overlaps somewhat with
``test_exception_translation.py``'s AC-4 coverage by design — that file
proves the *mapping table*; this file is the DoD's own structural proof that
*no public method* lets an SDK exception leak, driven by a compact,
non-duplicated case set built on the same wire-stub fixture helpers.
"""

import ast
import inspect
from pathlib import Path

import anthropic
import httpx
import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend import errors as errors_module, provider_anthropic
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic._internal.collaborators import (
    AnthropicClientCollaborators,
)
from ollama_llm_bench.backend.provider_anthropic.models import AnthropicClientSettings
from ollama_llm_bench.backend.provider_anthropic.tests.conftest import (
    FakeClock,
    FakeEventBus,
    make_chat_request,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PACKAGE_ROOT = Path(inspect.getfile(provider_anthropic)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")
_FORBIDDEN_SIBLING_ADAPTER_MODULES = (
    "ollama_llm_bench.backend.provider_openai_compatible",
    "ollama_llm_bench.backend.provider_gemini",
)


def _iter_source_files() -> list[Path]:
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_PACKAGE_ROOT)) for path in files]
    return files, ids


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_at_least_one_source_file_discovered() -> None:
    """Proves: STORY-019-AC-4

    Sanity guard for the AST walker itself: ``backend/provider_anthropic/``
    has at least one discoverable ``.py`` source file, so the parametrized
    checks below are not vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-019-AC-4

    Every source file under ``backend/provider_anthropic/`` (including its
    colocated tests) imports no ``PySide6``, no ``asyncio``, no ``anyio``,
    and no ``qasync`` — the adapter stays Qt-free and asyncio-free (D-R-01).
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    # Assert
    assert imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_defines_no_async_function(source_file: Path) -> None:
    """Proves: STORY-019-AC-4

    Every source file under ``backend/provider_anthropic/`` defines no
    ``async def`` function (DD-43) — ordinary synchronous, blocking Python
    with no event-loop or coroutine scheduling of any kind.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_imports_no_sibling_provider_adapter(source_file: Path) -> None:
    """Proves: STORY-019-AC-4

    Every source file under ``backend/provider_anthropic/`` imports no
    sibling provider-adapter package (``backend.provider_openai_compatible``/
    ``backend.provider_gemini``) — provider adapters never import one
    another (import-linter "Provider adapters are independent").
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported_modules = _imported_module_names(tree)

    # Assert
    assert not any(
        imported.startswith(forbidden)
        for imported in imported_modules
        for forbidden in _FORBIDDEN_SIBLING_ADAPTER_MODULES
    )


def _make_client(*, base_url: str, clock: FakeClock) -> AnthropicClient:
    """Build a real ``AnthropicClient`` against ``base_url``.

    Shared by every dynamic no-raw-SDK-exception test below, whether
    ``base_url`` points at the wire stub or at an always-refused port.
    """
    event_bus = FakeEventBus()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    collaborators = AnthropicClientCollaborators(
        clock=clock, event_bus=event_bus, inference_activity_store=gate
    )
    config = make_provider_config(base_url=base_url)
    settings = AnthropicClientSettings()
    return AnthropicClient(
        config=config,
        resolved_api_key="sk-ant-test-key",
        collaborators=collaborators,
        settings=settings,
    )


_SDK_FAILURE_STATUSES: tuple[int, ...] = (401, 400, 404, 429, 500)


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_chat_never_lets_a_raw_sdk_exception_escape(httpserver: HTTPServer, status: int) -> None:
    """Proves: STORY-019-AC-4

    Given the wire stub returns each category of ``anthropic``/``httpx``-raising
    HTTP failure, when ``chat`` is called, then the raised exception is
    always an instance of this project's own ``AppError`` taxonomy root and
    never an ``anthropic.*``/``httpx.*`` type — the DoD's structural
    no-raw-SDK-exception proof, driven dynamically rather than by static
    source inspection.
    """
    # Arrange
    httpserver.expect_request("/v1/messages", method="POST").respond_with_json(
        {"type": "error", "error": {"type": "api_error", "message": "boom"}}, status=status
    )
    clock = FakeClock()
    client = _make_client(base_url=httpserver.url_for("/"), clock=clock)
    request = make_chat_request()
    token = CancellationToken(clock=clock)

    # Act
    with pytest.raises(errors_module.AppError) as exc_info:
        client.chat(request, token=token)

    # Assert
    raised = exc_info.value
    assert not isinstance(raised, anthropic.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


def test_chat_connection_refused_never_lets_a_raw_httpx_exception_escape() -> None:
    """Proves: STORY-019-AC-4

    Given an untyped ``httpx`` transport failure (connection refused, no
    server listening at all), when ``chat`` is called, then the raised
    exception is an ``AppError``, never a raw ``httpx``/``anthropic`` type.
    """
    # Arrange: port 1 is a reserved, always-refused port on every OS.
    clock = FakeClock()
    client = _make_client(base_url="http://127.0.0.1:1/", clock=clock)
    request = make_chat_request()
    token = CancellationToken(clock=clock)

    # Act
    with pytest.raises(errors_module.AppError) as exc_info:
        client.chat(request, token=token)

    # Assert
    raised = exc_info.value
    assert not isinstance(raised, anthropic.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


def test_embed_never_lets_a_raw_sdk_exception_escape() -> None:
    """Proves: STORY-019-AC-4

    Given the Anthropic client (which exposes no embeddings endpoint), when
    ``embed`` is called, then the raised exception is always an
    ``AppError``, never a raw ``anthropic``/``httpx`` type — and no network
    call is issued at all.
    """
    # Arrange
    clock = FakeClock()
    client = _make_client(base_url="http://127.0.0.1:1/", clock=clock)

    # Act
    with pytest.raises(errors_module.AppError) as exc_info:
        client.embed("hello")

    # Assert
    raised = exc_info.value
    assert not isinstance(raised, anthropic.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


def test_list_models_never_lets_a_raw_sdk_exception_escape() -> None:
    """Proves: STORY-019-AC-4

    Given the Anthropic client (which exposes no models-list endpoint), when
    ``list_models`` is called, then the raised exception is always an
    ``AppError``, never a raw ``anthropic``/``httpx`` type.
    """
    # Arrange
    clock = FakeClock()
    client = _make_client(base_url="http://127.0.0.1:1/", clock=clock)

    # Act
    with pytest.raises(errors_module.AppError) as exc_info:
        client.list_models()

    # Assert
    raised = exc_info.value
    assert not isinstance(raised, anthropic.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_probe_health_never_raises_even_when_reachability_call_fails(
    httpserver: HTTPServer, status: int
) -> None:
    """Proves: STORY-019-AC-6

    Given the wire stub's reachability call fails with each SDK-raising
    HTTP status, when ``probe_health`` is called, then it never raises at
    all (not even an ``AppError``) — the never-raises contract holds
    regardless of which HTTP status the reachability handshake receives. A
    4xx/5xx response still proves reachability (§6.8.1) — only a
    connection-level failure means unreachable.
    """
    # Arrange
    httpserver.expect_request("/", method="GET").respond_with_json(
        {"error": {"message": "boom"}}, status=status
    )
    clock = FakeClock()
    client = _make_client(base_url=httpserver.url_for("/"), clock=clock)

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.model_count is None


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_test_inference_never_raises_even_when_chat_sdk_call_fails(
    httpserver: HTTPServer, status: int
) -> None:
    """Proves: STORY-019-AC-7

    Given the wire stub's chat call fails with each SDK-raising HTTP
    status, when ``test_inference`` is called, then it never raises at all
    — the never-raises contract holds regardless of which SDK exception
    category the underlying ``chat`` call translates.
    """
    # Arrange
    httpserver.expect_request("/v1/messages", method="POST").respond_with_json(
        {"type": "error", "error": {"type": "api_error", "message": "boom"}}, status=status
    )
    clock = FakeClock()
    client = _make_client(base_url=httpserver.url_for("/"), clock=clock)

    # Act
    result = client.test_inference("test-model")

    # Assert
    assert result.last_error is not None
