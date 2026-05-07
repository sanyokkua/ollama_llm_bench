---
name: pyside6
description: DEPRECATED — superseded by pyside6-ui. Use pyside6-ui for all PySide6 and styling work. This file retains the PyQt6→PySide6 import migration reference only.
paths: src/ollama_llm_bench/qt_classes/**/*.py, src/ollama_llm_bench/ui/**/*.py
allowed-tools: Read, Grep, Glob
---

# PySide6 Skill — Deprecated

> **This skill has been superseded by `pyside6-ui`.** Use the `pyside6-ui` skill for all PySide6 widget work, theming, styling, threading, and Qt architecture.

## Import Migration Reference (PyQt6 → PySide6)

| PyQt6 | PySide6 |
|-------|---------|
| `from PyQt6.QtCore import pyqtSignal` | `from PySide6.QtCore import Signal` |
| `from PyQt6.QtCore import pyqtSlot` | `from PySide6.QtCore import Slot` |
| `from PyQt6.QtWidgets import ...` | `from PySide6.QtWidgets import ...` |
| `from PyQt6.QtCore import QMutex, QMutexLocker` | `from PySide6.QtCore import QMutex, QMutexLocker` |

When touching existing PyQt6 files, migrate imports opportunistically to PySide6 equivalents.
