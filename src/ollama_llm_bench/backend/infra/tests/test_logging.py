"""Tests proving STORY-004-AC-2, AC-3, AC-4: the two-stream logging setup.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md``
§2 (the two log streams), §3 (logging configuration), §6 (bound context and correlation),
§7 (the redaction processor).
"""

import contextvars
import json
import logging
import threading
import time

import structlog

from ollama_llm_bench.backend.infra.api import app_log_path, configure_logging, open_run_log
from ollama_llm_bench.backend.infra.protocols import PlatformDetector

_QUEUE_DRAIN_WAIT_S = 0.5
_SECRET_API_KEY = "AKIAIOSFODNN7EXAMPLE"  # noqa: S105  # test fixture value, not a real credential


def _read_app_log_lines(platform_detector: PlatformDetector) -> list[dict[str, object]]:
    """Read and JSON-decode every record currently written to ``app.log``."""
    log_file = app_log_path(platform_detector)
    if not log_file.exists():
        return []
    lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def test_app_stream_is_redacted_and_run_stream_is_not(
    fake_platform_detector: PlatformDetector,
) -> None:
    """Proves: STORY-004-AC-2

    After ``configure_logging`` runs, a record emitted on the ``app.*`` namespace
    is written to ``<app-data>/logs/app/app.log`` with bound-context, level, and
    ISO-8601 UTC timestamp fields and has passed through ``redact_for_log``; a
    record emitted on a run-scoped ``run.*`` logger is written to
    ``<app-data>/logs/run/run_<run_id>_<unix_ts>.log`` and is not redacted — the
    raw secret survives.
    """
    # Arrange
    configure_logging(app_log_file=app_log_path(fake_platform_detector))
    app_logger = structlog.get_logger("app.test")

    # Act
    app_logger.info("provider_auth_attempt", api_key=_SECRET_API_KEY)
    time.sleep(_QUEUE_DRAIN_WAIT_S)
    with open_run_log(
        platform_detector=fake_platform_detector,
        run_id="run-1",
        correlation_id="corr-1",
        unix_ts=1_700_000_000,
    ) as run_logger:
        run_logger.info("provider_auth_attempt api_key=%s", _SECRET_API_KEY)

    app_records = _read_app_log_lines(fake_platform_detector)
    run_log_file = (
        fake_platform_detector.app_data_root / "logs" / "run" / "run_run-1_1700000000.log"
    )
    run_log_content = run_log_file.read_text(encoding="utf-8")

    # Assert
    assert len(app_records) == 1
    assert app_records[0]["api_key"] == "<redacted>"
    assert app_records[0]["level"] == "info"
    assert "timestamp" in app_records[0]
    assert _SECRET_API_KEY not in json.dumps(app_records[0])
    assert _SECRET_API_KEY in run_log_content


def test_run_stream_never_propagates_to_app_log(
    fake_platform_detector: PlatformDetector,
) -> None:
    """Proves: STORY-004-AC-3

    A record emitted on the ``run.*`` namespace never appears in ``app.log`` and
    a record emitted on the ``app.*`` namespace never appears in the run's log
    file — observed directly on file contents, not merely handler configuration.
    """
    # Arrange
    configure_logging(app_log_file=app_log_path(fake_platform_detector))
    app_logger = structlog.get_logger("app.test")

    # Act
    with open_run_log(
        platform_detector=fake_platform_detector,
        run_id="run-2",
        correlation_id="corr-2",
        unix_ts=1_700_000_100,
    ) as run_logger:
        run_logger.info("run_only_event")
        app_logger.info("app_only_event")
        time.sleep(_QUEUE_DRAIN_WAIT_S)

    app_records = _read_app_log_lines(fake_platform_detector)
    run_log_file = (
        fake_platform_detector.app_data_root / "logs" / "run" / "run_run-2_1700000100.log"
    )
    run_log_content = run_log_file.read_text(encoding="utf-8")

    # Assert
    assert "run_only_event" not in json.dumps(app_records)
    assert "app_only_event" not in run_log_content
    assert "run_only_event" in run_log_content
    assert any(record.get("event") == "app_only_event" for record in app_records)


def test_bound_run_context_propagates_across_worker_threads(
    fake_platform_detector: PlatformDetector,
) -> None:
    """Proves: STORY-004-AC-4

    Binding ``run_id``/``correlation_id`` once at run start via ``open_run_log``
    causes a record emitted from a different worker thread — started via
    ``contextvars.copy_context().run(...)`` within the bound scope — to carry
    both fields; after the ``with`` block exits, a new record carries neither.
    """
    # Arrange
    configure_logging(app_log_file=app_log_path(fake_platform_detector))
    app_logger = structlog.get_logger("app.worker")

    def _emit_from_worker() -> None:
        app_logger.info("worker_emitted_event")

    # Act
    with open_run_log(
        platform_detector=fake_platform_detector,
        run_id="run-3",
        correlation_id="corr-3",
        unix_ts=1_700_000_200,
    ):
        ctx = contextvars.copy_context()
        worker_thread = threading.Thread(target=lambda: ctx.run(_emit_from_worker))
        worker_thread.start()
        worker_thread.join()
        time.sleep(_QUEUE_DRAIN_WAIT_S)

    app_logger.info("after_run_closed_event")
    time.sleep(_QUEUE_DRAIN_WAIT_S)
    app_records = _read_app_log_lines(fake_platform_detector)
    bound_record = next(r for r in app_records if r.get("event") == "worker_emitted_event")
    unbound_record = next(r for r in app_records if r.get("event") == "after_run_closed_event")

    # Assert
    assert bound_record["run_id"] == "run-3"
    assert bound_record["correlation_id"] == "corr-3"
    assert "run_id" not in unbound_record
    assert "correlation_id" not in unbound_record


def test_configure_logging_called_twice_does_not_duplicate_handlers_or_records(
    fake_platform_detector: PlatformDetector,
) -> None:
    """Proves: STORY-004-AC-2

    Calling ``configure_logging`` twice is idempotent-safe: the ``app`` stdlib
    logger carries exactly one handler afterward, and a single log call after
    the second configuration produces exactly one line in ``app.log``, not two.
    """
    # Arrange
    log_file = app_log_path(fake_platform_detector)
    configure_logging(app_log_file=log_file)
    configure_logging(app_log_file=log_file)
    app_logger = structlog.get_logger("app.test")

    # Act
    app_logger.info("single_event")
    time.sleep(_QUEUE_DRAIN_WAIT_S)
    app_records = _read_app_log_lines(fake_platform_detector)

    # Assert
    assert len(logging.getLogger("app").handlers) == 1
    assert len(app_records) == 1
