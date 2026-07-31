"""Architecture test: the settings registry's defaults table is public (STORY-110-AC-5).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.6; ``06_Settings_Dialog/description.md`` §9 (Reset must re-seed every settings key,
which requires enumerating the in-code defaults table from outside
``backend/settings/``'s private internals).
"""

import ast
import inspect
from pathlib import Path

from ollama_llm_bench.adapters.ui_gateways._internal.settings import gateway
from ollama_llm_bench.backend import settings
from ollama_llm_bench.backend.settings import DEFAULTS


def test_settings_defaults_table_is_on_the_public_surface() -> None:
    """Proves: STORY-110-AC-5

    Given the settings module is imported through its package root only, when
    the settings registry's defaults table is read, then it is reachable from
    ``backend/settings/``'s public surface without importing anything under
    ``backend/settings/_internal/``.
    """
    assert len(DEFAULTS) > 0
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in DEFAULTS.items())
    # Opaque UI-state keys the Settings dialog's General tab never exposes must still be
    # present -- this is the exact reason `reset_to_defaults` needed this table promoted
    # (description.md §9).
    assert "ui.window_geometry" in DEFAULTS
    assert "ui.splitter_sizes" in DEFAULTS
    assert "benchmark.last_mode" in DEFAULTS


def test_defaults_import_site_never_reaches_into_internal() -> None:
    """Proves: STORY-110-AC-5

    Statically confirms no module under ``adapters/ui_gateways/`` imports
    ``backend.settings._internal`` to reach ``DEFAULTS`` -- the reach-in
    ``import-linter`` forbids -- by asserting the concrete gateway's own import
    statement names only the package root.
    """
    source = inspect.getsource(gateway)
    tree = ast.parse(source, filename=inspect.getfile(gateway))
    import_from_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    settings_imports = [
        node.module or ""
        for node in import_from_nodes
        if (node.module or "").startswith("ollama_llm_bench.backend.settings")
    ]

    assert settings_imports, "expected at least one backend.settings import in the gateway"
    assert all("_internal" not in module for module in settings_imports)


def test_defaults_table_source_file_is_discoverable() -> None:
    """Proves: STORY-110-AC-5

    Sanity guard: the settings package root actually resolves to a real
    file on disk, so the two assertions above are exercising the genuine
    package, not an empty/mocked stand-in.
    """
    package_root = Path(inspect.getfile(settings)).parent
    assert package_root.is_dir()
    assert (package_root / "api.py").is_file()
