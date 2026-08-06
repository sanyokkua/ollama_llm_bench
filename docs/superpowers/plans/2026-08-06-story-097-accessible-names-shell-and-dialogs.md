# STORY-097 — Accessible names for the shell, shared dialogs, and shared primitives

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every clickable control in the application shell, the seven shared modal dialogs, and the shared visual primitives a name that assistive technology and UI tests can read, and make ten specific controls use the exact name, test handle, and hover tooltip the specification pins for them.

**Architecture:** This is a naming pass, not a redesign — no layout, no styling, no behaviour changes except two tooltips that gain text. Two new shared primitives are added to `ui/shared/` (a dialog Close button and a gate-busy message strip) so the pinned strings for those repeated controls are written down once and mounted, rather than retyped per dialog. Eight existing test handles are renamed to the pinned values, which touches roughly twenty `findChild(...)` call sites across eight test files.

**Tech Stack:** Python 3.13, PySide6 6.8 Qt Widgets, pytest + pytest-qt, msgspec, icontract, ruff, mypy --strict, import-linter.

## Context

Today the entire application calls `setAccessibleName` four times and `setAccessibleDescription` never. Every other control — every button, dropdown, text field, and table in these five areas — is anonymous: a screen reader announces nothing useful, and a test cannot address it by name. The specification treats this as release-blocking, and pins exact values for a registry of controls whose purpose is not obvious from what is on screen (an icon with no label, a coloured dot, a status pill).

This story covers the first third of that registry — the ten rows that live in the application shell, the shared dialogs, and the shared primitives. Two sibling stories cover the rest, and a fourth adds the single app-wide test that catches a control silently moving between screens.

Three things are worth knowing before starting:

- **`widget.accessibleName()` returns an empty string unless it is set explicitly.** Qt does *not* fall back to the button's visible text at this level. So even a button reading "Cancel" needs `setAccessibleName("Cancel")`.
- **The test handle (`objectName`) and the announced name (`accessibleName`) are independent and both mandatory.** Renaming a visible label must never change a test handle, and vice versa.
- **The current test handles do not match the pinned ones.** The shell uses `settings_action`, `about_action`, `workspace_switcher_benchmark`; the specification pins `settings_menu_button`, `about_menu_button`, `workspace_benchmark_button`. Renaming is required, not optional, and is the single largest source of churn in this story.

## Global Constraints

Every task inherits these. They are enforced by the pull-request gate, not by review alone.

- **No `setStyleSheet` outside `src/ollama_llm_bench/ui/theme/`.** Enforced by `tests/architecture/test_ui_shared_style_authority.py`.
- **No colour hex literal in any widget file.** Same architecture test. Colour comes from theme role names via `setProperty("role", ...)`.
- **No `asyncio` / `anyio` / `qasync` anywhere.** Same architecture test.
- **No new pixel literal in layout code** — spacing comes from theme tokens. (The existing `setFixedSize(28, 28)` on the About icon buttons stays as-is; do not add more.)
- **Every public function in an `api.py` carries at least one `@icontract.require` or `@icontract.ensure`**, guarding programmer invariants only — never user input.
- **`__all__` in every `__init__.py` is a literal `list[str]`**, never computed.
- **Every test is fully annotated, returns `-> None`, and contains no `if` and no `for` in its body.** A table of cases is `@pytest.mark.parametrize`.
- **A test proving an acceptance criterion declares it on the first line of its docstring** in the exact form `"""Proves: STORY-097-AC-1` — the traceability generator parses this.
- **`uv run` prefixes every Python command.** Never `pip install`.
- **Never `git commit --no-verify`.** Never delete a failing test to make a suite pass.

### Pinned values — copy these exactly

These ten rows come from `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7.2. Note the em-dashes (`—`, U+2014) — they are not hyphens.

| Control                       | objectName                     | Accessible name                                       | Tooltip                                                                                          |
| ----------------------------- | ------------------------------ | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Shell · Settings button       | `settings_menu_button`         | `Settings`                                            | `Open the Settings dialog`                                                                       |
| Shell · About button          | `about_menu_button`            | `About`                                               | `Application information: version, links, data folders`                                          |
| Shell · Benchmark workspace   | `workspace_benchmark_button`   | `Benchmark workspace`                                 | `Benchmark workspace`                                                                            |
| Shell · Task Editor workspace | `workspace_task_editor_button` | `Task Editor workspace`                               | `Task Editor workspace`                                                                          |
| Shell · Running pill          | `running_pill_button`          | `Run in progress — open Progress`                     | `Switch to the Benchmark workspace and focus the Progress widget`                                |
| Shell · Readiness dot         | `provider_readiness_indicator` | `Provider readiness status`                           | `Provider readiness — click to open Settings / Providers` **(first line only — see Decision 4)** |
| All dialogs · Close           | `dialog_close_button`          | `Close dialog`                                        | `Close`                                                                                          |
| About · Open data folder      | `open_data_folder_button`      | `Open application data folder`                        | `Open the application data folder`                                                               |
| About · Copy path             | `copy_data_folder_path_button` | `Copy application data folder path`                   | `Copy the application data folder path`                                                          |
| Dialogs · Gate-busy strip     | `gate_busy_indicator`          | `Inference in flight — controls temporarily disabled` | `An inference is in flight; please wait.`                                                        |

## Decisions already made — do not re-litigate

1. **The pinned "Dialog close (✕)" row maps onto the existing footer `Close` button**, not onto a new title strip. The mockups draw a ✕ in a coloured dialog header; the real app uses ordinary windows, so that ✕ is drawn by the operating system and no Qt object exists to name. The About and Error dialogs both already have a footer `Close` button that does exactly what the row describes. A shared factory in `ui/shared/` defines it once; STORY-099 points the Settings dialog at the same factory. **`Cancel` and `Back` buttons that sit beside a distinct confirm button are NOT dialog-close buttons** and are not touched by this row.
1. **The gate-busy indicator is a static text strip, not an animated spinner.** The registry table says "spinner", but every mockup draws a static strip, and ADR-0018 retired support for the operating system's reduce-motion preference — a looping animation would have no way to be switched off. The strip takes its sentence from the caller; only the test handle, announced name, and tooltip are pinned.
1. **The Generate Analysis dialog adopts the shared strip**, replacing its hand-rolled `_busy_label`. Its visible sentence stays exactly `An inference is currently in flight — please wait.` (pinned verbatim by that dialog's own spec, EC-GA-3). Only the surrounding identity attributes change.
1. **The readiness dot's tooltip carries both.** The Main Window spec says the tooltip lists per-provider reachability; the accessibility registry and the Main Window mockup pin the fixed sentence `Provider readiness — click to open Settings / Providers`. Resolution: the pinned sentence is the **first line**, then a blank line, then the existing per-provider list. Nothing visible today is lost. **This one row's test asserts `toolTip().splitlines()[0] == pinned`; the other nine assert full equality.**
1. **The Settings button's tooltip is state-dependent.** When enabled it is the pinned `Open the Settings dialog`. When disabled it stays `Disabled - a benchmark is in progress.` (pinned verbatim by the Main Window spec §3.1, and required by the rule that a temporarily disabled control must explain itself). The pinned-value test asserts the idle/enabled state.
1. **About's two icon buttons keep their existing tooltips** — they already match the pinned values character for character. Only their test handles and announced names change.
1. **The ~10 buttons with no test handle at all get one**, using the existing `common_dialogs.<dialog>.<name>` convention. This is slightly wider than the two acceptance criteria and must be recorded in the story's notes.

______________________________________________________________________

## File Structure

**Create**

| File                                                              | Responsibility                                                              |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `src/ollama_llm_bench/ui/shared/_internal/dialog_close_button.py` | The one definition of a dialog Close button carrying the pinned trio.       |
| `src/ollama_llm_bench/ui/shared/_internal/gate_busy_indicator.py` | The one definition of the gate-busy message strip carrying the pinned trio. |
| `tests/integration/test_a11y_names_shell.py`                      | Both acceptance-criteria tests.                                             |

**Modify**

| File                                                                                                                  | Change                                                                    |
| --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `src/ollama_llm_bench/ui/shared/api.py`                                                                               | Add `make_dialog_close_button`, `make_gate_busy_indicator`.               |
| `src/ollama_llm_bench/ui/shared/__init__.py`                                                                          | Re-export the two new factories.                                          |
| `src/ollama_llm_bench/ui/shared/_internal/multi_check_filter_button.py`                                               | Announced name from its label.                                            |
| `src/ollama_llm_bench/ui/shared/provider_dropdown/_internal/view.py`                                                  | Announced name `Provider`.                                                |
| `src/ollama_llm_bench/ui/shared/model_dropdown/_internal/view.py`                                                     | Announced name `Model`.                                                   |
| `src/ollama_llm_bench/ui/main_window/_internal/menu_bar.py`                                                           | Five pinned controls: rename handles, add names and tooltips.             |
| `src/ollama_llm_bench/ui/main_window/_internal/status_bar.py`                                                         | Readiness dot: handle, name, two-part tooltip.                            |
| `src/ollama_llm_bench/ui/main_window/_internal/close_handler.py`                                                      | Names and handles on the four quit-confirmation buttons.                  |
| `src/ollama_llm_bench/ui/common_dialogs/_internal/about_view.py`                                                      | Adopt the shared Close button; pin the two icon buttons; name the rest.   |
| `src/ollama_llm_bench/ui/common_dialogs/_internal/error_view.py`                                                      | Adopt the shared Close button; name the rest.                             |
| `src/ollama_llm_bench/ui/common_dialogs/_internal/generate_analysis_view.py`                                          | Adopt the shared gate-busy strip; name the rest.                          |
| `src/ollama_llm_bench/ui/common_dialogs/_internal/{view,rename_run_view,resume_summary_view,retry_selection_view}.py` | Names on every control; handles on the unnamed buttons.                   |
| `tests/integration/conftest.py`                                                                                       | Receives the moved dialog builders; exposes the `common_dialogs` fixture. |
| `tests/integration/test_screenshot_harness.py`                                                                        | Request the `common_dialogs` fixture instead of defining the builders.    |
| 8 test files (see Task 3/4)                                                                                           | Follow the renamed test handles.                                          |
| `docs/stories/story-097-*.md`                                                                                         | Status `done`, notes recording Decisions 1–7.                             |

______________________________________________________________________

## Task 1: Extract the shared dialog builders so two test files can mount all seven dialogs

`tests/integration/test_screenshot_harness.py` already constructs all seven modal dialogs with canned data and stub gateways, in a private helper `_build_common_dialogs` (line ~488) plus its supporting `_canned_*` factories and `_Stub*Gateway` classes. The accessible-name walker needs exactly the same seven dialogs. Extract rather than duplicate.

**Files:**

- Modify: `tests/integration/conftest.py` (receives the moved code and exposes the fixture)
- Modify: `tests/integration/test_screenshot_harness.py`

**Interfaces:**

- Produces: a **`common_dialogs` pytest fixture** returning `dict[str, QDialog]` — keys unchanged (`07_common_dialogs__about`, `…__error`, `…__rename_run`, `…__run_summary`, `…__resume_summary`, `…__retry_selection`, `…__generate_analysis`). Later tasks request this fixture by name.

> **Owner ruling — this supersedes an earlier draft of this task.** The first attempt created a
> standalone `tests/integration/common_dialog_builders.py` and imported it as
> `from tests.integration.common_dialog_builders import build_common_dialogs`. That import needs
> `tests/__init__.py` and `tests/integration/__init__.py` to exist, or `mypy --strict` fails with
> *"Source file found twice under different module names"* — and the `mypy-strict` pre-commit hook
> passes staged files in one invocation (`pass_filenames: true`), so it fires at commit time
> whenever both files are staged together. But STORY-083 (`e8fac7b`) deliberately deleted those
> two `__init__.py` files, and `tests/integration/conftest.py`'s own module docstring records why:
> *"There are zero `__init__.py` files anywhere under `tests/`; adding one just to support that
> kind of import would be a wider, unrelated change to how this repository's test tree is
> packaged."* `common_dialog_builders.py` was also the only non-test, non-conftest helper module
> anywhere under `tests/` — there is no precedent for one.
>
> **Resolution: no new module and no `__init__.py`.** The builders move into
> `tests/integration/conftest.py` as module-private helpers and are handed to test modules
> through a `common_dialogs` fixture, exactly the shape STORY-083 established when it replaced
> `from tests.integration.conftest import _seed_setting` with a `seed_setting` fixture. pytest
> auto-injects fixtures by name, so no test module needs a cross-module import.

- [ ] **Step 1: Read the current helper and its dependencies**

```bash
uv run python - <<'PY'
import re, pathlib
src = pathlib.Path("tests/integration/test_screenshot_harness.py").read_text()
for m in re.finditer(r"^(def|class) (_?\w+)", src, re.M):
    print(m.group(0))
PY
```

Note every `_canned_*` function and `_Stub*Gateway` class that `_build_common_dialogs` reaches.

- [ ] **Step 2: Move the helper and its dependencies into `conftest.py`**

Move into `tests/integration/conftest.py`, keeping them **module-private** (leading underscore): `_build_common_dialogs`, every `_canned_*` factory and `_Stub*Gateway` class it uses, and the module-level constants they reference (`_RUN_ID`, `_MODEL_NAME`, `_PROVIDER_ID`, `_TIMESTAMP`, `_DIALOG_SIZE`). Carry their imports across, merging into `conftest.py`'s existing import block rather than appending a second one.

`_DIALOG_SIZE` is also used by `_build_settings_dialog`, which stays in `test_screenshot_harness.py`. Leave that file's own `_DIALOG_SIZE` in place — a two-int tuple duplicated across a test-helper boundary carries no drift risk and avoids re-creating the cross-module import this ruling exists to prevent.

Then expose exactly one public surface, a fixture:

```python
@pytest.fixture
def common_dialogs(qtbot: QtBot) -> dict[str, QDialog]:
    """All seven shared modal dialogs, built with canned data and stub gateways.

    Both the mockup-conformance screenshot harness and the accessibility-name walker
    mount the same seven dialogs from this one definition rather than two drifting
    copies. Three of the seven builders return `QDialog | None` -- `None` when their
    gateway's canned data is too thin to pass the dialog's own precondition. The
    canned data here satisfies every one of those preconditions, so a `None` means
    the canned data regressed and the narrowing below must keep failing loudly.
    """
    return _build_common_dialogs(qtbot=qtbot)
```

Extend `conftest.py`'s module docstring — its **"No cross-module import"** paragraph is the authority this task is honouring — to name `common_dialogs` alongside `seed_setting`, `shutdown_handle`, and `dispatcher_shutdown_timeout_ms`.

- [ ] **Step 3: Point the screenshot harness at the fixture**

In `test_screenshot_harness.py`, delete the moved definitions and add **no import** — pytest injects fixtures by name. Both tests that called `_build_common_dialogs(qtbot=qtbot)` now take a `common_dialogs: dict[str, QDialog]` parameter and use it directly. A test that took `qtbot` only to pass it to the builder no longer needs `qtbot` at all; drop the now-unused parameter.

- [ ] **Step 4: Verify the screenshot harness still passes**

```bash
uv run pytest tests/integration/test_screenshot_harness.py -q
```

Expected: same pass count as before the change, no new failures. If a dialog now builds as `None`, an import or constant did not come across — fix the extraction, do not loosen the assertion.

Also confirm the packaging ruling holds:

```bash
ls tests/__init__.py tests/integration/__init__.py   # must BOTH be "No such file"
uv run mypy --strict tests/integration/conftest.py tests/integration/test_screenshot_harness.py
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/conftest.py tests/integration/test_screenshot_harness.py
git commit -m "test(story-097): share the common-dialog builders through a conftest fixture"
```

______________________________________________________________________

## Task 2: Write both acceptance-criteria tests — expect them RED

Write the tests before any production change so the ten pinned rows fail loudly and each later task can be measured by how many rows turn green.

**Files:**

- Create: `tests/integration/test_a11y_names_shell.py`

**Interfaces:**

- Consumes: two fixtures from `tests/integration/conftest.py` — `common_dialogs` (added by Task 1) and `build_real_app_without_enabled_providers`. Both are injected by name; this file imports nothing from another test module.

**Why that fixture and not `build_real_app`:** the seeded fixture installs three *enabled* providers, two pointing at real local endpoints. Mounting the shell then triggers a real model-discovery call per provider on the developer's machine, making the test's timing depend on whether Ollama happens to be running. With every provider disabled nothing is submitted and no socket is touched.

- [ ] **Step 1: Write the pinned-value test**

```python
"""Accessibility-name conformance for the application shell, the shared modal dialogs,
and the shared visual primitives (STORY-097).

The pinned strings below are written out as literals, deliberately. They are copied
from `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7.2 --
importing the production constants instead would make the assertion a tautology that
passes whenever production and spec drift together.
"""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QTextEdit,
    QWidget,
)
import pytest

from ollama_llm_bench.compose import AppHandle

_INTERACTIVE_TYPES: tuple[type[QWidget], ...] = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)


_COMPOSITE_TYPES: tuple[type[QWidget], ...] = (QComboBox, QAbstractItemView)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    A dropdown's popup list, and a table's column headers and corner button, are
    constructed by Qt itself rather than by application code. They are parts of the
    control the application already named, not controls of their own, so requiring a
    separate name on each would mean announcing filler like "Filter rows popup list"
    and would break every future dropdown or table until boilerplate was added.
    """
    parent = widget.parent()
    while parent is not None:
        if isinstance(parent, _COMPOSITE_TYPES):
            return True
        parent = parent.parent()
    return False


def _interactive_descendants(root: QWidget) -> list[QWidget]:
    """Return every interactive control in `root`'s subtree, `root` included.

    "Interactive" is the set a user can click into or type into. Container widgets,
    plain labels, and custom-painted presentation surfaces are excluded -- the floor
    requires a name on controls, not on decoration. Qt's internal parts of a
    composite control are excluded too; see `_has_composite_ancestor`.
    """
    found = [
        w
        for w in root.findChildren(QWidget)
        if isinstance(w, _INTERACTIVE_TYPES) and not _has_composite_ancestor(w)
    ]
    if isinstance(root, _INTERACTIVE_TYPES):
        found.append(root)
    return found
```

`QComboBox` and `QAbstractItemView` stay in `_INTERACTIVE_TYPES` — a dropdown and a table each still need their own name. Only their Qt-constructed guts are skipped.

Now the pinned rows. **Controller ruling — this supersedes an earlier draft of this step.** The
project's test rule (`.claude/rules/testing.md:69`) forbids `if` and `for` in a test body, and a
single parametrized test covering both surfaces would need an `if` to choose between mounting the
shell and mounting a dialog, plus a conditional expression for the readiness dot's first-line
tooltip. So AC-2 is proven by **three branch-free tests**, each declaring
`Proves: STORY-097-AC-2` on the first line of its docstring — the traceability generator accepts
more than one test per acceptance criterion. Module-level *helpers* may branch; test bodies may
not.

```python
_ABOUT = "07_common_dialogs__about"
_ERROR = "07_common_dialogs__error"
_GENERATE = "07_common_dialogs__generate_analysis"

_READINESS_DOT_OBJECT_NAME = "provider_readiness_indicator"
_READINESS_DOT_TOOLTIP_FIRST_LINE = "Provider readiness — click to open Settings / Providers"

# (objectName, accessible name, tooltip)
_SHELL_ROWS: tuple[tuple[str, str, str], ...] = (
    ("settings_menu_button", "Settings", "Open the Settings dialog"),
    (
        "about_menu_button",
        "About",
        "Application information: version, links, data folders",
    ),
    ("workspace_benchmark_button", "Benchmark workspace", "Benchmark workspace"),
    ("workspace_task_editor_button", "Task Editor workspace", "Task Editor workspace"),
    (
        "running_pill_button",
        "Run in progress — open Progress",
        "Switch to the Benchmark workspace and focus the Progress widget",
    ),
)

# (dialog surface key, objectName, accessible name, tooltip)
_DIALOG_ROWS: tuple[tuple[str, str, str, str], ...] = (
    (_ABOUT, "dialog_close_button", "Close dialog", "Close"),
    (_ERROR, "dialog_close_button", "Close dialog", "Close"),
    (
        _ABOUT,
        "open_data_folder_button",
        "Open application data folder",
        "Open the application data folder",
    ),
    (
        _ABOUT,
        "copy_data_folder_path_button",
        "Copy application data folder path",
        "Copy the application data folder path",
    ),
    (
        _GENERATE,
        "gate_busy_indicator",
        "Inference in flight — controls temporarily disabled",
        "An inference is in flight; please wait.",
    ),
)


@pytest.mark.parametrize(
    ("object_name", "accessible_name", "tooltip"),
    _SHELL_ROWS,
    ids=[row[0] for row in _SHELL_ROWS],
)
def test_shell_registry_controls_use_pinned_values(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-097-AC-2

    Each icon-only or ambiguous control the application shell owns reports exactly the
    objectName, accessible name, and tooltip pinned by the accessibility registry -- no
    substitute, abbreviated, or generic value.
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()

    # Act
    control = handle.window.findChild(QWidget, object_name)

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted on the shell"
    assert (control.accessibleName(), control.toolTip()) == (accessible_name, tooltip)


@pytest.mark.parametrize(
    ("surface", "object_name", "accessible_name", "tooltip"),
    _DIALOG_ROWS,
    ids=[f"{row[0]}:{row[1]}" for row in _DIALOG_ROWS],
)
def test_dialog_registry_controls_use_pinned_values(
    common_dialogs: dict[str, QDialog],
    surface: str,
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-097-AC-2

    Each icon-only or ambiguous control the shared modal dialogs own reports exactly the
    objectName, accessible name, and tooltip pinned by the accessibility registry.
    """
    # Arrange
    root = common_dialogs[surface]

    # Act
    control = root.findChild(QWidget, object_name)

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted on {surface}"
    assert (control.accessibleName(), control.toolTip()) == (accessible_name, tooltip)


def test_readiness_dot_tooltip_leads_with_the_pinned_sentence(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
) -> None:
    """Proves: STORY-097-AC-2

    The provider-readiness dot reports the pinned objectName and accessible name, and its
    tooltip's FIRST line is the registry's pinned sentence. Only the first line is pinned:
    the lines beneath it carry the per-provider reachability detail the Main Window
    specification separately requires, which the registry's one sentence does not include.
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()

    # Act
    dot = handle.window.findChild(QWidget, _READINESS_DOT_OBJECT_NAME)

    # Assert
    assert dot is not None, "no provider-readiness dot is mounted on the shell"
    assert (dot.accessibleName(), dot.toolTip().splitlines()[0]) == (
        "Provider readiness status",
        _READINESS_DOT_TOOLTIP_FIRST_LINE,
    )
```

Note the running pill is hidden when no run is active, but `findChild` finds hidden children — the assertion holds without starting a run.

- [ ] **Step 2: Write the accessible-name walker**

```python
_DIALOG_SURFACES: tuple[str, ...] = (
    "07_common_dialogs__about",
    "07_common_dialogs__error",
    "07_common_dialogs__rename_run",
    "07_common_dialogs__run_summary",
    "07_common_dialogs__resume_summary",
    "07_common_dialogs__retry_selection",
    "07_common_dialogs__generate_analysis",
)


def test_every_shell_control_has_a_nonempty_accessible_name(
    common_dialogs: dict[str, QDialog],
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
) -> None:
    """Proves: STORY-097-AC-1

    Every interactive control mounted by the application shell, the seven shared modal
    dialogs, and the shared visual primitives reports a non-empty accessible name, so an
    assistive technology can announce it and a name-based UI test can address it.
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()
    menu_bar = handle.window.findChild(QWidget, "menu_bar")
    status_bar = handle.window.findChild(QWidget, "status_bar")
    assert menu_bar is not None
    assert status_bar is not None
    surfaces: list[QWidget] = [
        menu_bar,
        status_bar,
        *(common_dialogs[key] for key in _DIALOG_SURFACES),
    ]

    # Act
    unnamed = [
        f"{surface.objectName() or type(surface).__name__} > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'})"
        for surface in surfaces
        for control in _interactive_descendants(surface)
        if not control.accessibleName()
    ]

    # Assert
    assert unnamed == []
```

The walker is scoped to the menu bar and status bar rather than the whole main window because the whole window also mounts the New Benchmark, Progress, Result, Resume, and Task Editor widgets — those belong to STORY-098 and STORY-099 and would make this test fail for reasons outside its own scope.

- [ ] **Step 3: Run both tests and record the failure shape**

```bash
uv run pytest tests/integration/test_a11y_names_shell.py -q
```

Expected: 12 failures — 11 pinned-value cases (5 shell + 5 dialog + the readiness dot; all report `no control named … is mounted`, since not one pinned test handle exists yet) plus the walker listing roughly 40 unnamed controls. **Save this output**; each later task cites the reduced count as its gate.

- [ ] **Step 4: Commit the RED tests**

```bash
git add tests/integration/test_a11y_names_shell.py
git commit -m "test(story-097): add failing accessible-name and pinned-value tests"
```

______________________________________________________________________

## Task 3: Add the two new shared primitives and name the existing ones

**Files:**

- Create: `src/ollama_llm_bench/ui/shared/_internal/dialog_close_button.py`
- Create: `src/ollama_llm_bench/ui/shared/_internal/gate_busy_indicator.py`
- Modify: `src/ollama_llm_bench/ui/shared/api.py`, `src/ollama_llm_bench/ui/shared/__init__.py`
- Modify: `src/ollama_llm_bench/ui/shared/_internal/multi_check_filter_button.py`
- Modify: `src/ollama_llm_bench/ui/shared/provider_dropdown/_internal/view.py`
- Modify: `src/ollama_llm_bench/ui/shared/model_dropdown/_internal/view.py`
- Test: `src/ollama_llm_bench/ui/shared/tests/test_dialog_close_button.py`, `src/ollama_llm_bench/ui/shared/tests/test_gate_busy_indicator.py`

**Interfaces:**

- Produces:
  - `make_dialog_close_button(*, role: str = "primary-button") -> QPushButton`
  - `make_gate_busy_indicator(*, message: str) -> QLabel`

Both return the concrete Qt class rather than `QWidget`, unlike the module's three existing factories. That is deliberate: callers must reach `.setDefault(True)`, `.clicked`, `.setText(...)`, and `.setVisible(...)`. The convention exists so callers do not depend on *our* internal classes; `QPushButton` and `QLabel` are toolkit types, so nothing is leaked.

- [ ] **Step 1: Write the failing tests for both primitives**

Create `src/ollama_llm_bench/ui/shared/tests/test_dialog_close_button.py`:

```python
"""Unit tests for the shared dialog Close button (STORY-097)."""

from PySide6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.shared import make_dialog_close_button


def test_dialog_close_button_carries_the_pinned_identity(qtbot: QtBot) -> None:
    """The shared Close button reports the registry's pinned objectName, accessible
    name, and tooltip, so every dialog mounting it conforms by construction."""
    # Arrange / Act
    button = make_dialog_close_button()
    qtbot.addWidget(button)

    # Assert
    assert (button.objectName(), button.accessibleName(), button.toolTip()) == (
        "dialog_close_button",
        "Close dialog",
        "Close",
    )


def test_dialog_close_button_uses_the_requested_style_role(qtbot: QtBot) -> None:
    """A Close button sitting left of a distinct confirm takes the outlined-muted role;
    a Close button that is the footer's only action stays the filled primary."""
    # Arrange / Act
    beside_confirm = make_dialog_close_button(role="outlined-muted-button")
    qtbot.addWidget(beside_confirm)

    # Assert
    assert beside_confirm.property("role") == "outlined-muted-button"


def test_dialog_close_button_reads_close(qtbot: QtBot) -> None:
    """The button's visible text is `Close` -- the accessible name is the longer
    `Close dialog`, and the two are independent by design."""
    # Arrange / Act
    button: QPushButton = make_dialog_close_button()
    qtbot.addWidget(button)

    # Assert
    assert button.text() == "Close"
```

Create `src/ollama_llm_bench/ui/shared/tests/test_gate_busy_indicator.py`:

```python
"""Unit tests for the shared gate-busy indicator strip (STORY-097)."""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.shared import make_gate_busy_indicator

_GENERATE_ANALYSIS_MESSAGE = "An inference is currently in flight — please wait."


def test_gate_busy_indicator_carries_the_pinned_identity(qtbot: QtBot) -> None:
    """The shared strip reports the registry's pinned objectName, accessible name, and
    tooltip regardless of which sentence the caller supplies."""
    # Arrange / Act
    strip = make_gate_busy_indicator(message=_GENERATE_ANALYSIS_MESSAGE)
    qtbot.addWidget(strip)

    # Assert
    assert (strip.objectName(), strip.accessibleName(), strip.toolTip()) == (
        "gate_busy_indicator",
        "Inference in flight — controls temporarily disabled",
        "An inference is in flight; please wait.",
    )


def test_gate_busy_indicator_shows_the_callers_message(qtbot: QtBot) -> None:
    """The visible sentence is the caller's, because each surface's wording is pinned by
    that surface's own spec -- only the identity attributes are shared."""
    # Arrange / Act
    strip = make_gate_busy_indicator(message=_GENERATE_ANALYSIS_MESSAGE)
    qtbot.addWidget(strip)

    # Assert
    assert strip.text() == _GENERATE_ANALYSIS_MESSAGE


def test_gate_busy_indicator_starts_hidden(qtbot: QtBot) -> None:
    """The strip is mounted permanently and revealed only while the gate is held, so it
    must not be visible at construction."""
    # Arrange / Act
    strip = make_gate_busy_indicator(message=_GENERATE_ANALYSIS_MESSAGE)
    qtbot.addWidget(strip)

    # Assert
    assert not strip.isVisible()
```

- [ ] **Step 2: Run them to confirm they fail**

```bash
uv run pytest src/ollama_llm_bench/ui/shared/tests/test_dialog_close_button.py src/ollama_llm_bench/ui/shared/tests/test_gate_busy_indicator.py -q
```

Expected: collection errors — `cannot import name 'make_dialog_close_button'`.

- [ ] **Step 3: Implement the dialog Close button**

`src/ollama_llm_bench/ui/shared/_internal/dialog_close_button.py`:

```python
"""The one definition of a modal dialog's Close button (08_ACCESSIBILITY_FLOOR §7.2).

The registry pins one objectName, accessible name, and tooltip for the dialog-close
control across every screen it appears on. Defining the button here rather than in each
dialog is what makes "repeated controls share one objectName pattern" true by
construction instead of by seven copies staying in agreement.
"""

from typing import Final

from PySide6.QtWidgets import QPushButton

__all__: list[str] = ["build_dialog_close_button"]

DIALOG_CLOSE_OBJECT_NAME: Final = "dialog_close_button"
DIALOG_CLOSE_ACCESSIBLE_NAME: Final = "Close dialog"
DIALOG_CLOSE_TOOLTIP: Final = "Close"
DIALOG_CLOSE_TEXT: Final = "Close"


def build_dialog_close_button(*, role: str) -> QPushButton:
    """Build a dialog Close button carrying the registry's pinned identity.

    Args:
        role: The theme style role. Use ``"primary-button"`` when Close is the
            footer's only or right-most action, and ``"outlined-muted-button"``
            when it sits to the left of a distinct primary confirm.

    Returns:
        The button, unconnected -- the mounting dialog wires its own ``clicked``.
    """
    button = QPushButton(DIALOG_CLOSE_TEXT)
    button.setObjectName(DIALOG_CLOSE_OBJECT_NAME)
    button.setAccessibleName(DIALOG_CLOSE_ACCESSIBLE_NAME)
    button.setToolTip(DIALOG_CLOSE_TOOLTIP)
    button.setProperty("role", role)
    return button
```

- [ ] **Step 4: Implement the gate-busy strip**

`src/ollama_llm_bench/ui/shared/_internal/gate_busy_indicator.py`:

```python
"""The one definition of the gate-busy indicator strip (08_ACCESSIBILITY_FLOOR §7.2).

Shown while the application-wide single-inference gate is held by some other activity,
to explain why a control is temporarily disabled. The registry pins the identity
attributes; the visible sentence stays the caller's, because each surface's wording is
pinned separately by that surface's own specification.

Deliberately not animated. The registry table calls this a "spinner", but every mockup
draws a static strip, and ADR-0018 retired support for the operating system's
reduced-motion preference -- a looping animation would have no way to be switched off.
"""

from typing import Final

from PySide6.QtWidgets import QLabel

__all__: list[str] = ["build_gate_busy_indicator"]

GATE_BUSY_OBJECT_NAME: Final = "gate_busy_indicator"
GATE_BUSY_ACCESSIBLE_NAME: Final = "Inference in flight — controls temporarily disabled"
GATE_BUSY_TOOLTIP: Final = "An inference is in flight; please wait."


def build_gate_busy_indicator(*, message: str) -> QLabel:
    """Build a hidden gate-busy strip showing `message`.

    Args:
        message: The sentence the mounting surface's own specification pins.

    Returns:
        The strip, hidden -- the mounting surface reveals it when the gate is held.
    """
    strip = QLabel(message)
    strip.setObjectName(GATE_BUSY_OBJECT_NAME)
    strip.setAccessibleName(GATE_BUSY_ACCESSIBLE_NAME)
    strip.setToolTip(GATE_BUSY_TOOLTIP)
    strip.setProperty("role", "info-callout")
    strip.setWordWrap(True)
    strip.setVisible(False)
    return strip
```

- [ ] **Step 5: Expose both through the module's public surface**

In `src/ollama_llm_bench/ui/shared/api.py`, add the imports beside the existing ones and append the two factories. Keep `__all__` alphabetical:

```python
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from ollama_llm_bench.ui.shared._internal.dialog_close_button import (
    DIALOG_CLOSE_OBJECT_NAME,
    build_dialog_close_button,
)
from ollama_llm_bench.ui.shared._internal.gate_busy_indicator import (
    GATE_BUSY_OBJECT_NAME,
    build_gate_busy_indicator,
)
```

```python
__all__: list[str] = [
    "make_badge_label",
    "make_dialog_close_button",
    "make_gate_busy_indicator",
    "make_health_dot",
    "make_multi_check_filter_button",
    "resolve_badge_color_roles",
]
```

```python
@icontract.require(lambda role: len(role) > 0, "role must name a theme style role")
@icontract.ensure(lambda result: result.objectName() == DIALOG_CLOSE_OBJECT_NAME)
def make_dialog_close_button(*, role: str = "primary-button") -> QPushButton:
    """Build a dialog Close button carrying the pinned registry identity (§7.2).

    Args:
        role: The theme style role -- ``"primary-button"`` when Close is the footer's
            only or right-most action, ``"outlined-muted-button"`` when it sits left
            of a distinct primary confirm.

    Returns:
        The button, unconnected; the mounting dialog wires its own ``clicked`` handler.
    """
    return build_dialog_close_button(role=role)


@icontract.require(lambda message: len(message) > 0, "message must be non-empty")
@icontract.ensure(lambda result: result.objectName() == GATE_BUSY_OBJECT_NAME)
def make_gate_busy_indicator(*, message: str) -> QLabel:
    """Build the hidden gate-busy strip carrying the pinned registry identity (§7.2).

    Args:
        message: The sentence pinned by the mounting surface's own specification.

    Returns:
        The strip, hidden until the mounting surface reveals it.
    """
    return build_gate_busy_indicator(message=message)
```

In `src/ollama_llm_bench/ui/shared/__init__.py`, add both names to the imports from `.api` and to the literal `__all__`.

- [ ] **Step 6: Name the three remaining shared interactive controls**

`_internal/multi_check_filter_button.py`, in `__init__` right after `setProperty("role", ...)`:

```python
self.setAccessibleName(label)
```

`provider_dropdown/_internal/view.py`, after `setProperty("role", "dropdown")`:

```python
self.setAccessibleName("Provider")
```

`model_dropdown/_internal/view.py`, after `setProperty("role", "dropdown")`:

```python
self.setAccessibleName("Model")
```

An input field's accessible name is its field label, and these two dropdowns are labelled "Provider" and "Model" wherever they are mounted. A consumer needing something different can still call `setAccessibleName` after construction — the same way consumers already set the objectName from outside.

- [ ] **Step 7: Run the new unit tests and the shared module's existing suite**

```bash
uv run pytest src/ollama_llm_bench/ui/shared -q
```

Expected: all pass, including the pre-existing badge/health-dot/filter-button tests.

- [ ] **Step 8: Lint, typecheck, and check the architecture guard**

```bash
uv run ruff check src/ollama_llm_bench/ui/shared
uv run ruff format --check src/ollama_llm_bench/ui/shared
uv run mypy --strict src/ollama_llm_bench/ui/shared
uv run pytest tests/architecture/test_ui_shared_style_authority.py -q
```

Expected: clean. The architecture guard scans for colour literals — the two new files contain none.

- [ ] **Step 9: Commit**

```bash
git add src/ollama_llm_bench/ui/shared
git commit -m "feat(story-097): add shared dialog-close and gate-busy primitives with pinned names"
```

______________________________________________________________________

## Task 4: Pin the six shell controls and rename their test handles

**Files:**

- Modify: `src/ollama_llm_bench/ui/main_window/_internal/menu_bar.py`
- Modify: `src/ollama_llm_bench/ui/main_window/_internal/status_bar.py`
- Modify: `src/ollama_llm_bench/ui/main_window/_internal/close_handler.py`
- Modify (rename follow-through): `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py`, `tests/integration/test_theme_reapply_on_save.py`, `tests/integration/test_menu_opens_dialogs.py`, `tests/integration/test_compose_build_app.py`, `tests/integration/test_launch_not_ready_gating.py`, `tests/integration/test_quit_sequence.py`

**Interfaces:**

- Consumes: nothing from earlier tasks.
- Produces: the six pinned test handles the Task 2 test looks for.

**Rename map** — apply everywhere, production and tests:

| Old                              | New                            |
| -------------------------------- | ------------------------------ |
| `settings_action`                | `settings_menu_button`         |
| `about_action`                   | `about_menu_button`            |
| `workspace_switcher_benchmark`   | `workspace_benchmark_button`   |
| `workspace_switcher_task_editor` | `workspace_task_editor_button` |
| `running_pill`                   | `running_pill_button`          |

**Rename only the `setObjectName`/`findChild` string literals.** Do not rename the Python attributes (`self._settings_action`), the view-model fields (`settings_action_enabled`, `running_pill_visible`, `running_pill_label`), the signals (`running_pill_clicked`), or the test function names — those are unrelated identifiers that merely share a word, and renaming them would balloon the diff for no benefit.

- [ ] **Step 1: Add the pinned constants to `menu_bar.py`**

Beside the existing `_DISABLED_SETTINGS_TOOLTIP`:

```python
_SETTINGS_TOOLTIP: Final = "Open the Settings dialog"
_ABOUT_TOOLTIP: Final = "Application information: version, links, data folders"
_BENCHMARK_WORKSPACE_LABEL: Final = "Benchmark workspace"
_TASK_EDITOR_WORKSPACE_LABEL: Final = "Task Editor workspace"
_RUNNING_PILL_ACCESSIBLE_NAME: Final = "Run in progress — open Progress"
_RUNNING_PILL_TOOLTIP: Final = (
    "Switch to the Benchmark workspace and focus the Progress widget"
)
```

- [ ] **Step 2: Pin the two workspace segments**

In `_WorkspaceSwitcherWidget.__init__`, replace lines 30–37 with:

```python
self._benchmark_button = QPushButton("Benchmark")
self._benchmark_button.setObjectName("workspace_benchmark_button")
self._benchmark_button.setAccessibleName(_BENCHMARK_WORKSPACE_LABEL)
self._benchmark_button.setToolTip(_BENCHMARK_WORKSPACE_LABEL)
self._benchmark_button.setCheckable(True)
self._benchmark_button.setProperty("role", "segmented-control")
self._task_editor_button = QPushButton("Task Editor")
self._task_editor_button.setObjectName("workspace_task_editor_button")
self._task_editor_button.setAccessibleName(_TASK_EDITOR_WORKSPACE_LABEL)
self._task_editor_button.setToolTip(_TASK_EDITOR_WORKSPACE_LABEL)
self._task_editor_button.setCheckable(True)
self._task_editor_button.setProperty("role", "segmented-control")
```

The visible text stays "Benchmark" / "Task Editor" while the announced name is the longer "Benchmark workspace" — the registry pins the longer form because "Benchmark" alone is ambiguous when announced with no visual context.

- [ ] **Step 3: Pin Settings, About, and the running pill**

In `MenuBarWidget.__init__`, replace lines 81–95 with:

```python
self._settings_action = QPushButton("Settings")
self._settings_action.setObjectName("settings_menu_button")
self._settings_action.setAccessibleName("Settings")
self._settings_action.setToolTip(_SETTINGS_TOOLTIP)
self._settings_action.setProperty("role", "menu-action")
self._settings_action.clicked.connect(self.settings_requested)
self._about_action = QPushButton("About")
self._about_action.setObjectName("about_menu_button")
self._about_action.setAccessibleName("About")
self._about_action.setToolTip(_ABOUT_TOOLTIP)
self._about_action.setProperty("role", "menu-action")
self._about_action.clicked.connect(self.about_requested)
self._workspace_switcher = _WorkspaceSwitcherWidget()
self._workspace_switcher.segment_activated.connect(self.workspace_switch_requested)
self._running_pill = QPushButton()
self._running_pill.setObjectName("running_pill_button")
self._running_pill.setAccessibleName(_RUNNING_PILL_ACCESSIBLE_NAME)
self._running_pill.setToolTip(_RUNNING_PILL_TOOLTIP)
self._running_pill.setProperty("role", "running-pill")
self._running_pill.clicked.connect(self.running_pill_clicked)
self._running_pill.setVisible(False)
```

The pill's *visible* text is the run's name and changes as runs come and go; its *announced* name is the fixed "Run in progress — open Progress", so it is set once in the constructor and never recomputed.

- [ ] **Step 4: Make the Settings tooltip state-dependent**

In `apply_view_model`, replace the `setToolTip` call:

```python
self._settings_action.setToolTip(
    _SETTINGS_TOOLTIP if view_model.settings_action_enabled else _DISABLED_SETTINGS_TOOLTIP
)
```

Previously the enabled state carried an empty tooltip. The disabled string is unchanged — it is pinned verbatim by the Main Window spec and asserted by an existing test.

- [ ] **Step 5: Pin the readiness dot**

In `status_bar.py`, add beside the other module constants:

```python
_READINESS_DOT_OBJECT_NAME: Final = "provider_readiness_indicator"
_READINESS_DOT_ACCESSIBLE_NAME: Final = "Provider readiness status"
_READINESS_DOT_TOOLTIP: Final = "Provider readiness — click to open Settings / Providers"
```

Then in `_rebuild_health_dot`, replace the single `dot.setToolTip(...)` line with:

```python
dot.setObjectName(_READINESS_DOT_OBJECT_NAME)
dot.setAccessibleName(_READINESS_DOT_ACCESSIBLE_NAME)
dot.setToolTip(f"{_READINESS_DOT_TOOLTIP}\n\n{view_model.health_tooltip}")
```

Three things to understand here:

- The dot is **destroyed and rebuilt on every view-model application**, so all three attributes must be set inside `_rebuild_health_dot`, not once at construction.

- `make_health_dot` already sets a generic accessible name of the form `"LIVE: Ready"`. Overriding it after construction is correct and deliberate: the registry pins this particular dot's name, and other consumers of the shared primitive keep the state-in-words default.

- The tooltip is the pinned sentence, a blank line, then the existing per-provider detail. An existing test asserts `"provider-1: unreachable" in tooltip`, which the prefix does not disturb.

- [ ] **Step 6: Name the four quit-confirmation buttons**

In `close_handler.py`, `QMessageBox.addButton(...)` returns the created `QPushButton`. Capture and name each:

```python
cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
cancel_button.setObjectName("main_window.quit_confirm.cancel_button")
cancel_button.setAccessibleName("Cancel")
confirm_button = box.addButton("Confirm", QMessageBox.ButtonRole.AcceptRole)
confirm_button.setObjectName("main_window.quit_confirm.confirm_button")
confirm_button.setAccessibleName("Confirm")
```

Do the same for the unsaved-changes box's `Discard All`, `Cancel`, and `Save All` buttons, using the prefix `main_window.quit_unsaved.`. Match the existing `addButton(...)` calls' exact button-role arguments — read lines 151–166 and preserve them. These four are not reached by the Task 2 walker (a quit confirmation is not mounted in the idle shell), but they are interactive controls in this module and the floor applies to them.

- [ ] **Step 7: Follow the renames through every test**

```bash
grep -rln 'settings_action"\|about_action"\|workspace_switcher_benchmark\|workspace_switcher_task_editor\|"running_pill"' src tests
```

Update each hit. Expect: `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py` (6 sites), `tests/integration/test_theme_reapply_on_save.py`, `test_menu_opens_dialogs.py` (2), `test_compose_build_app.py` (4), `test_launch_not_ready_gating.py`, `test_quit_sequence.py`.

- [ ] **Step 8: Run the shell's own tests plus every integration test that addresses it**

```bash
uv run pytest src/ollama_llm_bench/ui/main_window tests/integration/test_menu_opens_dialogs.py tests/integration/test_compose_build_app.py tests/integration/test_quit_sequence.py tests/integration/test_launch_not_ready_gating.py tests/integration/test_theme_reapply_on_save.py -q
```

Expected: all pass. A `findChild` returning `None` means a rename site was missed.

- [ ] **Step 9: Confirm six pinned rows now pass**

```bash
uv run pytest tests/integration/test_a11y_names_shell.py -q
```

Expected: the five `test_shell_registry_controls_use_pinned_values` cases and `test_readiness_dot_tooltip_leads_with_the_pinned_sentence` pass — six in all; the five dialog cases and the walker still fail.

- [ ] **Step 10: Lint, typecheck, commit**

```bash
uv run ruff check src/ollama_llm_bench/ui/main_window tests
uv run ruff format --check src/ollama_llm_bench/ui/main_window tests
uv run mypy --strict src/ollama_llm_bench/ui/main_window
git add src/ollama_llm_bench/ui/main_window tests
git commit -m "feat(story-097): pin shell control names, handles, and tooltips"
```

______________________________________________________________________

## Task 5: Adopt the shared primitives in About, Error, and Generate Analysis

**Files:**

- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/about_view.py`
- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/error_view.py`
- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/generate_analysis_view.py`
- Modify: `src/ollama_llm_bench/ui/common_dialogs/tests/test_error_dialog.py`, `test_generate_analysis_dialog.py`

**Interfaces:**

- Consumes: `make_dialog_close_button`, `make_gate_busy_indicator` from Task 3.

- [ ] **Step 1: Adopt the shared Close button in the About dialog**

Add the import:

```python
from ollama_llm_bench.ui.shared import make_dialog_close_button
```

Replace `_build_footer`'s body (lines 142–151):

```python
def _build_footer(self) -> QHBoxLayout:
    footer = QHBoxLayout()
    footer.addStretch()
    self.close_button = make_dialog_close_button()
    self.close_button.setDefault(True)
    self.close_button.clicked.connect(self.accept)
    footer.addWidget(self.close_button)
    return footer
```

Close is this footer's only action, so it keeps the filled primary role — which is the factory's default.

- [ ] **Step 2: Pin the About dialog's two icon buttons**

Change only the objectName and add an accessible name; the tooltips already match the pinned values exactly:

```python
self.copy_path_button.setObjectName("copy_data_folder_path_button")
self.copy_path_button.setAccessibleName("Copy application data folder path")
```

```python
self.open_folder_button.setObjectName("open_data_folder_button")
self.open_folder_button.setAccessibleName("Open application data folder")
```

- [ ] **Step 3: Name the About dialog's remaining interactive control**

The repository link is a `QLabel` with a clickable hyperlink, not one of the interactive widget classes the walker inspects — but it is a real affordance, so name it anyway:

```python
self._repository_link.setAccessibleName("Project on GitHub")
self._repository_link.setToolTip("Open the project's GitHub repository in your browser")
```

- [ ] **Step 4: Adopt the shared Close button in the Error dialog**

Add the same import. In `_build_footer`, replace the `else` branch (lines 121–127):

```python
else:
    self.close_button = make_dialog_close_button()
    self.close_button.setDefault(True)
    self.close_button.clicked.connect(self.accept)
    footer.addWidget(self.close_button)
```

- [ ] **Step 5: Name the Error dialog's other controls**

```python
self.copy_details_button.setAccessibleName("Copy Details")
```

```python
self.action_button.setAccessibleName(payload.action.label)
```

```python
self.quit_button.setAccessibleName("Quit")
```

```python
self._detail_edit.setAccessibleName("Error detail")
```

The detail box is a read-only `QTextEdit`, but it accepts focus and is scrollable, so it is an interactive control the walker will check.

- [ ] **Step 6: Update the two Error-dialog tests that address the old handle**

In `src/ollama_llm_bench/ui/common_dialogs/tests/test_error_dialog.py`, replace `"common_dialogs.error.close_button"` with `"dialog_close_button"` at lines 106 and 166. Both assertions keep their meaning: line 106 asserts a Close button exists for non-fatal patterns, line 166 asserts the fatal pattern has none.

- [ ] **Step 7: Adopt the shared gate-busy strip in the Generate Analysis dialog**

Add the import beside the existing shared-dropdown imports:

```python
from ollama_llm_bench.ui.shared import make_gate_busy_indicator
```

Replace the `_busy_label` construction (lines 146–151):

```python
self._busy_label = make_gate_busy_indicator(message=_GATE_BUSY_MESSAGE)
outer.addWidget(self._busy_label)
```

`_GATE_BUSY_MESSAGE` keeps its current value — `"An inference is currently in flight — please wait."` — which is pinned verbatim by this dialog's own specification and must not change. Everything that reads or toggles `self._busy_label` elsewhere in the file (`_enter_gate_busy_state`, `_on_inference_activity_changed`) keeps working unchanged: the factory returns a `QLabel` with the same `role="info-callout"`, word wrap, and hidden-at-construction behaviour the hand-rolled label had.

- [ ] **Step 8: Name the Generate Analysis dialog's remaining controls**

```python
cancel_button.setObjectName("common_dialogs.generate_analysis.cancel_button")
cancel_button.setAccessibleName("Cancel")
```

```python
self._confirm_button.setAccessibleName(button_label)
```

The two dropdowns already carry "Provider" and "Model" from Task 3.

- [ ] **Step 9: Update the Generate Analysis test addressing the old handle**

In `test_generate_analysis_dialog.py` line 237, replace `"common_dialogs.generate_analysis.busy_label"` with `"gate_busy_indicator"`.

- [ ] **Step 10: Run the dialogs' own tests**

```bash
uv run pytest src/ollama_llm_bench/ui/common_dialogs -q
```

Expected: all pass.

- [ ] **Step 11: Confirm all eleven pinned rows now pass**

```bash
uv run pytest tests/integration/test_a11y_names_shell.py -q -k "pinned"
```

Expected: 11 passed (5 shell + 5 dialog + the readiness dot). The walker still fails — Task 6 finishes it.

- [ ] **Step 12: Lint, typecheck, commit**

```bash
uv run ruff check src/ollama_llm_bench/ui/common_dialogs
uv run ruff format --check src/ollama_llm_bench/ui/common_dialogs
uv run mypy --strict src/ollama_llm_bench/ui/common_dialogs
git add src/ollama_llm_bench/ui/common_dialogs
git commit -m "feat(story-097): adopt shared close and gate-busy primitives in About, Error, Generate Analysis"
```

______________________________________________________________________

## Task 6: Name every remaining dialog control and give the unnamed buttons a test handle

Four dialogs are untouched so far. Each needs an accessible name on every interactive control, and nine buttons across them have no test handle at all.

**Files:**

- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/view.py` (Run Summary)
- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/rename_run_view.py`
- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/resume_summary_view.py`
- Modify: `src/ollama_llm_bench/ui/common_dialogs/_internal/retry_selection_view.py`

**Convention:** the accessible name of a button with visible text is that text. The test handle follows the file's existing `common_dialogs.<dialog>.<snake_name>` pattern.

- [ ] **Step 1: Run Summary dialog (`view.py`)**

```python
self._back_button = QPushButton("Back")
self._back_button.setObjectName("common_dialogs.run_summary.back_button")
self._back_button.setAccessibleName("Back")
```

```python
self._start_button.setAccessibleName("Start Benchmark")
```

The `QScrollArea` at line 54 is a viewport container, not a control the user acts on; the walker's interactive set does not include it and it needs no name.

- [ ] **Step 2: Rename Run dialog (`rename_run_view.py`)**

All four controls already have test handles; add names only.

```python
self.new_name_edit.setAccessibleName("New run name")
```

```python
self.use_default_button.setAccessibleName("Use default")
```

```python
self.cancel_button.setAccessibleName("Cancel")
```

```python
self.rename_button.setAccessibleName("Rename")
```

Also fix a real defect the audit surfaced: the Rename button is disabled while the typed name is invalid but carries no tooltip explaining why, which the project's own UI rule forbids. In `_revalidate` (line 124, immediately after `self._validation_label.setText(...)`), replace the lone `setEnabled` call with:

```python
self.rename_button.setEnabled(result.is_valid)
self.rename_button.setToolTip("" if result.is_valid else (result.message or ""))
```

`ValidationResult.message` is `str | None` — the first failing rule's message, or `None` when the name is valid — so the `or ""` guard keeps `mypy --strict` happy without changing behaviour.

- [ ] **Step 3: Resume Summary dialog (`resume_summary_view.py`)**

```python
self.override_checkbox.setAccessibleName("Resume anyway")
```

```python
select_all = QPushButton("Select all")
select_all.setObjectName("common_dialogs.resume_summary.select_all_button")
select_all.setAccessibleName("Select all")
```

```python
clear_all = QPushButton("Clear all")
clear_all.setObjectName("common_dialogs.resume_summary.clear_all_button")
clear_all.setAccessibleName("Clear all")
```

```python
self.task_list.setAccessibleName("Tasks to resume")
```

```python
cancel_button = QPushButton("Cancel")
cancel_button.setObjectName("common_dialogs.resume_summary.cancel_button")
cancel_button.setAccessibleName("Cancel")
```

```python
self.resume_button.setAccessibleName("Resume Run")
```

```python
fix_button = QPushButton("Fix in Settings")
fix_button.setObjectName("common_dialogs.resume_summary.fix_in_settings_button")
fix_button.setAccessibleName("Fix in Settings")
```

The "Fix in Settings" button is created once per drift-warning row, so several instances can share the one objectName. That is the same pattern the registry mandates for repeated controls and is harmless here — no test addresses it by name.

- [ ] **Step 4: Retry Selection dialog (`retry_selection_view.py`)**

```python
self.filter_combo.setAccessibleName("Filter rows")
```

```python
check_all = QPushButton("Check all visible")
check_all.setObjectName("common_dialogs.retry_selection.check_all_button")
check_all.setAccessibleName("Check all visible")
```

```python
uncheck_all = QPushButton("Uncheck all visible")
uncheck_all.setObjectName("common_dialogs.retry_selection.uncheck_all_button")
uncheck_all.setAccessibleName("Uncheck all visible")
```

```python
self.table.setAccessibleName("Rows available to retry")
```

```python
cancel_button = QPushButton("Cancel")
cancel_button.setObjectName("common_dialogs.retry_selection.cancel_button")
cancel_button.setAccessibleName("Cancel")
```

```python
self.retry_button.setAccessibleName("Retry Selected")
```

Also give the Retry Selected button the missing explanatory tooltip. At line 180, immediately after `self.summary_label.setText(...)`, replace the lone `setEnabled` call with:

```python
self.retry_button.setEnabled(selected > 0)
self.retry_button.setToolTip("" if selected > 0 else "Select at least one row to retry.")
```

`selected` is the local already computed a few lines above and used in the summary line — do not introduce a second count.

- [ ] **Step 5: Run the walker — this is the task's real gate**

```bash
uv run pytest tests/integration/test_a11y_names_shell.py -q
```

Expected: 12 passed. If the walker still fails, its assertion message names each unnamed control as `surface > WidgetClass(objectName)` — go name exactly those. Do not weaken the interactive-type tuple to make it pass.

- [ ] **Step 6: Run the whole common-dialogs suite**

```bash
uv run pytest src/ollama_llm_bench/ui/common_dialogs -q
```

Expected: all pass. The two new tooltips may break an existing assertion that a tooltip is empty — if so, update the assertion to the new explanatory text; that is the intended behaviour change, not a regression.

- [ ] **Step 7: Lint, typecheck, commit**

```bash
uv run ruff check src/ollama_llm_bench/ui/common_dialogs
uv run ruff format --check src/ollama_llm_bench/ui/common_dialogs
uv run mypy --strict src/ollama_llm_bench/ui/common_dialogs
git add src/ollama_llm_bench/ui/common_dialogs
git commit -m "feat(story-097): name every remaining shared-dialog control"
```

______________________________________________________________________

## Task 7: Full-gate verification

This story touches `ui/shared` — a module almost every widget imports — and renames test handles used by integration tests. That is squarely inside the blast radius that requires the full gate, not just the changed modules' own tests.

- [ ] **Step 1: Run the full suite, bounded**

```bash
uv run pytest tests/unit tests/integration tests/e2e src -q
```

Expected: completes in roughly two minutes with zero failures. **Materially longer means it hung** — there is no test timeout configured, so a blocking modal produces no output at all. Kill it and diagnose rather than waiting.

Do **not** run this concurrently with any other full-suite run, including in a second agent. Timing-sensitive Qt tests fail under contention in a way indistinguishable from a real regression.

- [ ] **Step 2: If a failure appears, prove attribution before blaming it on something else**

Never accept "pre-existing and unrelated" without the exclusion test: re-run with only the suspect file ignored, compare the failure lists, and record that output. Note that `just coverage-layers` can segfault under random test ordering — rerun once before treating a crash as a regression.

- [ ] **Step 3: Run the complete local gate**

```bash
just check
```

Expected: lint, format-check, `mypy --strict`, import-check, architecture tests, and the test suite all pass.

- [ ] **Step 4: Check per-layer coverage**

```bash
just coverage-layers
```

Expected: widgets stay at or above 60%. This story adds two small widget factories with three unit tests each, so coverage should rise.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(story-097): resolve full-gate findings"
```

______________________________________________________________________

## Task 8: Close the story out

- [ ] **Step 1: Regenerate and validate the traceability record**

```bash
just trace
just trace-check
```

Expected: zero failures. `just trace` parses each test's `Proves:` docstring line, so both acceptance criteria should now map to their tests.

- [ ] **Step 2: Mark the story done and record the decisions**

In `docs/stories/story-097-accessible-names-shell-and-dialogs.md`, set `status: done` and add a `## Notes` section recording, in plain language:

- The pinned "Dialog close (✕)" row was realized as the existing footer Close button, because the mockups' in-dialog ✕ is drawn by the operating system in the real app and no Qt object exists to name (Decision 1).

- The gate-busy indicator is a static strip, not the animated spinner the registry table names, because no mockup shows one and ADR-0018 removed the reduce-motion preference that would let a user switch it off (Decision 2).

- The readiness dot's tooltip leads with the pinned sentence and keeps the per-provider reachability list beneath it, resolving a direct contradiction between the Main Window spec and the accessibility registry without deleting anything a user can see today. Its pinned-value assertion is a first-line match; the other nine rows are exact (Decision 4).

- The Settings button's tooltip is the pinned "Open the Settings dialog" when enabled and the spec's disabled reason when disabled (Decision 5).

- Nine buttons across the shared dialogs, plus the four quit-confirmation buttons, were given a test handle they previously lacked. This is wider than the two acceptance criteria and was an explicit scope decision, taken so STORY-091's automated handle check does not fail on day one (Decision 7).

- Two controls that were disabled with no explanation — the Rename button and the Retry Selected button — gained the explanatory tooltip the project's UI rule requires.

- `tests/integration/common_dialog_builders.py` was extracted from the screenshot harness so both it and the accessible-name walker mount the same seven dialogs.

- The story's test plan names one test for the second acceptance criterion; it is proven by three instead — the shell rows, the dialog rows, and the readiness dot's first-line tooltip. A single test would have needed an `if` in its body to choose which surface to mount, which `.claude/rules/testing.md` forbids. Update the story's test-plan bullet to name all three.

- [ ] **Step 3: Check whether the parent story can be unblocked**

STORY-089 depends on STORY-097, STORY-098, and STORY-099. Check the other two:

```bash
grep -l 'status:' docs/stories/story-098-*.md docs/stories/story-099-*.md | xargs grep -H '^status:'
```

Flip STORY-089 from `draft` to `ready` **only if both are already `done`**. Otherwise leave it `draft` and name the outstanding dependency in the closing report.

- [ ] **Step 4: Re-run traceability after any status change**

```bash
just trace
just trace-check
```

The record embeds each story's status, so it goes stale the moment one changes.

- [ ] **Step 5: Commit**

```bash
git add docs/stories traceability.yaml
git commit -m "docs(story-097): mark accessible-names shell story done and refresh traceability"
```

- [ ] **Step 6: Write the closing report**

Report what changed, what the full gate said, which decisions were taken and why, and rank the next stories to pick up. The natural next pick is whichever of STORY-098 (New Benchmark, Resume, Progress) or STORY-099 (Result, Settings, Task Editor) is still open — both are unblocked from the start and both gate STORY-089.

______________________________________________________________________

## Verification summary

| What                     | How                                                                                                                                          |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Both acceptance criteria | `uv run pytest tests/integration/test_a11y_names_shell.py -q` → 12 passed                                                                    |
| No shell regression      | `uv run pytest src/ollama_llm_bench/ui/main_window tests/integration/test_compose_build_app.py tests/integration/test_quit_sequence.py -q`   |
| No dialog regression     | `uv run pytest src/ollama_llm_bench/ui/common_dialogs tests/integration/test_screenshot_harness.py -q`                                       |
| Nothing else broken      | `uv run pytest tests/unit tests/integration tests/e2e src -q` (~2 min; longer means hung)                                                    |
| Style authority intact   | `uv run pytest tests/architecture/ -q`                                                                                                       |
| Full local gate          | `just check`                                                                                                                                 |
| Traceability             | `just trace && just trace-check` → zero failures                                                                                             |
| See it for real          | `uv run python -m ollama_llm_bench`, hover Settings / About / the workspace segments / the status-bar dot and confirm each shows its tooltip |
