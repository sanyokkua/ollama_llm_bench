"""Architecture test: ``backend/provider_openai_compatible/`` imports no Qt, no
``asyncio``, and no sibling provider adapter, and no provider SDK exception type
ever escapes any public method (STORY-018).

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``
Definition of Done ("An architecture test confirms ``backend/provider_openai_compatible/``
imports no Qt, no ``asyncio``, and no sibling provider adapter, and that no provider
SDK exception type escapes any public method"); ``docs/v3_specification/
16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §11 (concurrency stack: stdlib
+ Qt only). Mirrors ``tests/architecture/test_provider_registry_module.py``
(STORY-017) for the import-boundary AST checks, and adds the genuinely new
DoD-mandated proof: a dynamic, wire-stub-backed sweep of ``OpenAICompatibleClient``'s
public surface against every ``openai``/``httpx`` failure category, asserting the
raised exception is always an ``AppError`` (this project's own error-taxonomy root,
see ``backend/errors/__init__.py``) and never a raw ``openai.*``/``httpx.*`` type.
This overlaps somewhat with ``test_exception_translation.py``'s AC-5 coverage by
design — that file proves the *mapping table*; this file is the DoD's own structural
proof that *no public method* lets an SDK exception leak, driven by a compact,
non-duplicated case set built on the same wire-stub fixture helpers.
"""

import ast
import inspect
from pathlib import Path

import httpx
import openai
import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend import errors as errors_module, provider_openai_compatible
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.collaborators import (
    OpenAICompatibleClientCollaborators,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import (
    FakeClock,
    FakeEventBus,
    make_chat_request,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PACKAGE_ROOT = Path(inspect.getfile(provider_openai_compatible)).parent
_FORBIDDEN_IMPORT_ROOTS = ("PySide6", "asyncio", "anyio", "qasync")
_FORBIDDEN_SIBLING_ADAPTER_MODULES = (
    "ollama_llm_bench.backend.provider_anthropic",
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
    """Proves: STORY-018-AC-5

    Sanity guard for the AST walker itself: ``backend/provider_openai_compatible/``
    has at least one discoverable ``.py`` source file, so the parametrized
    checks below are not vacuously true.
    """
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_imports_no_qt_or_asyncio(source_file: Path) -> None:
    """Proves: STORY-018-AC-5

    Every source file under ``backend/provider_openai_compatible/``
    (including its colocated tests) imports no ``PySide6``, no ``asyncio``,
    no ``anyio``, and no ``qasync`` — the adapter stays Qt-free and
    asyncio-free (D-R-01).
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
    """Proves: STORY-018-AC-5

    Every source file under ``backend/provider_openai_compatible/`` defines
    no ``async def`` function (DD-43) — ordinary synchronous, blocking
    Python with no event-loop or coroutine scheduling of any kind.
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_module_imports_no_sibling_provider_adapter(source_file: Path) -> None:
    """Proves: STORY-018-AC-5

    Every source file under ``backend/provider_openai_compatible/`` imports
    no sibling provider-adapter package (``backend.provider_anthropic``/
    ``backend.provider_gemini``) — provider adapters never import one
    another (import-linter "Provider adapters are independent"). Both
    sibling packages do not exist yet (STORY-019/020 are unbuilt), so this
    check currently confirms the absence of any such import, not a failure
    guarded by their presence.
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


def _make_client(*, base_url: str, clock: FakeClock) -> OpenAICompatibleClient:
    """Build a real ``OpenAICompatibleClient`` against ``base_url``.

    Shared by every dynamic no-raw-SDK-exception test below, whether
    ``base_url`` points at the wire stub or at an always-refused port.
    """
    event_bus = FakeEventBus()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    collaborators = OpenAICompatibleClientCollaborators(
        clock=clock, event_bus=event_bus, inference_activity_store=gate
    )
    config = make_provider_config(base_url=base_url)
    settings = OpenAICompatibleClientSettings(embedding_model="embed-model")
    return OpenAICompatibleClient(
        config=config, resolved_api_key="", collaborators=collaborators, settings=settings
    )


_SDK_FAILURE_STATUSES: tuple[int, ...] = (401, 400, 404, 429, 500)


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_chat_never_lets_a_raw_sdk_exception_escape(httpserver: HTTPServer, status: int) -> None:
    """Proves: STORY-018-AC-5

    Given the wire stub returns each category of ``openai``/``httpx``-raising
    HTTP failure, when ``chat`` is called, then the raised exception is
    always an instance of this project's own ``AppError`` taxonomy root and
    never an ``openai.*``/``httpx.*`` type — the DoD's structural
    no-raw-SDK-exception proof, driven dynamically rather than by static
    source inspection.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_json(
        {"error": {"message": "boom", "code": "err"}}, status=status
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
    assert not isinstance(raised, openai.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


def test_chat_connection_refused_never_lets_a_raw_httpx_exception_escape() -> None:
    """Proves: STORY-018-AC-5

    Given an untyped ``httpx`` transport failure (connection refused, no
    server listening at all), when ``chat`` is called, then the raised
    exception is an ``AppError``, never a raw ``httpx``/``openai`` type.
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
    assert not isinstance(raised, openai.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_embed_never_lets_a_raw_sdk_exception_escape(httpserver: HTTPServer, status: int) -> None:
    """Proves: STORY-018-AC-5

    Given the wire stub returns each category of ``openai``-raising HTTP
    failure on ``/v1/embeddings``, when ``embed`` is called, then the raised
    exception is always an ``AppError``, never a raw ``openai``/``httpx``
    type.
    """
    # Arrange
    httpserver.expect_request("/embeddings", method="POST").respond_with_json(
        {"error": {"message": "boom", "code": "err"}}, status=status
    )
    clock = FakeClock()
    client = _make_client(base_url=httpserver.url_for("/"), clock=clock)

    # Act
    with pytest.raises(errors_module.AppError) as exc_info:
        client.embed("hello")

    # Assert
    raised = exc_info.value
    assert not isinstance(raised, openai.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_list_models_never_lets_a_raw_sdk_exception_escape(
    httpserver: HTTPServer, status: int
) -> None:
    """Proves: STORY-018-AC-5

    Given the wire stub returns each category of ``openai``-raising HTTP
    failure on ``/v1/models``, when ``list_models`` is called, then the
    raised exception is always an ``AppError``, never a raw
    ``openai``/``httpx`` type.
    """
    # Arrange
    httpserver.expect_request("/models", method="GET").respond_with_json(
        {"error": {"message": "boom", "code": "err"}}, status=status
    )
    clock = FakeClock()
    client = _make_client(base_url=httpserver.url_for("/"), clock=clock)

    # Act
    with pytest.raises(errors_module.AppError) as exc_info:
        client.list_models()

    # Assert
    raised = exc_info.value
    assert not isinstance(raised, openai.APIError)
    assert not isinstance(raised, httpx.HTTPError)
    assert type(raised).__module__.startswith("ollama_llm_bench")


@pytest.mark.parametrize("status", _SDK_FAILURE_STATUSES)
def test_probe_health_never_raises_even_when_discovery_sdk_call_fails(
    httpserver: HTTPServer, status: int
) -> None:
    """Proves: STORY-018-AC-7

    Given the wire stub's discovery call fails with each SDK-raising HTTP
    status, when ``probe_health`` is called, then it never raises at all
    (not even an ``AppError``) — the never-raises contract holds regardless
    of which SDK exception category the discovery call triggers internally.
    """
    # Arrange
    httpserver.expect_request("/", method="GET").respond_with_json({"ok": True})
    httpserver.expect_request("/models", method="GET").respond_with_json(
        {"error": {"message": "boom", "code": "err"}}, status=status
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
    """Proves: STORY-018-AC-9

    Given the wire stub's chat call fails with each SDK-raising HTTP status,
    when ``test_inference`` is called, then it never raises at all — the
    never-raises contract holds regardless of which SDK exception category
    the underlying ``chat`` call translates.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_json(
        {"error": {"message": "boom", "code": "err"}}, status=status
    )
    clock = FakeClock()
    client = _make_client(base_url=httpserver.url_for("/"), clock=clock)

    # Act
    result = client.test_inference("test-model")

    # Assert
    assert result.last_error is not None
