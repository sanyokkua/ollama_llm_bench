"""AdvancedOptionsWidget — per-run overrides for streaming, warmup, and reasoning effort."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import AdvancedRunOptions

_logger = logging.getLogger(__name__)

_REASONING_OPTIONS: list[str] = ["default", "low", "medium", "high"]
_CHILD_TOOLTIP = "Default value comes from Settings → General. Override here for this run only."
_GROUP_BOX_TOOLTIP = "When unchecked, values are read from Settings defaults. Check to override for this run only."


class AdvancedOptionsWidget(QWidget):
    """Checkable group box for per-run advanced option overrides.

    When the group box is unchecked (overrides disabled), child widgets
    are disabled and display the effective default values from
    AppSettingsService (passed in by the caller). When checked, children
    are enabled and editable.

    The defaults are injected by the caller — this widget never calls
    AppSettingsService directly.
    """

    def __init__(
        self,
        *,
        streaming_default: bool = True,
        warmup_default: bool = False,
        reasoning_default: str = "default",
        parent: QWidget | None = None,
    ) -> None:
        """Initialize AdvancedOptionsWidget with injected default values.

        Args:
            streaming_default: Default streaming-enabled state from app settings.
            warmup_default: Default warmup-enabled state from app settings.
            reasoning_default: Default reasoning effort level from app settings.
            parent: Optional parent widget for ownership management.
        """
        super().__init__(parent)
        self._streaming_default = streaming_default
        self._warmup_default = warmup_default
        self._reasoning_default = reasoning_default

        self._create_widgets()
        self._configure_widgets()
        self._build_layout()
        self._connect_signals()
        self._apply_defaults_to_children()
        self._set_children_enabled(False)

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        self._group_box = QGroupBox("Advanced Options")
        self._streaming_checkbox = QCheckBox("Enable Streaming")
        self._warmup_checkbox = QCheckBox("Enable Warmup")
        self._reasoning_label = QLabel("Reasoning Effort")
        self._reasoning_combo = QComboBox()

    # ------------------------------------------------------------------
    # Widget configuration
    # ------------------------------------------------------------------

    def _configure_widgets(self) -> None:
        self._group_box.setCheckable(True)
        self._group_box.setChecked(False)
        self._group_box.setToolTip(_GROUP_BOX_TOOLTIP)

        self._reasoning_combo.addItems(_REASONING_OPTIONS)

        self._streaming_checkbox.setToolTip(_CHILD_TOOLTIP)
        self._warmup_checkbox.setToolTip(_CHILD_TOOLTIP)
        self._reasoning_combo.setToolTip(_CHILD_TOOLTIP)
        self._reasoning_label.setToolTip(_CHILD_TOOLTIP)

    # ------------------------------------------------------------------
    # Layout assembly
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.setSpacing(3)
        group_layout.addWidget(self._streaming_checkbox)
        group_layout.addWidget(self._warmup_checkbox)
        group_layout.addWidget(self._reasoning_label)
        group_layout.addWidget(self._reasoning_combo)
        self._group_box.setLayout(group_layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._group_box)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._group_box.toggled.connect(self._on_override_toggled)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_defaults_to_children(self) -> None:
        """Snap all child widget values back to their stored defaults."""
        self._streaming_checkbox.setChecked(self._streaming_default)
        self._warmup_checkbox.setChecked(self._warmup_default)
        idx = self._reasoning_combo.findText(self._reasoning_default)
        if idx >= 0:
            self._reasoning_combo.setCurrentIndex(idx)

    def _set_children_enabled(self, enabled: bool) -> None:
        """Enable or disable all interactive child widgets."""
        self._streaming_checkbox.setEnabled(enabled)
        self._warmup_checkbox.setEnabled(enabled)
        self._reasoning_combo.setEnabled(enabled)
        self._reasoning_label.setEnabled(enabled)

    def _on_override_toggled(self, checked: bool) -> None:
        if not checked:
            self._apply_defaults_to_children()
        self._set_children_enabled(checked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_effective_options(self) -> AdvancedRunOptions:
        """Return the effective advanced run options.

        When overrides are disabled (group box unchecked), the returned
        values reflect the defaults. When enabled, they reflect the
        user-selected values.

        Returns:
            AdvancedRunOptions with current values and override flags.
        """
        is_override = self._group_box.isChecked()
        return AdvancedRunOptions(
            streaming_enabled=self._streaming_checkbox.isChecked(),
            warmup_enabled=self._warmup_checkbox.isChecked(),
            reasoning_effort=self._reasoning_combo.currentText(),
            streaming_is_override=is_override,
            warmup_is_override=is_override,
            reasoning_is_override=is_override,
        )

    def update_defaults(
        self,
        *,
        streaming: bool,
        warmup: bool,
        reasoning: str,
    ) -> None:
        """Update stored defaults and refresh displayed values if overrides are off.

        Call this when AppSettingsChangedEvent fires to keep the displayed
        defaults in sync with persisted settings.

        Args:
            streaming: New default for streaming-enabled.
            warmup: New default for warmup-enabled.
            reasoning: New default reasoning effort level.
        """
        self._streaming_default = streaming
        self._warmup_default = warmup
        self._reasoning_default = reasoning

        if not self._group_box.isChecked():
            self._apply_defaults_to_children()
