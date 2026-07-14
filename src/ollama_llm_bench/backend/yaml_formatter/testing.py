"""A configurable fake ``YamlFormatter`` for downstream module tests."""

from ruamel.yaml.comments import CommentedMap

from ollama_llm_bench.backend.yaml_formatter.models import SaveResult, TaskFileDocument

__all__: list[str] = ["FakeYamlFormatter"]


class FakeYamlFormatter:
    """An in-memory fake with externally settable per-path documents and save results.

    No real I/O behind it — set the document ``load_document`` should return
    and the ``SaveResult`` a save should produce directly.
    """

    def __init__(self) -> None:
        self._documents: dict[str, TaskFileDocument] = {}
        self._save_result = SaveResult(succeeded=True)
        self.recorded_loads: list[str] = []
        self.recorded_saves: list[tuple[TaskFileDocument, str, bool]] = []

    def load_document(self, source_path: str, /) -> TaskFileDocument:
        """Record the call and return whatever ``set_document`` configured, or empty."""
        self.recorded_loads.append(source_path)
        return self._documents.get(source_path, CommentedMap())

    def save(
        self, *, document: TaskFileDocument, target_path: str, format_on_save: bool
    ) -> SaveResult:
        """Record the call and return whatever ``set_save_result`` configured."""
        self.recorded_saves.append((document, target_path, format_on_save))
        return self._save_result

    def set_document(self, source_path: str, document: TaskFileDocument) -> None:
        """Test helper: force ``load_document(source_path)``'s return value."""
        self._documents[source_path] = document

    def set_save_result(self, result: SaveResult) -> None:
        """Test helper: force every subsequent ``save(...)``'s return value."""
        self._save_result = result
