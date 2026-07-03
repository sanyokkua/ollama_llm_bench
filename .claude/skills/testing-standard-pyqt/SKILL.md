---
name: testing-standard-pyqt
description: Use when writing any test.
allowed-tools: Read, Write, Bash
---

# Testing Standard (PySide6 / pytest-qt)

Source of truth: `docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md`.

Tests prove behaviour; architecture tests prove structure. The backend is Qt-free by construction, so the
large majority of behaviour is tested with no `QApplication` and no display. The UI layer is tested with
`pytest-qt` against real widgets — a widget is never replaced by a mock, because a mock silently diverges
from the real Qt API.

## The test pyramid

| Tier | Share of the suite | Scope |
|---|---|---|
| Unit | 70-80% | One module or one function in isolation |
| Integration | 15-25% | Several modules wired together, real local resources |
| End-to-end | 5-10% | The full application launched and smoke-tested |

Architecture tests are counted separately — a structural gate, not a tier of the behaviour pyramid.

## Layout: hybrid colocated + top-level

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

A colocated `src/ollama_llm_bench/<feature>/tests/` directory may only test files within its own module; a
cross-module behaviour test belongs in `tests/integration/`. An architecture test checks this rule itself.

## Naming and shape

Every test is fully annotated, returns `-> None`, follows Arrange-Act-Assert, and asserts exactly one
logical concept. No `if` and no `for` inside a test body — a table of cases is `@pytest.mark.parametrize`,
never a loop over assertions.

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

## pytest-qt basics

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

- `qtbot.addWidget(widget)` ties the widget's lifetime to the test — call it immediately after construction.
- Drive interaction primarily with `qtbot.mouseClick(button, Qt.LeftButton)` (the product is mouse-driven).
  `qtbot.keyClicks` is used **only** to type into a focused text input; `qtbot.keyClick` only for
  `Enter`/`Esc` on a dialog. Never assert custom keyboard navigation or focus-traversal — the product
  defines none.
- Wait for asynchronous effects with `qtbot.waitSignal` and `qtbot.waitUntil`:

```python
def test_readiness_probe_emits_health_changed(qtbot, mocker) -> None:
    bus = make_real_event_bus()
    service = make_readiness_service(bus=bus)

    with qtbot.waitSignal(bus.health_changed, timeout=2000) as blocker:
        service.trigger_probe()

    assert blocker.args[0].overall_status == ReadinessStatus.READY
```

- `qtbot` is function-scoped; it cannot be promoted to a wider scope.
- A custom `QAbstractItemModel` subclass is validated with `QAbstractItemModelTester`, which raises on any
  model-contract violation:

```python
def test_results_table_model_obeys_contract(qtbot) -> None:
    model = ResultsTableModel(rows=make_sample_rows())
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    # Any contract violation raises during construction or subsequent access.
    assert model.rowCount() == len(make_sample_rows())
```

The view layer is tested by feeding it a frozen `ViewModel` and asserting rendered state; the controller
layer is tested by driving store changes and asserting the view receives the expected `ViewModel`; the pure
`view_model_select` functions are tested directly with no Qt involvement at all.

## The shared contract-test suite per Protocol

Every swap-point `Protocol` that has both a real implementation and a `testing.py` fake (each per-aggregate
persistence Store, `LLMClient`, `EventBus`, `TaskRunner`, `InferenceActivityStore`, `ReadinessService`, the
evaluator ports) carries **one shared contract-test suite**, written once, parametrized over
`(real_impl, fake_impl)` so the **same assertions run twice**:

```python
# tests/contract/test_runs_store_contract.py
@pytest.fixture(params=["real", "fake"])
def runs_store(request, tmp_path) -> RunsStore:
    if request.param == "real":
        return SqliteRunsStore(connection=make_tmp_connection(tmp_path))
    return FakeRunsStore()  # the module's testing.py fake


def test_create_run_assigns_incrementing_run_id(runs_store: RunsStore) -> None:
    # Arrange / Act
    first = runs_store.create(make_run_config())
    second = runs_store.create(make_run_config())
    # Assert
    assert second.run_id > first.run_id
```

Both legs must pass in the pull-request gate. This proves the fake is a faithful stand-in — a test that
passes against the fake also holds against production code. **The `LLMClient` real leg runs against the
provider wire stub (below), never a live model.** An architecture test flags any `testing.py` fake whose
Protocol has no contract suite parametrized over both implementations.

## The provider wire stub (transport-level test double)

Provider adapters are the only modules that touch the network. They are tested at the **transport level**:
the real adapter and the real SDK make genuine HTTP calls to a local `pytest-httpserver` stub, not to a
live model — no interception or monkeypatching of SDK internals, the full adapter → SDK → HTTP client →
socket path runs for real.

```python
# tests/integration/provider_stub/test_openai_compatible_adapter.py
def test_adapter_translates_401_to_auth_error(httpserver) -> None:
    httpserver.expect_request("/v1/chat/completions").respond_with_json(
        {"error": {"message": "Invalid API key"}}, status=401,
    )
    adapter = OpenAICompatibleClient(base_url=httpserver.url_for("/v1"), api_key_env_var="DUMMY")

    with pytest.raises(ProviderAuthError):
        adapter.chat(make_chat_request())
```

Per provider dialect the integration module covers, at minimum: HTTP 401, 404 (unknown model), 429, and 500
with realistic bodies; a context-length-exceeded error body; a malformed/truncated stream chunk; a
mid-stream connection close; a stream with no usage data; and a non-streaming rejection of a streaming
request. Each case asserts the adapter's observable contract — the taxonomy error raised, or the
`ChatResponse`/`ChatChunk` values produced (`streamed`, `ttft_ms`, usage fields). The stub returns
programmed bytes with no model in the loop, so assertions are exact — no tolerance bands, no golden-text
drift. The stub lives under `tests/integration/provider_stub/` as shared fixture helpers; it is a test
fixture, not a shipped module.

## Mocking discipline

| Dependency | Substitute |
|---|---|
| `LLMClient` (provider network call) | `mocker.Mock(spec=LLMClient)` or the provider's `testing.py` fake |
| Each per-aggregate persistence Store | The matching `testing.py` fake, or `mocker.Mock(spec=...)` against the specific Protocol |
| `EventBus` | `mocker.Mock(spec=EventBus)` |
| File input/output | `tmp_path` |
| The system clock | The injected `Clock` Protocol — the single mechanism for backend time-dependent logic; `freezegun` only when a direct `datetime.now()`/`time.time()` call is unavoidable |

Every mock is constructed with `spec=`. Patch at the point of use (the consumer module), never the symbol's
source module. A `msgspec.Struct` DTO, a pure function, or a stdlib type is never mocked — construct or call
it directly.

## Coverage targets and how to check them

Branch coverage minimums are **enforced per layer**, not merely as one global gate:

| Layer | Branch coverage minimum | Enforcement |
|---|---|---|
| Backend — services, domain, errors, settings, persistence | 90% or higher | Enforced |
| View-models and controllers | 85% or higher | Enforced |
| Widgets — rendering code | 60% or higher | Enforced |

Check with `just coverage-layers`, which runs `uv run coverage report --include='<layer-glob>' --fail-under=<layer-min>`
per layer and fails the gate on the first layer below its minimum — `coverage.py` has no native per-path
`fail_under`, so this scripted loop is the mechanism. A drop in the backend layer fails the gate even when
the global number stays above the whole-project floor of 80%. The 60% widget floor is deliberately lower
than the backend floor: the accessibility-floor assertions and programmatic Qt construction cover behaviour
that branch coverage of rendering code does not capture.

Per-test time budgets: unit under 1 second (Hypothesis/`RuleBasedStateMachine` suites are `slow`-marked and
exempt), integration under 30 seconds, end-to-end under 60 seconds. The full pull-request suite completes
in under four minutes on CI.

## Cross-references

- `docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md` — full standard, including architecture-test layers and Hypothesis profiles.
- The `acceptance-criteria-authoring` skill — how an acceptance criterion maps to the Arrange-Act-Assert / parametrize / Hypothesis shape used here.
- The `edge-case-coverage` skill — how an `EC-` id is assigned a tier and proving module.
