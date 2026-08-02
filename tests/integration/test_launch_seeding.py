"""Integration test for default-seeding idempotency (STORY-078-AC-4)."""

from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_write_connection,
)
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _shutdown(handle: AppHandle) -> None:
    handle.window.close()
    handle.run_dispatcher.shutdown(timeout_ms=2000)
    handle.http_client.close()
    handle.write_conn.close()


@pytest.mark.parametrize(
    ("pre_seed_providers", "expected_provider_count"),
    [
        pytest.param(False, 3, id="empty_catalog_gets_seeded"),
        pytest.param(True, 1, id="non_empty_catalog_left_untouched"),
    ],
)
def test_seeding_is_idempotent_per_target_table(
    isolated_home: Path,
    qapp: QApplication,
    pre_seed_providers: bool,  # noqa: FBT001  # pytest.mark.parametrize test fixture
    expected_provider_count: int,
) -> None:
    """Proves: STORY-078-AC-4

    Default seeding is idempotent per target table: an empty provider catalog
    gets the three bundled default providers written; a non-empty catalog is
    left untouched; the settings table stays empty either way so every setting
    resolves to its built-in default.
    """
    # Arrange
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    if pre_seed_providers:
        write_conn.execute(
            "INSERT INTO providers "
            "(provider_id, name, provider_type, enabled, base_url, provider_order) "
            "VALUES ('00000000-0000-4000-8000-000000000001', 'Custom Provider', "
            "'openai_compatible', 1, 'http://localhost:11434', 0)"
        )
        write_conn.commit()
    write_conn.close()

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())

    # Assert
    provider_count = handle.write_conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    settings_count = handle.write_conn.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0]
    assert provider_count == expected_provider_count
    assert settings_count == 0

    # Cleanup
    _shutdown(handle)
