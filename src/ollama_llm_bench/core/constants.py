DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
  run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp    TEXT NOT NULL,
  judge_model  TEXT NOT NULL,
  status       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
  result_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            INTEGER NOT NULL REFERENCES benchmark_runs(run_id),
  task_id           TEXT    NOT NULL,
  model_name        TEXT    NOT NULL,
  status            TEXT    NOT NULL,
  llm_response      TEXT,
  time_taken_ms     INTEGER,
  tokens_generated  INTEGER,
  evaluation_score  REAL,
  evaluation_reason TEXT,
  error_message     TEXT
);
"""
INSERT_BENCHMARK_RUN = "INSERT INTO benchmark_runs (timestamp, judge_model, status) VALUES (?, ?, ?)"
SELECT_BENCHMARK_RUN_BY_ID = "SELECT run_id, timestamp, judge_model, status FROM benchmark_runs WHERE run_id = ?"
SELECT_ALL_BENCHMARK_RUNS = "SELECT run_id, timestamp, judge_model, status FROM benchmark_runs"
SELECT_BENCHMARK_RUNS_BY_STATUS = "SELECT run_id, timestamp, judge_model, status FROM benchmark_runs WHERE status = ?"
UPDATE_BENCHMARK_RUN = "UPDATE benchmark_runs SET timestamp = ?, judge_model = ?, status = ? WHERE run_id = ?"
DELETE_BENCHMARK_RUN = "DELETE FROM benchmark_runs WHERE run_id = ?"

INSERT_RESULT = """
        INSERT INTO results (
            run_id, task_id, model_name, status, llm_response,
            time_taken_ms, tokens_generated, evaluation_score,
            evaluation_reason, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
SELECT_RESULT_BY_ID = """
        SELECT result_id, run_id, task_id, model_name, status, 
               llm_response, time_taken_ms, tokens_generated,
               evaluation_score, evaluation_reason, error_message
        FROM results WHERE result_id = ?
    """
SELECT_RESULTS_BY_RUN_ID = """
        SELECT result_id, run_id, task_id, model_name, status, 
               llm_response, time_taken_ms, tokens_generated,
               evaluation_score, evaluation_reason, error_message
        FROM results WHERE run_id = ?
    """
SELECT_RESULTS_BY_RUN_ID_AND_STATUS = """
        SELECT result_id, run_id, task_id, model_name, status, 
               llm_response, time_taken_ms, tokens_generated,
               evaluation_score, evaluation_reason, error_message
        FROM results WHERE run_id = ? AND status = ?
    """
UPDATE_RESULT = """
        UPDATE results SET run_id = ?, task_id = ?, model_name = ?, 
               status = ?, llm_response = ?, time_taken_ms = ?, 
               tokens_generated = ?, evaluation_score = ?, 
               evaluation_reason = ?, error_message = ? WHERE result_id = ?
    """
DELETE_RESULT = "DELETE FROM results WHERE result_id = ?"
