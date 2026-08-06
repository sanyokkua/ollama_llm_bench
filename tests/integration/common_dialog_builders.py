"""Construction of all seven shared modal dialogs with canned data and stub gateways.

Extracted from `test_screenshot_harness.py` so the mockup-conformance screenshots
and the accessibility-name walker mount the same seven dialogs from one definition
rather than two drifting copies. Three of the seven factories return
`QDialog | None` -- `None` when their gateway's canned data is too thin to pass the
dialog's own precondition. The canned data here is built specifically to satisfy
every one of those preconditions, so a `None` means the canned data regressed, not
a normal outcome to tolerate.
"""

from collections.abc import Callable
from typing import Final

from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.clipboard import make_clipboard
from ollama_llm_bench.adapters.file_system_actions import make_file_system_actions
from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    ModelDescriptor,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
    ReadinessState,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
)
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.ui.common_dialogs import (
    AboutDialogCollaborators,
    ErrorDialogPattern,
    ErrorDialogPayload,
    GenerateAnalysisCollaborators,
    make_about_dialog,
    make_error_dialog,
    make_generate_analysis_dialog,
    make_rename_run_dialog,
    make_resume_summary_dialog,
    make_retry_selection_dialog,
    make_run_summary_dialog,
)
from ollama_llm_bench.ui.new_benchmark.testing import FakeRunValidator

_PROVIDER_ID: Final[str] = "550e8400-e29b-41d4-a716-446655440000"
_MODEL_NAME: Final[str] = "llama3.1:8b"
_RUN_ID: Final[int] = 1
_TIMESTAMP: Final[str] = "2026-08-05T12:00:00Z"

_DIALOG_SIZE: Final[tuple[int, int]] = (900, 700)


class _StubRenameRunGateway:
    """Structural ``RenameRunGateway`` returning one canned run header."""

    def __init__(self, *, runs: tuple[BenchmarkRun, ...]) -> None:
        self._runs = runs

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return self._runs

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        return None


class _StubRunSummaryGateway:
    """Structural ``RunSummaryGateway`` whose readiness passes preflight."""

    def __init__(self, *, readiness: AppReadinessSnapshot) -> None:
        self._readiness = readiness

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def start_run(self, request: RunStartRequest) -> RunId:
        return _RUN_ID


class _StubResumeSummaryGateway:
    """Structural ``ResumeSummaryGateway`` with non-empty resumable results."""

    def __init__(self, *, run: BenchmarkRun, results: tuple[BenchmarkResult, ...]) -> None:
        self._run = run
        self._results = results

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._run

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return ()

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        return None


class _StubRetrySelectionGateway:
    """Structural ``RetrySelectionGateway`` with a non-empty result table."""

    def __init__(self, *, results: tuple[BenchmarkResult, ...]) -> None:
        self._results = results

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        return None


class _StubRunAnalysisDispatcher:
    """Structural ``RunAnalysisDispatcher`` that always accepts a dispatch."""

    def regenerate_analysis(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> bool:
        return True


class _StubProviderListSource:
    """Structural ``ProviderListSource`` offering one enabled provider."""

    def __init__(self, *, providers: tuple[ProviderConfig, ...]) -> None:
        self._providers = providers

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return self._providers


class _StubModelFetcher:
    """Structural ``ModelFetcher`` delivering a canned catalogue synchronously."""

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],
    ) -> None:
        on_success(provider_id, (_MODEL_NAME,))


class _StubSubscription:
    """Structural ``Subscription`` handle; cancellation is a no-op for a capture."""

    def cancel(self) -> None:
        return None


class _StubGenerateAnalysisEventBus:
    """Structural ``EventBus`` fake routing around a real production defect.

    ``ui/common_dialogs/_internal/generate_analysis_view.py`` calls
    ``event_bus.subscribe(signal, handler)`` three times with no ``owner=``
    keyword. The real ``QtEventBusDeliverer.subscribe`` (used everywhere else
    in this harness) carries an ``icontract`` precondition requiring a non-
    ``None`` owner (08-J §2), so building this one dialog against the real
    bus raises ``icontract.errors.ViolationError`` -- a genuine bug that would
    crash any real user opening this dialog, masked in
    ``ui/common_dialogs/tests/test_generate_analysis_dialog.py`` by that
    module's own ``_FakeEventBus``, which accepts a missing owner silently.
    This mirrors that same fake, scoped to this one dialog only, so the
    screenshot capture is not blocked by a defect outside this story's scope
    (no ``src/`` change here -- see the task report).
    """

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> _StubSubscription:
        return _StubSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        return None


def _canned_provider() -> ProviderConfig:
    """Return one enabled provider entry for the Generate Analysis dropdown."""
    return ProviderConfig(
        provider_id=_PROVIDER_ID,
        name="Ollama (local)",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _canned_readiness() -> AppReadinessSnapshot:
    """Return a snapshot with one reachable provider and a reachable embedding."""
    return AppReadinessSnapshot(
        overall=ReadinessState.READY,
        per_provider=(
            ProviderHealth(
                provider_id=_PROVIDER_ID,
                reachable=True,
                discovery_supported=True,
                model_count=3,
                last_probe_ms=12,
                probed_at=0,
            ),
        ),
        embedding_reachable=True,
    )


def _canned_request() -> RunStartRequest:
    """Return a start request that passes the Run Summary preflight."""
    return RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _canned_run() -> BenchmarkRun:
    """Return one completed run header."""
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp=_TIMESTAMP,
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=4,
        completed_tasks=2,
        total_elapsed_ms=42_000,
        schema_version=1,
        created_at=_TIMESTAMP,
    )


def _canned_results() -> tuple[BenchmarkResult, ...]:
    """Return two result rows: one completed, one failed and retryable."""
    return (
        BenchmarkResult(
            result_id=1,
            run_id=_RUN_ID,
            task_id="synthetic_small_1",
            provider_id=_PROVIDER_ID,
            provider_name="Ollama (local)",
            model_name=_MODEL_NAME,
            status=ResultStatus.COMPLETED,
            created_at=_TIMESTAMP,
        ),
        BenchmarkResult(
            result_id=2,
            run_id=_RUN_ID,
            task_id="synthetic_small_2",
            provider_id=_PROVIDER_ID,
            provider_name="Ollama (local)",
            model_name=_MODEL_NAME,
            status=ResultStatus.FAILED_TIMEOUT,
            created_at=_TIMESTAMP,
        ),
    )


def build_common_dialogs(*, qtbot: QtBot) -> dict[str, QDialog]:
    """Construct all seven shared modal dialogs, shown but never exec()'d.

    Three of the seven factories (``make_run_summary_dialog``,
    ``make_resume_summary_dialog``, ``make_retry_selection_dialog``) return
    ``QDialog | None`` -- ``None`` when their gateway's canned data is too
    thin to pass the dialog's own precondition. The canned data above is
    constructed specifically to satisfy every one of those preconditions, so
    a ``None`` here means the canned data regressed, not a normal outcome to
    tolerate.
    """
    bus = make_qt_event_bus_deliverer()
    clipboard = make_clipboard()
    candidates: dict[str, QDialog | None] = {
        "07_common_dialogs__about": make_about_dialog(
            collaborators=AboutDialogCollaborators(
                clipboard=clipboard,
                file_system_actions=make_file_system_actions(),
                event_bus=bus,
            ),
            version="0.0.0",
            data_folder_path="/home/user/.local/share/OllamaLLMBench",
        ),
        "07_common_dialogs__error": make_error_dialog(
            payload=ErrorDialogPayload(
                title="Provider unreachable",
                message="The benchmark could not reach the configured provider.",
                detail="HttpConnectionError: connection refused (127.0.0.1:11434)",
                pattern=ErrorDialogPattern.RECOVERABLE,
            ),
            clipboard=clipboard,
            event_bus=bus,
        ),
        "07_common_dialogs__rename_run": make_rename_run_dialog(
            gateway=_StubRenameRunGateway(runs=(_canned_run(),)),
            run_id=_RUN_ID,
            current_custom_name=None,
            computed_default_name="Synthetic run — 2026-08-05 12:00",
        ),
        "07_common_dialogs__run_summary": make_run_summary_dialog(
            gateway=_StubRunSummaryGateway(readiness=_canned_readiness()),
            run_validator=FakeRunValidator(),
            request=_canned_request(),
        ),
        "07_common_dialogs__resume_summary": make_resume_summary_dialog(
            gateway=_StubResumeSummaryGateway(run=_canned_run(), results=_canned_results()),
            event_bus=bus,
            run_id=_RUN_ID,
        ),
        "07_common_dialogs__retry_selection": make_retry_selection_dialog(
            gateway=_StubRetrySelectionGateway(results=_canned_results()),
            run_id=_RUN_ID,
        ),
        "07_common_dialogs__generate_analysis": make_generate_analysis_dialog(
            run=_canned_run(),
            collaborators=GenerateAnalysisCollaborators(
                dispatcher=_StubRunAnalysisDispatcher(),
                provider_source=_StubProviderListSource(providers=(_canned_provider(),)),
                model_fetcher=_StubModelFetcher(),
                # Not the shared real `bus` -- see `_StubGenerateAnalysisEventBus`'s
                # docstring for the real production defect this routes around.
                event_bus=_StubGenerateAnalysisEventBus(),
            ),
        ),
    }
    dialogs: dict[str, QDialog] = {}
    for capture_id, dialog in candidates.items():
        if dialog is None:
            message = f"{capture_id} factory returned None; its gateway data is insufficient"
            raise AssertionError(message)
        qtbot.addWidget(dialog)
        dialog.resize(*_DIALOG_SIZE)
        dialog.show()
        dialogs[capture_id] = dialog
    qtbot.wait(0)
    return dialogs
