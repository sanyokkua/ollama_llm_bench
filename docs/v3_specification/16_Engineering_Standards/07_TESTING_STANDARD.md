# Testing Standard

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`, `16_Engineering_Standards/02_TOOLCHAIN.md`, `16_Engineering_Standards/03_CODING_STANDARDS.md`, `08_Cross_Cutting/08-A_architecture_principles.md`, `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`

This document fixes the test strategy for Ollama LLM Bench: the test pyramid and coverage targets, the colocated-plus-top-level test layout, how the Qt-free backend is tested headlessly, how PySide6 widgets are tested with `pytest-qt`, how the module boundaries are tested with `import-linter` and `pytest-archon`, how invariants are tested with Hypothesis, the fixture and mocking discipline, and the continuous-integration test environment. Every behaviour the specification describes must be reachable by a test that fails when that behaviour regresses.

---

## Table of Contents

1. Purpose and scope
2. The test pyramid
3. Test layout
4. Test structure and naming
5. Fixtures
6. Mocking discipline
7. Testing the Qt-free backend headlessly
7a. The provider wire stub (transport-level test double)
8. Testing PySide6 widgets
9. Architecture tests
10. Property-based testing
11. Coverage targets and time budgets
12. The CI test environment
13. Anti-patterns

---

## 1. Purpose and scope

Tests prove behaviour; the architecture-test layer proves structure. The two are kept distinct: a behaviour test asserts what the application does, an architecture test asserts that the codebase obeys the module-boundary and coding rules. Both run in the pull-request gate.

The backend is Qt-free by construction (see `01_PROJECT_STRUCTURE.md`), so the large majority of behaviour can be tested with no `QApplication` and no display. The UI layer is tested with `pytest-qt` against real widgets.

## 2. The test pyramid

| Tier | Share of the suite | Scope |
|---|---|---|
| Unit | 70–80% | One module or one function in isolation |
| Integration | 15–25% | Several modules wired together, real local resources |
| End-to-end | 5–10% | The full application launched and smoke-tested |

Architecture tests are counted separately — they are a structural gate, not a tier of the behaviour pyramid.

## 3. Test layout

The layout is hybrid. Unit tests are colocated inside the module they test; cross-cutting tests live at the top level.

```
src/ollama_llm_bench/<feature>/tests/   # Unit tests scoped to THIS module only
    __init__.py
    conftest.py
    test_*.py

tests/
├── conftest.py            # Root fixtures: Qt parity rig, Hypothesis profiles, filesystem isolation
├── architecture/          # import-linter wrappers + AST walkers
├── unit/                  # Cross-module unit tests
├── integration/           # Multi-module behaviour tests against real local resources
├── e2e/                   # Full-application smoke tests
└── typing_negative/       # Files that MUST FAIL mypy --strict
```

A colocated `src/ollama_llm_bench/<feature>/tests/` directory may only test files within its own module; a cross-module behaviour test belongs in `tests/integration/`. This rule is itself checked by an architecture test.

`pytest` discovers both roots:

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

## 4. Test structure and naming

Test names state the subject, the condition, and the expected outcome:

```python
def test_parse_judge_response_with_valid_json_returns_grade() -> None: ...
def test_create_run_with_no_models_raises_value_error() -> None: ...
```

Every test function is fully annotated and returns `-> None`. Each test follows the Arrange-Act-Assert shape and asserts exactly one logical concept. A test contains no `if` and no `for` — a table of cases is expressed with `@pytest.mark.parametrize`, never a loop over assertions.

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

## 5. Fixtures

- A fixture that needs cleanup uses `yield` and performs teardown after the yield.
- A fixture takes the smallest scope that works; `scope="function"` is the default and `scope="session"` is reserved for genuinely expensive resources.
- A test that needs varying instances uses a factory fixture.
- `autouse=True` is used only for environment-level concerns — the Qt parity rig and filesystem isolation — never to inject test-specific state.

Filesystem isolation is an autouse fixture that redirects the application-data directory into `tmp_path` so no test touches the real user profile:

```python
@pytest.fixture(autouse=True)
def _isolate_filesystem(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
```

## 6. Mocking discipline

- **Every mock is constructed with `spec=`.** A bare `mocker.Mock()` accepts any attribute, including a typo, and silently rots; `mocker.Mock(spec=LLMClient)` rejects anything outside the real interface.
- **Patching is done at the point of use** — the consumer module that imports the symbol — not at the symbol's source module.
- A `msgspec.Struct` DTO, a pure function, and a standard-library type are never mocked. They are constructed or called directly.

What is mocked in a unit test, and how:

| Dependency | Substitute |
|---|---|
| `LLMClient` (provider network call) | `mocker.Mock(spec=LLMClient)` or the provider's `testing.py` fake |
| Each per-aggregate persistence Store (`RunsStore`, `TasksStore`, `ResultsStore`, `ProvidersStore`, `ModelCapabilitiesStore`, `AppSettingsStore`) | The matching sub-feature package's `testing.py` fake, or `mocker.Mock(spec=...)` against the specific Protocol |
| `EventBus` | `mocker.Mock(spec=EventBus)` |
| File input/output | The `tmp_path` fixture |
| The system clock (backend time-dependent logic) | the injected **`Clock` Protocol** — the single mechanism for all backend logic that reads time (watchdogs, adaptive timeout, cooldowns); `freezegun` is restricted to code that unavoidably calls `datetime.now()`/`time.time()` directly and cannot take an injected clock (SPEC-106) |

## 6a. Shared contract-test suite per Protocol

Every swap-point `Protocol` that has both a real implementation and a `testing.py` fake (each per-aggregate persistence Store, `LLMClient`, `EventBus`, `TaskRunner`, `InferenceActivityStore`, `ReadinessService`, and the evaluator ports) carries a **single shared contract-test suite** that is run against **both** the real implementation and the fake. This guarantees the fake is a faithful stand-in, so a swap-point is genuinely interchangeable and a test that passes against the fake also holds against production code.

- The suite is written once as a parametrized abstract test module (for example `tests/contract/test_<protocol>_contract.py`) that takes the implementation under test as a fixture parameter.
- It is parametrized over `(real_impl, fake_impl)` so the **same** assertions run twice — once per implementation. Both legs must pass in the pull-request gate.
- **The `LLMClient` real leg runs against the provider wire stub (§7a)**, not a live model: the real adapter and the real provider SDK are pointed at a `pytest-httpserver` instance on `127.0.0.1` via the base-URL override, serving canned, deterministic responses. No contract-suite leg ever contacts a live LLM server; CI is fully offline.
- The contract suite asserts the behavioural contract from `08_Cross_Cutting/08-E_interfaces_contracts.md` (return shapes, error/no-raise rules, idempotency, the no-op-when-idle preconditions on `BenchmarkFlowApi.pause`/`stop`, the single-acquire semantics of `InferenceActivityStore.try_acquire`, etc.) — not implementation internals.
- Adding a new `Protocol` with a `testing.py` fake requires adding its contract suite; an architecture test (`tests/architecture/`) flags any `testing.py` fake whose Protocol has no contract suite parametrized over both implementations.

## 7. Testing the Qt-free backend headlessly

The backend layer imports no PySide6, so the entire benchmarking pipeline, evaluation pipeline, provider adapters, persistence layer, settings, and stores are tested with no `QApplication` and no display.

- Provider adapters — the real adapter code plus the real provider SDK — are tested against the **provider wire stub** (§7a), a local `pytest-httpserver` instance serving canned responses, so the streaming parse, error translation, TTFT capture, and usage capture paths are exercised deterministically offline. Each provider module's `testing.py` fake (which implements the `LLMClient` Protocol without any network or SDK) is what *other* modules use when they need an `LLMClient` collaborator; the fake never stands in for the adapter in the adapter's own tests.
- The persistence layer is tested against a SQLite database created in `tmp_path`; each test gets a fresh database file and the connection is closed in fixture teardown. An in-memory database is used only for a trivial test that does not exercise file behaviour.
- The benchmark and evaluation pipelines are tested with a faked `LLMClient`, a `tmp_path`-backed set of real per-aggregate persistence Stores (sharing one connection so cross-store transactions are genuine), and a `mocker.Mock(spec=EventBus)`; the result rows and emitted events are asserted directly.
- Backend logic is synchronous, so tests call it directly with an inline `TaskRunner` (no event loop, no async fixtures); cancellation paths are tested by setting the `CancellationToken` and asserting the work raises `TaskCancelledError` at the next checkpoint.
- Backend time-dependent logic is made deterministic by injecting a test `Clock` (the single mechanism, SPEC-106); `freezegun` is used only where a direct `datetime.now()`/`time.time()` call is unavoidable and no clock can be injected.

Because no `QApplication` is created in any backend test, these tests are fast and run identically on a headless CI runner.

## 7a. The provider wire stub (transport-level test double)

The provider adapters are the only modules that touch the network, and the provider SDKs are the dependency class most likely to break under the latest-versions policy (risk R-008). They are therefore tested at the **transport level**: the real adapter and the real SDK make genuine HTTP calls to a stub server, not to a live model.

- **Tooling.** `pytest-httpserver` (dev dependency) starts an HTTP server on `127.0.0.1` with an ephemeral port inside the test. The adapter under test is constructed with that server's URL as the provider base URL — the same base-URL override every supported SDK (OpenAI, Anthropic, Gemini) exposes. No interception or monkeypatching of SDK internals occurs; the full adapter → SDK → HTTP client → socket path runs for real.
- **Fixtures are canned wire payloads.** Each test registers the exact bytes the stub returns: streaming SSE chunk sequences (including the terminal sentinel), non-streaming completion bodies, usage payloads, and model-list responses. The payload shapes are pinned per provider dialect and updated from real captured traffic whenever a provider SDK version is deliberately bumped.
- **The error matrix is the point.** Per provider dialect, the integration module covers at minimum: HTTP 401, 404 (unknown model), 429, and 500 responses with realistic bodies; a context-length-exceeded error body (the `ProviderContextLengthError` translation path); a malformed or truncated stream chunk; a mid-stream connection close; a stream that sends no usage data; and a non-streaming rejection of a streaming request (the DD-51 fallback path). Each case asserts the adapter's observable contract: the taxonomy error raised or the `ChatResponse`/`ChatChunk` values produced, including `streamed`, `ttft_ms`, and usage fields.
- **Determinism.** The stub returns programmed bytes with no model in the loop, so assertions are exact (no tolerance bands, no golden-text drift). TTFT-related assertions verify presence and ordering (first chunk observed before trailing response), never wall-clock values.
- **Scope.** The wire stub backs the `LLMClient` contract-suite real leg (§6a) and the per-provider integration modules. It is a test fixture, not a shipped module; it lives under `tests/integration/provider_stub/` as shared fixture helpers.

## 8. Testing PySide6 widgets

Widget tests use `pytest-qt`. They exercise real widgets — a widget is never replaced by a mock, because a mock silently diverges from the real Qt API.

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

Rules:

- `qtbot.addWidget(widget)` ties the widget's lifetime to the test.
- User interaction is simulated primarily with `qtbot.mouseClick` (the product is mouse-driven). `qtbot.keyClicks` is used **only** to type into a focused text input (a supported path), and `qtbot.keyClick` only for `Enter`/`Esc` on a dialog (Qt defaults, DD-52). Tests **must not** assert custom keyboard navigation, accelerators, or focus-traversal behaviour — the product defines none, so such a test would validate behaviour that does not exist.
- Asynchronous expectations use `qtbot.waitSignal` and `qtbot.waitUntil`.
- `qtbot` is function-scoped; it cannot be promoted to a wider scope.
- A custom `QAbstractItemModel` subclass is validated with `QAbstractItemModelTester`, which raises on any model-contract violation.

The view layer is tested by feeding a view a frozen `ViewModel` and asserting the rendered state; the controller layer is tested by driving store changes and asserting the view receives the expected `ViewModel`. The pure `view_model_select` functions are tested directly with no Qt involvement.

## 9. Architecture tests

Architecture tests live in `tests/architecture/` and run in the pull-request gate. They have three layers.

**Layer one — import contracts.** `import-linter` runs the boundary contracts from `01_PROJECT_STRUCTURE.md` (Qt-free backend, private internals, provider independence, sole composition root). `pytest-archon` adds finer import rules:

```python
from pytest_archon import archrule


def test_ui_does_not_import_persistence() -> None:
    (archrule("ui-has-no-sqlite")
        .match("ollama_llm_bench.ui.*")
        .should_not_import("ollama_llm_bench.backend.persistence._internal.*")
        .should_not_import("sqlite3")
        .check("ollama_llm_bench"))
```

**Layer two — AST walkers.** Symbol-level rules that import analysis cannot see are checked by walking the abstract syntax tree of every source file:

- `test_no_bare_except` — no bare `except:` or `except Exception:` outside the explicit allowlist.
- `test_no_module_level_mutable_globals` — no mutable container assigned at module top level.
- `test_every_public_api_has_icontract` — every public function in every `api.py` carries at least one `icontract` decorator.
- `test_dtos_are_frozen_kw_only` — every `msgspec.Struct` is declared `frozen=True, kw_only=True, gc=False`.
- `test_no_setstylesheet_outside_theme` — `setStyleSheet` is not called outside the `ui/theme` module.
- `test_widget_module_shape` — every `ui/*` feature module contains the MVC-family four-file layout (`models.py` public; `view.py`, `controller.py`, `view_model_select.py` under `_internal/`; `08-A` §5, `01_PROJECT_STRUCTURE.md` §6).
- `test_view_is_passive` — no `view.py` imports an adapter gateway, a reactive store, or any backend symbol; views depend only on UI primitives, their controller, and `models.py` (the passive-View rule of `08-A` §5).

**Layer three — negative typing tests.** `tests/typing_negative/` contains files that **must fail** `mypy --strict`. They prove that the type system rejects a misuse — for example writing to a read-only settings property, or reading a key outside its scope. CI runs `mypy` against this directory and inverts the result: if `mypy` passes, the gate fails.

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

## 10. Property-based testing

Hypothesis covers invariants that example-based tests cannot exhaust — parsers, serializers, the evaluation scoring logic, and the reactive stores.

Three Hypothesis profiles are registered in `tests/conftest.py` and selected by the `HYPOTHESIS_PROFILE` environment variable: `dev` (a small example budget for fast local runs), `release`, and `ci` (a large example budget, derandomized for reproducibility). CI uses the large-budget profile.

Stateful sequences — for example a store accumulating and removing filter chips — are tested with a Hypothesis `RuleBasedStateMachine` whose `@invariant` methods assert the store's invariants hold after every operation.

`icontract-hypothesis` infers property tests directly from the `icontract` preconditions on a concrete function. It is applied only to concrete implementations, never to Protocol types.

## 11. Coverage targets and time budgets

Branch coverage minimums, **enforced per layer** on the Linux runner — not merely as a single global gate. The global `fail_under` is a floor; each layer is additionally gated at its own minimum so a well-covered UI cannot mask an under-covered backend:

| Layer | Branch coverage minimum | Enforcement |
|---|---|---|
| Backend — services, domain, errors, settings, persistence | 90% or higher | **Enforced** (gate fails below the minimum) |
| View-models and controllers | 85% or higher | **Enforced** (gate fails below the minimum) |
| Widgets — rendering code | 60% or higher | **Enforced** (gate fails below the minimum) |

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

The single `fail_under = 80` above is the **whole-project floor only**. The per-layer minimums in the table are enforced **in addition** to it via the concrete justfile recipe **`just coverage-layers`** (SPEC-068), which runs, per layer, `uv run coverage report --include='<layer-glob>' --fail-under=<layer-min>` — `backend/*` at its minimum, the view-model/controller packages at theirs, and the widget packages at 60% — and fails the gate on the first layer below its minimum. (`coverage.py` has no native per-path `fail_under`, so this scripted loop is the mechanism; it is wired as a PR-gate step.) A drop in the backend layer therefore fails the gate even when the global number stays above 80%. The **60% widget floor** is deliberately lower than the backend floor: programmatic Qt construction and the accessibility-floor assertions (`12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md`) cover behaviour that branch coverage of rendering code does not capture, so 60% is the normative minimum for rendering code, not an advisory target.

Per-test time budgets:

| Tier | Budget per test |
|---|---|
| Unit | under 1 second (property-based / Hypothesis tests and `RuleBasedStateMachine` suites are exempt — they are marked `slow` and run under the larger CI Hypothesis profile; the 1 s budget is a convention enforced via the `slow` marker, not a hard per-test timeout) |
| Integration | under 30 seconds |
| End-to-end | under 60 seconds |

The full pull-request suite completes in under four minutes on the CI runner. A test that legitimately exceeds its tier budget is marked `@pytest.mark.slow`; slow tests are excluded from the pull-request gate entirely and can be run locally on demand. There is no nightly CI workflow (DD-36).

## 12. The CI test environment

Local and CI test runs are deliberately kept in parity:

| Knob | Local | CI |
|---|---|---|
| Python | `3.13.3`, from `.python-version` | the same, pinned by version file |
| Dependencies | `uv sync` against `uv.lock` | `uv sync --frozen` |
| Qt platform | the native platform | the offscreen Qt platform plugin |
| Qt warnings | the same parity rig in `conftest.py` | the same rig, with PySide warning logging enabled |
| Hypothesis profile | the small `dev` profile | the large-budget CI profile |
| Test order | randomized by `pytest-randomly` | the same, with the seed recorded |

The Qt parity rig is an autouse fixture in the root `conftest.py` that installs a Qt message handler and fails any test emitting a Qt or PySide warning, unless the test is explicitly marked `@pytest.mark.allow_qt_warnings`. This surfaces missing-`@Slot` registrations and other Qt misuse as test failures rather than silent degradation.

Slow tests are run locally on demand by the maintainer (or, optionally, as additional steps in the pull-request gate). The `pip-audit` dependency-vulnerability scan may also be run locally on demand, but it is **enforced** as a gating step in the release-tag workflow before any artifact is built (`16_Engineering_Standards/08_CICD_AND_PACKAGING.md` §4, MISS-35). There is no scheduled / nightly CI workflow (DD-36).

## 13. Anti-patterns

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
