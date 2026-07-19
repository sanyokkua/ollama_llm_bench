"""Unit tests for the Run Summary dialog factory (STORY-055-AC-7, AC-8)."""

from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ModelDescriptor,
    ProviderHealth,
    ReadinessState,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.ui.common_dialogs import make_run_summary_dialog
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator

_PROVIDER_ID = "dddddddd-0000-4000-8000-000000000000"

_ALL_UNREACHABLE_SNAPSHOT = AppReadinessSnapshot(
    overall=ReadinessState.NOT_READY,
    per_provider=(
        ProviderHealth(
            provider_id=_PROVIDER_ID,
            reachable=False,
            discovery_supported=True,
            model_count=None,
            last_probe_ms=5,
            probed_at=0,
        ),
    ),
    embedding_reachable=False,
)

_ALL_READY_SNAPSHOT = AppReadinessSnapshot(
    overall=ReadinessState.READY,
    per_provider=(
        ProviderHealth(
            provider_id=_PROVIDER_ID,
            reachable=True,
            discovery_supported=True,
            model_count=1,
            last_probe_ms=5,
            probed_at=0,
        ),
    ),
    embedding_reachable=True,
)

_REQUEST = RunStartRequest(
    run_mode=RunMode.SYNTHETIC,
    test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name="llama3"),),
)


def test_preflight_recheck_refuses_open_when_no_model_reachable() -> None:
    """Proves: STORY-055-AC-7

    Covers: EC-RUN-3

    Given the Run Summary dialog is asked to open, when its preflight re-check
    detects that no test model is reachable, then the dialog does not open --
    the factory returns None.
    """
    # Arrange
    gateway = FakeNewBenchmarkGateway()
    gateway.set_readiness(_ALL_UNREACHABLE_SNAPSHOT)
    # Act
    dialog = make_run_summary_dialog(
        gateway=gateway, run_validator=FakeRunValidator(entries=()), request=_REQUEST
    )
    # Assert
    assert dialog is None


def test_run_summary_dialog_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-055-AC-8

    Constructed via its own factory (make_run_summary_dialog) with a fake
    NewBenchmarkGateway and mounted under qtbot, no exception is raised, the
    dialog reports isVisible(), and no error/critical-level structlog record is
    captured.
    """
    # Arrange
    gateway = FakeNewBenchmarkGateway()
    gateway.set_readiness(_ALL_READY_SNAPSHOT)
    # Act
    with structlog.testing.capture_logs() as logs:
        dialog = make_run_summary_dialog(
            gateway=gateway, run_validator=FakeRunValidator(entries=()), request=_REQUEST
        )
        assert dialog is not None
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)
