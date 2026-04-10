# Benchmark Dataset Format

Every benchmark task lives in a YAML file under `src/ollama_llm_bench/dataset/`.
There are currently **50** task files bundled with the package.
Files are loaded at runtime by `YamlBenchmarkTaskApi` and cached in memory for the life of the process.

## File Layout

Each YAML file contains either a single task **or** a list of tasks.
Both shapes are accepted by the loader.
Convention in the current dataset is one file = one task, wrapped in a top-level list (so the file starts with `- task_id: ...`).

| Parameter | Value |
|---|---|
| Directory | `src/ollama_llm_bench/dataset/` by default; override with `--dataset` / `-d` CLI flag |
| File extensions | `.yaml` and `.yml` (case-sensitive suffix check) |
| Parser | `yaml.safe_load` |
| Shape | Single task `dict` **or** list of task `dict`s |
| Task count | **50** at time of writing (run `ls src/ollama_llm_bench/dataset/*.yaml \| wc -l` to confirm) |

## Schema

Every task must be a mapping with the following fields.
All fields are **required** — missing fields cause the task to be skipped with a warning log (`YamlBenchmarkTaskApi.load_tasks` catches `KeyError`).

```yaml
- task_id: string                       # unique identifier
  category: string                      # high-level category
  sub_category: string                  # subcategory
  question: string                      # prompt shown to the model
  expected_answer:                      # tiered reference answers
    most_expected: string               # tier 1 — ideal (0.85–1.00)
    good_answer: string                 # tier 2 — acceptable (0.65–0.84)
    pass_option: string                 # tier 3 — minimum (0.30–0.64)
  incorrect_direction: string           # negative anchor (≤0.29)
```

### Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | `str` | yes | Unique across all tasks. Used as `task_id` foreign key in the `results` SQL table and referenced by `BenchmarkTask.task_id`. Convention: `<category>_<sub_category>_<short_slug>`. |
| `category` | `str` | yes | Broad category hint passed to the judge as `{category}` in the judge prompt. Used by `SYSTEM_PROMPT` to choose weighting rubric. |
| `sub_category` | `str` | yes | Refinement (e.g. language for coding tasks). Passed as `{sub_category}`. |
| `question` | `str` | yes | The raw question text. Sent **verbatim** to the test model during benchmarking (`SimplePromptBuilderApi.build_prompt` returns it unchanged). Multi-line YAML scalars (`\|` block style) are preferred. |
| `expected_answer.most_expected` | `str` | yes | Tier 1 reference — the ideal answer. If the test model's output exactly matches this (after trivial normalization), the judge should grade **1.00**. |
| `expected_answer.good_answer` | `str` | yes | Tier 2 reference — an acceptable answer with minor misses. Target score **0.65 – 0.95**. |
| `expected_answer.pass_option` | `str` | yes | Tier 3 reference — the bare minimum to pass. Target score **0.30 – 0.79**. |
| `incorrect_direction` | `str` | yes | Negative anchor describing common wrong answers or patterns the judge should penalize. Graded **≤ 0.29**. |

The three tiers plus the negative anchor map to the scoring rubric in `src/ollama_llm_bench/core/prompt_constants.py:SYSTEM_PROMPT` — see [benchmark-pipeline.md](benchmark-pipeline.md#scoring-system) for the full mapping.

## Annotated Example

This is the exact content of `src/ollama_llm_bench/dataset/general_knowledge_literature_orwell_1984.yaml`:

```yaml
- task_id: "general_knowledge_literature_orwell_1984"
  category: "General Knowledge"
  sub_category: "Literature"
  question: |
    What historical event inspired George Orwell's "1984," and what specific
    year did Orwell complete writing the novel, according to his published
    correspondence?
  expected_answer:
    most_expected: |
      George Orwell's "1984" was inspired by the totalitarian regimes of
      Nazi Germany and Stalinist Soviet Union. Orwell completed writing the
      novel in 1948, as confirmed by his published letters.
    good_answer: |
      The rise of fascism and Stalinism inspired "1984," which Orwell
      finished in 1948.
    pass_option: |
      Orwell was inspired by WWII-era dictatorships and completed "1984"
      in 1948.
  incorrect_direction: |
    Incorrect inspiration sources, wrong completion year, or confusing
    with other Orwell works.
```

Key things to note:

- The file contains a **list** with one item (`- task_id: ...`).
- All five text fields use YAML `|` block-scalar syntax to preserve newlines.
- The `pass_option` is genuinely minimal — "WWII-era dictatorships" is vague but accepts the core point.
- `incorrect_direction` names the failure modes without giving specific wrong answers.

## Category Breakdown (Current Dataset)

| Category | Count | Example subcategories |
|---|---|---|
| Coding | 10 | Java, JavaScript, Python, SQL |
| Data Extraction and Transformation | 7 | text→JSON, text→CSV, text→XML, text→Markdown |
| General Knowledge | 9 | AI/LLM concepts, Literature, Tech/Computing, Web |
| Text Operations | 24 | Rephrase (5 tones × 3 languages), Proofreading, Translation |

The categories influence the weights the judge model uses.
See the `Category-specific weights` block in `SYSTEM_PROMPT` (lines 19–25 of `core/prompt_constants.py`).

## Adding a New Task

1. Create a new file under `src/ollama_llm_bench/dataset/` following the naming pattern `<category>_<sub_category>_<slug>.yaml`.
2. Start the file with `- task_id:` (a list containing one task).
3. Fill in all seven fields — no field is optional.
4. Use `|` block scalars for any multi-line content.
5. For the three tiers, keep the quality ordering monotone: `most_expected` > `good_answer` > `pass_option`.
6. The cache is populated on first call to `load_tasks()`, which happens during `NewRunWidgetController.handle_start_click`. You must restart the app to pick up new files (the cache is not invalidated).

### Minimal Template

```yaml
- task_id: "yourcategory_yoursub_yourslug"
  category: "Your Category"
  sub_category: "Your Sub-category"
  question: |
    Write your prompt here. Multi-line is fine.
  expected_answer:
    most_expected: |
      The ideal, complete, correct answer you expect the best model to emit.
    good_answer: |
      An acceptable answer with minor issues.
    pass_option: |
      The minimum the judge should still call a pass.
  incorrect_direction: |
    Describe the wrong shapes the judge should penalize.
```

## Loading Behaviour

`YamlBenchmarkTaskApi.load_tasks()` iterates `task_folder_path.iterdir()`:

1. Skips non-files.
2. Skips files whose suffix is not `.yaml` or `.yml`.
3. Parses each file with `yaml.safe_load`.
4. Treats the result as a single task if it is a `dict`, or a list of tasks if it is a `list`.
5. Constructs a `BenchmarkTask` for each entry; on `KeyError` (missing field) logs a warning and skips.
6. Populates both `self._tasks_cache` (list) and `self._task_cache_map` (dict keyed by `task_id`).
7. Returns the cached list on subsequent calls without re-reading files.

Look-ups via `get_task(task_id)` are O(1) after the first `load_tasks()` call.
The loader does **not** validate uniqueness of `task_id` — a duplicate ID across files will silently overwrite the earlier entry in `_task_cache_map`.

## Dataset Path Resolution

`src/ollama_llm_bench/main.py:get_dataset_path(custom_path)` picks the dataset folder in this order:

1. If `--dataset` / `-d` was passed and the path exists and is a directory, use it.
2. Otherwise try `importlib.resources.path('ollama_llm_bench', 'dataset')` — the packaged location when installed via `uv sync` or a wheel.
3. Otherwise fall back to `Path(__file__).parent / 'dataset'` — the development source tree.

The resolved path is then passed to `ContextProvider.initialize(app_root, dataset_path)` → `_create_app_context` → `YamlBenchmarkTaskApi(task_folder_path=dataset_path)`.

### CLI Example

```bash
# Use the bundled dataset
uv run ollama_llm_bench

# Point at an external dataset folder
uv run ollama_llm_bench --dataset /path/to/my_benchmark_tasks
uv run ollama_llm_bench -d /path/to/my_benchmark_tasks
```

## Validation Failures You Might See

| Scenario | Log output | Outcome |
|---|---|---|
| Missing required field | `Missing required field 'KeyName' in task from <file>` | Task skipped, loading continues |
| Task entry is not a dict | `Skipping invalid task format in <file>` | Entry skipped |
| YAML parse error | `Failed to parse YAML file <file>: <reason>` | File skipped |
| Empty YAML file | `YAML file <file> is empty, skipping` | File skipped |
| Duplicate `task_id` | *(none — silently overwrites)* | Last-write-wins in cache |

## Related Documents

- [data-model.md](data-model.md) — the `BenchmarkTask` / `BenchmarkTaskAnswer` dataclasses
- [benchmark-pipeline.md](benchmark-pipeline.md) — how the judge uses these fields
- [services-reference.md](services-reference.md) — `YamlBenchmarkTaskApi` API reference
- [configuration.md](configuration.md) — the `--dataset` CLI flag
