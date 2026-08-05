# STORY-087 — Screenshot / Mockup-Conformance Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every screen the spec's screen index lists, in both the Light and Dark themes, to PNGs an operator can look at — and publish a checklist-driven written review of those captures against each screen's `mockup.html`.

**Architecture:** One self-contained pytest module, `tests/integration/test_screenshot_harness.py`, holding a screen registry, widget builders, a `QImage`-based capture primitive, and the three acceptance tests. Screens 01–05 and 09 come from **one real offline `build_app()`** (reusing the existing integration rig); the Settings dialog and the seven shared modal dialogs are constructed standalone and picked up by the app-level stylesheet. Theme selection is done by seeding the `ui.theme` setting **before** the app is built, so the application's own `ThemeManager` performs the switch — the harness never sets styling itself. Captures go to `tmp_path` in the gate and to `artifacts/screenshots/` when driven by a new `just screenshots` recipe.

**Tech Stack:** Python 3.13, PySide6 6.8, pytest + pytest-qt, `QT_QPA_PLATFORM=offscreen`.

______________________________________________________________________

## Context

`docs/v3_specification/08_Cross_Cutting/08-R_screen_index_and_traceability.md` §2 declares each screen's `mockup.html` **the visual source of truth** — "where a description and a mockup disagree on a visual detail, the mockup wins". `08-L_ui_standardization.md` §14 supplies a 13-item review checklist to apply to any UI surface.

Today neither rule is actionable. Nothing in the repository renders the real Qt widgets to anything a human can compare against a mockup, so "the mockup wins" can only be checked by eye against a running app, and the result is never written down. There is no `.grab()`, no `QScreen.grabWindow()`, and no screenshot output anywhere in the tree.

ADR-0011 (accepted 2026-07-23) decided to close this with an offscreen harness plus a documented, human-judged findings report — explicitly **not** a pixel gate, because the mockups are HTML and the widgets are Qt, so pixel equality is neither meaningful nor maintainable. Discrepancies the report surfaces become their own follow-up stories; this story never changes a widget's appearance.

Outcome: `just screenshots` produces ~28 PNGs, and `docs/development/mockup_conformance_review.md` records, per screen and per theme, a verdict against all 13 checklist items.

______________________________________________________________________

## Global Constraints

- The story file is `docs/stories/story-087-screenshot-mockup-conformance-harness.md`. It is currently `status: draft`; flip to `in-progress` when Task 1 starts and to `done` only after Task 7.
- **Never** run `git commit --no-verify`. Never delete a failing test to make the suite pass.
- Every test function is fully annotated, returns `-> None`, follows Arrange-Act-Assert, and contains **no `if` and no `for` in its body** — loops live in module-level helpers, tables of cases use `@pytest.mark.parametrize`.
- Every acceptance-criterion test's docstring **first line** is exactly `Proves: STORY-087-AC-N` — `scripts/_traceability_lib.py` matches `^\s*Proves:\s*(STORY-\d{3}-AC-\d+)\s*$` against the first docstring line only.
- No `setStyleSheet` call anywhere outside `src/ollama_llm_bench/ui/theme/`, including in this harness.
- No `asyncio`, no `anyio`, no `qasync`.
- Absolute imports only. Modern generics (`tuple[str, ...]`, `X | None`). `Final` on module constants.
- Render with **`QImage`, never `QPixmap`** — recorded project finding at `src/ollama_llm_bench/ui/results/_internal/charts_tab/painting.py:607-628`: `QImage` is pure raster and robust headless. Do not introduce a `QBuffer`-backed `QSvgGenerator` into this session; that combination was found to corrupt Qt paint-engine state and segfault a *later* image construction.
- The module carries `@pytest.mark.allow_qt_warnings` on every test that shows or resizes a widget. The root `conftest.py` Qt parity rig fails any test emitting a Qt warning, and the offscreen plugin emits `"This plugin does not support propagateSizeHints()"` on every resize-before-native-window. Precedent: `tests/integration/test_menu_opens_dialogs.py:135`, `tests/e2e/test_launch_idle_shutdown_smoke.py:60`.
- **Never call `.exec()` on a dialog in this harness.** Use `.show()`. A blocking modal in `tests/integration/` hangs the whole suite with no output — there is no `pytest-timeout` configured. This has happened before in this repo.
- Bound every verification run. The full gate takes ~2 minutes; `tests/integration` ~50 seconds. Materially longer means hung — kill and diagnose.
- Never run two full-suite verifications concurrently.

______________________________________________________________________

## The screen index — what must be captured

From `08-R` §2 (verified against `docs/v3_specification/*/mockup.html`, all 8 present):

| Screen id | Screen           | Mockup                                   |
| --------- | ---------------- | ---------------------------------------- |
| `01`      | Main Window      | `01_Main_Window/mockup.html`             |
| `02`      | New Benchmark    | `02_New_Benchmark_Widget/mockup.html`    |
| `03`      | Resume Benchmark | `03_Resume_Benchmark_Widget/mockup.html` |
| `04`      | Progress         | `04_Progress_Widget/mockup.html`         |
| `05`      | Result           | `05_Result_Widget/mockup.html`           |
| `06`      | Settings         | `06_Settings_Dialog/mockup.html`         |
| `07`      | Common Dialogs   | `07_Common_Dialogs/mockup.html`          |
| `09`      | Task Editor      | `09_Task_Editor/mockup.html`             |

There is no screen `08`. Screen `07` is seven distinct dialogs, so it gets **seven** captures; every other screen gets one. **14 captures per theme, 28 total.**

______________________________________________________________________

## File structure

| File                                                                     | Responsibility                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Create `tests/integration/test_screenshot_harness.py`                    | Everything: screen registry, builders, capture primitive, all tests. Single file because `tests/` has **no `__init__.py` anywhere** — cross-file imports between test modules are impossible by design, and a subdirectory `conftest.py` would not serve a test at `tests/integration/`. Restating a rig is the documented house style here (both existing conftests say so explicitly). |
| Create `docs/development/mockup_conformance_review.md`                   | The findings report. `docs/development` is already covered by `just format`'s `mdformat` run, so it stays formatted automatically.                                                                                                                                                                                                                                                       |
| Modify `justfile`                                                        | Add the `screenshots` recipe.                                                                                                                                                                                                                                                                                                                                                            |
| Modify `docs/stories/story-087-screenshot-mockup-conformance-harness.md` | Status transitions and Definition-of-done checkboxes.                                                                                                                                                                                                                                                                                                                                    |
| Modify `traceability.yaml`                                               | Regenerated by `just trace` — never hand-edited.                                                                                                                                                                                                                                                                                                                                         |

No `.gitignore` change: `.gitignore:702` already ignores `artifacts/` unanchored, at any depth.

No `CHANGELOG.md` entry: this is test tooling plus a process document, not a public-API or behaviour change (`.claude/rules/repository-documentation.md`).

______________________________________________________________________

### Task 1: Capture primitive, artifacts destination, and the `just screenshots` recipe

**Files:**

- Create: `tests/integration/test_screenshot_harness.py`
- Modify: `justfile`

**Interfaces:**

- Produces: `_ARTIFACTS_ENV_VAR: Final[str]`, `_artifacts_root(tmp_path: Path) -> Path`, `_capture(widget: QWidget, *, path: Path) -> None`.

- [ ] **Step 1: Flip the story to `in-progress`**

In `docs/stories/story-087-screenshot-mockup-conformance-harness.md`, change the front-matter line `status: draft` to `status: in-progress`.

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_screenshot_harness.py`:

```python
"""Offscreen screenshot harness for the 08-R §2 screen index (STORY-087).

Renders every screen the screen index enumerates, in both the Light and the Dark
theme, to PNGs in an artifacts directory, and validates the structure of the
mockup-conformance findings report that reviews those captures.

This is a review tool, not a pass/fail pixel gate (ADR-0011): nothing here
asserts that a capture matches its ``mockup.html``. The judgement lives in
``docs/development/mockup_conformance_review.md``, written by a human reading the
captures beside the mockups; these tests only prove the captures were produced
and that the report records a verdict for every checklist item.

Run it for review with ``just screenshots``, which points the artifacts directory
at ``artifacts/screenshots/`` instead of the per-test temporary directory.
"""

import os
from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot

_ARTIFACTS_ENV_VAR: Final[str] = "SCREENSHOT_ARTIFACTS_DIR"


def _artifacts_root(tmp_path: Path) -> Path:
    """Return the directory captures are written to.

    Honours the ``SCREENSHOT_ARTIFACTS_DIR`` environment variable so ``just
    screenshots`` can collect reviewable output, and falls back to the test's own
    temporary directory so the pull-request gate stays hermetic.
    """
    override = os.environ.get(_ARTIFACTS_ENV_VAR)
    if override:
        return Path(override)
    return tmp_path / "screenshots"


def _capture(widget: QWidget, *, path: Path) -> None:
    """Render ``widget`` to a PNG at ``path``.

    Uses ``QImage`` rather than ``QPixmap`` -- pure raster, no platform pixmap
    backend, which is the project's recorded choice for offscreen rendering
    (``ui/results/_internal/charts_tab/painting.py``).
    """
    size = widget.size()
    image = QImage(size.width(), size.height(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), format=b"PNG"):
        message = f"failed to write capture to {path}"
        raise AssertionError(message)


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_capture_writes_a_decodable_png_of_the_widget_size(
    qtbot: QtBot, tmp_path: Path
) -> None:
    # Arrange
    widget = QLabel("capture me")
    qtbot.addWidget(widget)
    widget.resize(320, 200)
    widget.show()
    qtbot.wait(0)
    destination = _artifacts_root(tmp_path) / "probe.png"

    # Act
    _capture(widget, path=destination)

    # Assert
    assert QImage(str(destination)).size() == widget.size()
```

- [ ] **Step 3: Run it to make sure it fails**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected before Step 2's file exists: collection error. After Step 2 it should already **pass** — this step is the sanity check that the offscreen render path works at all on this machine. If it fails with a blank/zero-size image, stop and diagnose before continuing; every later task depends on this primitive.

- [ ] **Step 4: Add the justfile recipe**

Append to `justfile`, matching the indentation and comment style of the neighbouring `test-e2e` recipe:

```make
# Capture every spec screen in both themes into artifacts/ for the mockup-conformance review (STORY-087).
screenshots:
    QT_QPA_PLATFORM=offscreen SCREENSHOT_ARTIFACTS_DIR=artifacts/screenshots uv run pytest tests/integration/test_screenshot_harness.py -q
```

- [ ] **Step 5: Verify the recipe runs and writes outside tmp_path**

```bash
just screenshots && ls artifacts/screenshots/
```

Expected: `probe.png` present. (Only the probe exists at this point.)

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_screenshot_harness.py justfile docs/stories/story-087-screenshot-mockup-conformance-harness.md
git commit -m "test(screenshots): add the offscreen capture primitive and just screenshots recipe"
```

______________________________________________________________________

### Task 2: The screen registry and the app-derived screens (01–05, 09)

**Files:**

- Modify: `tests/integration/test_screenshot_harness.py`

**Interfaces:**

- Consumes: `_capture`, `_artifacts_root` from Task 1.
- Produces: `_SCREEN_INDEX_IDS: Final[tuple[str, ...]]`, `_CAPTURE_IDS: Final[tuple[str, ...]]`, `_screen_id_of(capture_id: str) -> str`, `_capture_app_screens(*, qtbot: QtBot, handle: AppHandle, destination: Path) -> None`.

Six of the eight screens come out of one real `build_app()`. `compose.py`'s `_make_benchmark_workspace` builds a `QSplitter` whose three panes are the left `QTabWidget` (objectName `benchmark_left_panel`, tabs "New Benchmark" and "Resume"), the Progress widget, and the Result widget. The workspace region is a `QStackedWidget` with objectName `workspace_region`, and `compose.py` primes **both** pages (`switch_to(priming_workspace)` then `switch_to(active_workspace)`), so the Task Editor page already exists in the stack.

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_screenshot_harness.py` (imports merged into the existing block):

```python
from collections.abc import Callable

from PySide6.QtWidgets import QSplitter, QStackedWidget, QTabWidget

from ollama_llm_bench.compose import AppHandle

_SCREEN_INDEX_IDS: Final[tuple[str, ...]] = ("01", "02", "03", "04", "05", "06", "07", "09")

_CAPTURE_IDS: Final[tuple[str, ...]] = (
    "01_main_window",
    "02_new_benchmark",
    "03_resume_benchmark",
    "04_progress",
    "05_result",
    "06_settings",
    "07_common_dialogs__rename_run",
    "07_common_dialogs__run_summary",
    "07_common_dialogs__resume_summary",
    "07_common_dialogs__retry_selection",
    "07_common_dialogs__error",
    "07_common_dialogs__about",
    "07_common_dialogs__generate_analysis",
    "09_task_editor",
)

_WINDOW_SIZE: Final[tuple[int, int]] = (1600, 1000)


def _screen_id_of(capture_id: str) -> str:
    """Return the 08-R §2 screen-index id a capture belongs to."""
    return capture_id[:2]


def _covered_screen_ids() -> frozenset[str]:
    """Return every screen-index id the capture registry covers."""
    return frozenset(_screen_id_of(capture_id) for capture_id in _CAPTURE_IDS)


def test_capture_registry_covers_every_screen_in_the_screen_index() -> None:
    # Arrange / Act / Assert
    assert _covered_screen_ids() == frozenset(_SCREEN_INDEX_IDS)


def _task_editor_page(stack: QStackedWidget, *, benchmark: QWidget) -> QWidget:
    """Return the workspace page that is not the benchmark splitter."""
    pages = [stack.widget(index) for index in range(stack.count())]
    others = [page for page in pages if page is not benchmark]
    if len(others) != 1:
        message = f"expected exactly one non-benchmark workspace page, got {len(others)}"
        raise AssertionError(message)
    return others[0]


def _capture_app_screens(*, qtbot: QtBot, handle: AppHandle, destination: Path) -> None:
    """Capture screens 01-05 and 09 from a fully built application."""
    window = handle.window
    window.resize(*_WINDOW_SIZE)
    window.show()
    qtbot.wait(0)
    _capture(window, path=destination / "01_main_window.png")

    left_panel = window.findChild(QTabWidget, "benchmark_left_panel")
    splitter = left_panel.parentWidget()
    while splitter is not None and not isinstance(splitter, QSplitter):
        splitter = splitter.parentWidget()
    if splitter is None:
        message = "benchmark workspace splitter not found under the main window"
        raise AssertionError(message)

    left_panel.setCurrentIndex(0)
    qtbot.wait(0)
    _capture(left_panel.widget(0), path=destination / "02_new_benchmark.png")
    left_panel.setCurrentIndex(1)
    qtbot.wait(0)
    _capture(left_panel.widget(1), path=destination / "03_resume_benchmark.png")
    left_panel.setCurrentIndex(0)

    _capture(splitter.widget(1), path=destination / "04_progress.png")
    _capture(splitter.widget(2), path=destination / "05_result.png")

    stack = window.findChild(QStackedWidget, "workspace_region")
    task_editor = _task_editor_page(stack, benchmark=splitter)
    stack.setCurrentWidget(task_editor)
    qtbot.wait(0)
    _capture(task_editor, path=destination / "09_task_editor.png")
    stack.setCurrentWidget(splitter)


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_app_derived_screens_are_captured_from_one_real_app_build(
    qtbot: QtBot,
    tmp_path: Path,
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    # Arrange
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    destination = _artifacts_root(tmp_path) / "probe-app"

    # Act
    _capture_app_screens(qtbot=qtbot, handle=handle, destination=destination)
    drain_task_runner_deliveries(handle)

    # Assert
    assert {path.name for path in destination.glob("*.png")} == {
        "01_main_window.png",
        "02_new_benchmark.png",
        "03_resume_benchmark.png",
        "04_progress.png",
        "05_result.png",
        "09_task_editor.png",
    }
```

- [ ] **Step 2: Run the tests**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected: 3 passed. If `_task_editor_page` raises "expected exactly one non-benchmark workspace page", read `compose.py`'s `workspace_controller.switch_to(...)` priming pair and confirm both pages are primed at build time.

- [ ] **Step 3: Eyeball the six captures**

```bash
just screenshots && ls artifacts/screenshots/probe-app/
```

Then open two of them (`01_main_window.png`, `09_task_editor.png`) and confirm they are not blank. A blank capture means the widget was never laid out — add a `qtbot.wait(0)` after the relevant `show()`/`setCurrentWidget()`.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_screenshot_harness.py
git commit -m "test(screenshots): capture screens 01-05 and 09 from one real app build"
```

______________________________________________________________________

### Task 3: The Settings dialog capture (screen 06)

**Files:**

- Modify: `tests/integration/test_screenshot_harness.py`

**Interfaces:**

- Produces: `_build_settings_dialog(*, qtbot: QtBot) -> QDialog`.

The Settings dialog is not mounted in the window — `compose.py` builds it lazily inside `_open_settings()` and calls `.exec()`, which would block. Build it standalone instead. `FakeSettingsGateway` already exists at `src/ollama_llm_bench/ui/settings_dialog/testing.py` and takes no required constructor arguments; `make_settings_dialog` calls `controller.load()` and `probe_all()` at construction, both inert against the fake. Styling still comes from the app-level stylesheet, so the dialog renders in whichever theme the app applied.

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_screenshot_harness.py`:

```python
from PySide6.QtWidgets import QDialog

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.ui.settings_dialog import (
    SettingsDialogCollaborators,
    make_settings_dialog,
)
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway

_DIALOG_SIZE: Final[tuple[int, int]] = (900, 700)


def _build_settings_dialog(*, qtbot: QtBot) -> QDialog:
    """Construct the Settings dialog standalone, shown but never exec()'d."""
    collaborators = SettingsDialogCollaborators(
        gateway=FakeSettingsGateway(),
        event_bus=make_qt_event_bus_deliverer(),
        native_pickers=FakeNativePickers(),
        clipboard=make_clipboard(),
        file_system_actions=make_file_system_actions(),
        notifications=FakeNotificationService(),
    )
    dialog = make_settings_dialog(collaborators=collaborators)
    qtbot.addWidget(dialog)
    dialog.resize(*_DIALOG_SIZE)
    dialog.show()
    qtbot.wait(0)
    return dialog


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_settings_dialog_is_constructed_standalone_without_exec(qtbot: QtBot) -> None:
    # Arrange / Act
    dialog = _build_settings_dialog(qtbot=qtbot)

    # Assert
    assert dialog.isVisible()
```

**Before running:** confirm the exact import paths and factory names for `make_clipboard` and `make_file_system_actions` by reading `src/ollama_llm_bench/adapters/clipboard/api.py` and `src/ollama_llm_bench/adapters/file_system_actions/api.py`, and confirm the exact field names of `SettingsDialogCollaborators` in `src/ollama_llm_bench/ui/settings_dialog/models.py`. `theme_manager` and `platform_kind` are optional there (default `None` / `PlatformKind.UNKNOWN`) — leave them at their defaults; the theme is applied at the `QApplication` level, not per-dialog.

- [ ] **Step 2: Run the test**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_screenshot_harness.py
git commit -m "test(screenshots): build the Settings dialog standalone for capture"
```

______________________________________________________________________

### Task 4: The seven shared modal dialogs (screen 07)

**Files:**

- Modify: `tests/integration/test_screenshot_harness.py`

**Interfaces:**

- Produces: `_build_common_dialogs(*, qtbot: QtBot) -> dict[str, QDialog]` keyed by the `07_common_dialogs__*` capture ids.

This is the largest task. Read `src/ollama_llm_bench/ui/common_dialogs/api.py` and `protocols.py` in full before starting. Three factories **return `None`** unless their gateway yields non-empty data — a `None` return is the most likely failure mode here:

| Factory                       | Returns `None` when                                                                                                                                 |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make_run_summary_dialog`     | preflight fails (any HARD_ERROR validation entry, no reachable test-model provider, judge enabled with no judge model, unreachable embedding model) |
| `make_resume_summary_dialog`  | `gateway.resumable_results(run_id)` is empty                                                                                                        |
| `make_retry_selection_dialog` | `gateway.list_results(run_id)` is empty                                                                                                             |

No `testing.py` fake exists for any of `RunSummaryGateway`, `RenameRunGateway`, `ResumeSummaryGateway`, `RetrySelectionGateway`, or `RunAnalysisDispatcher`. Each is small — hand-roll a private stub in this module per Protocol, satisfying it structurally (these are `typing.Protocol`, so no inheritance is needed).

- [ ] **Step 1: Write the stub gateways**

The Protocols, verbatim from `src/ollama_llm_bench/ui/common_dialogs/protocols.py`:

```python
class _StubRenameRunGateway:
    """Structural ``RenameRunGateway`` returning one canned run header."""

    def __init__(self, *, runs: tuple[BenchmarkRun, ...]) -> None:
        self._runs = runs

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return self._runs

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        return None


class _StubResumeSummaryGateway:
    """Structural ``ResumeSummaryGateway`` with non-empty resumable results."""

    def __init__(
        self, *, run: BenchmarkRun, results: tuple[BenchmarkResult, ...]
    ) -> None:
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
```

Add a `_canned_provider() -> ProviderConfig` helper beside the other canned-data helpers in Step 2 — read `ProviderConfig`'s field list in `src/ollama_llm_bench/backend/domain/models.py` and construct one entry with `provider_id=_PROVIDER_ID`, `enabled=True`, and a display name. Never put a literal API key in it; `ProviderConfig` stores an environment-variable *name*, never a value.

`FakeRunValidator` already exists at `src/ollama_llm_bench/ui/new_benchmark/testing.py` — import it rather than writing another stub. Confirm it returns an empty entry tuple by default; a `HARD_ERROR` entry would make `make_run_summary_dialog` return `None`.

`RunSummaryGateway` needs `readiness_snapshot() -> AppReadinessSnapshot` and `start_run(request: RunStartRequest) -> RunId`. `_preflight_passes` (`ui/common_dialogs/api.py:339`) returns `False` on any of: a `HARD_ERROR` validation entry; no `request.test_models` entry whose `provider_id` is reachable in the snapshot; `judge_analysis_enabled` with `judge_model is None`; an `embedding_model` set while `readiness.embedding_reachable` is `False`. The canned data below satisfies all four.

```python
class _StubRunSummaryGateway:
    """Structural ``RunSummaryGateway`` whose readiness passes preflight."""

    def __init__(self, *, readiness: AppReadinessSnapshot) -> None:
        self._readiness = readiness

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def start_run(self, request: RunStartRequest) -> RunId:
        return 1
```

- [ ] **Step 2: Write the canned domain data**

All four structs are frozen `msgspec.Struct`s from `ollama_llm_bench.backend.domain` — construct them directly, never mock them. Field lists verified against `backend/domain/models.py`:

```python
_PROVIDER_ID: Final[str] = "ollama_local"
_MODEL_NAME: Final[str] = "llama3.1:8b"
_RUN_ID: Final[int] = 1
_TIMESTAMP: Final[str] = "2026-08-05T12:00:00Z"


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
        test_models=(
            ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),
        ),
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
```

`ProviderHealth.probed_at` and `last_probe_ms` are required and take plain integers; `BenchmarkRun.schema_version` and `created_at` are required with no default. If `msgspec` raises a `ValidationError` on any constrained field (`NonEmptyStr`, `ProviderIdStr`, `DurationMs`), read the `Annotated[..., msgspec.Meta(...)]` alias in `backend/domain/models.py` and adjust the literal — do not relax the alias.

- [ ] **Step 3: Write the seven builders and the failing test**

```python
def _build_common_dialogs(*, qtbot: QtBot) -> dict[str, QDialog]:
    """Construct all seven shared modal dialogs, shown but never exec()'d."""
    bus = make_qt_event_bus_deliverer()
    clipboard = make_clipboard()
    dialogs: dict[str, QDialog] = {
        "07_common_dialogs__about": make_about_dialog(
            collaborators=AboutDialogCollaborators(
                clipboard=clipboard,
                file_system_actions=make_file_system_actions(),
                event_bus=bus,
            ),
            version="0.0.0",
            data_folder_path="/tmp/ollama-llm-bench",
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
            gateway=_StubResumeSummaryGateway(
                run=_canned_run(), results=_canned_results()
            ),
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
                event_bus=bus,
            ),
        ),
    }
    for capture_id, dialog in dialogs.items():
        if dialog is None:
            message = f"{capture_id} factory returned None; its gateway data is insufficient"
            raise AssertionError(message)
        qtbot.addWidget(dialog)
        dialog.resize(*_DIALOG_SIZE)
        dialog.show()
    qtbot.wait(0)
    return dialogs


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_every_shared_modal_dialog_is_constructed_for_capture(qtbot: QtBot) -> None:
    # Arrange
    expected = frozenset(
        capture_id for capture_id in _CAPTURE_IDS if capture_id.startswith("07_")
    )

    # Act
    dialogs = _build_common_dialogs(qtbot=qtbot)

    # Assert
    assert frozenset(dialogs) == expected
```

Note the `for` loop and `if` sit in the **helper**, not the test body — that is what the no-loops-in-tests rule permits.

- [ ] **Step 4: Run the test**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected: 5 passed. A `None`-return assertion failure names exactly which dialog's stub data is too thin.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_screenshot_harness.py
git commit -m "test(screenshots): build all seven shared modal dialogs for capture"
```

______________________________________________________________________

### Task 5: The two acceptance tests — a full capture pass per theme

**Files:**

- Modify: `tests/integration/test_screenshot_harness.py`

**Interfaces:**

- Consumes: everything from Tasks 1–4.
- Produces: `_capture_every_screen(...) -> frozenset[str]`.

The theme is selected by seeding the `ui.theme` setting **before** `build_app()` runs, so the application's own `ThemeManager` applies it at construction — the harness performs no styling. This matters: `ThemeManager._reapply_if_changed` short-circuits when the *resolved* `ActiveThemeKind` is unchanged, so driving `set_theme_setting` after the fact is not reliably observable. Seeding pre-build sidesteps that entirely.

Because styling is applied at the `QApplication` level, the standalone dialogs built after the app inherit the same theme automatically.

- [ ] **Step 1: Write the two failing acceptance tests**

```python
_EXPECTED_CAPTURES: Final[frozenset[str]] = frozenset(
    f"{capture_id}.png" for capture_id in _CAPTURE_IDS
)


def _capture_every_screen(
    *,
    qtbot: QtBot,
    handle: AppHandle,
    destination: Path,
) -> frozenset[str]:
    """Capture every screen in the index and return the filenames written."""
    _capture_app_screens(qtbot=qtbot, handle=handle, destination=destination)
    _capture(
        _build_settings_dialog(qtbot=qtbot), path=destination / "06_settings.png"
    )
    for capture_id, dialog in _build_common_dialogs(qtbot=qtbot).items():
        _capture(dialog, path=destination / f"{capture_id}.png")
    return frozenset(path.name for path in destination.glob("*.png"))


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_harness_captures_every_screen_in_light_theme(
    qtbot: QtBot,
    tmp_path: Path,
    app_data_root_all_providers_disabled: Path,
    seed_setting: Callable[..., None],
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-087-AC-1

    Running the offscreen harness under the Light theme writes one PNG per screen
    enumerated in the 08-R §2 screen index into the artifacts directory.
    """
    # Arrange
    seed_setting(app_data_root_all_providers_disabled, key="ui.theme", value="light")
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    destination = _artifacts_root(tmp_path) / "light"

    # Act
    written = _capture_every_screen(
        qtbot=qtbot, handle=handle, destination=destination
    )
    drain_task_runner_deliveries(handle)

    # Assert
    assert written == _EXPECTED_CAPTURES


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_harness_captures_every_screen_in_dark_theme(
    qtbot: QtBot,
    tmp_path: Path,
    app_data_root_all_providers_disabled: Path,
    seed_setting: Callable[..., None],
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-087-AC-2

    Running the offscreen harness under the Dark theme writes one PNG per screen
    enumerated in the 08-R §2 screen index into the artifacts directory.
    """
    # Arrange
    seed_setting(app_data_root_all_providers_disabled, key="ui.theme", value="dark")
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    destination = _artifacts_root(tmp_path) / "dark"

    # Act
    written = _capture_every_screen(
        qtbot=qtbot, handle=handle, destination=destination
    )
    drain_task_runner_deliveries(handle)

    # Assert
    assert written == _EXPECTED_CAPTURES
```

**`drain_task_runner_deliveries` must be called from the test body, never a fixture finalizer** — pytest-qt's `_close_widgets` runs before fixture teardown. The reasoning is documented at length in `tests/integration/conftest.py:216-274`.

- [ ] **Step 2: Run both acceptance tests**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected: 7 passed, in well under 60 seconds total. If either test exceeds the 30-second integration budget, split the dialog captures into their own test rather than marking it `slow`.

- [ ] **Step 3: Verify the negative control**

Temporarily change one entry of `_CAPTURE_IDS` (e.g. `"09_task_editor"` → `"09_task_editorX"`) and re-run. Both acceptance tests must **fail** on the set comparison. Revert the change and re-run to green. Do **not** verify by deleting an assertion — falsify the condition instead.

- [ ] **Step 4: Produce the real artifacts for the review**

```bash
just screenshots && ls artifacts/screenshots/light artifacts/screenshots/dark
```

Expected: 14 PNGs in each directory. Confirm the Light and Dark versions of `01_main_window.png` genuinely differ — if they look identical, the theme seeding did not take effect and Task 6 would review a lie.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_screenshot_harness.py
git commit -m "test(screenshots): capture every spec screen in the Light and Dark themes"
```

______________________________________________________________________

### Task 6: The mockup-conformance findings report

**Files:**

- Create: `docs/development/mockup_conformance_review.md`
- Modify: `tests/integration/test_screenshot_harness.py`

**Interfaces:**

- Produces: `_REPORT_PATH: Final[Path]`, `_CHECKLIST_ITEMS: Final[tuple[str, ...]]`, `_VERDICTS: Final[frozenset[str]]`, `_report_section(text, *, screen_id, theme) -> str`, `_verdicts_in(section: str) -> tuple[str, ...]`.

The 13 checklist items are `08-L` §14 verbatim. The verdicts are **written by hand** after looking at each PNG beside its `mockup.html`; the test validates coverage only, never the judgement (ADR-0011: "a review tool and process artifact, not a pass/fail pixel gate"). The closest precedent for a test asserting on a Markdown document is `tests/architecture/test_circuit_breaker_spec_reflects_dd71.py`.

- [ ] **Step 1: Write the report skeleton**

Create `docs/development/mockup_conformance_review.md`. Header, then **one `## Screen NN — <name>` section per screen id, each with a `### Screen NN — Light` and a `### Screen NN — Dark` subsection**, each subsection carrying the 13-row table. Sixteen tables total.

```markdown
# Mockup conformance review

Each screen the specification's screen index lists is rendered by the offscreen
screenshot harness in both themes and reviewed here against that screen's
`mockup.html`, using the standardization review checklist.

Regenerate the captures with `just screenshots`; they land in
`artifacts/screenshots/light/` and `artifacts/screenshots/dark/` (git-ignored).

The mockup is the visual source of truth: where a capture and its mockup
disagree on a visual detail, the mockup is right. This document records what was
observed. It never changes a widget — a real discrepancy becomes its own story.

Verdicts: `conforms`, `discrepancy`, `not-applicable`. Any `discrepancy` row
must say what differs in Notes.

## Screen 01 — Main Window

Mockup: `docs/v3_specification/01_Main_Window/mockup.html`

### Screen 01 — Light

Capture: `artifacts/screenshots/light/01_main_window.png`

| # | Checklist item | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out | conforms |  |
| 2 | Any disabled control is genuinely transient and carries a tooltip explaining why | conforms |  |
| 3 | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip | conforms |  |
| 4 | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |  |
| 5 | The running pill is present only while a run is in a non-terminal stage | conforms |  |
| 6 | The status bar is present with the version string on the right | conforms |  |
| 7 | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most | not-applicable | No dialog on this surface. |
| 8 | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style | conforms |  |
| 9 | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip | not-applicable | No field rows on this surface. |
| 10 | No glyph-only control without a hover tooltip; every control has an accessible name | conforms |  |
| 11 | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals | conforms |  |
| 12 | Every state shown by colour is also shown by text and/or glyph | conforms |  |
| 13 | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes | conforms |  |

### Screen 01 — Dark

Capture: `artifacts/screenshots/dark/01_main_window.png`

| # | Checklist item | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out | conforms |  |
```

…repeat rows 1–13, then the same two-subsection shape for screens 02, 03, 04, 05, 06, 07, 09.

The **Screen 07** section covers the dialog family as a whole; name each of the seven per-dialog captures in its Notes where a verdict differs between them.

- [ ] **Step 2: Actually review — this is the substance of the story**

For each of the 8 screens, open the Light capture, the Dark capture, and the screen's `mockup.html` side by side. Walk all 13 items. Replace the placeholder `conforms` values with what you actually observe. Every `discrepancy` needs a Notes entry saying what differs. Do not leave a row you did not genuinely check — an unchecked `conforms` is worse than an honest `discrepancy`, because it makes the review look complete when it is not.

List every `discrepancy` found in a closing `## Follow-ups` section, each with a one-line description, so a later story can pick them up. This story fixes none of them.

- [ ] **Step 3: Write the failing structural test**

```python
import re

_REPORT_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "development"
    / "mockup_conformance_review.md"
)

_VERDICTS: Final[frozenset[str]] = frozenset(
    {"conforms", "discrepancy", "not-applicable"}
)

_CHECKLIST_ITEM_COUNT: Final[int] = 13

_ROW_RE: Final[re.Pattern[str]] = re.compile(
    r"^\|\s*(\d{1,2})\s*\|[^|]*\|\s*([a-z-]+)\s*\|", re.MULTILINE
)

_THEMES: Final[tuple[str, ...]] = ("light", "dark")

_REPORT_CASES: Final[tuple[tuple[str, str], ...]] = tuple(
    (screen_id, theme) for screen_id in _SCREEN_INDEX_IDS for theme in _THEMES
)

_REPORT_CASE_IDS: Final[tuple[str, ...]] = tuple(
    f"{screen_id}-{theme}" for screen_id, theme in _REPORT_CASES
)


def _report_section(text: str, *, screen_id: str, theme: str) -> str:
    """Return the report text for one screen under one theme."""
    heading = re.compile(
        rf"^###\s+Screen\s+{screen_id}\b.*\b{theme}\b.*$", re.MULTILINE | re.IGNORECASE
    )
    match = heading.search(text)
    if match is None:
        message = f"no '### Screen {screen_id} ... {theme}' section in the report"
        raise AssertionError(message)
    rest = text[match.end() :]
    following = re.search(r"^##+\s", rest, re.MULTILINE)
    return rest if following is None else rest[: following.start()]


def _verdicts_in(section: str) -> tuple[str, ...]:
    """Return the verdict cell of every numbered checklist row in ``section``."""
    return tuple(match.group(2) for match in _ROW_RE.finditer(section))


@pytest.mark.parametrize(("screen_id", "theme"), _REPORT_CASES, ids=_REPORT_CASE_IDS)
def test_mockup_conformance_report_covers_every_screen(
    screen_id: str, theme: str
) -> None:
    """Proves: STORY-087-AC-3

    The findings report records a valid standardization-review-checklist verdict
    for all thirteen 08-L §14 items, for every screen in the screen index, under
    both the Light and the Dark theme.
    """
    # Arrange
    section = _report_section(
        _REPORT_PATH.read_text(encoding="utf-8"), screen_id=screen_id, theme=theme
    )

    # Act
    verdicts = _verdicts_in(section)

    # Assert
    assert (len(verdicts), tuple(v for v in verdicts if v not in _VERDICTS)) == (
        _CHECKLIST_ITEM_COUNT,
        (),
    )
```

- [ ] **Step 4: Run it**

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected: 23 passed (7 + 16 parametrized report cases). A failure names the exact `screen-theme` pair whose table is short a row or carries an unrecognised verdict.

- [ ] **Step 5: Confirm mdformat leaves the report parseable**

```bash
just format && QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q
```

`just format` runs `mdformat` over `docs/development`. If it rewrites the tables in a way the regex no longer matches, loosen `_ROW_RE` rather than fighting the formatter.

- [ ] **Step 6: Commit**

```bash
git add docs/development/mockup_conformance_review.md tests/integration/test_screenshot_harness.py
git commit -m "docs(screenshots): add the mockup-conformance findings report and its coverage test"
```

______________________________________________________________________

### Task 7: Gate, traceability, and story closeout

**Files:**

- Modify: `docs/stories/story-087-screenshot-mockup-conformance-harness.md`

- Modify: `traceability.yaml` (generated)

- [ ] **Step 1: Lint and format the touched files**

```bash
just lint && just format-check
```

Fix every finding in a file you touched. "Pre-existing" is not a valid reason to skip one.

- [ ] **Step 2: Run the full gate**

This change adds an EventBus-carrying app build and new widget construction inside `tests/integration/`, and it touches the `justfile` — that is squarely inside the blast radius that requires the full gate, not just the module's own tests.

```bash
uv run pytest tests/unit tests/integration tests/e2e src -q
```

Expected: green, in roughly 2 minutes. Materially longer means something is hung — kill it and diagnose; the most likely cause is a dialog that ended up `.exec()`-ing.

Do not run this concurrently with any other full-suite run.

- [ ] **Step 3: Regenerate and validate traceability**

```bash
just trace && just trace-check
```

Expected: `trace-check` reports zero failures. If it reports an orphan test, the `Proves:` line is not the first line of that test's docstring.

- [ ] **Step 4: Close out the story file**

In `docs/stories/story-087-screenshot-mockup-conformance-harness.md`: set `status: done`, and tick every Definition-of-done checkbox. Add a short note recording any `discrepancy` the report found, naming it as a follow-up rather than a defect of this story.

- [ ] **Step 5: Commit**

```bash
git add docs/stories/story-087-screenshot-mockup-conformance-harness.md traceability.yaml
git commit -m "docs(story-087): mark the screenshot/mockup-conformance harness story done"
```

______________________________________________________________________

## Verification

| What                             | How                                                                                       | Expected                                                       |
| -------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| The capture path works headless  | `just screenshots`                                                                        | 14 PNGs each in `artifacts/screenshots/light/` and `.../dark/` |
| The captures are real, not blank | Open `light/01_main_window.png` and `dark/01_main_window.png`                             | Both show the app shell; the two differ visibly                |
| Acceptance criteria              | `QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_screenshot_harness.py -q` | 23 passed                                                      |
| The AC tests can actually fail   | Rename one `_CAPTURE_IDS` entry, re-run, revert                                           | Both AC-1 and AC-2 fail on the set comparison                  |
| No regression anywhere           | `uv run pytest tests/unit tests/integration tests/e2e src -q`                             | Green in ~2 minutes                                            |
| Traceability                     | `just trace && just trace-check`                                                          | Zero failures                                                  |

## Risks

- **A dialog factory returns `None`.** Three of the seven do so on insufficient gateway data. The builder raises with the offending capture id rather than silently writing 13 PNGs instead of 14. If Run Summary's preflight proves disproportionately expensive to satisfy, capture its blocked state and say so in the report.
- **Suite time.** Both acceptance tests run a full capture pass and now execute in the gate. If either exceeds the 30-second integration budget, split the dialog captures into a separate test rather than marking anything `slow`.
- **A blank capture.** A widget rendered before layout produces an empty image and the tests still pass — set equality only checks filenames. Step 3 of Task 2 and Step 4 of Task 5 are the human checks that catch this; do not skip them.
