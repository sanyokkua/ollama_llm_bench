"""Widget-local Synthetic size validation (STORY-071).

``description.md`` §6 / ``synthetic.md`` §4: the SYNTHETIC hard error
"Select at least one input size and one output size." No concrete backend
``RunValidator`` exists yet (``protocols.py`` defers it to a future story), so
this decorator layers the one Synthetic-only rule this widget owns over the
injected validator. The future concrete validator must not duplicate this rule
without removing this wrapper.
"""

from typing import Final

from ollama_llm_bench.backend.domain import RunMode, RunStartRequest
from ollama_llm_bench.ui.new_benchmark.models import RunValidationSeverity, ValidationEntry
from ollama_llm_bench.ui.new_benchmark.protocols import RunValidator

__all__: list[str] = ["MISSING_SIZES_MESSAGE", "SyntheticSizeRuleValidator"]

MISSING_SIZES_MESSAGE: Final[str] = "Select at least one input size and one output size."


class SyntheticSizeRuleValidator:
    """Decorate the injected ``RunValidator`` with the §6 Synthetic size rule."""

    def __init__(self, *, inner: RunValidator) -> None:
        self._inner = inner

    def validate(self, request: RunStartRequest) -> tuple[ValidationEntry, ...]:
        """Return the local size-rule entry (when violated) plus every inner entry.

        fast-synchronous; pure; never raises (invalid configuration is data).
        """
        local: tuple[ValidationEntry, ...] = ()
        if request.run_mode is RunMode.SYNTHETIC:
            config = request.performance_config
            if config is None or not config.input_sizes or not config.output_sizes:
                local = (
                    ValidationEntry(
                        severity=RunValidationSeverity.HARD_ERROR,
                        message=MISSING_SIZES_MESSAGE,
                    ),
                )
        return local + self._inner.validate(request)
