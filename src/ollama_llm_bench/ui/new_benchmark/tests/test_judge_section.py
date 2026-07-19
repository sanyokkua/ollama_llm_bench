"""Unit tests for ``_internal.judge_section.JudgeSectionWidget`` (STORY-055-AC-1, AC-2)."""

from typing import cast

from PySide6.QtWidgets import QComboBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType, RunMode
from ollama_llm_bench.ui.new_benchmark._internal.judge_section import JudgeSectionWidget
from ollama_llm_bench.ui.new_benchmark.tests.conftest import FakeEventBus

_PROVIDER_A = ProviderConfig(
    provider_id="aaaaaaaa-1111-4111-8111-111111111111",
    name="Ollama Local",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    enabled=True,
    default_models=("llama3", "nomic-embed-text"),
)
_PROVIDER_B = ProviderConfig(
    provider_id="bbbbbbbb-2222-4222-8222-222222222222",
    name="Anthropic",
    provider_type=ProviderType.ANTHROPIC,
    enabled=True,
    default_models=("claude-3-5-sonnet", "text-embedding-3-small"),
)


@pytest.mark.parametrize(
    ("mode", "expect_checked"),
    [
        (RunMode.SYNTHETIC, False),
        (RunMode.TASKS, False),
        (RunMode.GRADED, True),
    ],
    ids=["synthetic_off", "tasks_off", "graded_on"],
)
def test_analysis_toggle_default_per_mode(
    qtbot: QtBot,
    mode: RunMode,
    expect_checked: bool,  # noqa: FBT001  # parametrize tuple element
) -> None:
    """Proves: STORY-055-AC-1

    For each RunMode, the "Generate run analysis" toggle initialises to the
    specified per-mode default: SYNTHETIC/TASKS -> OFF, GRADED -> ON.
    """
    # Arrange
    widget = JudgeSectionWidget(
        provider_configs_source=lambda: (), hide_embedding_models_source=lambda: False
    )
    qtbot.addWidget(widget)
    # Act
    widget.set_mode(mode)
    # Assert
    assert widget.judge_analysis_enabled is expect_checked


def test_judge_model_dropdown_follows_provider(qtbot: QtBot, fake_event_bus: FakeEventBus) -> None:
    """Proves: STORY-055-AC-2

    Given the Judge section, when the user selects a judge provider, then the judge
    model dropdown is repopulated from that provider via set_provider(provider_id)
    and lists only non-embedding chat-capable models.
    """
    # Arrange
    widget = JudgeSectionWidget(
        provider_configs_source=lambda: (_PROVIDER_A, _PROVIDER_B),
        hide_embedding_models_source=lambda: True,
        event_bus=fake_event_bus,
    )
    qtbot.addWidget(widget)
    provider_dropdown = cast(
        "QComboBox", widget.findChild(QComboBox, "new_benchmark.judge.provider_dropdown")
    )
    model_dropdown = cast(
        "QComboBox", widget.findChild(QComboBox, "new_benchmark.judge.model_dropdown")
    )
    # Act
    provider_dropdown.setCurrentIndex(1)  # selects _PROVIDER_B, a genuine index change
    # Assert
    model_items = tuple(model_dropdown.itemText(i) for i in range(model_dropdown.count()))
    assert model_items == ("claude-3-5-sonnet",)
