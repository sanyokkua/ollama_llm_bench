"""``NewBenchmarkGateway`` and the locally-declared ``ModeVisibilityPolicy``/``RunValidator``
(D-R-06).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.2 (``NewBenchmarkGateway``, declared verbatim) and
``11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`` §6.2-§6.3.
``ModeVisibilityPolicy`` is declared locally rather than importing a backend class --
``backend.mode_visibility`` exposes free functions (``is_visible``/``visible_sections``), not
a Protocol type; any object exposing a matching ``visible_sections`` callable (including the
backend module itself, structurally) satisfies this Protocol with no adapter shim required,
per ``protocol-first-interfaces``.

``RunValidator`` is likewise declared locally (STORY-055 Design Decision 1): neither
``08-E_interfaces_contracts.md`` nor the codebase declares a canonical ``RunValidator``
Protocol as of this story -- only ``02_New_Benchmark_Widget/description.md`` and
``implementation_structure.md`` name it in prose. The concrete backend implementation is a
future story's responsibility; its eventual home (per ``implementation_structure.md``) is
``ollama_llm_bench.backend.benchmark_pipeline.protocols``, and it MUST satisfy this exact
shape structurally.

``NewBenchmarkGateway.notify_error`` is a **local addition**, not present in the vendored
``08-E_interfaces_contracts.md`` §7b.2 declaration -- STORY-055-AC-7 needs a way to surface
the Run Summary dialog's preflight-refusal toast without editing the read-only spec file.
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
from ollama_llm_bench.ui.new_benchmark.models import ValidationEntry

__all__: list[str] = ["ModeVisibilityPolicy", "NewBenchmarkGateway", "RunValidator"]


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

        fast-synchronous.
        """
        ...

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id.

        fast-synchronous (enqueues to the dispatcher thread and returns).
        """
        ...

    def notify_error(self, message: str) -> None:
        """Surface a non-blocking, user-facing error toast (STORY-055-AC-7).

        fast-synchronous. Used when the Run Summary dialog factory refuses to open
        (the preflight re-check failed) -- the widget's own fields stay untouched.
        ``message`` is passed through unchanged -- UI/display surfaces do not apply
        redaction (``08-E`` §22, STORY-106-AC-3).
        """
        ...


class ModeVisibilityPolicy(Protocol):
    """The one method this widget needs from the Mode Visibility Policy (§6.3)."""

    def visible_sections(self, mode: RunMode) -> tuple[ConfigSection, ...]:
        """Return every ``ConfigSection`` visible for ``mode`` (non-``HIDDEN``).

        fast-synchronous; pure; never raises for a valid ``RunMode`` member.
        """
        ...


class RunValidator(Protocol):
    """Computes Run Validator entries for a would-be ``RunStartRequest`` (§6).

    Declared locally: no canonical Protocol exists in ``08-E_interfaces_contracts.md``
    as of STORY-055 -- the concrete backend implementation is a future story's
    responsibility and MUST satisfy this exact shape structurally.
    """

    def validate(self, request: RunStartRequest) -> tuple[ValidationEntry, ...]:
        """Return every hard-error/soft-warning entry for ``request``.

        fast-synchronous; pure; called on every configuration change and again by
        the Run Summary dialog's preflight re-check (``run_summary_dialog.md`` §8).
        Never raises -- an invalid configuration is reported as data
        (``ValidationEntry`` rows), never an exception.
        """
        ...
