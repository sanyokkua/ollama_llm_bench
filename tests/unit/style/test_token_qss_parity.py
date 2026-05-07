"""Tests for QSS token parity — every {placeholder} must exist in tokens.py."""

import re
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.style.theme_loader import apply_theme
from ollama_llm_bench.ui.style.tokens import DARK_TOKENS, LIGHT_TOKENS, SHARED_TOKENS

QSS_DIR = Path(__file__).parent.parent.parent.parent / "src" / "ollama_llm_bench" / "ui" / "style"
ALL_TOKEN_KEYS: set[str] = set(DARK_TOKENS) | set(LIGHT_TOKENS) | set(SHARED_TOKENS)

# icons_dir is a runtime-injected token, not in tokens.py — exclude it.
# "placeholders" appears literally in the QSS file comment (line 3) and is not a token.
_RUNTIME_TOKENS: set[str] = {"icons_dir", "placeholders"}


def _extract_placeholders(qss_text: str) -> set[str]:
    """Return all {name} placeholders found in a QSS template, excluding runtime tokens."""
    all_found = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", qss_text))
    return all_found - _RUNTIME_TOKENS


# ---------------------------------------------------------------------------
# Group A — placeholder resolution parity
# ---------------------------------------------------------------------------


def test_qss_placeholders_resolve_dark() -> None:
    # Arrange
    qss_text = (QSS_DIR / "theme_dark.qss").read_text(encoding="utf-8")

    # Act
    placeholders = _extract_placeholders(qss_text)
    missing = placeholders - ALL_TOKEN_KEYS

    # Assert
    assert missing == set(), f"dark QSS has unresolved placeholders: {missing}"


def test_qss_placeholders_resolve_light() -> None:
    # Arrange
    qss_text = (QSS_DIR / "theme_light.qss").read_text(encoding="utf-8")

    # Act
    placeholders = _extract_placeholders(qss_text)
    missing = placeholders - ALL_TOKEN_KEYS

    # Assert
    assert missing == set(), f"light QSS has unresolved placeholders: {missing}"


# ---------------------------------------------------------------------------
# Group B — structural rule presence (spinbox, radio)
# ---------------------------------------------------------------------------


def test_spinbox_up_button_rule_in_dark_qss() -> None:
    # Arrange
    qss_text = (QSS_DIR / "theme_dark.qss").read_text(encoding="utf-8")

    # Act / Assert
    assert "QSpinBox::up-button" in qss_text


def test_spinbox_up_button_rule_in_light_qss() -> None:
    # Arrange
    qss_text = (QSS_DIR / "theme_light.qss").read_text(encoding="utf-8")

    # Act / Assert
    assert "QSpinBox::up-button" in qss_text


def test_radio_indicator_9px_radius_in_dark_qss() -> None:
    # Arrange
    qss_text = (QSS_DIR / "theme_dark.qss").read_text(encoding="utf-8")

    # Act / Assert
    assert "border-radius: 9px" in qss_text


def test_radio_indicator_9px_radius_in_light_qss() -> None:
    # Arrange
    qss_text = (QSS_DIR / "theme_light.qss").read_text(encoding="utf-8")

    # Act / Assert
    assert "border-radius: 9px" in qss_text


# ---------------------------------------------------------------------------
# Group C — parametrized rules present in both themes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["theme_dark.qss", "theme_light.qss"],
    ids=["dark", "light"],
)
def test_button_danger_disabled_rule_present(filename: str) -> None:
    # Arrange
    qss_text = (QSS_DIR / filename).read_text(encoding="utf-8")

    # Act / Assert
    assert 'QPushButton[role="danger"]:disabled' in qss_text


@pytest.mark.parametrize(
    "filename",
    ["theme_dark.qss", "theme_light.qss"],
    ids=["dark", "light"],
)
def test_button_icon_disabled_rule_present(filename: str) -> None:
    # Arrange
    qss_text = (QSS_DIR / filename).read_text(encoding="utf-8")

    # Act / Assert
    assert 'QPushButton[role="icon"]:disabled' in qss_text


@pytest.mark.parametrize(
    "filename",
    ["theme_dark.qss", "theme_light.qss"],
    ids=["dark", "light"],
)
def test_provider_type_badge_rule_present(filename: str) -> None:
    # Arrange
    qss_text = (QSS_DIR / filename).read_text(encoding="utf-8")

    # Act / Assert
    assert 'variant="provider-type"' in qss_text


@pytest.mark.parametrize(
    "filename",
    ["theme_dark.qss", "theme_light.qss"],
    ids=["dark", "light"],
)
def test_tab_pane_has_top_border(filename: str) -> None:
    # Arrange
    qss_text = (QSS_DIR / filename).read_text(encoding="utf-8")

    # Act / Assert
    assert "border-top:" in qss_text


# ---------------------------------------------------------------------------
# Group D — apply_theme warns on unresolved token
# ---------------------------------------------------------------------------


def test_theme_loader_warns_on_unresolved_token(mocker: MockerFixture) -> None:
    # Arrange — inject a template with a key that will never be in tokens.py
    from PySide6.QtWidgets import QApplication

    mocker.patch.object(Path, "read_text", return_value="bg: {nonexistent_key_xyz};")
    mock_logger = mocker.patch("ollama_llm_bench.ui.style.theme_loader.logger")
    mock_app = mocker.Mock(spec=QApplication)

    # Act
    apply_theme(mock_app, "dark")

    # Assert — the unresolved placeholder must trigger a warning log
    assert mock_logger.warning.called
