# Phase 6 — Quality & Packaging: Implementation Plan

**Generated**: 2026-04-17
**Source**: docs/v2/v2-implementation-plan.md sections 6.1, 6.2
**Scope**: Expand the test suite to integration and HTTP-level coverage, add the task validation CLI, migrate to OS-aware user data paths, and add PyInstaller packaging configuration for macOS, Linux, and Windows.

---

## Prerequisites

- Phases 1–5 complete (providers, evaluators, cosine layer, UI, settings/history)
- `uv sync` run successfully with all current deps
- `./scripts/ai-check.sh` passes (ruff, pyright, mypy, pytest) on the clean branch

---

## Architecture Decisions

These are non-negotiable constraints from the V2 plan and project rules:

1. **`core/` must stay pure Python** — no Qt, no `openai`, no `yaml` imports. `app_paths.py` will live in `backend/core/` and may only use `stdlib` (`sys`, `os`, `pathlib`).
2. **Absolute imports only** — `from ollama_llm_bench.backend.core.app_paths import get_user_data_dir`.
3. **Constructor DI with keyword-only args** — all new services accept deps via `__init__(self, *, ...)`.
4. **Integration tests use `tmp_path`** — never share mutable state between test functions; use `":memory:"` for SQLite or a fresh `tmp_path / "test.db"`.
5. **`pytest-qt`** — add as dev dep; use `qtbot` for signal capture in new widget tests. Existing tests that use the manual `qapp` fixture pattern are acceptable to leave as-is.
6. **`pytest-httpserver`** — add as dev dep; use for integration tests that verify the real HTTP conversation between `OpenAICompatibleProvider` and the API endpoints.
7. **OS-aware data directory** — `main.py` must pass the platform-specific path as `app_root` to `ContextProvider.initialize()`. The existing fallback logic in `app_context.py` (lines 410–416) already copies `providers.yaml` from the bundle if absent; `app_root` just needs to be set correctly.
8. **PyInstaller** — build tool only, added as a standalone dev dep (`uv add --dev pyinstaller`); not an application dependency.
9. **`db.sqlite` must not be in the repo** — `.gitignore` already includes `db.sqlite` (verified).

---

## Task 1: Add Missing Test Dependencies

**Files to modify**:
- `pyproject.toml`

**Depends on**: None

### Context

The existing `tests/unit/widgets/` and `tests/unit/qt_classes/` files expect a `QApplication` instance but do not use `pytest-qt`'s `qtbot`. Several test files create their own `qapp` fixture. Phase 6 requires `pytest-qt` (for `qtbot` in new widget tests), `pytest-httpserver` (for integration-level HTTP mocking), and `pytest-randomly` (for order randomization). None of these are currently in `[dependency-groups].dev` of `pyproject.toml`.

### Requirements

1. `pytest-qt>=4.4` added under `[dependency-groups]` `dev` in `pyproject.toml`.
2. `pytest-httpserver>=1.1` added under `[dependency-groups]` `dev`.
3. `pytest-randomly>=3.15` added under `[dependency-groups]` `dev`.
4. `uv sync` succeeds after the change.
5. `uv run pytest tests/unit/ -q` still passes (no regressions from adding new deps).

### Existing Code Reference

- `pyproject.toml` lines 16–23: current `[dependency-groups]` `dev` section — add new packages here alongside `pytest`, `pytest-mock`, `pytest-cov`, `ruff`, `mypy`, `pyright`.
- `tests/unit/widgets/test_progress_panel_widget.py` lines 22–28: the manual `qapp` fixture pattern that pre-dates `pytest-qt` — leave unchanged.

### Implementation Guidance

In `pyproject.toml` under `[dependency-groups]`, section `dev`, append:

```toml
"pytest-qt>=4.4",
"pytest-httpserver>=1.1",
"pytest-randomly>=3.15",
```

No other files need changing. Run `uv sync` after editing.

### Verification

- [ ] `uv sync` exits 0.
- [ ] `uv run pytest tests/unit/ -q` passes.
- [ ] `uv run python -c "from pytest_httpserver import HTTPServer; print('ok')"` succeeds.
- [ ] `uv run python -c "import pytestqt; print('ok')"` succeeds.

---

## Task 2: Integration Tests — Data Layer (SqLiteDataApi + SchemaMigrationRunner)

**Files to create**:
- `tests/integration/test_sq_lite_data_api.py`
- `tests/integration/test_schema_migration_runner.py`

**Files to modify**:
- `tests/integration/conftest.py` (currently empty — add shared fixtures)

**Depends on**: Task 1

### Context

`tests/integration/` is currently empty. `SqLiteDataApi` and `SchemaMigrationRunner` are the most critical backend services with no integration coverage. Phase 6 requires integration tests that exercise real SQLite I/O against in-memory databases, and that verify the V1→V2 migration path is idempotent and correct.

`SqLiteDataApi` is at `src/ollama_llm_bench/backend/services/sq_lite_data_api.py`. It accepts a `Path` as its sole constructor argument and creates the schema on `__init__`. Using `":memory:"` string as the path is supported by `sqlite3`.

`SchemaMigrationRunner` is at `src/ollama_llm_bench/backend/services/schema_migration_runner.py` (75 lines). Its public entry point is `run_migration(conn: sqlite3.Connection) -> None` which is idempotent.

### Requirements

**`test_sq_lite_data_api.py`**:

1. A function-scoped fixture `data_api(tmp_path)` creates a fresh `SqLiteDataApi(tmp_path / "test.db")` and returns it. Each test gets a clean DB instance.
2. `test_create_and_get_run` — creates a `BenchmarkRun` via `data_api.create_run()`, then retrieves it with `data_api.get_run(run_id)` and asserts all fields match.
3. `test_update_run_status` — creates a run, calls `data_api.update_run_status(run_id, BenchmarkRunStatus.RUNNING)`, fetches the run, asserts `.status == BenchmarkRunStatus.RUNNING`.
4. `test_get_all_runs_returns_all` — inserts 3 runs, asserts `len(data_api.get_all_runs()) == 3`.
5. `test_save_and_get_result` — creates a run, saves a `BenchmarkResult` via `data_api.save_result()`, retrieves it with `data_api.get_result(result_id)`, asserts fields match.
6. `test_get_results_for_run` — saves 2 results with the same `run_id`, asserts `len(data_api.get_results_for_run(run_id)) == 2`.
7. `test_upsert_and_get_setting` — upserts `("ui.theme", "light")`, then `get_setting("ui.theme")` returns `"light"`. Upserting again with `"dark"` returns `"dark"`.
8. `test_get_setting_missing_returns_none` — `get_setting("no.such.key")` returns `None`.
9. `test_save_and_get_prompt_variants` — saves 2 `PromptVariant` objects with the same `run_id`, asserts `get_prompt_variants_for_run(run_id)` returns 2 items.

**`test_schema_migration_runner.py`**:

10. `test_migration_creates_schema_version_table` — open an in-memory connection, run `SchemaMigrationRunner().run_migration(conn)`, query `SELECT version FROM schema_version`, assert value is `2`.
11. `test_migration_is_idempotent` — run migration twice on the same connection; second call must not raise.
12. `test_migration_from_v1_schema` — create a minimal V1 schema (tables `runs` and `results` with only V1 columns, no `schema_version` table), run migration, verify V2 columns (`provider_id`, `ttft_ms`) now exist in the migrated tables by querying `PRAGMA table_info(benchmark_results)`.

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/sq_lite_data_api.py` — `SqLiteDataApi.__init__` takes `db_path: Path`; CRUD method names to test: `create_run`, `get_run`, `update_run_status`, `get_all_runs`, `save_result`, `get_result`, `update_result`, `get_results_for_run`, `upsert_setting`, `get_setting`, `save_prompt_variant`, `get_prompt_variants_for_run`.
- `src/ollama_llm_bench/backend/services/schema_migration_runner.py` — `SchemaMigrationRunner` has `run_migration(conn: sqlite3.Connection) -> None`.
- `src/ollama_llm_bench/backend/core/sql_constants.py` — `MIGRATION_V1_TO_V2` contains the exact `ALTER TABLE` statements; use this to understand the V1 table structure for `test_migration_from_v1_schema`.
- `src/ollama_llm_bench/backend/core/models.py` — `BenchmarkRun`, `BenchmarkResult`, `PromptVariant` dataclass definitions. Construct them with minimum required fields; fields typed `| None` may be left as `None`. Use `uuid.uuid4().hex` for ID fields.

### Implementation Guidance

**`tests/integration/conftest.py`**:
```python
import pytest
from pathlib import Path
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi

@pytest.fixture
def data_api(tmp_path: Path) -> SqLiteDataApi:
    return SqLiteDataApi(tmp_path / "test.db")
```

For **`test_migration_from_v1_schema`**, set up a minimal V1 schema before running migration:
```sql
CREATE TABLE runs (id TEXT PRIMARY KEY, name TEXT, created_at TEXT);
CREATE TABLE results (id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, response TEXT);
```
Then call `SchemaMigrationRunner().run_migration(conn)` and verify:
```python
cursor = conn.execute("PRAGMA table_info(benchmark_results)")
columns = {row[1] for row in cursor.fetchall()}
assert "ttft_ms" in columns
assert "provider_id" in columns
```

### Verification

- [ ] `uv run pytest tests/integration/ -v` passes, showing all 12 tests.
- [ ] No SQL errors in migration test.
- [ ] Integration tests are isolated: each test function gets its own `tmp_path`.

---

## Task 3: Provider Integration Tests with Mock HTTP Server

**Files to create**:
- `tests/integration/test_openai_compatible_provider_http.py`

**Depends on**: Task 1

### Context

The existing `tests/unit/services/providers/test_openai_compatible_provider.py` (838 lines) uses `mocker.Mock` to stub the `openai.OpenAI` client at the Python-object level. Phase 6 requires at least a small set of tests that exercise the real HTTP conversation between `OpenAICompatibleProvider` and a mock server, verifying that the provider correctly serializes requests and parses responses at the wire level. `pytest-httpserver` starts a real `localhost` HTTP server for each test.

### Requirements

1. `test_sync_inference_success` — mock server returns a valid `chat/completions` JSON response; assert `InferenceResponse.content` is populated, `has_error` is `False`, `total_time_ms > 0`.
2. `test_sync_inference_api_error` — mock server returns HTTP 400 with an `{"error": {"message": "bad request"}}` body; assert `InferenceResponse.has_error` is `True` and `InferenceResponse.error_message` is non-empty.
3. `test_stream_inference_yields_chunks` — mock server returns `text/event-stream` SSE response with 3 content delta chunks and a `[DONE]` sentinel; assert `list(provider.inference_stream(...))` returns 3 `StreamChunk` objects with non-empty `content`.
4. `test_get_available_models_success` — mock server returns a `/v1/models` list response; assert the returned list is non-empty and contains `ModelDescriptor` instances.
5. `test_get_available_models_error` — mock server returns HTTP 500; assert an empty list is returned (no exception propagated to caller).

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/providers/openai_compatible_provider.py` — `OpenAICompatibleProvider.__init__` signature: `def __init__(self, *, provider_config: ProviderConfig, model_name_parser: ModelNameParserApi) -> None`. The `ProviderConfig` dataclass (in `models.py`) requires: `id: str`, `type: ProviderType`, `api_key: str`, `base_url: str`, `label: str`, `enabled: bool`, `default_models: list[str]`.
- `src/ollama_llm_bench/backend/services/model_name_parser.py` — `ModelNameParser` has no constructor dependencies; use the real implementation.
- `src/ollama_llm_bench/backend/core/models.py` — `BenchmarkTask` dataclass for constructing a minimal task; `InferenceResponse`, `StreamChunk` for return type assertions.
- `tests/unit/services/providers/test_openai_compatible_provider.py` — see how `ProviderConfig` and `BenchmarkTask` are constructed in existing unit tests to replicate the pattern.

### Implementation Guidance

```python
import pytest
from pytest_httpserver import HTTPServer
from ollama_llm_bench.backend.services.providers.openai_compatible_provider import OpenAICompatibleProvider
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.core.models import (
    ProviderConfig, ProviderType, BenchmarkTask, TaskType, Difficulty, ResponseScope
)

@pytest.fixture
def model_name_parser() -> ModelNameParser:
    return ModelNameParser()

@pytest.fixture
def make_provider(httpserver: HTTPServer, model_name_parser: ModelNameParser):
    """Factory fixture: returns a provider pointed at the mock HTTP server."""
    def _factory() -> OpenAICompatibleProvider:
        config = ProviderConfig(
            id="test",
            type=ProviderType.OPENAI_COMPATIBLE,
            api_key="test-key",
            base_url=httpserver.url_for("/"),
            label="Test",
            enabled=True,
            default_models=[],
        )
        return OpenAICompatibleProvider(provider_config=config, model_name_parser=model_name_parser)
    return _factory
```

**Sync chat response JSON** (for mock server):
```json
{
  "id": "chatcmpl-test",
  "object": "chat.completion",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
}
```

**SSE streaming body** (for mock server, `content_type="text/event-stream"`):
```
data: {"id":"chatcmpl-1","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-1","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}

data: {"id":"chatcmpl-1","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":"stop"}]}

data: [DONE]

```

**Models list response JSON**:
```json
{
  "object": "list",
  "data": [
    {"id": "llama3.2:3b", "object": "model", "owned_by": "library"},
    {"id": "qwen2.5:7b", "object": "model", "owned_by": "library"}
  ]
}
```

Set up mock routes with `httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json(...)`.

Build a minimal `BenchmarkTask` for inference calls:
```python
task = BenchmarkTask(
    task_id="t1", task_type=TaskType.FACTUAL_QA,
    question="What is 2+2?", golden_answer="4",
    difficulty=Difficulty.EASY, response_scope=ResponseScope.EXACT,
    required_terms=None, pass_criteria=None, fail_criteria=None,
)
```

### Verification

- [ ] `uv run pytest tests/integration/test_openai_compatible_provider_http.py -v` — all 5 tests pass.
- [ ] No real network calls made (httpserver received all requests: `httpserver.check_assertions()`).

---

## Task 4: Task Validation CLI Script

**Files to create**:
- `scripts/validate_tasks.py`

**Depends on**: None (pure Python, uses existing services)

### Context

Phase 6 requires a `scripts/validate_tasks.py` tool that task authors and CI can use to verify a YAML task file is well-formed and that the `golden_answer` passes all evaluation layers. If the task has a `fail_example` field, that must produce a FAIL verdict. The `scripts/` directory already exists (contains `ai-check.sh` and `migrate_tasks_v1_to_v2.py`).

### Requirements

1. CLI accepts `validate_tasks.py <yaml_file_or_dir> [--providers-yaml <path>] [--skip-llm-judge]`.
2. Loads task(s) from the provided path using `TaskFileLoader`.
3. For each task, runs the `golden_answer` as the model response through all evaluation layers using real service instances (no mocks).
4. Asserts the pipeline produces a PASS verdict for `golden_answer`.
5. If the task YAML contains a top-level `fail_example` string field, runs it through the pipeline and asserts it produces a FAIL verdict.
6. Prints a `✓` / `✗` line per task with task_id, verdict, and any error reason.
7. Exits with code `0` if all tasks pass, `1` if any fail.
8. `--skip-llm-judge` flag disables Layer 4 (LLMJudgeEvaluator). Default: Layer 4 is attempted if providers.yaml is valid.
9. Must not import any Qt module.

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/task_file_loader.py` — `TaskFileLoader` with `load_tasks(path: Path) -> list[BenchmarkTask]`.
- `src/ollama_llm_bench/backend/services/evaluators/rule_based_evaluator.py` — `RuleBasedEvaluator()` (no deps).
- `src/ollama_llm_bench/backend/services/evaluators/keyword_evaluator.py` — `KeywordEvaluator()` (no deps).
- `src/ollama_llm_bench/backend/services/evaluators/cosine_evaluator.py` — `CosineSimilarityEvaluator(embedding_service=...)`.
- `src/ollama_llm_bench/backend/services/evaluators/llm_judge_evaluator.py` — `LLMJudgeEvaluator(judge_prompt_service=..., provider=..., model_name=...)`.
- `src/ollama_llm_bench/app_context.py` — `_create_app_context()` shows exact instantiation order and constructor signatures for all evaluators. Replicate the evaluator wiring logic from there.
- `src/ollama_llm_bench/backend/core/models.py` — `EvalVerdict`, `EvaluationResult`, `BenchmarkTask`.
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` — see the pipeline stopping logic: stop when any layer returns a non-UNKNOWN verdict.

### Implementation Guidance

Script structure:

```python
#!/usr/bin/env python3
"""Task validation script. Usage: python scripts/validate_tasks.py <path> [--providers-yaml <path>] [--skip-llm-judge]"""

import argparse
import sys
from pathlib import Path

# Ensure src/ is on sys.path when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ollama_llm_bench.backend.services.task_file_loader import TaskFileLoader
from ollama_llm_bench.backend.services.evaluators.rule_based_evaluator import RuleBasedEvaluator
from ollama_llm_bench.backend.services.evaluators.keyword_evaluator import KeywordEvaluator
from ollama_llm_bench.backend.core.models import EvalVerdict, BenchmarkTask

def build_pipeline(*, skip_llm_judge: bool, providers_yaml: Path | None) -> list:
    """Return ordered list of evaluator instances."""
    ...

def validate_task(task: BenchmarkTask, pipeline: list, fail_example: str | None) -> tuple[bool, str]:
    """Run pipeline against golden_answer and optional fail_example. Returns (passed, reason)."""
    ...

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate benchmark task YAML files")
    ...
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
```

The `fail_example` field is not in the `BenchmarkTask` dataclass — it is an optional raw YAML field. Two approaches (pick one):
- **Option A (preferred)**: Add `fail_example: str | None = None` to `BenchmarkTask` in `models.py` so `TaskFileLoader` picks it up automatically.
- **Option B**: Load the raw YAML dict manually alongside `TaskFileLoader` and extract `fail_example` from there.

### Verification

- [ ] `python scripts/validate_tasks.py src/ollama_llm_bench/dataset/ --skip-llm-judge` exits `0` and prints a `✓` per task.
- [ ] Passing a non-existent path exits `1` with a clear error message.
- [ ] `python scripts/validate_tasks.py --help` shows usage.

---

## Task 5: OS-Aware User Data Directory

**Files to create**:
- `src/ollama_llm_bench/backend/core/app_paths.py`
- `tests/unit/core/test_app_paths.py`

**Files to modify**:
- `src/ollama_llm_bench/main.py`

**Depends on**: None

### Context

Currently, `main.py` passes an `app_root` to `ContextProvider.initialize()`. The existing `app_context.py` logic (lines 410–416) already handles:
- `db.sqlite` at `app_root / "db.sqlite"`
- `providers.yaml` at `app_root / "providers.yaml"` with fallback to the bundled package file

The only change required is making `app_root` point to the correct OS-specific user data directory instead of whatever it currently defaults to.

Target directories:
- macOS: `~/Library/Application Support/OllamaLLMBench/`
- Linux: `$XDG_DATA_HOME/OllamaLLMBench/` (fallback: `~/.local/share/OllamaLLMBench/`)
- Windows: `%APPDATA%\OllamaLLMBench\`

No third-party library (e.g., `platformdirs`) should be added — use `sys.platform` and `os.environ` only.

### Requirements

1. New module `src/ollama_llm_bench/backend/core/app_paths.py` with two public functions:
   - `get_user_data_dir() -> Path` — returns the platform-specific directory path, does NOT create it.
   - `ensure_user_data_dir() -> Path` — creates the directory with `mkdir(parents=True, exist_ok=True)` and returns it.
2. `main.py` imports `ensure_user_data_dir` and calls it before `ContextProvider.initialize()`, passing the result as `app_root`.
3. No Qt or third-party imports in `app_paths.py` — stdlib only (`sys`, `os`, `pathlib`).
4. Unit tests at `tests/unit/core/test_app_paths.py` cover all three platforms using `monkeypatch`.

### Existing Code Reference

- `src/ollama_llm_bench/main.py` — find where `ContextProvider.initialize()` is called; determine what is currently passed as `app_root` (likely `Path.cwd()` or similar).
- `src/ollama_llm_bench/app_context.py` lines 410–416 — existing `providers.yaml` fallback logic (already correct, no changes needed here).
- `src/ollama_llm_bench/app_context.py` lines 340–350 — `ContextProvider.initialize(app_root: Path | None, dataset_path: Path | None)` signature.

### Implementation Guidance

**`app_paths.py`**:

```python
"""Platform-specific user data directory resolution for OllamaLLMBench."""
import os
import sys
from pathlib import Path

_APP_NAME: str = "OllamaLLMBench"


def get_user_data_dir() -> Path:
    """Return the OS-specific user data directory for this application.

    - macOS:   ~/Library/Application Support/OllamaLLMBench/
    - Windows: %APPDATA%\\OllamaLLMBench\\
    - Linux:   $XDG_DATA_HOME/OllamaLLMBench/ (default: ~/.local/share/OllamaLLMBench/)
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_NAME
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA") or str(Path.home())
        return Path(app_data) / _APP_NAME
    # Linux and other POSIX
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / _APP_NAME


def ensure_user_data_dir() -> Path:
    """Create and return the user data directory."""
    data_dir = get_user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
```

**`main.py`** change — replace the current `app_root` derivation with:
```python
from ollama_llm_bench.backend.core.app_paths import ensure_user_data_dir
# inside main():
app_root = ensure_user_data_dir()
ContextProvider.initialize(app_root=app_root, dataset_path=dataset_path)
```

**`tests/unit/core/test_app_paths.py`** — use `monkeypatch`:
```python
import sys
import pytest
from pathlib import Path
from ollama_llm_bench.backend.core.app_paths import get_user_data_dir

def test_get_user_data_dir_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = get_user_data_dir()
    assert result == Path.home() / "Library" / "Application Support" / "OllamaLLMBench"

def test_get_user_data_dir_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")
    result = get_user_data_dir()
    assert result == Path("C:\\Users\\test\\AppData\\Roaming") / "OllamaLLMBench"

def test_get_user_data_dir_linux_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = get_user_data_dir()
    assert result == Path.home() / ".local" / "share" / "OllamaLLMBench"

def test_get_user_data_dir_linux_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    result = get_user_data_dir()
    assert result == Path("/custom/data") / "OllamaLLMBench"
```

### Verification

- [ ] `uv run pytest tests/unit/core/test_app_paths.py -v` — all 4 platform tests pass.
- [ ] `uv run mypy src/ollama_llm_bench/backend/core/app_paths.py` — no errors.
- [ ] After running `uv run ollama_llm_bench`, `~/Library/Application Support/OllamaLLMBench/` exists (on macOS).

---

## Task 6: PyInstaller Packaging Configuration

**Files to create**:
- `ollama_llm_bench.spec`
- `scripts/build_macos.sh`
- `scripts/build_linux.sh`
- `scripts/build_windows.ps1`

**Files to modify**:
- `pyproject.toml` (add `pyinstaller` to dev deps)

**Depends on**: Task 5 (app_paths.py must exist before packaging)

### Context

Phase 6.2 requires PyInstaller-based cross-platform packaging. The app bundles PySide6 (large), OpenAI/Anthropic/Google SDKs, PyYAML, and the dataset + QSS theme files. `providers.yaml` is bundled inside the app; the existing fallback logic in `app_context.py` already copies it to the user data directory on first launch. The `.spec` file is the authoritative build configuration; the shell scripts wrap it with platform-specific steps (signing, DMG creation, AppImage wrapping, NSIS).

### Requirements

1. Add `pyinstaller>=6.0` to `[dependency-groups]` `dev` in `pyproject.toml`. Run `uv sync`.
2. `ollama_llm_bench.spec` produces a single-directory bundle (not `--onefile`) for faster startup.
3. Data files bundled: `providers.yaml`, `dataset/` directory, `ui/style/theme_dark.qss`, `ui/style/theme_light.qss`.
4. Hidden imports declared for: `openai`, `openai.types`, `openai.types.chat`, `anthropic`, `anthropic.types`, `google.genai`, `yaml`, `sqlite3`, `logging.handlers`, `PySide6.QtCore`, `PySide6.QtWidgets`, `PySide6.QtGui`, `PySide6.QtSvg`.
5. `scripts/build_macos.sh` — runs PyInstaller, then `hdiutil create` to produce `.dmg`.
6. `scripts/build_linux.sh` — runs PyInstaller; optionally wraps with `appimagetool` if on PATH, otherwise prints instructions.
7. `scripts/build_windows.ps1` — runs PyInstaller; documents NSIS step (not automated).
8. The built app uses `ensure_user_data_dir()` (Task 5) at runtime — no hardcoded paths in the bundle.

### Existing Code Reference

- `src/ollama_llm_bench/main.py` — entry point for the `.spec` `Analysis`.
- `src/ollama_llm_bench/providers.yaml` — must be included as a data file in the bundle.
- `src/ollama_llm_bench/dataset/` — must be included.
- `src/ollama_llm_bench/ui/style/theme_dark.qss`, `theme_light.qss` — must be included.
- `src/ollama_llm_bench/backend/core/app_paths.py` (Task 5) — runtime data dir resolver; already in source before packaging.
- `pyproject.toml` `[tool.hatch.build.targets.wheel]` — shows which files hatch includes; mirror these in the `.spec` `datas` list.

### Implementation Guidance

**`ollama_llm_bench.spec`**:

```python
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

SRC = Path("src/ollama_llm_bench")

datas = [
    (str(SRC / "providers.yaml"), "ollama_llm_bench"),
    (str(SRC / "dataset"), "ollama_llm_bench/dataset"),
    (str(SRC / "ui/style/theme_dark.qss"), "ollama_llm_bench/ui/style"),
    (str(SRC / "ui/style/theme_light.qss"), "ollama_llm_bench/ui/style"),
]

hidden_imports = [
    "openai", "openai.types", "openai.types.chat",
    "anthropic", "anthropic.types",
    "google.genai",
    "yaml", "sqlite3", "logging.handlers",
    "PySide6.QtCore", "PySide6.QtWidgets", "PySide6.QtGui",
    "PySide6.QtSvg", "PySide6.QtOpenGL",
]

a = Analysis(
    ["src/ollama_llm_bench/main.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ollama_llm_bench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True,
               upx_exclude=[], name="ollama_llm_bench")
# macOS: wrap in .app bundle
app = BUNDLE(
    coll,
    name="OllamaLLMBench.app",
    bundle_identifier="com.ollama.llmbench",
    info_plist={"NSHighResolutionCapable": True},
)
```

**`scripts/build_macos.sh`**:
```bash
#!/usr/bin/env bash
set -e
uv run pyinstaller ollama_llm_bench.spec --clean
hdiutil create -volname "OllamaLLMBench" -srcfolder dist/OllamaLLMBench.app \
    -ov -format UDZO dist/OllamaLLMBench.dmg
echo "Built: dist/OllamaLLMBench.dmg"
```

**`scripts/build_linux.sh`**: Run PyInstaller to produce `dist/ollama_llm_bench/`; if `appimagetool` is on PATH, create AppImage. Otherwise print manual AppImage instructions.

**`scripts/build_windows.ps1`**: Run `uv run pyinstaller ollama_llm_bench.spec --clean`; print NSIS packaging instructions (requires NSIS installed separately).

### Verification

- [ ] `uv run pyinstaller ollama_llm_bench.spec --clean` completes without errors.
- [ ] `dist/OllamaLLMBench.app` (macOS) or `dist/ollama_llm_bench/` (Linux) is produced.
- [ ] The built app launches and shows the main window.
- [ ] `providers.yaml` is present inside the bundle.

---

## Task 7: Final Quality Gate and Documentation Update

**Files to modify**:
- `.claude/CLAUDE.md` — update "V2 Non-Negotiable Decisions" and "V2 New Services & Locations" to note Phase 6 complete
- `docs/v2/v2-implementation-plan.md` — mark Phase 6 sections as complete

**Depends on**: Tasks 1–6

### Context

With all tasks complete, run the full quality pipeline to confirm no regressions and that coverage thresholds are met.

### Requirements

1. `./scripts/ai-check.sh` exits `0` (ruff lint, ruff format, pyright, mypy, pytest all pass sequentially).
2. `uv run pytest --cov=src --cov-report=term-missing` shows >= 80% branch coverage.
3. `uv run mypy src/` in strict mode shows 0 errors.
4. CLAUDE.md updated to reflect Phase 6 completion.
5. `scripts/validate_tasks.py` is marked executable (`chmod +x scripts/validate_tasks.py`).

### Implementation Guidance

If `./scripts/ai-check.sh` fails at any step:
- **Ruff lint**: `uv run ruff check --fix src/ tests/` then `uv run ruff format src/ tests/`
- **Mypy**: `uv run mypy src/ --show-error-codes` — fix each error; use the `/fix-types` skill for systematic resolution
- **Coverage < 80%**: `uv run pytest --cov=src --cov-report=term-missing -q` — identify under-covered modules; add parametrized edge-case tests
- **Pytest failures**: `uv run pytest tests/ -v --tb=long` — identify failing tests and fix root cause

### Verification

- [ ] `./scripts/ai-check.sh` exits 0.
- [ ] `uv run pytest --cov=src --cov-report=term-missing -q` — >= 80% coverage, all tests green.
- [ ] `uv run mypy src/` — 0 errors.
- [ ] CLAUDE.md reflects Phase 6 state.
- [ ] `scripts/validate_tasks.py` is executable.

---

## Final Verification Checklist

When all 7 tasks are complete, verify end-to-end:

- [ ] `uv run pytest tests/ -v` — all unit and integration tests pass
- [ ] `./scripts/ai-check.sh` — exits 0
- [ ] `uv run pytest --cov=src --cov-report=term-missing` — >= 80% branch coverage
- [ ] `uv run ollama_llm_bench` — app starts, OS-specific data directory is created, dark theme loads
- [ ] On macOS: `~/Library/Application Support/OllamaLLMBench/` exists after first run
- [ ] `python scripts/validate_tasks.py src/ollama_llm_bench/dataset/ --skip-llm-judge` — exits 0
- [ ] `uv run pyinstaller ollama_llm_bench.spec --clean` — completes without errors
- [ ] No Qt imports in `backend/core/app_paths.py` or any `backend/core/` file
- [ ] All new public functions have strict type annotations
- [ ] Absolute imports only throughout (`from ollama_llm_bench.backend.core.app_paths import ...`)
- [ ] `pytest-qt`, `pytest-httpserver`, `pytest-randomly`, `pyinstaller` present in `pyproject.toml` `[dependency-groups]` `dev`
