# STORY-098 — Accessible names for New Benchmark / Resume / Progress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every interactive control in `ui/new_benchmark/`, `ui/resume_benchmark/`, and
`ui/progress/` a non-empty accessible name; pin the two §7.2 registry rows this story owns
(judge-model refresh button, rename-run pencil) to their exact `objectName`/accessible-name/
tooltip; and give the Resume run table's delegate-painted rename glyph an accessible name via a
new `Qt.ItemDataRole.AccessibleTextRole` mechanism on the table model, since a delegate-painted
glyph is not a `QWidget` and cannot carry `setAccessibleName` directly.

**Architecture:** No new modules, no new Gateway/Protocol surface. This is a widget-construction
sweep (add `setAccessibleName`/`setObjectName`/`setToolTip` calls) plus one small `data()`
extension on two table-model classes to answer a new Qt item-data role. Two new/extended test
files prove it: an integration walker test (mirrors STORY-097's shape) and colocated unit tests
for the `AccessibleTextRole` mechanism.

**Tech Stack:** PySide6 (`QWidget`, `QAbstractTableModel`, `QStyledItemDelegate`), `pytest-qt`.

## Global Constraints

- No `setStyleSheet()` outside `ui/theme/`; no colour literal in touched widget code.
- No `asyncio`/`anyio`/`qasync` anywhere in `src/`.
- Every `msgspec.Struct` this story touches (none new expected) stays
  `frozen=True, kw_only=True, gc=False`.
- `mypy --strict`, `ruff check`, `ruff format --check`, and `import-linter` must stay green for
  every file touched, including files this story only ripples into (test files whose expected
  `objectName`/tooltip strings change).
- `view.py` in every `ui/*` module stays passive: no Gateway/store/backend import added.
- Accessible name is independent of `objectName` — both are mandatory per control; a repeated
  control (the rename pencil) uses one shared `objectName` pattern across every screen.

______________________________________________________________________

## Context

STORY-097 (done) covered Main Window, common dialogs, and shared primitives and established the
pattern this story reuses: a widget-tree walker that asserts every "interactive" control
(`QAbstractButton`, `QComboBox`, `QLineEdit`, `QTextEdit`, `QAbstractSpinBox`,
`QAbstractItemView`) has a non-empty `accessibleName()`, plus parametrized tests for the handful
of icon-only/ambiguous controls whose `objectName`/accessible-name/tooltip triple is pinned
verbatim in `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7.2. STORY-098 is the second of
three per-workspace child stories under the STORY-089 sweep (STORY-099 does Result/Settings/Task
Editor next) and closes the gap on New Benchmark, Resume Benchmark, and Progress — currently
**zero** `setAccessibleName` calls exist in any of the three modules except the Progress stage
badge and the two shared dropdown widgets (`ui/shared/provider_dropdown`,
`ui/shared/model_dropdown`) that these modules already reuse.

This story is also the first in the sweep that has to handle a control that **isn't a
`QWidget`**: the Resume run table's rename-pencil (✎) and more-actions (⋯) glyphs are painted
directly onto the Tasks column by `RowActionsDelegate` (a `QStyledItemDelegate`), not
instantiated per row — deliberately, to keep the table virtualised for hundreds of rows. A
delegate has no `setAccessibleName` API, so its accessible name must instead come from the table
model answering `Qt.ItemDataRole.AccessibleTextRole` for that cell.

**Correction to the story's design-constraints text, resolved below (flagging per AGENTS.md
rather than resolving silently):** the story says to extend `adapters/qt_table_models/`'s shared
base model and "use it to give the Resume table's ... row actions an accessible name." Direct
investigation of `ui/resume_benchmark/_internal/run_table_model.py` shows this is **not
possible as literally written** — `RunTableModel` is a **bespoke** `QAbstractTableModel`, and its
own docstring says so explicitly: *"A bespoke `QAbstractTableModel` (not
`adapters.qt_table_models`'s `_FrozenRowTableModel` — that base carries no sort/filter state)."*
It does not inherit from `_FrozenRowTableModel` and cannot "use" a base-class extension it
doesn't derive from.

The `adapters/qt_table_models/` module reference in the story's front-matter is still correct,
though, because STORY-099's Providers table (`_ProvidersTableModel`) genuinely **is** built on
`_FrozenRowTableModel` and the story's own "Unblocks" section says STORY-099 "reuses the same
`AccessibleTextRole` mechanism this story adds to `adapters/qt_table_models/`." **Resolution used
below:** extend `_FrozenRowTableModel.data()` generically (for STORY-099 to reuse later) *and*,
separately, add the equivalent `AccessibleTextRole` branch directly to `RunTableModel.data()` —
two small, independent changes sharing one technique, not one inheritance chain. AC-3's proof
test for the real Resume table moves to `ui/resume_benchmark/tests/test_run_table_model.py`
(the only file that can actually exercise `RunTableModel`); the story's stated
`adapters/qt_table_models/tests/test_accessible_text_role.py` path is kept, but it proves the
generic base-class mechanism in isolation, not the Resume table itself.

A second concrete gap surfaced by investigation: STORY-097's walker helper
(`_INTERACTIVE_TYPES`/`_COMPOSITE_TYPES` in `tests/integration/test_a11y_names_shell.py`) has a
known, previously-noted limitation — `QAbstractSpinBox`'s Qt-internal child `QLineEdit` is not in
`_COMPOSITE_TYPES`, so the walker will flag that internal child as an unnamed, unfixable control.
STORY-097 never hit this because it had no spin boxes in scope; STORY-098 does (the Performance
Matrix repeats stepper, and ~10 spin/double-spin controls inside Advanced Options), so this story
must fix the walker.

______________________________________________________________________

## File structure

No new modules. Files touched:

**Production:**

- `src/ollama_llm_bench/ui/new_benchmark/_internal/judge_section.py` — pin the refresh button,
  name the analysis checkbox.
- `src/ollama_llm_bench/ui/new_benchmark/_internal/task_files.py` — name 4 buttons + the list.
- `src/ollama_llm_bench/ui/new_benchmark/_internal/test_models.py` — name 2 buttons, checkbox,
  the refresh button (distinct from judge's), 2 lists.
- `src/ollama_llm_bench/ui/new_benchmark/_internal/mode_selector.py` — name 3 radio buttons.
- `src/ollama_llm_bench/ui/new_benchmark/_internal/performance_matrix.py` — name 10 checkboxes +
  1 stepper.
- `src/ollama_llm_bench/ui/new_benchmark/_internal/advanced_options.py` — name ~28
  dynamically-built controls via their shared factory functions (single highest-leverage edit).
- `src/ollama_llm_bench/ui/new_benchmark/_internal/view.py` — name the Start button.
- `src/ollama_llm_bench/ui/resume_benchmark/_internal/view.py` — name search field, table,
  resume button.
- `src/ollama_llm_bench/ui/resume_benchmark/_internal/run_table_model.py` — add the
  `AccessibleTextRole` branch for `COL_TASKS` (AC-3).
- `src/ollama_llm_bench/ui/progress/_internal/header.py` — re-pin the rename pencil to the
  registry values; name pause/resume and stop buttons.
- `src/ollama_llm_bench/ui/progress/_internal/view.py` — name the log verbosity combo, log
  search field, log clear button, log body.
- `src/ollama_llm_bench/adapters/qt_table_models/_internal/base.py` — add the generic
  `AccessibleTextRole` branch to `_FrozenRowTableModel.data()` (for STORY-099 to reuse).

**Tests:**

- `tests/integration/test_a11y_names_benchmark_surfaces.py` — new, AC-1 walker + AC-2 pinned-row
  parametrized tests (mirrors `tests/integration/test_a11y_names_shell.py`'s shape).
- `tests/integration/test_a11y_names_shell.py` — extend `_COMPOSITE_TYPES` with
  `QAbstractSpinBox` (shared walker fix; see Task 1's DRY note on extracting this instead of
  duplicating it a second time).
- `src/ollama_llm_bench/adapters/qt_table_models/tests/test_accessible_text_role.py` — new,
  proves the generic base-class mechanism (AC-3, mechanism half).
- `src/ollama_llm_bench/ui/resume_benchmark/tests/test_run_table_model.py` — extended, proves
  `RunTableModel.data()` answers `AccessibleTextRole` for `COL_TASKS` with "Rename run" (AC-3,
  real-table half).
- `src/ollama_llm_bench/ui/resume_benchmark/tests/test_row_actions_delegate.py` — extended,
  `test_delegate_creates_no_per_row_widget` (AC-3, negative-space half — the delegate must still
  be the only thing that paints the glyphs).
- Ripple fixes: any existing test asserting the Progress header pencil's old `objectName`
  (`"progress.header.rename_pencil"`) or old tooltip (`"Rename this run"`) — grep
  `ui/progress/tests/` and `tests/integration/` before starting Task 6.

______________________________________________________________________

## Task 1: Fix the shared accessible-name walker for `QAbstractSpinBox`, then write it into a new file

**Files:**

- Modify: `tests/integration/test_a11y_names_shell.py` (the `_COMPOSITE_TYPES` tuple)
- Create: `tests/integration/test_a11y_names_benchmark_surfaces.py`

**Interfaces:**

- Consumes: nothing from later tasks.

- Produces: `_interactive_descendants(root: QWidget) -> list[QWidget]` (copied/adapted into the
  new file) — every later task's production-code change is proven against this walker. The new
  file's walker must accept the exact same set of Qt classes as `test_a11y_names_shell.py`'s,
  plus the `QAbstractSpinBox` fix.

- [ ] **Step 1: Read the existing walker verbatim**

Open `tests/integration/test_a11y_names_shell.py` and copy out `_INTERACTIVE_TYPES`,
`_COMPOSITE_TYPES`, `_has_composite_ancestor`, and `_interactive_descendants` exactly as they
exist today.

- [ ] **Step 2: Fix `_COMPOSITE_TYPES` in the existing file**

```python
from PySide6.QtWidgets import QAbstractItemView, QAbstractSpinBox, QComboBox

_COMPOSITE_TYPES = (QComboBox, QAbstractItemView, QAbstractSpinBox)
```

This excludes a `QAbstractSpinBox`'s Qt-internal `QLineEdit` child from the walker — only the
spin box itself is required to carry an accessible name, not the internal edit Qt composites
inside it.

- [ ] **Step 3: Run the shell suite to confirm the fix doesn't regress it**

Run: `uv run pytest tests/integration/test_a11y_names_shell.py -v`
Expected: PASS, same pass count as before (this file doesn't currently construct any
`QAbstractSpinBox`, so the fix is a no-op for it today, but it must stay green).

- [ ] **Step 4: Create the new test file, adapted for the three benchmark-workflow modules**

```python
"""Proves: STORY-098-AC-1, STORY-098-AC-2

Accessible-name floor for the New Benchmark, Resume, and Progress widgets
(12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md #7-accessible-names, #72).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QWidget,
)

from ollama_llm_bench.ui.new_benchmark import make_new_benchmark_widget
from ollama_llm_bench.ui.progress import make_progress_widget
from ollama_llm_bench.ui.resume_benchmark import make_resume_benchmark_widget

_INTERACTIVE_TYPES = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)
_COMPOSITE_TYPES = (QComboBox, QAbstractItemView, QAbstractSpinBox)


def _has_composite_ancestor(widget: QWidget) -> bool:
    parent = widget.parent()
    while parent is not None:
        if isinstance(parent, _COMPOSITE_TYPES):
            return True
        parent = parent.parent()
    return False


def _interactive_descendants(root: QWidget) -> list[QWidget]:
    found = [
        w
        for w in root.findChildren(QWidget)
        if isinstance(w, _INTERACTIVE_TYPES) and not _has_composite_ancestor(w)
    ]
    if isinstance(root, _INTERACTIVE_TYPES) and not _has_composite_ancestor(root):
        found.append(root)
    return found
```

Use the exact factory-function names and construction kwargs from each module's `api.py` —
confirm the real signatures of `make_new_benchmark_widget`, `make_progress_widget`, and
`make_resume_benchmark_widget` before writing the fixture (each takes its module's Gateway plus
`EventBus`/store collaborators as keyword args per `pyside6-spec-ui`'s factory pattern — mock
each with `mocker.Mock(spec=...)` per `testing.md`'s mocking discipline).

- [ ] **Step 5: Write the failing AC-1 test**

```python
def test_every_benchmark_surface_control_has_a_nonempty_accessible_name(
    qtbot, mocker
) -> None:
    widgets = [
        make_new_benchmark_widget(...),  # fill with mocked collaborators, see Step 4
        make_resume_benchmark_widget(...),
        make_progress_widget(...),
    ]
    for widget in widgets:
        qtbot.addWidget(widget)

    unnamed = [
        f"{type(w).__name__}#{w.objectName() or '<no objectName>'}"
        for root in widgets
        for w in _interactive_descendants(root)
        if not w.accessibleName()
    ]

    assert unnamed == []
```

This must use one `for` per widget list comprehension only (no `if`/`for` inside the test body
itself per `testing.md`'s no-`if`-no-`for`-in-test-body rule — the comprehensions above are
expression-level, not statements inside the test body, matching STORY-097's own precedent in
`test_a11y_names_shell.py`).

- [ ] **Step 6: Run it, confirm it fails listing every currently-unnamed control**

Run: `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py::test_every_benchmark_surface_control_has_a_nonempty_accessible_name -v`
Expected: FAIL, with `unnamed` printed showing every control from Tasks 2–8 below.

- [ ] **Step 7: Write the failing AC-2 parametrized test**

```python
_PINNED_ROWS = (
    pytest.param(
        "progress", "rename_run_button", "Rename run", "Rename run", id="progress-rename-pencil"
    ),
    pytest.param(
        "new_benchmark",
        "judge_model_refresh_button",
        "Refresh judge model list",
        "Refresh the judge provider's model list",
        id="new-benchmark-judge-refresh",
    ),
)


@pytest.mark.parametrize(("surface", "object_name", "accessible_name", "tooltip"), _PINNED_ROWS)
def test_benchmark_surface_registry_controls_use_pinned_values(
    qtbot, mocker, surface, object_name, accessible_name, tooltip
) -> None:
    widget = _SURFACE_FACTORIES[surface](...)
    qtbot.addWidget(widget)

    control = widget.findChild(QAbstractButton, object_name)

    assert control is not None
    assert control.accessibleName() == accessible_name
    assert control.toolTip() == tooltip
```

- [ ] **Step 8: Run it, confirm it fails (control not found or wrong name yet)**

Run: `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py -v`
Expected: 2 FAILED (both `_PINNED_ROWS` cases), plus the AC-1 test still failing from Step 6.

- [ ] **Step 9: Commit**

```bash
git add tests/integration/test_a11y_names_shell.py tests/integration/test_a11y_names_benchmark_surfaces.py
git commit -m "test(story-098): exclude spin-box internals from the walker, add failing accessible-name and pinned-value tests"
```

______________________________________________________________________

## Task 2: New Benchmark — Judge section (pinned refresh button + analysis checkbox)

**Files:**

- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/judge_section.py`

**Interfaces:**

- Consumes: none.

- Produces: `self._refresh_button.objectName() == "judge_model_refresh_button"`,
  `.accessibleName() == "Refresh judge model list"` — this is one of the two AC-2 rows Task 1's
  test asserts against.

- [ ] **Step 1: Pin the refresh button (§7.2 registry row)**

In `_build_ui`, immediately after the existing three lines that construct `self._refresh_button`:

```python
self._refresh_button = QPushButton("Refresh")
self._refresh_button.setObjectName("judge_model_refresh_button")
self._refresh_button.setProperty("role", "outlined-muted-button")
self._refresh_button.setAccessibleName("Refresh judge model list")
self._refresh_button.setToolTip("Refresh the judge provider's model list")  # already present, unchanged
self._refresh_button.clicked.connect(self._on_refresh_clicked)
```

- [ ] **Step 2: Name the analysis checkbox**

```python
self._analysis_checkbox = QCheckBox("Generate run analysis for this run")
self._analysis_checkbox.setObjectName("new_benchmark.judge.analysis_checkbox")
self._analysis_checkbox.setAccessibleName("Generate run analysis for this run")
```

- [ ] **Step 3: Run the AC-2 parametrized case for this row**

Run: `uv run pytest "tests/integration/test_a11y_names_benchmark_surfaces.py::test_benchmark_surface_registry_controls_use_pinned_values[new-benchmark-judge-refresh]" -v`
Expected: PASS.

- [ ] **Step 4: Run mypy/ruff on the touched file**

Run: `uv run mypy --strict src/ollama_llm_bench/ui/new_benchmark/_internal/judge_section.py && uv run ruff check src/ollama_llm_bench/ui/new_benchmark/_internal/judge_section.py`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/ollama_llm_bench/ui/new_benchmark/_internal/judge_section.py
git commit -m "feat(story-098): pin the judge-model refresh button and name the analysis checkbox"
```

______________________________________________________________________

## Task 3: New Benchmark — Task Files, Test Models, Mode Selector, Performance Matrix

**Files:**

- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/task_files.py`
- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/test_models.py`
- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/mode_selector.py`
- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/performance_matrix.py`

**Interfaces:**

- Consumes: none.
- Produces: every control listed below carries a non-empty `accessibleName()` — Task 1's AC-1
  walker test depends on all of these.

For every text-labelled button/checkbox in this task, the accessible name is **the control's own
visible text** (per `08_ACCESSIBILITY_FLOOR.md` §7's source table: "a button or menu item with a
text label → its visible text"). Where a control was also missing an `objectName`, add one
following the module's existing `"<module>.<section>.<control>"` dotted-path convention (already
used everywhere else in these two files) — §7.1 mandates a stable objectName on every
interactive control; this story is already touching these exact lines, so fixing the missing
half at the same time avoids a second remediation pass later.

- [ ] **Step 1: `task_files.py` — name 4 buttons + the list**

```python
self._add_file_button = QPushButton("Add File")
self._add_file_button.setObjectName("new_benchmark.task_files.add_file_button")
self._add_file_button.setAccessibleName("Add File")

self._add_folder_button = QPushButton("Add Folder")
self._add_folder_button.setObjectName("new_benchmark.task_files.add_folder_button")
self._add_folder_button.setAccessibleName("Add Folder")

self._remove_button = QPushButton("Remove")
self._remove_button.setObjectName("new_benchmark.task_files.remove_button")
self._remove_button.setAccessibleName("Remove")

self._open_in_editor_button = QPushButton("Open in Task Editor")
self._open_in_editor_button.setObjectName("new_benchmark.task_files.open_in_editor_button")
self._open_in_editor_button.setAccessibleName("Open in Task Editor")

self._list = QListWidget()
self._list.setObjectName("new_benchmark.task_files.list")  # already present
self._list.setAccessibleName("Selected task files")
```

- [ ] **Step 2: `test_models.py` — name checkbox, refresh button, 2 lists, 2 buttons**

The refresh button here is **not** the pinned §7.2 row — that is `judge_section.py`'s button.
This one refreshes the test-models list and needs its own, different accessible name so a
screen-reader user (and this story's own walker) can tell the two apart.

```python
self._hide_embedding_checkbox = QCheckBox("Hide embedding models")
self._hide_embedding_checkbox.setObjectName("new_benchmark.test_models.hide_embedding_checkbox")
self._hide_embedding_checkbox.setAccessibleName("Hide embedding models")

self._refresh_button = QPushButton("Refresh")
self._refresh_button.setObjectName("new_benchmark.test_models.refresh_button")
self._refresh_button.setAccessibleName("Refresh test models list")

self._available_list = QListWidget()
# objectName "new_benchmark.test_models.available_list" already present
self._available_list.setAccessibleName("Available test models")

self._select_all_button = QPushButton("Select All")
self._select_all_button.setObjectName("new_benchmark.test_models.select_all_button")
self._select_all_button.setAccessibleName("Select All")

self._clear_all_button = QPushButton("Clear All")
self._clear_all_button.setObjectName("new_benchmark.test_models.clear_all_button")
self._clear_all_button.setAccessibleName("Clear All")

self._summary_list = QListWidget()
# objectName "new_benchmark.test_models.summary_list" already present
self._summary_list.setAccessibleName("Selected test models")
```

- [ ] **Step 3: `mode_selector.py` — name the 3 `QRadioButton`s**

Each button's visible text is already `f"{title}\n{caption}"` (multi-line). Read the actual
`title`/`caption` values for each `RunMode` member at the point they're used to build
`button.setText(...)` — flatten them into a single-line accessible name rather than inventing new
wording:

```python
for mode, button in self._buttons.items():
    title, caption = ...  # the same two strings already used for button.setText(f"{title}\n{caption}")
    button.setObjectName(f"new_benchmark.mode_selector.{mode.value}")
    button.setAccessibleName(f"{title}: {caption}")
```

(Adapt to the loop/dict-comprehension shape the file already uses to build `self._buttons` — do
not introduce a new construction path.)

- [ ] **Step 4: `performance_matrix.py` — name the 10 checkboxes + the stepper**

The 10 checkboxes already have their objectName pattern (`new_benchmark.performance_matrix. {group}.{size_key}`); only the accessible name is missing, and it's the checkbox's own `caption`
text:

```python
box = QCheckBox(caption)
box.setObjectName(f"new_benchmark.performance_matrix.{group}.{size_key}")  # already present
box.setAccessibleName(caption)
```

The repeats stepper has no visible text of its own — an input field's accessible-name source is
its associated field label (§7's source table). Read the exact label string this stepper is
already presented with (its `QFormLayout`/row label, or an adjacent `QLabel`) and reuse it
verbatim:

```python
self._repeats_stepper = QSpinBox()
# objectName "new_benchmark.performance_matrix.repeats" already present
self._repeats_stepper.setAccessibleName(<the exact existing label text for this row>)
```

- [ ] **Step 5: Run the AC-1 walker, confirm the unnamed count drops**

Run: `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py::test_every_benchmark_surface_control_has_a_nonempty_accessible_name -v`
Expected: still FAIL (Advanced Options, Resume, Progress not done yet), but the printed `unnamed`
list must no longer include anything from `task_files.py`, `test_models.py`,
`mode_selector.py`, or `performance_matrix.py`.

- [ ] **Step 6: mypy/ruff on all four touched files**

Run: `uv run mypy --strict src/ollama_llm_bench/ui/new_benchmark/_internal/{task_files,test_models,mode_selector,performance_matrix}.py && uv run ruff check src/ollama_llm_bench/ui/new_benchmark/_internal/{task_files,test_models,mode_selector,performance_matrix}.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/ui/new_benchmark/_internal/task_files.py \
        src/ollama_llm_bench/ui/new_benchmark/_internal/test_models.py \
        src/ollama_llm_bench/ui/new_benchmark/_internal/mode_selector.py \
        src/ollama_llm_bench/ui/new_benchmark/_internal/performance_matrix.py
git commit -m "feat(story-098): name Task Files, Test Models, Mode Selector, and Performance Matrix controls"
```

______________________________________________________________________

## Task 4: New Benchmark — Advanced Options (28 controls via the shared factory) + Start button

**Files:**

- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/advanced_options.py`
- Modify: `src/ollama_llm_bench/ui/new_benchmark/_internal/view.py`

**Interfaces:**

- Consumes: none.
- Produces: every one of the ~28 controls `AdvancedOptionsSectionWidget` builds carries a
  non-empty accessible name equal to its existing `_LABELS` entry.

This is the single largest remediation surface in the module, but it collapses to **one factory
edit per row-builder function** because all 28 controls already flow through
`_make_checkbox_row`, `_make_reasoning_effort_row`, `_make_float_row`, `_make_int_row`, and
`_make_text_row`, each called once per `SettingKey` and each already receiving the resolved
label text at the `form.addRow(_LABELS.get(key, key), row.widget)` call site.

- [ ] **Step 1: Thread the label through each factory and set it as the accessible name**

Each `_make_*_row` function currently returns a small row object holding `.widget`. Change each
to also receive the resolved label (or look it up from `_LABELS.get(key, key)` itself, matching
whatever the function already receives) and call:

```python
def _make_checkbox_row(key: SettingKey, ...) -> _Row:
    box = QCheckBox()
    box.setObjectName(f"new_benchmark.advanced_options.{key.value}")
    box.setAccessibleName(_LABELS.get(key, key))
    ...
    return _Row(widget=box, ...)
```

Apply the identical two-line addition (`setObjectName` + `setAccessibleName`) inside
`_make_reasoning_effort_row` (on its `combo`), `_make_float_row` (on its `spin`),
`_make_int_row` (on its `spin`), and `_make_text_row` (on its `line_edit`) — same pattern, same
label source, one control constructed per call.

- [ ] **Step 2: Name the activation and evaluation group boxes**

```python
self._activation_box = QGroupBox("Override advanced options for this run")
self._activation_box.setObjectName("new_benchmark.advanced_options.activation_box")
self._activation_box.setAccessibleName("Override advanced options for this run")
```

`QGroupBox` is not in `_INTERACTIVE_TYPES` (it's not a control the walker requires), so this step
is optional polish, not required for AC-1 — include it only if trivial to do alongside Step 1;
otherwise skip.

- [ ] **Step 3: Name the Start Benchmark button in `view.py`**

```python
self.start_button = QPushButton("Start Benchmark")
# objectName "new_benchmark.start_button" already present
self.start_button.setAccessibleName("Start Benchmark")
```

- [ ] **Step 4: Run the AC-1 walker, confirm `new_benchmark` contributes zero unnamed controls**

Run: `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py::test_every_benchmark_surface_control_has_a_nonempty_accessible_name -v`
Expected: still FAIL overall (Resume, Progress remain), but the printed `unnamed` list must
contain no `new_benchmark`-sourced entries at all.

- [ ] **Step 5: mypy/ruff**

Run: `uv run mypy --strict src/ollama_llm_bench/ui/new_benchmark/_internal/advanced_options.py src/ollama_llm_bench/ui/new_benchmark/_internal/view.py && uv run ruff check src/ollama_llm_bench/ui/new_benchmark/_internal/advanced_options.py src/ollama_llm_bench/ui/new_benchmark/_internal/view.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/ui/new_benchmark/_internal/advanced_options.py \
        src/ollama_llm_bench/ui/new_benchmark/_internal/view.py
git commit -m "feat(story-098): name all Advanced Options controls and the Start button"
```

______________________________________________________________________

## Task 5: Resume Benchmark — search field, table, resume button (widget-level AC-1 only)

**Files:**

- Modify: `src/ollama_llm_bench/ui/resume_benchmark/_internal/view.py`

**Interfaces:**

- Consumes: none.
- Produces: `self._search_edit`, `self._table_view`, `self._resume_button` each carry a
  non-empty `accessibleName()`.

This task does **not** touch the delegate-painted rename/overflow glyphs — those are AC-3, Task
7 below.

- [ ] **Step 1: Name the search field**

```python
self._search_edit = QLineEdit()
# objectName "resume_benchmark.search" already present
self._search_edit.setPlaceholderText("Search by name or mode…")  # already present
self._search_edit.setAccessibleName("Search runs by name or mode")
```

- [ ] **Step 2: Name the table (§7's table rule: an accessible name describing content)**

```python
self._table_view = QTableView()
# objectName "resume_benchmark.table" already present
self._table_view.setAccessibleName("Past benchmark runs")
```

- [ ] **Step 3: Name the Resume Run button**

```python
self._resume_button = QPushButton("Resume Run")
# objectName "resume_benchmark.resume_button" already present
self._resume_button.setAccessibleName("Resume Run")
```

- [ ] **Step 4: Run the AC-1 walker, confirm `resume_benchmark`'s widget-level controls are covered**

Run: `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py::test_every_benchmark_surface_control_has_a_nonempty_accessible_name -v`
Expected: still FAIL (Progress remains), and `unnamed` must contain no
`resume_benchmark`-sourced entries.

- [ ] **Step 5: mypy/ruff**

Run: `uv run mypy --strict src/ollama_llm_bench/ui/resume_benchmark/_internal/view.py && uv run ruff check src/ollama_llm_bench/ui/resume_benchmark/_internal/view.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/ui/resume_benchmark/_internal/view.py
git commit -m "feat(story-098): name the Resume search field, run table, and Resume Run button"
```

______________________________________________________________________

## Task 6: Progress — re-pin the rename pencil, name pause/resume, stop, and the log panel

**Files:**

- Modify: `src/ollama_llm_bench/ui/progress/_internal/header.py`
- Modify: `src/ollama_llm_bench/ui/progress/_internal/view.py`
- Modify: any test asserting the pencil's old `objectName`/tooltip (grep first, see Step 0)

**Interfaces:**

- Consumes: none.

- Produces: `self._pencil_button.objectName() == "rename_run_button"`,
  `.accessibleName() == "Rename run"`, `.toolTip() == "Rename run"` — the second of the two AC-2
  rows Task 1's test asserts against.

- [ ] **Step 0: Find every existing reference to the pencil's current identity before renaming it**

Run: `rg -n '"progress.header.rename_pencil"|"Rename this run"' src/ollama_llm_bench tests`

Update every match found (production code and test assertions) in the same commit as Step 1
below — a rename that doesn't update its own tests leaves the suite red for a reason unrelated
to this story's actual work.

- [ ] **Step 1: Re-pin the rename pencil to the exact §7.2 registry values**

```python
self._pencil_button = QToolButton()
self._pencil_button.setObjectName("rename_run_button")
self._pencil_button.setText("✎")
self._pencil_button.setAccessibleName("Rename run")
self._pencil_button.setToolTip("Rename run")
self._pencil_button.setFixedSize(28, 28)
self._pencil_button.clicked.connect(self.rename_clicked)
```

- [ ] **Step 2: Name the pause/resume button, tracking its dynamic text**

This button's visible text toggles between "Pause" and "Resume". Find every call site that sets
`self._pause_resume_button.setText(...)` (construction plus wherever the toggle happens) and add
a matching `setAccessibleName` call using the same string, mirroring the stage badge's existing
`f"{stage.value} stage badge"` dynamic-accessible-name pattern in `stage_badge.py`:

```python
self._pause_resume_button.setText(next_label)
self._pause_resume_button.setAccessibleName(next_label)
```

- [ ] **Step 3: Name the stop button (static text, no toggling)**

```python
self._stop_button = QPushButton("Stop")
# objectName "progress.header.stop" already present
self._stop_button.setAccessibleName("Stop")
```

- [ ] **Step 4: Name the log panel controls in `view.py`**

```python
self._log_verbosity_combo = QComboBox()
# objectName "progress.log.verbosity" already present
self._log_verbosity_combo.setAccessibleName("Log verbosity")

self._log_search_edit = QLineEdit()
# objectName "progress.log.search" already present
self._log_search_edit.setPlaceholderText("Search the run log…")  # already present
self._log_search_edit.setAccessibleName("Search the run log")

self._log_clear_button = QPushButton(...)  # confirm existing visible text before choosing wording
# objectName "progress.log.clear" already present
self._log_clear_button.setAccessibleName("Clear log")  # or the button's own visible text if it has one

self._log_body = QTextEdit()
self._log_body.setReadOnly(True)  # already present
# objectName "progress.log.body" already present
self._log_body.setAccessibleName("Run log")
```

- [ ] **Step 5: Run the full AC-1 walker and both AC-2 parametrized cases**

Run: `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py -v`
Expected: **all PASS** — this is the first point where the full new test file goes green.

- [ ] **Step 6: Run the shell suite too (it now shares the `QAbstractSpinBox` fix from Task 1)**

Run: `uv run pytest tests/integration/test_a11y_names_shell.py -v`
Expected: PASS, unchanged pass count.

- [ ] **Step 7: mypy/ruff on every file touched this task, plus any rippled test file from Step 0**

Run: `uv run mypy --strict src/ollama_llm_bench/ui/progress/_internal/header.py src/ollama_llm_bench/ui/progress/_internal/view.py && uv run ruff check src/ollama_llm_bench/ui/progress/_internal/header.py src/ollama_llm_bench/ui/progress/_internal/view.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add src/ollama_llm_bench/ui/progress/_internal/header.py \
        src/ollama_llm_bench/ui/progress/_internal/view.py \
        <any rippled test files from Step 0>
git commit -m "feat(story-098): re-pin the Progress rename pencil and name pause/resume, stop, and the log panel"
```

______________________________________________________________________

## Task 7: AC-3 — `AccessibleTextRole` for the Resume table's delegate-painted rename glyph

**Files:**

- Modify: `src/ollama_llm_bench/adapters/qt_table_models/_internal/base.py`
- Create: `src/ollama_llm_bench/adapters/qt_table_models/tests/test_accessible_text_role.py`
- Modify: `src/ollama_llm_bench/ui/resume_benchmark/_internal/run_table_model.py`
- Modify/Create: `src/ollama_llm_bench/ui/resume_benchmark/tests/test_run_table_model.py`
- Modify/Create: `src/ollama_llm_bench/ui/resume_benchmark/tests/test_row_actions_delegate.py`

**Interfaces:**

- Consumes: `RunTableModel`'s existing `COL_TASKS = 4` constant
  (`ui/resume_benchmark/_internal/run_table_model.py`) and `RowActionsDelegate`'s existing
  `pencil_clicked`/`more_clicked` signals (`ui/resume_benchmark/_internal/row_actions_delegate.py`)
  — neither changes shape in this task.
- Produces: `RunTableModel.data(index_at_col_tasks, Qt.ItemDataRole.AccessibleTextRole) == "Rename run"`; `_FrozenRowTableModel.data(..., AccessibleTextRole)` answers via an optional
  constructor-supplied callback, `None` when none is supplied (backward compatible with the
  three existing concrete subclasses, which pass nothing and keep today's behaviour).

**Two independent, same-technique changes — not one inheritance chain.** See the Context section
above for why: `RunTableModel` does not inherit `_FrozenRowTableModel`, so extending the base
class alone would not touch the Resume table at all.

- [ ] **Step 1: Write the failing generic-mechanism test (base-class half)**

```python
"""Proves: STORY-098-AC-3

The shared table-model base can answer Qt.ItemDataRole.AccessibleTextRole
when constructed with an accessible-text callback
(08_ACCESSIBILITY_FLOOR.md #7-accessible-names).
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt

from ollama_llm_bench.adapters.qt_table_models._internal.base import _FrozenRowTableModel


def test_frozen_row_table_model_answers_accessible_text_role_when_configured() -> None:
    model: _FrozenRowTableModel[str] = _FrozenRowTableModel(
        headers=("Col",),
        cell_value=lambda row, _col: row,
        rows=("row-0",),
        accessible_text=lambda row, _col: f"accessible: {row}",
    )
    index = model.index(0, 0)

    result = model.data(index, Qt.ItemDataRole.AccessibleTextRole)

    assert result == "accessible: row-0"


def test_frozen_row_table_model_returns_none_for_accessible_text_role_when_unconfigured() -> None:
    model: _FrozenRowTableModel[str] = _FrozenRowTableModel(
        headers=("Col",), cell_value=lambda row, _col: row, rows=("row-0",)
    )
    index = model.index(0, 0)

    result = model.data(index, Qt.ItemDataRole.AccessibleTextRole)

    assert result is None
```

(Confirm `_FrozenRowTableModel`'s real `__init__` parameter order/names from `base.py` before
finalizing this call — the shape above follows the existing `headers`/`cell_value`/`rows`
keyword-only pattern already in the file.)

- [ ] **Step 2: Run it, confirm it fails**

Run: `uv run pytest src/ollama_llm_bench/adapters/qt_table_models/tests/test_accessible_text_role.py -v`
Expected: FAIL — `accessible_text` is not a recognized constructor argument yet.

- [ ] **Step 3: Extend `_FrozenRowTableModel`**

```python
class _FrozenRowTableModel[RowT](QAbstractTableModel):
    def __init__(
        self,
        *,
        headers: tuple[str, ...],
        cell_value: Callable[[RowT, int], object],
        rows: tuple[RowT, ...],
        accessible_text: Callable[[RowT, int], str] | None = None,
    ) -> None:
        super().__init__()
        self._headers = headers
        self._cell_value = cell_value
        self._accessible_text = accessible_text
        self._rows = rows

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._cell_value(self._rows[index.row()], index.column())
        if role == Qt.ItemDataRole.AccessibleTextRole and self._accessible_text is not None:
            return self._accessible_text(self._rows[index.row()], index.column())
        return None
```

- [ ] **Step 4: Run the new test, confirm it passes; run the existing `qt_table_models` suite to confirm no regression**

Run: `uv run pytest src/ollama_llm_bench/adapters/qt_table_models/tests/ -v`
Expected: all PASS — including the three existing concrete-subclass tests
(`_SummaryTableModel`, `_DetailsTableModel`, `_ProvidersTableModel`), none of which pass
`accessible_text` and must keep returning `None` for that role exactly as before.

- [ ] **Step 5: Write the failing real-table test (`RunTableModel` half)**

```python
"""Proves: STORY-098-AC-3

RunTableModel answers Qt.ItemDataRole.AccessibleTextRole for the actions
cell (COL_TASKS) with the registry's canonical "Rename run" wording
(08_ACCESSIBILITY_FLOOR.md #72).
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import COL_TASKS, RunTableModel


def test_actions_cell_exposes_rename_run_as_accessible_text(make_run_row) -> None:
    model = RunTableModel(rows=(make_run_row(),), theme_manager=..., platform_kind=...)
    index = model.index(0, COL_TASKS)

    result = model.data(index, Qt.ItemDataRole.AccessibleTextRole)

    assert result == "Rename run"
```

(Reuse whatever row-building fixture/helper `test_run_table_model.py` already has for
`theme_manager`/`platform_kind`/row construction — do not invent a new one; check the file's
existing fixtures first.)

- [ ] **Step 6: Run it, confirm it fails**

Run: `uv run pytest src/ollama_llm_bench/ui/resume_benchmark/tests/test_run_table_model.py::test_actions_cell_exposes_rename_run_as_accessible_text -v`
Expected: FAIL — `RunTableModel.data()` returns `None` for this role today.

- [ ] **Step 7: Add the branch to `RunTableModel.data()`**

```python
def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
    if not index.isValid():
        return None
    row = self._visible_rows[index.row()]
    if role == Qt.ItemDataRole.UserRole and index.column() == COL_STATUS:
        return row.status_badge_status
    if role == Qt.ItemDataRole.AccessibleTextRole and index.column() == COL_TASKS:
        return "Rename run"
    if role != Qt.ItemDataRole.DisplayRole:
        return None
    ...  # existing DisplayRole branch, unchanged
```

- [ ] **Step 8: Run it, confirm it passes**

Run: `uv run pytest src/ollama_llm_bench/ui/resume_benchmark/tests/test_run_table_model.py -v`
Expected: all PASS.

- [ ] **Step 9: Confirm (or write) the delegate's negative-space test**

Check whether `test_delegate_creates_no_per_row_widget` already exists in
`src/ollama_llm_bench/ui/resume_benchmark/tests/test_row_actions_delegate.py`. If it does,
re-run it now to confirm it still passes (this task changes no delegate code, so it should be
unaffected). If it doesn't exist yet, add it:

```python
def test_delegate_creates_no_per_row_widget(qtbot, make_run_row) -> None:
    """Proves: STORY-098-AC-3

    The delegate paints the rename/more-actions glyphs directly; it never
    instantiates a per-row QWidget, keeping the table virtualised (EC-RB-12).
    """
    table = QTableView()
    model = RunTableModel(rows=(make_run_row(), make_run_row()), theme_manager=..., platform_kind=...)
    table.setModel(model)
    delegate = RowActionsDelegate(theme_manager=..., platform_kind=...)
    table.setItemDelegateForColumn(COL_TASKS, delegate)
    qtbot.addWidget(table)

    children_before = len(table.viewport().findChildren(QWidget))
    table.viewport().update()
    qtbot.wait(50)
    children_after = len(table.viewport().findChildren(QWidget))

    assert children_after == children_before
```

- [ ] **Step 10: Run the full Resume Benchmark colocated suite**

Run: `uv run pytest src/ollama_llm_bench/ui/resume_benchmark/tests/ -v`
Expected: all PASS.

- [ ] **Step 11: mypy/ruff on every file touched this task**

Run: `uv run mypy --strict src/ollama_llm_bench/adapters/qt_table_models/_internal/base.py src/ollama_llm_bench/ui/resume_benchmark/_internal/run_table_model.py && uv run ruff check src/ollama_llm_bench/adapters/qt_table_models/_internal/base.py src/ollama_llm_bench/ui/resume_benchmark/_internal/run_table_model.py`
Expected: no errors.

- [ ] **Step 12: Commit**

```bash
git add src/ollama_llm_bench/adapters/qt_table_models/_internal/base.py \
        src/ollama_llm_bench/adapters/qt_table_models/tests/test_accessible_text_role.py \
        src/ollama_llm_bench/ui/resume_benchmark/_internal/run_table_model.py \
        src/ollama_llm_bench/ui/resume_benchmark/tests/test_run_table_model.py \
        src/ollama_llm_bench/ui/resume_benchmark/tests/test_row_actions_delegate.py
git commit -m "feat(story-098): answer AccessibleTextRole for the Resume table's rename action"
```

______________________________________________________________________

## Task 8: Full-suite verification and traceability close-out

**Files:** none (verification only).

- [ ] **Step 1: Run the full gate**

Run: `just check`
Expected: lint, format-check, typecheck, import-check, arch-test, then the full pytest run
(`tests/unit tests/integration tests/e2e src`) all green, no new findings versus the baseline on
`master`/pre-story `HEAD` (per AGENTS.md's exclusion-test rule if anything looks pre-existing —
re-run with only the suspect file ignored and compare).

- [ ] **Step 2: Regenerate and validate traceability**

Run: `just trace && just trace-check`
Expected: `traceability.yaml` regenerates with STORY-098's three acceptance criteria each mapped
to their proving tests, zero orphan clauses, zero orphan tests, zero gaps.

- [ ] **Step 3: Flip `status: ready` for any story whose remaining `depends_on` are now `done`**

Per the story's own closing checklist: check STORY-089's `depends_on` — it should **not** be
flipped yet unless STORY-097 (done) and STORY-099 (not yet started) are both `done`. Confirm
STORY-099's status and leave STORY-089 `draft`, naming STORY-099 as the outstanding dependency in
the closing report.

- [ ] **Step 4: Mark STORY-098 `status: done` in its front-matter**

Edit `docs/stories/story-098-accessible-names-benchmark-surfaces.md`'s front-matter
`status: ready` → `status: done`, then re-run `just trace` once more (Step 2's output embeds
each story's status, so it goes stale the moment this changes).

- [ ] **Step 5: Commit**

```bash
git add docs/stories/story-098-accessible-names-benchmark-surfaces.md traceability.yaml
git commit -m "docs(story-098): mark accessible-names benchmark-surfaces story done, refresh traceability"
```

______________________________________________________________________

## Self-review

**Spec coverage:**

- AC-1 (every interactive control named) — Tasks 2–6, proven by Task 1's walker test, run
  incrementally in each task and asserted fully green in Task 6 Step 5.
- AC-2 (2 pinned registry rows) — Task 2 (judge refresh) and Task 6 (rename pencil), proven by
  Task 1's parametrized test.
- AC-3 (delegate accessible text, no per-row widget) — Task 7, both halves.
- Design constraint "virtualisation is load-bearing, don't replace the delegate with per-row
  widgets" — honored: Task 7 adds a `data()` branch only, the delegate itself is untouched except
  for its own negative-space test.
- Design constraint "no `setStyleSheet`, no colour literal, no `asyncio`" — no task introduces
  any of these; all touched files are `_internal/` widget-construction and a model's `data()`
  method.
- STORY-097's known walker gap (`QAbstractSpinBox` internals) — fixed in Task 1 before it can
  produce a false failure in Task 3/4's spin-box work.

**Placeholder scan:** no task contains "TBD"/"handle appropriately"/"similar to Task N" — every
step names its exact file, exact string, or exact existing-value lookup instruction where a
literal wasn't independently verified during planning (mode-selector title/caption, the repeats
stepper's label, the log clear button's visible text, the log verbosity combo's label) — each of
those is an explicit "read the existing value, don't invent one" instruction, not a placeholder.

**Type consistency:** `_FrozenRowTableModel`'s new `accessible_text` parameter, `RunTableModel`'s
`COL_TASKS` branch, and both new/extended test files all reference the same role
(`Qt.ItemDataRole.AccessibleTextRole`) and the same canonical string (`"Rename run"`) throughout.

______________________________________________________________________

## Verification (end-to-end)

1. `uv run pytest tests/integration/test_a11y_names_benchmark_surfaces.py tests/integration/test_a11y_names_shell.py -v` — both files fully green.
1. `uv run pytest src/ollama_llm_bench/adapters/qt_table_models/tests/ src/ollama_llm_bench/ui/resume_benchmark/tests/ src/ollama_llm_bench/ui/new_benchmark/tests/ src/ollama_llm_bench/ui/progress/tests/ -v` — every colocated suite green, no regression in existing controller/view tests that reference an objectName or tooltip this story changed (the Task 6 Step 0 grep).
1. `just check` — full gate green (see Task 8).
1. `just trace-check` — zero gaps (see Task 8).
1. Manual: launch the app (`just run` or the project's documented dev entry point), open New
   Benchmark, Resume, and an active Progress view, and spot-check with a Qt accessibility
   inspector (or `widget.accessibleName()` in a debugger) that the rename pencil on both Progress
   and the Resume table row hover reports "Rename run", and that the judge refresh button reports
   "Refresh judge model list" — this is the one check the automated suite can't fully stand in
   for, since it's confirming the *visual* hover/glyph position matches the *logical* accessible
   name a screen reader would announce.
