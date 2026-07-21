"""Architecture tests scoped to STORY-067's own additions (Definition of done).

Asserts: the General-tab field registry maps every control to exactly one
``08-G`` setting key with no duplicates (STORY-067-AC-1); and
``_internal/controller.py`` never imports a raw backend persistence or
import-export module directly -- every write goes through the locally-
declared ``SettingsGateway`` (D-R-06). The broader no-``setStyleSheet``/no-
colour-literal/no-``asyncio`` sweep for the whole ``ui/settings_dialog/`` tree
(which already recursively covers every file this story added, including
``_internal/general_tab/`` and the two new ``_internal/sub_dialogs/`` pairs)
lives in ``test_story_066_settings_dialog.py`` and is not duplicated here.
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.field_binders import FIELD_REGISTRY

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MODULE_ROOT = _PACKAGE_ROOT / "ui" / "settings_dialog"
_CONTROLLER_FILE = _MODULE_ROOT / "_internal" / "controller.py"

_FORBIDDEN_MODULES = (
    "ollama_llm_bench.backend.persistence",
    "ollama_llm_bench.backend.import_export",
)


def test_general_tab_registers_no_setting_key_outside_field_registry() -> None:
    """Proves: STORY-067-AC-1

    Every General-tab control binds to exactly one ``FIELD_REGISTRY`` entry --
    no two entries share a ``setting_key``.
    """
    keys = [spec.setting_key for spec in FIELD_REGISTRY]
    assert len(keys) == len(set(keys)), "every General-tab control must bind to exactly one key"


def test_controller_module_imports_no_backend_store_protocol_directly() -> None:
    """Proves: STORY-067 Definition of done

    ``_internal/controller.py`` never imports ``backend.persistence`` or
    ``backend.import_export`` directly -- Save/Import/Export/Reset all go
    through the locally-declared ``SettingsGateway`` (D-R-06).
    """
    tree = ast.parse(_CONTROLLER_FILE.read_text(encoding="utf-8"), filename=str(_CONTROLLER_FILE))
    offenders = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and any(node.module.startswith(forbidden) for forbidden in _FORBIDDEN_MODULES)
    ]
    assert offenders == [], (
        f"controller.py must depend only on SettingsGateway, found import of {offenders}"
    )
