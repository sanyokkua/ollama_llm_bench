---
paths:
  - "tests/**/*.py"
  - "src/**/tests/**/*.py"
---

# Testing Standard

Source of truth: `docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md`. A
behaviour test asserts what the application does; an architecture test asserts the codebase
obeys the module-boundary and coding rules. Both run in the pull-request gate. Every behaviour
the specification describes must be reachable by a test that fails when that behaviour
regresses.

## The test pyramid

| Tier | Share of the suite | Scope |
|---|---|---|
| Unit | 70-80% | One module or one function in isolation |
| Integration | 15-25% | Several modules wired together, real local resources |
| End-to-end | 5-10% | The full application launched and smoke-tested |

Architecture tests are counted **separately** — a structural gate, not a tier of the behaviour
pyramid.

## Test layout — hybrid: colocated + top-level

```
src/ollama_llm_bench/<feature>/tests/   # Unit tests scoped to THIS module only
    __init__.py
    conftest.py
    test_*.py

tests/
├── conftest.py            # Root fixtures: Qt parity rig, Hypothesis profiles, filesystem isolation
├── architecture/           # import-linter wrappers + AST walkers
├── unit/                   # Cross-module unit tests
├── integration/            # Multi-module behaviour tests against real local resources
├── e2e/                    # Full-application smoke tests
└── typing_negative/        # Files that MUST FAIL mypy --strict
```

A colocated `src/ollama_llm_bench/<feature>/tests/` directory may only test files within its
own module; a cross-module behaviour test belongs in `tests/integration/` — itself checked by
an architecture test.

```toml
[tool.pytest.ini_options]
testpaths = ["src", "tests"]
pythonpath = ["src"]
addopts = ["--import-mode=importlib", "--strict-markers", "--strict-config", "-ra"]
markers = [
    "unit: Fast isolated unit tests",
    "integration: Tests requiring real local resources",
    "slow: Tests exceeding the standard time budget",
    "property: Hypothesis-driven property tests",
    "allow_qt_warnings: Test may emit Qt warnings without failing",
]
```

## Test structure and naming

```python
def test_parse_judge_response_with_valid_json_returns_grade() -> None: ...
def test_create_run_with_no_models_raises_value_error() -> None: ...
```

Every test function is fully annotated and returns `-> None`. Each test follows
Arrange-Act-Assert and asserts exactly one logical concept. A test contains **no `if` and no
`for`** — a table of cases is `@pytest.mark.parametrize`, never a loop over assertions.

```python
def test_calculate_elapsed_returns_formatted_string() -> None:
    # Arrange
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 5, 30, tzinfo=UTC)
    # Act
    result = calculate_elapsed(start=start, end=end)
    # Assert
    assert result == "5m 30s"
```

## Fixtures

- A fixture needing cleanup uses `yield` and tears down after the yield.
- Smallest scope that works; `scope="function"` is default, `scope="session"` only for
  genuinely expensive resources.
- A test needing varying instances uses a factory fixture.
- `autouse=True` only for environment-level concerns (the Qt parity rig, filesystem isolation)
  — never to inject test-specific state.

Filesystem isolation is an autouse fixture redirecting the application-data directory into
`tmp_path` so no test touches the real user profile:

```python
@pytest.fixture(autouse=True)
def _isolate_filesystem(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
```

## Mocking discipline

- **Every mock is constructed with `spec=`.** A bare `mocker.Mock()` accepts any attribute,
  including a typo; `mocker.Mock(spec=LLMClient)` rejects anything outside the real interface.
- **Patch at the point of use** — the consumer module that imports the symbol — never the
  symbol's source module.
- A `msgspec.Struct` DTO, a pure function, and a standard-library type are **never** mocked —
  construct or call them directly.

| Dependency | Substitute |
|---|---|
| `LLMClient` (provider network call) | `mocker.Mock(spec=LLMClient)` or the provider's `testing.py` fake |
| Each per-aggregate persistence Store (`RunsStore`, `TasksStore`, `ResultsStore`, `ProvidersStore`, `ModelCapabilitiesStore`, `AppSettingsStore`) | The matching `testing.py` fake, or `mocker.Mock(spec=...)` against the specific Protocol |
| `EventBus` | `mocker.Mock(spec=EventBus)` |
| File input/output | The `tmp_path` fixture |
| The system clock (backend time-dependent logic) | The injected **`Clock` Protocol** — the single mechanism for all backend time reads; `freezegun` restricted to code that unavoidably calls `datetime.now()`/`time.time()` directly with no injectable clock |

## Shared contract-test suite per Protocol

Every swap-point `Protocol` with both a real implementation and a `testing.py` fake (each
per-aggregate Store, `LLMClient`, `EventBus`, `TaskRunner`, `InferenceActivityStore`,
`ReadinessService`, the evaluator ports) carries a **single shared contract-test suite** run
against **both** implementations, parametrized over `(real_impl, fake_impl)`, proving the fake
is a faithful stand-in. **The `LLMClient` real leg runs against the provider wire stub (§7a
below)**, never a live model — CI is fully offline. An architecture test flags any `testing.py`
fake whose Protocol has no contract suite parametrized over both implementations.

## Testing the Qt-free backend headlessly

The backend imports no PySide6, so the entire pipeline, evaluators, provider adapters,
persistence, settings, and stores are tested with no `QApplication` and no display.

- Provider adapters (real adapter + real SDK) are tested against the **provider wire stub**
  below — never a live model.
- The persistence layer is tested against a SQLite database created in `tmp_path`; each test
  gets a fresh file, closed in fixture teardown. An in-memory database is used only for a
  trivial test not exercising file behaviour.
- The pipelines are tested with a faked `LLMClient`, real `tmp_path`-backed per-aggregate
  Stores sharing one connection, and `mocker.Mock(spec=EventBus)`.
- Backend logic is synchronous: tests call it directly with an **inline `TaskRunner`** (no
  event loop, no async fixtures); cancellation paths set the `CancellationToken` and assert
  `TaskCancelledError` at the next checkpoint.
- Time-dependent backend logic is made deterministic with an injected test `Clock`.

## The provider wire stub (transport-level test double)

`pytest-httpserver` starts an HTTP server on `127.0.0.1` with an ephemeral port inside the
test. The adapter under test is constructed with that server's URL as the provider base URL
(the same override every supported SDK exposes) — no interception or monkeypatching of SDK
internals; the full adapter -> SDK -> HTTP client -> socket path runs for real.

- **Canned wire payloads**: streaming SSE chunk sequences (incl. terminal sentinel),
  non-streaming bodies, usage payloads, model-list responses, pinned per provider dialect.
- **The error matrix is the point**: per provider dialect, cover at minimum HTTP 401, 404, 429,
  500 with realistic bodies; a context-length-exceeded body; a malformed/truncated stream
  chunk; a mid-stream connection close; a stream with no usage data; a non-streaming rejection
  of a streaming request. Each case asserts the taxonomy error raised or the
  `ChatResponse`/`ChatChunk` values produced (`streamed`, `ttft_ms`, usage fields).
- **Determinism**: programmed bytes, no model in the loop — exact assertions, no tolerance
  bands. TTFT assertions verify presence/ordering only, never wall-clock values.
- Lives under `tests/integration/provider_stub/` as shared fixture helpers — a test fixture,
  not a shipped module.

## Testing PySide6 widgets

Widget tests use `pytest-qt`. A widget is **never** replaced by a mock — a mock silently
diverges from the real Qt API.

```python
def test_start_button_disabled_when_no_providers(qtbot, mocker) -> None:
    settings = mocker.Mock(spec=SettingsStore)
    settings.get.return_value = ""
    bus = mocker.Mock(spec=EventBus)

    widget = make_new_benchmark_widget(settings=settings, bus=bus)
    qtbot.addWidget(widget)

    start_button = widget.findChild(QPushButton, "start_button")
    assert not start_button.isEnabled()
```

- `qtbot.addWidget(widget)` ties the widget's lifetime to the test.
- `qtbot.mouseClick` is the primary interaction simulator (the product is mouse-driven).
  `qtbot.keyClicks` only to type into a focused text input; `qtbot.keyClick` only for
  `Enter`/`Esc` on a dialog (Qt defaults). Tests must not assert custom keyboard navigation,
  accelerators, or focus-traversal behaviour — the product defines none.
- Asynchronous expectations use `qtbot.waitSignal` and `qtbot.waitUntil`.
- `qtbot` is function-scoped; it cannot be promoted to a wider scope.
- A custom `QAbstractItemModel` subclass is validated with `QAbstractItemModelTester`.

The view layer is tested by feeding it a frozen `ViewModel` and asserting rendered state; the
controller is tested by driving store changes and asserting the expected `ViewModel`; the pure
`view_model_select` functions are tested directly with no Qt involvement.

## Architecture tests — three layers

**Layer one — import contracts.** `import-linter` runs the boundary contracts (Qt-free
backend, private internals, provider independence, sole composition root). `pytest-archon`
adds finer rules:

```python
from pytest_archon import archrule


def test_ui_does_not_import_persistence() -> None:
    (archrule("ui-has-no-sqlite")
        .match("ollama_llm_bench.ui.*")
        .should_not_import("ollama_llm_bench.backend.persistence._internal.*")
        .should_not_import("sqlite3")
        .check("ollama_llm_bench"))
```

**Layer two — AST walkers.** Symbol-level rules import analysis cannot see: no bare `except:`
outside the allowlist; no module-level mutable globals; every public `api.py` function carries
at least one `icontract` decorator; every `msgspec.Struct` is `frozen=True, kw_only=True,
gc=False`; `setStyleSheet` is not called outside `ui/theme`; every `ui/*` feature module
follows the MVC-family four-file layout; no `view.py` imports an adapter gateway, a reactive
store, or any backend symbol (the passive-View rule).

**Layer three — negative typing tests.** `tests/typing_negative/` contains files that **must
fail** `mypy --strict`. CI inverts the result:

```yaml
- name: Negative typing tests must fail mypy
  run: |
    set +e
    uv run mypy --strict tests/typing_negative/
    if [ $? -eq 0 ]; then
      echo "ERROR: typing_negative tests unexpectedly passed mypy"
      exit 1
    fi
    echo "OK: typing_negative tests failed mypy as required"
```

## Property-based testing

Hypothesis covers invariants example-based tests cannot exhaust — parsers, serializers,
scoring logic, reactive stores. Three profiles registered in `tests/conftest.py`, selected by
`HYPOTHESIS_PROFILE`: `dev` (small budget, fast local), `release`, `ci` (large budget,
derandomized). Stateful sequences use a Hypothesis `RuleBasedStateMachine` with `@invariant`
methods. `icontract-hypothesis` infers property tests from `icontract` preconditions on
concrete implementations only, never Protocol types.

## Coverage targets and time budgets

Branch coverage minimums, **enforced per layer**, not merely as a single global gate:

| Layer | Branch coverage minimum | Enforcement |
|---|---|---|
| Backend — services, domain, errors, settings, persistence | >= 90% | Enforced |
| View-models and controllers | >= 85% | Enforced |
| Widgets — rendering code | >= 60% | Enforced |

```toml
[tool.coverage.run]
source_pkgs = ["ollama_llm_bench"]
branch = true
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:", "raise NotImplementedError"]
```

`fail_under = 80` is the **whole-project floor only**. The per-layer minimums are enforced
**additionally** via `just coverage-layers`, which runs, per layer,
`uv run coverage report --include='<layer-glob>' --fail-under=<layer-min>` and fails on the
first layer below its minimum (`coverage.py` has no native per-path `fail_under`). A drop in
the backend layer fails the gate even when the global number stays above 80%. The 60% widget
floor is deliberately lower — programmatic Qt construction and the accessibility-floor
assertions cover behaviour branch coverage of rendering code does not capture.

| Tier | Budget per test |
|---|---|
| Unit | < 1 second (Hypothesis/`RuleBasedStateMachine` suites are exempt — marked `slow`) |
| Integration | < 30 seconds |
| End-to-end | < 60 seconds |

The full pull-request suite completes in under four minutes on the CI runner. A test
legitimately exceeding its tier budget is `@pytest.mark.slow` and excluded from the
pull-request gate (run locally on demand). There is no nightly CI workflow (DD-36).

## The CI test environment

| Knob | Local | CI |
|---|---|---|
| Python | `3.13.3` from `.python-version` | same, pinned by version file |
| Dependencies | `uv sync` against `uv.lock` | `uv sync --frozen` |
| Qt platform | native | offscreen Qt platform plugin |
| Qt warnings | the parity rig in `conftest.py` | same rig, PySide warning logging enabled |
| Hypothesis profile | small `dev` profile | large-budget CI profile |
| Test order | randomized by `pytest-randomly` | same, seed recorded |

The Qt parity rig is an autouse fixture in the root `conftest.py` installing a Qt message
handler that fails any test emitting a Qt/PySide warning, unless marked
`@pytest.mark.allow_qt_warnings`.

## Anti-patterns

| Anti-pattern | Why it is wrong | Correct approach |
|---|---|---|
| `Mock()` with no `spec=` | Accepts any attribute, masks typos | `mocker.Mock(spec=Class)` |
| Patching the symbol's source module | Misses `from module import name` usage | Patch the consumer module |
| A `for` loop over assertions | One failure hides the rest | `@pytest.mark.parametrize` |
| An `if` inside a test body | Two tests pretending to be one | Split into two tests |
| `setUp` / `tearDown` methods | `unittest` holdover | `@pytest.fixture` |
| `qtbot` promoted past function scope | Scope mismatch error | A function-scoped factory fixture |
| Mocking a `msgspec.Struct` DTO | Pointless; it is frozen and structural | Construct it directly |
| A widget replaced by a mock | Diverges silently from the real Qt API | A real widget under `qtbot.addWidget` |
| An in-memory SQLite database for a persistence test | Hides file and WAL behaviour | A `tmp_path` database file |
| State assigned inside an `autouse` fixture | Hidden coupling between tests | An explicit fixture named in the test signature |
| A behaviour test placed in a module's colocated `tests/` | Crosses the module boundary | `tests/integration/` |
