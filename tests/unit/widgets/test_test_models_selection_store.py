"""Unit tests for TestModelsSelectionStore."""

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import ModelDescriptor, ModelSelectionKey
from ollama_llm_bench.ui.widgets.panels.control.test_models_selection_store import (
    TestModelsSelectionStore,
)

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_descriptor(provider_id: str, model_name: str) -> ModelDescriptor:
    """Create a minimal ModelDescriptor for test use."""
    return ModelDescriptor(
        provider_id=provider_id,
        provider_type="openai_compatible",
        model_name=model_name,
        display_label=f"{provider_id} · {model_name}",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(qapp: QApplication) -> TestModelsSelectionStore:
    """Return a fresh empty TestModelsSelectionStore per test."""
    return TestModelsSelectionStore()


# ---------------------------------------------------------------------------
# Tests — count and membership
# ---------------------------------------------------------------------------


def test_add_model_increases_count(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "model1"))
    assert store.count == 1


def test_add_duplicate_is_idempotent(store: TestModelsSelectionStore) -> None:
    d = _make_descriptor("pA", "model1")
    store.add(d)
    store.add(d)
    assert store.count == 1


def test_remove_model_decreases_count(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "model1"))
    store.remove(ModelSelectionKey(provider_id="pA", model_name="model1"))
    assert store.count == 0


def test_remove_nonexistent_key_is_noop(store: TestModelsSelectionStore) -> None:
    store.remove(ModelSelectionKey(provider_id="pA", model_name="ghost"))
    assert store.count == 0


def test_contains_returns_true_for_added_model(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "model1"))
    assert store.contains(ModelSelectionKey(provider_id="pA", model_name="model1"))


def test_contains_returns_false_for_missing_model(store: TestModelsSelectionStore) -> None:
    assert not store.contains(ModelSelectionKey(provider_id="pA", model_name="ghost"))


# ---------------------------------------------------------------------------
# Tests — all() and filter_by_provider()
# ---------------------------------------------------------------------------


def test_all_returns_every_model(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "m1"))
    store.add(_make_descriptor("pB", "m2"))
    assert len(store.all()) == 2


def test_filter_by_provider_returns_only_that_provider(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "m1"))
    store.add(_make_descriptor("pB", "m2"))
    result = store.filter_by_provider("pA")
    assert len(result) == 1
    assert result[0].provider_id == "pA"


def test_filter_by_provider_returns_empty_for_unknown_provider(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "m1"))
    assert store.filter_by_provider("pZ") == []


# ---------------------------------------------------------------------------
# Tests — clear_for_provider()
# ---------------------------------------------------------------------------


def test_clear_for_provider_leaves_other_providers(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "m1"))
    store.add(_make_descriptor("pB", "m2"))
    store.clear_for_provider("pA")
    assert store.count == 1
    assert store.filter_by_provider("pB")


def test_clear_for_provider_removes_multiple_models_from_that_provider(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "m1"))
    store.add(_make_descriptor("pA", "m2"))
    store.add(_make_descriptor("pB", "m3"))
    store.clear_for_provider("pA")
    assert store.count == 1


# ---------------------------------------------------------------------------
# Tests — clear_all()
# ---------------------------------------------------------------------------


def test_clear_all_empties_store(store: TestModelsSelectionStore) -> None:
    store.add(_make_descriptor("pA", "m1"))
    store.add(_make_descriptor("pB", "m2"))
    store.clear_all()
    assert store.count == 0


# ---------------------------------------------------------------------------
# Tests — cross-provider key uniqueness
# ---------------------------------------------------------------------------


def test_same_model_name_across_providers_are_distinct(store: TestModelsSelectionStore) -> None:
    """Critical: (pA, llama3) and (pB, llama3) must coexist as distinct selections."""
    store.add(_make_descriptor("pA", "llama3:8b"))
    store.add(_make_descriptor("pB", "llama3:8b"))
    assert store.count == 2
    assert store.contains(ModelSelectionKey(provider_id="pA", model_name="llama3:8b"))
    assert store.contains(ModelSelectionKey(provider_id="pB", model_name="llama3:8b"))


# ---------------------------------------------------------------------------
# Tests — signal emission
# ---------------------------------------------------------------------------


def test_selection_changed_emitted_on_add(store: TestModelsSelectionStore, mocker: MockerFixture) -> None:
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.add(_make_descriptor("pA", "m1"))
    callback.assert_called_once()


def test_selection_changed_not_emitted_on_duplicate_add(store: TestModelsSelectionStore, mocker: MockerFixture) -> None:
    d = _make_descriptor("pA", "m1")
    store.add(d)
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.add(d)  # duplicate — no signal
    callback.assert_not_called()


def test_selection_changed_emitted_on_remove(store: TestModelsSelectionStore, mocker: MockerFixture) -> None:
    store.add(_make_descriptor("pA", "m1"))
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.remove(ModelSelectionKey(provider_id="pA", model_name="m1"))
    callback.assert_called_once()


def test_selection_changed_not_emitted_on_remove_nonexistent(
    store: TestModelsSelectionStore, mocker: MockerFixture
) -> None:
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.remove(ModelSelectionKey(provider_id="pA", model_name="ghost"))
    callback.assert_not_called()


def test_selection_changed_emitted_on_clear_all(store: TestModelsSelectionStore, mocker: MockerFixture) -> None:
    store.add(_make_descriptor("pA", "m1"))
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.clear_all()
    callback.assert_called_once()


def test_clear_all_on_empty_store_does_not_emit(store: TestModelsSelectionStore, mocker: MockerFixture) -> None:
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.clear_all()  # already empty
    callback.assert_not_called()


def test_selection_changed_emitted_on_clear_for_provider(
    store: TestModelsSelectionStore, mocker: MockerFixture
) -> None:
    store.add(_make_descriptor("pA", "m1"))
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.clear_for_provider("pA")
    callback.assert_called_once()


def test_selection_changed_not_emitted_on_clear_for_empty_provider(
    store: TestModelsSelectionStore, mocker: MockerFixture
) -> None:
    callback = mocker.Mock()
    store.selection_changed.connect(callback)
    store.clear_for_provider("pZ")  # no entries for pZ
    callback.assert_not_called()
