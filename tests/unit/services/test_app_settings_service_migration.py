"""Unit tests for AppSettingsService legacy key migration."""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_JUDGE_OVERRIDE_COSINE_LOW,
    SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL,
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
    AppSettingsService,
)
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def db_api(tmp_path: Path) -> SqLiteDataApi:
    return SqLiteDataApi(tmp_path / "test.sqlite")


def _seed_setting(db_api: SqLiteDataApi, key: str, value: str) -> None:
    db_api.set_app_setting(key=key, value=value)


def test_migration_keyword_fail_key_is_moved(db_api: SqLiteDataApi) -> None:
    _seed_setting(db_api, "eval.force_judge_on_keyword_fail", "true")

    AppSettingsService(data_api=db_api)

    assert db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL) is not None
    setting = db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL)
    assert setting is not None
    assert setting.value == "true"


def test_migration_cosine_key_is_moved(db_api: SqLiteDataApi) -> None:
    _seed_setting(db_api, "eval.force_judge_on_cosine", "true")

    AppSettingsService(data_api=db_api)

    setting = db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_COSINE_LOW)
    assert setting is not None
    assert setting.value == "true"


def test_migration_run_analysis_key_is_moved(db_api: SqLiteDataApi) -> None:
    _seed_setting(db_api, "eval.force_judge_on_run_analysis", "true")

    AppSettingsService(data_api=db_api)

    setting = db_api.get_app_setting(SETTING_JUDGE_RUN_ANALYSIS_ENABLED)
    assert setting is not None
    assert setting.value == "true"


def test_migration_is_idempotent(db_api: SqLiteDataApi) -> None:
    _seed_setting(db_api, "eval.force_judge_on_keyword_fail", "true")

    AppSettingsService(data_api=db_api)
    AppSettingsService(data_api=db_api)

    setting = db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL)
    assert setting is not None
    assert setting.value == "true"


def test_migration_does_not_overwrite_existing_new_key(db_api: SqLiteDataApi) -> None:
    _seed_setting(db_api, "eval.force_judge_on_keyword_fail", "true")
    _seed_setting(db_api, SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL, "false")

    AppSettingsService(data_api=db_api)

    setting = db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL)
    assert setting is not None
    assert setting.value == "false"


def test_migration_no_old_keys_leaves_new_keys_absent(db_api: SqLiteDataApi) -> None:
    AppSettingsService(data_api=db_api)

    assert db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL) is None
    assert db_api.get_app_setting(SETTING_JUDGE_OVERRIDE_COSINE_LOW) is None
    assert db_api.get_app_setting(SETTING_JUDGE_RUN_ANALYSIS_ENABLED) is None
