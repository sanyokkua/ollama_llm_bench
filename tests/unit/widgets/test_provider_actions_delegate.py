"""Unit tests for ProviderActionsDelegate signal emission."""

import pytest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from ollama_llm_bench.ui.widgets.settings.provider_actions_delegate import ProviderActionsDelegate


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


class TestProviderActionsDelegate:
    def _make_editor(self, qapp: QApplication, row: int) -> tuple[ProviderActionsDelegate, object, object]:
        """Return (delegate, editor, parent_widget). Caller must keep parent_widget alive."""
        from unittest.mock import MagicMock

        from PySide6.QtCore import QModelIndex
        from PySide6.QtWidgets import QWidget

        delegate = ProviderActionsDelegate()
        parent = QWidget()
        option = QStyleOptionViewItem()
        index = MagicMock(spec=QModelIndex)
        index.row.return_value = row
        editor = delegate.createEditor(parent, option, index)
        return delegate, editor, parent

    def test_test_button_emits_test_requested(self, qapp: QApplication) -> None:
        delegate, editor, _parent = self._make_editor(qapp, row=2)
        received: list[int] = []
        delegate.signals.test_requested.connect(received.append)

        from PySide6.QtWidgets import QAbstractButton

        test_btn = next(b for b in editor.findChildren(QAbstractButton) if b.text() == "Test")
        test_btn.click()

        assert received == [2]

    def test_edit_button_emits_edit_requested(self, qapp: QApplication) -> None:
        delegate, editor, _parent = self._make_editor(qapp, row=1)
        received: list[int] = []
        delegate.signals.edit_requested.connect(received.append)

        from PySide6.QtWidgets import QAbstractButton

        edit_btn = next(b for b in editor.findChildren(QAbstractButton) if b.text() == "Edit")
        edit_btn.click()

        assert received == [1]

    def test_delete_button_emits_delete_requested(self, qapp: QApplication) -> None:
        delegate, editor, _parent = self._make_editor(qapp, row=0)
        received: list[int] = []
        delegate.signals.delete_requested.connect(received.append)

        from PySide6.QtWidgets import QAbstractButton

        delete_btn = next(b for b in editor.findChildren(QAbstractButton) if b.text() == "Delete")
        delete_btn.click()

        assert received == [0]

    def test_different_rows_emit_correct_index(self, qapp: QApplication) -> None:
        delegate_r0, editor_r0, _p0 = self._make_editor(qapp, row=0)
        delegate_r5, editor_r5, _p5 = self._make_editor(qapp, row=5)
        received_r0: list[int] = []
        received_r5: list[int] = []
        delegate_r0.signals.test_requested.connect(received_r0.append)
        delegate_r5.signals.test_requested.connect(received_r5.append)

        from PySide6.QtWidgets import QAbstractButton

        btn_r0 = next(b for b in editor_r0.findChildren(QAbstractButton) if b.text() == "Test")
        btn_r5 = next(b for b in editor_r5.findChildren(QAbstractButton) if b.text() == "Test")
        btn_r0.click()
        btn_r5.click()

        assert received_r0 == [0]
        assert received_r5 == [5]

    def test_refreshed_editor_emits_updated_row_index(self, qapp: QApplication) -> None:
        """After a row is deleted and editors are refreshed, the surviving row editor fires the new index.

        Simulates: 3-row table, row 0 deleted, editors for rows 0 and 1 recreated.
        Clicking Edit on the refreshed row-0 editor must emit 0 (not 1, the pre-delete index).
        """
        from PySide6.QtWidgets import QAbstractButton

        # Before deletion: row 1 editor captures closure index = 1
        _delegate_old, editor_old_row1, _parent_old = self._make_editor(qapp, row=1)
        received_old: list[int] = []
        _delegate_old.signals.edit_requested.connect(received_old.append)

        edit_old = next(b for b in editor_old_row1.findChildren(QAbstractButton) if b.text() == "Edit")
        edit_old.click()
        assert received_old == [1]

        # After deletion of row 0: the delegate creates a NEW editor for row 0 (formerly row 1)
        delegate_new, editor_new_row0, _parent_new = self._make_editor(qapp, row=0)
        received_new: list[int] = []
        delegate_new.signals.edit_requested.connect(received_new.append)

        edit_new = next(b for b in editor_new_row0.findChildren(QAbstractButton) if b.text() == "Edit")
        edit_new.click()
        assert received_new == [0]  # refreshed closure captures correct post-delete index
