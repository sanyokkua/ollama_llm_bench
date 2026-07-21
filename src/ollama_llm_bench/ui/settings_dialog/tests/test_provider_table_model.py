"""Tests for the Providers-tab table model, the Health Dot status mapping, and
the credential-resolution-based Auth badge mapping (STORY-066-AC-1).
"""

from PySide6.QtTest import QAbstractItemModelTester
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_table_models import make_providers_table_model
from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow
from ollama_llm_bench.backend.domain import ProviderConfig, ProviderTestStatus, ProviderType
from ollama_llm_bench.ui.settings_dialog._internal.view_model_select import (
    provider_auth_badge,
    provider_config_to_row,
    provider_test_status_to_health,
)
from ollama_llm_bench.ui.theme import HealthDisplayState

# ---------------------------------------------------------------------------
# STORY-066-AC-1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected_health"),
    [
        (ProviderTestStatus.READY, HealthDisplayState.LIVE),
        (ProviderTestStatus.ZERO_MODELS, HealthDisplayState.REACHABLE_NO_MODELS),
        (ProviderTestStatus.UNREACHABLE, HealthDisplayState.DOWN),
        (ProviderTestStatus.MISSING_ENV, HealthDisplayState.DOWN),
        (ProviderTestStatus.UNTESTED, HealthDisplayState.NOT_TESTED),
    ],
)
def test_health_dot_per_status(
    status: ProviderTestStatus, expected_health: HealthDisplayState
) -> None:
    """Proves: STORY-066-AC-1

    Covers: EC-PROV-6

    For each documented ``ProviderTestStatus``, the row's Health Dot state
    matches the ``description.md`` §3.2 table exactly. The Health Dot is a pure
    function of ``ProviderTestStatus`` alone.
    """
    # Act
    health = provider_test_status_to_health(status)
    # Assert
    assert health is expected_health


def test_each_provider_test_status_is_mapped() -> None:
    """Proves: STORY-066-AC-1

    Every ``ProviderTestStatus`` member (including ``TESTING``, mid-probe)
    resolves without raising ``KeyError`` -- the mapping is exhaustive.
    """
    # Act / Assert
    for status in ProviderTestStatus:
        health = provider_test_status_to_health(status)
        assert isinstance(health, HealthDisplayState)


@pytest.mark.parametrize(
    ("api_key_env_var_name", "resolves", "expected_badge"),
    [
        (None, False, "none"),
        ("", False, "none"),
        ("OPENAI_API_KEY", True, "env ✓"),
        ("OPENAI_API_KEY", False, "env ✗"),
    ],
)
def test_provider_auth_badge_is_pure_function_of_credential_resolution(
    api_key_env_var_name: str | None, *, resolves: bool, expected_badge: str
) -> None:
    """Proves: STORY-066-AC-1

    Covers: EC-PROV-6

    The Auth badge is ``"none"`` when no env-var name is configured, ``"env
    ✓"`` when a name is configured and resolves, and ``"env ✗"`` when a name
    is configured but does not resolve -- per the corrected ``description.md``
    §3.2/§12 credential-resolution model.
    """
    # Act
    badge = provider_auth_badge(api_key_env_var_name=api_key_env_var_name, resolves=resolves)
    # Assert
    assert badge == expected_badge


@pytest.mark.parametrize("status", [ProviderTestStatus.READY, ProviderTestStatus.UNREACHABLE])
@pytest.mark.parametrize(
    ("api_key_raw", "resolves", "expected_badge"),
    [
        (None, False, "none"),
        ("OPENAI_API_KEY", True, "env ✓"),
        ("OPENAI_API_KEY", False, "env ✗"),
    ],
)
def test_auth_badge_is_independent_of_health_dot_status(
    status: ProviderTestStatus, api_key_raw: str | None, *, resolves: bool, expected_badge: str
) -> None:
    """Proves: STORY-066-AC-1

    Covers: EC-PROV-6

    Crossing every Auth-badge case against two different ``ProviderTestStatus``
    values (a healthy ``READY`` and an unhealthy ``UNREACHABLE``) proves the
    Auth badge and the Health Dot are independent axes: a ``READY`` provider
    with no key field still reads ``"none"``, and an ``UNREACHABLE`` provider
    whose key resolves still reads ``"env ✓"``.
    """
    # Arrange
    config = ProviderConfig(
        provider_id="aaaaaaaa-1111-4111-8111-111111111111",
        name="Provider Under Test",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        base_url="https://example.invalid/v1",
        api_key_raw=api_key_raw,
        enabled=True,
        last_probe_status=status,
    )
    # Act
    row = provider_config_to_row(
        config=config, original=None, is_session_added=False, api_key_resolves=resolves
    )
    # Assert
    assert row.auth_badge == expected_badge
    assert row.health is status


# ---------------------------------------------------------------------------
# Table model contract (Definition of done)
# ---------------------------------------------------------------------------

_EXPECTED_COLUMN_COUNT = 6


def test_providers_table_model_satisfies_qt_model_contract(qtbot: QtBot) -> None:
    """Proves: STORY-066-AC-1

    Wrapping ``make_providers_table_model``'s result in
    ``QAbstractItemModelTester`` raises on any model-contract violation;
    constructing the tester over a populated model must not raise.
    """
    # Arrange
    rows = (
        ProviderTableRow(
            provider_id="aaaaaaaa-1111-4111-8111-111111111111",
            label="Ollama Local",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url_display="http://localhost:11434/v1",
            auth_badge="none",
            health=ProviderTestStatus.READY,
            enabled=True,
        ),
    )
    model = make_providers_table_model(rows=rows)
    # Act
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    # Assert
    assert tester.model() is model
    assert model.rowCount() == 1
    assert model.columnCount() == _EXPECTED_COLUMN_COUNT
