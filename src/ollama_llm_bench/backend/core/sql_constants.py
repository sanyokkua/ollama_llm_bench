"""V2 SQL constants: DDL schema, migration script, and DML statements for all 5 tables."""

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
  run_id                INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp             TEXT NOT NULL,
  run_mode              TEXT NOT NULL DEFAULT 'full_grading',
  judge_provider_id     TEXT NOT NULL DEFAULT '',
  judge_model           TEXT NOT NULL,
  embedding_provider_id TEXT,
  embedding_model       TEXT,
  status                TEXT NOT NULL,
  task_file_paths       TEXT NOT NULL DEFAULT '[]',
  models_json           TEXT NOT NULL DEFAULT '[]',
  total_tasks           INTEGER NOT NULL DEFAULT 0,
  completed_tasks       INTEGER NOT NULL DEFAULT 0,
  judge_summary         TEXT,
  performance_config    TEXT,
  perf_analysis_result  TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_results (
  result_id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id                 INTEGER NOT NULL REFERENCES benchmark_runs(run_id),
  run_type               TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  completed_at           TEXT,
  provider_id            TEXT NOT NULL DEFAULT '',
  provider_type          TEXT NOT NULL DEFAULT '',
  model_name             TEXT NOT NULL,
  model_family           TEXT,
  model_size_b           REAL,
  quantization_label     TEXT,
  task_id                TEXT NOT NULL,
  task_category          TEXT NOT NULL DEFAULT '',
  task_type              TEXT NOT NULL DEFAULT '',
  task_difficulty        TEXT,
  response_scope         TEXT,
  source_language        TEXT,
  target_language        TEXT,
  prompt_version         TEXT NOT NULL DEFAULT 'v1',
  prompt_hash            TEXT NOT NULL DEFAULT '',
  user_prompt_sent       TEXT NOT NULL DEFAULT '',
  system_prompt_sent     TEXT,
  golden_answer          TEXT NOT NULL DEFAULT '',
  raw_response           TEXT,
  sanitized_response     TEXT,
  response_char_length   INTEGER,
  has_thinking_block     INTEGER NOT NULL DEFAULT 0,
  status                 TEXT NOT NULL DEFAULT 'NOT_COMPLETED',
  total_time_ms          INTEGER,
  ttft_ms                INTEGER,
  prompt_tokens          INTEGER,
  completion_tokens      INTEGER,
  tokens_per_second      REAL,
  rule_check_result      TEXT,
  rule_check_flag        TEXT,
  rule_check_resolved    INTEGER NOT NULL DEFAULT 0,
  keyword_check_result   TEXT,
  missing_exact_terms    TEXT,
  found_forbidden_terms  TEXT,
  semantic_term_scores   TEXT,
  keyword_check_resolved INTEGER NOT NULL DEFAULT 0,
  cosine_similarity      REAL,
  cosine_embedding_model TEXT,
  cosine_strategy        TEXT,
  cosine_auto_pass       INTEGER NOT NULL DEFAULT 0,
  cosine_resolved        INTEGER NOT NULL DEFAULT 0,
  judge_result           TEXT,
  judge_score            REAL,
  judge_reasoning        TEXT,
  judge_prompt_template  TEXT,
  judge_time_ms          INTEGER,
  judge_completion_tokens INTEGER,
  final_verdict          TEXT,
  resolution_layer       TEXT,
  has_inference_error    INTEGER NOT NULL DEFAULT 0,
  inference_error_message TEXT,
  has_judge_error        INTEGER NOT NULL DEFAULT 0,
  judge_error_message    TEXT
);

CREATE TABLE IF NOT EXISTS prompt_variants (
  variant_id           TEXT PRIMARY KEY,
  run_id               INTEGER NOT NULL REFERENCES benchmark_runs(run_id),
  variant_label        TEXT NOT NULL,
  system_prompt        TEXT,
  user_prompt_template TEXT NOT NULL,
  created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# benchmark_runs
# ---------------------------------------------------------------------------

INSERT_BENCHMARK_RUN = """
    INSERT INTO benchmark_runs (
        timestamp, run_mode, judge_provider_id, judge_model,
        embedding_provider_id, embedding_model, status,
        task_file_paths, models_json, total_tasks, completed_tasks,
        judge_summary, performance_config, perf_analysis_result
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_BENCHMARK_RUN_BY_ID = """
    SELECT run_id, timestamp, run_mode, judge_provider_id, judge_model,
           embedding_provider_id, embedding_model, status,
           task_file_paths, models_json, total_tasks, completed_tasks,
           judge_summary, performance_config, perf_analysis_result
    FROM benchmark_runs WHERE run_id = ?
"""

SELECT_ALL_BENCHMARK_RUNS = """
    SELECT run_id, timestamp, run_mode, judge_provider_id, judge_model,
           embedding_provider_id, embedding_model, status,
           task_file_paths, models_json, total_tasks, completed_tasks,
           judge_summary, performance_config, perf_analysis_result
    FROM benchmark_runs
"""

SELECT_BENCHMARK_RUNS_BY_STATUS = """
    SELECT run_id, timestamp, run_mode, judge_provider_id, judge_model,
           embedding_provider_id, embedding_model, status,
           task_file_paths, models_json, total_tasks, completed_tasks,
           judge_summary, performance_config, perf_analysis_result
    FROM benchmark_runs WHERE status = ?
"""

UPDATE_BENCHMARK_RUN = """
    UPDATE benchmark_runs
    SET timestamp = ?, run_mode = ?, judge_provider_id = ?, judge_model = ?,
        embedding_provider_id = ?, embedding_model = ?, status = ?,
        task_file_paths = ?, models_json = ?, total_tasks = ?, completed_tasks = ?,
        judge_summary = ?, performance_config = ?, perf_analysis_result = ?
    WHERE run_id = ?
"""

UPDATE_RUN_PERF_ANALYSIS = """
    UPDATE benchmark_runs SET perf_analysis_result = ? WHERE run_id = ?
"""

DELETE_BENCHMARK_RUN = "DELETE FROM benchmark_runs WHERE run_id = ?"
DELETE_RESULTS_BY_RUN_ID = "DELETE FROM benchmark_results WHERE run_id = ?"
DELETE_PROMPT_VARIANTS_BY_RUN_ID = "DELETE FROM prompt_variants WHERE run_id = ?"

# Migration: add performance columns to benchmark_runs if they do not exist yet
MIGRATE_ADD_PERFORMANCE_COLUMNS = """
    ALTER TABLE benchmark_runs ADD COLUMN performance_config   TEXT;
    ALTER TABLE benchmark_runs ADD COLUMN perf_analysis_result TEXT;
"""

# ---------------------------------------------------------------------------
# benchmark_results
# ---------------------------------------------------------------------------

INSERT_RESULT = """
    INSERT INTO benchmark_results (
        run_id, run_type, created_at, completed_at,
        provider_id, provider_type, model_name, model_family, model_size_b, quantization_label,
        task_id, task_category, task_type, task_difficulty, response_scope,
        source_language, target_language,
        prompt_version, prompt_hash, user_prompt_sent, system_prompt_sent, golden_answer,
        raw_response, sanitized_response, response_char_length, has_thinking_block,
        status, total_time_ms, ttft_ms, prompt_tokens, completion_tokens, tokens_per_second,
        rule_check_result, rule_check_flag, rule_check_resolved,
        keyword_check_result, missing_exact_terms, found_forbidden_terms,
        semantic_term_scores, keyword_check_resolved,
        cosine_similarity, cosine_embedding_model, cosine_strategy,
        cosine_auto_pass, cosine_resolved,
        judge_result, judge_score, judge_reasoning, judge_prompt_template,
        judge_time_ms, judge_completion_tokens,
        final_verdict, resolution_layer,
        has_inference_error, inference_error_message,
        has_judge_error, judge_error_message
    ) VALUES (
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?,
        ?, ?,
        ?, ?, ?,
        ?, ?,
        ?, ?, ?, ?,
        ?, ?,
        ?, ?,
        ?, ?,
        ?, ?
    )
"""

SELECT_RESULT_BY_ID = """
    SELECT result_id, run_id, run_type, created_at, completed_at,
           provider_id, provider_type, model_name, model_family, model_size_b, quantization_label,
           task_id, task_category, task_type, task_difficulty, response_scope,
           source_language, target_language,
           prompt_version, prompt_hash, user_prompt_sent, system_prompt_sent, golden_answer,
           raw_response, sanitized_response, response_char_length, has_thinking_block,
           status, total_time_ms, ttft_ms, prompt_tokens, completion_tokens, tokens_per_second,
           rule_check_result, rule_check_flag, rule_check_resolved,
           keyword_check_result, missing_exact_terms, found_forbidden_terms,
           semantic_term_scores, keyword_check_resolved,
           cosine_similarity, cosine_embedding_model, cosine_strategy,
           cosine_auto_pass, cosine_resolved,
           judge_result, judge_score, judge_reasoning, judge_prompt_template,
           judge_time_ms, judge_completion_tokens,
           final_verdict, resolution_layer,
           has_inference_error, inference_error_message,
           has_judge_error, judge_error_message
    FROM benchmark_results WHERE result_id = ?
"""

SELECT_RESULTS_BY_RUN_ID = """
    SELECT result_id, run_id, run_type, created_at, completed_at,
           provider_id, provider_type, model_name, model_family, model_size_b, quantization_label,
           task_id, task_category, task_type, task_difficulty, response_scope,
           source_language, target_language,
           prompt_version, prompt_hash, user_prompt_sent, system_prompt_sent, golden_answer,
           raw_response, sanitized_response, response_char_length, has_thinking_block,
           status, total_time_ms, ttft_ms, prompt_tokens, completion_tokens, tokens_per_second,
           rule_check_result, rule_check_flag, rule_check_resolved,
           keyword_check_result, missing_exact_terms, found_forbidden_terms,
           semantic_term_scores, keyword_check_resolved,
           cosine_similarity, cosine_embedding_model, cosine_strategy,
           cosine_auto_pass, cosine_resolved,
           judge_result, judge_score, judge_reasoning, judge_prompt_template,
           judge_time_ms, judge_completion_tokens,
           final_verdict, resolution_layer,
           has_inference_error, inference_error_message,
           has_judge_error, judge_error_message
    FROM benchmark_results WHERE run_id = ?
"""

SELECT_RESULTS_BY_RUN_ID_AND_STATUS = """
    SELECT result_id, run_id, run_type, created_at, completed_at,
           provider_id, provider_type, model_name, model_family, model_size_b, quantization_label,
           task_id, task_category, task_type, task_difficulty, response_scope,
           source_language, target_language,
           prompt_version, prompt_hash, user_prompt_sent, system_prompt_sent, golden_answer,
           raw_response, sanitized_response, response_char_length, has_thinking_block,
           status, total_time_ms, ttft_ms, prompt_tokens, completion_tokens, tokens_per_second,
           rule_check_result, rule_check_flag, rule_check_resolved,
           keyword_check_result, missing_exact_terms, found_forbidden_terms,
           semantic_term_scores, keyword_check_resolved,
           cosine_similarity, cosine_embedding_model, cosine_strategy,
           cosine_auto_pass, cosine_resolved,
           judge_result, judge_score, judge_reasoning, judge_prompt_template,
           judge_time_ms, judge_completion_tokens,
           final_verdict, resolution_layer,
           has_inference_error, inference_error_message,
           has_judge_error, judge_error_message
    FROM benchmark_results WHERE run_id = ? AND status = ?
"""

UPDATE_RESULT = """
    UPDATE benchmark_results
    SET run_id = ?, run_type = ?, created_at = ?, completed_at = ?,
        provider_id = ?, provider_type = ?, model_name = ?, model_family = ?,
        model_size_b = ?, quantization_label = ?,
        task_id = ?, task_category = ?, task_type = ?, task_difficulty = ?,
        response_scope = ?, source_language = ?, target_language = ?,
        prompt_version = ?, prompt_hash = ?, user_prompt_sent = ?,
        system_prompt_sent = ?, golden_answer = ?,
        raw_response = ?, sanitized_response = ?, response_char_length = ?,
        has_thinking_block = ?, status = ?,
        total_time_ms = ?, ttft_ms = ?, prompt_tokens = ?,
        completion_tokens = ?, tokens_per_second = ?,
        rule_check_result = ?, rule_check_flag = ?, rule_check_resolved = ?,
        keyword_check_result = ?, missing_exact_terms = ?,
        found_forbidden_terms = ?, semantic_term_scores = ?,
        keyword_check_resolved = ?, cosine_similarity = ?,
        cosine_embedding_model = ?, cosine_strategy = ?,
        cosine_auto_pass = ?, cosine_resolved = ?,
        judge_result = ?, judge_score = ?, judge_reasoning = ?,
        judge_prompt_template = ?, judge_time_ms = ?,
        judge_completion_tokens = ?, final_verdict = ?,
        resolution_layer = ?, has_inference_error = ?,
        inference_error_message = ?, has_judge_error = ?,
        judge_error_message = ?
    WHERE result_id = ?
"""

DELETE_RESULT = "DELETE FROM benchmark_results WHERE result_id = ?"

# ---------------------------------------------------------------------------
# prompt_variants
# ---------------------------------------------------------------------------

INSERT_PROMPT_VARIANT = """
    INSERT INTO prompt_variants (
        variant_id, run_id, variant_label, system_prompt, user_prompt_template, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
"""

SELECT_PROMPT_VARIANTS_BY_RUN_ID = """
    SELECT variant_id, run_id, variant_label, system_prompt, user_prompt_template, created_at
    FROM prompt_variants WHERE run_id = ?
"""

# ---------------------------------------------------------------------------
# app_settings
# ---------------------------------------------------------------------------

UPSERT_APP_SETTING = """
    INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
"""

SELECT_APP_SETTING_BY_KEY = "SELECT key, value, updated_at FROM app_settings WHERE key = ?"

SELECT_ALL_APP_SETTINGS = "SELECT key, value, updated_at FROM app_settings"
