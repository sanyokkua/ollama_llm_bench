"""The concrete ``RunsStore`` implementation over the single-writer connection.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.1; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §5.1-§5.4,
§7.
"""

from collections.abc import Callable
import sqlite3
import threading

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunProviderEntry,
    BenchmarkRunSettingEntry,
    RunId,
    RunMode,
    RunStatus,
    RunStatusPatch,
)
from ollama_llm_bench.backend.errors import PersistenceError

__all__: list[str] = [
    "SqliteRunsStore",
]


class SqliteRunsStore:
    """``RunsStore`` over the single write connection and read-only factory.

    Satisfies the ``RunsStore`` Protocol structurally. Every method wraps
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

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Insert a run header and its three frozen snapshot child tables
        (models, providers, settings) in one transaction. Return the new run id.

        The header ``INSERT`` omits the ``run_id`` column — ``run.run_id`` is a
        caller-supplied placeholder this method ignores; SQLite's
        ``INTEGER PRIMARY KEY`` auto-assigns the real id, captured via
        ``cursor.lastrowid`` and used for the three child-table inserts.

        Raises:
            PersistenceError: The underlying write failed, including a
                CHECK-constraint or partial-unique-index violation (an
                ``sqlite3.IntegrityError``).
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                new_run_id = self._insert_run_header(run)
                self._insert_run_models(new_run_id, run.models)
                self._insert_run_providers(new_run_id, run.providers)
                self._insert_run_settings(new_run_id, run.settings_snapshot)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to create run header and snapshots"
                raise PersistenceError(message=message) from exc
        return new_run_id

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load one run, fully assembled with its snapshot collections.

        Raises:
            PersistenceError: The run does not exist, or the underlying read
                failed.
        """
        conn = self._read_conn_factory()
        try:
            header_row = self._select_run_header(conn, run_id)
            if header_row is None:
                message = f"run {run_id} does not exist"
                raise PersistenceError(message=message)
            models = self._select_run_models(conn, run_id)
            providers = self._select_run_providers(conn, run_id)
            settings_snapshot = self._select_run_settings(conn, run_id)
        except sqlite3.Error as exc:
            message = f"failed to read run {run_id}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        return _row_to_benchmark_run(
            header_row, models=models, providers=providers, settings_snapshot=settings_snapshot
        )

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header, newest first, without snapshot collections.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute(_SELECT_RUN_HEADER_COLUMNS + " ORDER BY timestamp DESC")
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            message = "failed to list runs"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()
        return tuple(_row_to_benchmark_run(row) for row in rows)

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Apply a partial update to a run header. Writes only ``benchmark_runs``.

        Raises:
            PersistenceError: The run does not exist, or the underlying write
                failed.
        """
        assignments, values = _build_status_patch_assignments(patch)
        if not assignments:
            return
        values.append(run_id)
        sql = f"UPDATE benchmark_runs SET {', '.join(assignments)} WHERE run_id = ?"  # noqa: S608
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._write_conn.execute(sql, values)
                if cursor.rowcount == 0:
                    message = f"run {run_id} does not exist"
                    raise PersistenceError(message=message)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to update status of run {run_id}"
                raise PersistenceError(message=message) from exc
            except PersistenceError:
                self._write_conn.rollback()
                raise

    def rename_run(self, run_id: RunId, run_name: str | None) -> None:
        """Set or clear the user-facing run name.

        Raises:
            PersistenceError: The underlying write failed.
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_conn.execute(
                    "UPDATE benchmark_runs SET run_name = ? WHERE run_id = ?",
                    (run_name, run_id),
                )
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to rename run {run_id}"
                raise PersistenceError(message=message) from exc

    def delete_run(self, run_id: RunId) -> None:
        """Delete a run; ``ON DELETE CASCADE`` removes every dependent row.

        Raises:
            PersistenceError: The underlying write failed.
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_conn.execute("DELETE FROM benchmark_runs WHERE run_id = ?", (run_id,))
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to delete run {run_id}"
                raise PersistenceError(message=message) from exc

    def _insert_run_header(self, run: BenchmarkRun) -> RunId:
        cursor = self._write_conn.execute(
            """
            INSERT INTO benchmark_runs (
                run_name, timestamp, run_mode, status, total_tasks, completed_tasks,
                total_elapsed_ms, run_analysis, judge_provider_id, judge_provider_name,
                embedding_provider_name, embedding_model_name, schema_version,
                created_at, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_name,
                run.timestamp,
                run.run_mode.value,
                run.status.value,
                run.total_tasks,
                run.completed_tasks,
                run.total_elapsed_ms,
                run.run_analysis,
                run.judge_provider_id,
                run.judge_provider_name,
                run.embedding_provider_name,
                run.embedding_model_name,
                run.schema_version,
                run.created_at,
                run.started_at,
                run.finished_at,
            ),
        )
        new_run_id = cursor.lastrowid
        if new_run_id is None:
            message = "sqlite did not return a lastrowid for the new run header"
            raise PersistenceError(message=message)
        return new_run_id

    def _insert_run_models(self, run_id: RunId, models: tuple[BenchmarkRunModelEntry, ...]) -> None:
        for entry in models:
            self._write_conn.execute(
                """
                INSERT INTO benchmark_run_models (
                    run_id, role, provider_id, model_name, model_family,
                    model_params_b, quantization
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    entry.role.value,
                    entry.provider_id,
                    entry.model_name,
                    entry.model_family,
                    entry.model_params_b,
                    entry.quantization,
                ),
            )

    def _insert_run_providers(
        self, run_id: RunId, providers: tuple[BenchmarkRunProviderEntry, ...]
    ) -> None:
        for entry in providers:
            self._write_conn.execute(
                """
                INSERT INTO benchmark_run_providers (
                    run_id, provider_id, name, provider_type, base_url, api_key_raw,
                    azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    entry.provider_id,
                    entry.name,
                    entry.provider_type.value,
                    entry.base_url,
                    entry.api_key_raw,
                    entry.azure_endpoint_raw,
                    entry.azure_deployment_raw,
                    entry.azure_api_version_raw,
                ),
            )

    def _insert_run_settings(
        self, run_id: RunId, settings_snapshot: tuple[BenchmarkRunSettingEntry, ...]
    ) -> None:
        for entry in settings_snapshot:
            self._write_conn.execute(
                "INSERT INTO benchmark_run_settings (run_id, setting_key, setting_value) "
                "VALUES (?, ?, ?)",
                (run_id, entry.setting_key, entry.setting_value),
            )

    def _select_run_header(self, conn: sqlite3.Connection, run_id: RunId) -> sqlite3.Row | None:
        cursor = conn.execute(_SELECT_RUN_HEADER_COLUMNS + " WHERE run_id = ?", (run_id,))
        row: sqlite3.Row | None = cursor.fetchone()
        return row

    def _select_run_models(
        self, conn: sqlite3.Connection, run_id: RunId
    ) -> tuple[BenchmarkRunModelEntry, ...]:
        cursor = conn.execute(
            "SELECT role, provider_id, model_name, model_family, model_params_b, "
            "quantization FROM benchmark_run_models WHERE run_id = ? "
            "ORDER BY role, provider_id, model_name",
            (run_id,),
        )
        return tuple(
            BenchmarkRunModelEntry(
                role=row[0],
                provider_id=row[1],
                model_name=row[2],
                model_family=row[3],
                model_params_b=row[4],
                quantization=row[5],
            )
            for row in cursor.fetchall()
        )

    def _select_run_providers(
        self, conn: sqlite3.Connection, run_id: RunId
    ) -> tuple[BenchmarkRunProviderEntry, ...]:
        cursor = conn.execute(
            "SELECT provider_id, name, provider_type, base_url, api_key_raw, "
            "azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw "
            "FROM benchmark_run_providers WHERE run_id = ? ORDER BY provider_id",
            (run_id,),
        )
        return tuple(
            BenchmarkRunProviderEntry(
                provider_id=row[0],
                name=row[1],
                provider_type=row[2],
                base_url=row[3],
                api_key_raw=row[4],
                azure_endpoint_raw=row[5],
                azure_deployment_raw=row[6],
                azure_api_version_raw=row[7],
            )
            for row in cursor.fetchall()
        )

    def _select_run_settings(
        self, conn: sqlite3.Connection, run_id: RunId
    ) -> tuple[BenchmarkRunSettingEntry, ...]:
        cursor = conn.execute(
            "SELECT setting_key, setting_value FROM benchmark_run_settings "
            "WHERE run_id = ? ORDER BY setting_key",
            (run_id,),
        )
        return tuple(
            BenchmarkRunSettingEntry(setting_key=row[0], setting_value=row[1])
            for row in cursor.fetchall()
        )


_SELECT_RUN_HEADER_COLUMNS = """
    SELECT run_id, run_name, timestamp, run_mode, status, total_tasks, completed_tasks,
           total_elapsed_ms, run_analysis, judge_provider_id, judge_provider_name,
           embedding_provider_name, embedding_model_name, schema_version, created_at,
           started_at, finished_at
    FROM benchmark_runs
"""


def _row_to_benchmark_run(
    row: sqlite3.Row,
    *,
    models: tuple[BenchmarkRunModelEntry, ...] = (),
    providers: tuple[BenchmarkRunProviderEntry, ...] = (),
    settings_snapshot: tuple[BenchmarkRunSettingEntry, ...] = (),
) -> BenchmarkRun:
    """Assemble a ``BenchmarkRun`` from one ``benchmark_runs`` row plus its snapshots."""
    return BenchmarkRun(
        run_id=row[0],
        run_name=row[1],
        timestamp=row[2],
        run_mode=RunMode(row[3]),
        status=RunStatus(row[4]),
        total_tasks=row[5],
        completed_tasks=row[6],
        total_elapsed_ms=row[7],
        run_analysis=row[8],
        judge_provider_id=row[9],
        judge_provider_name=row[10],
        embedding_provider_name=row[11],
        embedding_model_name=row[12],
        schema_version=row[13],
        created_at=row[14],
        started_at=row[15],
        finished_at=row[16],
        models=models,
        providers=providers,
        settings_snapshot=settings_snapshot,
    )


def _build_status_patch_assignments(
    patch: RunStatusPatch,
) -> tuple[list[str], list[object]]:
    """Build the ``SET`` clause fragments and bound values for a non-``None`` patch."""
    assignments: list[str] = []
    values: list[object] = []
    if patch.status is not None:
        assignments.append("status = ?")
        values.append(patch.status.value)
    if patch.completed_tasks is not None:
        assignments.append("completed_tasks = ?")
        values.append(patch.completed_tasks)
    if patch.total_elapsed_ms is not None:
        assignments.append("total_elapsed_ms = ?")
        values.append(patch.total_elapsed_ms)
    if patch.run_analysis is not None:
        assignments.append("run_analysis = ?")
        values.append(patch.run_analysis)
    if patch.started_at is not None:
        assignments.append("started_at = ?")
        values.append(patch.started_at)
    if patch.finished_at is not None:
        assignments.append("finished_at = ?")
        values.append(patch.finished_at)
    return assignments, values
