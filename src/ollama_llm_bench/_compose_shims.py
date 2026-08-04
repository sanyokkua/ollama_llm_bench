"""Private shim/stub classes and helpers used only by ``compose.py``'s ``build_app`` (STORY-077,
ADR-0010). None of this is wiring -- it is small structural adapters (an ``LLMClient``
stand-in, a filename-composition bridge, inert stub Protocol implementations for gateways
with no real backend target yet) that ``build_app`` constructs and passes to a factory. It
lives in its own private module, separate from ``compose.py``, purely to keep the composition
root itself within its line budget (`tests/architecture/test_compose_line_budget.py`) --
``build_app`` remains the sole place concrete implementations are wired together.
"""

from collections.abc import Callable
import re

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.csv_export import ExportKind, compose_export_filename
from ollama_llm_bench.backend.domain import (  # fmt: skip
    BenchmarkRun,
    ChatRequest,
    ChatResponse,
    InferenceTestOutcome,
    InferenceTestResult,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    RunId,
    RunStartRequest,
)
from ollama_llm_bench.backend.errors import EmbeddingUnavailableError
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.provider_registry import ChatStream
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.ui.new_benchmark.models import ValidationEntry

_EXPORT_KIND_MAP: dict[str, ExportKind] = {"Summary": ExportKind.SUMMARY, "Details": ExportKind.DETAILS}  # fmt: skip


def _sanitise_run_name(*, run_name: str, run_id: RunId) -> str:
    """Copy of ``csv_export._internal.filename.sanitise_run_name`` (import-linter forbids reaching it)."""  # fmt: skip
    replaced = re.sub(r"[^A-Za-z0-9._-]", "_", run_name)
    collapsed = re.sub(r"_+", "_", replaced).rstrip("_")
    while collapsed[:1] in {"_", "."}:
        collapsed = collapsed[1:]
    return collapsed[:80] or f"Run_{run_id}"


class _ExportFilenameBridge:
    """Bridges the UI ``ExportFilenameHelper`` onto ``compose_export_filename``; unmapped kinds fall back to a local sanitise copy."""  # fmt: skip

    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        name = run.run_name or f"Run {run.run_id}"
        export_kind = _EXPORT_KIND_MAP.get(kind)
        if export_kind is not None:
            return compose_export_filename(run_name=name, run_id=run.run_id, kind=export_kind, ext=ext)  # fmt: skip
        return f"{_sanitise_run_name(run_name=name, run_id=run.run_id)}_{kind}.{ext}"


class _EmbeddingSelection:
    """A resolved ``(provider, model)`` pair satisfying ``ReadinessEmbeddingSelection``."""

    def __init__(self, *, provider: ProviderConfig, model_name: str) -> None:
        self.provider = provider
        self.model_name = model_name


class _ReadinessEmbeddingSelector:
    """A thin adapter over ``SettingsService`` + ``ProvidersStore`` (sanctioned by ``readiness/protocols.py``)."""  # fmt: skip

    def __init__(self, *, settings: SettingsService, providers_store: ProvidersStore) -> None:
        self._settings = settings
        self._providers_store = providers_store

    def resolve_embedding_selection(self) -> _EmbeddingSelection | None:
        name = self._settings.get_str("embedding.selected_provider_name")
        model_name = self._settings.get_str("embedding.selected_model_name")
        provider = self._providers_store.get_by_name(name) if name else None
        if provider is None or not model_name:
            return None
        return _EmbeddingSelection(provider=provider, model_name=model_name)


class _NullEmbeddingClient:
    """Structural ``LLMClient`` stand-in for "no embedding provider configured" (Fix 1) -- satisfies ``make_embedding_service``'s ``client is not None`` precondition without guessing a provider the user never chose; ``embed`` raises ``EmbeddingUnavailableError``, which ``EmbeddingService.embed`` degrades to an empty vector, so `GRADED` reports itself unusable instead of crashing startup."""  # fmt: skip

    def list_models(self) -> tuple[ModelName, ...]: return ()  # fmt: skip

    def probe_health(self) -> ProviderHealth: return ProviderHealth(provider_id="00000000-0000-4000-8000-000000000000", reachable=False, discovery_supported=False, model_count=None, last_probe_ms=0, last_error="no embedding provider configured", probed_at=0)  # fmt: skip

    def test_inference(self, model_name: ModelName) -> InferenceTestResult: return InferenceTestResult(outcome=InferenceTestOutcome.REACHABILITY_FAILED, provider_id="00000000-0000-4000-8000-000000000000", model_name=model_name or "unconfigured", last_error="no embedding provider configured", tested_at=0)  # fmt: skip

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse: raise EmbeddingUnavailableError(message="no embedding provider is configured")  # noqa: ARG002  # fmt: skip

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream: raise EmbeddingUnavailableError(message="no embedding provider is configured")  # noqa: ARG002  # fmt: skip

    def embed(self, text: str) -> tuple[float, ...]: raise EmbeddingUnavailableError(message="no embedding provider is configured")  # noqa: ARG002  # fmt: skip

    def supports_streaming(self) -> bool: return False  # fmt: skip

    def supports_reasoning_effort(self) -> bool: return False  # fmt: skip

    def supports_thinking(self) -> bool: return False  # fmt: skip

    def supports_embedding(self) -> bool: return False  # fmt: skip

    def supports_discovery(self) -> bool: return False  # fmt: skip

    def close(self) -> None: return None  # fmt: skip


class _NoActiveRunTaskPaths:
    """Stub ``ActiveRunTaskPaths`` (Gap 3): no tracker exists yet; always empty."""

    def task_paths_for(self, run_id: RunId) -> tuple[str, ...]: return ()  # noqa: ARG002  # fmt: skip


class _NoRunValidator:
    """Stub ``RunValidator`` (Gap 4): validation messages inert until a real backend implementation lands."""  # fmt: skip

    def validate(self, request: RunStartRequest) -> tuple[ValidationEntry, ...]: return ()  # noqa: ARG002  # fmt: skip


class _NoOpManualProviderProbeCommand:  # Stub ManualProviderProbeCommand: no manual-probe target wired yet
    def probe(self) -> None: return None  # fmt: skip


class _AlwaysOkRunLogWriteStatus:
    """Stub ``RunLogWriteStatus``: no write-failure tracker is wired yet."""

    def write_failed(self) -> bool: return False  # fmt: skip


class _NoModelFetcher:
    """Stub ``ModelFetcher`` for the Result widget's model picker: no fetch target wired yet; reports an empty catalog."""  # fmt: skip

    def fetch_models(self, provider_id: object, *, on_success: Callable[..., None], on_error: Callable[..., None]) -> None:  # noqa: ARG002  # fmt: skip
        on_success(provider_id, ())
