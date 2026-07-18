"""In-memory ordered ``(provider_id, model_name)`` selection set (STORY-054-AC-3, AC-5).

Widget-local -- not a shared backend store. Insertion order is preserved (a plain
``dict`` used as an ordered set) so the Selected Models Summary renders pairs in the
order the user selected them, per ``02_New_Benchmark_Widget/state_machine.md`` §3.
"""

__all__: list[str] = ["SelectionStore"]


class SelectionStore:
    """An ordered, in-memory set of ``(provider_id, model_name)`` pairs."""

    def __init__(self) -> None:
        self._pairs: dict[tuple[str, str], None] = {}

    def add(self, provider_id: str, model_name: str) -> None:
        """Add ``(provider_id, model_name)``; a no-op if already present."""
        self._pairs[(provider_id, model_name)] = None

    def remove(self, provider_id: str, model_name: str) -> None:
        """Remove ``(provider_id, model_name)``; a no-op if absent."""
        self._pairs.pop((provider_id, model_name), None)

    def clear_provider(self, provider_id: str) -> None:
        """Remove every pair belonging to ``provider_id``; other providers untouched."""
        for pair in [p for p in self._pairs if p[0] == provider_id]:
            del self._pairs[pair]

    def contains(self, provider_id: str, model_name: str) -> bool:
        """Return whether ``(provider_id, model_name)`` is currently selected."""
        return (provider_id, model_name) in self._pairs

    @property
    def pairs(self) -> tuple[tuple[str, str], ...]:
        """Every selected pair, in insertion order."""
        return tuple(self._pairs.keys())

    @property
    def provider_count(self) -> int:
        """The number of distinct providers with at least one selected pair."""
        return len({pair[0] for pair in self._pairs})
