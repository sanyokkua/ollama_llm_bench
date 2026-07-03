# Persistence Schema

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `10_Domain_and_Data/01_DOMAIN_MODEL.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`

This document is the binding SQLite schema for Ollama LLM Bench: the database location, the connection pragmas, the full `CREATE TABLE` statement for every one of the fifteen tables, every index with its rationale, every foreign key with its `ON DELETE` policy, the storage convention, the no-migration schema-versioning rule, and the crash-recovery sweep. It is the contract for the persistence module.

---

## Table of Contents

1. Database location and lifecycle
2. Connection pragmas
3. Storage convention
4. Catalog tables
5. Run-data tables
6. Indexes
7. Foreign keys and cascade policy
8. Schema versioning — additive structural steps; no data migration (DD-53)
9. Crash-recovery sweep
10. Seed data

---

## 1. Database location and lifecycle

The application stores all durable state in a single SQLite database file in the per-OS application data folder:

| OS | Database path |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/ollama_llm_bench.db` |
| Linux | `~/.local/share/OllamaLLMBench/ollama_llm_bench.db` |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\ollama_llm_bench.db` |

WAL mode produces two sidecar files alongside the database — `ollama_llm_bench.db-wal` and `ollama_llm_bench.db-shm` — which SQLite manages automatically.

On first start the application creates the database, runs every `CREATE TABLE` statement in this document, writes the single `app_meta` row, and seeds the built-in catalog data (Section 10). On every subsequent start it opens the existing file and performs the schema-version check (Section 8) followed by the crash-recovery sweep (Section 9). The database file is never migrated and never rewritten in place; it is replaced only by deleting it (which discards all data).

---

## 2. Connection pragmas

Every connection to the database applies these pragmas immediately after opening, before any statement runs.

```sql
PRAGMA journal_mode = WAL;        -- write-ahead logging: background pipeline writes while the UI reads
PRAGMA synchronous = NORMAL;      -- safe under WAL; one fsync per checkpoint, not per commit
PRAGMA busy_timeout = 5000;       -- wait up to 5000 ms for a lock before raising SQLITE_BUSY
PRAGMA foreign_keys = ON;         -- enforce every declared foreign key and ON DELETE CASCADE
PRAGMA temp_store = MEMORY;       -- keep transient B-trees off disk
PRAGMA wal_autocheckpoint = 1000; -- PASSIVE auto-checkpoint every ~1000 WAL pages (~4 MB); the default, set explicitly
PRAGMA journal_size_limit = 67108864; -- write connection only: truncate the -wal back to 64 MB after a checkpoint
```

Rationale:

- **`journal_mode = WAL`** lets the benchmark pipeline write results on a background worker while the UI reads runs and results concurrently, without writer-blocks-reader contention.
- **`synchronous = NORMAL`** is the recommended durability level under WAL: it is safe against application crashes and only risks the last transactions on an operating-system crash or power loss, in exchange for far fewer `fsync` calls.
- **`busy_timeout = 5000`** absorbs the brief contention windows that occur when the pipeline commits while the UI queries, so callers see far fewer `SQLITE_BUSY` errors.
- **`foreign_keys = ON`** must be set per connection (SQLite does not persist it). It enforces the declared foreign keys and the `ON DELETE CASCADE` rules, so deleting a run reliably removes every dependent row.
- **`temp_store = MEMORY`** keeps the transient structures used by sorts and joins in memory.
- **`wal_autocheckpoint = 1000`** (SPEC-039) makes SQLite run a non-blocking **PASSIVE** checkpoint after each commit that crosses ~1000 WAL pages. PASSIVE reclaims only frames older than the oldest live read snapshot, so it depends on readers not pinning the WAL — see §2.2.
- **`journal_size_limit = 67108864`** (SPEC-039, **write connection only**) caps the on-disk `-wal` file: after a checkpoint frees frames, SQLite truncates the file back to 64 MB rather than leaving it at its high-water mark. It bounds disk footprint without affecting correctness.

`journal_mode` is persistent once set on the file; the other pragmas are connection-scoped and are re-applied on every connection — except `journal_size_limit`, which is applied only on the single write connection (it governs how the writer truncates the shared `-wal` file).

### 2.1 Connection topology (DD-41)

The application opens a small, fixed set of connections, each with the pragmas above:

- **Exactly one write connection**, opened by the persistence layer at startup and guarded
  by **one `threading.Lock`** — together these are "the single DB writer". Every store
  write acquires the lock, runs its transaction with `BEGIN IMMEDIATE` (claiming SQLite's
  write lock up front, so a transaction never fails a mid-flight lock upgrade),
  **synchronously on the calling thread**, commits, and releases. A write is durably
  committed when the store call returns; there is no write queue and no back-pressure.
- **Read-only connections** for readers (the UI's queries, chart aggregation snapshots).
  Under WAL they observe the most recent committed snapshot and never block — or are
  blocked by — the writer. **Reads use short-lived read transactions (SPEC-039):** each
  query or aggregation snapshot opens, reads, and closes its own read transaction; no read
  transaction is held open across UI idle or for the span of a run. A large aggregation read
  (tens of MB for a big sweep) is a single bounded read that then closes, releasing its
  snapshot. This is the root-cause guard against unbounded `-wal` growth — because no reader
  pins an old snapshot for long, the PASSIVE auto-checkpoint can always reclaim WAL frames
  while a long run keeps committing.
- **WAL reclamation (SPEC-039).** The single writer additionally issues
  `PRAGMA wal_checkpoint(TRUNCATE)` at **run end** and at **clean shutdown**, hard-reclaiming
  the WAL back to empty at the natural quiescent points. Between those points, the PASSIVE
  auto-checkpoint plus the `journal_size_limit` cap keep the file bounded during the run.
- **Write affinity during a run (DD-38).** Run-domain writes (result rows, the run header)
  are issued only by the dispatcher thread; worker units never write. Outside a run, the
  GUI thread issues only small fast writes (a settings save, a rename), and a worker unit
  (for example a configuration import) writes through the same lock.
- `busy_timeout` remains as defence in depth (e.g. against checkpoint interplay); with a
  single write connection, application-level writer-vs-writer `SQLITE_BUSY` cannot occur.

---

## 3. Storage convention

The schema is fully relational and stores **no JSON blob columns**. Every structured or multi-valued field is decomposed into a dedicated child table with one row per element:

- A run's models, provider snapshot, and settings snapshot are the child tables `benchmark_run_models`, `benchmark_run_providers`, and `benchmark_run_settings`.
- A task's keyword lists are the child table `benchmark_task_terms`.
- A result's per-term keyword outcomes and inference attempts are the child tables `benchmark_result_terms` and `benchmark_result_attempts`.

Consequently every value is an individually addressable, typed, queryable column. There is no opaque structure anywhere in the schema.

Type and value conventions:

| Code shape | SQLite column type | Convention |
|---|---|---|
| `int` | `INTEGER` | direct |
| `float` / `real` | `REAL` | direct |
| `str` | `TEXT` | direct |
| `bool` | `INTEGER` | `1` true, `0` false; `CHECK (col IN (0,1))` |
| enum (`StrEnum`) | `TEXT` | the enum member value string; `CHECK` constraint listing the allowed values |
| timestamp | `TEXT` | ISO-8601 UTC string, for example `2026-05-22T14:53:09Z` |
| optional value | nullable column | SQL `NULL` represents an unset value |
| auto key | `INTEGER PRIMARY KEY` | SQLite rowid alias; auto-increments |

Enum columns carry a `CHECK` constraint enumerating the permitted values, so an out-of-domain string can never be written.

---

## 4. Catalog tables

The six catalog tables hold configuration independent of any run. A run never writes to them.

### 4.1 `app_meta`

```sql
CREATE TABLE app_meta (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version  INTEGER NOT NULL CHECK (schema_version >= 1),
    created_at      TEXT    NOT NULL
);
```

A single-row table (`id` is constrained to `1`) holding the schema generation the file was created with and the database creation time. Written once at database creation; never updated.

### 4.2 `providers`

```sql
CREATE TABLE providers (
    provider_id                   TEXT    PRIMARY KEY,
    name                          TEXT    NOT NULL CHECK (length(name) > 0),
    provider_type                 TEXT    NOT NULL
                                      CHECK (provider_type IN ('openai_compatible','anthropic','gemini')),
    enabled                       INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    base_url                      TEXT,
    api_key_raw                   TEXT,
    azure_endpoint_raw            TEXT,
    azure_deployment_raw          TEXT,
    azure_api_version_raw         TEXT,
    -- Last reachability + discovery probe (LLMClient.probe_health)
    last_probe_status             TEXT    NOT NULL DEFAULT 'untested'
                                      CHECK (last_probe_status IN
                                          ('untested','ready','zero_models','unreachable','missing_env','testing')),
    last_probe_at                 TEXT,
    last_probe_reachable          INTEGER         CHECK (last_probe_reachable IS NULL
                                                     OR last_probe_reachable IN (0,1)),
    last_probe_model_count        INTEGER         CHECK (last_probe_model_count IS NULL
                                                     OR last_probe_model_count >= 0),
    last_probe_message            TEXT,
    -- Last user-initiated end-to-end inference test (LLMClient.test_inference)
    last_inference_test_at        TEXT,
    last_inference_test_outcome   TEXT             CHECK (last_inference_test_outcome IS NULL
                                                     OR last_inference_test_outcome IN
                                                       ('success','reachability_failed','auth_failed',
                                                        'model_not_found','timeout','provider_error','gate_busy')),
    last_inference_test_model     TEXT,
    last_inference_test_message   TEXT,
    provider_order                INTEGER NOT NULL DEFAULT 0 CHECK (provider_order >= 0),
    UNIQUE (name)
);
```

One row per configured LLM provider. The `provider_id` PRIMARY KEY is a UUID4 textual representation (for example `"a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"`) **auto-generated by `ProvidersStore` on insert**; the application never accepts a user-typed identifier (DD-33, `08_Cross_Cutting/08-F_spec_issues_log.md`). The user-entered unique display label is `name` and the `UNIQUE (name)` constraint enforces global uniqueness across the catalog. The `ProvidersStore.add(draft)` path returns the newly-generated `provider_id` to the caller; the `update(provider_id, config)` path mutates `name` (and the other mutable columns) after a pre-check via `get_by_name`. The UI surfaces (Settings table, dropdowns, dialogs, event log, exports) render `name`; only the data layer and event payloads use `provider_id`.

`api_key_raw` stores **only the NAME of an environment variable** (for example `OPENAI_API_KEY`), or empty for a keyless local provider — never a literal secret and never a resolved value (D-R-18, superseding D-R-09). The three `azure_*_raw` columns hold **plain literal configuration values**: `azure_endpoint_raw` is the endpoint URL, `azure_deployment_raw` is the deployment name, and `azure_api_version_raw` is the API version — these are not secrets and are stored as-is. Literal secret values are rejected at entry (Settings editor and import), so `api_key_raw` never contains a credential value; the per-run snapshot copies the env-var name (and the plain azure config) verbatim, and the api-key name is resolved live at run/resume by reading that environment variable from the process environment (unset/empty → provider status `MISSING_ENV`; the resolved value lives only in memory, never on disk). The application layer rejects a literal secret in `api_key_raw` on write (a value that looks like a literal credential rather than an environment-variable name is a `ConfigurationError`). The column NAMES are unchanged for schema stability; only their documented meaning is the env-var name / plain config value.

The two "last test" column sets are deliberately independent: `last_probe_*` carries the outcome of the most recent `LLMClient.probe_health()` (reachability + conditional discovery; never billable), and `last_inference_test_*` carries the outcome of the most recent user-initiated `LLMClient.test_inference()` (one short canned chat call; potentially billable). The Provider Edit dialog reads both on open and writes both on Save when the user has invoked the respective action; either column set may be NULL when the corresponding action has never been performed for this provider. The two sets replace the previous single conflated `last_test_*` triplet — there is no longer a column named `last_test_status`, `last_test_at`, or `last_test_message`.

### 4.3 `provider_models`

```sql
CREATE TABLE provider_models (
    provider_id  TEXT    NOT NULL,
    model_name   TEXT    NOT NULL CHECK (length(model_name) > 0),
    model_order  INTEGER NOT NULL DEFAULT 0 CHECK (model_order >= 0),
    PRIMARY KEY (provider_id, model_name),
    FOREIGN KEY (provider_id) REFERENCES providers (provider_id) ON DELETE CASCADE
);
```

The hand-entered model list for provider types with no model-discovery endpoint. Providers that support discovery leave this empty.

### 4.4 Embedding selection (no table — `app_settings` keys)

Per D-R-13 the embedding feature is **one selected `(provider, embedding model)`**, not a multi-row named catalog, so **there is no `embedding_configs` table**. Embeddings have no user-facing name. The per-provider embedding-model list is **dynamic** — discovered from the provider (or its preconfigured list) at display time — and is **not** persisted; only the last selection is stored, as two `app_settings` keys:

- `embedding.selected_provider_name` — the stable provider **name** (not the UUID, which regenerates on import; see §6 and `06_IMPORT_FORMATS.md`).
- `embedding.selected_model_name` — the embedding model string.

The selection is owned by `AppSettingsStore` (the `app_settings` key/value store, §4.5); there is **no `EmbeddingConfigStore`**. At use time the pair is resolved to a live provider and model and re-validated by the start-up capability probe (`11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` §6.6a). When no embedding selection exists or it fails to resolve, `GRADED` is disabled until the user picks a working `(provider, model)` in Settings. The embedding selection is global configuration (not per-run-overridable, `08_Cross_Cutting/08-C_settings_hierarchy.md` §4); the resolved `(provider, model)` is frozen into the run snapshot at run start as `embedding_provider_name` / `embedding_model_name` (§5.1).

### 4.5 `app_settings`

```sql
CREATE TABLE app_settings (
    setting_key    TEXT PRIMARY KEY CHECK (length(setting_key) > 0),
    setting_value  TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
```

The user-saved layer of the settings hierarchy. One row per setting key the user has changed from its built-in default; numbers and booleans are stored as text. The table starts empty.

### 4.6 `model_capabilities`

```sql
CREATE TABLE model_capabilities (
    provider_id       TEXT    NOT NULL,
    model_name        TEXT    NOT NULL,
    capability        TEXT    NOT NULL
                          CHECK (capability IN ('streaming','reasoning_effort','thinking')),
    supported         INTEGER NOT NULL CHECK (supported IN (-1,0,1)),
    last_observed_at  TEXT    NOT NULL,
    observed_via      TEXT    NOT NULL CHECK (observed_via IN ('probe','inference','manual')),
    detail            TEXT,
    PRIMARY KEY (provider_id, model_name, capability),
    FOREIGN KEY (provider_id) REFERENCES providers (provider_id) ON DELETE CASCADE
);
```

A per-`(provider, model, capability)` cache of probed model capabilities. `supported` is tri-state: `1` supported, `0` not supported, `-1` unknown.

---

## 5. Run-data tables

The nine run-data tables hold the immutable record of each benchmark run. All are write-once or pipeline-written and cascade-delete with their run.

### 5.1 `benchmark_runs`

```sql
CREATE TABLE benchmark_runs (
    run_id                  INTEGER PRIMARY KEY,
    run_name                TEXT,
    timestamp               TEXT    NOT NULL,
    run_mode                TEXT    NOT NULL
                                CHECK (run_mode IN ('synthetic','tasks','graded')),
    status                  TEXT    NOT NULL
                                CHECK (status IN ('incomplete','completed','failed','stopped')),
    total_tasks             INTEGER NOT NULL CHECK (total_tasks >= 0),
    completed_tasks         INTEGER NOT NULL DEFAULT 0
                                CHECK (completed_tasks >= 0 AND completed_tasks <= total_tasks),
    total_elapsed_ms        INTEGER NOT NULL DEFAULT 0 CHECK (total_elapsed_ms >= 0),
    run_analysis            TEXT,
    -- Judge provider snapshot (DD-33): both the FK linkage value and the display-fidelity name snapshot.
    judge_provider_id       TEXT,
    judge_provider_name     TEXT    CHECK (judge_provider_name IS NULL OR length(judge_provider_name) > 0),
    -- Embedding selection snapshot (DD-33): the resolved (provider name, embedding model name) pair, frozen at run start.
    embedding_provider_name TEXT    CHECK (embedding_provider_name IS NULL OR length(embedding_provider_name) > 0),
    embedding_model_name    TEXT    CHECK (embedding_model_name IS NULL OR length(embedding_model_name) > 0),
    schema_version          INTEGER NOT NULL CHECK (schema_version >= 1),
    created_at              TEXT    NOT NULL,
    started_at              TEXT,
    finished_at             TEXT,
    -- Snapshot invariant: judge id/name are paired; the embedding pair is both-or-neither.
    CHECK ((judge_provider_id IS NULL) = (judge_provider_name IS NULL)),
    CHECK ((embedding_provider_name IS NULL) = (embedding_model_name IS NULL))
);
```

One row per run. `status` is constrained to the four persisted values only; the in-memory `RUNNING` and `PAUSED` states are never written here. `run_analysis` is the single consolidated run-level analysis narrative covering every mode. `run_name` is nullable: when null, the effective name is generated from `run_id`, `run_mode`, and `timestamp`.

**Judge provider and embedding selection snapshot (DD-33).** The header carries two snapshots captured at run start: the judge pair `(judge_provider_id, judge_provider_name)` and the embedding pair `(embedding_provider_name, embedding_model_name)`. For the judge, `judge_provider_id` is the FK linkage value (reports and aggregations may follow it to the catalog row) and `judge_provider_name` is the **display-fidelity snapshot** the historical UI renders. For the embedding selection there is no catalog row to link to — the selection lives in `app_settings` as `(provider name, model name)` — so the snapshot stores the resolved **provider name** and **embedding model name** directly, both as display-fidelity snapshots. A later change (the user editing a provider's `name`, or selecting a different embedding model) does not propagate to these frozen columns. Each pair is null when the run did not need that role (for example a `TASKS` run with the analysis toggle OFF has the judge pair null; a run that did not use embedding-based grading has the embedding pair null). The CHECK constraints enforce that each pair is both-or-neither.

The `judge_provider_id` column is intentionally NOT a declared foreign key — historical fidelity requires that a deleted catalog row not cascade onto the run history. The application validates the logical reference at use time. The embedding columns are plain name snapshots with no catalog linkage.

### 5.2 `benchmark_run_models`

```sql
CREATE TABLE benchmark_run_models (
    run_id          INTEGER NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('test','judge','embedding')),
    provider_id     TEXT    NOT NULL,
    model_name      TEXT    NOT NULL,
    model_family    TEXT,
    model_params_b  REAL    CHECK (model_params_b IS NULL OR model_params_b > 0),
    quantization    TEXT,
    PRIMARY KEY (run_id, role, provider_id, model_name),
    FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
);
```

The frozen model snapshot: one `test` row per benchmark target, at most one `judge` row, at most one `embedding` row. Frozen at run creation. The two singleton invariants (at most one `judge`, at most one `embedding`) are enforced by the partial unique indexes `ux_run_models_one_judge` / `ux_run_models_one_embedding` (Section 6, SPEC-038); the `test` role is unconstrained because a run targets many test models.

### 5.3 `benchmark_run_providers`

```sql
CREATE TABLE benchmark_run_providers (
    run_id                 INTEGER NOT NULL,
    provider_id            TEXT    NOT NULL,
    name                   TEXT    NOT NULL CHECK (length(name) > 0),
    provider_type          TEXT    NOT NULL
                               CHECK (provider_type IN ('openai_compatible','anthropic','gemini')),
    base_url               TEXT,
    api_key_raw            TEXT,
    azure_endpoint_raw     TEXT,
    azure_deployment_raw   TEXT,
    azure_api_version_raw  TEXT,
    PRIMARY KEY (run_id, provider_id),
    FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
);
```

The frozen provider snapshot: a verbatim copy of every provider configuration the run references. The pipeline connects through this snapshot. Frozen at run creation. The `name` column is the snapshot of the provider's display name at run start (DD-33); a later rename of the catalog row does not propagate to this column. No `UNIQUE (name)` constraint applies here because the snapshot may include two providers that briefly shared a name on a later catalog rename — uniqueness is an invariant of the live catalog, not of the historical snapshot.

### 5.4 `benchmark_run_settings`

```sql
CREATE TABLE benchmark_run_settings (
    run_id         INTEGER NOT NULL,
    setting_key    TEXT    NOT NULL CHECK (length(setting_key) > 0),
    setting_value  TEXT    NOT NULL,
    PRIMARY KEY (run_id, setting_key),
    FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
);
```

The frozen settings snapshot: one row per per-run-overridable feature flag, evaluation toggle, cosine threshold, timeout parameter, and pipeline-event toggle in effect at Start. Every settings read during the run consults these rows. Frozen at run creation.

### 5.5 `benchmark_tasks`

```sql
CREATE TABLE benchmark_tasks (
    run_id             INTEGER NOT NULL,
    task_id            TEXT    NOT NULL,
    task_origin        TEXT    NOT NULL CHECK (task_origin IN ('file','synthetic')),
    category           TEXT    NOT NULL DEFAULT '',
    sub_category       TEXT    NOT NULL DEFAULT '',
    cosine_enabled     INTEGER NOT NULL DEFAULT 1 CHECK (cosine_enabled IN (0,1)),
    difficulty         TEXT    NOT NULL DEFAULT 'medium'
                           CHECK (difficulty IN ('easy','medium','hard')),
    question           TEXT    NOT NULL CHECK (length(question) > 0),
    golden_answer      TEXT,
    pass_criteria      TEXT    NOT NULL DEFAULT '',
    fail_criteria      TEXT    NOT NULL DEFAULT '',
    source_language    TEXT,
    target_language    TEXT,
    source_material    TEXT,
    fail_example       TEXT,
    input_size_label   TEXT,
    output_size_label  TEXT,
    repeat_index       INTEGER CHECK (repeat_index IS NULL OR repeat_index >= 1),
    task_order         INTEGER NOT NULL DEFAULT 0 CHECK (task_order >= 0),
    PRIMARY KEY (run_id, task_id),
    FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
);
```

A snapshot of every task used by the run, copied in at run creation so the run is independent of the source files. Frozen at run creation.

### 5.6 `benchmark_task_terms`

```sql
CREATE TABLE benchmark_task_terms (
    run_id      INTEGER NOT NULL,
    task_id     TEXT    NOT NULL,
    term_kind   TEXT    NOT NULL CHECK (term_kind IN ('exact','semantic','forbidden')),
    term_order  INTEGER NOT NULL CHECK (term_order >= 0),
    term_text   TEXT    NOT NULL CHECK (length(term_text) > 0),
    PRIMARY KEY (run_id, task_id, term_kind, term_order),
    FOREIGN KEY (run_id, task_id)
        REFERENCES benchmark_tasks (run_id, task_id) ON DELETE CASCADE
);
```

The keyword lists declared by a task, one row per term. A task with no required terms has no rows here. Frozen at run creation.

### 5.7 `benchmark_results`

```sql
CREATE TABLE benchmark_results (
    result_id                INTEGER PRIMARY KEY,
    run_id                   INTEGER NOT NULL,
    task_id                  TEXT    NOT NULL,
    provider_id              TEXT    NOT NULL,
    provider_name            TEXT    NOT NULL CHECK (length(provider_name) > 0),
    model_name               TEXT    NOT NULL,
    status                   TEXT    NOT NULL
                                 CHECK (status IN
                                     ('pending','running_inference','awaiting_keyword_check',
                                      'awaiting_cosine_check','awaiting_judge_check','completed',
                                      'failed_inference','failed_provider','failed_timeout',
                                      'failed_judge_timeout','errored')),
    verdict                  TEXT    CHECK (verdict IS NULL OR verdict IN ('pass','fail')),
    created_at               TEXT    NOT NULL,
    started_at               TEXT,
    finished_at              TEXT,
    system_prompt_sent       TEXT,
    user_prompt_sent         TEXT,
    raw_response             TEXT,
    sanitized_response       TEXT,
    has_thinking_block       INTEGER NOT NULL DEFAULT 0 CHECK (has_thinking_block IN (0,1)),
    response_char_length     INTEGER CHECK (response_char_length IS NULL OR response_char_length >= 0),
    total_time_ms            INTEGER CHECK (total_time_ms IS NULL OR total_time_ms >= 0),
    ttft_ms                  INTEGER CHECK (ttft_ms IS NULL OR ttft_ms >= 0),
    prompt_tokens            INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    completion_tokens        INTEGER CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    tokens_per_second        REAL    CHECK (tokens_per_second IS NULL OR tokens_per_second >= 0),
    tokens_estimated         INTEGER NOT NULL DEFAULT 0 CHECK (tokens_estimated IN (0,1)),
    sanity_check_passed      INTEGER CHECK (sanity_check_passed IS NULL OR sanity_check_passed IN (0,1)),
    keyword_verdict          TEXT    CHECK (keyword_verdict IS NULL OR keyword_verdict IN ('pass','fail')),
    cosine_similarity        REAL    CHECK (cosine_similarity IS NULL
                                            OR (cosine_similarity >= 0.0 AND cosine_similarity <= 1.0)),
    cosine_verdict           TEXT    CHECK (cosine_verdict IS NULL OR cosine_verdict IN ('pass','fail')),
    judge_verdict            TEXT    CHECK (judge_verdict IS NULL OR judge_verdict IN ('pass','fail')),
    judge_reasoning          TEXT,
    judge_time_ms            INTEGER CHECK (judge_time_ms IS NULL OR judge_time_ms >= 0),
    judge_completion_tokens  INTEGER CHECK (judge_completion_tokens IS NULL OR judge_completion_tokens >= 0),
    resolution_layer         TEXT    CHECK (resolution_layer IS NULL
                                            OR resolution_layer IN ('keyword','cosine','judge','skip')),
    error_kind               TEXT    CHECK (error_kind IS NULL
                                            OR error_kind IN ('llm','provider','timeout','judge_timeout','other')),
    error_message            TEXT,
    FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE,
    FOREIGN KEY (run_id, task_id)
        REFERENCES benchmark_tasks (run_id, task_id) ON DELETE CASCADE
);
```

The core run-data table: one row per `(task, provider, model)` combination. `status` and `verdict` are separate columns — `status` is the eleven-value pipeline lifecycle state, `verdict` is the binary `PASS`/`FAIL` quality outcome and is `NULL` until `status` reaches `completed`. `cosine_similarity` is the only numeric quality value (the "Cosine Score"); the judge produces no numeric score. The pipeline never throws — any failure is captured into `status`, `error_kind`, and `error_message`.

**Result → snapshot test-model link (SPEC-038).** Every `benchmark_results` row's `(run_id, provider_id, model_name)` must match a `role = 'test'` row in `benchmark_run_models`. This link is **not a declared foreign key**, by necessity: the same `(provider_id, model_name)` may be snapshotted in two roles in one run (a model used as both a test target and the judge — anonymous judging, `08_Cross_Cutting/08-P_judge_protocol.md`), so `(run_id, provider_id, model_name)` is not unique in `benchmark_run_models` and SQLite cannot FK to "the test row only". The link is instead guaranteed at the source — run creation inserts the initial `pending` result rows only for snapshotted test targets, in the same transaction that writes the model snapshot (`12_Quality_and_NFRs/06_DATA_INTEGRITY.md` §run-creation) — and verified by a data-integrity check plus an architecture test asserting no `benchmark_results` row references a `(run_id, provider_id, model_name)` absent from the run's `test`-role snapshot.

**`provider_id` and `provider_name` (DD-33).** The `provider_id` column is the FK linkage value (the internal UUID4 of the TEST-role provider; stable across rename); the `provider_name` column is the **display-fidelity snapshot** of the provider's name at task start. Historical UI surfaces (the Result widget tabs, exports, the run-log file) render `provider_name`; only the data layer, the live Event Bus events, and aggregations that join on the run-snapshot tables use `provider_id`. A later catalog rename of the provider does not propagate to `provider_name` on already-stored rows. The crash-recovery sweep (Section 9) does not touch `provider_name` — the snapshot is permanent for the lifetime of the row, including across a re-run of the row via the retry path (the re-run uses the snapshot already on the row).

### 5.8 `benchmark_result_terms`

```sql
CREATE TABLE benchmark_result_terms (
    result_id         INTEGER NOT NULL,
    term_kind         TEXT    NOT NULL
                          CHECK (term_kind IN ('exact_missing','forbidden_found','semantic')),
    term_order        INTEGER NOT NULL CHECK (term_order >= 0),
    term_text         TEXT    NOT NULL CHECK (length(term_text) > 0),
    similarity_score  REAL    CHECK (similarity_score IS NULL
                                     OR (similarity_score >= 0.0 AND similarity_score <= 1.0)),
    PRIMARY KEY (result_id, term_kind, term_order),
    FOREIGN KEY (result_id) REFERENCES benchmark_results (result_id) ON DELETE CASCADE
);
```

The per-term outcome of the keyword phase for one result: which exact terms were missing, which forbidden terms appeared, and the similarity of each semantic term. `similarity_score` is set only for `semantic` rows. Populated only when the keyword phase runs; cleared and rewritten on retry.

### 5.9 `benchmark_result_attempts`

```sql
CREATE TABLE benchmark_result_attempts (
    result_id      INTEGER NOT NULL,
    attempt_index  INTEGER NOT NULL CHECK (attempt_index >= 1),
    timeout_ms     INTEGER NOT NULL CHECK (timeout_ms >= 0),
    duration_ms    INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    outcome        TEXT    NOT NULL CHECK (outcome IN ('success','timeout','error')),
    error_kind     TEXT    CHECK (error_kind IS NULL
                                  OR error_kind IN ('llm','provider','timeout','judge_timeout','other')),
    error_message  TEXT,
    PRIMARY KEY (result_id, attempt_index),
    FOREIGN KEY (result_id) REFERENCES benchmark_results (result_id) ON DELETE CASCADE
);
```

One row per inference attempt for a result, recording the adaptive-timeout budget used and the outcome. The number of rows is the result's retry count. Cleared and rewritten on retry.

---

## 6. Indexes

Every index below exists for a specific, recurring query. Primary-key indexes are created implicitly by SQLite and are not repeated here.

```sql
-- benchmark_runs: the Resume widget lists runs newest-first.
CREATE INDEX idx_runs_timestamp        ON benchmark_runs (timestamp DESC);
-- benchmark_runs: the crash-recovery sweep and the Resume widget filter by status.
CREATE INDEX idx_runs_status           ON benchmark_runs (status);

-- benchmark_results: every Result-widget table and chart loads all results for a run.
CREATE INDEX idx_results_run           ON benchmark_results (run_id);
-- benchmark_results: the pipeline and the resume sweep scan a run's results by status.
CREATE INDEX idx_results_run_status    ON benchmark_results (run_id, status);
-- benchmark_results: per-task drill-down and the heatmap join results to their task.
CREATE INDEX idx_results_run_task      ON benchmark_results (run_id, task_id);
-- benchmark_results: per-model aggregation groups on the composite target identity.
CREATE INDEX idx_results_run_model     ON benchmark_results (run_id, provider_id, model_name);

-- benchmark_tasks: the Result widget joins results to tasks for category/difficulty.
CREATE INDEX idx_tasks_run             ON benchmark_tasks (run_id);

-- benchmark_task_terms: the keyword phase loads a task's terms.
CREATE INDEX idx_task_terms_task       ON benchmark_task_terms (run_id, task_id);

-- benchmark_result_terms: the detail panel loads a result's per-term outcomes.
CREATE INDEX idx_result_terms_result   ON benchmark_result_terms (result_id);

-- benchmark_result_attempts: the detail panel loads a result's attempt history.
CREATE INDEX idx_result_attempts_result ON benchmark_result_attempts (result_id);

-- benchmark_run_models: the run loads its frozen model snapshot, often by role.
CREATE INDEX idx_run_models_run        ON benchmark_run_models (run_id, role);

-- benchmark_run_models singletons (SPEC-038): enforce "at most one judge row" and
-- "at most one embedding row" per run at the DB level (was prose-only). Partial unique
-- indexes — the test role is intentionally NOT constrained (a run has many test targets).
CREATE UNIQUE INDEX ux_run_models_one_judge
    ON benchmark_run_models (run_id) WHERE role = 'judge';
CREATE UNIQUE INDEX ux_run_models_one_embedding
    ON benchmark_run_models (run_id) WHERE role = 'embedding';

-- benchmark_run_providers: the run loads its frozen provider snapshot.
CREATE INDEX idx_run_providers_run     ON benchmark_run_providers (run_id);

-- benchmark_run_settings: the run loads its frozen settings snapshot.
CREATE INDEX idx_run_settings_run      ON benchmark_run_settings (run_id);

-- model_capabilities: the capability service queries all capabilities of a model.
CREATE INDEX idx_model_caps_model      ON model_capabilities (provider_id, model_name);

-- provider_models: the Settings dialog loads a provider's manual model list in order.
CREATE INDEX idx_provider_models_order ON provider_models (provider_id, model_order);
```

Index rationale summary:

| Index | Serves |
|---|---|
| `idx_runs_timestamp` | Resume widget run list, newest-first. |
| `idx_runs_status` | Crash-recovery sweep; Resume widget status filter. |
| `idx_results_run` | Loading all results of a run for tables and charts. |
| `idx_results_run_status` | Pipeline scans and the resume sweep over a run's results. |
| `idx_results_run_task` | Per-task drill-down and the task-by-model heatmap. |
| `idx_results_run_model` | Per-model chart aggregation on the composite target key. |
| `idx_tasks_run` | Joining results to tasks for category and difficulty. |
| `idx_task_terms_task` | Keyword phase loading a task's terms. |
| `idx_result_terms_result` | Detail panel loading a result's term outcomes. |
| `idx_result_attempts_result` | Detail panel loading a result's attempt history. |
| `idx_run_models_run` | Loading the run model snapshot, filtered by role. |
| `idx_run_providers_run` | Loading the run provider snapshot. |
| `idx_run_settings_run` | Loading the run settings snapshot. |
| `idx_model_caps_model` | Capability lookup per `(provider, model)`. |
| `idx_provider_models_order` | Ordered manual model list in the Settings dialog. |

---

## 7. Foreign keys and cascade policy

All foreign keys use `ON DELETE CASCADE`. With `PRAGMA foreign_keys = ON`, deleting a parent row removes every dependent row in a single statement.

| Child table | Foreign key | Parent | On delete |
|---|---|---|---|
| `provider_models` | `provider_id` | `providers (provider_id)` | CASCADE |
| `model_capabilities` | `provider_id` | `providers (provider_id)` | CASCADE |
| `benchmark_run_models` | `run_id` | `benchmark_runs (run_id)` | CASCADE |
| `benchmark_run_providers` | `run_id` | `benchmark_runs (run_id)` | CASCADE |
| `benchmark_run_settings` | `run_id` | `benchmark_runs (run_id)` | CASCADE |
| `benchmark_tasks` | `run_id` | `benchmark_runs (run_id)` | CASCADE |
| `benchmark_task_terms` | `(run_id, task_id)` | `benchmark_tasks (run_id, task_id)` | CASCADE |
| `benchmark_results` | `run_id` | `benchmark_runs (run_id)` | CASCADE |
| `benchmark_results` | `(run_id, task_id)` | `benchmark_tasks (run_id, task_id)` | CASCADE |
| `benchmark_result_terms` | `result_id` | `benchmark_results (result_id)` | CASCADE |
| `benchmark_result_attempts` | `result_id` | `benchmark_results (result_id)` | CASCADE |

Deleting a `benchmark_runs` row therefore cascades to all eight of its descendant tables (the three snapshot tables, `benchmark_tasks` and its `benchmark_task_terms`, and `benchmark_results` and its `benchmark_result_terms` and `benchmark_result_attempts`). Deleting a `providers` row cascades to its `provider_models` and `model_capabilities`.

Deliberate non-foreign-keys: the `provider_id` columns in `benchmark_run_providers`, `benchmark_run_models`, and `benchmark_results`, plus the `judge_provider_id` column on `benchmark_runs`, are logical references, not declared foreign keys. They must survive provider deletion — a past run keeps its own frozen snapshot (the FK linkage value plus the display-fidelity name snapshot per DD-33) and remains fully readable even after the catalog row is removed. The application validates these logical references at use time. The `benchmark_runs` embedding columns (`embedding_provider_name`, `embedding_model_name`) are plain frozen name snapshots with no catalog linkage at all.

---

## 8. Schema versioning — additive structural steps; no data migration (DD-53)

The application has no migration framework and performs no backward-compatibility upgrade.

- The application binary embeds a single integer constant, the **expected schema version**.
- The `app_meta.schema_version` column records the version the database file was created with. `benchmark_runs.schema_version` records the version that wrote each run, for diagnostic traceability.
- On every startup, after opening the database, the application reads `app_meta.schema_version` and compares it to the expected version.
- **If they match**, startup continues with the crash-recovery sweep (Section 9).
- **If the stored version is lower and within the same major lineage (DD-53)**, startup applies the ordered **additive structural steps** from the stored version to the expected version — each step one idempotent, single-transaction statement of exactly three permitted kinds: `ALTER TABLE … ADD COLUMN` (nullable or with a `DEFAULT`), `CREATE TABLE`, or `CREATE INDEX` — then updates `app_meta.schema_version` and continues. **No step is ever a data migration or conversion**: no `UPDATE`, no backfill, no transformation, no rewriting of existing rows — existing rows merely acquire the new column's `NULL`/default. A failure mid-step leaves the prior committed steps applied and halts with a hard error naming the failed step.
- **If the stored version is higher than expected, or from a different major lineage**, startup halts with a hard, clearly reported error. The application does not alter the database and does not start the main window. The error message states the stored version, the expected version, and instructs the user that the database is incompatible with this application build.
- **If the database file does not exist**, the application creates it, runs every `CREATE TABLE` and `CREATE INDEX` statement in this document, writes the single `app_meta` row with `schema_version` set to the expected version, and seeds the built-in catalog data (Section 10).

There are no data migrations or conversions (DD-53). Within a major lineage the schema evolves only through the additive structural steps above, recorded in this document as an ordered step list; any non-additive structural change is a new major lineage and a fresh database — existing data is not carried forward across majors.

---

## 9. Crash-recovery sweep

If the application terminates while a run is executing, the persisted state is already self-consistent at the run level — the run's `status` is `incomplete`, because `incomplete` is exactly the status of a created or in-progress run and the in-memory `RUNNING`/`PAUSED` states are never written. There is therefore nothing to sweep on `benchmark_runs`; an interrupted run is correctly `incomplete` and is offered for resume by the Resume widget.

Recovery is required only at the **result level**. A `benchmark_results` row can be left in a non-terminal in-flight status (`running_inference`, `awaiting_keyword_check`, `awaiting_cosine_check`, or `awaiting_judge_check`) when the application died mid-task. Such a row must be reset so the task re-runs cleanly.

The sweep runs once at startup (immediately after the schema-version check passes) and again whenever a run is resumed. It executes inside a single transaction:

```sql
-- Step 1: clear the child rows of every result left mid-flight.
DELETE FROM benchmark_result_terms
WHERE result_id IN (
    SELECT result_id FROM benchmark_results
    WHERE status IN ('running_inference','awaiting_keyword_check',
                      'awaiting_cosine_check','awaiting_judge_check')
);

DELETE FROM benchmark_result_attempts
WHERE result_id IN (
    SELECT result_id FROM benchmark_results
    WHERE status IN ('running_inference','awaiting_keyword_check',
                      'awaiting_cosine_check','awaiting_judge_check')
);

-- Step 2: reset every result left mid-flight back to PENDING and clear its in-flight columns.
UPDATE benchmark_results
SET status                  = 'pending',
    verdict                 = NULL,
    started_at              = NULL,
    finished_at             = NULL,
    system_prompt_sent      = NULL,
    user_prompt_sent        = NULL,
    raw_response            = NULL,
    sanitized_response      = NULL,
    has_thinking_block      = 0,
    response_char_length    = NULL,
    total_time_ms           = NULL,
    ttft_ms                 = NULL,
    prompt_tokens           = NULL,
    completion_tokens       = NULL,
    tokens_per_second       = NULL,
    sanity_check_passed     = NULL,
    keyword_verdict         = NULL,
    cosine_similarity       = NULL,
    cosine_verdict          = NULL,
    judge_verdict           = NULL,
    judge_reasoning         = NULL,
    judge_time_ms           = NULL,
    judge_completion_tokens = NULL,
    resolution_layer        = NULL,
    error_kind              = NULL,
    error_message           = NULL
WHERE status IN ('running_inference','awaiting_keyword_check',
                 'awaiting_cosine_check','awaiting_judge_check');
```

After the sweep, every result is either in a terminal status (`completed` or a terminal-failure) or in `pending`; no result remains in an in-flight status. The run's `completed_tasks` counter is recomputed from the surviving terminal rows when the run is next opened or resumed. Rows already in a terminal status — including the retryable terminal-failure states — are left untouched by the sweep; the user retries those explicitly from the Resume or Retry surface, which separately resets the chosen rows to `pending` and clears their child rows.

---

## 10. Seed data

On first start, after creating the schema, the application writes the following seed data inside a single transaction.

**`app_meta`** — one row: `id = 1`, `schema_version` set to the application's expected version, `created_at` set to the current UTC instant.

**`providers`** — three built-in rows, all `provider_type = 'openai_compatible'`, all `enabled = 1`, no real API key. Each `provider_id` is a fresh UUID4 generated at first start (DD-33); the values below are illustrative:

| `provider_id` (UUID4, generated at seed) | `name` | `base_url` | `provider_order` |
|---|---|---|---|
| e.g. `1f1c0c44-2d8f-4c12-9b8a-b0a1e6c2dc31` | Ollama (local) | `http://localhost:11434/v1` | 0 |
| e.g. `2a9d7e22-7c64-4d39-803b-3f0a91c14b88` | LM Studio (local) | `http://localhost:1234/v1` | 1 |
| e.g. `3b1c8e9d-4a52-4b27-9e84-7d35c8a1ab02` | llama.cpp (local) | `http://localhost:8080/v1` | 2 |

These are ordinary editable rows. The Settings "Reset to Defaults" action deletes all rows from `providers`, `provider_models`, and `app_settings` and re-seeds exactly these three providers (with freshly-generated UUID4 ids). The seed `name` values are unique among the three, satisfying the `UNIQUE (name)` constraint.

**Embedding selection** — no embedding keys at database creation (there is no `embedding_configs` table). On first start the application probes the enabled providers and, if it finds an embedding-capable model, writes the `embedding.selected_provider_name` and `embedding.selected_model_name` `app_settings` keys to that `(provider, model)`; if none is found, the keys are left unset and `GRADED` remains disabled until the user picks a working selection in Settings.

**`app_settings`** — no rows. The table starts empty; every setting key resolves to its built-in default until the user saves a change.

The run-data tables (`benchmark_runs` and its eight descendants) are empty at database creation and receive rows only when the user creates a run.
