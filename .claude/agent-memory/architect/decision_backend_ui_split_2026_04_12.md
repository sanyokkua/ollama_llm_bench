---
name: Backend/UI package split decision (2026-04-12)
description: Architectural decision to introduce backend/ and ui/ namespace groups; covers migration strategy, import path mapping, and key constraints
type: project
---

Decided to introduce a `backend/` namespace package under `src/ollama_llm_bench/`
containing `core/`, `services/`, and pure `utils/`, while expanding `ui/` to
absorb `qt_classes/` (moved to `ui/qt_classes/`) and `widget_utils.py` (moved
to `ui/utils/widget_utils.py`).

**Why:** User requested explicit visual and logical separation of pure-Python
backend from PySide6-dependent UI code. Secondary goal: fix the `utils/widget_utils.py`
violation (QComboBox import in an otherwise pure-Python package).

**How to apply:** When any future feature adds a new module, place it under
`backend/` if it has no PySide6 dependency, under `ui/` if it does. The rule
mirrors the existing layering contract but is now structurally enforced by
directory boundaries.

Key import path mapping:
- `ollama_llm_bench.core.*` → `ollama_llm_bench.backend.core.*`
- `ollama_llm_bench.services.*` → `ollama_llm_bench.backend.services.*`
- `ollama_llm_bench.utils.{run,text,time}_utils` → `ollama_llm_bench.backend.utils.*`
- `ollama_llm_bench.utils.widget_utils` → `ollama_llm_bench.ui.utils.widget_utils`
- `ollama_llm_bench.qt_classes.*` → `ollama_llm_bench.ui.qt_classes.*`
- `ollama_llm_bench.ui.*` (controllers, widgets, main_window) — unchanged

`app_context.py` and `main.py` remain at root — they are the composition root
and entry point by design and legitimately import from both `backend/` and `ui/`.

There are 0 tests at the time of this decision (no `tests/` directory exists).
Open question: create empty `tests/conftest.py` to prevent pytest from failing
on missing testpaths directory.

PLAN.md written to project root with 13 implementation steps.
