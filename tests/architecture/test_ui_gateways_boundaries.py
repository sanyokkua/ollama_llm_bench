"""Architecture guard for adapters/ui_gateways (STORY-105 Definition of Done)."""

from pytest_archon import archrule


def test_ui_gateways_holds_no_ui_import() -> None:
    """adapters/ui_gateways (STORY-105) holds no asyncio-family import and never
    imports the ui layer -- the gateway Protocol it annotates against is a
    deliberate structural duplicate, not an import, of the UI-owned declaration
    (ADR-0014).
    """
    (
        archrule("ui-gateways-holds-no-ui-import")
        .match("ollama_llm_bench.adapters.ui_gateways*")
        .should_not_import("asyncio")
        .should_not_import("anyio")
        .should_not_import("qasync")
        .should_not_import("ollama_llm_bench.ui.*")
        .check("ollama_llm_bench")
    )
