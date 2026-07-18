"""``NewBenchmarkGateway`` and the locally-declared ``ModeVisibilityPolicy`` (D-R-06).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.2 (``NewBenchmarkGateway``, declared verbatim) and
``11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`` §6.2-§6.3. ``ModeVisibilityPolicy``
is declared locally rather than importing a backend class -- ``backend.mode_visibility``
exposes free functions (``is_visible``/``visible_sections``), not a Protocol type; any
object exposing a matching ``visible_sections`` callable (including the backend module
itself, structurally) satisfies this Protocol with no adapter shim required, per
``protocol-first-interfaces``.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ProviderConfig,
    RunId,
    RunMode,
    RunStartRequest,
    SettingKey,
)
from ollama_llm_bench.backend.mode_visibility import ConfigSection

__all__: list[str] = ["ModeVisibilityPolicy", "NewBenchmarkGateway"]


class NewBenchmarkGateway(Protocol):
    """Adapter gateway for the New Benchmark widget (D-R-06)."""

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a user-saved setting (Advanced-Options defaults,
        ``benchmark.last_mode``, ``embedding.hide_from_test_models``), or ``None``.

        fast-synchronous.
        """
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a user-saved setting (e.g. ``benchmark.last_mode``).

        fast-synchronous.
        """
        ...

    def provider_list(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers, in display order, for the model picker.

        fast-synchronous.
        """
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the pre-run readiness gate.

        fast-synchronous. Unused by this story -- STORY-055 (Start flow) consumes it.
        """
        ...

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id.

        fast-synchronous (enqueues to the dispatcher thread and returns). Unused by
        this story -- STORY-055 (Start flow) consumes it.
        """
        ...


class ModeVisibilityPolicy(Protocol):
    """The one method this widget needs from the Mode Visibility Policy (§6.3)."""

    def visible_sections(self, mode: RunMode) -> tuple[ConfigSection, ...]:
        """Return every ``ConfigSection`` visible for ``mode`` (non-``HIDDEN``).

        fast-synchronous; pure; never raises for a valid ``RunMode`` member.
        """
        ...
