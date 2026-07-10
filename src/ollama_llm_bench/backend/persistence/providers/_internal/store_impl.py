"""The concrete ``ProvidersStore`` implementation over the single-writer connection.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.4; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §4.2-§4.3,
§7.
"""

from collections.abc import Callable
import sqlite3
import threading
from typing import Final
import uuid

from ollama_llm_bench.backend.domain import (
    InferenceTestOutcome,
    ProviderConfig,
    ProviderConfigDraft,
    ProviderId,
    ProviderTestStatus,
    ProviderType,
)
from ollama_llm_bench.backend.errors import PersistenceError

__all__: list[str] = [
    "SqliteProvidersStore",
    "seed_builtin_providers",
]

_BUILTIN_PROVIDER_SEEDS: Final[tuple[tuple[str, str], ...]] = (
    ("Ollama (local)", "http://localhost:11434/v1"),
    ("LM Studio (local)", "http://localhost:1234/v1"),
    ("llama.cpp (local)", "http://localhost:8080/v1"),
)
"""The three built-in local providers' ``(name, base_url)`` pairs, in seed order
(``provider_order`` 0/1/2), per ``03_PERSISTENCE_SCHEMA.md`` §10."""

_SELECT_PROVIDER_COLUMNS = """
    SELECT provider_id, name, provider_type, enabled, base_url, api_key_raw,
           azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw,
           last_probe_status, last_probe_at, last_probe_reachable,
           last_probe_model_count, last_probe_message, last_inference_test_at,
           last_inference_test_outcome, last_inference_test_model,
           last_inference_test_message, provider_order
    FROM providers
"""


class SqliteProvidersStore:
    """``ProvidersStore`` over the single write connection and read-only factory.

    Satisfies the ``ProvidersStore`` Protocol structurally. Every method wraps
    ``sqlite3.Error`` (including ``sqlite3.IntegrityError`` from the
    ``UNIQUE (name)`` constraint) into ``PersistenceError``.
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

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Return every configured provider in display order, each with its
        manual model list.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute(_SELECT_PROVIDER_COLUMNS + " ORDER BY provider_order, name")
            rows = cursor.fetchall()
            return tuple(
                _row_to_provider_config(row, models=self._select_provider_models(conn, row[0]))
                for row in rows
            )
        except sqlite3.Error as exc:
            message = "failed to list providers"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()

    def get_by_name(self, name: str) -> ProviderConfig | None:
        """Return the provider whose ``name`` matches ``name``, or ``None``.

        Raises:
            PersistenceError: The underlying read failed.
        """
        conn = self._read_conn_factory()
        try:
            cursor = conn.execute(_SELECT_PROVIDER_COLUMNS + " WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row is None:
                return None
            models = self._select_provider_models(conn, row[0])
            return _row_to_provider_config(row, models=models)
        except sqlite3.Error as exc:
            message = f"failed to look up provider by name {name!r}"
            raise PersistenceError(message=message) from exc
        finally:
            conn.close()

    def add(self, draft: ProviderConfigDraft) -> ProviderId:
        """Insert a new provider with a fresh UUID4 ``provider_id``, returned
        only after commit.

        Raises:
            PersistenceError: A row named ``draft.name`` already exists, or
                the underlying write failed.
        """
        new_provider_id = str(uuid.uuid4())
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._insert_provider_row(new_provider_id, draft)
                self._insert_provider_models(new_provider_id, draft.default_models)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to add provider named {draft.name!r}"
                raise PersistenceError(message=message) from exc
        return new_provider_id

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        """Update every column but ``provider_id`` on the matching row.

        Raises:
            PersistenceError: No row with ``provider_id`` exists, the update
                would duplicate another row's ``name``, or the underlying
                write failed.
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._update_provider_row(provider_id, config)
                if cursor.rowcount == 0:
                    message = f"provider {provider_id} does not exist"
                    raise PersistenceError(message=message)
                self._write_conn.execute(
                    "DELETE FROM provider_models WHERE provider_id = ?", (provider_id,)
                )
                self._insert_provider_models(provider_id, config.default_models)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to update provider {provider_id}"
                raise PersistenceError(message=message) from exc
            except PersistenceError:
                self._write_conn.rollback()
                raise

    def delete(self, provider_id: ProviderId) -> None:
        """Delete the provider row; ``ON DELETE CASCADE`` removes its
        ``provider_models`` and ``model_capabilities`` rows.

        Raises:
            PersistenceError: The underlying write failed.
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_conn.execute(
                    "DELETE FROM providers WHERE provider_id = ?", (provider_id,)
                )
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = f"failed to delete provider {provider_id}"
                raise PersistenceError(message=message) from exc

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Replace the entire provider catalog atomically.

        Raises:
            PersistenceError: ``configs`` contains a duplicate ``name``, or
                the underlying write failed.
        """
        with self._lock:
            self._write_conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_conn.execute("DELETE FROM providers")
                for config in configs:
                    self._insert_provider_row_from_config(config)
                    self._insert_provider_models(config.provider_id, config.default_models)
                self._write_conn.commit()
            except sqlite3.Error as exc:
                self._write_conn.rollback()
                message = "failed to replace provider catalog"
                raise PersistenceError(message=message) from exc

    def _insert_provider_row(self, provider_id: ProviderId, draft: ProviderConfigDraft) -> None:
        self._write_conn.execute(
            """
            INSERT INTO providers (
                provider_id, name, provider_type, enabled, base_url, api_key_raw,
                azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw,
                provider_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                draft.name,
                draft.provider_type.value,
                int(draft.enabled),
                draft.base_url,
                draft.api_key_raw,
                draft.azure_endpoint_raw,
                draft.azure_deployment_raw,
                draft.azure_api_version_raw,
                draft.provider_order,
            ),
        )

    def _insert_provider_row_from_config(self, config: ProviderConfig) -> None:
        self._write_conn.execute(
            """
            INSERT INTO providers (
                provider_id, name, provider_type, enabled, base_url, api_key_raw,
                azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw,
                last_probe_status, last_probe_at, last_probe_reachable,
                last_probe_model_count, last_probe_message, last_inference_test_at,
                last_inference_test_outcome, last_inference_test_model,
                last_inference_test_message, provider_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config.provider_id,
                config.name,
                config.provider_type.value,
                int(config.enabled),
                config.base_url,
                config.api_key_raw,
                config.azure_endpoint_raw,
                config.azure_deployment_raw,
                config.azure_api_version_raw,
                config.last_probe_status.value,
                config.last_probe_at,
                _bool_to_int_or_none(value=config.last_probe_reachable),
                config.last_probe_model_count,
                config.last_probe_message,
                config.last_inference_test_at,
                config.last_inference_test_outcome.value
                if config.last_inference_test_outcome is not None
                else None,
                config.last_inference_test_model,
                config.last_inference_test_message,
                config.provider_order,
            ),
        )

    def _update_provider_row(
        self, provider_id: ProviderId, config: ProviderConfig
    ) -> sqlite3.Cursor:
        return self._write_conn.execute(
            """
            UPDATE providers SET
                name = ?, provider_type = ?, enabled = ?, base_url = ?, api_key_raw = ?,
                azure_endpoint_raw = ?, azure_deployment_raw = ?, azure_api_version_raw = ?,
                last_probe_status = ?, last_probe_at = ?, last_probe_reachable = ?,
                last_probe_model_count = ?, last_probe_message = ?, last_inference_test_at = ?,
                last_inference_test_outcome = ?, last_inference_test_model = ?,
                last_inference_test_message = ?, provider_order = ?
            WHERE provider_id = ?
            """,
            (
                config.name,
                config.provider_type.value,
                int(config.enabled),
                config.base_url,
                config.api_key_raw,
                config.azure_endpoint_raw,
                config.azure_deployment_raw,
                config.azure_api_version_raw,
                config.last_probe_status.value,
                config.last_probe_at,
                _bool_to_int_or_none(value=config.last_probe_reachable),
                config.last_probe_model_count,
                config.last_probe_message,
                config.last_inference_test_at,
                config.last_inference_test_outcome.value
                if config.last_inference_test_outcome is not None
                else None,
                config.last_inference_test_model,
                config.last_inference_test_message,
                config.provider_order,
                provider_id,
            ),
        )

    def _insert_provider_models(self, provider_id: ProviderId, models: tuple[str, ...]) -> None:
        for order, model_name in enumerate(models):
            self._write_conn.execute(
                "INSERT INTO provider_models (provider_id, model_name, model_order) "
                "VALUES (?, ?, ?)",
                (provider_id, model_name, order),
            )

    def _select_provider_models(
        self, conn: sqlite3.Connection, provider_id: str
    ) -> tuple[str, ...]:
        cursor = conn.execute(
            "SELECT model_name FROM provider_models WHERE provider_id = ? ORDER BY model_order",
            (provider_id,),
        )
        return tuple(row[0] for row in cursor.fetchall())


def _bool_to_int_or_none(*, value: bool | None) -> int | None:
    """Convert an optional bool to SQLite's ``0``/``1``/``NULL`` tri-state."""
    if value is None:
        return None
    return int(value)


def _row_to_provider_config(row: sqlite3.Row, *, models: tuple[str, ...]) -> ProviderConfig:
    """Assemble a ``ProviderConfig`` from one ``providers`` row plus its model list."""
    return ProviderConfig(
        provider_id=row[0],
        name=row[1],
        provider_type=ProviderType(row[2]),
        enabled=bool(row[3]),
        base_url=row[4],
        api_key_raw=row[5],
        azure_endpoint_raw=row[6],
        azure_deployment_raw=row[7],
        azure_api_version_raw=row[8],
        default_models=models,
        last_probe_status=ProviderTestStatus(row[9]),
        last_probe_at=row[10],
        last_probe_reachable=bool(row[11]) if row[11] is not None else None,
        last_probe_model_count=row[12],
        last_probe_message=row[13],
        last_inference_test_at=row[14],
        last_inference_test_outcome=InferenceTestOutcome(row[15]) if row[15] is not None else None,
        last_inference_test_model=row[16],
        last_inference_test_message=row[17],
        provider_order=row[18],
    )


def seed_builtin_providers(write_conn: sqlite3.Connection, lock: threading.Lock) -> None:
    """Seed the three built-in local providers in one transaction.

    Each of Ollama, LM Studio, and llama.cpp is inserted as an
    ``openai_compatible`` provider, ``enabled = 1``, with no API key, a fresh
    UUID4 ``provider_id``, and ``provider_order`` 0/1/2 respectively, per
    ``03_PERSISTENCE_SCHEMA.md`` §10. Safe to call repeatedly — each call
    generates fresh ids, so a caller wanting a re-seed (Reset to Defaults)
    first clears ``providers`` itself.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.

    Raises:
        PersistenceError: The underlying write failed.
    """
    with lock:
        write_conn.execute("BEGIN IMMEDIATE")
        try:
            for order, (name, base_url) in enumerate(_BUILTIN_PROVIDER_SEEDS):
                write_conn.execute(
                    """
                    INSERT INTO providers (
                        provider_id, name, provider_type, enabled, base_url, provider_order
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        name,
                        ProviderType.OPENAI_COMPATIBLE.value,
                        base_url,
                        order,
                    ),
                )
            write_conn.commit()
        except sqlite3.Error as exc:
            write_conn.rollback()
            message = "failed to seed built-in providers"
            raise PersistenceError(message=message) from exc
