"""Architecture smoke test: the package tree scaffolded in Phase 0 is importable and Qt-free.

Proves the scaffold end-to-end -- real signal, not a fake pass (see
docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md).
"""


def test_import_ollama_llm_bench_succeeds() -> None:
    import ollama_llm_bench  # noqa: F401, PLC0415  # import-success is the assertion
