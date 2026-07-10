"""Property test proving additive-only schema evolution never mutates an existing row.

Source of truth: STORY-008 acceptance criterion AC-4 and
``docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md`` EC-PERSIST-1 (the
older-same-major additive branch).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading

from hypothesis import given, settings, strategies as st
import pytest

from ollama_llm_bench.backend.persistence.app_settings._internal import version_check
from ollama_llm_bench.backend.persistence.app_settings._internal.schema_ddl import SchemaStep

# --------------------------------------------------------------------------------- #
# A scratch table, independent of the real 15-table schema, used purely to prove the
# apply mechanism itself (_apply_additive_steps) is additive-only and safe. Each
# Hypothesis example rebuilds this table fresh in its own tmp_path database file.
# --------------------------------------------------------------------------------- #

_SEED_ROWS: tuple[tuple[int, str, int], ...] = (
    (1, "alpha", 100),
    (2, "beta", 200),
    (3, "gamma", 300),
)

_NEW_COLUMN_NAMES: tuple[str, ...] = ("evolved_note", "evolved_priority", "evolved_flag")


def _make_scratch_db(db_path: Path) -> tuple[sqlite3.Connection, threading.Lock]:
    """Create a scratch database file with a seeded table and an app_meta row.

    _apply_additive_steps only touches the schema-evolution ladder's own
    statements and the app_meta.schema_version update, so a minimal app_meta
    row is enough context for it to run against.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    lock = threading.Lock()
    conn.execute(
        "CREATE TABLE scratch_widgets "
        "(id INTEGER PRIMARY KEY, label TEXT NOT NULL, weight INTEGER NOT NULL)"
    )
    conn.executemany("INSERT INTO scratch_widgets (id, label, weight) VALUES (?, ?, ?)", _SEED_ROWS)
    conn.execute(
        "CREATE TABLE app_meta (id INTEGER PRIMARY KEY CHECK (id = 1), "
        "schema_version INTEGER NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO app_meta (id, schema_version, created_at) VALUES (1, 1, '2026-01-01T00:00:00+00:00')"
    )
    return conn, lock


def _synthetic_step(*, from_version: int, column_name: str, default: str) -> SchemaStep:
    """Build one synthetic ADD COLUMN additive step for the scratch table."""
    return SchemaStep(
        from_version=from_version,
        to_version=from_version + 1,
        statements=(
            f"ALTER TABLE scratch_widgets ADD COLUMN {column_name} TEXT DEFAULT '{default}'",
        ),
    )


@st.composite
def _additive_step_sequences(draw: st.DrawFn) -> tuple[SchemaStep, ...]:
    """Generate a random-length ordered sequence of synthetic additive steps.

    Each step is a distinct ADD COLUMN on the same scratch table, chained
    from_version -> to_version so the real _apply_additive_steps ladder-walk
    logic drives every step in sequence.
    """
    step_count = draw(st.integers(min_value=1, max_value=len(_NEW_COLUMN_NAMES)))
    defaults = draw(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=0, max_size=8
            ),
            min_size=step_count,
            max_size=step_count,
        )
    )
    return tuple(
        _synthetic_step(
            from_version=index + 1, column_name=_NEW_COLUMN_NAMES[index], default=default
        )
        for index, default in enumerate(defaults)
    )


def _new_column_values(conn: sqlite3.Connection, *, column_name: str) -> set[str | None]:
    """Return the distinct values a synthetic new column holds across every row.

    ``column_name`` is always one of the fixed ``_NEW_COLUMN_NAMES`` entries
    generated internally by this test module, never user input.
    """
    query = f"SELECT {column_name} FROM scratch_widgets"  # noqa: S608  # fixed internal column name, not user input
    return {row[0] for row in conn.execute(query).fetchall()}


def _declared_default(step: SchemaStep) -> str:
    """Extract the literal DEFAULT value embedded in a synthetic step's DDL."""
    return step.statements[0].rsplit("DEFAULT '", 1)[1].rstrip("'")


def _assert_new_column_is_null_or_default(
    conn: sqlite3.Connection, *, step: SchemaStep, column_name: str
) -> None:
    """Assert every row's value for one newly added column is NULL or its DEFAULT."""
    values = _new_column_values(conn, column_name=column_name)
    assert values <= {_declared_default(step), None}


def _assert_every_new_column_is_null_or_default(
    conn: sqlite3.Connection, *, steps: tuple[SchemaStep, ...]
) -> None:
    """Assert every step's new column is NULL/DEFAULT-only, across all applied steps."""
    column_names = _NEW_COLUMN_NAMES[: len(steps)]
    for step, column_name in zip(steps, column_names, strict=True):
        _assert_new_column_is_null_or_default(conn, step=step, column_name=column_name)


@contextmanager
def _patched_schema_ladder(*, steps: tuple[SchemaStep, ...]) -> Iterator[None]:
    """Temporarily install the generated steps as the module's evolution ladder.

    A plain context manager (not the function-scoped ``monkeypatch`` fixture)
    is used because Hypothesis flags function-scoped fixtures as unsafe to
    reuse across generated examples within one ``@given`` invocation.

    ``_apply_additive_steps`` reads ``ADDITIVE_STEPS`` and ``EXPECTED_SCHEMA_VERSION``
    as its own module-level globals, not as parameters — both are patched here
    so the real ladder-walk loop (which iterates ``ADDITIVE_STEPS`` and stops
    once ``version >= EXPECTED_SCHEMA_VERSION``) walks through every generated
    synthetic step. ``EXPECTED_SCHEMA_VERSION`` is 1 in the real schema today,
    with no older version or declared step to evolve from, so this is the only
    way to exercise a multi-step ladder against the real function.
    """
    original_steps = getattr(version_check, "ADDITIVE_STEPS")  # noqa: B009  # patching a module attribute not in its __all__
    original_version = getattr(version_check, "EXPECTED_SCHEMA_VERSION")  # noqa: B009  # same
    setattr(version_check, "ADDITIVE_STEPS", steps)  # noqa: B010  # same
    setattr(version_check, "EXPECTED_SCHEMA_VERSION", steps[-1].to_version)  # noqa: B010  # same
    try:
        yield
    finally:
        setattr(version_check, "ADDITIVE_STEPS", original_steps)  # noqa: B010  # same
        setattr(version_check, "EXPECTED_SCHEMA_VERSION", original_version)  # noqa: B010  # same


@given(steps=_additive_step_sequences())
@settings(max_examples=50, deadline=None)
def test_additive_steps_never_mutate_existing_rows(
    steps: tuple[SchemaStep, ...],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Proves: STORY-008-AC-4

    For every ordered sequence of additive structural steps, applying them via
    the real _apply_additive_steps code path leaves every pre-existing row's
    original column values byte-identical to their pre-apply snapshot, and
    populates every new column on a pre-existing row with only its declared
    DEFAULT/NULL — never an UPDATE, backfill, or rewrite of existing data.
    """
    # Arrange
    db_path = tmp_path_factory.mktemp("schema_evolution") / "scratch.db"
    conn, lock = _make_scratch_db(db_path)
    try:
        before = conn.execute(
            "SELECT id, label, weight FROM scratch_widgets ORDER BY id"
        ).fetchall()

        # Act — exercising the real step-application code path, not a parallel reimplementation.
        with _patched_schema_ladder(steps=steps):
            version_check._apply_additive_steps(conn, lock, current=steps[0].from_version)

        # Assert: original column values are unchanged for every pre-existing row.
        after_original_columns = conn.execute(
            "SELECT id, label, weight FROM scratch_widgets ORDER BY id"
        ).fetchall()
        assert after_original_columns == before

        # Assert: every new column on a pre-existing row is NULL or its declared DEFAULT.
        _assert_every_new_column_is_null_or_default(conn, steps=steps)
    finally:
        conn.close()
