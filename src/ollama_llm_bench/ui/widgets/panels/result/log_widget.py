from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QTextEdit, QVBoxLayout, QWidget


class LogWidget(QWidget):
    def __init__(self):
        super().__init__()

        self._clean_button = QPushButton("Clean")
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout = QVBoxLayout()
        layout.addWidget(self._clean_button)
        layout.addWidget(self._text_edit)
        self.setLayout(layout)

        self._clean_button.clicked.connect(self.clear_text)

    def append_text(self, text: str):
        self._text_edit.append(text)
        scrollbar = self._text_edit.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def clear_text(self):
        self._text_edit.clear()
