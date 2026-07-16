"""Architecture guard for adapters/qt_table_models (STORY-046 Definition of Done)."""

from pytest_archon import archrule


def test_qt_table_models_holds_no_backend_protocol_or_asyncio() -> None:
    """Proves: STORY-046-AC-1

    adapters/qt_table_models depends only on PySide6 and backend.domain — no
    backend store/service Protocol module, and no asyncio anywhere.
    """
    (
        archrule("qt-table-models-is-domain-only")
        .match("ollama_llm_bench.adapters.qt_table_models*")
        .should_not_import("asyncio")
        .should_not_import("ollama_llm_bench.backend.persistence.*")
        .should_not_import("ollama_llm_bench.backend.stores.*")
        .should_not_import("ollama_llm_bench.backend.benchmark_pipeline*")
        .check("ollama_llm_bench")
    )
