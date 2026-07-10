"""The first-run schema DDL and the additive-structural-step scaffold (DD-53).

Source of truth:
``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §4-§6 (every
``CREATE TABLE`` / ``CREATE INDEX`` statement) and §10 (seed data — the ``app_meta``
row only; the three built-in providers are out of scope, owned by STORY-012).
"""

from dataclasses import dataclass
import sqlite3
import threading
from typing import Final

from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.persistence.app_settings.models import EXPECTED_SCHEMA_VERSION

__all__: list[str] = [
    "ADDITIVE_STEPS",
    "CREATE_INDEX_STATEMENTS",
    "CREATE_TABLE_STATEMENTS",
    "SchemaStep",
    "run_first_run_ddl",
]

# --------------------------------------------------------------------------------- #
# CREATE TABLE statements (§4-§5), in FK-dependency order. Every statement uses
# IF NOT EXISTS so a re-run after an interrupted first run is safe.
# --------------------------------------------------------------------------------- #

CREATE_TABLE_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        schema_version  INTEGER NOT NULL CHECK (schema_version >= 1),
        created_at      TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS providers (
        provider_id                   TEXT    PRIMARY KEY,
        name                          TEXT    NOT NULL CHECK (length(name) > 0),
        provider_type                 TEXT    NOT NULL
                                          CHECK (provider_type IN
                                              ('openai_compatible','anthropic','gemini')),
        enabled                       INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
        base_url                      TEXT,
        api_key_raw                   TEXT,
        azure_endpoint_raw            TEXT,
        azure_deployment_raw          TEXT,
        azure_api_version_raw         TEXT,
        last_probe_status             TEXT    NOT NULL DEFAULT 'untested'
                                          CHECK (last_probe_status IN
                                              ('untested','ready','zero_models','unreachable',
                                               'missing_env','testing')),
        last_probe_at                 TEXT,
        last_probe_reachable          INTEGER         CHECK (last_probe_reachable IS NULL
                                                         OR last_probe_reachable IN (0,1)),
        last_probe_model_count        INTEGER         CHECK (last_probe_model_count IS NULL
                                                         OR last_probe_model_count >= 0),
        last_probe_message            TEXT,
        last_inference_test_at        TEXT,
        last_inference_test_outcome   TEXT             CHECK (last_inference_test_outcome IS NULL
                                                         OR last_inference_test_outcome IN
                                                           ('success','reachability_failed',
                                                            'auth_failed','model_not_found',
                                                            'timeout','provider_error','gate_busy')),
        last_inference_test_model     TEXT,
        last_inference_test_message   TEXT,
        provider_order                INTEGER NOT NULL DEFAULT 0 CHECK (provider_order >= 0),
        UNIQUE (name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_models (
        provider_id  TEXT    NOT NULL,
        model_name   TEXT    NOT NULL CHECK (length(model_name) > 0),
        model_order  INTEGER NOT NULL DEFAULT 0 CHECK (model_order >= 0),
        PRIMARY KEY (provider_id, model_name),
        FOREIGN KEY (provider_id) REFERENCES providers (provider_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        setting_key    TEXT PRIMARY KEY CHECK (length(setting_key) > 0),
        setting_value  TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_capabilities (
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_runs (
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
        judge_provider_id       TEXT,
        judge_provider_name     TEXT    CHECK (judge_provider_name IS NULL
                                               OR length(judge_provider_name) > 0),
        embedding_provider_name TEXT    CHECK (embedding_provider_name IS NULL
                                               OR length(embedding_provider_name) > 0),
        embedding_model_name    TEXT    CHECK (embedding_model_name IS NULL
                                               OR length(embedding_model_name) > 0),
        schema_version          INTEGER NOT NULL CHECK (schema_version >= 1),
        created_at              TEXT    NOT NULL,
        started_at              TEXT,
        finished_at             TEXT,
        CHECK ((judge_provider_id IS NULL) = (judge_provider_name IS NULL)),
        CHECK ((embedding_provider_name IS NULL) = (embedding_model_name IS NULL))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_run_models (
        run_id          INTEGER NOT NULL,
        role            TEXT    NOT NULL CHECK (role IN ('test','judge','embedding')),
        provider_id     TEXT    NOT NULL,
        model_name      TEXT    NOT NULL,
        model_family    TEXT,
        model_params_b  REAL    CHECK (model_params_b IS NULL OR model_params_b > 0),
        quantization    TEXT,
        PRIMARY KEY (run_id, role, provider_id, model_name),
        FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_run_providers (
        run_id                 INTEGER NOT NULL,
        provider_id            TEXT    NOT NULL,
        name                   TEXT    NOT NULL CHECK (length(name) > 0),
        provider_type          TEXT    NOT NULL
                                   CHECK (provider_type IN
                                       ('openai_compatible','anthropic','gemini')),
        base_url               TEXT,
        api_key_raw            TEXT,
        azure_endpoint_raw     TEXT,
        azure_deployment_raw   TEXT,
        azure_api_version_raw  TEXT,
        PRIMARY KEY (run_id, provider_id),
        FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_run_settings (
        run_id         INTEGER NOT NULL,
        setting_key    TEXT    NOT NULL CHECK (length(setting_key) > 0),
        setting_value  TEXT    NOT NULL,
        PRIMARY KEY (run_id, setting_key),
        FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_tasks (
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_task_terms (
        run_id      INTEGER NOT NULL,
        task_id     TEXT    NOT NULL,
        term_kind   TEXT    NOT NULL CHECK (term_kind IN ('exact','semantic','forbidden')),
        term_order  INTEGER NOT NULL CHECK (term_order >= 0),
        term_text   TEXT    NOT NULL CHECK (length(term_text) > 0),
        PRIMARY KEY (run_id, task_id, term_kind, term_order),
        FOREIGN KEY (run_id, task_id)
            REFERENCES benchmark_tasks (run_id, task_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_results (
        result_id                INTEGER PRIMARY KEY,
        run_id                   INTEGER NOT NULL,
        task_id                  TEXT    NOT NULL,
        provider_id              TEXT    NOT NULL,
        provider_name            TEXT    NOT NULL CHECK (length(provider_name) > 0),
        model_name               TEXT    NOT NULL,
        status                   TEXT    NOT NULL
                                     CHECK (status IN
                                         ('pending','running_inference','awaiting_keyword_check',
                                          'awaiting_cosine_check','awaiting_judge_check',
                                          'completed','failed_inference','failed_provider',
                                          'failed_timeout','failed_judge_timeout','errored')),
        verdict                  TEXT    CHECK (verdict IS NULL OR verdict IN ('pass','fail')),
        created_at               TEXT    NOT NULL,
        started_at               TEXT,
        finished_at              TEXT,
        system_prompt_sent       TEXT,
        user_prompt_sent         TEXT,
        raw_response             TEXT,
        sanitized_response       TEXT,
        has_thinking_block       INTEGER NOT NULL DEFAULT 0 CHECK (has_thinking_block IN (0,1)),
        response_char_length     INTEGER CHECK (response_char_length IS NULL
                                               OR response_char_length >= 0),
        total_time_ms            INTEGER CHECK (total_time_ms IS NULL OR total_time_ms >= 0),
        ttft_ms                  INTEGER CHECK (ttft_ms IS NULL OR ttft_ms >= 0),
        prompt_tokens            INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
        completion_tokens        INTEGER CHECK (completion_tokens IS NULL
                                               OR completion_tokens >= 0),
        tokens_per_second        REAL    CHECK (tokens_per_second IS NULL
                                               OR tokens_per_second >= 0),
        tokens_estimated         INTEGER NOT NULL DEFAULT 0 CHECK (tokens_estimated IN (0,1)),
        sanity_check_passed      INTEGER CHECK (sanity_check_passed IS NULL
                                               OR sanity_check_passed IN (0,1)),
        keyword_verdict          TEXT    CHECK (keyword_verdict IS NULL
                                               OR keyword_verdict IN ('pass','fail')),
        cosine_similarity        REAL    CHECK (cosine_similarity IS NULL
                                               OR (cosine_similarity >= 0.0
                                                   AND cosine_similarity <= 1.0)),
        cosine_verdict           TEXT    CHECK (cosine_verdict IS NULL
                                               OR cosine_verdict IN ('pass','fail')),
        judge_verdict            TEXT    CHECK (judge_verdict IS NULL
                                               OR judge_verdict IN ('pass','fail')),
        judge_reasoning          TEXT,
        judge_time_ms            INTEGER CHECK (judge_time_ms IS NULL OR judge_time_ms >= 0),
        judge_completion_tokens  INTEGER CHECK (judge_completion_tokens IS NULL
                                               OR judge_completion_tokens >= 0),
        resolution_layer         TEXT    CHECK (resolution_layer IS NULL
                                               OR resolution_layer IN
                                                   ('keyword','cosine','judge','skip')),
        error_kind               TEXT    CHECK (error_kind IS NULL
                                               OR error_kind IN
                                                   ('llm','provider','timeout','judge_timeout',
                                                    'other')),
        error_message            TEXT,
        FOREIGN KEY (run_id) REFERENCES benchmark_runs (run_id) ON DELETE CASCADE,
        FOREIGN KEY (run_id, task_id)
            REFERENCES benchmark_tasks (run_id, task_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_result_terms (
        result_id         INTEGER NOT NULL,
        term_kind         TEXT    NOT NULL
                              CHECK (term_kind IN ('exact_missing','forbidden_found','semantic')),
        term_order        INTEGER NOT NULL CHECK (term_order >= 0),
        term_text         TEXT    NOT NULL CHECK (length(term_text) > 0),
        similarity_score  REAL    CHECK (similarity_score IS NULL
                                         OR (similarity_score >= 0.0 AND similarity_score <= 1.0)),
        PRIMARY KEY (result_id, term_kind, term_order),
        FOREIGN KEY (result_id) REFERENCES benchmark_results (result_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmark_result_attempts (
        result_id      INTEGER NOT NULL,
        attempt_index  INTEGER NOT NULL CHECK (attempt_index >= 1),
        timeout_ms     INTEGER NOT NULL CHECK (timeout_ms >= 0),
        duration_ms    INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
        outcome        TEXT    NOT NULL CHECK (outcome IN ('success','timeout','error')),
        error_kind     TEXT    CHECK (error_kind IS NULL
                                      OR error_kind IN
                                          ('llm','provider','timeout','judge_timeout','other')),
        error_message  TEXT,
        PRIMARY KEY (result_id, attempt_index),
        FOREIGN KEY (result_id) REFERENCES benchmark_results (result_id) ON DELETE CASCADE
    )
    """,
)

# --------------------------------------------------------------------------------- #
# CREATE INDEX statements (§6). Every statement uses IF NOT EXISTS.
# --------------------------------------------------------------------------------- #

CREATE_INDEX_STATEMENTS: Final[tuple[str, ...]] = (
    "CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON benchmark_runs (timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON benchmark_runs (status)",
    "CREATE INDEX IF NOT EXISTS idx_results_run ON benchmark_results (run_id)",
    "CREATE INDEX IF NOT EXISTS idx_results_run_status ON benchmark_results (run_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_results_run_task ON benchmark_results (run_id, task_id)",
    "CREATE INDEX IF NOT EXISTS idx_results_run_model "
    "ON benchmark_results (run_id, provider_id, model_name)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_run ON benchmark_tasks (run_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_terms_task ON benchmark_task_terms (run_id, task_id)",
    "CREATE INDEX IF NOT EXISTS idx_result_terms_result ON benchmark_result_terms (result_id)",
    "CREATE INDEX IF NOT EXISTS idx_result_attempts_result "
    "ON benchmark_result_attempts (result_id)",
    "CREATE INDEX IF NOT EXISTS idx_run_models_run ON benchmark_run_models (run_id, role)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_run_models_one_judge "
    "ON benchmark_run_models (run_id) WHERE role = 'judge'",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_run_models_one_embedding "
    "ON benchmark_run_models (run_id) WHERE role = 'embedding'",
    "CREATE INDEX IF NOT EXISTS idx_run_providers_run ON benchmark_run_providers (run_id)",
    "CREATE INDEX IF NOT EXISTS idx_run_settings_run ON benchmark_run_settings (run_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_caps_model ON model_capabilities (provider_id, model_name)",
    "CREATE INDEX IF NOT EXISTS idx_provider_models_order "
    "ON provider_models (provider_id, model_order)",
)


@dataclass(frozen=True, slots=True)
class SchemaStep:
    """One ordered additive structural step in the schema-evolution ladder (DD-53).

    Strictly private — never crosses this module's boundary, so the
    ``@dataclass`` coding-style exception for private internal types applies
    (never a ``msgspec.Struct``, per ``coding-style.md``).
    """

    from_version: int
    to_version: int
    statements: tuple[str, ...]


# The ordered additive structural steps that bring an older same-major database
# forward to EXPECTED_SCHEMA_VERSION. Empty today because EXPECTED_SCHEMA_VERSION
# starts at 1 — there is no older version yet to evolve from. A future story
# appends SchemaStep entries here (each exactly an ADD COLUMN / CREATE TABLE /
# CREATE INDEX statement) in the same commit that bumps EXPECTED_SCHEMA_VERSION.
ADDITIVE_STEPS: Final[tuple[SchemaStep, ...]] = ()


def run_first_run_ddl(
    write_conn: sqlite3.Connection, lock: threading.Lock, *, clock: Clock
) -> None:
    """Create every table/index and seed the single ``app_meta`` row.

    Runs every ``CREATE TABLE`` then every ``CREATE INDEX`` statement — each
    auto-commits individually under ``isolation_level=None`` and is
    deliberately NOT wrapped in the same transaction as the seed insert (the
    DDL and the seed insert are two separate atomicity units per ADR-0004's
    first-run-atomicity ambiguity resolution). The seed insert then runs in
    its own single ``BEGIN IMMEDIATE`` transaction using ``INSERT OR IGNORE``,
    so re-running this function after an interrupted first run is safe.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.
        clock: The injected time source for ``app_meta.created_at``.
    """
    for statement in CREATE_TABLE_STATEMENTS:
        write_conn.execute(statement)
    for statement in CREATE_INDEX_STATEMENTS:
        write_conn.execute(statement)

    with lock:
        write_conn.execute("BEGIN IMMEDIATE")
        try:
            write_conn.execute(
                "INSERT OR IGNORE INTO app_meta (id, schema_version, created_at) VALUES (1, ?, ?)",
                (EXPECTED_SCHEMA_VERSION, clock.now_utc()),
            )
            write_conn.commit()
        except sqlite3.Error:
            write_conn.rollback()
            raise
