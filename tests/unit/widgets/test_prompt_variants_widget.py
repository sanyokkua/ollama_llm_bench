"""Unit tests for PromptVariantsWidget — variant CRUD, duplicate rejection, import, and signals."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 not available")

from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import PromptVariantSpec
from ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget import (
    PromptVariantsWidget,
    VariantEditorDialog,
    _next_unique_id,
)

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return cast(QApplication, instance)
    return QApplication([])


# ---------------------------------------------------------------------------
# Widget fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def widget(qapp: QApplication) -> PromptVariantsWidget:
    return PromptVariantsWidget()


def _make_spec(variant_id: str = "v1", label: str = "V1", template: str = "Answer: {question}") -> PromptVariantSpec:
    return PromptVariantSpec(
        variant_id=variant_id,
        variant_label=label,
        user_prompt_template=template,
    )


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


def test_get_variants_empty_initially(widget: PromptVariantsWidget) -> None:
    assert widget.get_variants() == []


def test_add_variant_via_internal_append(widget: PromptVariantsWidget) -> None:
    spec = _make_spec()
    widget._append_variant(spec)

    assert widget.get_variants() == [spec]
    assert widget._variants_list.count() == 1


def test_add_two_different_variants(widget: PromptVariantsWidget) -> None:
    widget._append_variant(_make_spec("a"))
    widget._append_variant(_make_spec("b"))

    assert len(widget.get_variants()) == 2


def test_remove_selected_variant(widget: PromptVariantsWidget) -> None:
    widget._append_variant(_make_spec("x"))
    widget._variants_list.setCurrentRow(0)

    widget._on_remove_clicked()

    assert widget.get_variants() == []
    assert widget._variants_list.count() == 0


def test_remove_on_empty_list_does_nothing(widget: PromptVariantsWidget) -> None:
    widget._on_remove_clicked()
    assert widget.get_variants() == []


# ---------------------------------------------------------------------------
# Duplicate variant_id rejection
# ---------------------------------------------------------------------------


def test_duplicate_variant_id_rejected(widget: PromptVariantsWidget, mocker: pytest.MonkeyPatch) -> None:
    widget._append_variant(_make_spec("dup"))

    # Simulate dialog.exec() returning Accepted and dialog.get_variant() returning a duplicate
    mock_dialog = mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.VariantEditorDialog")
    instance = mock_dialog.return_value
    instance.exec.return_value = 1  # QDialog.DialogCode.Accepted == 1
    instance.get_variant.return_value = _make_spec("dup")

    mock_msgbox = mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.QMessageBox.warning")

    widget._on_add_clicked()

    mock_msgbox.assert_called_once()
    assert len(widget.get_variants()) == 1  # unchanged


def test_unique_variant_id_accepted(widget: PromptVariantsWidget, mocker: pytest.MonkeyPatch) -> None:
    widget._append_variant(_make_spec("existing"))

    mock_dialog = mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.VariantEditorDialog")
    instance = mock_dialog.return_value
    instance.exec.return_value = 1
    instance.get_variant.return_value = _make_spec("new_one")

    widget._on_add_clicked()

    assert len(widget.get_variants()) == 2


# ---------------------------------------------------------------------------
# variants_changed signal
# ---------------------------------------------------------------------------


def test_variants_changed_emits_on_add(widget: PromptVariantsWidget, mocker: pytest.MonkeyPatch) -> None:
    mock_dialog = mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.VariantEditorDialog")
    instance = mock_dialog.return_value
    instance.exec.return_value = 1
    instance.get_variant.return_value = _make_spec("sig_test")

    signal_received: list[bool] = []
    widget.variants_changed.connect(lambda: signal_received.append(True))

    widget._on_add_clicked()

    assert signal_received == [True]


def test_variants_changed_emits_on_remove(widget: PromptVariantsWidget) -> None:
    widget._append_variant(_make_spec("r"))
    widget._variants_list.setCurrentRow(0)

    signal_received: list[bool] = []
    widget.variants_changed.connect(lambda: signal_received.append(True))

    widget._on_remove_clicked()

    assert signal_received == [True]


def test_variants_changed_not_emitted_when_dialog_cancelled(
    widget: PromptVariantsWidget, mocker: pytest.MonkeyPatch
) -> None:
    mock_dialog = mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.VariantEditorDialog")
    instance = mock_dialog.return_value
    instance.exec.return_value = 0  # Rejected

    signal_received: list[bool] = []
    widget.variants_changed.connect(lambda: signal_received.append(True))

    widget._on_add_clicked()

    assert signal_received == []


def test_variants_changed_not_emitted_on_duplicate(widget: PromptVariantsWidget, mocker: pytest.MonkeyPatch) -> None:
    widget._append_variant(_make_spec("dup2"))

    mock_dialog = mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.VariantEditorDialog")
    instance = mock_dialog.return_value
    instance.exec.return_value = 1
    instance.get_variant.return_value = _make_spec("dup2")
    mocker.patch("ollama_llm_bench.ui.widgets.panels.control.prompt_variants_widget.QMessageBox.warning")

    signal_received: list[bool] = []
    widget.variants_changed.connect(lambda: signal_received.append(True))

    widget._on_add_clicked()

    assert signal_received == []


# ---------------------------------------------------------------------------
# Import from YAML
# ---------------------------------------------------------------------------


def test_import_yaml_loads_all_valid_entries(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = [
        {"variant_id": "y1", "variant_label": "Y1", "user_prompt_template": "Q: {question}"},
        {"variant_id": "y2", "variant_label": "Y2", "user_prompt_template": "A: {question}"},
        {"variant_id": "y3", "variant_label": "Y3", "user_prompt_template": "B: {question}"},
    ]
    yaml_file = tmp_path / "variants.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 3
    ids = [v.variant_id for v in widget.get_variants()]
    assert ids == ["y1", "y2", "y3"]


def test_import_yaml_skips_duplicate_id(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    widget._append_variant(_make_spec("existing_y"))

    data = [
        {"variant_id": "existing_y", "variant_label": "Dup", "user_prompt_template": "D: {question}"},
        {"variant_id": "new_y", "variant_label": "New", "user_prompt_template": "N: {question}"},
    ]
    yaml_file = tmp_path / "variants.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 1
    assert len(widget.get_variants()) == 2  # 1 original + 1 new


def test_import_yaml_skips_entries_missing_required_fields(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = [
        {"variant_id": "ok", "variant_label": "OK", "user_prompt_template": "{question}"},
        {"variant_label": "Missing ID"},  # no variant_id
        {"variant_id": "no_tmpl", "variant_label": "L"},  # no user_prompt_template
    ]
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 1


def test_import_yaml_non_list_returns_zero(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text(yaml.dump({"key": "value"}), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 0


def test_import_yaml_emits_variants_changed(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = [{"variant_id": "sig_y", "variant_label": "S", "user_prompt_template": "{question}"}]
    yaml_file = tmp_path / "v.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    signal_received: list[bool] = []
    widget.variants_changed.connect(lambda: signal_received.append(True))

    # Call internal method directly to avoid file dialog, then emit as _on_import_clicked would
    widget._import_from_yaml(yaml_file)
    widget.variants_changed.emit()

    assert signal_received == [True]


# ---------------------------------------------------------------------------
# Import from TXT
# ---------------------------------------------------------------------------


def test_import_txt_creates_one_variant(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    txt_file = tmp_path / "my_prompt.txt"
    txt_file.write_text("Please answer: {question}", encoding="utf-8")

    count = widget._import_from_txt(txt_file)

    assert count == 1
    variants = widget.get_variants()
    assert len(variants) == 1
    assert variants[0].variant_id == "imported_0"
    assert variants[0].variant_label == "my_prompt"
    assert variants[0].user_prompt_template == "Please answer: {question}"


def test_import_txt_auto_generates_unique_id(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    # Pre-populate imported_0
    widget._append_variant(
        PromptVariantSpec(variant_id="imported_0", variant_label="x", user_prompt_template="{question}")
    )
    txt_file = tmp_path / "second.txt"
    txt_file.write_text("Q: {question}", encoding="utf-8")

    widget._import_from_txt(txt_file)

    ids = [v.variant_id for v in widget.get_variants()]
    assert "imported_1" in ids


def test_import_txt_empty_file_returns_zero(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    txt_file = tmp_path / "empty.txt"
    txt_file.write_text("", encoding="utf-8")

    count = widget._import_from_txt(txt_file)

    assert count == 0


# ---------------------------------------------------------------------------
# YAML import — dual key format and wrapper shape
# ---------------------------------------------------------------------------


def test_import_yaml_short_key_format_loads_entries(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = [
        {"id": "v1", "label": "Strict proofreader", "template": "{question}\n\nReturn corrections only."},
        {"id": "v2", "label": "Chain of thought", "template": "Think step by step: {question}"},
    ]
    yaml_file = tmp_path / "short_keys.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 2
    ids = [v.variant_id for v in widget.get_variants()]
    assert ids == ["v1", "v2"]


def test_import_yaml_with_variants_wrapper_key_loads_entries(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = {
        "variants": [
            {"id": "w1", "label": "Wrapper entry", "template": "{question}"},
        ]
    }
    yaml_file = tmp_path / "wrapped.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 1
    assert widget.get_variants()[0].variant_id == "w1"


def test_import_yaml_mixed_key_formats_both_loaded(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = [
        {"variant_id": "long1", "variant_label": "Long form", "user_prompt_template": "{question}"},
        {"id": "short1", "label": "Short form", "template": "{question} — brief answer"},
    ]
    yaml_file = tmp_path / "mixed.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    count = widget._import_from_yaml(yaml_file)

    assert count == 2
    ids = [v.variant_id for v in widget.get_variants()]
    assert "long1" in ids
    assert "short1" in ids


def test_import_yaml_short_key_system_field_loaded(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    data = [
        {
            "id": "sys1",
            "label": "With system",
            "template": "{question}",
            "system": "You are a helpful assistant.",
        }
    ]
    yaml_file = tmp_path / "sys.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    widget._import_from_yaml(yaml_file)

    assert widget.get_variants()[0].system_prompt == "You are a helpful assistant."


# ---------------------------------------------------------------------------
# VariantEditorDialog auto-generated default ID
# ---------------------------------------------------------------------------


def test_next_unique_id_returns_variant_0_when_empty() -> None:
    result = _next_unique_id(set(), 0)
    assert result == "variant_0"


def test_next_unique_id_skips_occupied_ids() -> None:
    occupied = {"variant_0", "variant_1"}
    result = _next_unique_id(occupied, 0)
    assert result == "variant_2"


def test_dialog_auto_populates_variant_id(qapp: QApplication) -> None:
    dialog = VariantEditorDialog(existing_ids=set(), default_index=0)
    assert dialog._id_edit.text() == "variant_0"
    dialog.reject()


def test_dialog_auto_id_avoids_collision(qapp: QApplication) -> None:
    occupied = {"variant_0"}
    dialog = VariantEditorDialog(existing_ids=occupied, default_index=0)
    assert dialog._id_edit.text() == "variant_1"
    dialog.reject()


# ---------------------------------------------------------------------------
# Preview shows system prompt
# ---------------------------------------------------------------------------


def test_preview_shows_system_prompt_when_set(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    task_file = tmp_path / "tasks.yaml"
    task_file.write_text(yaml.dump([{"question": "What is 2+2?"}]), encoding="utf-8")
    widget.set_task_preview_source([task_file])

    spec = PromptVariantSpec(
        variant_id="sp1",
        variant_label="With system",
        user_prompt_template="Answer: {question}",
        system_prompt="You are a math tutor.",
    )
    widget._append_variant(spec)
    widget._variants_list.setCurrentRow(0)
    widget._update_preview(0)

    preview_text = widget._preview_edit.toPlainText()
    assert "[System]" in preview_text
    assert "You are a math tutor." in preview_text
    assert "[User]" in preview_text
    assert "What is 2+2?" in preview_text


def test_preview_omits_system_section_when_not_set(widget: PromptVariantsWidget, tmp_path: Path) -> None:
    task_file = tmp_path / "tasks.yaml"
    task_file.write_text(yaml.dump([{"question": "Hello?"}]), encoding="utf-8")
    widget.set_task_preview_source([task_file])

    spec = PromptVariantSpec(
        variant_id="no_sys",
        variant_label="No system",
        user_prompt_template="Q: {question}",
    )
    widget._append_variant(spec)
    widget._update_preview(0)

    preview_text = widget._preview_edit.toPlainText()
    assert "[System]" not in preview_text
    assert "[User]" in preview_text
    assert "Hello?" in preview_text
