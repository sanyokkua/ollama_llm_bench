"""Authoritative acceptance-criteria tests for STORY-005's app-data-dir creation.

Covers STORY-005-AC-4, EC-PLAT-1, EC-PLAT-4 — see
``docs/stories/story-005-platform-detector-and-app-data-paths.md``.
"""

import errno
import os
from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.platform import create_app_data_dir

# `mkdir(mode=0o500)` has no effect on a process running as root — root bypasses
# filesystem permission checks entirely, so the permission-failure branch cannot
# be observed under a root-run sandbox/CI. Guard those cases with a clear skip
# reason rather than let them fail spuriously (mirrors the coder's test_sanity.py).
_RUNNING_AS_ROOT = hasattr(os, "getuid") and os.getuid() == 0


def _make_read_only_parent(tmp_path: Path) -> Path:
    """Create a read-only-for-owner parent directory under ``tmp_path``."""
    parent = tmp_path / "locked"
    parent.mkdir(mode=0o500)
    return parent


@pytest.mark.skipif(_RUNNING_AS_ROOT, reason="root bypasses filesystem permission checks")
def test_app_data_dir_creation_is_idempotent_and_raises_named_error_on_permission_failure(
    tmp_path: Path,
) -> None:
    """Proves: STORY-005-AC-4

    Creating ``<app-data>`` is recursive and idempotent (a second call on an
    already-existing tree does not raise), and a simulated permission failure
    raises a ``ConfigurationError`` whose message names the attempted path.
    """
    # Arrange — idempotency leg
    writable_target = tmp_path / "nested" / "OllamaLLMBench"

    # Act — idempotency leg
    first_result = create_app_data_dir(writable_target)
    second_result = create_app_data_dir(writable_target)  # must not raise

    # Assert — idempotency leg
    assert first_result == writable_target
    assert second_result == writable_target
    assert writable_target.is_dir()

    # Arrange — permission-failure leg
    parent = _make_read_only_parent(tmp_path)
    unwritable_target = parent / "OllamaLLMBench"
    try:
        # Act / Assert — permission-failure leg
        with pytest.raises(ConfigurationError) as exc_info:
            create_app_data_dir(unwritable_target)
        assert str(unwritable_target) in str(exc_info.value)
    finally:
        parent.chmod(0o700)


@pytest.mark.skipif(_RUNNING_AS_ROOT, reason="root bypasses filesystem permission checks")
def test_app_data_dir_creation_permission_failure_and_non_ascii_path(tmp_path: Path) -> None:
    """Proves: STORY-005-AC-4

    Also exercises EC-PLAT-1 and EC-PLAT-4. A permission failure raises a
    ``ConfigurationError`` naming the attempted path (EC-PLAT-1), and a path
    containing non-ASCII characters is created and
    resolved without a ``UnicodeError`` or mojibake (EC-PLAT-4).
    """
    # Arrange — permission-failure leg (EC-PLAT-1)
    parent = _make_read_only_parent(tmp_path)
    unwritable_target = parent / "OllamaLLMBench"
    try:
        # Act / Assert — permission-failure leg
        with pytest.raises(ConfigurationError) as exc_info:
            create_app_data_dir(unwritable_target)
        assert str(unwritable_target) in str(exc_info.value)
    finally:
        parent.chmod(0o700)

    # Arrange — non-ASCII leg (EC-PLAT-4)
    non_ascii_segment = "Пользователь_😀"
    non_ascii_target = tmp_path / non_ascii_segment / "OllamaLLMBench"

    # Act
    result_path = create_app_data_dir(non_ascii_target)

    # Assert
    assert result_path == non_ascii_target
    assert non_ascii_target.is_dir()
    assert non_ascii_segment in str(result_path)


def test_app_data_dir_creation_raises_named_error_on_disk_space_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves: STORY-005-AC-4

    Also exercises EC-PLAT-1: a disk-space failure (``OSError`` with
    ``errno.ENOSPC``) during directory creation raises a ``ConfigurationError``
    whose message names both the attempted path and the actual failure reason
    reported by the OS — not a hardcoded "permission denied" string — proving
    the reason is genuinely surfaced from the underlying exception.
    """
    # Arrange
    target = tmp_path / "nested" / "OllamaLLMBench"
    no_space_error = OSError(errno.ENOSPC, "No space left on device")

    def _raise_no_space(self: Path, *args: object, **kwargs: object) -> None:
        raise no_space_error

    monkeypatch.setattr(Path, "mkdir", _raise_no_space)

    # Act / Assert
    with pytest.raises(ConfigurationError) as exc_info:
        create_app_data_dir(target)
    message = str(exc_info.value)
    assert str(target) in message
    assert "permission denied" not in message.lower()
    assert "space" in message.lower()
