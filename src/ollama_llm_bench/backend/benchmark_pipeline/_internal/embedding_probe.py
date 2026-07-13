"""DD-48 run-start embedding fail-fast probe (04_EVALUATION_PIPELINE.md §4)."""

from ollama_llm_bench.backend.embedding.protocols import EmbeddingService

_PROBE_TEXT = "probe"


def run_needs_embeddings(
    *,
    run_mode_graded: bool,
    cosine_enabled: bool,
    has_golden_answer_task: bool,
    keyword_enabled: bool,
    has_semantic_terms_task: bool,
) -> bool:
    """Return whether this run needs the embedding pair at all (DD-46/DD-48)."""
    if not run_mode_graded:
        return False
    needs_cosine = cosine_enabled and has_golden_answer_task
    needs_keyword_semantic = keyword_enabled and has_semantic_terms_task
    return needs_cosine or needs_keyword_semantic


def run_embedding_probe(*, embedding_service: EmbeddingService) -> str | None:
    """Issue one embed("probe") call under the held BENCHMARK_RUN gate.

    Returns:
        None on success; a human-readable error string naming the embedding
        pair on failure. Never raises — the caller decides what to persist.
    """
    vector = embedding_service.embed(_PROBE_TEXT)
    if not vector:
        return "embedding endpoint cannot embed: the run-start probe returned an empty vector"
    return None
