"""Unit tests proving the four ``ui/common_dialogs/`` gateway Protocols are satisfied
structurally by their sibling per-widget gateways, with no dedicated adapter class
written for any of them (STORY-104-AC-2).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.3 (``ResumeGateway``); ``ui/common_dialogs/protocols.py`` (the four Common-Dialogs
gateways and the sibling each one's docstring already names as its structural
satisfier). Every sibling gateway's own exhaustive per-method wiring is already proven by
its own dedicated test file (``test_resume_gateway.py``, ``test_new_benchmark_gateway.py``,
``test_progress_gateway.py``, each of which explicitly defers this proof to
STORY-104-AC-2 rather than duplicating it). This file's job is narrower: build each
sibling gateway through its real ``adapters/ui_gateways`` factory, assign it to a
variable annotated with the Common-Dialogs Protocol (a static structural-satisfaction
check under ``mypy --strict``), and call every method the Protocol declares to prove it
also works at runtime. Collaborators the exercised methods do not touch are given simple,
non-raising fakes returning trivial defaults rather than the "raise on any unexpected
call" fakes the sibling gateways' own dedicated test files use -- that extra precision
belongs to those files, whose whole point is proving each gateway's *exhaustive*
per-method wiring; this file only needs the specific methods under test to work.
"""

from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.ui_gateways import (
    make_new_benchmark_gateway,
    make_progress_gateway,
    make_resume_gateway,
)
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
    SummarySerializationRequest,
)
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    Iso8601Utc,
    ModelDescriptor,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ReadinessState,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
    SettingKey,
)
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.provider_registry import LLMClient
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.backend.run_drift.models import RunDriftDetectionInputs
from ollama_llm_bench.backend.settings.testing import FakeSettingsService

if TYPE_CHECKING:
    from ollama_llm_bench.ui.common_dialogs.protocols import (
        RenameRunGateway,
        ResumeSummaryGateway,
        RetrySelectionGateway,
        RunSummaryGateway,
    )

_RUN_ID: Final[RunId] = 42
_PROVIDER_ID: Final[ProviderId] = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME: Final = "llama3"
_RESULT_IDS: Final[tuple[ResultId, ...]] = (1, 2)
# A run id deliberately distinct from ``_RUN_ID``: the seeded rows below back
# ``_RESULT_IDS`` so ``FakeResultsStore.reset_results``/``reset_results_for_retry``
# find them by id (avoiding a ``KeyError`` on an unseeded id) without appearing in
# any ``_RUN_ID``-scoped listing (``list_results``/``resumable_results`` stay ``()``).
_FOREIGN_RUN_ID: Final[RunId] = 999


def _make_run() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp="2026-08-01T00:00:00Z",
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-08-01T00:00:00Z",
    )


def _make_snapshot() -> AppReadinessSnapshot:
    return AppReadinessSnapshot(
        overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
    )


def _make_run_start_request() -> RunStartRequest:
    return RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _make_seeded_result(result_id: ResultId) -> BenchmarkResult:
    """A pre-seeded ``FakeResultsStore`` row backing one of ``_RESULT_IDS``.

    ``PENDING`` and scoped to ``_FOREIGN_RUN_ID`` (not ``_RUN_ID``) so
    ``reset_results``/``reset_results_for_retry`` find it by id -- avoiding a
    ``KeyError`` on an id the store never saw -- while ``changed`` stays 0 (the
    row is already ``PENDING``) and it never appears in a ``_RUN_ID``-scoped
    listing.
    """
    return BenchmarkResult(
        result_id=result_id,
        run_id=_FOREIGN_RUN_ID,
        task_id="task-1",
        provider_id=_PROVIDER_ID,
        provider_name="Test Provider",
        model_name=_MODEL_NAME,
        status=ResultStatus.PENDING,
        created_at="2026-08-01T00:00:00Z",
    )


# -- reusable fakes -----------------------------------------------------------------------


class _FakeRunsStore:
    """Working fake: ``list_runs``/``get_run`` return a canned run; ``rename_run``
    records its call."""

    def __init__(self) -> None:
        self.rename_run_calls: list[tuple[RunId, str | None]] = []

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return (_make_run(),)

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return _make_run()

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise NotImplementedError

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        self.rename_run_calls.append((run_id, name))

    def delete_run(self, run_id: RunId) -> None:
        raise NotImplementedError


class _FakeReadinessService:
    """Working fake: ``snapshot``/``probe_all`` both return the same canned snapshot."""

    def snapshot(self) -> AppReadinessSnapshot:
        return _make_snapshot()

    def probe_all(self) -> AppReadinessSnapshot:
        return _make_snapshot()

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        raise NotImplementedError

    def record_embedding_capability_result(self, *, reachable: bool) -> None:
        return None


class _FakeProvidersStore:
    """Working fake: ``list_providers`` returns an empty catalog, so
    ``ResumeGateway.detect_drift``'s per-provider ``list_models()`` loop never runs."""

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        return ()

    def get_by_name(self, name: str) -> ProviderConfig | None:
        raise NotImplementedError

    def add(self, draft: object) -> ProviderId:
        raise NotImplementedError

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        raise NotImplementedError

    def delete(self, provider_id: ProviderId) -> None:
        raise NotImplementedError

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        raise NotImplementedError

    def replace_providers_in_open_transaction(self, configs: tuple[ProviderConfig, ...]) -> None:
        raise NotImplementedError


class _FakeProviderRegistry:
    """Never-reachable fake: ``get_client`` is unreachable given an empty provider
    catalog."""

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        raise NotImplementedError

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        raise NotImplementedError

    def reload(self) -> None:
        raise NotImplementedError


class _FakeRunDriftDetector:
    """Working fake: ``detect`` always returns an empty warning tuple."""

    def detect(self, inputs: RunDriftDetectionInputs, /) -> tuple[DriftWarning, ...]:
        return ()


class _FakeBenchmarkFlowApi:
    """Working fake: ``start``/``resume`` record their call and return canned values."""

    def __init__(self) -> None:
        self.resume_calls: list[RunId] = []
        self.start_calls: list[RunStartRequest] = []

    def start(self, request: RunStartRequest) -> RunId:
        self.start_calls.append(request)
        return _RUN_ID

    def resume(self, run_id: RunId) -> None:
        self.resume_calls.append(run_id)

    def pause(self) -> None:
        return None

    def resume_paused(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def shutdown(self, timeout_ms: int) -> None:
        return None

    def is_running(self) -> bool:
        return False

    def current_run(self) -> BenchmarkRun | None:
        return None


class _FakeTasksStore:
    """Never-called stub: neither ``list_tasks`` nor ``create_tasks`` is exercised here."""

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return ()

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        return None


class _FakeAppSettingsStore:
    """Never-called stub: returns trivial, always-valid defaults."""

    def get_setting(self, key: SettingKey) -> str | None:
        return None

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        return None

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        return None

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        return None

    def list_settings(self) -> dict[SettingKey, str]:
        return {}

    def get_schema_version(self) -> int:
        return 1


class _FakeTableSerializer:
    """Never-called stub: ``serialize_table`` is not part of any Common-Dialogs
    Protocol."""

    def serialize_summary_csv(self, request: SummarySerializationRequest) -> str:
        return ""

    def serialize_summary_markdown(self, request: SummarySerializationRequest) -> str:
        return ""

    def serialize_details_csv(self, request: DetailsSerializationRequest) -> str:
        return ""

    def serialize_details_markdown(self, request: DetailsSerializationRequest) -> str:
        return ""


class _FakeClock:
    """Never-called stub: a trivial fixed-time ``Clock``."""

    def now_utc(self) -> Iso8601Utc:
        return "2026-08-01T00:00:00Z"

    def monotonic_ms(self) -> int:
        return 0


class _FakePlatformDetector:
    """Never-called stub: a trivial fixed ``PlatformDetector``."""

    @property
    def app_data_root(self) -> Path:
        return Path("/tmp/ollama-llm-bench-test")  # noqa: S108 -- never touched at runtime


class _FakeTaskRunner:
    """Never-called stub: ``ProgressGateway``'s manual-probe dispatch is not exercised
    here."""

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> Future[object]:
        raise NotImplementedError


class _FakeManualProviderProbeCommand:
    """Never-called stub: backs only ``ProgressGateway.manual_provider_probe``."""

    def probe(self) -> None:
        return None


class _FakeRunLogWriteStatus:
    """Never-called stub: backs only ``ProgressGateway.run_log_write_failed``."""

    def write_failed(self) -> bool:
        return False


# -- STORY-104-AC-2 cases -------------------------------------------------------------


def _case_run_summary_gateway_via_new_benchmark_gateway() -> None:
    flow = _FakeBenchmarkFlowApi()
    gateway: RunSummaryGateway = make_new_benchmark_gateway(
        app_settings=_FakeAppSettingsStore(),
        settings=FakeSettingsService(),
        provider_registry=_FakeProviderRegistry(),
        readiness=_FakeReadinessService(),
        flow=flow,
        notification=FakeNotificationService(),
    )

    snapshot = gateway.readiness_snapshot()
    run_id = gateway.start_run(_make_run_start_request())

    assert snapshot == _make_snapshot()
    assert run_id == _RUN_ID
    assert len(flow.start_calls) == 1


def _case_rename_run_gateway_via_resume_gateway() -> None:
    runs_store = _FakeRunsStore()
    gateway: RenameRunGateway = make_resume_gateway(
        runs_store=runs_store,
        results_store=FakeResultsStore(),
        tasks_store=_FakeTasksStore(),
        app_settings=_FakeAppSettingsStore(),
        readiness=_FakeReadinessService(),
        providers_store=_FakeProvidersStore(),
        provider_registry=_FakeProviderRegistry(),
        detector=_FakeRunDriftDetector(),
        flow=_FakeBenchmarkFlowApi(),
        serializer=_FakeTableSerializer(),
        clock=_FakeClock(),
    )

    runs = gateway.list_runs()
    gateway.rename_run(_RUN_ID, "renamed")

    assert runs == (_make_run(),)
    assert runs_store.rename_run_calls == [(_RUN_ID, "renamed")]


def _case_rename_run_gateway_via_progress_gateway() -> None:
    runs_store = _FakeRunsStore()
    gateway: RenameRunGateway = make_progress_gateway(
        flow=_FakeBenchmarkFlowApi(),
        runs_store=runs_store,
        results_store=FakeResultsStore(),
        app_settings=_FakeAppSettingsStore(),
        settings=FakeSettingsService(),
        platform_detector=_FakePlatformDetector(),
        task_runner=_FakeTaskRunner(),
        clock=_FakeClock(),
        probe_command=_FakeManualProviderProbeCommand(),
        write_status=_FakeRunLogWriteStatus(),
    )

    runs = gateway.list_runs()
    gateway.rename_run(_RUN_ID, "renamed")

    assert runs == (_make_run(),)
    assert runs_store.rename_run_calls == [(_RUN_ID, "renamed")]


def _case_resume_summary_gateway_via_resume_gateway() -> None:
    gateway: ResumeSummaryGateway = make_resume_gateway(
        runs_store=_FakeRunsStore(),
        results_store=FakeResultsStore(initial=(_make_seeded_result(1), _make_seeded_result(2))),
        tasks_store=_FakeTasksStore(),
        app_settings=_FakeAppSettingsStore(),
        readiness=_FakeReadinessService(),
        providers_store=_FakeProvidersStore(),
        provider_registry=_FakeProviderRegistry(),
        detector=_FakeRunDriftDetector(),
        flow=_FakeBenchmarkFlowApi(),
        serializer=_FakeTableSerializer(),
        clock=_FakeClock(),
    )

    run = gateway.get_run(_RUN_ID)
    resumable = gateway.resumable_results(_RUN_ID)
    warnings = gateway.detect_drift(_RUN_ID)
    reset_count = gateway.reset_results(_RESULT_IDS)
    gateway.resume_run(_RUN_ID)

    assert run == _make_run()
    assert resumable == ()
    assert warnings == ()
    assert reset_count == 0


def _case_retry_selection_gateway_via_resume_gateway() -> None:
    flow = _FakeBenchmarkFlowApi()
    gateway: RetrySelectionGateway = make_resume_gateway(
        runs_store=_FakeRunsStore(),
        results_store=FakeResultsStore(initial=(_make_seeded_result(1), _make_seeded_result(2))),
        tasks_store=_FakeTasksStore(),
        app_settings=_FakeAppSettingsStore(),
        readiness=_FakeReadinessService(),
        providers_store=_FakeProvidersStore(),
        provider_registry=_FakeProviderRegistry(),
        detector=_FakeRunDriftDetector(),
        flow=flow,
        serializer=_FakeTableSerializer(),
        clock=_FakeClock(),
    )

    results = gateway.list_results(_RUN_ID)
    retry_count = gateway.reset_results_for_retry(_RESULT_IDS)
    gateway.resume_run(_RUN_ID)

    assert results == ()
    assert retry_count == 0
    assert flow.resume_calls == [_RUN_ID]


_AC2_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("run_summary_via_new_benchmark", _case_run_summary_gateway_via_new_benchmark_gateway),
    ("rename_run_via_resume", _case_rename_run_gateway_via_resume_gateway),
    ("rename_run_via_progress", _case_rename_run_gateway_via_progress_gateway),
    ("resume_summary_via_resume", _case_resume_summary_gateway_via_resume_gateway),
    ("retry_selection_via_resume", _case_retry_selection_gateway_via_resume_gateway),
)
_AC2_CASE_IDS = [case[0] for case in _AC2_CASES]


@pytest.mark.parametrize("case", _AC2_CASES, ids=_AC2_CASE_IDS)
def test_common_dialog_gateways_are_satisfied_by_their_sibling_gateway(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-104-AC-2

    Each of the four Common-Dialogs gateway Protocols (``RunSummaryGateway``,
    ``RenameRunGateway``, ``ResumeSummaryGateway``, ``RetrySelectionGateway``) is
    satisfied structurally by the sibling per-widget gateway
    ``ui/common_dialogs/protocols.py`` already names -- ``NewBenchmarkGateway`` or
    ``ResumeGateway``, and for ``RenameRunGateway`` both ``ResumeGateway`` and
    ``ProgressGateway`` -- with no dedicated adapter class written for any of them.
    Table-driven (one row per sibling-gateway pairing the AC-2 table names, five rows
    total since ``RenameRunGateway`` has two sibling satisfiers), because each row's
    construction and assertions genuinely differ and a loop would hide which pairing
    failed.
    """
    _name, run_case = case
    run_case()
