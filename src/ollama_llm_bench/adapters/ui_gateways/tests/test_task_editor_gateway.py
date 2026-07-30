"""Unit tests for the concrete ``TaskEditorGateway`` (STORY-111).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.7, §7b, §4 (the threading contract).

Collaborators are hand-written, call-recording fakes rather than
``mocker.Mock(spec=...)`` -- each gateway method hits a *different* collaborator by a
*different* method name (``get_setting``/``set_setting`` split across
``AppSettingsStore.get_setting``/``SettingsService.set``, ``active_workspace`` maps to
``WorkspaceStore.active_workspace``, ``active_run_task_paths`` maps to
``RunRegistryStore.active_run_id`` plus, only when a run is active,
``ActiveRunTaskPaths.task_paths_for``), so a single shared ``Mock(spec=Protocol)`` per
collaborator would not let each row assert both "the right collaborator got the right
call" and "no other collaborator/method was touched" as precisely as a purpose-built
fake. Every fake raises on a method the gateway must never call, so a wrong-collaborator
wiring bug fails loudly instead of silently no-op'ing. ``_FakeWorkspaceStore``/
``_FakeRunRegistryStore`` still declare their real ``psygnal.Signal`` class attribute so
each fake stays structurally compatible with its Protocol under ``mypy --strict``, even
though this gateway never touches it.
"""

from collections.abc import Callable
from typing import Final

from psygnal import Signal
import pytest

from ollama_llm_bench.adapters.ui_gateways import TaskEditorGateway, make_task_editor_gateway
from ollama_llm_bench.adapters.ui_gateways.protocols import ActiveRunTaskPaths
from ollama_llm_bench.backend.domain import BenchmarkRun, RunId, SettingKey
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores import RunRegistryStore, WorkspaceStore
from ollama_llm_bench.backend.stores.models import RunRegistryState, WorkspaceState

_KEY_LAST_FOLDER: Final[SettingKey] = "ui.task_editor_last_folder"
_KNOWN_RUN_ID: Final[RunId] = 42


# -- hand-written, call-recording fakes -------------------------------------------------


class _FakeAppSettingsStore:
    """Records every ``get_setting`` call; the other methods must never be hit."""

    def __init__(self, *, values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(values or {})
        self.get_setting_calls: list[SettingKey] = []

    def get_setting(self, key: SettingKey) -> str | None:
        self.get_setting_calls.append(key)
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("TaskEditorGateway must never write through AppSettingsStore")

    def list_settings(self) -> dict[SettingKey, str]:
        raise AssertionError("TaskEditorGateway must never call AppSettingsStore.list_settings")

    def get_schema_version(self) -> int:
        raise AssertionError(
            "TaskEditorGateway must never call AppSettingsStore.get_schema_version"
        )


class _FakeSettingsService:
    """Records ``set`` calls; every getter must never fire."""

    def __init__(self) -> None:
        self.set_calls: list[tuple[SettingKey, str]] = []

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        raise AssertionError("TaskEditorGateway must never call SettingsService.get_str")

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        raise AssertionError("TaskEditorGateway must never call SettingsService.get_bool")

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        raise AssertionError("TaskEditorGateway must never call SettingsService.get_int")

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        raise AssertionError("TaskEditorGateway must never call SettingsService.get_float")

    def set(self, key: SettingKey, value: str) -> None:
        self.set_calls.append((key, value))

    def upsert(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("TaskEditorGateway must never call SettingsService.upsert")


class _FakeWorkspaceStore:
    """Records ``active_workspace`` calls; ``set_active_workspace`` must never fire."""

    active_workspace_changed = Signal(WorkspaceState)

    def __init__(self, *, active_workspace: str = "task_editor") -> None:
        self._active_workspace = active_workspace
        self.active_workspace_calls = 0

    def active_workspace(self) -> str:
        self.active_workspace_calls += 1
        return self._active_workspace

    def set_active_workspace(self, name: str) -> None:
        raise AssertionError(
            "TaskEditorGateway must never call WorkspaceStore.set_active_workspace"
        )


class _FakeRunRegistryStore:
    """Records ``active_run_id`` calls; ``set_active_run`` must never fire."""

    active_run_changed = Signal(RunRegistryState)

    def __init__(self, *, active_run_id: RunId | None = None) -> None:
        self._active_run_id = active_run_id
        self.active_run_id_calls = 0

    def active_run_id(self) -> RunId | None:
        self.active_run_id_calls += 1
        return self._active_run_id

    def set_active_run(self, run_id: RunId | None) -> None:
        raise AssertionError("TaskEditorGateway must never call RunRegistryStore.set_active_run")


class _FakeActiveRunTaskPaths:
    """Records ``task_paths_for`` calls; raises if ever called (STORY-111-AC-2 uses this
    to prove the gateway short-circuits before reaching this collaborator)."""

    def __init__(self, *, paths: tuple[str, ...] = (), forbid_calls: bool = False) -> None:
        self._paths = paths
        self._forbid_calls = forbid_calls
        self.task_paths_for_calls: list[RunId] = []

    def task_paths_for(self, run_id: RunId) -> tuple[str, ...]:
        if self._forbid_calls:
            raise AssertionError(
                "TaskEditorGateway.active_run_task_paths must not call "
                "ActiveRunTaskPaths.task_paths_for when no run is active"
            )
        self.task_paths_for_calls.append(run_id)
        return self._paths


def _make_gateway(
    *,
    app_settings: AppSettingsStore | None = None,
    settings: SettingsService | None = None,
    workspace_store: WorkspaceStore | None = None,
    run_registry: RunRegistryStore | None = None,
    active_run_task_paths: ActiveRunTaskPaths | None = None,
) -> TaskEditorGateway:
    return make_task_editor_gateway(
        app_settings=app_settings if app_settings is not None else _FakeAppSettingsStore(),
        settings=settings if settings is not None else _FakeSettingsService(),
        workspace_store=workspace_store if workspace_store is not None else _FakeWorkspaceStore(),
        run_registry=run_registry if run_registry is not None else _FakeRunRegistryStore(),
        active_run_task_paths=active_run_task_paths
        if active_run_task_paths is not None
        else _FakeActiveRunTaskPaths(forbid_calls=True),
    )


# -- STORY-111-AC-1 -----------------------------------------------------------------------


def _case_get_setting_returns_none_when_unset() -> None:
    # Arrange -- an empty store: the key was never persisted.
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_setting(_KEY_LAST_FOLDER)

    # Assert
    assert app_settings.get_setting_calls == [_KEY_LAST_FOLDER]
    assert result is None


def _case_get_setting_returns_the_stored_value_unchanged() -> None:
    # Arrange
    app_settings = _FakeAppSettingsStore(values={_KEY_LAST_FOLDER: "/home/user/tasks"})
    gateway = _make_gateway(app_settings=app_settings)

    # Act
    result = gateway.get_setting(_KEY_LAST_FOLDER)

    # Assert
    assert app_settings.get_setting_calls == [_KEY_LAST_FOLDER]
    assert result == "/home/user/tasks"


def _case_set_setting_writes_through_settings_service() -> None:
    # Arrange
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    # Act
    gateway.set_setting(_KEY_LAST_FOLDER, "/home/user/other-tasks")

    # Assert
    assert settings.set_calls == [(_KEY_LAST_FOLDER, "/home/user/other-tasks")]


def _case_active_workspace_returns_the_store_value_unchanged() -> None:
    # Arrange
    workspace_store = _FakeWorkspaceStore(active_workspace="task_editor")
    gateway = _make_gateway(workspace_store=workspace_store)

    # Act
    result = gateway.active_workspace()

    # Assert
    assert workspace_store.active_workspace_calls == 1
    assert result == "task_editor"


def _case_active_run_task_paths_returns_the_collaborators_paths() -> None:
    # Arrange -- an active run whose paths the collaborator resolves.
    run_registry = _FakeRunRegistryStore(active_run_id=_KNOWN_RUN_ID)
    task_paths = ("/tasks/one.yaml", "/tasks/two.yaml")
    active_run_task_paths = _FakeActiveRunTaskPaths(paths=task_paths)
    gateway = _make_gateway(run_registry=run_registry, active_run_task_paths=active_run_task_paths)

    # Act
    result = gateway.active_run_task_paths()

    # Assert
    assert run_registry.active_run_id_calls == 1
    assert active_run_task_paths.task_paths_for_calls == [_KNOWN_RUN_ID]
    assert result == task_paths


_AC1_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("get_setting_unset", _case_get_setting_returns_none_when_unset),
    ("get_setting_stored", _case_get_setting_returns_the_stored_value_unchanged),
    ("set_setting", _case_set_setting_writes_through_settings_service),
    ("active_workspace", _case_active_workspace_returns_the_store_value_unchanged),
    ("active_run_task_paths", _case_active_run_task_paths_returns_the_collaborators_paths),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-111-AC-1

    For each of the four ``TaskEditorGateway`` methods, calling it performs exactly
    the stated interaction against its injected collaborator (the right collaborator,
    the right method, the right key/value) and returns that collaborator's value
    unchanged. Table-driven, one row per method (plus one extra row distinguishing
    "unset" from "stored" for ``get_setting``), because the variation across rows --
    which collaborator, which method name -- is a finite enumerable set and is the
    point of the criterion.
    """
    # Arrange / Act / Assert -- each case is a fully self-contained scenario so every
    # row exercises its own fresh collaborators with no shared mutable state.
    _name, run_case = case
    run_case()


# -- STORY-111-AC-2 -----------------------------------------------------------------------


def test_active_run_task_paths_is_empty_when_no_run_is_active() -> None:
    """Proves: STORY-111-AC-2

    Given a run registry reporting that no run is active, when
    ``active_run_task_paths()`` is called, then it returns an empty tuple and raises
    no exception -- the gateway short-circuits before ever calling
    ``ActiveRunTaskPaths.task_paths_for`` (the fake raises ``AssertionError`` if that
    ever happens).
    """
    # Arrange
    run_registry = _FakeRunRegistryStore(active_run_id=None)
    active_run_task_paths = _FakeActiveRunTaskPaths(forbid_calls=True)
    gateway = _make_gateway(run_registry=run_registry, active_run_task_paths=active_run_task_paths)

    # Act
    result = gateway.active_run_task_paths()

    # Assert
    assert result == ()
    assert active_run_task_paths.task_paths_for_calls == []


# -- construction side-effects -------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator() -> None:
    """Construction-side-effect-free proof (parity with STORY-105..109's own gateway
    tests; not tied to a numbered acceptance criterion for this story).

    Given fake settings, workspace-store, run-registry, and active-run-task-paths
    collaborators that record every call, when ``make_task_editor_gateway(...)`` is
    called, then the factory returns a gateway and no method was invoked on any
    collaborator.
    """
    # Arrange
    app_settings = _FakeAppSettingsStore()
    settings = _FakeSettingsService()
    workspace_store = _FakeWorkspaceStore()
    run_registry = _FakeRunRegistryStore()
    active_run_task_paths = _FakeActiveRunTaskPaths(forbid_calls=True)

    # Act
    gateway = make_task_editor_gateway(
        app_settings=app_settings,
        settings=settings,
        workspace_store=workspace_store,
        run_registry=run_registry,
        active_run_task_paths=active_run_task_paths,
    )

    # Assert
    assert gateway is not None
    assert app_settings.get_setting_calls == []
    assert settings.set_calls == []
    assert workspace_store.active_workspace_calls == 0
    assert run_registry.active_run_id_calls == 0
    assert active_run_task_paths.task_paths_for_calls == []
