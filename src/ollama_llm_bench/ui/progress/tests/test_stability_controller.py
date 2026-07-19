"""Colocated ``StabilityController`` tests for ``ui/progress/``
(STORY-058-AC-6, EC-PROV-3, EC-PROV-4, EC-PROV-4b)."""

from typing import TYPE_CHECKING

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.events import (
    SIGNAL_JUDGE_MODEL_EXCLUDED,
    SIGNAL_MODEL_STABILITY_CHANGED,
    JudgeModelExcludedEvent,
    ModelStabilityChangedEvent,
)
from ollama_llm_bench.ui.progress._internal.stability_controller import StabilityController
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus

if TYPE_CHECKING:
    from ollama_llm_bench.ui.progress.models import StabilityViewModel

_EXPECTED_CONSECUTIVE_TIMEOUTS = 3


def _stability_event(*, model_state: str, provider_state: str) -> ModelStabilityChangedEvent:
    return ModelStabilityChangedEvent(
        run_id=1,
        provider_id="prov-1",
        model_name="model-1",
        model_state=model_state,
        model_consecutive_successes=0,
        model_promotion_threshold=3,
        provider_state=provider_state,
        provider_consecutive_failures=0,
        provider_cooldown_remaining_ms=0,
    )


def _bind(
    *, gateway: FakeProgressGateway, event_bus: FakeEventBus, qtbot: QtBot
) -> tuple[StabilityController, ProgressView]:
    view = ProgressView()
    qtbot.addWidget(view)
    controller = StabilityController(gateway=gateway, event_bus=event_bus)
    controller.bind(view)
    return controller, view


_BAND_CASES = [
    ("ok", "closed", "ok", "closed"),
    ("warn", "closed", "warn", "closed"),
    ("excluded", "closed", "excluded", "closed"),
    ("ok", "probing", "ok", "warn"),
    ("ok", "tripped", "ok", "open"),
]


@pytest.mark.parametrize(
    ("model_state", "provider_state", "expected_model_band", "expected_provider_band"),
    _BAND_CASES,
)
def test_stability_bands_per_signal(  # noqa: PLR0913  # one parametrize table (4 columns)
    # plus three independently-overridable fixtures
    model_state: str,
    provider_state: str,
    expected_model_band: str,
    expected_provider_band: str,
    qtbot: QtBot,
    fake_gateway: FakeProgressGateway,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-058-AC-6

    For each model-/provider-stability condition carried by
    `_model_stability_changed`, the StabilityController derives the specified
    band (EC-PROV-3: breaker OPEN -> provider band "open" with retry-probe
    link; EC-PROV-4: role=INFERENCE exclusion reached -> model band
    "excluded").
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    captured: list[StabilityViewModel] = []
    view.apply_stability = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(
        SIGNAL_MODEL_STABILITY_CHANGED,
        _stability_event(model_state=model_state, provider_state=provider_state),
    )

    # Assert
    vm = captured[-1]
    assert vm.model_band == expected_model_band
    assert vm.provider_band == expected_provider_band
    assert vm.show_retry_probe == (expected_provider_band == "open")


def test_provider_open_band_shows_retry_probe_link(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-6

    Covers EC-PROV-3. When the provider band is "open", `show_retry_probe` is set so the
    inline retry-probe link renders.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    captured: list[StabilityViewModel] = []
    view.apply_stability = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(
        SIGNAL_MODEL_STABILITY_CHANGED, _stability_event(model_state="ok", provider_state="tripped")
    )

    # Assert
    assert captured[-1].show_retry_probe is True


def test_judge_model_excluded_callout_persists_across_later_stability_events(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-058-AC-6

    Covers EC-PROV-4b. Once `_judge_model_excluded` fires, the red judge-exclusion callout is
    shown and persists for the run -- a later `_model_stability_changed`
    event (for the unrelated role=INFERENCE bucket, still OK) never clears
    it.
    """
    # Arrange
    _controller, view = _bind(gateway=fake_gateway, event_bus=fake_event_bus, qtbot=qtbot)
    captured: list[StabilityViewModel] = []
    view.apply_stability = captured.append  # type: ignore[method-assign, assignment]

    # Act -- the judge model is excluded
    fake_event_bus.emit(
        SIGNAL_JUDGE_MODEL_EXCLUDED,
        JudgeModelExcludedEvent(
            run_id=1,
            provider_id="prov-1",
            model_name="judge-model",
            consecutive_timeouts=_EXPECTED_CONSECUTIVE_TIMEOUTS,
            exclusion_reason="max-budget timeouts",
            excluded_at=0,
            remaining_tasks_affected=4,
        ),
    )
    assert captured[-1].judge_excluded_text is not None
    assert str(_EXPECTED_CONSECUTIVE_TIMEOUTS) in captured[-1].judge_excluded_text

    # Act -- an unrelated, healthy test-model stability update arrives later
    fake_event_bus.emit(
        SIGNAL_MODEL_STABILITY_CHANGED, _stability_event(model_state="ok", provider_state="closed")
    )

    # Assert -- the judge-exclusion callout is still present
    assert captured[-1].model_band == "ok"
    assert captured[-1].judge_excluded_text is not None
