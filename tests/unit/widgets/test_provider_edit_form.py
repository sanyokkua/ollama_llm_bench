"""Unit tests for ProviderEditForm widget."""

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import ProviderConfig, ProviderType
from ollama_llm_bench.ui.widgets.settings.provider_edit_form import ProviderEditForm

# ---------------------------------------------------------------------------
# QApplication fixture (module-scoped to avoid creating many instances)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication for this module's tests."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def _make_form(
    used_ids: set[str] | None = None,
    qapp: QApplication | None = None,
) -> ProviderEditForm:
    return ProviderEditForm(used_ids=used_ids or set())


def _openai_config(**kwargs: object) -> ProviderConfig:
    defaults: dict[str, object] = {
        "provider_id": "local",
        "label": "Local",
        "provider_type": ProviderType.OPENAI_COMPATIBLE,
        "api_key": "ollama",
        "api_key_raw": "ollama",
        "enabled": True,
        "base_url": "http://localhost:11434/v1",
    }
    defaults.update(kwargs)
    return ProviderConfig(**defaults)  # type: ignore[arg-type]


def _gemini_config(**kwargs: object) -> ProviderConfig:
    defaults: dict[str, object] = {
        "provider_id": "gemini_p",
        "label": "Gemini",
        "provider_type": ProviderType.GEMINI,
        "api_key": "",
        "api_key_raw": "${GEMINI_KEY}",
        "enabled": True,
    }
    defaults.update(kwargs)
    return ProviderConfig(**defaults)  # type: ignore[arg-type]


def _anthropic_config(**kwargs: object) -> ProviderConfig:
    defaults: dict[str, object] = {
        "provider_id": "anthropic_p",
        "label": "Anthropic",
        "provider_type": ProviderType.ANTHROPIC,
        "api_key": "",
        "api_key_raw": "${ANTHROPIC_KEY}",
        "enabled": True,
    }
    defaults.update(kwargs)
    return ProviderConfig(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Field visibility tests
# ---------------------------------------------------------------------------


def test_form_shows_base_url_for_openai_compatible(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_openai_config())

    assert not form._base_url_edit.isHidden()


def test_form_hides_base_url_for_gemini(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_gemini_config())

    assert not form._base_url_edit.isVisible()


def test_form_shows_gemini_base_url_field_for_gemini(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_gemini_config())

    assert not form._gemini_base_url_edit.isHidden()


def test_form_hides_gemini_base_url_field_for_openai_compatible(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_openai_config())

    assert not form._gemini_base_url_edit.isVisible()


def test_gemini_form_roundtrip_preserves_base_url(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_gemini_config(base_url="https://proxy.example.com"))
    config = form.get_config(original_provider_id="gemini_p")

    assert config.base_url == "https://proxy.example.com"


def test_gemini_populate_without_base_url_leaves_field_empty(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_gemini_config())

    assert form._gemini_base_url_edit.text() == ""


def test_azure_fields_hidden_by_default(qapp: QApplication) -> None:
    """Azure sub-fields must be hidden when azure_deployment and azure_api_version are None."""
    form = _make_form()

    form.populate(_openai_config(azure_deployment=None, azure_api_version=None))

    assert not form._azure_deployment_edit.isVisible()
    assert not form._azure_api_version_edit.isVisible()


def test_azure_fields_visible_when_flag_checked(qapp: QApplication) -> None:
    """Azure sub-fields must become visible after the azure flag is checked."""
    form = _make_form()
    form.populate(_openai_config())

    form._azure_flag.setChecked(True)

    assert not form._azure_deployment_edit.isHidden()
    assert not form._azure_api_version_edit.isHidden()


# ---------------------------------------------------------------------------
# Validation — ID field
# ---------------------------------------------------------------------------


def test_id_validation_rejects_invalid_chars(qapp: QApplication) -> None:
    form = _make_form()

    form._id_edit.setText("My Provider!")
    form._label_edit.setText("Valid Label")

    assert not form.is_valid


def test_id_validation_rejects_duplicate(qapp: QApplication) -> None:
    form = _make_form(used_ids={"existing_id"})

    form._id_edit.setText("existing_id")
    form._label_edit.setText("Valid Label")

    assert not form.is_valid


def test_id_validation_accepts_valid_id(qapp: QApplication) -> None:
    form = _make_form(used_ids={"other_id"})

    form._id_edit.setText("my_provider_1")
    form._label_edit.setText("Valid Label")

    # No ID error should be visible
    assert not form._id_error.isVisible()


# ---------------------------------------------------------------------------
# Validation — Base URL
# ---------------------------------------------------------------------------


def test_base_url_validation_rejects_ftp_scheme(qapp: QApplication) -> None:
    form = _make_form()
    form.populate(_openai_config())

    form._id_edit.setText("valid_id")
    form._label_edit.setText("Valid")
    form._base_url_edit.setText("ftp://localhost/v1")

    assert not form.is_valid


def test_base_url_validation_accepts_http(qapp: QApplication) -> None:
    form = _make_form()
    form.populate(_openai_config())

    form._id_edit.setText("valid_id")
    form._label_edit.setText("Valid")
    form._base_url_edit.setText("http://localhost:11434/v1")

    assert not form._base_url_error.isVisible()


# ---------------------------------------------------------------------------
# Validation — API key env var pattern
# ---------------------------------------------------------------------------


def test_api_key_env_var_pattern_accepted(qapp: QApplication) -> None:
    form = _make_form()
    form._id_edit.setText("valid_id")
    form._label_edit.setText("Valid")

    form._api_key_edit.setText("${MY_KEY}")

    assert not form._api_key_error.isVisible()


def test_api_key_env_var_bad_pattern_rejected(qapp: QApplication) -> None:
    """${bad-var} contains a hyphen — must fail the env-var pattern check."""
    form = _make_form()
    form._id_edit.setText("valid_id")
    form._label_edit.setText("Valid")

    form._api_key_edit.setText("${bad-var}")

    assert not form.is_valid
    assert not form._api_key_error.isHidden()


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


def test_get_config_preserves_api_key_raw(qapp: QApplication) -> None:
    """get_config() must store the literal field text in api_key_raw."""
    form = _make_form()
    form._id_edit.setText("p1")
    form._label_edit.setText("P1 Label")

    form._api_key_edit.setText("${MY_KEY}")

    config = form.get_config(original_provider_id="p1")

    assert config.api_key_raw == "${MY_KEY}"


def test_get_config_api_key_is_empty_string(qapp: QApplication) -> None:
    """get_config() always sets api_key='' (resolution happens at runtime, not in the form)."""
    form = _make_form()
    form._id_edit.setText("p1")
    form._label_edit.setText("P1 Label")
    form._api_key_edit.setText("sk-plain")

    config = form.get_config(original_provider_id="p1")

    assert config.api_key == ""


# ---------------------------------------------------------------------------
# populate
# ---------------------------------------------------------------------------


def test_populate_fills_id_field(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_openai_config(provider_id="my_local", label="My Local"))

    assert form._id_edit.text() == "my_local"


def test_populate_fills_label_field(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_openai_config(label="Awesome Provider"))

    assert form._label_edit.text() == "Awesome Provider"


def test_populate_sets_correct_type_combo_index(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_gemini_config())

    assert form._type_combo.currentText() == ProviderType.GEMINI.value


def test_populate_fills_api_key_from_api_key_raw(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_openai_config(api_key_raw="${SOME_VAR}", api_key=""))

    assert form._api_key_edit.text() == "${SOME_VAR}"


def test_populate_sets_azure_flag_when_deployment_present(qapp: QApplication) -> None:
    form = _make_form()

    form.populate(_openai_config(azure_deployment="my-deploy"))

    assert form._azure_flag.isChecked()


def test_populate_does_not_emit_form_changed(qapp: QApplication) -> None:
    """populate() must not emit form_changed — it uses blockSignals internally."""
    form = _make_form()
    emitted: list[int] = []
    form.form_changed.connect(lambda: emitted.append(1))

    form.populate(_openai_config())

    assert emitted == []


# ---------------------------------------------------------------------------
# form_changed signal
# ---------------------------------------------------------------------------


def test_form_changed_emitted_on_label_edit(qapp: QApplication) -> None:
    form = _make_form()
    emitted: list[int] = []
    form.form_changed.connect(lambda: emitted.append(1))

    form._label_edit.setText("New label text")

    assert len(emitted) >= 1
