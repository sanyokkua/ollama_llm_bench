from pathlib import Path

import pytest

from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def data_api(tmp_path: Path) -> SqLiteDataApi:
    return SqLiteDataApi(tmp_path / "test.db")
