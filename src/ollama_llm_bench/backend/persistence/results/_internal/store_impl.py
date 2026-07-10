"""The concrete ``ResultsStore`` implementation over the single-writer connection.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.3; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §5.7,
§9.
"""

from collections.abc import Callable
import sqlite3
import threading
from typing import Final

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResult,
    BenchmarkResultAttempt,
    BenchmarkResultTerm,
    ErrorKind,
    ResolutionLayer,
    ResultId,
    ResultPatch,
    ResultStatus,
    ResultTermKind,
    RunId,
    Verdict,
)
from ollama_llm_bench.backend.errors import PersistenceError

__all__: list[str] = [
    "SqliteResultsStore",
]

# The retryable terminal-failure statuses (`08-E` §7.3, resumable-set definition).
_RETRYABLE_FAILURE_STATUSES: Final[tuple[ResultStatus, ...]] = (
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)

# The four non-terminal in-flight statuses the crash-recovery sweep resets
# (`03_PERSISTENCE_SCHEMA.md` §9).
_IN_FLIGHT_STATUSES: Final[tuple[ResultStatus, ...]] = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)

# The shared full-reset column list (`03_PERSISTENCE_SCHEMA.md` §9; `08-E` §7.3
# `reset_results`): every outcome/in-flight column set NULL except
# `has_thinking_block`, which resets to 0. Identity columns are excluded.
_FULL_RESET_SET_CLAUSE: Final[str] = """
    status                  = 'pending',
    verdict                 = NULL,
    started_at              = NULL,
    finished_at             = NULL,
    system_prompt_sent      = NULL,
    user_prompt_sent        = NULL,
    raw_response             = NULL,
    sanitized_response       = NULL,
    has_thinking_block       = 0,
    response_char_length     = NULL,
    total_time_ms            = NULL,
    ttft_ms                  = NULL,
    prompt_tokens            = NULL,
    completion_tokens        = NULL,
    tokens_per_second        = NULL,
    sanity_check_passed      = NULL,
    keyword_verdict          = NULL,
    cosine_similarity        = NULL,
    cosine_verdict           = NULL,
    judge_verdict            = NULL,
    judge_reasoning          = NULL,
    judge_time_ms            = NULL,
    judge_completion_tokens  = NULL,
    resolution_layer         = NULL,
    error_kind               = NULL,
    error_message            = NULL
"""

# The judge-only reset column list (`08-E` §7.3 `reset_results_for_retry`): clears
# only the judge outputs, the combined verdict, and the error columns; preserves
# the inference response, timing/token metrics, and keyword/cosine outcomes.
_JUDGE_ONLY_RESET_SET_CLAUSE: Final[str] = """
    status                   = 'awaiting_judge_check',
    judge_verdict            = NULL,
    judge_reasoning          = NULL,
    judge_time_ms            = NULL,
    judge_completion_tokens  = NULL,
    verdict                  = NULL,
    resolution_layer         = NULL,
    error_kind               = NULL,
    error_message            = NULL
"""


class SqliteResultsStore:
    """``ResultsStore`` over the single write connection and read-only factory.

    Satisfies the ``ResultsStore`` Protocol structurally. Every method wraps
    ``sqlite3.Error`` into ``PersistenceError``.
    """

    def __init__(
        self,
        *,
        write_conn: sqlite3.Connection,
        lock: threading.Lock,
        read_conn_factory: Callable[[], sqlite3.Connection],
    ) -> None:
        self._write_conn = write_conn
        self._lock = lock
        self._read_conn_factory = read_conn_factory

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert the initial result rows for a run in one transaction.

        Each ``BenchmarkResult.result_id`` in ``results`` is a caller
        placeholder this method ignores; SQLite's ``INTEGER PRIMARY KEY``
        auto-assigns the real id. The caller re-reads via ``list_results`` to
        learn the assigned ids.

        Raises:
            PersistenceError: The underlying write failed, including a
                CHECK-constraint or foreign-key violation (an
                ``sqlite3.IntegrityError``).
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                for result in results:
                    new_result_id = self._insert_result_header(result)
                    self._insert_result_terms(new_result_id, result.terms)
                    self._insert_result_attempts(new_result_id, result.attempts)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to create results"
                raise PersistenceError(message=message) from exc

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Apply a partial update to one result, replacing its term/attempt
        child rows wholesale when the patch carries them, in one transaction.

        Raises:
            PersistenceError: The result does not exist, or the underlying
                write failed.
        """
        assignments, values = _build_result_patch_assignments(patch)
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                if assignments:
                    sql = (
                        f"UPDATE benchmark_results SET {', '.join(assignments)} "  # noqa: S608
                        "WHERE result_id = ?"
                    )
                    cursor = self._write_conn.execute(sql, (*values, result_id))
                    if cursor.rowcount == 0:
                        message = f"result {result_id} does not exist"
                        raise PersistenceError(message=message)
                if patch.terms is not None:
                    self._replace_result_terms(result_id, patch.terms)
                if patch.attempts is not None:
                    self._replace_result_attempts(result_id, patch.attempts)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to update result {result_id}"
                raise PersistenceError(message=message) from exc
            except PersistenceError:
                self._write_conn.rollback()
                raise

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return every result of a run, each assembled with its term and
        attempt child rows, ordered by ``result_id`` ascending.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            rows = conn.execute(
                _SELECT_RESULT_COLUMNS + " WHERE run_id = ? ORDER BY result_id ASC", (run_id,)
            ).fetchall()
            terms_by_result, attempts_by_result = self._select_children_for_run(conn, run_id)
        except sqlite3.Error as exc:
            message = f"failed to list results for run {run_id}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        return tuple(
            _row_to_benchmark_result(
                row,
                terms=terms_by_result.get(row[0], ()),
                attempts=attempts_by_result.get(row[0], ()),
            )
            for row in rows
        )

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible to (re-)run on resume: rows in
        ``PENDING`` and rows in a retryable terminal-failure status.

        Raises:
            PersistenceError: The underlying read failed.
        """
        resumable_statuses = (ResultStatus.PENDING, *_RETRYABLE_FAILURE_STATUSES)
        placeholders = ",".join("?" * len(resumable_statuses))
        conn = self._read_conn_factory()
        try:
            sql = (
                _SELECT_RESULT_COLUMNS
                + f" WHERE run_id = ? AND status IN ({placeholders}) ORDER BY result_id ASC"
            )
            rows = conn.execute(
                sql, (run_id, *(status.value for status in resumable_statuses))
            ).fetchall()
            terms_by_result, attempts_by_result = self._select_children_for_run(conn, run_id)
        except sqlite3.Error as exc:
            message = f"failed to list resumable results for run {run_id}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        return tuple(
            _row_to_benchmark_result(
                row,
                terms=terms_by_result.get(row[0], ()),
                attempts=attempts_by_result.get(row[0], ()),
            )
            for row in rows
        )

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the named results to ``PENDING``, in one
        transaction. A row already in ``PENDING`` is left unchanged.

        Raises:
            PersistenceError: The underlying write failed.
        """
        if not result_ids:
            return 0
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                current_rows = self._select_current_statuses(result_ids)
                targets = tuple(
                    row_id
                    for row_id, status, _sanitized_response in current_rows
                    if status != ResultStatus.PENDING.value
                )
                self._full_reset(targets)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to reset results"
                raise PersistenceError(message=message) from exc
        return len(targets)

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Reset the named results for retry from the failed stage (DD-66), in
        one transaction. A row already in ``PENDING`` is left unchanged.

        Raises:
            PersistenceError: The underlying write failed.
        """
        if not result_ids:
            return 0
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                current_rows = self._select_current_statuses(result_ids)
                judge_only_targets, full_reset_targets = _partition_retry_targets(current_rows)
                self._judge_only_reset(judge_only_targets)
                self._full_reset(full_reset_targets)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to reset results for retry"
                raise PersistenceError(message=message) from exc
        return len(judge_only_targets) + len(full_reset_targets)

    def recover_in_flight_results(self) -> int:
        """Run the crash-recovery sweep in one transaction: clear the child
        rows of every result left mid-flight, then reset those rows to
        ``PENDING``. Idempotent — a second call resets zero rows.

        Raises:
            PersistenceError: The underlying write failed.
        """
        placeholders = ",".join("?" * len(_IN_FLIGHT_STATUSES))
        in_flight_values = tuple(status.value for status in _IN_FLIGHT_STATUSES)
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_conn.execute(
                    "DELETE FROM benchmark_result_terms WHERE result_id IN ("  # noqa: S608
                    f"SELECT result_id FROM benchmark_results WHERE status IN ({placeholders}))",
                    in_flight_values,
                )
                self._write_conn.execute(
                    "DELETE FROM benchmark_result_attempts WHERE result_id IN ("  # noqa: S608
                    f"SELECT result_id FROM benchmark_results WHERE status IN ({placeholders}))",
                    in_flight_values,
                )
                cursor = self._write_conn.execute(
                    f"UPDATE benchmark_results SET {_FULL_RESET_SET_CLAUSE} "  # noqa: S608
                    f"WHERE status IN ({placeholders})",
                    in_flight_values,
                )
                reset_count = cursor.rowcount
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to run the crash-recovery sweep"
                raise PersistenceError(message=message) from exc
        return reset_count

    def _insert_result_header(self, result: BenchmarkResult) -> ResultId:
        cursor = self._write_conn.execute(
            """
            INSERT INTO benchmark_results (
                run_id, task_id, provider_id, provider_name, model_name, status, verdict,
                created_at, started_at, finished_at, system_prompt_sent, user_prompt_sent,
                raw_response, sanitized_response, has_thinking_block, response_char_length,
                total_time_ms, ttft_ms, prompt_tokens, completion_tokens, tokens_per_second,
                tokens_estimated, sanity_check_passed, keyword_verdict, cosine_similarity,
                cosine_verdict, judge_verdict, judge_reasoning, judge_time_ms,
                judge_completion_tokens, resolution_layer, error_kind, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                result.task_id,
                result.provider_id,
                result.provider_name,
                result.model_name,
                result.status.value,
                result.verdict.value if result.verdict is not None else None,
                result.created_at,
                result.started_at,
                result.finished_at,
                result.system_prompt_sent,
                result.user_prompt_sent,
                result.raw_response,
                result.sanitized_response,
                1 if result.has_thinking_block else 0,
                result.response_char_length,
                result.total_time_ms,
                result.ttft_ms,
                result.prompt_tokens,
                result.completion_tokens,
                result.tokens_per_second,
                1 if result.tokens_estimated else 0,
                _bool_or_none(value=result.sanity_check_passed),
                result.keyword_verdict.value if result.keyword_verdict is not None else None,
                result.cosine_similarity,
                result.cosine_verdict.value if result.cosine_verdict is not None else None,
                result.judge_verdict.value if result.judge_verdict is not None else None,
                result.judge_reasoning,
                result.judge_time_ms,
                result.judge_completion_tokens,
                result.resolution_layer.value if result.resolution_layer is not None else None,
                result.error_kind.value if result.error_kind is not None else None,
                result.error_message,
            ),
        )
        new_result_id = cursor.lastrowid
        if new_result_id is None:
            message = "sqlite did not return a lastrowid for the new result header"
            raise PersistenceError(message=message)
        return new_result_id

    def _insert_result_terms(
        self, result_id: ResultId, terms: tuple[BenchmarkResultTerm, ...]
    ) -> None:
        for term in terms:
            self._write_conn.execute(
                "INSERT INTO benchmark_result_terms "
                "(result_id, term_kind, term_order, term_text, similarity_score) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    result_id,
                    term.term_kind.value,
                    term.term_order,
                    term.term_text,
                    term.similarity_score,
                ),
            )

    def _insert_result_attempts(
        self, result_id: ResultId, attempts: tuple[BenchmarkResultAttempt, ...]
    ) -> None:
        for attempt in attempts:
            self._write_conn.execute(
                "INSERT INTO benchmark_result_attempts "
                "(result_id, attempt_index, timeout_ms, duration_ms, outcome, error_kind, "
                "error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result_id,
                    attempt.attempt_index,
                    attempt.timeout_ms,
                    attempt.duration_ms,
                    attempt.outcome.value,
                    attempt.error_kind.value if attempt.error_kind is not None else None,
                    attempt.error_message,
                ),
            )

    def _replace_result_terms(
        self, result_id: ResultId, terms: tuple[BenchmarkResultTerm, ...]
    ) -> None:
        self._write_conn.execute(
            "DELETE FROM benchmark_result_terms WHERE result_id = ?", (result_id,)
        )
        self._insert_result_terms(result_id, terms)

    def _replace_result_attempts(
        self, result_id: ResultId, attempts: tuple[BenchmarkResultAttempt, ...]
    ) -> None:
        self._write_conn.execute(
            "DELETE FROM benchmark_result_attempts WHERE result_id = ?", (result_id,)
        )
        self._insert_result_attempts(result_id, attempts)

    def _select_children_for_run(
        self, conn: sqlite3.Connection, run_id: RunId
    ) -> tuple[
        dict[ResultId, tuple[BenchmarkResultTerm, ...]],
        dict[ResultId, tuple[BenchmarkResultAttempt, ...]],
    ]:
        term_rows = conn.execute(
            "SELECT t.result_id, t.term_kind, t.term_order, t.term_text, t.similarity_score "
            "FROM benchmark_result_terms t JOIN benchmark_results r "
            "ON t.result_id = r.result_id "
            "WHERE r.run_id = ? ORDER BY t.result_id, t.term_kind, t.term_order",
            (run_id,),
        ).fetchall()
        attempt_rows = conn.execute(
            "SELECT a.result_id, a.attempt_index, a.timeout_ms, a.duration_ms, a.outcome, "
            "a.error_kind, a.error_message "
            "FROM benchmark_result_attempts a JOIN benchmark_results r "
            "ON a.result_id = r.result_id "
            "WHERE r.run_id = ? ORDER BY a.result_id, a.attempt_index",
            (run_id,),
        ).fetchall()
        return _group_terms_by_result(term_rows), _group_attempts_by_result(attempt_rows)

    def _select_current_statuses(
        self, result_ids: tuple[ResultId, ...]
    ) -> tuple[tuple[ResultId, str, str | None], ...]:
        placeholders = ",".join("?" * len(result_ids))
        sql = (
            "SELECT result_id, status, sanitized_response FROM benchmark_results "  # noqa: S608
            f"WHERE result_id IN ({placeholders})"
        )
        rows = self._write_conn.execute(sql, result_ids).fetchall()
        return tuple((row[0], row[1], row[2]) for row in rows)

    def _full_reset(self, result_ids: tuple[ResultId, ...]) -> None:
        if not result_ids:
            return
        placeholders = ",".join("?" * len(result_ids))
        self._write_conn.execute(
            "DELETE FROM benchmark_result_terms WHERE result_id IN "  # noqa: S608
            f"({placeholders})",
            result_ids,
        )
        self._write_conn.execute(
            "DELETE FROM benchmark_result_attempts WHERE result_id IN "  # noqa: S608
            f"({placeholders})",
            result_ids,
        )
        self._write_conn.execute(
            f"UPDATE benchmark_results SET {_FULL_RESET_SET_CLAUSE} "  # noqa: S608
            f"WHERE result_id IN ({placeholders})",
            result_ids,
        )

    def _judge_only_reset(self, result_ids: tuple[ResultId, ...]) -> None:
        if not result_ids:
            return
        placeholders = ",".join("?" * len(result_ids))
        self._write_conn.execute(
            f"UPDATE benchmark_results SET {_JUDGE_ONLY_RESET_SET_CLAUSE} "  # noqa: S608
            f"WHERE result_id IN ({placeholders})",
            result_ids,
        )


_SELECT_RESULT_COLUMNS = """
    SELECT result_id, run_id, task_id, provider_id, provider_name, model_name, status, verdict,
           created_at, started_at, finished_at, system_prompt_sent, user_prompt_sent,
           raw_response, sanitized_response, has_thinking_block, response_char_length,
           total_time_ms, ttft_ms, prompt_tokens, completion_tokens, tokens_per_second,
           tokens_estimated, sanity_check_passed, keyword_verdict, cosine_similarity,
           cosine_verdict, judge_verdict, judge_reasoning, judge_time_ms,
           judge_completion_tokens, resolution_layer, error_kind, error_message
    FROM benchmark_results
"""


def _bool_or_none(*, value: bool | None) -> int | None:
    """Convert a nullable boolean domain value into SQLite's ``0``/``1``/``NULL``."""
    if value is None:
        return None
    return 1 if value else 0


def _group_terms_by_result(
    term_rows: list[sqlite3.Row],
) -> dict[ResultId, tuple[BenchmarkResultTerm, ...]]:
    """Group ordered ``benchmark_result_terms`` rows into one tuple per result.

    ``term_rows`` is fetched ordered by ``result_id, term_kind, term_order``,
    so appending in fetch order already yields ``term_order``-ascending
    tuples — no extra sort is needed.
    """
    terms_by_result: dict[ResultId, list[BenchmarkResultTerm]] = {}
    for result_id, term_kind, term_order, term_text, similarity_score in term_rows:
        terms_by_result.setdefault(result_id, []).append(
            BenchmarkResultTerm(
                term_kind=ResultTermKind(term_kind),
                term_order=term_order,
                term_text=term_text,
                similarity_score=similarity_score,
            )
        )
    return {result_id: tuple(terms) for result_id, terms in terms_by_result.items()}


def _group_attempts_by_result(
    attempt_rows: list[sqlite3.Row],
) -> dict[ResultId, tuple[BenchmarkResultAttempt, ...]]:
    """Group ordered ``benchmark_result_attempts`` rows into one tuple per result.

    ``attempt_rows`` is fetched ordered by ``result_id, attempt_index``, so
    appending in fetch order already yields ``attempt_index``-ascending
    tuples — no extra sort is needed.
    """
    attempts_by_result: dict[ResultId, list[BenchmarkResultAttempt]] = {}
    for (
        result_id,
        attempt_index,
        timeout_ms,
        duration_ms,
        outcome,
        error_kind,
        error_message,
    ) in attempt_rows:
        attempts_by_result.setdefault(result_id, []).append(
            BenchmarkResultAttempt(
                attempt_index=attempt_index,
                timeout_ms=timeout_ms,
                duration_ms=duration_ms,
                outcome=AttemptOutcome(outcome),
                error_kind=ErrorKind(error_kind) if error_kind is not None else None,
                error_message=error_message,
            )
        )
    return {result_id: tuple(attempts) for result_id, attempts in attempts_by_result.items()}


def _row_to_benchmark_result(
    row: sqlite3.Row,
    *,
    terms: tuple[BenchmarkResultTerm, ...] = (),
    attempts: tuple[BenchmarkResultAttempt, ...] = (),
) -> BenchmarkResult:
    """Assemble a ``BenchmarkResult`` from one ``benchmark_results`` row plus its children."""
    return BenchmarkResult(
        result_id=row[0],
        run_id=row[1],
        task_id=row[2],
        provider_id=row[3],
        provider_name=row[4],
        model_name=row[5],
        status=ResultStatus(row[6]),
        verdict=Verdict(row[7]) if row[7] is not None else None,
        created_at=row[8],
        started_at=row[9],
        finished_at=row[10],
        system_prompt_sent=row[11],
        user_prompt_sent=row[12],
        raw_response=row[13],
        sanitized_response=row[14],
        has_thinking_block=bool(row[15]),
        response_char_length=row[16],
        total_time_ms=row[17],
        ttft_ms=row[18],
        prompt_tokens=row[19],
        completion_tokens=row[20],
        tokens_per_second=row[21],
        tokens_estimated=bool(row[22]),
        sanity_check_passed=bool(row[23]) if row[23] is not None else None,
        keyword_verdict=Verdict(row[24]) if row[24] is not None else None,
        cosine_similarity=row[25],
        cosine_verdict=Verdict(row[26]) if row[26] is not None else None,
        judge_verdict=Verdict(row[27]) if row[27] is not None else None,
        judge_reasoning=row[28],
        judge_time_ms=row[29],
        judge_completion_tokens=row[30],
        resolution_layer=ResolutionLayer(row[31]) if row[31] is not None else None,
        error_kind=ErrorKind(row[32]) if row[32] is not None else None,
        error_message=row[33],
        terms=terms,
        attempts=attempts,
    )


def _append_identity_and_response_fields(
    patch: ResultPatch, assignments: list[str], values: list[object]
) -> None:
    """Append the status/verdict/timing/prompt/response ``ResultPatch`` fields."""
    if patch.status is not None:
        assignments.append("status = ?")
        values.append(patch.status.value)
    if patch.verdict is not None:
        assignments.append("verdict = ?")
        values.append(patch.verdict.value)
    if patch.started_at is not None:
        assignments.append("started_at = ?")
        values.append(patch.started_at)
    if patch.finished_at is not None:
        assignments.append("finished_at = ?")
        values.append(patch.finished_at)
    if patch.system_prompt_sent is not None:
        assignments.append("system_prompt_sent = ?")
        values.append(patch.system_prompt_sent)
    if patch.user_prompt_sent is not None:
        assignments.append("user_prompt_sent = ?")
        values.append(patch.user_prompt_sent)
    if patch.raw_response is not None:
        assignments.append("raw_response = ?")
        values.append(patch.raw_response)
    if patch.sanitized_response is not None:
        assignments.append("sanitized_response = ?")
        values.append(patch.sanitized_response)
    if patch.has_thinking_block is not None:
        assignments.append("has_thinking_block = ?")
        values.append(1 if patch.has_thinking_block else 0)


def _append_metrics_fields(
    patch: ResultPatch, assignments: list[str], values: list[object]
) -> None:
    """Append the char-length/timing/token-metric ``ResultPatch`` fields.

    ``tokens_estimated`` has no ``None`` variant on ``ResultPatch`` (unlike
    every other field), so it is always included, never conditionally skipped.
    """
    if patch.response_char_length is not None:
        assignments.append("response_char_length = ?")
        values.append(patch.response_char_length)
    if patch.total_time_ms is not None:
        assignments.append("total_time_ms = ?")
        values.append(patch.total_time_ms)
    if patch.ttft_ms is not None:
        assignments.append("ttft_ms = ?")
        values.append(patch.ttft_ms)
    if patch.prompt_tokens is not None:
        assignments.append("prompt_tokens = ?")
        values.append(patch.prompt_tokens)
    if patch.completion_tokens is not None:
        assignments.append("completion_tokens = ?")
        values.append(patch.completion_tokens)
    if patch.tokens_per_second is not None:
        assignments.append("tokens_per_second = ?")
        values.append(patch.tokens_per_second)
    assignments.append("tokens_estimated = ?")
    values.append(1 if patch.tokens_estimated else 0)
    if patch.sanity_check_passed is not None:
        assignments.append("sanity_check_passed = ?")
        values.append(1 if patch.sanity_check_passed else 0)


def _append_evaluation_fields(
    patch: ResultPatch, assignments: list[str], values: list[object]
) -> None:
    """Append the keyword/cosine/judge/error ``ResultPatch`` fields."""
    if patch.keyword_verdict is not None:
        assignments.append("keyword_verdict = ?")
        values.append(patch.keyword_verdict.value)
    if patch.cosine_similarity is not None:
        assignments.append("cosine_similarity = ?")
        values.append(patch.cosine_similarity)
    if patch.cosine_verdict is not None:
        assignments.append("cosine_verdict = ?")
        values.append(patch.cosine_verdict.value)
    if patch.judge_verdict is not None:
        assignments.append("judge_verdict = ?")
        values.append(patch.judge_verdict.value)
    if patch.judge_reasoning is not None:
        assignments.append("judge_reasoning = ?")
        values.append(patch.judge_reasoning)
    if patch.judge_time_ms is not None:
        assignments.append("judge_time_ms = ?")
        values.append(patch.judge_time_ms)
    if patch.judge_completion_tokens is not None:
        assignments.append("judge_completion_tokens = ?")
        values.append(patch.judge_completion_tokens)
    if patch.resolution_layer is not None:
        assignments.append("resolution_layer = ?")
        values.append(patch.resolution_layer.value)
    if patch.error_kind is not None:
        assignments.append("error_kind = ?")
        values.append(patch.error_kind.value)
    if patch.error_message is not None:
        assignments.append("error_message = ?")
        values.append(patch.error_message)


def _build_result_patch_assignments(
    patch: ResultPatch,
) -> tuple[list[str], list[object]]:
    """Build the ``SET`` clause fragments and bound values for a ``ResultPatch``."""
    assignments: list[str] = []
    values: list[object] = []
    _append_identity_and_response_fields(patch, assignments, values)
    _append_metrics_fields(patch, assignments, values)
    _append_evaluation_fields(patch, assignments, values)
    return assignments, values


def _partition_retry_targets(
    current_rows: tuple[tuple[ResultId, str, str | None], ...],
) -> tuple[tuple[ResultId, ...], tuple[ResultId, ...]]:
    """Partition fetched rows into judge-only-reset and full-reset id tuples.

    Rows already ``PENDING`` are excluded from both buckets. A
    ``FAILED_JUDGE_TIMEOUT`` row, or an ``ERRORED`` row with a non-null
    ``sanitized_response``, gets the judge-only reset; every other retryable
    status gets the full reset.
    """
    judge_only: list[ResultId] = []
    full_reset: list[ResultId] = []
    for result_id, status, sanitized_response in current_rows:
        if status == ResultStatus.PENDING.value:
            continue
        is_judge_timeout = status == ResultStatus.FAILED_JUDGE_TIMEOUT.value
        is_errored_with_response = (
            status == ResultStatus.ERRORED.value and sanitized_response is not None
        )
        if is_judge_timeout or is_errored_with_response:
            judge_only.append(result_id)
        else:
            full_reset.append(result_id)
    return tuple(judge_only), tuple(full_reset)
