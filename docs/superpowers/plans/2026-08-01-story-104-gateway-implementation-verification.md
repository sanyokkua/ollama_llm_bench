# STORY-104 — Gateway Implementation Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two acceptance-criteria tests STORY-104 requires, proving that every one
of the seven UI-declared gateway Protocols (`08_Cross_Cutting/08-E_interfaces_contracts.md`
§7b) has exactly one production implementation reachable from `adapters/ui_gateways/`'s
public surface, and that the four `ui/common_dialogs/` gateway Protocols are satisfied
structurally by their sibling per-widget gateways with no dedicated adapter class.

**Architecture:** STORY-104 adds **no new implementation**. All seven per-widget gateway
factories and their concrete classes already exist and already ship in
`src/ollama_llm_bench/adapters/ui_gateways/` (delivered by STORY-105 … STORY-111, all
`status: done`). This plan writes two pure-verification test files: an architecture test
(`tests/architecture/test_gateway_implementations_exist.py`) that dynamically discovers
every class under `adapters/ui_gateways/_internal/` and checks Protocol satisfaction by
method-name introspection, and a unit test
(`tests/unit/test_common_dialog_gateway_structural_satisfaction.py`) that builds each
sibling gateway through its real factory with hand-written fake collaborators and calls
every method the relevant Common-Dialogs Protocol declares.

**Tech Stack:** Python 3.13, `pytest` + `pytest-parametrize`, `msgspec` domain types,
`typing.Protocol` structural checks via `inspect`/`pkgutil`, no PySide6 involvement (both
tests are pure Python — no `QApplication` needed).

## Global Constraints

- No `src/` file is created or modified by this plan — both tasks are additive test files
  only, per STORY-104's own scope (Out of scope: "The per-gateway implementations
  themselves — each is owned by its own child story").
- Every test function is fully annotated, returns `-> None`, follows Arrange-Act-Assert,
  and contains no `if`/`for` — a table of cases uses `@pytest.mark.parametrize`
  (`testing.md`).
- The first line of a docstring on a test proving an acceptance criterion is
  `"""Proves: STORY-104-AC-1` / `STORY-104-AC-2` in the fixed traceability form
  (`traceability-and-stories.md`).
- Every mock/fake is hand-written or `spec=`-based per this module's own established
  convention (`adapters/ui_gateways/tests/test_resume_gateway.py`,
  `test_new_benchmark_gateway.py`) — no bare `mocker.Mock()`.
- Absolute imports only, three import blocks (stdlib / third-party / first-party),
  alphabetically sorted within each block (`coding-style.md`).
- `mypy --strict`, `ruff check`, `ruff format --check`, and `import-linter` must all pass
  on both new files before either task is considered done — fix every issue reported in a
  touched file, "pre-existing" is never a valid excuse (CLAUDE.md Quality gates).
- `just trace` must be re-run after both files exist (new `Proves:` lines change
  `traceability.yaml`), and `just trace-check` must pass with zero gaps before STORY-104
  can be marked `done`.

______________________________________________________________________

### Task 1: Architecture test — every gateway Protocol has exactly one production implementation

**Files:**

- Create: `tests/architecture/test_gateway_implementations_exist.py`

**Interfaces:**

- Consumes: the seven already-shipped `make_*_gateway` factories and their `__all__` entry
  in `src/ollama_llm_bench/adapters/ui_gateways/api.py`; the seven concrete `_*Gateway`
  classes under `src/ollama_llm_bench/adapters/ui_gateways/_internal/<widget>/gateway.py`;
  the seven UI-owned gateway Protocols at `ui/main_window/protocols.py`,
  `ui/new_benchmark/protocols.py`, `ui/progress/protocols.py`, `ui/results/protocols.py`,
  `ui/resume_benchmark/protocols.py`, `ui/settings_dialog/protocols.py`,
  `ui/task_editor/protocols.py` — every one of these already exists; nothing is created or
  changed.

- Produces: nothing consumed by a later task in this plan — Task 3 only runs this test,
  it does not import from it.

- [ ] **Step 1: Write the architecture test**

Create `tests/architecture/test_gateway_implementations_exist.py` with this exact content:

```python
"""Architecture guard: every UI-declared gateway Protocol has exactly one production
implementation, reachable through exactly one ``make_*_gateway`` factory, in
``adapters/ui_gateways/`` (STORY-104-AC-1).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b (the seven gateway Protocols);
``docs/stories/story-104-ui-adapter-gateway-implementations.md`` Design constraints (why
this test resolves each widget module's own Protocol copy, never
``adapters/ui_gateways/protocols.py``'s deliberate mirror, and why "reachable through the
public surface" means reached via a ``make_*_gateway`` factory rather than an importable
class name -- the seven concrete classes are ``_``-prefixed and unexported).

This file lives under ``tests/architecture/`` rather than ``adapters/ui_gateways/tests/``
because it is a cross-module (``adapters`` + seven ``ui`` widget modules) structural check
-- the ``testing.md`` "colocated tests test only their own module" rule places a check
like this at the top level, mirroring ``test_result_gateway_protocol_mirrors.py``'s own
precedent for the same reason. This module's own name (``tests.architecture.*``) falls
outside the ``ollama_llm_bench.adapters``/``ollama_llm_bench.ui`` namespaces
import-linter's "Module internals are private" contract matches
(``root_packages = ["ollama_llm_bench"]``), so importing
``adapters.ui_gateways._internal`` here to enumerate its classes is legal, unlike doing so
from production code or a colocated module test.
"""

import importlib
import inspect
import pkgutil

import pytest

from ollama_llm_bench.adapters import ui_gateways
from ollama_llm_bench.adapters.ui_gateways import _internal as _ui_gateways_internal
from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway
from ollama_llm_bench.ui.new_benchmark.protocols import NewBenchmarkGateway
from ollama_llm_bench.ui.progress.protocols import ProgressGateway
from ollama_llm_bench.ui.results.protocols import ResultGateway
from ollama_llm_bench.ui.resume_benchmark.protocols import ResumeGateway
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway
from ollama_llm_bench.ui.task_editor.protocols import TaskEditorGateway

_GATEWAY_PROTOCOLS: tuple[tuple[str, type], ...] = (
    ("MainWindowGateway", MainWindowGateway),
    ("NewBenchmarkGateway", NewBenchmarkGateway),
    ("ProgressGateway", ProgressGateway),
    ("ResultGateway", ResultGateway),
    ("ResumeGateway", ResumeGateway),
    ("SettingsGateway", SettingsGateway),
    ("TaskEditorGateway", TaskEditorGateway),
)
_GATEWAY_PROTOCOL_IDS = [name for name, _ in _GATEWAY_PROTOCOLS]


def _protocol_method_names(protocol: type) -> frozenset[str]:
    """Return the public method names a ``Protocol`` class declares directly."""
    return frozenset(
        name
        for name, member in vars(protocol).items()
        if not name.startswith("_") and callable(member)
    )


def _discover_internal_classes() -> dict[str, type]:
    """Import every non-``testing`` module under ``adapters/ui_gateways/_internal`` and
    return every class defined directly in one of those modules, keyed by its
    fully-qualified name."""
    discovered: dict[str, type] = {}
    prefix = f"{_ui_gateways_internal.__name__}."
    for module_info in pkgutil.walk_packages(_ui_gateways_internal.__path__, prefix=prefix):
        if module_info.name.rsplit(".", 1)[-1] == "testing":
            continue
        module = importlib.import_module(module_info.name)
        for _, member in inspect.getmembers(module, inspect.isclass):
            if member.__module__ == module.__name__:
                discovered[f"{module.__name__}.{member.__qualname__}"] = member
    return discovered


def _classes_satisfying(protocol: type, candidates: dict[str, type]) -> list[str]:
    """Return the qualified names of every candidate class structurally satisfying
    ``protocol`` -- every one of the Protocol's declared methods is a callable attribute
    of the candidate."""
    method_names = _protocol_method_names(protocol)
    return [
        qualname
        for qualname, candidate in candidates.items()
        if all(callable(getattr(candidate, name, None)) for name in method_names)
    ]


def _factories_returning(protocol_name: str) -> list[str]:
    """Return the names of every ``make_*_gateway`` factory in ``adapters.ui_gateways``'s
    public surface whose return-type annotation is named ``protocol_name`` -- proving the
    satisfying class is reachable through the module's public factory, not merely present
    somewhere under ``_internal``."""
    matches: list[str] = []
    for name in ui_gateways.__all__:
        if not (name.startswith("make_") and name.endswith("_gateway")):
            continue
        factory = getattr(ui_gateways, name)
        return_annotation = inspect.signature(factory).return_annotation
        if getattr(return_annotation, "__name__", None) == protocol_name:
            matches.append(name)
    return matches


@pytest.mark.parametrize(
    ("protocol_name", "protocol"), _GATEWAY_PROTOCOLS, ids=_GATEWAY_PROTOCOL_IDS
)
def test_every_ui_gateway_protocol_has_one_production_implementation(
    protocol_name: str, protocol: type
) -> None:
    """Proves: STORY-104-AC-1

    For every gateway Protocol declared in a ``ui/*`` widget module's own
    ``protocols.py`` (never ``adapters/ui_gateways/protocols.py``'s deliberate mirror --
    see this file's module docstring and STORY-104's Design constraints), exactly one
    production class defined under ``adapters/ui_gateways/_internal`` -- outside any
    ``testing.py`` module -- structurally satisfies it, and that class is reachable
    through exactly one ``make_*_gateway`` factory in the module's public surface.
    """
    candidates = _discover_internal_classes()

    satisfying = _classes_satisfying(protocol, candidates)
    assert satisfying, (
        f"{protocol_name}: no production class under adapters/ui_gateways/_internal "
        "satisfies it"
    )
    assert len(satisfying) == 1, (
        f"{protocol_name}: expected exactly one production implementation, "
        f"found {satisfying}"
    )

    factories = _factories_returning(protocol_name)
    assert factories, f"{protocol_name}: no make_*_gateway factory returns it"
    assert len(factories) == 1, (
        f"{protocol_name}: expected exactly one make_*_gateway factory returning it, "
        f"found {factories}"
    )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/architecture/test_gateway_implementations_exist.py -v`

Expected: `7 passed` (one per gateway Protocol: `MainWindowGateway`, `NewBenchmarkGateway`,
`ProgressGateway`, `ResultGateway`, `ResumeGateway`, `SettingsGateway`,
`TaskEditorGateway`). If a row fails, it means either a production class's method set has
drifted from its UI-owned Protocol, or more than one class in `_internal/` now
structurally satisfies the same Protocol — both are real regressions to investigate, not
test bugs to work around.

- [ ] **Step 3: Lint and type-check the new file**

Run: `uv run ruff check tests/architecture/test_gateway_implementations_exist.py --fix`
Run: `uv run ruff format tests/architecture/test_gateway_implementations_exist.py`
Run: `uv run mypy --strict tests/architecture/test_gateway_implementations_exist.py`
Run: `uv run lint-imports`

Expected: all four commands exit `0`. Fix any reported issue in this file before
continuing — do not suppress with an unjustified `# noqa`/`# type: ignore`.

- [ ] **Step 4: Commit**

```bash
git add tests/architecture/test_gateway_implementations_exist.py
git commit -m "test(story-104): prove every UI gateway Protocol has one production implementation"
```

______________________________________________________________________

### Task 2: Unit test — Common-Dialogs gateways are satisfied structurally by their siblings

**Files:**

- Create: `tests/unit/test_common_dialog_gateway_structural_satisfaction.py`

**Interfaces:**

- Consumes: `make_new_benchmark_gateway`, `make_resume_gateway`, `make_progress_gateway`
  from `ollama_llm_bench.adapters.ui_gateways` (already shipped, unchanged); the four
  Common-Dialogs Protocols (`RunSummaryGateway`, `RenameRunGateway`, `ResumeSummaryGateway`,
  `RetrySelectionGateway`) from `ollama_llm_bench.ui.common_dialogs.protocols` (already
  shipped, unchanged); the reusable fakes `FakeResultsStore`
  (`ollama_llm_bench.backend.persistence.results.testing`), `FakeSettingsService`
  (`ollama_llm_bench.backend.settings.testing`), and `FakeNotificationService`
  (`ollama_llm_bench.adapters.notification_service.testing`) — all three already exist.

- Produces: nothing consumed by a later task in this plan.

- [ ] **Step 1: Write the unit test**

Create `tests/unit/test_common_dialog_gateway_structural_satisfaction.py` with this exact
content:

```python
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
from typing import Final

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
    ProviderId,
    ReadinessState,
    ResultId,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
    SettingKey,
)
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.backend.run_drift.models import RunDriftDetectionInputs
from ollama_llm_bench.backend.settings.testing import FakeSettingsService
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

    def probe(self, provider_id: ProviderId) -> object:
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

    def replace_providers_in_open_transaction(
        self, configs: tuple[ProviderConfig, ...]
    ) -> None:
        raise NotImplementedError


class _FakeProviderRegistry:
    """Never-reachable fake: ``get_client`` is unreachable given an empty provider
    catalog."""

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        raise NotImplementedError

    def get_client(self, provider_id: ProviderId) -> object:
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
        return Path("/tmp/ollama-llm-bench-test")


class _FakeTaskRunner:
    """Never-called stub: ``ProgressGateway``'s manual-probe dispatch is not exercised
    here."""

    def submit(
        self, fn: Callable[[], object], *, token: CancellationToken
    ) -> Future[object]:
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
        results_store=FakeResultsStore(),
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
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_common_dialog_gateway_structural_satisfaction.py -v`

Expected: `5 passed` (`run_summary_via_new_benchmark`, `rename_run_via_resume`,
`rename_run_via_progress`, `resume_summary_via_resume`, `retry_selection_via_resume`).

If `run_summary_via_new_benchmark` fails on the `mypy`-adjacent assignment line (Step 3
below is where that surfaces, not `pytest` — a Protocol mismatch at the
`gateway: RunSummaryGateway = make_new_benchmark_gateway(...)` line is a **static** type
error, not a runtime one; `pytest` will only fail here if a called method itself raises).

- [ ] **Step 3: Lint and type-check the new file**

Run: `uv run ruff check tests/unit/test_common_dialog_gateway_structural_satisfaction.py --fix`
Run: `uv run ruff format tests/unit/test_common_dialog_gateway_structural_satisfaction.py`
Run: `uv run mypy --strict tests/unit/test_common_dialog_gateway_structural_satisfaction.py`
Run: `uv run lint-imports`

Expected: all four commands exit `0`. This is the step that actually proves AC-2's
structural-satisfaction claim under `mypy --strict` — each `gateway: <Protocol> = make_*_gateway(...)` assignment only type-checks if the returned concrete class truly
satisfies that Protocol. If `mypy` reports a missing/mismatched member here, that is a
real AC-2 failure (the claimed structural satisfaction does not actually hold), not a
test-code bug to silence with `# type: ignore`.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_common_dialog_gateway_structural_satisfaction.py
git commit -m "test(story-104): prove Common-Dialogs gateways are satisfied by sibling gateways"
```

______________________________________________________________________

### Task 3: Regenerate traceability and close out the story

**Files:**

- Modify: `traceability.yaml` (repository root) — regenerated, never hand-edited.
- Modify: `docs/stories/story-104-ui-adapter-gateway-implementations.md` — check off the
  Definition of done items and flip `status: ready` to `status: done`.

**Interfaces:**

- Consumes: the two new test files from Task 1 and Task 2 (their `Proves:` docstring
  lines are what `scripts/trace.py` reads).

- Produces: nothing — this is the terminal task of the plan.

- [ ] **Step 1: Run the full quality gate**

Run: `just check`

Expected: exit `0`. This runs `ruff check`, `ruff format --check`, `mypy --strict`,
`import-linter`, the `pytest-archon`/AST architecture tests, and the full `pytest` suite
together — broader than Task 1/2's individual `Step 3` lint/type checks, so a full-suite
regression (e.g. an unrelated test order dependency) surfaces here if one exists.

- [ ] **Step 2: Regenerate traceability.yaml**

Run: `uv run python scripts/trace.py`

Expected output: `trace.py: wrote traceability.yaml (<N> stories, <M> test(s) collected).`
with `<M>` twelve higher than before this plan (7 new parametrized rows for AC-1 + 5 new
parametrized rows for AC-2).

- [ ] **Step 3: Verify traceability is green**

Run: `uv run python scripts/validate_traceability.py`

Expected: exit `0`, no reported gap. If this fails on an unrelated pre-existing gap (not
introduced by this plan), stop and report it rather than working around it — STORY-104
cannot be marked `done` while `just trace-check` is red for any reason, per CLAUDE.md's
"Never mark a story `done` without `just trace-check` passing."

- [ ] **Step 4: Update STORY-104's Definition of done and status**

Open `docs/stories/story-104-ui-adapter-gateway-implementations.md` and:

1. Change the front-matter `status: ready` to `status: done`.
1. Check off every Definition of done item now genuinely satisfied:

```markdown
## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-104.
- [x] The seven child stories (STORY-105 … STORY-111) are `done`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.
```

- [ ] **Step 5: Regenerate traceability once more to pick up the status change**

Run: `uv run python scripts/trace.py`
Run: `uv run python scripts/validate_traceability.py`

Expected: both exit `0`. `traceability.yaml`'s `stories.STORY-104.status` field must now
read `done`.

- [ ] **Step 6: Commit**

```bash
git add traceability.yaml docs/stories/story-104-ui-adapter-gateway-implementations.md
git commit -m "docs(story-104): mark story done — gateway conformance proven, traceability green"
```

______________________________________________________________________

## Self-Review

**1. Spec coverage.** STORY-104-AC-1 (every gateway Protocol has exactly one production
implementation reachable from the adapters public surface) → Task 1. STORY-104-AC-2 (the
four Common-Dialogs gateways are satisfied structurally by sibling gateways) → Task 2,
covering all five sibling-gateway pairings the story's own AC-2 table names (including
both of `RenameRunGateway`'s two satisfiers). The Design constraints (resolve the
UI-owned Protocol copy, not the adapter mirror; reachability means via the factory, not an
importable class name; `SettingsGateway`'s amended ADR-0015/0016 shape) are respected by
construction — Task 1 never imports `adapters/ui_gateways/protocols.py`'s mirrors, and
Task 2 never touches `SettingsGateway` at all (no Common-Dialogs gateway is satisfied by
it). Traceability regeneration and story closeout → Task 3.

**2. Placeholder scan.** No `TODO`/`TBD`/"add appropriate handling" anywhere; every step
carries complete, runnable code or an exact command with its expected output.

**3. Type consistency.** `make_resume_gateway`'s eleven keyword parameters
(`runs_store`, `results_store`, `tasks_store`, `app_settings`, `readiness`,
`providers_store`, `provider_registry`, `detector`, `flow`, `serializer`, `clock`) are
named identically across all three Task 2 cases that call it. `make_progress_gateway`'s
ten parameters and `make_new_benchmark_gateway`'s six match their real factory signatures
in `src/ollama_llm_bench/adapters/ui_gateways/api.py` exactly, as read directly from that
file during planning — not guessed.
