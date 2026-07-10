"""The concrete ``TasksStore`` implementation over the single-writer connection.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.2; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §5.5-§5.6.
"""

from collections.abc import Callable
import sqlite3
import threading

from ollama_llm_bench.backend.domain import (
    BenchmarkTask,
    Difficulty,
    RequiredTerms,
    RunId,
    TaskOrigin,
    TaskTermKind,
)
from ollama_llm_bench.backend.errors import PersistenceError

__all__: list[str] = [
    "SqliteTasksStore",
]


class SqliteTasksStore:
    """``TasksStore`` over the single write connection and read-only factory.

    Satisfies the ``TasksStore`` Protocol structurally. Every method wraps
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

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Insert a run's frozen task snapshot and its keyword-term child rows
        in one transaction.

        Raises:
            PersistenceError: The underlying write failed, including a
                primary-key or CHECK-constraint violation (an
                ``sqlite3.IntegrityError``).
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                for task in tasks:
                    self._insert_task(run_id, task)
                    self._insert_task_terms(run_id, task.task_id, task.required_terms)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to create tasks for run {run_id}"
                raise PersistenceError(message=message) from exc

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return a run's frozen tasks in ascending ``task_order``, each
        assembled with its exact/semantic/forbidden term child rows.

        An empty/missing run naturally yields ``()``.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            task_rows = conn.execute(
                _SELECT_TASK_COLUMNS + " WHERE run_id = ? ORDER BY task_order ASC",
                (run_id,),
            ).fetchall()
            term_rows = conn.execute(
                "SELECT task_id, term_kind, term_order, term_text "
                "FROM benchmark_task_terms WHERE run_id = ? "
                "ORDER BY task_id, term_kind, term_order",
                (run_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            message = f"failed to list tasks for run {run_id}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        terms_by_task = _group_terms_by_task(term_rows)
        return tuple(
            _row_to_benchmark_task(row, terms_by_task.get(row[0], RequiredTerms()))
            for row in task_rows
        )

    def _insert_task(self, run_id: RunId, task: BenchmarkTask) -> None:
        self._write_conn.execute(
            """
            INSERT INTO benchmark_tasks (
                run_id, task_id, task_origin, category, sub_category, cosine_enabled,
                difficulty, question, golden_answer, pass_criteria, fail_criteria,
                source_language, target_language, source_material, fail_example,
                input_size_label, output_size_label, repeat_index, task_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task.task_id,
                task.task_origin.value,
                task.category,
                task.sub_category,
                1 if task.cosine_enabled else 0,
                task.difficulty.value,
                task.question,
                task.golden_answer,
                task.pass_criteria,
                task.fail_criteria,
                task.source_language,
                task.target_language,
                task.source_material,
                task.fail_example,
                task.input_size_label,
                task.output_size_label,
                task.repeat_index,
                task.task_order,
            ),
        )

    def _insert_task_terms(
        self, run_id: RunId, task_id: str, required_terms: RequiredTerms
    ) -> None:
        term_groups = (
            (TaskTermKind.EXACT, required_terms.exact),
            (TaskTermKind.SEMANTIC, required_terms.semantic),
            (TaskTermKind.FORBIDDEN, required_terms.forbidden),
        )
        for term_kind, terms in term_groups:
            for term_order, term_text in enumerate(terms):
                self._write_conn.execute(
                    "INSERT INTO benchmark_task_terms "
                    "(run_id, task_id, term_kind, term_order, term_text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (run_id, task_id, term_kind.value, term_order, term_text),
                )


_SELECT_TASK_COLUMNS = """
    SELECT task_id, task_origin, category, sub_category, cosine_enabled, difficulty,
           question, golden_answer, pass_criteria, fail_criteria, source_language,
           target_language, source_material, fail_example, input_size_label,
           output_size_label, repeat_index, task_order
    FROM benchmark_tasks
"""


def _group_terms_by_task(
    term_rows: list[sqlite3.Row],
) -> dict[str, RequiredTerms]:
    """Group ordered ``benchmark_task_terms`` rows into one ``RequiredTerms`` per task.

    ``term_rows`` is fetched ordered by ``task_id, term_kind, term_order``, so
    appending in fetch order already yields ``term_order``-ascending tuples
    within each kind — no extra sort is needed.
    """
    exact_by_task: dict[str, list[str]] = {}
    semantic_by_task: dict[str, list[str]] = {}
    forbidden_by_task: dict[str, list[str]] = {}
    for task_id, term_kind, _term_order, term_text in term_rows:
        bucket = {
            TaskTermKind.EXACT.value: exact_by_task,
            TaskTermKind.SEMANTIC.value: semantic_by_task,
            TaskTermKind.FORBIDDEN.value: forbidden_by_task,
        }[term_kind]
        bucket.setdefault(task_id, []).append(term_text)
    task_ids = exact_by_task.keys() | semantic_by_task.keys() | forbidden_by_task.keys()
    return {
        task_id: RequiredTerms(
            exact=tuple(exact_by_task.get(task_id, ())),
            semantic=tuple(semantic_by_task.get(task_id, ())),
            forbidden=tuple(forbidden_by_task.get(task_id, ())),
        )
        for task_id in task_ids
    }


def _row_to_benchmark_task(row: sqlite3.Row, required_terms: RequiredTerms) -> BenchmarkTask:
    """Assemble a ``BenchmarkTask`` from one ``benchmark_tasks`` row plus its terms."""
    return BenchmarkTask(
        task_id=row[0],
        task_origin=TaskOrigin(row[1]),
        category=row[2],
        sub_category=row[3],
        cosine_enabled=bool(row[4]),
        difficulty=Difficulty(row[5]),
        question=row[6],
        golden_answer=row[7],
        pass_criteria=row[8],
        fail_criteria=row[9],
        source_language=row[10],
        target_language=row[11],
        source_material=row[12],
        fail_example=row[13],
        input_size_label=row[14],
        output_size_label=row[15],
        repeat_index=row[16],
        task_order=row[17],
        required_terms=required_terms,
    )
