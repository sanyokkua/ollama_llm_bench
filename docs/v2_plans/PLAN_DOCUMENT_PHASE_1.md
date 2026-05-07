# Phase 1 — Provider Abstraction Layer: Implementation Plan

**Generated**: 2026-04-16
**Source**: `docs/v2/v2-implementation-plan.md` sections 1.1, 1.2, 1.3, 1.4, 1.5
**Scope**: Build the runtime client infrastructure — new Protocol interfaces, OpenAI-compatible + cloud provider clients, embedding service, and ProviderRegistry — that replaces the single `OllamaApi` with a multi-provider system the execution engine (Phase 2) will consume.

---

## Phase 0 Validation

Phase 0 is **complete**. Verified:
- `src/ollama_llm_bench/backend/core/models.py` — all V2 dataclasses and StrEnums present (BenchmarkTask, BenchmarkRun, BenchmarkResult with 57 fields, PromptVariant, AppSetting, ProviderConfig, EmbeddingConfig, ProvidersConfig, all RunMode/TaskType/ProviderType enums)
- `src/ollama_llm_bench/backend/core/sql_constants.py` — V2 5-table schema + migration DDL complete
- `src/ollama_llm_bench/backend/core/interfaces.py` — existing ABCs + `ProviderConfigLoaderApi(Protocol)` present
- `src/ollama_llm_bench/backend/services/provider_config_loader.py` — YAML loader with `${ENV_VAR}` resolution complete
- `src/ollama_llm_bench/backend/services/schema_migration_runner.py` — V1→V2 migration runner complete
- `src/ollama_llm_bench/providers.yaml` — exists with 7 providers (3 local, 4 cloud) + embedding config

**Known gap found during validation**: `qt_benchmark_execution_task.py` references `response.time_taken_ms` and `response.tokens_generated` from `InferenceResponse`, but `BenchmarkResult` already uses V2 field names (`total_time_ms`, `completion_tokens`). The mapping code is out of sync with models.py. Task 2 resolves this.

---

## Prerequisites

Before starting Phase 1:
- Phase 0 complete (verified above)
- Python 3.13+ and UV installed
- Ollama running locally for integration verification
- No `tests/` directory exists — Task 1 creates it

---

## Architecture Decisions

These are non-negotiable constraints for every task in this phase:

1. **Drop the `ollama` Python SDK** — use `openai` SDK via Ollama's `/v1/` endpoint. The `ollama` SDK returns provider-internal metrics (`eval_count`, `eval_duration`); the `openai` SDK measures wall-clock time. Both produce different numbers for identical runs, making comparison meaningless.

2. **Both sync AND streaming per provider** — streaming captures `ttft_ms` (time-to-first-token). Sync is simpler for judge calls. Neither replaces the other.

3. **Single `OpenAICompatibleProvider`** handles Ollama, LM Studio, llama.cpp, OpenAI cloud, Azure — differentiated only by `base_url` + `api_key` from `providers.yaml`.

4. **Standardized metrics everywhere**: `total_time_ms` (wall-clock), `ttft_ms` (first token), `prompt_tokens`, `completion_tokens`, `tokens_per_second`. No provider-specific internal fields.

5. **Architecture invariants**: `core/` = pure Python only; `services/` = no Qt; threading in `qt_classes/` only; UI updates via EventBus only; constructor DI (keyword-only args); absolute imports only.

6. **New interfaces use `Protocol`** (structural typing), not `ABC`. Existing ABCs (`LLMApi`, `DataApi`, etc.) are kept as-is for backward compatibility until Phase 2 replaces the execution engine.

7. **`LLMApi(ABC)` is NOT removed in Phase 1** — `OllamaApi` still implements it and `BenchmarkFlowApi` still accepts `llm_api: LLMApi`. Full replacement happens in Phase 2 when the execution engine is updated.

---

## Task 1: Add SDK Dependencies and Test Infrastructure

**Files to create**:
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/unit/__init__.py`
- `tests/unit/conftest.py`
- `tests/unit/core/__init__.py`
- `tests/unit/services/__init__.py`
- `tests/unit/services/providers/__init__.py`
- `tests/integration/__init__.py`
- `tests/integration/conftest.py`
- `src/ollama_llm_bench/backend/services/providers/__init__.py`

**Files to modify**:
- `pyproject.toml` — add `openai`, `anthropic`, `google-genai` dependencies

**Depends on**: None

### Context

The project has zero tests and three new SDK dependencies that must be added before any provider implementation can be built or tested. This task creates the structural scaffolding — dependency declarations and pytest directory layout — that all subsequent tasks depend on.

### Requirements

1. Run `uv add openai` — adds `openai` SDK (latest compatible version) to `[project.dependencies]` in `pyproject.toml` and updates `uv.lock`.
2. Run `uv add anthropic` — adds `anthropic` SDK similarly.
3. Run `uv add google-genai` — adds `google-genai` SDK (Google's unified AI SDK) similarly.
4. The `tests/` directory structure exists as shown in "Files to create" above.
5. `tests/conftest.py` is an empty file (scaffolding only — shared fixtures added as needed by later tasks).
6. `tests/unit/conftest.py` and `tests/integration/conftest.py` are empty files; their presence makes pytest discover subtrees correctly.
7. `src/ollama_llm_bench/backend/services/providers/__init__.py` is an empty file — it creates the Python package where all provider implementations will live.
8. Running `uv run pytest tests/ -q` after this task completes must exit 0 (no tests collected, no errors).
9. Running `uv run python -c "import openai; import anthropic; import google.genai"` must succeed without import errors.

### Existing Code Reference

- `pyproject.toml` lines 1–30 — current dependency block; add the three new packages under `[project.dependencies]` following the existing bounded-range style (e.g., `"openai>=1.0"`, `"anthropic>=0.40"`, `"google-genai>=1.0"`).
- `pyproject.toml` lines 55–80 — existing pytest configuration under `[tool.pytest.ini_options]`; no changes needed, it already declares `testpaths = ["tests"]`.

### Implementation Guidance

- Use `uv add openai anthropic google-genai` in one command (or three separate commands).
- All `__init__.py` files in `tests/` are empty — they exist only for pytest package discovery.
- Do NOT add `pytest-randomly` or other test plugins yet.

### Verification

- [ ] `uv run python -c "import openai; import anthropic; import google.genai; print('OK')"` prints `OK`
- [ ] `pyproject.toml` contains `openai`, `anthropic`, and `google-genai` in `[project.dependencies]`
- [ ] `uv.lock` updated (contains `openai`, `anthropic`, `google-genai` entries)
- [ ] `tests/unit/services/providers/` directory exists
- [ ] `src/ollama_llm_bench/backend/services/providers/__init__.py` exists
- [ ] `uv run pytest tests/ -q` exits 0

---

## Task 2: Update InferenceResponse and Add ModelDescriptor + StreamChunk to models.py

**Files to modify**:
- `src/ollama_llm_bench/backend/core/models.py`
- `src/ollama_llm_bench/backend/services/ollama_llm_api.py`
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py`

**Files to create**:
- `tests/unit/core/test_models.py`

**Depends on**: Task 1 (test infrastructure exists)

### Context

`InferenceResponse` currently uses V1 field names (`time_taken_ms`, `tokens_generated`) while `BenchmarkResult` already uses V2 names (`total_time_ms`, `completion_tokens`). This inconsistency means `qt_benchmark_execution_task.py` cannot correctly map inference results to stored results. This task fixes the naming, adds the missing `ttft_ms`/`prompt_tokens` fields, and introduces two new model types (`ModelDescriptor`, `StreamChunk`) that the provider interfaces in Task 3 depend on.

### Requirements

1. `InferenceResponse` in `models.py` is updated to:
   ```python
   @dataclass(frozen=True)
   class InferenceResponse:
       llm_response: str = ""
       total_time_ms: int = 0          # renamed from time_taken_ms
       completion_tokens: int = 0      # renamed from tokens_generated
       prompt_tokens: int | None = None  # new
       ttft_ms: int | None = None        # new — populated only by streaming inference
       has_error: bool = False
       error_message: str | None = None
   ```
2. `OllamaApi` in `ollama_llm_api.py` is updated to use `total_time_ms=time_taken_ms` and `completion_tokens=tokens_generated` in its `InferenceResponse` construction (lines ~135–139 of the original file).
3. `qt_benchmark_execution_task.py` is updated wherever it reads `response.time_taken_ms` → `response.total_time_ms` and `response.tokens_generated` → `response.completion_tokens` (lines ~272–273, ~373–374, ~434–435, ~457–458).
4. `ModelDescriptor` is added to `models.py`:
   ```python
   @dataclass(frozen=True, slots=True, kw_only=True)
   class ModelDescriptor:
       provider_id: str
       provider_type: str
       model_name: str
       display_label: str        # e.g. "ollama_local / llama3.1:8b"
       model_family: str | None = None
       model_size_b: float | None = None
       quantization_label: str | None = None
   ```
5. `StreamChunk` is added to `models.py`:
   ```python
   @dataclass(frozen=True, slots=True)
   class StreamChunk:
       delta_content: str
       is_final: bool = False
       finish_reason: str | None = None
   ```
6. `ModelDescriptor` and `StreamChunk` are importable via `from ollama_llm_bench.backend.core.models import ModelDescriptor, StreamChunk`.
7. Unit tests in `tests/unit/core/test_models.py` verify:
   - `InferenceResponse()` constructs with all defaults (`total_time_ms=0`, `completion_tokens=0`, `ttft_ms=None`)
   - `InferenceResponse(total_time_ms=500, completion_tokens=100, ttft_ms=50)` stores values correctly
   - `ModelDescriptor(provider_id="ollama_local", provider_type="openai_compatible", model_name="llama3.2:3b", display_label="ollama_local / llama3.2:3b")` constructs correctly
   - `ModelDescriptor` is frozen (assigning to a field raises `FrozenInstanceError`)
   - `StreamChunk(delta_content="Hello")` constructs with `is_final=False`
   - `StreamChunk(delta_content="", is_final=True, finish_reason="stop")` stores all fields

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` lines 277–286 — current `InferenceResponse` definition to update
- `src/ollama_llm_bench/backend/services/ollama_llm_api.py` lines 121, 129, 135–139 — where `tokens_generated` and `time_taken_ms` are assigned and used in `InferenceResponse(...)` construction
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines ~272–273, ~373–374, ~434–435, ~457–458 — where `response.time_taken_ms` and `response.tokens_generated` are read; rename these references

### Implementation Guidance

- Place `ModelDescriptor` between `ProvidersConfig` and `AvgSummaryTableItem` in `models.py` (after config dataclasses, before display dataclasses).
- Place `StreamChunk` immediately after `InferenceResponse`.
- In `OllamaApi`, the only change is two keyword argument names in the `InferenceResponse(...)` call — no logic changes needed.
- In `qt_benchmark_execution_task.py`, search for all occurrences of `.time_taken_ms` and `.tokens_generated` that reference an `InferenceResponse` object and rename them. Do NOT rename occurrences that reference `BenchmarkResult` fields (those are already correctly named `total_time_ms` and `completion_tokens`).

### Verification

- [ ] `uv run pytest tests/unit/core/test_models.py -v` — all tests pass
- [ ] `uv run python -c "from ollama_llm_bench.backend.core.models import InferenceResponse, ModelDescriptor, StreamChunk; print('OK')"` prints `OK`
- [ ] `uv run ruff check src/ tests/` — no errors
- [ ] `uv run mypy src/` — no new errors introduced

---

## Task 3: Add LLMProviderApi, EmbeddingProviderApi, and ProviderRegistryApi Protocols to interfaces.py

**Files to modify**:
- `src/ollama_llm_bench/backend/core/interfaces.py`
- `src/ollama_llm_bench/app_context.py`

**Depends on**: Task 2 (`ModelDescriptor`, `StreamChunk`, updated `InferenceResponse` must exist)

### Context

The new provider system is contract-first: the `LLMProviderApi`, `EmbeddingProviderApi`, and `ProviderRegistryApi` Protocol definitions in `interfaces.py` are the single source of truth that all provider implementations (Tasks 5–9) conform to. Defining them before any implementation ensures no circular dependencies and enables type checking of each provider independently. The existing `LLMApi(ABC)` is NOT modified or removed.

### Requirements

1. `LLMProviderApi` Protocol is added to `interfaces.py`:
   ```python
   class LLMProviderApi(Protocol):
       @property
       def provider_id(self) -> str: ...
       @property
       def provider_type(self) -> str: ...

       def get_available_models(self) -> list[ModelDescriptor]: ...

       def inference_sync(
           self,
           *,
           model: str,
           messages: list[dict[str, str]],
           temperature: float = 0.0,
           max_tokens: int | None = None,
       ) -> InferenceResponse: ...

       def inference_stream(
           self,
           *,
           model: str,
           messages: list[dict[str, str]],
           temperature: float = 0.0,
           max_tokens: int | None = None,
       ) -> Generator[StreamChunk, None, InferenceResponse]: ...

       def supports_structured_output(self) -> bool: ...
       def supports_streaming(self) -> bool: ...
       def warm_up(self, model: str) -> bool: ...
   ```
2. `EmbeddingProviderApi` Protocol is added:
   ```python
   class EmbeddingProviderApi(Protocol):
       def encode(self, texts: list[str]) -> list[list[float]]: ...
   ```
3. `ProviderRegistryApi` Protocol is added:
   ```python
   class ProviderRegistryApi(Protocol):
       def load(self) -> None: ...
       def reload(self) -> None: ...
       def get_provider(self, provider_id: str) -> LLMProviderApi: ...
       def get_all_providers(self) -> list[LLMProviderApi]: ...
       def get_enabled_providers(self) -> list[LLMProviderApi]: ...
       def get_embedding_provider(self) -> EmbeddingProviderApi: ...
   ```
4. `get_provider_registry() -> ProviderRegistryApi` abstract method is added to `AppContext(ABC)` (lines 657–739 of `interfaces.py`).
5. New imports added at the top of `interfaces.py`:
   ```python
   from collections.abc import Generator
   # In the models import block, add:
   ModelDescriptor,
   StreamChunk,
   ```
6. The existing `LLMApi(ABC)`, `DataApi(ABC)`, `EventBus(ABC)`, `AppContext(ABC)`, `ProviderConfigLoaderApi(Protocol)` etc. are unchanged.
7. `ApplicationContext` in `app_context.py` is updated to add a stub implementation of `get_provider_registry()` that raises `NotImplementedError("Wired in Task 10")` — this prevents `TypeError: Can't instantiate abstract class` at startup while the real wiring waits for Task 10.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/interfaces.py` lines 1–27 — existing imports to extend
- `src/ollama_llm_bench/backend/core/interfaces.py` lines 657–739 — `AppContext(ABC)` to add `get_provider_registry()` to
- `src/ollama_llm_bench/backend/core/interfaces.py` lines 783–807 — `ProviderConfigLoaderApi(Protocol)` — follow this pattern for the three new Protocols
- `src/ollama_llm_bench/app_context.py` — `ApplicationContext(AppContext)` to add the stub method

### Implementation Guidance

- Position the three new Protocol classes after the existing `ProviderConfigLoaderApi(Protocol)` at the bottom of `interfaces.py`.
- The `inference_stream` return type `Generator[StreamChunk, None, InferenceResponse]` means: yields `StreamChunk` objects, receives `None` from `.send()`, returns `InferenceResponse` when exhausted. Import `Generator` from `collections.abc`.
- `messages: list[dict[str, str]]` is the OpenAI chat format: `[{"role": "user", "content": "..."}, {"role": "system", "content": "..."}]`.
- Do NOT add `@runtime_checkable` to these Protocols — no `isinstance()` checks are needed.

### Verification

- [ ] `uv run python -c "from ollama_llm_bench.backend.core.interfaces import LLMProviderApi, EmbeddingProviderApi, ProviderRegistryApi; print('OK')"` prints `OK`
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ollama_llm_bench --help` does not crash (`ApplicationContext` still instantiable with stub)
- [ ] `uv run ruff check src/` — no errors

---

## Task 4: Implement ModelNameParser + Unit Tests

**Files to create**:
- `src/ollama_llm_bench/backend/services/model_name_parser.py`
- `tests/unit/services/test_model_name_parser.py`

**Depends on**: Task 2 (`ModelDescriptor` exists)

### Context

`ModelDescriptor` stores parsed model metadata (`model_family`, `model_size_b`, `quantization_label`) extracted from raw model name strings like `llama3.1:8b-instruct-q4_K_M`. `ModelNameParser` is a stateless utility that provider implementations call when constructing `ModelDescriptor` objects from API-returned model names. It handles Ollama naming conventions and gracefully returns `None` for fields it cannot parse (cloud model names like `gpt-4o` are opaque).

### Requirements

1. `ModelNameParser` is a concrete class with no ABC or Protocol — it is a stateless utility.
2. Single public method:
   ```python
   def parse(self, *, provider_id: str, provider_type: str, model_name: str) -> ModelDescriptor
   ```
3. For Ollama-style names (`family:size-variant-quant`, e.g., `llama3.1:8b-instruct-q4_K_M`):
   - `model_family`: the portion before `:`, e.g. `llama3.1` (keep as-is including version)
   - `model_size_b`: float parsed from size token matching `\d+(?:\.\d+)?[bB]`, e.g. `8b` → `8.0`, `0.5b` → `0.5`
   - `quantization_label`: token matching `q\d+(?:_[a-zA-Z0-9]+)*` pattern, e.g. `q4_K_M`
   - Returns `None` for any field the regex does not match
4. For names with no `:` separator (e.g., `mistral`, `llava`): `model_family = model_name`, size and quant = `None`
5. For cloud-style names (`gpt-4o`, `claude-opus-4-6`, `gemini-2.0-flash`): all parsed fields are `None`
6. `display_label` is always `f"{provider_id} / {model_name}"` regardless of parsing success
7. `ModelNameParser.__init__(self)` takes no arguments (purely stateless)
8. Unit tests cover:
   - `llama3.1:8b-instruct-q4_K_M` → `model_size_b=8.0`, `quantization_label="q4_K_M"`
   - `mistral:7b` → `model_size_b=7.0`, `quantization_label=None`
   - `qwen2.5:72b-instruct-q2_K` → `model_size_b=72.0`, `quantization_label="q2_K"`
   - `llava:latest` → `model_size_b=None`, `quantization_label=None`
   - `gpt-4o` → all parsed fields `None`
   - `claude-opus-4-6` → all parsed fields `None`
   - `display_label` is always `provider_id + " / " + model_name`
   - Empty string `model_name` returns a valid `ModelDescriptor` (no crash)

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` — `ModelDescriptor` definition (from Task 2) — the return type
- `src/ollama_llm_bench/backend/services/app_result_api.py` — follow the class structure pattern (private helpers as `@staticmethod`, module-level logger)

### Implementation Guidance

- Module-level regex constants:
  ```python
  _SIZE_PATTERN: re.Pattern[str] = re.compile(r"(\d+(?:\.\d+)?)b", re.IGNORECASE)
  _QUANT_PATTERN: re.Pattern[str] = re.compile(r"q\d+(?:_[a-zA-Z0-9]+)*", re.IGNORECASE)
  ```
- Extract private helpers: `_extract_size(tag: str) -> float | None`, `_extract_quant(tag: str) -> str | None`.
- The `parse()` method should be under 30 lines. Never raise exceptions — always return a valid `ModelDescriptor`.
- Module-level logger: `logger = logging.getLogger(__name__)`.

### Verification

- [ ] `uv run pytest tests/unit/services/test_model_name_parser.py -v` — all tests pass
- [ ] `uv run python -c "from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser; print(ModelNameParser().parse(provider_id='ollama_local', provider_type='openai_compatible', model_name='llama3.1:8b-instruct-q4_K_M'))"` prints a `ModelDescriptor`
- [ ] `uv run ruff check src/ tests/` — no errors
- [ ] `uv run mypy src/` — no errors

---

## Task 5: Implement OpenAICompatibleProvider + Unit Tests

**Files to create**:
- `src/ollama_llm_bench/backend/services/providers/openai_compatible_provider.py`
- `tests/unit/services/providers/test_openai_compatible_provider.py`

**Depends on**: Task 1 (`openai` SDK installed, `providers/` package exists), Task 2 (`InferenceResponse`, `StreamChunk`, `ModelDescriptor`), Task 3 (`LLMProviderApi` Protocol), Task 4 (`ModelNameParser`)

### Context

`OpenAICompatibleProvider` is the universal client for every provider that speaks the OpenAI REST protocol: Ollama (local), LM Studio, llama.cpp, OpenAI cloud, Azure. It implements `LLMProviderApi` structurally and is the primary replacement for `OllamaApi`. Both sync and streaming inference modes are implemented here.

### Requirements

1. Class signature:
   ```python
   class OpenAICompatibleProvider:
       def __init__(
           self,
           *,
           provider_id: str,
           provider_type: str,
           base_url: str,
           api_key: str,
           name_parser: ModelNameParser,
       ) -> None: ...
   ```
2. `provider_id` and `provider_type` are exposed as `@property` (backing store `_provider_id`, `_provider_type`).
3. `get_available_models(self) -> list[ModelDescriptor]`:
   - Calls `self._client.models.list()`
   - Maps each model to `ModelDescriptor` via `self._name_parser.parse(...)`
   - Returns sorted list by `model_name`
   - On `openai.APIConnectionError` or any `openai.OpenAIError`: logs WARNING, returns `[]`
4. `inference_sync(self, *, model, messages, temperature, max_tokens) -> InferenceResponse`:
   - Records `start_ns = time.monotonic_ns()`
   - Calls `self._client.chat.completions.create(model=model, messages=messages, stream=False, temperature=temperature, max_tokens=max_tokens)`
   - Records `end_ns`
   - Computes `total_time_ms = (end_ns - start_ns) // 1_000_000`
   - Extracts `response.choices[0].message.content`, `response.usage.prompt_tokens`, `response.usage.completion_tokens`
   - Returns `InferenceResponse(llm_response=content, total_time_ms=total_time_ms, completion_tokens=completion_tokens, prompt_tokens=prompt_tokens, ttft_ms=None)`
   - On any `openai.OpenAIError`: logs ERROR, returns `InferenceResponse(has_error=True, error_message=str(e))`
5. `inference_stream(self, *, model, messages, temperature, max_tokens) -> Generator[StreamChunk, None, InferenceResponse]`:
   - Records `start_ns`
   - Calls `.create(model=model, messages=messages, stream=True, stream_options={"include_usage": True}, temperature=temperature, max_tokens=max_tokens)`
   - On first chunk with non-empty `delta.content`: records `ttft_ns`
   - Yields `StreamChunk(delta_content=content)` per chunk
   - Accumulates all content; on stream end extracts `usage` from final chunk
   - Records `end_ns`, returns `InferenceResponse(llm_response=full_content, total_time_ms=..., ttft_ms=..., completion_tokens=..., prompt_tokens=...)`
   - On `openai.OpenAIError`: logs ERROR, returns `InferenceResponse(has_error=True, error_message=str(e))`
6. `supports_structured_output(self) -> bool` — returns `True`
7. `supports_streaming(self) -> bool` — returns `True`
8. `warm_up(self, model: str) -> bool`:
   - Calls `inference_sync(model=model, messages=[{"role": "user", "content": "hi"}], max_tokens=1)`
   - Returns `not response.has_error`
   - Retries up to `_WARM_UP_RETRIES = 3` times with `_WARM_UP_SLEEP_S = 10` seconds between attempts on failure
   - Logs WARNING on each retry
9. `openai.OpenAI` client constructed once in `__init__` as `self._client = openai.OpenAI(base_url=base_url, api_key=api_key)`.
10. Unit tests mock `openai.OpenAI` using `mocker.Mock(spec=openai.OpenAI)` and verify:
    - Successful `inference_sync` populates `InferenceResponse` fields correctly
    - `openai.APIConnectionError` returns `InferenceResponse(has_error=True)`
    - `get_available_models` returns sorted list on success
    - `get_available_models` returns `[]` on connection error
    - `warm_up` returns `True` when `inference_sync` succeeds
    - `warm_up` returns `False` after 3 failed retries

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/ollama_llm_api.py` lines 59–96 — warm_up retry pattern to follow
- `src/ollama_llm_bench/backend/core/interfaces.py` — `LLMProviderApi` Protocol (Task 3) — class must satisfy it structurally
- `src/ollama_llm_bench/backend/core/models.py` — `InferenceResponse`, `ModelDescriptor`, `StreamChunk` (Task 2)
- `src/ollama_llm_bench/backend/services/model_name_parser.py` — `ModelNameParser` (Task 4)

### Implementation Guidance

- Use `time.monotonic_ns()` for all timing; convert to ms with `// 1_000_000`.
- Module-level constants: `_WARM_UP_RETRIES: int = 3`, `_WARM_UP_SLEEP_S: int = 10`.
- For streaming, the generator `return` statement (not `yield`) is what carries the final `InferenceResponse` back to the caller using `StopIteration.value`. The caller retrieves it via `yield from` or by catching `StopIteration`.

### Verification

- [ ] `uv run pytest tests/unit/services/providers/test_openai_compatible_provider.py -v` — all tests pass
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ruff check src/ tests/` — no errors

---

## Task 6: Implement AnthropicProvider + Unit Tests

**Files to create**:
- `src/ollama_llm_bench/backend/services/providers/anthropic_provider.py`
- `tests/unit/services/providers/test_anthropic_provider.py`

**Depends on**: Task 1 (`anthropic` SDK), Task 2 (`InferenceResponse`, `StreamChunk`, `ModelDescriptor`), Task 3 (`LLMProviderApi` Protocol)

### Context

Anthropic's API does not speak the OpenAI protocol and requires the `anthropic` Python SDK. `AnthropicProvider` wraps it and presents the same `LLMProviderApi` interface as `OpenAICompatibleProvider`. Key differences: no `/models` endpoint (model list is static from config), and no `response_format` structured output support.

### Requirements

1. Class signature:
   ```python
   class AnthropicProvider:
       def __init__(
           self,
           *,
           provider_id: str,
           api_key: str,
           default_models: tuple[str, ...],
       ) -> None: ...
   ```
2. `provider_id` property returns injected value; `provider_type` property returns `"anthropic"`.
3. `get_available_models(self) -> list[ModelDescriptor]`:
   - Returns `ModelDescriptor` objects built from `default_models` — no API call
   - All parsed fields `None`; `display_label = f"{self._provider_id} / {model_name}"`
4. `inference_sync(self, *, model, messages, temperature, max_tokens) -> InferenceResponse`:
   - Extracts system message (where `role == "system"`) from `messages`, passes remaining as Anthropic `messages=` parameter and system text as `system=` parameter
   - Records wall-clock time with `time.monotonic_ns()`
   - Calls `self._client.messages.create(model=model, max_tokens=max_tokens or _DEFAULT_MAX_TOKENS, system=system_text, messages=non_system_messages, temperature=temperature)`
   - Extracts `response.content[0].text`, `response.usage.input_tokens`, `response.usage.output_tokens`
   - Returns `InferenceResponse(llm_response=text, total_time_ms=..., completion_tokens=output_tokens, prompt_tokens=input_tokens, ttft_ms=None)`
   - On `anthropic.APIError`: returns `InferenceResponse(has_error=True, error_message=str(e))`
5. `inference_stream(self, *, model, messages, temperature, max_tokens) -> Generator[StreamChunk, None, InferenceResponse]`:
   - Uses `self._client.messages.stream(...)` context manager
   - Yields `StreamChunk` for each text delta event; records `ttft_ns` on first non-empty delta
   - Returns `InferenceResponse(...)` with `ttft_ms` populated
6. `supports_structured_output(self) -> bool` — returns `False`
7. `supports_streaming(self) -> bool` — returns `True`
8. `warm_up(self, model: str) -> bool` — single `inference_sync` call, returns `not response.has_error`, no retry loop
9. Module-level constant: `_DEFAULT_MAX_TOKENS: int = 4096`
10. Unit tests mock `anthropic.Anthropic` using `mocker.Mock(spec=anthropic.Anthropic)` and verify success and error paths.

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/providers/openai_compatible_provider.py` (Task 5) — follow same structural pattern
- `src/ollama_llm_bench/backend/core/interfaces.py` — `LLMProviderApi` Protocol must be satisfied

### Verification

- [ ] `uv run pytest tests/unit/services/providers/test_anthropic_provider.py -v` — all tests pass
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ruff check src/ tests/` — no errors

---

## Task 7: Implement GeminiProvider + Unit Tests

**Files to create**:
- `src/ollama_llm_bench/backend/services/providers/gemini_provider.py`
- `tests/unit/services/providers/test_gemini_provider.py`

**Depends on**: Task 1 (`google-genai` SDK), Task 2 (`InferenceResponse`, `StreamChunk`, `ModelDescriptor`), Task 3 (`LLMProviderApi` Protocol)

### Context

Google Gemini requires the `google-genai` Python SDK (unified Google AI SDK, not the older `google-generativeai`). Like Anthropic, it does not speak the OpenAI protocol. It supports structured output via `response_mime_type`. Model list comes from `default_models` config (static, same pattern as Anthropic).

### Requirements

1. Class signature:
   ```python
   class GeminiProvider:
       def __init__(
           self,
           *,
           provider_id: str,
           api_key: str,
           default_models: tuple[str, ...],
       ) -> None: ...
   ```
2. `provider_id` property returns injected value; `provider_type` property returns `"gemini"`.
3. `get_available_models(self) -> list[ModelDescriptor]`:
   - Returns `ModelDescriptor` objects from `default_models` (static, no API call); all parsed fields `None`
4. `inference_sync(self, *, model, messages, temperature, max_tokens) -> InferenceResponse`:
   - Extracts system message from `messages` → passes as `system_instruction` in `GenerateContentConfig`
   - Converts remaining messages: `role="user"` → `"user"`, `role="assistant"` → `"model"`
   - Calls `self._client.models.generate_content(model=model, contents=contents, config=GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens, system_instruction=system_text))`
   - Extracts `response.text`, `response.usage_metadata.prompt_token_count`, `response.usage_metadata.candidates_token_count`
   - Returns `InferenceResponse(llm_response=text, total_time_ms=..., completion_tokens=candidates_token_count, prompt_tokens=prompt_token_count, ttft_ms=None)`
   - On any `Exception`: returns `InferenceResponse(has_error=True, error_message=str(e))`
5. `inference_stream(self, *, model, messages, temperature, max_tokens) -> Generator[StreamChunk, None, InferenceResponse]`:
   - Uses `self._client.models.generate_content_stream(...)` iterator
   - Yields `StreamChunk` per chunk; records `ttft_ns` on first chunk
   - Returns complete `InferenceResponse` at end
6. `supports_structured_output(self) -> bool` — returns `True`
7. `supports_streaming(self) -> bool` — returns `True`
8. `warm_up(self, model: str) -> bool` — single `inference_sync` call, no retry
9. Imports: `import google.genai` and `from google.genai import types as genai_types`
10. `self._client = google.genai.Client(api_key=api_key)` constructed once in `__init__`
11. Module-level constant: `_DEFAULT_MAX_TOKENS: int = 8192`
12. Unit tests mock `google.genai.Client` and verify success + error paths.

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/providers/anthropic_provider.py` (Task 6) — follow same structural pattern

### Verification

- [ ] `uv run pytest tests/unit/services/providers/test_gemini_provider.py -v` — all tests pass
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ruff check src/ tests/` — no errors

---

## Task 8: Implement OpenAIEmbeddingProvider + EmbeddingService + Unit Tests

**Files to create**:
- `src/ollama_llm_bench/backend/services/providers/openai_embedding_provider.py`
- `src/ollama_llm_bench/backend/services/embedding_service.py`
- `tests/unit/services/providers/test_openai_embedding_provider.py`
- `tests/unit/services/test_embedding_service.py`

**Depends on**: Task 1 (`openai` SDK, `providers/` package), Task 3 (`EmbeddingProviderApi` Protocol)

### Context

`OpenAIEmbeddingProvider` calls the `/v1/embeddings` endpoint (supported by Ollama and OpenAI). `EmbeddingService` wraps it with an LRU cache keyed on input text so repeated calls for the same text (common during cosine similarity evaluation) avoid redundant network calls. `CosineSimilarityEvaluator` (Phase 3) will consume `EmbeddingService`.

### Requirements

1. `EmbeddingError(RuntimeError)` — custom exception defined in `openai_embedding_provider.py`.
2. `OpenAIEmbeddingProvider` class:
   ```python
   class OpenAIEmbeddingProvider:
       def __init__(self, *, base_url: str, api_key: str, model: str) -> None: ...
       def encode(self, texts: list[str]) -> list[list[float]]: ...
   ```
   - `encode()` calls `self._client.embeddings.create(model=self._model, input=texts)`
   - Returns `[item.embedding for item in response.data]`
   - On `openai.OpenAIError`: logs ERROR, raises `EmbeddingError(str(e))`
   - On empty `texts`: returns `[]` (no API call)
3. `EmbeddingService` class:
   ```python
   class EmbeddingService:
       def __init__(self, *, provider: EmbeddingProviderApi, cache_size: int = 512) -> None: ...
       def encode_single(self, text: str) -> list[float]: ...
       def encode_batch(self, texts: list[str]) -> list[list[float]]: ...
   ```
   - `encode_single(text)`: checks `self._cache` (keyed on text); on miss calls `provider.encode([text])`, caches result, returns `embeddings[0]`
   - `encode_batch(texts)`: partitions into cached/uncached; calls `provider.encode(uncached_texts)` once; caches new results; returns all embeddings in original order
   - Cache: `collections.OrderedDict[str, list[float]]` with max-size LRU eviction (`OrderedDict.move_to_end()` on hit, pop oldest when at `cache_size` capacity)
   - `encode_batch([])` returns `[]`
4. `EmbeddingProviderApi` Protocol (Task 3) is satisfied by `OpenAIEmbeddingProvider` structurally.
5. Unit tests for `OpenAIEmbeddingProvider`:
   - Successful `encode` returns list of float vectors
   - `openai.OpenAIError` raises `EmbeddingError`
   - Empty input `[]` returns `[]` with no API call
6. Unit tests for `EmbeddingService`:
   - Cache hit avoids second provider call (mock verifies `encode` called only once for repeated text)
   - `encode_batch` with mixed cached/uncached calls provider only for uncached subset
   - `encode_batch([])` returns `[]`
   - Cache evicts oldest entry when at capacity

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/interfaces.py` — `EmbeddingProviderApi(Protocol)` (Task 3)
- `src/ollama_llm_bench/backend/services/providers/openai_compatible_provider.py` (Task 5) — import and error handling patterns

### Implementation Guidance

- `self._client = openai.OpenAI(base_url=base_url, api_key=api_key)` in `__init__`.
- LRU eviction in `EmbeddingService._store(text, embedding)`:
  ```python
  if text in self._cache:
      self._cache.move_to_end(text)
  else:
      if len(self._cache) >= self._cache_size:
          self._cache.popitem(last=False)  # evict oldest
      self._cache[text] = embedding
  ```

### Verification

- [ ] `uv run pytest tests/unit/services/providers/test_openai_embedding_provider.py tests/unit/services/test_embedding_service.py -v` — all pass
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ruff check src/ tests/` — no errors

---

## Task 9: Implement ProviderRegistry + Unit Tests

**Files to create**:
- `src/ollama_llm_bench/backend/services/provider_registry.py`
- `tests/unit/services/test_provider_registry.py`

**Depends on**: Task 3 (`ProviderRegistryApi` Protocol), Task 4 (`ModelNameParser`), Task 5 (`OpenAICompatibleProvider`), Task 6 (`AnthropicProvider`), Task 7 (`GeminiProvider`), Task 8 (`EmbeddingService`, `OpenAIEmbeddingProvider`)

### Context

`ProviderRegistry` is the composition root for all provider clients. It reads `providers.yaml` via `ProviderConfigLoader`, constructs the correct provider class based on `provider_type`, and exposes the unified `LLMProviderApi` interface. After Phase 2 updates the execution engine, everything that calls an LLM goes through `ProviderRegistry.get_provider(provider_id)`.

### Requirements

1. Custom exceptions (defined in `provider_registry.py`):
   - `ProviderNotFoundError(KeyError)` — raised when `provider_id` is not in the registry
2. Class signature:
   ```python
   class ProviderRegistry:
       def __init__(
           self,
           *,
           config_loader: ProviderConfigLoaderApi,
           providers_yaml_path: Path,
       ) -> None: ...
       def load(self) -> None: ...
       def reload(self) -> None: ...
       def get_provider(self, provider_id: str) -> LLMProviderApi: ...
       def get_all_providers(self) -> list[LLMProviderApi]: ...
       def get_enabled_providers(self) -> list[LLMProviderApi]: ...
       def get_embedding_provider(self) -> EmbeddingProviderApi: ...
   ```
3. `load()` implementation:
   - Calls `self._config_loader.load(self._providers_yaml_path)` → `ProvidersConfig`
   - Constructs providers using a dispatch dict (not `isinstance` chaining):
     ```python
     _PROVIDER_FACTORIES = {
         ProviderType.OPENAI_COMPATIBLE: _build_openai_compatible,
         ProviderType.ANTHROPIC: _build_anthropic,
         ProviderType.GEMINI: _build_gemini,
     }
     ```
     where `_build_*` are module-level private functions taking `(config: ProviderConfig, name_parser: ModelNameParser) -> LLMProviderApi`
   - Stores all constructed providers in `self._providers: dict[str, LLMProviderApi]` keyed by `provider_id`
   - Stores `self._config: ProvidersConfig`
   - Resolves embedding provider: finds the `ProviderConfig` matching `config.embedding.provider_id`, constructs `OpenAIEmbeddingProvider`, wraps in `EmbeddingService`, stores as `self._embedding_service`
   - If embedding provider not found or construction fails: logs WARNING, sets `self._embedding_service = None`
   - Sets `self._is_loaded = True`
   - On `Exception`: logs ERROR, stores empty `self._providers = {}`, sets `self._is_loaded = True` (so get_* don't crash with "not loaded" error)
4. `reload()` — calls `load()` again, replacing all internal state
5. `get_provider(provider_id) -> LLMProviderApi`:
   - Guards `self._is_loaded` — raises `RuntimeError("ProviderRegistry not loaded — call load() first")` if not loaded
   - Raises `ProviderNotFoundError(f"Provider '{provider_id}' not found")` on `KeyError`
6. `get_all_providers() -> list[LLMProviderApi]` — returns `list(self._providers.values())`
7. `get_enabled_providers() -> list[LLMProviderApi]`:
   - Returns providers where the corresponding `ProviderConfig.enabled` is `True`
   - Cross-references `self._config.providers` for enabled status
8. `get_embedding_provider() -> EmbeddingProviderApi`:
   - Returns `self._embedding_service`
   - Raises `RuntimeError("Embedding provider not available")` if `self._embedding_service is None`
9. Calling any `get_*` before `load()` raises `RuntimeError("ProviderRegistry not loaded — call load() first")`
10. Unit tests mock `ProviderConfigLoaderApi` and verify:
    - After `load()`, `get_all_providers()` returns correct provider count
    - `get_provider("ollama_local")` returns an `OpenAICompatibleProvider`-like object
    - `get_provider("nonexistent")` raises `ProviderNotFoundError`
    - `get_enabled_providers()` filters by `enabled=True`
    - `get_provider()` before `load()` raises `RuntimeError`
    - Load failure (exception from config_loader) leaves registry with empty providers, not crashing

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/provider_config_loader.py` — `ProviderConfigLoader` — concrete implementation of `ProviderConfigLoaderApi` that gets injected
- `src/ollama_llm_bench/backend/core/interfaces.py` — `ProviderConfigLoaderApi(Protocol)`, `ProviderRegistryApi(Protocol)`, `LLMProviderApi(Protocol)`, `EmbeddingProviderApi(Protocol)`
- `src/ollama_llm_bench/backend/core/models.py` — `ProviderType`, `ProviderConfig`, `ProvidersConfig`, `EmbeddingConfig`

### Verification

- [ ] `uv run pytest tests/unit/services/test_provider_registry.py -v` — all tests pass
- [ ] `uv run python -c "from ollama_llm_bench.backend.services.provider_registry import ProviderRegistry, ProviderNotFoundError; print('OK')"` prints `OK`
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ruff check src/ tests/` — no errors

---

## Task 10: Wire ProviderRegistry into ApplicationContext + Update Documentation

**Files to modify**:
- `src/ollama_llm_bench/app_context.py`
- `.claude/CLAUDE.md`

**Depends on**: Task 3 (`ProviderRegistryApi` in `AppContext` ABC), Task 9 (`ProviderRegistry` complete)

### Context

`ProviderRegistry` must be instantiated at application startup and accessible through `ApplicationContext`. This task replaces the Task 3 stub with a real implementation, wires `ProviderRegistry` into `_create_app_context()`, and updates project documentation. The existing `OllamaApi` and `get_llm_api()` are kept in place — Phase 2 will remove them when the execution engine migrates to use `ProviderRegistry`.

### Requirements

1. `ApplicationContext.__init__` accepts `*, provider_registry: ProviderRegistryApi` as a new keyword argument alongside existing args.
2. `ApplicationContext.get_provider_registry(self) -> ProviderRegistryApi` returns `self._provider_registry` (replaces the `NotImplementedError` stub from Task 3).
3. `_create_app_context(app_root: Path, dataset_path: Path) -> ApplicationContext` is updated:
   - Resolves `providers_yaml_path`:
     ```python
     import importlib.resources
     providers_yaml_path = app_root / "providers.yaml"
     if not providers_yaml_path.exists():
         ref = importlib.resources.files("ollama_llm_bench").joinpath("providers.yaml")
         providers_yaml_path = Path(str(ref))
     ```
   - Instantiates `ProviderConfigLoader()` and `ProviderRegistry(config_loader=config_loader, providers_yaml_path=providers_yaml_path)`
   - Calls `registry.load()` wrapped in `try/except Exception` — logs ERROR on failure but does not crash
   - Passes `provider_registry=registry` to `ApplicationContext(...)`
4. The existing `OllamaApi` instantiation, `get_llm_api()` method, and all associated slots are KEPT unchanged.
5. `.claude/CLAUDE.md` "V2 New Services & Locations" table is updated: mark `OpenAICompatibleProvider`, `AnthropicProvider`, `GeminiProvider`, `EmbeddingService`, `ProviderRegistry`, `ProviderConfigLoader`, `ModelNameParser` as **IMPLEMENTED (Phase 1)**.
6. `.claude/CLAUDE.md` "Key Files" table adds `src/ollama_llm_bench/backend/services/provider_registry.py`.
7. `uv run ollama_llm_bench` starts the application without errors, with `ProviderRegistry` loaded (even if Ollama is not running — registry load failure is logged, not crashed).

### Existing Code Reference

- `src/ollama_llm_bench/app_context.py` lines 232–265 — `ContextProvider.initialize()` and `_create_app_context()` to extend
- `src/ollama_llm_bench/main.py` lines 74–103 — `get_dataset_path()` fallback pattern to replicate for `providers.yaml` resolution
- `src/ollama_llm_bench/backend/core/interfaces.py` lines 657–739 — `AppContext(ABC)` with `get_provider_registry()` abstract method (Task 3)

### Implementation Guidance

- Check whether `ApplicationContext` uses `__slots__` — if yes, add `"_provider_registry"` to the slots tuple.
- Add `provider_registry` as the last keyword argument in `ApplicationContext.__init__` to minimize diff noise.
- The `registry.load()` guard:
  ```python
  try:
      registry.load()
  except Exception:
      logger.exception("provider_registry_load_failed")
  ```

### Verification

- [ ] `uv run ollama_llm_bench` starts without `TypeError` or `RuntimeError`
- [ ] `uv run pytest tests/ -q` — all tests pass, no regressions
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run ruff check src/ tests/` — no errors

---

## Final Verification Checklist

When ALL tasks are complete, verify end-to-end:

- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] App starts without errors: `uv run ollama_llm_bench`
- [ ] All 3 provider classes importable:
  ```bash
  uv run python -c "
  from ollama_llm_bench.backend.services.providers.openai_compatible_provider import OpenAICompatibleProvider
  from ollama_llm_bench.backend.services.providers.anthropic_provider import AnthropicProvider
  from ollama_llm_bench.backend.services.providers.gemini_provider import GeminiProvider
  print('OK')
  "
  ```
- [ ] ProviderRegistry importable: `uv run python -c "from ollama_llm_bench.backend.services.provider_registry import ProviderRegistry; print('OK')"`
- [ ] No Qt imports in `core/` or `services/`
- [ ] All new code uses absolute imports: `from ollama_llm_bench.backend.core.models import ...`
- [ ] All new classes use keyword-only constructor args (`*` in `__init__`)
- [ ] Type annotations on all public methods
- [ ] `uv run mypy src/` — zero errors
- [ ] `uv run ruff format --check src/ tests/` — zero formatting violations
- [ ] No stale `time_taken_ms` / `tokens_generated` references anywhere (all updated to `total_time_ms` / `completion_tokens`)
- [ ] `.claude/CLAUDE.md` updated to reflect Phase 1 completion
