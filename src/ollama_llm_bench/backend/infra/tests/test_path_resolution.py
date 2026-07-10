"""Tests proving STORY-004-AC-5: path resolution over a fake ``PlatformDetector``.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md``
§9 (rotation, retention, and locations); ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md``
§8.1 (application-log rotation policy).
"""

import logging.handlers

from ollama_llm_bench.backend.infra._internal.logging_setup import _QUEUE_LISTENER_ATTR
from ollama_llm_bench.backend.infra.api import (
    app_log_dir,
    app_log_path,
    configure_logging,
    run_log_dir,
)
from ollama_llm_bench.backend.infra.protocols import PlatformDetector

_EXPECTED_ROTATION_MAX_BYTES = 10 * 1024 * 1024
_EXPECTED_ROTATION_BACKUP_COUNT = 5


def test_log_paths_resolve_from_platform_detector_and_rotation_is_configured(
    fake_platform_detector: PlatformDetector,
) -> None:
    """Proves: STORY-004-AC-5

    Given a fake ``PlatformDetector`` supplying a known ``app_data_root``, the
    path-resolution surface returns ``<app_data_root>/logs/app/app.log`` and
    ``<app_data_root>/logs/run/`` as the resolved locations ``configure_logging``
    writes into, and ``app.log``'s rotation is configured with a 10 MB trigger
    and 5 retained backups.
    """
    # Arrange
    expected_app_log_path = fake_platform_detector.app_data_root / "logs" / "app" / "app.log"
    expected_run_log_dir = fake_platform_detector.app_data_root / "logs" / "run"

    # Act
    resolved_app_log_path = app_log_path(fake_platform_detector)
    resolved_app_log_dir = app_log_dir(fake_platform_detector)
    resolved_run_log_dir = run_log_dir(fake_platform_detector)
    configure_logging(app_log_file=resolved_app_log_path)
    app_logger = logging.getLogger("app")
    queue_listener = getattr(app_logger, _QUEUE_LISTENER_ATTR)
    rotating_handler = next(
        handler
        for handler in queue_listener.handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    )

    # Assert
    assert resolved_app_log_path == expected_app_log_path
    assert resolved_app_log_dir == expected_app_log_path.parent
    assert resolved_run_log_dir == expected_run_log_dir
    assert rotating_handler.maxBytes == _EXPECTED_ROTATION_MAX_BYTES
    assert rotating_handler.backupCount == _EXPECTED_ROTATION_BACKUP_COUNT
