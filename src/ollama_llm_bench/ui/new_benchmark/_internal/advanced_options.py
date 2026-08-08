"""``AdvancedOptionsSectionWidget`` -- the activation-checkbox-gated collapsible
section of per-run setting overrides (STORY-055-AC-3).

Source of truth: ``02_New_Benchmark_Widget/description.md`` §4.7 (activation
gating, per-control tables, the completeness and carriage rules -- DD-47) and
``backend.settings.PER_RUN_OVERRIDABLE`` (the authoritative key set). The
**completeness rule** (DD-47) requires every key in ``PER_RUN_OVERRIDABLE`` except
``feature.judge_run_analysis_enabled`` (the form's own primary analysis toggle,
owned by ``_internal/judge_section.py``) to have a control here -- including keys
the §4.7 prose tables do not individually name (the ``circuit_breaker.*`` keys and
several ``eval.*`` keys added by later stories; see ``registry.py``'s module
docstring). ``_CONTROL_KEYS`` below is exhaustive over that set; a test compares it
against ``PER_RUN_OVERRIDABLE`` and fails on any gap.
"""

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import ReasoningEffort, SettingKey
from ollama_llm_bench.backend.settings import PER_RUN_OVERRIDABLE

__all__: list[str] = ["AdvancedOptionsSectionWidget"]

_ANALYSIS_TOGGLE_KEY: SettingKey = "feature.judge_run_analysis_enabled"
_REASONING_EFFORT_KEY: SettingKey = "feature.reasoning_effort_default"
_TEMPERATURE_KEY: SettingKey = "benchmark.temperature"

# Every PER_RUN_OVERRIDABLE key except the analysis toggle, grouped in description.md
# §4.7's declared order, then the registry-only keys not individually named there.
_INFERENCE_KEYS: Final[tuple[SettingKey, ...]] = (
    "benchmark.warmup_enabled",
    _REASONING_EFFORT_KEY,
    "benchmark.max_output_tokens",
    _TEMPERATURE_KEY,
)
_TIMEOUT_RETRY_KEYS: Final[tuple[SettingKey, ...]] = (
    "benchmark.min_timeout_seconds",
    "benchmark.max_timeout_seconds",
    "benchmark.retry_count",
    "benchmark.consecutive_max_timeouts_to_exclude",
)
_RUN_BOUNDARY_KEYS: Final[tuple[SettingKey, ...]] = (
    "benchmark.pause_on_phase_switch",
    "benchmark.pause_on_provider_switch",
    "benchmark.pause_on_model_switch",
    "benchmark.stop_on_provider_health_failure",
)
_EVALUATION_KEYS: Final[tuple[SettingKey, ...]] = (
    "eval.phase_keyword_enabled",
    "eval.phase_cosine_enabled",
    "eval.phase_judge_enabled",
    "eval.force_judge_on_prior_failure",
    "eval.cosine_threshold",
    "eval.judge_timeout_min_seconds",
    "eval.judge_timeout_max_seconds",
    "eval.judge_timeout_escalation_steps",
    "eval.judge_timeout_consecutive_threshold",
    "eval.embedding_timeout_seconds",
    "eval.min_sample_size",
)
_EVALUATION_EXTRA_KEYS: Final[tuple[SettingKey, ...]] = (
    "eval.judge_max_completion_tokens",
    "eval.embedding_consecutive_failures_to_skip",
    "eval.embedding_cache_max_entries",
    "eval.min_cosine_coverage",
    "eval.sanity_min_chars",
    "eval.sanity_error_markers",
    "eval.keyword_semantic_pass_threshold",
    "eval.judge_max_parse_retries",
)
_CIRCUIT_BREAKER_KEYS: Final[tuple[SettingKey, ...]] = (
    "circuit_breaker.enabled",
    "circuit_breaker.failure_threshold",
    "circuit_breaker.cooldown_seconds",
)
_CONTROL_KEYS: Final[tuple[SettingKey, ...]] = (
    _INFERENCE_KEYS
    + _TIMEOUT_RETRY_KEYS
    + _RUN_BOUNDARY_KEYS
    + _EVALUATION_KEYS
    + _EVALUATION_EXTRA_KEYS
    + _CIRCUIT_BREAKER_KEYS
)

_BOOLEAN_KEYS: Final[frozenset[SettingKey]] = frozenset(
    {
        "benchmark.warmup_enabled",
        "benchmark.pause_on_phase_switch",
        "benchmark.pause_on_provider_switch",
        "benchmark.pause_on_model_switch",
        "benchmark.stop_on_provider_health_failure",
        "eval.phase_keyword_enabled",
        "eval.phase_cosine_enabled",
        "eval.phase_judge_enabled",
        "eval.force_judge_on_prior_failure",
        "circuit_breaker.enabled",
    }
)
_FLOAT_KEYS: Final[frozenset[SettingKey]] = frozenset(
    {"eval.cosine_threshold", "eval.min_cosine_coverage", "eval.keyword_semantic_pass_threshold"}
)
_TEXT_KEYS: Final[frozenset[SettingKey]] = frozenset({"eval.sanity_error_markers"})

_TIMEOUT_RETRY_NOTE: Final[str] = (
    "Each retry uses a longer timeout from the [min, max] range. A model failing this many\n"
    "times at the maximum is excluded; its remaining tasks are marked failed."
)

_LABELS: Final[dict[SettingKey, str]] = {
    "benchmark.warmup_enabled": "Enable Warmup",
    _REASONING_EFFORT_KEY: "Reasoning Effort",
    "benchmark.max_output_tokens": "Max Output Tokens",
    _TEMPERATURE_KEY: "Temperature",
    "benchmark.min_timeout_seconds": "Minimum timeout (s)",
    "benchmark.max_timeout_seconds": "Maximum timeout (s)",
    "benchmark.retry_count": "Retry count",
    "benchmark.consecutive_max_timeouts_to_exclude": "Max max-timeout failures before exclusion",
    "benchmark.pause_on_phase_switch": "Pause at phase switch",
    "benchmark.pause_on_provider_switch": "Pause at provider switch",
    "benchmark.pause_on_model_switch": "Pause at model switch",
    "benchmark.stop_on_provider_health_failure": "Stop on provider health failure",
    "eval.phase_keyword_enabled": "Keyword phase",
    "eval.phase_cosine_enabled": "Cosine phase",
    "eval.phase_judge_enabled": "Judge phase",
    "eval.force_judge_on_prior_failure": "Force judge after prior failure",
    "eval.cosine_threshold": "Cosine threshold",
    "eval.judge_timeout_min_seconds": "Judge timeout min (s)",
    "eval.judge_timeout_max_seconds": "Judge timeout max (s)",
    "eval.judge_timeout_escalation_steps": "Judge timeout escalation steps",
    "eval.judge_timeout_consecutive_threshold": "Judge consecutive-timeout threshold",
    "eval.embedding_timeout_seconds": "Embedding timeout (s)",
    "eval.min_sample_size": "Minimum sample size",
    "eval.judge_max_completion_tokens": "Judge max completion tokens",
    "eval.embedding_consecutive_failures_to_skip": "Embedding consecutive failures to skip",
    "eval.embedding_cache_max_entries": "Embedding cache max entries",
    "eval.min_cosine_coverage": "Minimum cosine coverage",
    "eval.sanity_min_chars": "Sanity check minimum characters",
    "eval.sanity_error_markers": "Sanity check error markers",
    "eval.keyword_semantic_pass_threshold": "Keyword semantic pass threshold",
    "eval.judge_max_parse_retries": "Judge max parse retries",
    "circuit_breaker.enabled": "Circuit breaker enabled",
    "circuit_breaker.failure_threshold": "Circuit breaker failure threshold",
    "circuit_breaker.cooldown_seconds": "Circuit breaker cooldown (s)",
}

_REASONING_EFFORT_ITEMS: Final[tuple[str, ...]] = tuple(effort.value for effort in ReasoningEffort)


class _ControlRow:
    """One control's widget plus its typed get/set-as-string accessors."""

    def __init__(
        self, *, get_text: Callable[[], str], set_text: Callable[[str], None], widget: QWidget
    ) -> None:
        self.get_text = get_text
        self.set_text = set_text
        self.widget = widget


def _name_control(widget: QWidget, *, key: SettingKey) -> None:
    """Set the objectName/accessibleName every row-factory control needs (STORY-098-AC-1)."""
    widget.setObjectName(f"new_benchmark.advanced_options.{key}")
    widget.setAccessibleName(_LABELS.get(key, key))


def _make_checkbox_row(key: SettingKey, *, changed: Callable[[], None]) -> _ControlRow:
    box = QCheckBox()
    _name_control(box, key=key)
    box.setObjectName(f"new_benchmark.advanced_options.{key}.checkbox")
    box.setMinimumHeight(24)  # 08_ACCESSIBILITY_FLOOR.md §6 -- 24px click-target floor
    box.toggled.connect(lambda _checked: changed())
    return _ControlRow(
        get_text=lambda: "true" if box.isChecked() else "false",
        set_text=lambda value: box.setChecked(value == "true"),
        widget=box,
    )


def _make_reasoning_effort_row(key: SettingKey, *, changed: Callable[[], None]) -> _ControlRow:
    combo = QComboBox()
    _name_control(combo, key=key)
    combo.setObjectName(f"new_benchmark.advanced_options.{key}.combo")
    combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    combo.addItems(_REASONING_EFFORT_ITEMS)
    combo.currentTextChanged.connect(lambda _text: changed())
    return _ControlRow(
        get_text=combo.currentText,
        set_text=combo.setCurrentText,
        widget=combo,
    )


def _make_float_row(key: SettingKey, *, changed: Callable[[], None]) -> _ControlRow:
    spin = QDoubleSpinBox()
    _name_control(spin, key=key)
    spin.setObjectName(f"new_benchmark.advanced_options.{key}.spin")
    spin.setRange(0.0, 1.0)
    spin.setSingleStep(0.01)
    spin.setDecimals(2)
    spin.valueChanged.connect(lambda _value: changed())
    return _ControlRow(
        get_text=lambda: f"{spin.value():.2f}",
        set_text=lambda value: spin.setValue(_coerce_float(value)),
        widget=spin,
    )


def _make_int_row(key: SettingKey, *, changed: Callable[[], None]) -> _ControlRow:
    spin = QSpinBox()
    _name_control(spin, key=key)
    spin.setObjectName(f"new_benchmark.advanced_options.{key}.spin")
    spin.setRange(0, 1_000_000)
    spin.valueChanged.connect(lambda _value: changed())
    return _ControlRow(
        get_text=lambda: str(spin.value()),
        set_text=lambda value: spin.setValue(_coerce_int(value)),
        widget=spin,
    )


def _make_text_row(key: SettingKey, *, changed: Callable[[], None]) -> _ControlRow:
    line_edit = QLineEdit()
    _name_control(line_edit, key=key)
    line_edit.setObjectName(f"new_benchmark.advanced_options.{key}.line_edit")
    line_edit.setMinimumHeight(24)  # 08_ACCESSIBILITY_FLOOR.md §6 -- 24px click-target floor
    line_edit.textChanged.connect(lambda _text: changed())
    return _ControlRow(get_text=line_edit.text, set_text=line_edit.setText, widget=line_edit)


def _coerce_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _coerce_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _make_control_row(key: SettingKey, *, changed: Callable[[], None]) -> _ControlRow:
    if key in _BOOLEAN_KEYS:
        return _make_checkbox_row(key, changed=changed)
    if key == _REASONING_EFFORT_KEY:
        return _make_reasoning_effort_row(key, changed=changed)
    if key == _TEMPERATURE_KEY or key in _TEXT_KEYS:
        return _make_text_row(key, changed=changed)
    if key in _FLOAT_KEYS:
        return _make_float_row(key, changed=changed)
    return _make_int_row(key, changed=changed)


class AdvancedOptionsSectionWidget(QWidget):
    """The Advanced Options section: activation checkbox plus every per-run control."""

    advanced_config_changed = Signal()

    def __init__(
        self, *, initial_values: dict[SettingKey, str], grading_visible: bool = False
    ) -> None:
        """Build the section, seeded from ``initial_values``.

        Args:
            initial_values: One value per key in ``PER_RUN_OVERRIDABLE`` minus
                ``feature.judge_run_analysis_enabled``, in registry storage form.
            grading_visible: Whether the Evaluation controls sub-group starts shown
                (``True`` only in ``GRADED``; the controller updates this on mode
                change via ``set_grading_visible``).
        """
        super().__init__()
        self.setObjectName("new_benchmark.advanced_options")
        self._seeded_values: dict[SettingKey, str] = dict(initial_values)
        self._rows: dict[SettingKey, _ControlRow] = {}
        self._build_ui(grading_visible=grading_visible)

    def _build_ui(self, *, grading_visible: bool) -> None:
        layout = QVBoxLayout(self)
        self._activation_box = QGroupBox("Override advanced options for this run")
        self._activation_box.setObjectName("new_benchmark.advanced_options.activation_box")
        self._activation_box.setAccessibleName("Override advanced options for this run")
        self._activation_box.setCheckable(True)
        self._activation_box.setChecked(False)
        self._activation_box.toggled.connect(self._on_activation_toggled)
        layout.addWidget(self._activation_box)

        box_layout = QVBoxLayout(self._activation_box)
        box_layout.addWidget(self._build_group("Inference", _INFERENCE_KEYS))
        box_layout.addWidget(self._build_group("Adaptive timeout and retry", _TIMEOUT_RETRY_KEYS))
        note = QLabel(_TIMEOUT_RETRY_NOTE)
        note.setProperty("role", "muted-note")
        note.setWordWrap(True)
        box_layout.addWidget(note)
        box_layout.addWidget(self._build_group("Run boundary", _RUN_BOUNDARY_KEYS))
        self._evaluation_group = self._build_group(
            "Evaluation", _EVALUATION_KEYS + _EVALUATION_EXTRA_KEYS
        )
        self._evaluation_group.setVisible(grading_visible)
        box_layout.addWidget(self._evaluation_group)
        box_layout.addWidget(self._build_group("Circuit breaker", _CIRCUIT_BREAKER_KEYS))

        self._controls_container = self._activation_box
        self._controls_container.setChecked(False)
        self._apply_controls_visibility()

    def _build_group(self, title: str, keys: tuple[SettingKey, ...]) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)
        for key in keys:
            row = _make_control_row(key, changed=self.advanced_config_changed.emit)
            row.set_text(self._seeded_values.get(key, ""))
            # Re-snapshot the seed as the control's own round-tripped representation
            # (e.g. a QDoubleSpinBox formats "0.7" as "0.70"; an unseeded "" becomes
            # "0.00") -- comparing against the raw input string would spuriously mark
            # every never-touched control dirty (DD-47's carriage rule requires exact
            # no-op detection).
            self._seeded_values[key] = row.get_text()
            self._rows[key] = row
            form.addRow(_LABELS.get(key, key), row.widget)
        return group

    def _apply_controls_visibility(self) -> None:
        for row in self._rows.values():
            row.widget.setEnabled(self._activation_box.isChecked())

    def _on_activation_toggled(self, _checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        if not self._activation_box.isChecked():
            self._reset_dirty_rows()
        self._apply_controls_visibility()
        self.advanced_config_changed.emit()

    def _reset_dirty_rows(self) -> None:
        """Discard per-run edits back to their seeded values (description.md §4.7:
        "Unchecking...discards the per-run edits")."""
        for key, row in self._rows.items():
            with QSignalBlocker(row.widget):
                row.set_text(self._seeded_values.get(key, ""))

    def set_grading_visible(self, grading_visible: bool) -> None:  # noqa: FBT001  # boolean state setter
        """Show/hide the Evaluation controls sub-group (visible only in ``GRADED``)."""
        self._evaluation_group.setVisible(grading_visible)

    @property
    def override_enabled(self) -> bool:
        """The activation checkbox's current state."""
        return self._activation_box.isChecked()

    @property
    def current_values(self) -> dict[SettingKey, str]:
        """Every control's current value, in registry storage form."""
        return {key: row.get_text() for key, row in self._rows.items()}

    @property
    def dirty_keys(self) -> frozenset[SettingKey]:
        """The keys whose current value differs from its seeded value (DD-47)."""
        return frozenset(
            key
            for key, row in self._rows.items()
            if row.get_text() != self._seeded_values.get(key, "")
        )


if frozenset(_CONTROL_KEYS) != PER_RUN_OVERRIDABLE - {_ANALYSIS_TOGGLE_KEY}:
    # A plain ``raise`` (not ``assert``) so this DD-47 completeness invariant still holds
    # under ``python -O``, which strips ``assert`` statements.
    raise AssertionError(
        "_CONTROL_KEYS must cover every PER_RUN_OVERRIDABLE key except the analysis toggle"
    )
