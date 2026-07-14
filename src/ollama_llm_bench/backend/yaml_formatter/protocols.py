"""YamlFormatter — this module's swap point (§1, §2, §3)."""

from typing import Protocol

from ollama_llm_bench.backend.yaml_formatter.models import SaveResult, TaskFileDocument


class YamlFormatter(Protocol):
    """The single writer of task files — comment-preserving, atomic, canonical."""

    def load_document(self, source_path: str, /) -> TaskFileDocument:
        """Round-trip load ``source_path`` into a comment-carrying document handle.

        blocking. The returned handle carries both data and its attached
        comment tokens. This module cannot import ``backend/errors``
        (`01_MODULE_INVENTORY.md` §4.5) and is not the file-content-rejection
        authority — ``TaskFileValidator`` is — so a genuinely malformed YAML
        file's ``ruamel.yaml`` error (a ``YAMLError``) is left to propagate
        uncaught.

        Args:
            source_path: The absolute path of the ``.yaml``/``.yml`` file to load.

        Returns:
            The round-trip document handle for ``source_path``.
        """
        ...

    def save(
        self, *, document: TaskFileDocument, target_path: str, format_on_save: bool
    ) -> SaveResult:
        """Serialize ``document`` and atomically commit it to ``target_path``.

        blocking; runs off the UI thread (the caller's responsibility — see
        `16_CONCURRENCY_MODEL.md`). Never raises for an I/O failure — reports
        a typed ``SaveResult`` instead. A comment-token-count mismatch after
        reordering is an ``icontract`` postcondition violation (a
        ``FormatterDefect``, §8) — a genuine programmer error, left to
        propagate and crash the process.

        Args:
            document: The document handle to serialize; owned by the caller,
                not mutated while the save is in flight.
            target_path: The absolute path of the ``.yaml``/``.yml`` file to write.
            format_on_save: Whether to apply canonical field ordering (§6.3)
                and style normalization (§6.4). The top-level shape is
                normalized to Form A and the save is atomic either way.

        Returns:
            The typed save outcome.
        """
        ...
