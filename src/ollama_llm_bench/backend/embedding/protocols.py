"""EmbeddingService — this module's swap point (§9, 08-E §10)."""

from typing import Protocol

from ollama_llm_bench.backend.domain import CosineScore, CosineThreshold


class EmbeddingService(Protocol):
    """The single shared embedding + cosine-scoring facade for one run (§9).

    One instance is constructed once at the composition root (bound to the
    run's frozen ``EMBEDDING``-role model and settings snapshot) and shared by
    the cosine evaluator, the keyword-semantic evaluator, and the
    readiness/capability probe (§9, §6.1). It is called by at most one worker
    at a time — execution is strictly serial app-wide (D-R-16) — so the
    service is a single-accessor structure with no internal locking.
    """

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the embedding vector for ``text``, cache-backed (§6.2).

        Normalises ``text`` by trimming surrounding whitespace, checks the
        in-memory LRU cache keyed on ``(provider_id, model_name,
        normalised_text)`` for this instance's fixed embedding model, and on a
        miss calls the provider's embedding endpoint, stores the result in the
        cache, and returns it. Never raises to its caller — a provider failure
        or timeout degrades to an empty vector for that call and is counted
        toward the consecutive-failure short-circuit (§7, §8, DD-70); once
        short-circuited, no further provider call is attempted and every
        subsequent call also degrades to an empty vector.

        Args:
            text: The raw text to embed; only surrounding whitespace is
                trimmed before it is sent or used as a cache key.

        Returns:
            The embedding vector for ``text``, or an empty tuple when the
            underlying provider call failed, timed out, or the cosine
            dimension is already short-circuited (§8).
        """
        ...

    def cosine(self, text_a: str, text_b: str) -> CosineScore:
        """Return the whole-text cosine similarity between two texts (§6.3, §6.4).

        Embeds ``text_a`` and ``text_b`` (each cache-backed via :meth:`embed`)
        and computes the clamped ``[0.0, 1.0]`` Cosine Score between the two
        vectors. Returns ``0.0`` whenever either vector has zero norm — an
        empty/degenerate text, or a vector that could not be produced because
        the underlying embedding call failed, timed out, or the cosine
        dimension is short-circuited (§8). The comparison is always the whole
        text against the whole text — no sliding-window, sub-span, or
        fragment matching (§6.4).

        Args:
            text_a: The first text to compare (e.g. ``sanitized_response``).
            text_b: The second text to compare (e.g. ``golden_answer``).

        Returns:
            The clamped Cosine Score in ``[0.0, 1.0]``. Never raises.
        """
        ...

    def cosine_threshold(self) -> CosineThreshold:
        """Return the run's single ``eval.cosine_threshold`` pass/fail cutoff (§6.4).

        Read once from the frozen run settings snapshot this instance was
        constructed with. The service maps no score to a verdict itself — the
        cosine phase compares the returned threshold against a Cosine Score
        and writes ``cosine_verdict``.

        Returns:
            The configured cosine threshold, typed as ``CosineThreshold``.
        """
        ...

    def is_short_circuited(self) -> bool:
        """Whether the cosine dimension has short-circuited run-wide (DD-70, §7).

        ``True`` once ``eval.embedding_consecutive_failures_to_skip``
        consecutive embedding failures/timeouts have occurred with no
        intervening success; a single success resets the counter. Once
        short-circuited for this service instance, no further embedding call
        is attempted for the remainder of the run.

        Returns:
            ``True`` when the cosine dimension is short-circuited for the rest
            of this instance's lifetime, ``False`` otherwise.
        """
        ...
