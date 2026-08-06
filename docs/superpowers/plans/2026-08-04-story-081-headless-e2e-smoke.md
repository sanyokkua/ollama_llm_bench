# STORY-081 — Headless E2E Smoke Tier + NOT_READY Surfacing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Context

STORY-081 is the last unshipped story of Phase 11. Its job is to prove the fully wired
application starts, becomes usable, and shuts down cleanly — and that when the startup health
check fails every probe, the app still opens, stays clickable, tells the user what's wrong, and
refuses to start a benchmark.

Two discoveries during planning changed its shape:

1. **The story cannot be test-only as written.** It declares `owner: tester` and "this story
   exercises them end to end, it does not implement them". But two of AC-2's four clauses have
   no production code behind them:

   - **No modal is ever shown when the health check fails.** `MainWindowController._on_readiness_changed`
     (`controller.py:225-229`) sets health state and tooltip and re-renders. Nothing else. A grep
     across all of `src/` finds no readiness result that opens a dialog anywhere.
   - **The Start button stays enabled.** Readiness is not an input to `compute_start_button_state`
     (`ui/new_benchmark/_internal/view_model_select.py:251-277`), and `compose.py:285` injects a
     stub validator returning no entries. A run genuinely can't start — the Run Summary pre-flight
     refuses at `ui/common_dialogs/api.py:194-200` — but spec §5 requires more: *"The user must
     never reach an enabled run-start affordance for an environment that cannot run a benchmark."*
     An enabled button is exactly that affordance.

   Both fixes are spec-directed (`08-M_app_lifecycle.md:119`), not invented behaviour.

1. **The e2e tier isn't run by any gate.** `just check` runs `tests/unit tests/integration src`;
   `pr-gate.yml:75-81` matches. Only `just test` and the release workflow reach `tests/e2e/`. A
   smoke test no gate runs will rot silently.

**Decisions taken (confirmed with the owner):**

- Fold both production fixes into STORY-081; it becomes coder-owned.
- EC-M-5's proving test goes in `tests/integration/`, per the spec's edge-case-to-test mapping
  (`06_EDGE_CASE_TO_TEST_MAPPING.md:267`) and the precedent of every sibling lifecycle case —
  **not** `tests/e2e/` as the story's own test plan says. The story text gets corrected.
- Wire `tests/e2e/` into both `just check` and the CI PR gate.

**Goal:** Prove launch → idle → clean shutdown end to end, and make a totally-failed health check
surface an explanatory modal and a disabled Start button.

**Architecture:** Two small production changes in the UI layer (main window controller, new
benchmark view-model + controller), then a new `tests/e2e/` smoke tier with its own conftest, plus
one integration test for the NOT_READY path. No backend or adapter change; no new dependency.

**Tech Stack:** PySide6 6.8, pytest + pytest-qt, msgspec, structlog, `uv`, `just`.

## Global Constraints

- Python 3.13; `mypy --strict` is the typing authority; `ruff check --fix` **then** `ruff format`.
- Line length 100. Modern generics only (`list[str]`, `T | None`); `Final` on module constants.
- No `setStyleSheet` outside `ui/theme/`. No colour literals in widget code.
- A UI controller may hold only its own Gateway Protocol — never a backend Store/Service.
- Every test is fully annotated, returns `-> None`, and contains no `if` and no `for` in its body.
- A test proving an acceptance criterion declares `Proves: STORY-081-AC-N` on the **first line**
  of its docstring.
- Every mock is constructed with `spec=`. Never `git commit --no-verify`.
- Per-test budget: e2e under 60 seconds, integration under 30 seconds.
- `docs/v3_specification/` is read-only — never edited.

## File Structure

| File                                                                   | Responsibility                                                    |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `src/ollama_llm_bench/ui/new_benchmark/_internal/view_model_select.py` | Modify — `compute_start_button_state` gains a readiness input     |
| `src/ollama_llm_bench/ui/new_benchmark/_internal/controller.py`        | Modify — pass readiness in; subscribe to readiness changes        |
| `src/ollama_llm_bench/ui/main_window/_internal/controller.py`          | Modify — show the explanatory modal on entering NOT_READY         |
| `tests/e2e/conftest.py`                                                | Create — the e2e rig (isolated home, offline app build, teardown) |
| `tests/e2e/test_launch_idle_shutdown_smoke.py`                         | Create — AC-1                                                     |
| `tests/integration/test_launch_not_ready_gating.py`                    | Create — AC-2 + EC-M-5                                            |
| `justfile`                                                             | Modify — `check` runs e2e; new `test-e2e` recipe pins offscreen   |
| `.github/workflows/pr-gate.yml`                                        | Modify — gate runs `tests/e2e`                                    |
| `docs/stories/story-081-headless-e2e-smoke.md`                         | Modify — front-matter + corrected test plan                       |
| `CHANGELOG.md`                                                         | Modify — user-facing behaviour change                             |

**Reuse, do not reinvent:**

- `tests/integration/conftest.py:114-121` `isolated_home` — monkeypatches `HOME`/`USERPROFILE`.
  Required: on macOS `XDG_DATA_HOME` is ignored (`backend/platform/_internal/detector.py:39-58`),
  so the root `_isolate_filesystem` fixture alone does **not** isolate app data.
- `tests/integration/conftest.py:173-198` `app_data_root_all_providers_disabled` — the
  seeded-then-disabled pattern. `build_app` re-seeds builtin providers whenever the table is empty
  (`compose.py:393-394`), and those point at `localhost:11434`/`localhost:1234`. Without this the
  suite makes real network calls on a developer machine running Ollama.
- `tests/integration/conftest.py:216-274` `_drain_pending_task_runner_deliveries` — must be called
  from the **test body**, never a fixture finalizer.
- `src/ollama_llm_bench/ui/new_benchmark/testing.py` `FakeNewBenchmarkGateway` — has
  `set_readiness(snapshot)` at `:74-76` and records `recorded_notify_error_messages`.
- `src/ollama_llm_bench/adapters/notification_service/testing.py` `FakeNotificationService` —
  records `error_calls: list[tuple[str, bool]]`.
- `src/ollama_llm_bench/ui/main_window/_internal/tests/conftest.py` `make_harness` — the main
  window rig, with `FakeMainWindowGateway.set_readiness_snapshot(...)`.

______________________________________________________________________

### Task 1: Gate the Start button on a totally-failed health check

**Files:**

- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/view_model_select.py:251-277`
- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/controller.py` (imports, `_push_view_model`, `_subscribe`)
- Test: `src/ollama_llm_bench/ui/new_benchmark/tests/test_view_model_select.py` (existing file — add cases)

**Interfaces:**

- Produces: `compute_start_button_state(*, validation_entries: tuple[ValidationEntry, ...], gate_idle: bool, readiness_not_ready: bool) -> tuple[bool, str]`

- Produces: module constant `_NOT_READY_TOOLTIP: Final[str]`

- [ ] **Step 1: Find every call site before changing the signature**

```bash
cd /Users/ok/Development/GitHub/ollama_llm_bench
grep -rn "compute_start_button_state" src tests
```

Expected: the definition, one production call in `_internal/controller.py`, and existing tests.
Every one of them must be updated in this task — a missed site fails `mypy --strict`.

- [ ] **Step 2: Write the failing tests**

Add to `src/ollama_llm_bench/ui/new_benchmark/tests/test_view_model_select.py`:

```python
def test_start_button_disabled_when_readiness_is_not_ready() -> None:
    """Proves: STORY-081-AC-2

    A totally-failed health check must never leave an enabled run-start
    affordance (08-M_app_lifecycle.md section 5).
    """
    # Arrange / Act
    enabled, tooltip = compute_start_button_state(
        validation_entries=(), gate_idle=True, readiness_not_ready=True
    )
    # Assert
    assert (enabled, tooltip) == (False, "No provider is reachable — check provider settings.")


def test_start_button_enabled_when_readiness_is_usable() -> None:
    """Proves: STORY-081-AC-2

    A usable environment is left alone -- the readiness gate only fires on a
    total failure, never on DEGRADED.
    """
    # Arrange / Act
    enabled, tooltip = compute_start_button_state(
        validation_entries=(), gate_idle=True, readiness_not_ready=False
    )
    # Assert
    assert (enabled, tooltip) == (True, "")
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run pytest src/ollama_llm_bench/ui/new_benchmark/tests/test_view_model_select.py -q -p no:randomly
```

Expected: FAIL — `TypeError: compute_start_button_state() got an unexpected keyword argument 'readiness_not_ready'`.

- [ ] **Step 4: Add the constant**

In `view_model_select.py`, beside `_IN_FLIGHT_TOOLTIP` (line 40):

```python
_NOT_READY_TOOLTIP: Final[str] = "No provider is reachable — check provider settings."
```

- [ ] **Step 5: Change the function**

Replace `view_model_select.py:251-277` with:

```python
def compute_start_button_state(
    *,
    validation_entries: tuple[ValidationEntry, ...],
    gate_idle: bool,
    readiness_not_ready: bool,
) -> tuple[bool, str]:
    """Derive the Start button's ``(enabled, tooltip)`` pair (STORY-055-AC-4, AC-5; STORY-081-AC-2).

    Args:
        validation_entries: The Run Validator's current findings.
        gate_idle: Whether the single-inference gate is currently ``IDLE``.
        readiness_not_ready: Whether application readiness is ``NOT_READY`` -- every
            operability check failed, so no benchmark can run. Gated ahead of the
            in-flight check because the user must never reach an enabled run-start
            affordance for an environment that cannot run a benchmark
            (``08-M_app_lifecycle.md`` section 5). ``DEGRADED`` does not gate here:
            the spec gates only the modes whose prerequisites failed.

    Returns:
        ``(True, "")`` when nothing blocks Start and there is nothing to review;
        ``(True, "Click to review warnings before starting.")`` when only soft
        warnings remain; ``(False, <tooltip>)`` otherwise -- a joined hard-error
        message list takes precedence over the readiness and in-flight tooltips.
    """
    hard_error_messages = tuple(
        entry.message
        for entry in validation_entries
        if entry.severity is RunValidationSeverity.HARD_ERROR
    )
    if hard_error_messages:
        return False, "\n".join(hard_error_messages)
    if readiness_not_ready:
        return False, _NOT_READY_TOOLTIP
    if not gate_idle:
        return False, _IN_FLIGHT_TOOLTIP
    if validation_entries:
        return True, _REVIEW_WARNINGS_TOOLTIP
    return True, ""
```

Add `Final` to the `typing` import if it is not already present.

- [ ] **Step 6: Update the production call site**

In `controller.py`, replace lines 224-226:

```python
        readiness = self._gateway.readiness_snapshot()
        start_enabled, start_tooltip = compute_start_button_state(
            validation_entries=validation_entries,
            gate_idle=self._gate_idle,
            readiness_not_ready=readiness.overall is ReadinessState.NOT_READY,
        )
```

Add to the imports in `controller.py`:

```python
from ollama_llm_bench.backend.domain import ReadinessState
```

(If `ReadinessState` is already imported, skip. `_embedding_status()` at `:205-216` keeps its own
`readiness_snapshot()` call — it needs `embedding_reachable`, a different field, and only in
GRADED mode.)

- [ ] **Step 7: Subscribe to readiness changes so the button updates live**

Without this the button never re-evaluates when the deferred startup probe resolves. In
`controller.py`, add `SIGNAL_APP_READINESS_CHANGED` to the `backend.events` import block
(alphabetical order — it sorts before `SIGNAL_INFERENCE_ACTIVITY_CHANGED`), then add to the
subscribe block after line 102:

```python
        self._event_bus.subscribe(
            SIGNAL_APP_READINESS_CHANGED, self._on_readiness_changed, owner=self._view
        )
```

And add the handler beside the other `_on_*` handlers:

```python
    def _on_readiness_changed(self, _payload: object) -> None:
        """Re-render so the Start button reflects the new readiness (STORY-081-AC-2)."""
        self._render()
```

`owner=self._view` matches every other subscription in this controller — the owner must be the
`QWidget`, so the subscription dies with it.

- [ ] **Step 8: Update every other call site the Step 1 grep found**

Each existing test calling `compute_start_button_state` needs `readiness_not_ready=False` added.
That value preserves their current expectations exactly.

- [ ] **Step 9: Run the module's tests**

```bash
uv run pytest src/ollama_llm_bench/ui/new_benchmark -q -p no:randomly
```

Expected: PASS, no failures.

- [ ] **Step 10: Lint and typecheck the touched files**

```bash
uv run ruff check --fix src/ollama_llm_bench/ui/new_benchmark
uv run ruff format src/ollama_llm_bench/ui/new_benchmark
uv run mypy --strict src/ollama_llm_bench/ui/new_benchmark
```

Expected: all clean. Fix anything reported — "pre-existing" is not a valid reason to skip.

- [ ] **Step 11: Commit**

```bash
git add src/ollama_llm_bench/ui/new_benchmark
git commit -m "feat(story-081): gate Start on a totally-failed readiness probe"
```

______________________________________________________________________

### Task 2: Show the explanatory modal when readiness turns NOT_READY

**Files:**

- Modify: `src/ollama_llm_bench/ui/main_window/_internal/controller.py:225-229`
- Test: `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py` (existing — add cases)

**Interfaces:**

- Consumes: `NotificationService.show_error(text: str, *, blocking: bool = False) -> None`
  (`adapters/notification_service/_internal/qt_notification_service.py:33-52`) — with
  `blocking=True` this is `QMessageBox.critical(...)`, a real modal dialog.
- Produces: no new public symbol; behaviour only.

**Design note — edge-triggered, not level-triggered.** The modal fires on the *transition into*
`NOT_READY`, not on every readiness event that happens to be `NOT_READY`. The probe re-runs on
demand and after any provider/embedding settings change (`08-M_app_lifecycle.md:119`); a
level-triggered modal would re-open on every one of those, which is unusable. At construction the
service is `CHECKING` (`backend/readiness/api.py:66-69` postcondition), so the first real
`NOT_READY` always arrives as an event and always trips the edge.

- [ ] **Step 1: Write the failing tests**

Add to `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py`. Match the
existing file's harness usage — read the surrounding tests first for the exact `make_harness`
call shape and the `AppReadinessChangedEvent` construction already used at `:367-400`.

```python
def test_entering_not_ready_shows_blocking_explanatory_modal(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-081-AC-2

    A totally-failed health check is surfaced twice -- the status bar dot and a
    blocking explanatory modal (EC-M-5, 08-M_app_lifecycle.md section 5).
    """
    # Arrange
    harness = make_harness()
    # Act
    harness.event_bus.publish(
        SIGNAL_APP_READINESS_CHANGED, _not_ready_event()
    )
    # Assert
    assert [blocking for _text, blocking in harness.notifications.error_calls] == [True]


def test_repeated_not_ready_results_show_the_modal_once(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-081-AC-2

    The probe re-runs on demand and after settings changes; the modal is
    edge-triggered so a still-broken environment does not re-prompt.
    """
    # Arrange
    harness = make_harness()
    # Act
    harness.event_bus.publish(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())
    harness.event_bus.publish(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())
    # Assert
    assert len(harness.notifications.error_calls) == 1


def test_modal_text_names_the_unreachable_providers_and_the_remedy(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-081-AC-2

    The modal states what is wrong and how to correct it, not merely that
    something failed (08-M_app_lifecycle.md section 5).
    """
    # Arrange
    harness = make_harness()
    # Act
    harness.event_bus.publish(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())
    # Assert
    text = harness.notifications.error_calls[0][0]
    assert "provider-1" in text and "Settings" in text
```

Add the shared builder beside the file's other private helpers. Note the event carries
`ProviderHealthSummary` (`backend/events/models.py:603-611`), **not** the richer
`ProviderHealth` that `AppReadinessSnapshot` holds, and `checked_at` is required:

```python
def _not_ready_event() -> AppReadinessChangedEvent:
    """Build a readiness event where every operability check failed."""
    return AppReadinessChangedEvent(
        overall=ReadinessState.NOT_READY,
        per_provider=(
            ProviderHealthSummary(
                provider_id="provider-1",
                reachable=False,
                discovery_supported=True,
                model_count=None,
            ),
        ),
        embedding_reachable=False,
        checked_at="2026-01-01T00:00:00+00:00",
    )
```

Import `ProviderHealthSummary` and `AppReadinessChangedEvent` from
`ollama_llm_bench.backend.events`, and `ReadinessState` from
`ollama_llm_bench.backend.domain`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py -q -p no:randomly -k not_ready
```

Expected: FAIL — `error_calls` is empty, because nothing shows a modal today.

- [ ] **Step 3: Add the message builder**

In `controller.py`, beside the other module constants (after line 59):

```python
_NOT_READY_MODAL_TITLE: Final[str] = "No provider is reachable."
_NOT_READY_MODAL_REMEDY: Final[str] = (
    "Open Settings to check each provider's base URL and credentials, then re-run "
    "the check from the health dot in the status bar."
)
```

And a private module-level function beside `_format_health_tooltip`:

```python
def _format_not_ready_modal_text(event: AppReadinessChangedEvent) -> str:
    """Explain a totally-failed readiness probe and how to correct it (STORY-081-AC-2).

    Args:
        event: The readiness result whose overall state is ``NOT_READY``.

    Returns:
        A multi-line message naming each unreachable provider, the embedding
        model's reachability, and the remedy.
    """
    unreachable = ", ".join(
        health.provider_id for health in event.per_provider if not health.reachable
    )
    lines = [_NOT_READY_MODAL_TITLE, ""]
    if unreachable:
        lines.append(f"Unreachable providers: {unreachable}")
    if not event.embedding_reachable:
        lines.append("Embedding model: unreachable")
    lines.extend(["", _NOT_READY_MODAL_REMEDY])
    return "\n".join(lines)
```

- [ ] **Step 4: Trip the edge in the handler**

Replace `controller.py:225-229` with:

```python
    def _on_readiness_changed(self, event: AppReadinessChangedEvent) -> None:
        was_not_ready = self._health_state is ReadinessState.NOT_READY
        self._health_state = event.overall
        self._health_tooltip = _format_health_tooltip(event)
        logger.debug("readiness_changed_reflected", overall=event.overall.value)
        if event.overall is ReadinessState.NOT_READY and not was_not_ready:
            logger.info("readiness_not_ready_modal_shown")
            self._notifications.show_error(_format_not_ready_modal_text(event), blocking=True)
        self._render()
```

Ensure `ReadinessState` and `Final` are imported in `controller.py`.

Note: `show_error` text is **never** passed through `redact()` — redaction is scoped to `app.*`
logs and adapter-boundary SDK-exception wrapping, never a display surface.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
uv run pytest src/ollama_llm_bench/ui/main_window -q -p no:randomly
```

Expected: PASS across the whole module — confirm the existing NOT_READY tooltip test at
`test_controller.py:367-400` still passes.

- [ ] **Step 6: Lint and typecheck**

```bash
uv run ruff check --fix src/ollama_llm_bench/ui/main_window
uv run ruff format src/ollama_llm_bench/ui/main_window
uv run mypy --strict src/ollama_llm_bench/ui/main_window
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/ui/main_window
git commit -m "feat(story-081): surface a totally-failed readiness probe in an explanatory modal"
```

______________________________________________________________________

### Task 3: Build the e2e rig and the launch→idle→shutdown smoke test (AC-1)

**Files:**

- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_launch_idle_shutdown_smoke.py`

**Interfaces:**

- Consumes: `build_app(*, app: QApplication, loop: QEventLoop) -> AppHandle` (`compose.py:338`);
  `AppHandle.shutdown(*, timeout_ms: int) -> None` (`compose.py:193`).
- Produces: fixtures `isolated_home`, `offline_app_data_root`, `build_smoke_app`, `shutdown_handle`.

**Why `tests/e2e/` needs its own conftest:** a conftest applies only to descendants of its own
directory, so `tests/integration/conftest.py`'s rig is invisible here, and there are no
`__init__.py` files under `tests/` to import a shared helper through. The root
`tests/conftest.py` (Qt parity rig, filesystem isolation) *does* apply.

- [ ] **Step 1: Write the conftest**

Create `tests/e2e/conftest.py`. Copy the *rationale comments* from
`tests/integration/conftest.py:13-24` and `:350-355` — they explain why each piece exists.

```python
"""Fixtures for the end-to-end smoke tier: an isolated, fully offline composed app.

`tests/integration/conftest.py` holds an equivalent rig, but a conftest applies only
to descendants of its own directory and there are no `__init__.py` files under
`tests/` to import a shared helper through, so the rig is restated here.
"""

import sqlite3
import threading
from collections.abc import Callable, Generator
from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import seed_builtin_providers
from ollama_llm_bench.compose import AppHandle, build_app

_SHUTDOWN_TIMEOUT_MS = 2000
_MAX_DRAIN_PASSES = 10
_DRAIN_TICK_MS = 10


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """Drop the `colorSchemeChanged` connection each `build_app` leaves on the shared qapp.

    `ThemeManager` connects to the session-scoped `qapp.styleHints()` and production
    never disconnects it, so without this every built app leaks a connection into the
    next test.
    """
    style_hints = qapp.styleHints()
    yield
    style_hints.colorSchemeChanged.disconnect()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the resolved app-data root into `tmp_path`.

    The root `_isolate_filesystem` fixture sets only the XDG/LOCALAPPDATA variables.
    On macOS the platform detector ignores those and reads `Path.home()`, so `HOME`
    and `USERPROFILE` are the only cross-platform lever.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
```

Then the offline app-data fixture. **This is the load-bearing offline guarantee:** `build_app`
re-seeds the builtin providers whenever the catalog is empty (`compose.py:393-394`), and those
point at `localhost:11434` and `localhost:1234`. Seed them first, then disable every one, so the
readiness probe has nothing to dial.

```python
@pytest.fixture
def offline_app_data_root(isolated_home: Path) -> Path:
    """Seed the app-data directory, then disable every provider so no probe dials out.

    Leaving the catalog empty does not work: `build_app` re-seeds the builtins, which
    point at localhost:11434 / localhost:1234. On a developer machine running Ollama
    that is real network I/O from a test that looks clean on an offline CI runner.
    """
    app_data_root = isolated_home / ".local" / "share" / "OllamaLLMBench"
    app_data_root.mkdir(parents=True, exist_ok=True)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=_FixedClock())
    seed_builtin_providers(write_conn, lock)
    with lock:
        write_conn.execute("UPDATE provider SET enabled = 0")
        write_conn.commit()
    write_conn.close()
    return app_data_root
```

Before writing this, **verify against the real rig** — read
`tests/integration/conftest.py:124-198` and copy its exact table/column names, its `_FixedClock`
shape, and its `ensure_schema` call. Do not guess the `UPDATE` statement; the integration rig
already does this correctly and is the reference.

Finish with the build and teardown fixtures, mirroring
`tests/integration/conftest.py:294-334` and `:277-291`:

```python
@pytest.fixture
def build_smoke_app(
    qapp: QApplication, offline_app_data_root: Path
) -> Generator[Callable[[], AppHandle]]:
    """Build the real composed app against the offline app-data root."""
    built: list[AppHandle] = []

    def _build() -> AppHandle:
        handle = build_app(app=qapp, loop=QEventLoop())
        built.append(handle)
        return handle

    yield _build
    for handle in built:
        handle.window.close()


@pytest.fixture
def shutdown_handle() -> Callable[[AppHandle], None]:
    """Run the ordered shutdown the way production does -- window first, then handle."""

    def _shutdown(handle: AppHandle) -> None:
        handle.window.close()
        handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    return _shutdown
```

`AppHandle.shutdown` is **not** idempotent — a second call raises `sqlite3.ProgrammingError` on
the closed connection (`__main__.py:198-204`). The `build_smoke_app` finalizer therefore only
closes the window; the test calls `shutdown_handle` exactly once.

- [ ] **Step 2: Write the smoke test**

Create `tests/e2e/test_launch_idle_shutdown_smoke.py`:

```python
"""End-to-end smoke tier: the full application launched, settled, and shut down."""

import threading
import time
from collections.abc import Callable

from PySide6.QtWidgets import QMainWindow
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle

_E2E_BUDGET_S = 60.0
_IDLE_TIMEOUT_MS = 10_000
_DISPATCHER_THREAD_NAME = "pipeline-dispatcher"


def test_app_launches_reaches_idle_and_shuts_down_cleanly(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-1

    Launches the whole wired application, shows the main window, waits for the
    deferred startup readiness tick to settle it into a navigable idle state,
    then runs the ordered shutdown -- no worker thread outliving it and the
    database checkpointed and closed, inside the 60-second e2e budget.
    """
    # Arrange
    started_at = time.monotonic()
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)

    # Act
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)
    shutdown_handle(handle)

    # Assert
    assert time.monotonic() - started_at < _E2E_BUDGET_S
```

- [ ] **Step 3: Run it**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e -q -p no:randomly
```

Expected: PASS. If the Qt parity rig fails it on a `propagateSizeHints()` warning, add
`@pytest.mark.allow_qt_warnings` with a comment explaining it is offscreen-plugin behaviour —
copy the wording from `tests/integration/test_menu_opens_dialogs.py:135-139`.

- [ ] **Step 4: Split the shutdown assertions into their own test**

One test asserts one logical concept, so the thread and database checks are separate tests in the
same file. Both build and shut down their own app.

```python
def test_shutdown_leaves_no_dispatcher_thread_running(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-1

    The ordered shutdown joins the dispatcher thread; no worker outlives it.
    """
    # Arrange
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)

    # Act
    shutdown_handle(handle)

    # Assert
    assert not [t for t in threading.enumerate() if t.name == _DISPATCHER_THREAD_NAME]


def test_shutdown_closes_the_write_connection(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-1

    The database is checkpointed and closed, so any later statement is rejected.
    """
    # Arrange
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)

    # Act
    shutdown_handle(handle)

    # Assert
    with pytest.raises(sqlite3.ProgrammingError):
        handle.write_conn.execute("SELECT 1")
```

Add `import sqlite3` to the test module's imports.

The dispatcher thread is private (`_ThreadRunDispatcher._thread`), so `threading.enumerate()`
filtered on the name is the only available handle — there is no `is_alive()` accessor.

- [ ] **Step 5: Run the whole e2e tier**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e -q -p no:randomly
```

Expected: 3 passed.

- [ ] **Step 6: Prove the tier does not poison its neighbours**

Random ordering means these tests interleave with the rest of the suite. Verify before trusting:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/unit tests/integration tests/e2e -q -p no:randomly
```

Expected: no *new* failures versus the pre-existing baseline. Establish that baseline first by
running the same command with `--ignore=tests/e2e`, and compare the two counts.

- [ ] **Step 7: Lint and typecheck**

```bash
uv run ruff check --fix tests/e2e
uv run ruff format tests/e2e
uv run mypy --strict tests/e2e
```

- [ ] **Step 8: Commit**

```bash
git add tests/e2e
git commit -m "test(story-081): add the headless e2e smoke tier for launch, idle, and shutdown"
```

______________________________________________________________________

### Task 4: Prove the NOT_READY launch path (AC-2, EC-M-5)

**Files:**

- Create: `tests/integration/test_launch_not_ready_gating.py`

**Interfaces:**

- Consumes: the `tests/integration/conftest.py` rig — `build_real_app_without_enabled_providers`,
  `shutdown_handle`, `drain_task_runner_deliveries`.

**Placement:** `tests/integration/`, per `06_EDGE_CASE_TO_TEST_MAPPING.md:267` and the precedent
of EC-M-1/2/3 (`test_launch_*.py`) and EC-M-4 (`test_launch_crash_recovery.py`). The story's own
test plan says `tests/e2e/`; it is corrected in Task 6.

**How to force a totally-failed probe:** `build_app` takes no readiness parameter and there is no
`backend/readiness/testing.py`. Patch the factory in the `compose` namespace — the established
mechanism, precedent at `tests/integration/test_compose_build_app.py:239-241`:

```python
mocker.patch("ollama_llm_bench.compose.make_readiness_service", side_effect=_capture)
```

Wrap the real service so `probe_all()` returns a `NOT_READY` snapshot and emits
`SIGNAL_APP_READINESS_CHANGED`; the UI learns readiness only from the bus
(`adapters/ui_gateways/_internal/main_window/gateway.py:125-126`).

**Two different provider types are involved — do not mix them up.** The fake must return an
`AppReadinessSnapshot` whose `per_provider` holds `ProviderHealth`
(`backend/domain/models.py:621-631`: `provider_id`, `reachable`, `discovery_supported`,
`model_count`, `last_probe_ms`, `probed_at`, optional `last_error`), while the event it emits
holds `ProviderHealthSummary` (`backend/events/models.py:603-611` — no `last_probe_ms`, no
`probed_at`, plus a required `checked_at` on the event itself). Both must say
`reachable=False` and the snapshot must carry `embedding_reachable=False`, or aggregation will
not resolve `NOT_READY`.

- [ ] **Step 1: Write the test module**

Read `tests/integration/test_compose_build_app.py:216-256` first — it is the closest existing
test and shows the exact `build_app` + `window.show()` + `waitUntil` drive for the deferred tick.

Create `tests/integration/test_launch_not_ready_gating.py` with a module docstring, a fake
readiness service implementing all four `ReadinessService` methods (`snapshot`, `probe_all`,
`probe`, `record_embedding_capability_result`), and these four tests:

```python
def test_readiness_probe_total_failure_resolves_not_ready_and_gates_run_start(...) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. When every operability check fails, readiness resolves to
    NOT_READY and the Start button is disabled, so the user never reaches an
    enabled run-start affordance for an environment that cannot run a benchmark.
    """
```

Assert `start_button.isEnabled() is False`, locating it with
`handle.window.findChild(QPushButton, "new_benchmark.start_button")`.

```python
def test_readiness_probe_total_failure_shows_not_ready_in_the_status_bar(...) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. The failure is surfaced in the status bar.
    """
```

Assert on the health dot's `text_label` property being `"Not ready"`. Reuse the locator helper
from `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py:356-364` — copy it
into this module (there is no importable shared home for it).

```python
def test_readiness_probe_total_failure_shows_an_explanatory_modal(...) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. The failure is surfaced through an explanatory modal as well
    as the status bar.
    """
```

Patch `NotificationService.show_error` at its point of use and assert it was called with
`blocking=True`, rather than driving a real `QMessageBox.exec()` — a real modal blocks the test
thread and would need the `QTimer.singleShot` dismissal dance. If a real dialog is driven
instead, use `_dismiss_and_clear_modal_stack` from
`tests/integration/test_menu_opens_dialogs.py:99-132` **exactly** — skipping the modal-stack
clear has previously aborted the whole pytest process with exit 134.

```python
def test_user_interface_stays_navigable_when_not_ready(...) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. A not-ready environment gates run start but never blocks
    navigation -- the window stays visible and the workspace switch still works.
    """
```

Every test ends with `drain_task_runner_deliveries(handle)` **in the test body**, then
`shutdown_handle(handle)`. Draining from a fixture finalizer runs after pytest-qt has already
destroyed the window.

- [ ] **Step 2: Run it**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_launch_not_ready_gating.py -q -p no:randomly
```

Expected: 4 passed.

- [ ] **Step 3: Confirm it did not destabilise the suite**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/unit tests/integration tests/e2e -q -p no:randomly
```

Expected: no new failures against the Task 3 Step 6 baseline. If a *different* file starts
failing, re-run with only this file ignored before concluding it is unrelated — a
"pre-existing and unrelated" claim needs that exclusion test behind it.

- [ ] **Step 4: Lint, typecheck, commit**

```bash
uv run ruff check --fix tests/integration/test_launch_not_ready_gating.py
uv run ruff format tests/integration/test_launch_not_ready_gating.py
uv run mypy --strict tests/integration/test_launch_not_ready_gating.py
git add tests/integration/test_launch_not_ready_gating.py
git commit -m "test(story-081): prove the not-ready launch gates run start (EC-M-5)"
```

______________________________________________________________________

### Task 5: Run the e2e tier in the local and CI gates

**Files:**

- Modify: `justfile:55-56`

- Modify: `.github/workflows/pr-gate.yml:75-81`

- [ ] **Step 1: Add a pinned-offscreen e2e recipe and fold it into `check`**

In `justfile`, add beside the `test` recipe:

```make
test-e2e:
    QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e -q
```

Nothing outside the CI workflows sets `QT_QPA_PLATFORM` today, so pinning it here is what makes
a local run match CI. Then change `check` (line 55-56) to include the tier:

```make
check: lint format-check typecheck import-check arch-test
    uv run pytest tests/unit tests/integration tests/e2e src -q
```

- [ ] **Step 2: Add the tier to the PR gate**

In `.github/workflows/pr-gate.yml`, extend the existing behaviour-test step (around line 75-81)
so `tests/e2e` is collected alongside `tests/unit tests/integration`. The workflow already sets
`QT_QPA_PLATFORM: offscreen` at job level (`pr-gate.yml:12-13`), so no env change is needed.

- [ ] **Step 3: Verify the local gate**

```bash
just check
```

Expected: every stage passes, and the pytest stage's collected count is higher than before by the
number of e2e tests added.

- [ ] **Step 4: Commit**

```bash
git add justfile .github/workflows/pr-gate.yml
git commit -m "ci(story-081): run the e2e smoke tier in the local and PR gates"
```

______________________________________________________________________

### Task 6: Correct the story, regenerate traceability, update the changelog

**Files:**

- Modify: `docs/stories/story-081-headless-e2e-smoke.md`

- Modify: `CHANGELOG.md`

- Regenerate: `traceability.yaml`

- [ ] **Step 1: Update the front-matter**

The story is no longer test-only and now touches a third module:

```yaml
status: done
modules:
  - ui/main_window/
  - ui/new_benchmark/
  - backend/readiness/
owner: coder
```

`ui/new_benchmark/` must be present in `01_MODULE_INVENTORY.md` — it is. Three modules keeps the
story inside its `M` bound (up to three modules, up to six acceptance criteria).

- [ ] **Step 2: Correct the body**

Three edits, each recording a real decision rather than quietly rewriting history:

1. **In scope** — add: the explanatory modal shown on entering `NOT_READY`, and the Start button's
   readiness gate. Both were found missing during planning and are required by
   `08-M_app_lifecycle.md` section 5.
1. **Out of scope** — remove the "it does not implement them" clause, which is no longer true.
1. **Test plan** — point AC-2 at `tests/integration/test_launch_not_ready_gating.py`, and add a
   note: the story originally planned it under `tests/e2e/`, corrected to match
   `06_EDGE_CASE_TO_TEST_MAPPING.md:267` (tier `integration`) and the placement of every sibling
   lifecycle edge case.

Also record in the notes that the modal is **edge-triggered** on entering `NOT_READY`, since the
spec fixes the requirement but not the frequency, and a level-triggered modal would re-prompt on
every on-demand re-probe.

- [ ] **Step 3: Add the changelog entry**

Under `[Unreleased]` in `CHANGELOG.md` — this is user-facing behaviour, not an internal refactor:

```markdown
### Added

- A failed startup health check now explains itself in a modal dialog naming the unreachable
  providers and how to fix them.

### Fixed

- The Start button is now disabled when no provider is reachable, instead of appearing usable and
  failing at the Run Summary step.
```

- [ ] **Step 4: Regenerate and validate traceability**

```bash
just trace
just trace-check
```

Expected: `trace-check` reports zero failures. Confirm EC-M-5 no longer has an empty test list:

```bash
awk '/^  EC-M-5:/{p=1} p&&/^  EC-[A-Z]+-/&&!/^  EC-M-5:/{p=0} p' traceability.yaml
```

Expected: a populated `tests:` list. Before this story it read `tests: []`.

- [ ] **Step 5: Run the full gate**

```bash
just check
just trace-check
```

Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add docs/stories/story-081-headless-e2e-smoke.md CHANGELOG.md traceability.yaml
git commit -m "docs(story-081): mark the story done and regenerate the traceability record"
```

______________________________________________________________________

## Verification

Run in order. Every one must pass before the story is `done`.

| #   | Command                                                                                        | Expected                                 |
| --- | ---------------------------------------------------------------------------------------------- | ---------------------------------------- |
| 1   | `just check`                                                                                   | All stages green, e2e tier included      |
| 2   | `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e -q`                                         | 3 passed                                 |
| 3   | `QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_launch_not_ready_gating.py -q` | 4 passed                                 |
| 4   | `just trace-check`                                                                             | Zero failures; EC-M-5 has a proving test |
| 5   | `uv run mypy --strict src tests`                                                               | Clean                                    |
| 6   | `uv run lint-imports`                                                                          | All contracts kept                       |

**Manual check of the real behaviour** — the tests assert the mechanism; this confirms the user
actually sees it. With no LLM server running locally:

```bash
uv run python -m ollama_llm_bench
```

Expect: the window opens, the status bar dot reads **"Not ready"**, a modal appears naming the
unreachable providers and pointing at Settings, the Start button is disabled with the tooltip
"No provider is reachable — check provider settings.", and the window still switches workspaces
and opens Settings normally. Closing the window exits without hanging.

**Do not** run the manual check against a machine with Ollama or LM Studio listening on
`localhost:11434` / `localhost:1234` — readiness will resolve `READY` or `DEGRADED` and the
NOT_READY path will not be exercised.

## Risks

| Risk                                                                       | Mitigation                                                                                                                                  |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| The e2e tier destabilises other tests through the shared session `qapp`    | Task 3 Step 6 and Task 4 Step 3 explicitly diff against a pre-e2e baseline before trusting the result                                       |
| A real modal in an integration test blocks the suite                       | Patch `show_error` rather than driving `QMessageBox.exec()`; if a real dialog is unavoidable, use `_dismiss_and_clear_modal_stack` verbatim |
| The smoke test dials a local LLM server on a developer machine             | `offline_app_data_root` seeds then disables every provider; `build_app` would otherwise re-seed the localhost builtins                      |
| Changing `compute_start_button_state`'s signature silently misses a caller | Task 1 Step 1 greps every call site first; `mypy --strict` catches the rest                                                                 |
| The 60-second e2e budget is unenforced (no `pytest-timeout`)               | AC-1's test asserts its own elapsed wall-clock, so the budget is a real assertion rather than a convention                                  |
