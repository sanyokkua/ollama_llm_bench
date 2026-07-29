"""Tests proving STORY-079: the single-instance advisory lock on ``<app-data>/.instance.lock``.

Source of truth: ``docs/v3_specification/12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md``
§5 (file-lock policy, SPEC-035 stale-owner recovery) and §6 (multi-instance handling).
"""

import os
from pathlib import Path

import msgspec

from ollama_llm_bench.backend.infra._internal.instance_lock import LOCK_FILENAME
from ollama_llm_bench.backend.infra.api import acquire_instance_lock
from ollama_llm_bench.backend.infra.models import (
    InstanceLockHandle,
    InstanceLockOutcome,
    InstanceLockRecord,
)
from ollama_llm_bench.backend.infra.tests.conftest import FAKE_NOW_UTC, FakeClock


def test_first_acquisition_succeeds_and_records_pid_and_timestamp(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """Proves: STORY-079-AC-1

    Given a data directory with no live lock owner, acquisition succeeds and
    ``<app-data>/.instance.lock`` records this process's PID and the clock's
    start timestamp.
    """
    # Arrange
    expected_lock_file = tmp_path / LOCK_FILENAME

    # Act
    result = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert result.lock is not None
    held_locks.append(result.lock)
    written = msgspec.json.decode(expected_lock_file.read_bytes(), type=InstanceLockRecord)

    # Assert
    assert result.outcome is InstanceLockOutcome.ACQUIRED
    assert result.lock_file == expected_lock_file
    assert written == InstanceLockRecord(pid=os.getpid(), started_at=FAKE_NOW_UTC)
