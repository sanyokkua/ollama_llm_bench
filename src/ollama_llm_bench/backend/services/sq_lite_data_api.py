"""SQLite-backed implementation of DataApi for V2 benchmark data persistence."""

import contextlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from ollama_llm_bench.backend.core.interfaces import DataApi
from ollama_llm_bench.backend.core.models import (
    AppSetting,
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    EmbeddingConfig,
    PromptVariant,
    ProviderConfig,
    ProviderType,
    RunMode,
)
from ollama_llm_bench.backend.core.sql_constants import (
    CREATE_EMBEDDING_CONFIG_TABLE,
    CREATE_INDEX_RUN_NAME_UNIQUE,
    CREATE_MODEL_CAPABILITIES_TABLE,
    CREATE_PROVIDERS_TABLE,
    DB_SCHEMA,
    DELETE_BENCHMARK_RUN,
    DELETE_PROMPT_VARIANTS_BY_RUN_ID,
    DELETE_PROVIDER,
    DELETE_RESULT,
    DELETE_RESULTS_BY_RUN_ID,
    INSERT_BENCHMARK_RUN,
    INSERT_PROMPT_VARIANT,
    INSERT_RESULT,
    MIGRATE_ADD_PERFORMANCE_COLUMNS,
    MIGRATE_ADD_RUN_NAME,
    MIGRATE_FIX_COMPLETED_WITH_NON_TERMINAL_RESULTS,
    MIGRATE_PROMPT_VARIANTS_COMPOSITE_PK,
    SELECT_ALL_APP_SETTINGS,
    SELECT_ALL_BENCHMARK_RUNS,
    SELECT_ALL_PROVIDERS,
    SELECT_APP_SETTING_BY_KEY,
    SELECT_BENCHMARK_RUN_BY_ID,
    SELECT_BENCHMARK_RUNS_BY_STATUS,
    SELECT_EMBEDDING_CONFIG,
    SELECT_MODEL_CAPABILITY,
    SELECT_PROMPT_VARIANTS_BY_RUN_ID,
    SELECT_PROVIDERS_COUNT,
    SELECT_RESULT_BY_ID,
    SELECT_RESULTS_BY_RUN_ID,
    SELECT_RESULTS_BY_RUN_ID_AND_STATUS,
    SELECT_STATUS_COUNTS_BY_RUN_ID,
    UPDATE_BENCHMARK_RUN,
    UPDATE_PROVIDER_TEST_STATUS,
    UPDATE_RESULT,
    UPDATE_RUN_NAME,
    UPDATE_RUN_PERF_ANALYSIS,
    UPSERT_APP_SETTING,
    UPSERT_EMBEDDING_CONFIG,
    UPSERT_MODEL_CAPABILITY,
    UPSERT_PROVIDER,
)

logger = logging.getLogger(__name__)


class SqLiteDataApi(DataApi):
    """SQLite-based implementation of DataApi for persistent storage of V2 benchmark data.

    Uses a local SQLite database with foreign keys enabled.  All rows are
    accessed via sqlite3.Row for named-column access.  Schema creation is
    applied automatically at construction time.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the SQLite data access layer and ensure the schema is current.

        Args:
            db_path: Path to the SQLite database file; parent directories are
                created if absent.
        """
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Open a connection with Row factory and foreign-key enforcement.

        Returns:
            Configured sqlite3 Connection.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """Create the V2 schema tables if absent and seed the schema version row."""
        logger.debug("Initializing database schema at %s", self._db_path)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(DB_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (2, datetime.now(UTC).isoformat()),
            )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE benchmark_runs ADD COLUMN judge_summary TEXT")
            for stmt in MIGRATE_ADD_PERFORMANCE_COLUMNS.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    with contextlib.suppress(sqlite3.OperationalError):
                        conn.execute(stmt)
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(MIGRATE_ADD_RUN_NAME)
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(CREATE_INDEX_RUN_NAME_UNIQUE)
            conn.execute(CREATE_MODEL_CAPABILITIES_TABLE)
            with contextlib.suppress(Exception):
                conn.execute(MIGRATE_FIX_COMPLETED_WITH_NON_TERMINAL_RESULTS)
            conn.execute(CREATE_PROVIDERS_TABLE)
            with contextlib.suppress(Exception):
                conn.executescript(MIGRATE_PROMPT_VARIANTS_COMPOSITE_PK)
            conn.execute(CREATE_EMBEDDING_CONFIG_TABLE)
            self._migrate_providers_test_status(conn)

    def _migrate_providers_test_status(self, conn: sqlite3.Connection) -> None:
        """Add last_test_status/at/message columns to providers if they do not yet exist."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(providers)")}
        for col in ("last_test_status", "last_test_at", "last_test_message"):
            if col not in existing:
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(f"ALTER TABLE providers ADD COLUMN {col} TEXT")

    def _row_to_benchmark_run(self, row: sqlite3.Row) -> BenchmarkRun:
        """Build a BenchmarkRun from a sqlite3.Row using named column access.

        Args:
            row: Row returned from a benchmark_runs query.

        Returns:
            Populated BenchmarkRun dataclass instance.
        """
        task_file_paths: tuple[str, ...] = tuple(json.loads(row["task_file_paths"] or "[]"))
        return BenchmarkRun(
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            run_mode=RunMode(row["run_mode"] or "full_grading"),
            judge_provider_id=row["judge_provider_id"] or "",
            judge_model=row["judge_model"],
            embedding_provider_id=row["embedding_provider_id"],
            embedding_model=row["embedding_model"],
            status=BenchmarkRunStatus(row["status"]),
            task_file_paths=task_file_paths,
            models_json=row["models_json"] or "[]",
            total_tasks=row["total_tasks"] or 0,
            completed_tasks=row["completed_tasks"] or 0,
            judge_summary=row["judge_summary"],
            performance_config=row["performance_config"],
            perf_analysis_result=row["perf_analysis_result"],
            run_name=row["run_name"],
        )

    def _row_to_benchmark_result(self, row: sqlite3.Row) -> BenchmarkResult:
        """Build a BenchmarkResult from a sqlite3.Row using named column access.

        Integer-stored booleans are converted to Python bool.

        Args:
            row: Row returned from a benchmark_results query.

        Returns:
            Populated BenchmarkResult dataclass instance.
        """
        return BenchmarkResult(
            result_id=row["result_id"],
            run_id=row["run_id"],
            run_type=row["run_type"] or "",
            created_at=row["created_at"] or "",
            completed_at=row["completed_at"],
            provider_id=row["provider_id"] or "",
            provider_type=row["provider_type"] or "",
            model_name=row["model_name"],
            model_family=row["model_family"],
            model_size_b=row["model_size_b"],
            quantization_label=row["quantization_label"],
            task_id=row["task_id"],
            task_category=row["task_category"] or "",
            task_type=row["task_type"] or "",
            task_difficulty=row["task_difficulty"],
            response_scope=row["response_scope"],
            source_language=row["source_language"],
            target_language=row["target_language"],
            prompt_version=row["prompt_version"] or "v1",
            prompt_hash=row["prompt_hash"] or "",
            user_prompt_sent=row["user_prompt_sent"] or "",
            system_prompt_sent=row["system_prompt_sent"],
            golden_answer=row["golden_answer"] or "",
            raw_response=row["raw_response"],
            sanitized_response=row["sanitized_response"],
            response_char_length=row["response_char_length"],
            has_thinking_block=bool(row["has_thinking_block"]),
            status=BenchmarkResultStatus(row["status"] or "NOT_COMPLETED"),
            total_time_ms=row["total_time_ms"],
            ttft_ms=row["ttft_ms"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            tokens_per_second=row["tokens_per_second"],
            rule_check_result=row["rule_check_result"],
            rule_check_flag=row["rule_check_flag"],
            rule_check_resolved=bool(row["rule_check_resolved"]),
            keyword_check_result=row["keyword_check_result"],
            missing_exact_terms=row["missing_exact_terms"],
            found_forbidden_terms=row["found_forbidden_terms"],
            semantic_term_scores=row["semantic_term_scores"],
            keyword_check_resolved=bool(row["keyword_check_resolved"]),
            cosine_similarity=row["cosine_similarity"],
            cosine_embedding_model=row["cosine_embedding_model"],
            cosine_strategy=row["cosine_strategy"],
            cosine_auto_pass=bool(row["cosine_auto_pass"]),
            cosine_resolved=bool(row["cosine_resolved"]),
            judge_result=row["judge_result"],
            judge_score=row["judge_score"],
            judge_reasoning=row["judge_reasoning"],
            judge_prompt_template=row["judge_prompt_template"],
            judge_time_ms=row["judge_time_ms"],
            judge_completion_tokens=row["judge_completion_tokens"],
            final_verdict=row["final_verdict"],
            resolution_layer=row["resolution_layer"],
            has_inference_error=bool(row["has_inference_error"]),
            inference_error_message=row["inference_error_message"],
            has_judge_error=bool(row["has_judge_error"]),
            judge_error_message=row["judge_error_message"],
        )

    # ------------------------------------------------------------------
    # BenchmarkRun CRUD
    # ------------------------------------------------------------------

    @override
    def create_benchmark_run(self, benchmark_run: BenchmarkRun) -> int:
        """Store a new benchmark run and return its assigned row ID.

        Args:
            benchmark_run: The benchmark run to persist.

        Returns:
            Unique integer ID assigned to the created run.

        Raises:
            RuntimeError: If the INSERT returns no lastrowid.
        """
        logger.debug("Creating benchmark run: timestamp=%s", benchmark_run.timestamp)
        task_file_paths_json = json.dumps(list(benchmark_run.task_file_paths))
        with self._get_connection() as conn:
            cursor = conn.execute(
                INSERT_BENCHMARK_RUN,
                (
                    benchmark_run.timestamp,
                    benchmark_run.run_mode,
                    benchmark_run.judge_provider_id,
                    benchmark_run.judge_model,
                    benchmark_run.embedding_provider_id,
                    benchmark_run.embedding_model,
                    benchmark_run.status,
                    task_file_paths_json,
                    benchmark_run.models_json,
                    benchmark_run.total_tasks,
                    benchmark_run.completed_tasks,
                    benchmark_run.judge_summary,
                    benchmark_run.performance_config,
                    benchmark_run.perf_analysis_result,
                    benchmark_run.run_name,
                ),
            )
            run_id = cursor.lastrowid
        if run_id is None:
            raise RuntimeError("INSERT_BENCHMARK_RUN returned no lastrowid — database invariant violated.")
        logger.info("Created benchmark run with ID %d", run_id)
        return run_id

    @override
    def retrieve_benchmark_run(self, run_id: int) -> BenchmarkRun:
        """Fetch a specific benchmark run by its identifier.

        Args:
            run_id: Unique ID of the run to retrieve.

        Returns:
            The requested BenchmarkRun instance.

        Raises:
            ValueError: If no run with the given ID exists.
        """
        logger.debug("Retrieving benchmark run with ID %d", run_id)
        with self._get_connection() as conn:
            row = conn.execute(SELECT_BENCHMARK_RUN_BY_ID, (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Benchmark run with ID {run_id} not found")
        return self._row_to_benchmark_run(row)

    @override
    def retrieve_benchmark_runs(self) -> list[BenchmarkRun]:
        """Retrieve all stored benchmark runs.

        Returns:
            List of all BenchmarkRun records; empty if none exist.
        """
        logger.debug("Retrieving all benchmark runs")
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_ALL_BENCHMARK_RUNS).fetchall()
        results = [self._row_to_benchmark_run(row) for row in rows]
        logger.debug("Retrieved %d benchmark runs", len(results))
        return results

    @override
    def retrieve_benchmark_runs_with_status(self, status: BenchmarkRunStatus) -> list[BenchmarkRun]:
        """Retrieve benchmark runs filtered by execution status.

        Args:
            status: Status to filter runs by.

        Returns:
            List of BenchmarkRun records matching the given status.
        """
        logger.debug("Retrieving benchmark runs with status %s", status)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_BENCHMARK_RUNS_BY_STATUS, (status,)).fetchall()
        results = [self._row_to_benchmark_run(row) for row in rows]
        logger.debug("Retrieved %d runs with status %s", len(results), status)
        return results

    @override
    def update_benchmark_run(self, benchmark_run: BenchmarkRun) -> None:
        """Update an existing benchmark run in storage.

        Args:
            benchmark_run: The updated BenchmarkRun instance.
        """
        logger.debug("Updating benchmark run ID %d", benchmark_run.run_id)
        task_file_paths_json = json.dumps(list(benchmark_run.task_file_paths))
        with self._get_connection() as conn:
            conn.execute(
                UPDATE_BENCHMARK_RUN,
                (
                    benchmark_run.timestamp,
                    benchmark_run.run_mode,
                    benchmark_run.judge_provider_id,
                    benchmark_run.judge_model,
                    benchmark_run.embedding_provider_id,
                    benchmark_run.embedding_model,
                    benchmark_run.status,
                    task_file_paths_json,
                    benchmark_run.models_json,
                    benchmark_run.total_tasks,
                    benchmark_run.completed_tasks,
                    benchmark_run.judge_summary,
                    benchmark_run.performance_config,
                    benchmark_run.perf_analysis_result,
                    benchmark_run.run_name,
                    benchmark_run.run_id,
                ),
            )
        logger.info("Updated benchmark run with ID %d", benchmark_run.run_id)

    @override
    def delete_benchmark_run(self, run_id: int) -> None:
        """Remove a benchmark run from storage.

        Args:
            run_id: Unique ID of the run to delete.
        """
        logger.debug("Deleting benchmark run with ID %d", run_id)
        with self._get_connection() as conn:
            conn.execute(DELETE_PROMPT_VARIANTS_BY_RUN_ID, (run_id,))
            conn.execute(DELETE_RESULTS_BY_RUN_ID, (run_id,))
            cursor = conn.execute(DELETE_BENCHMARK_RUN, (run_id,))
            affected = cursor.rowcount
        if affected == 0:
            logger.warning("No benchmark run found with ID %d to delete", run_id)
        else:
            logger.info("Deleted benchmark run with ID %d", run_id)

    def update_run_perf_analysis(self, *, run_id: int, analysis: str) -> None:
        """Persist the LLM-generated performance analysis text for a finished run.

        Args:
            run_id: Unique ID of the benchmark run.
            analysis: Analysis text produced by the judge LLM.
        """
        logger.debug("Storing perf analysis for run_id=%d", run_id)
        with self._get_connection() as conn:
            conn.execute(UPDATE_RUN_PERF_ANALYSIS, (analysis, run_id))
        logger.info("Stored perf analysis for run_id=%d", run_id)

    @override
    def update_run_name(self, *, run_id: int, run_name: str) -> None:
        """Persist a user-supplied display name for a benchmark run.

        Args:
            run_id: Unique ID of the benchmark run.
            run_name: New display name for the run.
        """
        logger.debug("Updating run_name for run_id=%d", run_id)
        with self._get_connection() as conn:
            conn.execute(UPDATE_RUN_NAME, (run_name, run_id))
        logger.info("Updated run_name for run_id=%d", run_id)

    # ------------------------------------------------------------------
    # BenchmarkResult CRUD
    # ------------------------------------------------------------------

    @override
    def create_benchmark_result(self, benchmark_result: BenchmarkResult) -> int:
        """Store a single benchmark result and return its assigned row ID.

        Args:
            benchmark_result: The result to persist.

        Returns:
            Unique integer ID assigned to the created result.

        Raises:
            RuntimeError: If the INSERT returns no lastrowid.
        """
        logger.debug(
            "Creating benchmark result for run_id=%d task_id=%s", benchmark_result.run_id, benchmark_result.task_id
        )
        with self._get_connection() as conn:
            cursor = conn.execute(INSERT_RESULT, self._result_to_params(benchmark_result))
            result_id = cursor.lastrowid
        if result_id is None:
            raise RuntimeError("INSERT_RESULT returned no lastrowid — database invariant violated.")
        logger.info("Created benchmark result with ID %d", result_id)
        return result_id

    @override
    def create_benchmark_results(self, benchmark_result: list[BenchmarkResult]) -> None:
        """Store multiple benchmark results in bulk.

        Args:
            benchmark_result: List of results to persist.
        """
        logger.debug("Creating %d benchmark results", len(benchmark_result))
        with self._get_connection() as conn:
            for result in benchmark_result:
                conn.execute(INSERT_RESULT, self._result_to_params(result))
        logger.info("Created %d benchmark results", len(benchmark_result))

    @override
    def retrieve_benchmark_result(self, result_id: int) -> BenchmarkResult:
        """Fetch a specific benchmark result by its identifier.

        Args:
            result_id: Unique ID of the result to retrieve.

        Returns:
            The requested BenchmarkResult instance.

        Raises:
            ValueError: If no result with the given ID exists.
        """
        logger.debug("Retrieving benchmark result with ID %d", result_id)
        with self._get_connection() as conn:
            row = conn.execute(SELECT_RESULT_BY_ID, (result_id,)).fetchone()
        if row is None:
            raise ValueError(f"Benchmark result with ID {result_id} not found")
        return self._row_to_benchmark_result(row)

    @override
    def retrieve_benchmark_results_for_run(self, run_id: int) -> list[BenchmarkResult]:
        """Retrieve all results associated with a specific benchmark run.

        Args:
            run_id: Unique ID of the parent benchmark run.

        Returns:
            List of BenchmarkResult records belonging to the run; empty if none exist.
        """
        logger.debug("Retrieving results for run ID %d", run_id)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_RESULTS_BY_RUN_ID, (run_id,)).fetchall()
        results = [self._row_to_benchmark_result(row) for row in rows]
        logger.debug("Retrieved %d results for run ID %d", len(results), run_id)
        return results

    @override
    def retrieve_benchmark_results_for_run_with_status(
        self, *, run_id: int, status: BenchmarkResultStatus
    ) -> list[BenchmarkResult]:
        """Retrieve benchmark results for a run, filtered by status.

        Args:
            run_id: Unique ID of the parent benchmark run.
            status: Status to filter results by.

        Returns:
            List of BenchmarkResult records matching the run ID and status.
        """
        logger.debug("Retrieving results for run ID %d with status %s", run_id, status)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_RESULTS_BY_RUN_ID_AND_STATUS, (run_id, status)).fetchall()
        results = [self._row_to_benchmark_result(row) for row in rows]
        logger.debug("Retrieved %d results for run ID %d with status %s", len(results), run_id, status)
        return results

    @override
    def retrieve_status_counts_for_run(self, run_id: int) -> dict[str, int]:
        """Return a mapping of status value → row count for the given run.

        Args:
            run_id: Benchmark run to aggregate.

        Returns:
            Dict mapping BenchmarkResultStatus string values to their counts.
        """
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_STATUS_COUNTS_BY_RUN_ID, (run_id,)).fetchall()
        return dict(rows)

    @override
    def update_benchmark_result(self, benchmark_result: BenchmarkResult) -> None:
        """Update an existing benchmark result in storage.

        Args:
            benchmark_result: The updated BenchmarkResult instance.
        """
        logger.debug("Updating benchmark result ID %d", benchmark_result.result_id)
        params = self._result_to_update_params(benchmark_result)
        with self._get_connection() as conn:
            conn.execute(UPDATE_RESULT, params)
        logger.info("Updated benchmark result with ID %d", benchmark_result.result_id)

    @override
    def delete_benchmark_result(self, result_id: int) -> None:
        """Remove a benchmark result from storage.

        Args:
            result_id: Unique ID of the result to delete.
        """
        logger.debug("Deleting benchmark result with ID %d", result_id)
        with self._get_connection() as conn:
            cursor = conn.execute(DELETE_RESULT, (result_id,))
            affected = cursor.rowcount
        if affected == 0:
            logger.warning("No benchmark result found with ID %d to delete", result_id)
        else:
            logger.info("Deleted benchmark result with ID %d", result_id)

    # ------------------------------------------------------------------
    # AppSettings
    # ------------------------------------------------------------------

    @override
    def get_app_setting(self, key: str) -> AppSetting | None:
        """Retrieve an app setting by key, or None if not set.

        Args:
            key: Setting key to look up.

        Returns:
            The AppSetting if found, or None if the key is not stored.
        """
        with self._get_connection() as conn:
            row = conn.execute(SELECT_APP_SETTING_BY_KEY, (key,)).fetchone()
        if row is None:
            return None
        return AppSetting(key=row["key"], value=row["value"], updated_at=row["updated_at"])

    @override
    def set_app_setting(self, *, key: str, value: str) -> None:
        """Persist or update an app setting key-value pair.

        Args:
            key: Setting key to create or overwrite.
            value: New value to store for the key.
        """
        updated_at = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(UPSERT_APP_SETTING, (key, value, updated_at))
        logger.debug("Set app setting key=%s", key)

    @override
    def get_all_app_settings(self) -> list[AppSetting]:
        """Retrieve all stored app settings.

        Returns:
            List of all AppSetting records; empty if none exist.
        """
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_ALL_APP_SETTINGS).fetchall()
        return [AppSetting(key=row["key"], value=row["value"], updated_at=row["updated_at"]) for row in rows]

    # ------------------------------------------------------------------
    # PromptVariants
    # ------------------------------------------------------------------

    @override
    def create_prompt_variant(self, variant: PromptVariant) -> None:
        """Store a new prompt variant for a Prompt Eval run.

        Args:
            variant: PromptVariant record to persist.
        """
        logger.debug("Creating prompt variant id=%s for run_id=%d", variant.variant_id, variant.run_id)
        with self._get_connection() as conn:
            conn.execute(
                INSERT_PROMPT_VARIANT,
                (
                    variant.variant_id,
                    variant.run_id,
                    variant.variant_label,
                    variant.system_prompt,
                    variant.user_prompt_template,
                    variant.created_at,
                ),
            )
        logger.info("Created prompt variant id=%s", variant.variant_id)

    @override
    def retrieve_prompt_variants_for_run(self, run_id: int) -> list[PromptVariant]:
        """Retrieve all prompt variants associated with a benchmark run.

        Args:
            run_id: Unique ID of the parent benchmark run.

        Returns:
            List of PromptVariant records for the run; empty if none exist.
        """
        logger.debug("Retrieving prompt variants for run_id=%d", run_id)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_PROMPT_VARIANTS_BY_RUN_ID, (run_id,)).fetchall()
        return [
            PromptVariant(
                variant_id=row["variant_id"],
                run_id=row["run_id"],
                variant_label=row["variant_label"],
                system_prompt=row["system_prompt"],
                user_prompt_template=row["user_prompt_template"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @override
    def reset_results(self, result_ids: list[int]) -> None:
        """Reset listed result rows to NOT_COMPLETED, clearing all inferred fields.

        Args:
            result_ids: IDs of the benchmark results to reset.
        """
        if not result_ids:
            return
        placeholders = "(" + ", ".join("?" * len(result_ids)) + ")"
        # Placeholders are constructed from len(result_ids) only — no user-supplied text in the query.
        sql = (
            f"UPDATE benchmark_results "  # noqa: S608
            "SET status = 'NOT_COMPLETED', "
            "completed_at = NULL, raw_response = NULL, sanitized_response = NULL, "
            "response_char_length = NULL, has_thinking_block = 0, "
            "total_time_ms = NULL, ttft_ms = NULL, prompt_tokens = NULL, "
            "completion_tokens = NULL, tokens_per_second = NULL, "
            "rule_check_result = NULL, rule_check_flag = NULL, rule_check_resolved = 0, "
            "keyword_check_result = NULL, missing_exact_terms = NULL, "
            "found_forbidden_terms = NULL, semantic_term_scores = NULL, "
            "keyword_check_resolved = 0, cosine_similarity = NULL, "
            "cosine_embedding_model = NULL, cosine_strategy = NULL, "
            "cosine_auto_pass = 0, cosine_resolved = 0, "
            "judge_result = NULL, judge_score = NULL, judge_reasoning = NULL, "
            "judge_prompt_template = NULL, judge_time_ms = NULL, "
            "judge_completion_tokens = NULL, final_verdict = NULL, "
            "resolution_layer = NULL, has_inference_error = 0, "
            "inference_error_message = NULL, has_judge_error = 0, "
            f"judge_error_message = NULL WHERE result_id IN {placeholders}"
        )
        with self._get_connection() as conn:
            cursor = conn.execute(sql, result_ids)
        logger.debug("reset_results: reset %d rows", cursor.rowcount)

    # ------------------------------------------------------------------
    # Private parameter builders
    # ------------------------------------------------------------------

    def _result_to_params(self, r: BenchmarkResult) -> tuple[object, ...]:
        """Build the INSERT parameter tuple for a BenchmarkResult.

        Follows the column order declared in INSERT_RESULT.

        Args:
            r: BenchmarkResult to serialize.

        Returns:
            Tuple of 57 values matching the INSERT_RESULT placeholder order.
        """
        return (
            r.run_id,
            r.run_type,
            r.created_at,
            r.completed_at,
            r.provider_id,
            r.provider_type,
            r.model_name,
            r.model_family,
            r.model_size_b,
            r.quantization_label,
            r.task_id,
            r.task_category,
            r.task_type,
            r.task_difficulty,
            r.response_scope,
            r.source_language,
            r.target_language,
            r.prompt_version,
            r.prompt_hash,
            r.user_prompt_sent,
            r.system_prompt_sent,
            r.golden_answer,
            r.raw_response,
            r.sanitized_response,
            r.response_char_length,
            int(r.has_thinking_block),
            r.status,
            r.total_time_ms,
            r.ttft_ms,
            r.prompt_tokens,
            r.completion_tokens,
            r.tokens_per_second,
            r.rule_check_result,
            r.rule_check_flag,
            int(r.rule_check_resolved),
            r.keyword_check_result,
            r.missing_exact_terms,
            r.found_forbidden_terms,
            r.semantic_term_scores,
            int(r.keyword_check_resolved),
            r.cosine_similarity,
            r.cosine_embedding_model,
            r.cosine_strategy,
            int(r.cosine_auto_pass),
            int(r.cosine_resolved),
            r.judge_result,
            r.judge_score,
            r.judge_reasoning,
            r.judge_prompt_template,
            r.judge_time_ms,
            r.judge_completion_tokens,
            r.final_verdict,
            r.resolution_layer,
            int(r.has_inference_error),
            r.inference_error_message,
            int(r.has_judge_error),
            r.judge_error_message,
        )

    def _result_to_update_params(self, r: BenchmarkResult) -> tuple[object, ...]:
        """Build the UPDATE parameter tuple for a BenchmarkResult.

        Follows the SET column order declared in UPDATE_RESULT and appends
        result_id as the WHERE parameter.

        Args:
            r: BenchmarkResult to serialize.

        Returns:
            Tuple of 58 values (57 SET values + result_id WHERE clause).
        """
        return (
            r.run_id,
            r.run_type,
            r.created_at,
            r.completed_at,
            r.provider_id,
            r.provider_type,
            r.model_name,
            r.model_family,
            r.model_size_b,
            r.quantization_label,
            r.task_id,
            r.task_category,
            r.task_type,
            r.task_difficulty,
            r.response_scope,
            r.source_language,
            r.target_language,
            r.prompt_version,
            r.prompt_hash,
            r.user_prompt_sent,
            r.system_prompt_sent,
            r.golden_answer,
            r.raw_response,
            r.sanitized_response,
            r.response_char_length,
            int(r.has_thinking_block),
            r.status,
            r.total_time_ms,
            r.ttft_ms,
            r.prompt_tokens,
            r.completion_tokens,
            r.tokens_per_second,
            r.rule_check_result,
            r.rule_check_flag,
            int(r.rule_check_resolved),
            r.keyword_check_result,
            r.missing_exact_terms,
            r.found_forbidden_terms,
            r.semantic_term_scores,
            int(r.keyword_check_resolved),
            r.cosine_similarity,
            r.cosine_embedding_model,
            r.cosine_strategy,
            int(r.cosine_auto_pass),
            int(r.cosine_resolved),
            r.judge_result,
            r.judge_score,
            r.judge_reasoning,
            r.judge_prompt_template,
            r.judge_time_ms,
            r.judge_completion_tokens,
            r.final_verdict,
            r.resolution_layer,
            int(r.has_inference_error),
            r.inference_error_message,
            int(r.has_judge_error),
            r.judge_error_message,
            r.result_id,
        )

    # ------------------------------------------------------------------
    # Model capabilities
    # ------------------------------------------------------------------

    @override
    def get_model_capability(self, provider_id: str, model_name: str, capability: str) -> int | None:
        """Retrieve a stored model capability flag as a raw integer.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key.

        Returns:
            1 if supported, 0 if not supported, -1 if unknown, None if no row exists.
        """
        with self._get_connection() as conn:
            row = conn.execute(SELECT_MODEL_CAPABILITY, (provider_id, model_name, capability)).fetchone()
        if row is None:
            return None
        return int(row["supported"])

    @override
    def set_model_capability(
        self,
        provider_id: str,
        model_name: str,
        capability: str,
        *,
        supported: bool,
        observed_via: str,
        detail: str | None = None,
    ) -> None:
        """Persist or update a model capability observation.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key.
            supported: True if the capability is supported, False otherwise.
            observed_via: Short label describing how the observation was made.
            detail: Optional additional context such as the raw error message.
        """
        with self._get_connection() as conn:
            conn.execute(
                UPSERT_MODEL_CAPABILITY,
                (
                    provider_id,
                    model_name,
                    capability,
                    1 if supported else 0,
                    datetime.now(UTC).isoformat(),
                    observed_via,
                    detail,
                ),
            )

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def _row_to_provider_config(self, row: sqlite3.Row) -> ProviderConfig:
        raw_key: str = row["api_key_raw"] or ""
        default_models_json: str = row["default_models"] or "[]"
        try:
            default_models: tuple[str, ...] = tuple(str(m) for m in json.loads(default_models_json))
        except (json.JSONDecodeError, TypeError):
            default_models = ()
        return ProviderConfig(
            provider_id=str(row["provider_id"]),
            label=str(row["label"] or ""),
            provider_type=ProviderType(str(row["provider_type"])),
            api_key=raw_key,
            api_key_raw=raw_key,
            enabled=bool(row["enabled"]),
            base_url=str(row["base_url"]) if row["base_url"] is not None else None,
            default_models=default_models,
            azure_deployment=str(row["azure_deployment"]) if row["azure_deployment"] is not None else None,
            azure_api_version=str(row["azure_api_version"]) if row["azure_api_version"] is not None else None,
            last_test_status=str(row["last_test_status"]) if row["last_test_status"] is not None else None,
            last_test_at=str(row["last_test_at"]) if row["last_test_at"] is not None else None,
            last_test_message=str(row["last_test_message"]) if row["last_test_message"] is not None else None,
        )

    @override
    def count_providers(self) -> int:
        """Return the total number of provider rows in the providers table."""
        with self._get_connection() as conn:
            row = conn.execute(SELECT_PROVIDERS_COUNT).fetchone()
        return int(row["cnt"]) if row is not None else 0

    @override
    def load_all_providers(self) -> list[ProviderConfig]:
        """Load all provider rows from the providers table."""
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_ALL_PROVIDERS).fetchall()
        return [self._row_to_provider_config(r) for r in rows]

    @override
    def upsert_provider(self, provider: ProviderConfig) -> None:
        """Insert or replace a provider row, storing api_key_raw."""
        with self._get_connection() as conn:
            conn.execute(
                UPSERT_PROVIDER,
                (
                    provider.provider_id,
                    provider.label,
                    provider.provider_type.value,
                    provider.api_key_raw,
                    int(provider.enabled),
                    provider.base_url,
                    json.dumps(list(provider.default_models)),
                    provider.azure_deployment,
                    provider.azure_api_version,
                ),
            )

    @override
    def delete_provider(self, provider_id: str) -> None:
        """Delete a provider row by its identifier."""
        with self._get_connection() as conn:
            conn.execute(DELETE_PROVIDER, (provider_id,))

    @override
    def load_embedding_config(self) -> EmbeddingConfig | None:
        """Load the singleton embedding config row."""
        with self._get_connection() as conn:
            row = conn.execute(SELECT_EMBEDDING_CONFIG).fetchone()
        if row is None:
            return None
        return EmbeddingConfig(provider_id=str(row["provider_id"]), model=str(row["model"]))

    @override
    def upsert_embedding_config(self, config: EmbeddingConfig) -> None:
        """Insert or replace the singleton embedding config row."""
        with self._get_connection() as conn:
            conn.execute(UPSERT_EMBEDDING_CONFIG, (config.provider_id, config.model))

    @override
    def replace_all_providers(self, providers: list[ProviderConfig]) -> None:
        """Delete all existing providers and insert providers atomically.

        Args:
            providers: Replacement list of ProviderConfig instances.
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM providers")
            for p in providers:
                conn.execute(
                    UPSERT_PROVIDER,
                    (
                        p.provider_id,
                        p.label,
                        p.provider_type.value,
                        p.api_key_raw,
                        int(p.enabled),
                        p.base_url,
                        json.dumps(list(p.default_models)),
                        p.azure_deployment,
                        p.azure_api_version,
                    ),
                )
        logger.debug("replace_all_providers: replaced with %d providers", len(providers))

    @override
    def update_provider_test_status(self, provider_id: str, status: str, tested_at: str, message: str) -> None:
        """Persist the last health-check result columns for a provider row."""
        with self._get_connection() as conn:
            conn.execute(UPDATE_PROVIDER_TEST_STATUS, (status, tested_at, message, provider_id))
