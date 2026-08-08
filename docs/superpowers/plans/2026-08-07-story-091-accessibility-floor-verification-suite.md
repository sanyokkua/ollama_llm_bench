# STORY-091 — Accessibility-Floor Verification Suite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the five automated, release-blocking accessibility-floor checks the spec's
verification table names but that don't exist yet — an objectName architecture test, an
accessible-name walker, a click-target-size check, a focus-ring-visibility check, and a
no-custom-shortcut grep gate — plus the one small production fix (`ui/theme/`) needed to make
the focus-ring check provable against real behaviour rather than a check with nothing correct
to pass against.

**Architecture:** Two checks (objectName, no-shortcut) are pure AST walkers over `src/` with no
`QApplication`, living in `tests/architecture/`. Three checks (accessible-name walker,
click-target, focus-ring) mount the real, fully-composed application via `compose.build_app`
plus the Settings dialog and the seven shared modal dialogs (all `QDialog | None`-narrowed,
never `.exec()`'d), living in `tests/e2e/` under `QT_QPA_PLATFORM=offscreen`. A single new
shared fixture set in `tests/e2e/conftest.py` mounts every surface once per test and exposes a
generic `interactive_descendants` walker so the three e2e tests don't triplicate it (the
repo's established "restate per tier, don't leak fixtures across tiers" convention still
applies — nothing here imports across `tests/integration/` and `tests/e2e/`).

**Tech Stack:** Python 3.13.3, PySide6 6.8+, pytest + pytest-qt, `ast` (stdlib) for the
architecture-tier walkers, `just test-e2e` / `just arch-test` / `just check`.

## Global Constraints

- Every test function is fully annotated, returns `-> None`, and its docstring's first line is
  `Proves: STORY-091-AC-N` (traceability-and-stories.md).
- `ruff check --fix` then `ruff format`, `mypy --strict`, `import-linter` all pass on every
  touched file — no new findings, including in the file this story edits inside `ui/theme/`.
- No `setStyleSheet()` call is added outside `src/ollama_llm_bench/ui/theme/` — the one
  production change in this story stays inside that module (pyside6-app-development.md).
- No `asyncio`/`anyio`/`qasync` import anywhere in `src/` (project-wide non-negotiable).
- `tests/e2e/` is the only tier that mounts the whole wired application under
  `QT_QPA_PLATFORM=offscreen`; nothing here is added to `tests/integration/`
  (`docs/stories/story-091-...md` Design constraints).
- Every mock is `spec=`'d; a widget is never replaced by a mock (testing.md).
- Traceability: after any story-file or test-docstring change, `just trace` then
  `just trace-check` must pass with zero gaps before the story can move toward `done`.
- Falsification is mandatory, not optional, for all five checks (the story's own Test-plan
  section states this for the three e2e checks; this plan extends the same discipline to the
  two architecture checks — see Task 8): a check that cannot be proven to catch a real
  regression proves nothing (`feedback_negative_control_must_break_not_delete.md`).

______________________________________________________________________

## File structure

| File                                                            | Action | Responsibility                                                                                                              |
| --------------------------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------- |
| `src/ollama_llm_bench/ui/theme/_internal/stylesheet_builder.py` | Modify | Add the `:focus` QSS rule for focus-retaining widget types, using `FocusRingTokens.outer_width` + `border_focus`            |
| `src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py`  | Modify | Prove the new `:focus` rule is emitted with the right selector and colour                                                   |
| `tests/architecture/test_objectnames_present.py`                | Create | AC-1 — every interactive control constructed in `ui/`/`adapters/` sets a non-empty `objectName`                             |
| `tests/architecture/test_no_custom_keyboard_shortcuts.py`       | Create | AC-5 — no `QShortcut`, `.setShortcut(`, or unescaped `&`-mnemonic anywhere in `src/`                                        |
| `tests/e2e/conftest.py`                                         | Modify | Add `interactive_descendants` walker fixture + `mounted_app_surfaces` fixture (window + Settings dialog + 7 shared dialogs) |
| `tests/e2e/test_accessible_name_walker.py`                      | Create | AC-2 — every interactive element in the mounted app has a non-empty accessible name                                         |
| `tests/e2e/test_click_target_size.py`                           | Create | AC-3 — every interactive control has a >=24x24px hit area                                                                   |
| `tests/e2e/test_focus_ring_visibility.py`                       | Create | AC-4 — every focus-retaining control reports `hasFocus()` and renders the `focus.ring` colour after a click                 |

______________________________________________________________________

### Task 1: Wire the `focus.ring` token into a real `:focus` QSS rule

`FocusRingTokens` (`src/ollama_llm_bench/ui/theme/models.py:173-178`) and its values
(`FOCUS_RING_TOKENS = FocusRingTokens(outer_width=1, inner_glow_width=2, inner_glow_opacity=0.40)`, `src/ollama_llm_bench/ui/theme/_internal/scalars.py:19`) are wired
into both `ThemeTokens` containers (`_internal/factory.py:28,44`) but never consumed by
`render_stylesheet` — grep confirms zero `:focus` selectors anywhere in `ui/theme/`. Per
`08_ACCESSIBILITY_FLOOR.md` §5, "the ring is never suppressed... for controls that hold focus
after a click — text inputs, text areas, dropdowns/combos, spinners, lists, tables." This task
renders the token's outer 1px `border.focus` line as a real `:focus` QSS rule (the inner glow
is a visual refinement the AC-4 test does not require — it checks `hasFocus()` plus the
rendered `border_focus` colour, not a pixel-exact two-layer glow).

**Files:**

- Modify: `src/ollama_llm_bench/ui/theme/_internal/stylesheet_builder.py`
- Test: `src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py`

**Interfaces:**

- Consumes: `ThemeTokens.focus_ring.outer_width: int` (`models.py:174-178,211`),
  `ThemeTokens.colors.border_focus: str` (`models.py:92`) — both already present, no model
  change needed.

- Produces: `render_stylesheet(tokens: ThemeTokens) -> str` now additionally emits a QSS block
  selecting `QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QTableView:focus, QListView:focus, QTreeView:focus`. Task 7 (focus-ring e2e test) depends on
  this exact selector list and on `border_focus` being the colour it renders.

- [ ] **Step 1: Write the failing test**

Add to `src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py` (after the existing two
tests, same file, same imports already present):

```python
def test_stylesheet_renders_focus_ring_for_focus_retaining_input_types(
    qapp: QApplication,
) -> None:
    """Proves: STORY-091 Definition of Done (08_ACCESSIBILITY_FLOOR.md §5)

    build_stylesheet() emits a :focus rule for every focus-retaining input type --
    QLineEdit, QTextEdit, QComboBox, QAbstractSpinBox, QTableView, QListView, QTreeView --
    using the focus_ring outer width and the border_focus colour. Momentary buttons
    (QPushButton) are deliberately excluded (DD-52).
    """
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    stylesheet = build_stylesheet(tokens)

    assert "QLineEdit:focus" in stylesheet
    assert "QTextEdit:focus" in stylesheet
    assert "QComboBox:focus" in stylesheet
    assert "QAbstractSpinBox:focus" in stylesheet
    assert "QTableView:focus" in stylesheet
    assert "QListView:focus" in stylesheet
    assert "QTreeView:focus" in stylesheet
    assert f"{tokens.focus_ring.outer_width}px solid {tokens.colors.border_focus}" in stylesheet
    assert "QPushButton:focus" not in stylesheet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py -q`
Expected: FAIL — `assert "QLineEdit:focus" in stylesheet` (the substring is not yet emitted).

- [ ] **Step 3: Write the minimal implementation**

In `src/ollama_llm_bench/ui/theme/_internal/stylesheet_builder.py`, add a new QSS block to the
returned string in `render_stylesheet`, immediately after the existing
`'QPushButton[role="destructive-button"]'` block (i.e. as the new final block before the
closing `)`):

```python
        "\n"
        "QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus,\n"
        "QTableView:focus, QListView:focus, QTreeView:focus {\n"
        f"    border: {tokens.focus_ring.outer_width}px solid {tokens.colors.border_focus};\n"
        "    outline: none;\n"
        "}\n"
    )
```

(Replace the existing trailing `"}\n"\n    )` of the destructive-button block with the sequence
above — the new block's own `"}\n"` becomes the new final line before the closing `)`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py -q`
Expected: PASS, all three tests in the file green.

- [ ] **Step 5: Full-file lint/type check and commit**

Run: `uv run ruff check --fix src/ollama_llm_bench/ui/theme/ && uv run ruff format src/ollama_llm_bench/ui/theme/ && uv run mypy --strict src/ollama_llm_bench/ui/theme/`
Expected: no findings.

```bash
git add src/ollama_llm_bench/ui/theme/_internal/stylesheet_builder.py src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py
git commit -m "feat(story-091): render the focus.ring token as a real :focus QSS rule"
```

______________________________________________________________________

### Task 2: objectName architecture test (AC-1)

No objectName-related architecture test exists yet (`grep -rn "objectName" tests/architecture/`
returns nothing). The technique: two-pass AST analysis over every `.py` file under `ui/` and
`adapters/` (excluding `tests/` subdirectories and `conftest.py`, matching the established
`_iter_python_files` pattern in `tests/architecture/test_ui_theme_style_authority.py:15-25`).
Pass 1 builds the transitive closure of "interactive" class names — Qt's own interactive base
classes (matching the same set already established at runtime by
`tests/integration/test_a11y_names_shell.py:30-39`'s `_INTERACTIVE_TYPES`, translated to their
Qt class names) plus any locally-defined subclass of one, transitively (confirmed live examples
exist: `ProviderDropdownWidget(QComboBox)`, `MultiCheckFilterButtonWidget(QPushButton)`,
`_FilterChipButton(QPushButton)` x3, `_FocusOutLineEdit(QLineEdit)`). Pass 2 walks each
function/method's own lexical scope for constructions of an interactive-named class and
verifies a matching `.setObjectName(...)` call exists in the same scope with a non-empty
argument (matches the codebase's dominant real pattern:
`self.setObjectName("main_window")` / `central.setObjectName("main_window_central")` —
`src/ollama_llm_bench/ui/main_window/_internal/shell.py:71,157`).

**Files:**

- Create: `tests/architecture/test_objectnames_present.py`

**Interfaces:**

- Consumes: nothing from another task — self-contained AST walker.

- Produces: nothing another task depends on; this is a leaf check.

- [ ] **Step 1: Write the test file with self-verifying fixtures first**

Create `tests/architecture/test_objectnames_present.py`:

```python
"""Architecture test for the accessibility floor's objectName requirement (§7.1, §10)."""

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_SCAN_ROOTS = (_SRC_ROOT / "ui", _SRC_ROOT / "adapters")

_QT_INTERACTIVE_BASE_NAMES = frozenset(
    {
        "QPushButton",
        "QToolButton",
        "QCheckBox",
        "QRadioButton",
        "QAbstractButton",
        "QComboBox",
        "QLineEdit",
        "QTextEdit",
        "QPlainTextEdit",
        "QSpinBox",
        "QDoubleSpinBox",
        "QAbstractSpinBox",
        "QTableView",
        "QTableWidget",
        "QListView",
        "QListWidget",
        "QTreeView",
        "QTreeWidget",
        "QAbstractItemView",
    }
)


def _iter_python_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*.py")
            if "tests" not in path.parts and path.name != "conftest.py"
        )
    return sorted(files)


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _collect_class_bases(files: list[Path]) -> dict[str, set[str]]:
    class_bases: dict[str, set[str]] = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = {name for base in node.bases if (name := _base_name(base)) is not None}
                class_bases.setdefault(node.name, set()).update(bases)
    return class_bases


def _interactive_class_names(files: list[Path]) -> frozenset[str]:
    class_bases = _collect_class_bases(files)
    interactive = set(_QT_INTERACTIVE_BASE_NAMES)
    changed = True
    while changed:
        changed = False
        for name, bases in class_bases.items():
            if name not in interactive and bases & interactive:
                interactive.add(name)
                changed = True
    return frozenset(interactive)


def _target_repr(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _target_repr(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _ctor_name(call: ast.Call) -> str | None:
    if isinstance(call.func, (ast.Name, ast.Attribute)):
        return _base_name(call.func) if isinstance(call.func, ast.Attribute) else call.func.id
    return None


class _ScopeCollector(ast.NodeVisitor):
    """Collects (construction, setObjectName) pairs per lexical function scope.

    A push/pop scope stack keyed on each ``FunctionDef`` means a construction in an outer
    method is never matched against a ``setObjectName`` call made inside a nested inner
    function, and vice versa -- each function's own statements are checked against only
    that same function's own ``setObjectName`` calls.
    """

    def __init__(self, interactive_names: frozenset[str]) -> None:
        self._interactive_names = interactive_names
        self.offenders: list[tuple[int, str, str]] = []
        self._scope_stack: list[tuple[dict[str, int], dict[str, ast.expr | None]]] = [({}, {})]

    def _pop_scope(self) -> None:
        constructions, named = self._scope_stack.pop()
        for repr_, lineno in constructions.items():
            if repr_ not in named:
                self.offenders.append((lineno, repr_, "no setObjectName call"))
            elif isinstance(named[repr_], ast.Constant) and named[repr_].value == "":  # type: ignore[union-attr]
                self.offenders.append((lineno, repr_, "empty objectName"))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope_stack.append(({}, {}))
        self.generic_visit(node)
        self._pop_scope()

    def visit_Assign(self, node: ast.Assign) -> None:
        value = node.value
        if isinstance(value, ast.Call) and _ctor_name(value) in self._interactive_names:
            constructions, _ = self._scope_stack[-1]
            for target in node.targets:
                repr_ = _target_repr(target)
                if repr_ is not None:
                    constructions[repr_] = node.lineno
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "setObjectName":
            constructions, named = self._scope_stack[-1]
            obj_repr = _target_repr(node.func.value)
            arg = node.args[0] if node.args else None
            if obj_repr is not None:
                named[obj_repr] = arg
            elif isinstance(node.func.value, ast.Call) and _ctor_name(node.func.value) in self._interactive_names:
                key = f"<chained:{node.lineno}>"
                constructions[key] = node.lineno
                named[key] = arg
        self.generic_visit(node)

    def finalize(self) -> None:
        while self._scope_stack:
            self._pop_scope()


def test_scope_collector_flags_missing_and_empty_objectname_on_synthetic_source() -> None:
    """Proves: STORY-091-AC-1 (self-check)

    _ScopeCollector flags a QPushButton with no setObjectName call and one with an empty
    string, and does not flag one that sets a non-empty objectName -- proving the walker
    catches a real regression before it is trusted against the real source tree.
    """
    source = """
class _View:
    def _build(self):
        good = QPushButton("Save")
        good.setObjectName("save_button")
        missing = QPushButton("Cancel")
        empty = QPushButton("Close")
        empty.setObjectName("")
"""
    tree = ast.parse(source)
    collector = _ScopeCollector(frozenset({"QPushButton"}))
    collector.visit(tree)
    collector.finalize()

    flagged_vars = {repr_ for _, repr_, _ in collector.offenders}
    assert flagged_vars == {"missing", "empty"}


def test_every_interactive_control_sets_a_nonempty_objectname() -> None:
    """Proves: STORY-091-AC-1

    Every interactive control constructed in ui/ or adapters/ -- a Qt built-in interactive
    widget type or a local subclass of one -- calls setObjectName with a non-empty value in
    its own construction scope (08_ACCESSIBILITY_FLOOR.md §7.1, §10).
    """
    files = _iter_python_files(_SCAN_ROOTS)
    interactive_names = _interactive_class_names(files)
    offenders: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collector = _ScopeCollector(interactive_names)
        collector.visit(tree)
        collector.finalize()
        offenders.extend(
            f"{path.relative_to(_SRC_ROOT)}:{lineno} {repr_} -- {reason}"
            for lineno, repr_, reason in collector.offenders
        )
    assert offenders == [], "controls with no author-assigned objectName:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run the self-check test first, confirm it passes on the synthetic fixture**

Run: `uv run pytest tests/architecture/test_objectnames_present.py::test_scope_collector_flags_missing_and_empty_objectname_on_synthetic_source -v`
Expected: PASS. This proves the walker's own logic is sound (finds real offenders, doesn't
flag the correctly-named control) before it is trusted against 46+ real source files.

- [ ] **Step 3: Run the real test against the source tree**

Run: `uv run pytest tests/architecture/test_objectnames_present.py::test_every_interactive_control_sets_a_nonempty_objectname -v`
Expected: PASS, given `setObjectName` coverage is already near-complete per STORY-097/098/099
(167 call sites across 44 files) — but treat any reported offender as a **real, live gap** to
fix in the offending `ui/`/`adapters/` file (not a reason to weaken the check), since those
three stories' own tests only proved the 17 *pinned* rows, not exhaustive coverage.

- [ ] **Step 4: Lint/type check and commit**

Run: `uv run ruff check --fix tests/architecture/test_objectnames_present.py && uv run ruff format tests/architecture/test_objectnames_present.py && uv run mypy --strict tests/architecture/test_objectnames_present.py`
Expected: no findings. (The `# type: ignore[union-attr]` on the `_pop_scope` narrowing is
justified: `named[repr_]` is looked up after confirming `repr_ in named` two lines above via
the `elif`, but `mypy` cannot narrow a dict-lookup across the `elif` boundary — keep the
specific code, remove it only if `mypy` proves it unnecessary.)

```bash
git add tests/architecture/test_objectnames_present.py
git commit -m "test(story-091): add the objectName architecture check (AC-1)"
```

______________________________________________________________________

### Task 3: no-custom-keyboard-shortcut architecture test (AC-5)

Zero existing `QShortcut`/`setShortcut`/mnemonic scanning anywhere (`grep -rn "QShortcut\|setShortcut" src/` returns nothing) — this is greenfield. Scope: the whole
`src/ollama_llm_bench/` tree (matching the spec's "registered anywhere in the application"
wording, §4/§10), excluding `tests/` subdirectories.

**Files:**

- Create: `tests/architecture/test_no_custom_keyboard_shortcuts.py`

**Interfaces:**

- Consumes: nothing from another task.

- Produces: nothing another task depends on.

- [ ] **Step 1: Write the test file**

Create `tests/architecture/test_no_custom_keyboard_shortcuts.py`:

```python
"""Architecture test for the accessibility floor's mouse-only requirement (§4, §10)."""

import ast
from pathlib import Path
import re

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_MNEMONIC_RE = re.compile(r"(?<!&)&(?!&)")
_TEXT_SETTING_ATTRS = frozenset({"setText", "setWindowTitle", "setTitle"})
_TEXT_CONSTRUCTOR_NAMES = frozenset({"QAction", "QMenu"})


def _iter_python_files() -> list[Path]:
    return sorted(
        path
        for path in _SRC_ROOT.rglob("*.py")
        if "tests" not in path.parts and path.name != "conftest.py"
    )


def _offenders_in_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    relative = path.relative_to(_SRC_ROOT)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "QShortcut":
            offenders.append(f"{relative}:{node.lineno} QShortcut(...) constructed")
        if isinstance(func, ast.Attribute) and func.attr in {"setShortcut", "setShortcuts"}:
            offenders.append(f"{relative}:{node.lineno} .{func.attr}(...) called")
        if isinstance(func, ast.Attribute) and func.attr in _TEXT_SETTING_ATTRS:
            offenders.extend(
                f"{relative}:{node.lineno} .{func.attr}({arg.value!r}) has an unescaped '&' mnemonic"
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _MNEMONIC_RE.search(arg.value)
            )
        if isinstance(func, ast.Name) and func.id in _TEXT_CONSTRUCTOR_NAMES:
            offenders.extend(
                f"{relative}:{node.lineno} {func.id}({arg.value!r}) has an unescaped '&' mnemonic"
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _MNEMONIC_RE.search(arg.value)
            )
    return offenders


def test_mnemonic_regex_flags_unescaped_ampersand_and_spares_escaped_one() -> None:
    """Proves: STORY-091-AC-5 (self-check)

    The mnemonic regex matches a single '&' (a Qt accelerator marker) and does not match
    an escaped '&&' (Qt's literal-ampersand form) -- proving the check catches a real
    mnemonic before it is trusted against the real source tree.
    """
    assert _MNEMONIC_RE.search("&Save") is not None
    assert _MNEMONIC_RE.search("Save && Close") is None


def test_no_custom_shortcut_accelerator_or_mnemonic_is_registered() -> None:
    """Proves: STORY-091-AC-5

    No module registers a QShortcut, a QAction/button shortcut, or an unescaped '&'
    mnemonic in a button/action/window/group-box label. The toolkit's built-in modal
    Enter/Esc defaults register nothing and so never appear here (D-R-07).
    """
    offenders = [offender for path in _iter_python_files() for offender in _offenders_in_file(path)]
    assert offenders == [], "custom keyboard affordances found:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run the self-check test, confirm it passes**

Run: `uv run pytest tests/architecture/test_no_custom_keyboard_shortcuts.py::test_mnemonic_regex_flags_unescaped_ampersand_and_spares_escaped_one -v`
Expected: PASS.

- [ ] **Step 3: Run the real test against the source tree**

Run: `uv run pytest tests/architecture/test_no_custom_keyboard_shortcuts.py::test_no_custom_shortcut_accelerator_or_mnemonic_is_registered -v`
Expected: PASS immediately (research confirmed zero existing violations). If it fails, the
finding is real — file it, do not narrow the regex/attribute set to make it pass.

- [ ] **Step 4: Lint/type check and commit**

Run: `uv run ruff check --fix tests/architecture/test_no_custom_keyboard_shortcuts.py && uv run ruff format tests/architecture/test_no_custom_keyboard_shortcuts.py && uv run mypy --strict tests/architecture/test_no_custom_keyboard_shortcuts.py`

```bash
git add tests/architecture/test_no_custom_keyboard_shortcuts.py
git commit -m "test(story-091): add the no-custom-keyboard-shortcut architecture check (AC-5)"
```

______________________________________________________________________

### Task 4: Shared e2e fixtures — `interactive_descendants` walker + `mounted_app_surfaces`

Tasks 5, 6, and 7 (AC-2, AC-3, AC-4) all need the same two things: a generic widget-tree walker
(the pattern already established three times over in `tests/integration/test_a11y_names_*.py`
— restated here for `tests/e2e/`, per that tier's own "restate, don't share across tiers"
convention already documented in `tests/e2e/conftest.py`'s module docstring) and every mounted
surface of the real application: `handle.window` (built via the existing `build_smoke_app`
fixture at `tests/e2e/conftest.py:178-203`, which already eagerly contains every workspace tab
per `compose.py`'s eager construction), the Settings dialog, and the seven shared modal
dialogs. Building these fixtures once in `conftest.py` avoids each of the three new test files
independently building the whole app — directly mitigates the Qt-object-churn risk
`docs/stories/story-117-reduce-qt-object-churn-in-accessibility-tests.md` (draft, not blocking,
but real) already flagged for repeatedly-mounted-app accessibility tests.

**Files:**

- Modify: `tests/e2e/conftest.py`

**Interfaces:**

- Consumes: `build_smoke_app: Callable[[], AppHandle]` fixture (already defined,
  `tests/e2e/conftest.py:178-203`); `AppHandle.window` (`compose.py`).

- Produces (new fixtures, consumed by Tasks 5-7):

  - `interactive_descendants: Callable[[QWidget], list[QWidget]]`
  - `mounted_app_surfaces: list[QWidget]` — `[handle.window, settings_dialog, *common_dialogs.values()]`

- [ ] **Step 1: Add the interactive-descendants walker, restated from the tests/integration/ precedent**

Add to `tests/e2e/conftest.py` (new imports: `QAbstractButton`, `QAbstractItemView`,
`QAbstractSpinBox`, `QComboBox`, `QLineEdit`, `QTextEdit` from `PySide6.QtWidgets`; `cast` from
`typing`; `Iterable` from `collections.abc` if not already imported):

```python
_INTERACTIVE_TYPES: tuple[type[QWidget], ...] = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)
_COMPOSITE_TYPES: tuple[type[QWidget], ...] = (QComboBox, QAbstractItemView, QAbstractSpinBox)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    Restated from tests/integration/test_a11y_names_shell.py:41-56 (the established,
    deliberate per-tier restatement convention -- no shared tests/support/ module exists).
    """
    parent = cast("QObject | None", widget.parent())
    while parent is not None:
        if isinstance(parent, _COMPOSITE_TYPES):
            return True
        parent = cast("QObject | None", parent.parent())
    return False


@pytest.fixture
def interactive_descendants() -> Callable[[QWidget], list[QWidget]]:
    def _walk(root: QWidget) -> list[QWidget]:
        descendants = cast("Iterable[QWidget]", root.findChildren(QWidget))
        found = [
            w for w in descendants if isinstance(w, _INTERACTIVE_TYPES) and not _has_composite_ancestor(w)
        ]
        if isinstance(root, _INTERACTIVE_TYPES):
            found.append(root)
        return found

    return _walk
```

- [ ] **Step 2: Add the standalone Settings-dialog builder, restated from the screenshot-harness precedent**

Copy `tests/integration/test_screenshot_harness.py:207-227` (`_build_settings_dialog`)
verbatim into `tests/e2e/conftest.py`, unchanged. Add its required imports if not already
present in `tests/e2e/conftest.py`: `from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers`, `from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService`, `from ollama_llm_bench.ui.settings_dialog import SettingsDialogCollaborators, make_settings_dialog`, `from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway` (plus
`make_clipboard`/`make_file_system_actions`/`make_qt_event_bus_deliverer`, already imported in
`tests/e2e/conftest.py` if `test_icon_only_registry_conformance.py`'s imports were shared, or
add them from `ollama_llm_bench.adapters.clipboard`, `ollama_llm_bench.adapters.file_system_actions`,
`ollama_llm_bench.adapters.qt_event_bus` respectively).

- [ ] **Step 3: Add the seven shared common dialogs, restated from tests/integration/conftest.py**

Copy `tests/integration/conftest.py` lines 98-394 verbatim into `tests/e2e/conftest.py`: the
`_PROVIDER_ID`/`_MODEL_NAME`/`_RUN_ID`/`_TIMESTAMP`/`_DIALOG_SIZE` constants, all eight
`_Stub*` classes (`_StubRenameRunGateway`, `_StubRunSummaryGateway`,
`_StubResumeSummaryGateway`, `_StubRetrySelectionGateway`, `_StubRunAnalysisDispatcher`,
`_StubProviderListSource`, `_StubModelFetcher`, `_StubSubscription`,
`_StubGenerateAnalysisEventBus`), the five `_canned_*` functions
(`_canned_provider`/`_canned_readiness`/`_canned_request`/`_canned_run`/`_canned_results`), and
`_build_common_dialogs` itself. Copy the matching import block from lines 35-96 of that same
file (trim to only the names Task 4's copied code actually uses — `ruff` will flag the rest as
unused). **Do not** copy the `common_dialogs` pytest fixture at lines 397-408 as-is; Step 4
below folds its call into `mounted_app_surfaces` directly instead of exposing a second,
separate fixture.

- [ ] **Step 4: Add the `mounted_app_surfaces` fixture**

```python
@pytest.fixture
def mounted_app_surfaces(
    qtbot: QtBot, build_smoke_app: Callable[[], AppHandle]
) -> list[QWidget]:
    """Every top-level surface the accessibility-floor checks (AC-2/3/4) must walk.

    The main window (built via build_smoke_app -- eagerly contains every workspace tab per
    compose.py's construction order), the Settings dialog, and the seven shared modal
    dialogs, all shown but never exec()'d.
    """
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=5000)

    settings_dialog = _build_settings_dialog(qtbot=qtbot)
    common_dialogs = _build_common_dialogs(qtbot=qtbot)

    return [handle.window, settings_dialog, *common_dialogs.values()]
```

- [ ] **Step 5: Lint/type check the whole conftest and commit**

Run: `uv run ruff check --fix tests/e2e/conftest.py && uv run ruff format tests/e2e/conftest.py && uv run mypy --strict tests/e2e/conftest.py`
Expected: no findings — pay particular attention to unused-import findings from the trimmed
copy in Step 3.

```bash
git add tests/e2e/conftest.py
git commit -m "test(story-091): add shared mounted_app_surfaces and interactive_descendants e2e fixtures"
```

______________________________________________________________________

### Task 5: Accessible-name walker e2e test (AC-2)

**Files:**

- Create: `tests/e2e/test_accessible_name_walker.py`

**Interfaces:**

- Consumes: `mounted_app_surfaces: list[QWidget]`, `interactive_descendants: Callable[[QWidget], list[QWidget]]` (Task 4).

- Produces: nothing another task depends on.

- [ ] **Step 1: Write the test**

Create `tests/e2e/test_accessible_name_walker.py`:

```python
"""E2E accessibility-floor check: every interactive element has a non-empty accessible name.

Proves the accessibility floor's §7/§10 verification row (08_ACCESSIBILITY_FLOOR.md).
"""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget


def test_every_interactive_element_has_a_nonempty_accessible_name(
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-2

    Every interactive element across the mounted application, the Settings dialog, and the
    seven shared modal dialogs -- especially every icon-only button -- reports a non-empty
    accessible name.
    """
    unnamed = [
        f"{type(surface).__name__}({surface.objectName() or '<no objectName>'}) > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'})"
        for surface in mounted_app_surfaces
        for control in interactive_descendants(surface)
        if not control.accessibleName()
    ]
    assert unnamed == [], "controls with no accessible name:\n" + "\n".join(unnamed)
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e/test_accessible_name_walker.py -v`
Expected: PASS given STORY-089/097/098/099's coverage (167 `setAccessibleName` call sites
across 44 files) — but any reported gap is real (this walker is exhaustive across the whole
mounted app; the three prior stories' own tests only proved specific surfaces/rows).

- [ ] **Step 3: Lint/type check and commit**

Run: `uv run ruff check --fix tests/e2e/test_accessible_name_walker.py && uv run ruff format tests/e2e/test_accessible_name_walker.py && uv run mypy --strict tests/e2e/test_accessible_name_walker.py`

```bash
git add tests/e2e/test_accessible_name_walker.py
git commit -m "test(story-091): add the accessible-name walker e2e check (AC-2)"
```

______________________________________________________________________

### Task 6: Click-target size e2e test (AC-3)

**Files:**

- Create: `tests/e2e/test_click_target_size.py`

**Interfaces:**

- Consumes: `mounted_app_surfaces: list[QWidget]`, `interactive_descendants: Callable[[QWidget], list[QWidget]]` (Task 4).

- Produces: nothing another task depends on.

- [ ] **Step 1: Write the test**

Create `tests/e2e/test_click_target_size.py`:

```python
"""E2E accessibility-floor check: every clickable control has a >=24x24px hit area.

Proves the accessibility floor's §6/§10 verification row (08_ACCESSIBILITY_FLOOR.md).
"""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget

_MIN_HIT_AREA_PX = 24


def test_every_clickable_control_meets_24px_minimum_hit_area(
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-3

    Every interactive control across the mounted application, the Settings dialog, and the
    seven shared modal dialogs offers a hit area of at least 24x24 logical pixels at the
    application's default scale.
    """
    undersized = [
        f"{type(surface).__name__}({surface.objectName() or '<no objectName>'}) > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'}) "
        f"{control.width()}x{control.height()}"
        for surface in mounted_app_surfaces
        for control in interactive_descendants(surface)
        if control.width() < _MIN_HIT_AREA_PX or control.height() < _MIN_HIT_AREA_PX
    ]
    assert undersized == [], "controls below the 24x24px minimum hit area:\n" + "\n".join(undersized)
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e/test_click_target_size.py -v`
Expected: PASS or a real, reportable gap. **Watch for false positives from genuinely
zero-geometry hidden controls** (a widget never laid out because its parent tab/page was never
made current) — if any offender's reported size is `0x0`, that is very likely a layout-timing
artifact, not a real undersized control; if seen, add an `if control.isVisible()` (or
`isVisibleTo(surface)`) filter to the comprehension and re-run before treating it as a finding.

- [ ] **Step 3: Lint/type check and commit**

Run: `uv run ruff check --fix tests/e2e/test_click_target_size.py && uv run ruff format tests/e2e/test_click_target_size.py && uv run mypy --strict tests/e2e/test_click_target_size.py`

```bash
git add tests/e2e/test_click_target_size.py
git commit -m "test(story-091): add the click-target-size e2e check (AC-3)"
```

______________________________________________________________________

### Task 7: Focus-ring visibility e2e test (AC-4)

Depends on Task 1's `:focus` QSS rule existing — without it this test fails against real
production behaviour, which is the correct state until Task 1 lands.

**Files:**

- Create: `tests/e2e/test_focus_ring_visibility.py`

**Interfaces:**

- Consumes: `mounted_app_surfaces: list[QWidget]`, `interactive_descendants: Callable[[QWidget], list[QWidget]]` (Task 4); `tokens.colors.border_focus` values from `make_dark_theme_tokens`/`make_light_theme_tokens` (`ollama_llm_bench.ui.theme`, already-public API) — the Dark value `"#0f766e"` and Light value `"#0a7b6e"` (`src/ollama_llm_bench/ui/theme/_internal/colors.py:14,47`); the `:focus` rule from Task 1.

- Produces: nothing another task depends on.

- [ ] **Step 1: Write the test**

Create `tests/e2e/test_focus_ring_visibility.py`:

```python
"""E2E accessibility-floor check: every focus-retaining input renders the focus ring.

Proves the accessibility floor's §5/§10 verification row (08_ACCESSIBILITY_FLOOR.md), scoped
to focus-retaining controls only -- momentary buttons are exempt per DD-52.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QAbstractItemView, QAbstractSpinBox, QComboBox, QLineEdit, QTextEdit, QWidget
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens, make_light_theme_tokens

_FOCUS_RETAINING_TYPES: tuple[type[QWidget], ...] = (
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)


def _image_contains_color(image: QImage, color: QColor, *, tolerance: int = 8) -> bool:
    target = (color.red(), color.green(), color.blue())
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            channels = (pixel.red(), pixel.green(), pixel.blue())
            if all(abs(a - b) <= tolerance for a, b in zip(channels, target, strict=True)):
                return True
    return False


def test_focus_retaining_input_renders_focus_ring_on_click(
    qtbot: QtBot,
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-4

    Every focus-retaining input control (text inputs, combos, spinners, lists, tables --
    not momentary buttons, DD-52) reports hasFocus() and renders the focus.ring border
    colour after a click. Checked against both themes' border_focus value since the live
    app's active theme depends on the host's OS colour-scheme detection.
    """
    dark_focus = QColor(make_dark_theme_tokens(platform_kind=PlatformKind.LINUX).colors.border_focus)
    light_focus = QColor(make_light_theme_tokens(platform_kind=PlatformKind.LINUX).colors.border_focus)

    checked = 0
    for surface in mounted_app_surfaces:
        for control in interactive_descendants(surface):
            if not isinstance(control, _FOCUS_RETAINING_TYPES) or not control.isVisible():
                continue
            qtbot.mouseClick(control, Qt.MouseButton.LeftButton)
            assert control.hasFocus(), f"{control.objectName()} did not report hasFocus() after a click"

            image = control.grab().toImage()
            assert _image_contains_color(image, dark_focus) or _image_contains_color(image, light_focus), (
                f"{control.objectName()} does not render the focus.ring border colour after a click"
            )
            checked += 1

    assert checked > 0, "no focus-retaining control was found to test"
```

- [ ] **Step 2: Run it and confirm it fails without Task 1, then passes with it**

Before Task 1 lands, this test fails at the `_image_contains_color` assertion for every
focus-retaining control (no `:focus` rule exists yet) — that is the expected, correct red
state proving Task 1 is load-bearing, not decorative. After Task 1:

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e/test_focus_ring_visibility.py -v`
Expected: PASS.

**Watch the runtime.** This clicks every focus-retaining control across every mounted surface
— if the suite runs materially over the e2e tier's 60-second-per-test budget (testing.md), or
if repeated app mounting/focus churn triggers the native GC-related SIGSEGV flake tracked by
`docs/stories/story-117-...md` (draft, not blocking), report it rather than silently narrowing
which controls are checked (`feedback_no_concurrent_full_suite_runs.md`,
`project_native_crash_flake_narrowed.md` precedent for how that class of flake was diagnosed).

- [ ] **Step 3: Lint/type check and commit**

Run: `uv run ruff check --fix tests/e2e/test_focus_ring_visibility.py && uv run ruff format tests/e2e/test_focus_ring_visibility.py && uv run mypy --strict tests/e2e/test_focus_ring_visibility.py`

```bash
git add tests/e2e/test_focus_ring_visibility.py
git commit -m "test(story-091): add the focus-ring-visibility e2e check (AC-4)"
```

______________________________________________________________________

### Task 8: Falsification pass — prove all five checks fail for the right reason

The story's own Test-plan section requires this for the three e2e checks; this plan extends
the same discipline to both architecture checks, since a check that has never been seen to fail
proves nothing (`feedback_negative_control_must_break_not_delete.md`). Tasks 2 and 3 already
include this as a permanent, committed self-check test (`test_scope_collector_flags_...`,
`test_mnemonic_regex_flags_...`) rather than a throwaway manual step, since the underlying
production source is otherwise already fully compliant and there is nothing to temporarily
break and revert. For the three e2e checks (no synthetic-fixture equivalent — they walk the
real mounted app), falsify by hand, confirm red, then revert — never delete the assertion to
"prove" it.

**Files:** none created; this task temporarily edits and reverts real widget code to observe a
red run, then permanently deletes those edits.

**Interfaces:** none — verification only.

- [ ] **Step 1: Falsify AC-2 (accessible-name walker)**

Temporarily blank one control's accessible name — e.g. in
`src/ollama_llm_bench/ui/main_window/_internal/menu_bar.py`, find any `setAccessibleName(` call
and change its argument to `""`.

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e/test_accessible_name_walker.py -v`
Expected: FAIL, naming that exact control in the assertion message.

Revert the edit (`git checkout -- src/ollama_llm_bench/ui/main_window/_internal/menu_bar.py`).

- [ ] **Step 2: Falsify AC-3 (click-target size)**

Temporarily shrink one control below 24px — e.g. find any `setFixedSize(`/`setMinimumSize(`
call on an interactive control reachable from `mounted_app_surfaces` and reduce it to `(10, 10)`.

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e/test_click_target_size.py -v`
Expected: FAIL, naming that control's undersized dimensions.

Revert the edit.

- [ ] **Step 3: Falsify AC-4 (focus-ring visibility)**

Temporarily comment out the `:focus` QSS block added in Task 1
(`src/ollama_llm_bench/ui/theme/_internal/stylesheet_builder.py`).

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e/test_focus_ring_visibility.py -v`
Expected: FAIL — no control renders the border colour after a click.

Revert the edit; re-run to confirm green again.

- [ ] **Step 4: Confirm both architecture-tier self-checks are already committed and green**

Run: `uv run pytest tests/architecture/test_objectnames_present.py tests/architecture/test_no_custom_keyboard_shortcuts.py -v`
Expected: 4 tests PASS (two self-checks, two real checks) — the self-checks already satisfy
this task's intent for AC-1/AC-5 permanently, not just for this one verification pass.

- [ ] **Step 5: Commit the falsification pass as a no-op if nothing was left uncommitted**

No files should be modified after this task (every falsifying edit was reverted). Confirm with
`git status --short` before moving to Task 9; if it shows changes, they were not reverted —
revert them now.

______________________________________________________________________

### Task 9: Full gate, traceability, and story closeout

**Files:**

- Modify: `docs/stories/story-091-accessibility-floor-verification-suite.md` (Definition of
  done checkboxes; `status: ready` → `in-progress` at the start of implementation is the
  convention — leave the final `in-progress` → `done` flip to whoever confirms the gate is
  green, per `traceability-and-stories.md`'s lifecycle).
- Modify: `traceability.yaml` (regenerated, never hand-edited).

**Interfaces:** none — this task only runs commands and updates tracking files.

- [ ] **Step 1: Run the full gate**

Run: `just check`
Expected: green — lint, format-check, `mypy --strict`, import-check, arch-test, then the full
`pytest tests/unit tests/integration tests/e2e src` run. Budget ~2 minutes normally; if it runs
materially longer, treat it as a hang per AGENTS.md's "What will bite you" — kill and diagnose,
don't wait it out.

- [ ] **Step 2: Regenerate and validate traceability**

Run: `just trace && just trace-check`
Expected: `just trace` regenerates `traceability.yaml` with all five STORY-091 ACs now pointing
at real tests; `just trace-check` passes with zero gaps (no orphan clause, no orphan test, no
unproven AC on a `done` story).

- [ ] **Step 3: Check STORY-093's remaining dependencies**

Read `docs/stories/story-093-*.md`'s `depends_on:` front-matter. STORY-091 is one entry; per
this story's own "Unblocks" section, flip STORY-093 `draft` → `ready` **only if every other
entry in its `depends_on` is also `status: done`** — otherwise leave it `draft` and name the
still-outstanding dependency in the closing report.

- [ ] **Step 4: Update STORY-091's own Definition of Done checkboxes and commit**

Check off every completed item in `docs/stories/story-091-accessibility-floor-verification-suite.md`'s
Definition of done list (all five ACs proven, both tiers wired into their `just` recipes,
lint/type/import-linter clean, traceability zero-gap, module inventory unchanged, STORY-093
handled, next candidates named).

```bash
git add docs/stories/story-091-accessibility-floor-verification-suite.md traceability.yaml
git commit -m "docs(story-091): close out DoD checklist and regenerate traceability"
```

- [ ] **Step 5: Propose next stories in the closing report**

Per the story's own "What to do on completion" section: with STORY-091 done, the accessibility
thread is closed. Name the remaining finalization work as the next candidates — the
packaging/release chain (STORY-094 → STORY-095 / STORY-096) and then STORY-093 once its other
dependencies clear — ranked, in the closing report.

______________________________________________________________________

## Self-Review

**Spec coverage:**

- §7.1 objectName → Task 2 (AC-1). ✓
- §7 accessible names → Task 5 (AC-2). ✓
- §6 click-target size → Task 6 (AC-3). ✓
- §5 focus indication → Task 1 (production fix) + Task 7 (AC-4). ✓
- §4 mouse-only / no custom shortcut → Task 3 (AC-5). ✓
- §10 verification-method table's tier assignment (architecture vs. e2e) → matched exactly:
  AC-1/AC-5 in `tests/architecture/`, AC-2/AC-3/AC-4 in `tests/e2e/`. ✓
- §8 reduced motion / high contrast → explicitly out of scope per ADR-0018; no task added. ✓
- Falsification requirement (story Test-plan section) → Task 8, extended to all five checks. ✓
- "Unblocks"/STORY-093 flip, traceability regeneration, next-story proposal → Task 9. ✓

**Placeholder scan:** no `TODO`/`TBD`/"add appropriate handling" anywhere; every code step
contains complete, runnable code; the two large-boilerplate copies (Task 4 Steps 2-3) are exact
file:line copy instructions, not vague restatement — the alternative (retyping ~320 lines of
already-existing, already-tested code) would add transcription risk with no informational
value over citing the precise source range.

**Type/signature consistency:** `interactive_descendants: Callable[[QWidget], list[QWidget]]`
and `mounted_app_surfaces: list[QWidget]` (Task 4) are used with identical names and types in
Tasks 5, 6, and 7. `render_stylesheet(tokens: ThemeTokens) -> str` (Task 1) is the same
signature Task 7's test indirectly depends on via the QSS string it produces. `FOCUS_RING_TOKENS`/`border_focus` field names match across Task 1 and Task 7.
