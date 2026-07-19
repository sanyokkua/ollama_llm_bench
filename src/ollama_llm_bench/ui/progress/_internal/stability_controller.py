"""``StabilityController`` -- the model- and provider-stability callouts and the
judge-model exclusion callout (``04_Progress_Widget/implementation_structure.md`` §4.4;
description.md §6.2, §6.3, §6.4; STORY-058-AC-6; EC-PROV-3, EC-PROV-4, EC-PROV-4b).

Depends only on ``ProgressGateway`` plus ``EventBus`` (D-R-06) -- never a raw backend
Store/Service Protocol, and never ``AdaptiveTimeoutService``/the circuit breaker
directly. The "retry probe" action calls ``ProgressGateway.manual_provider_probe()``.
"""

import structlog

from ollama_llm_bench.backend.events import (
    SIGNAL_JUDGE_MODEL_EXCLUDED,
    SIGNAL_MODEL_STABILITY_CHANGED,
    EventBus,
    JudgeModelExcludedEvent,
    ModelStabilityChangedEvent,
)
from ollama_llm_bench.ui.progress._internal.select import apply_judge_excluded, select_stability
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import StabilityViewModel
from ollama_llm_bench.ui.progress.protocols import ProgressGateway

__all__: list[str] = ["StabilityController"]

logger = structlog.get_logger(__name__)

_EMPTY_STABILITY_VM = StabilityViewModel(
    model_band="ok",
    model_text="—",
    provider_band="closed",
    provider_text="—",
    show_retry_probe=False,
    show_open_settings=False,
    judge_excluded_text=None,
)


class StabilityController:
    """Subscribes ``_model_stability_changed``/``_judge_model_excluded``; the judge
    exclusion callout is sticky for the remainder of the run (EC-PROV-4b)."""

    def __init__(self, *, gateway: ProgressGateway, event_bus: EventBus) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._view: ProgressView | None = None
        self._current_vm = _EMPTY_STABILITY_VM
        self._judge_excluded_text: str | None = None
        logger.debug("stability_controller_constructed")

    def bind(self, view: ProgressView) -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime."""
        self._view = view
        self._event_bus.subscribe(
            SIGNAL_MODEL_STABILITY_CHANGED, self._on_model_stability_changed, owner=view
        )
        self._event_bus.subscribe(
            SIGNAL_JUDGE_MODEL_EXCLUDED, self._on_judge_model_excluded, owner=view
        )

    def on_retry_probe_clicked(self) -> None:
        """The provider-band ``OPEN`` callout's "retry probe" inline link (§6.3)."""
        logger.debug("stability_retry_probe_clicked")
        self._gateway.manual_provider_probe()

    def _on_model_stability_changed(self, payload: object) -> None:
        if not isinstance(payload, ModelStabilityChangedEvent):
            return
        logger.debug("stability_event_received", signal_name=SIGNAL_MODEL_STABILITY_CHANGED)
        vm = select_stability(payload)
        if self._judge_excluded_text is not None:
            vm = StabilityViewModel(
                model_band=vm.model_band,
                model_text=vm.model_text,
                provider_band=vm.provider_band,
                provider_text=vm.provider_text,
                show_retry_probe=vm.show_retry_probe,
                show_open_settings=vm.show_open_settings,
                judge_excluded_text=self._judge_excluded_text,
            )
        self._apply(vm)

    def _on_judge_model_excluded(self, payload: object) -> None:
        if not isinstance(payload, JudgeModelExcludedEvent):
            return
        logger.debug("stability_event_received", signal_name=SIGNAL_JUDGE_MODEL_EXCLUDED)
        vm = apply_judge_excluded(self._current_vm, payload)
        self._judge_excluded_text = vm.judge_excluded_text
        self._apply(vm)

    def _apply(self, vm: StabilityViewModel) -> None:
        self._current_vm = vm
        logger.debug("stability_applied", model_band=vm.model_band, provider_band=vm.provider_band)
        if self._view is not None:
            self._view.apply_stability(vm)
