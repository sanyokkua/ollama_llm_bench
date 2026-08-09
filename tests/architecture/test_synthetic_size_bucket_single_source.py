"""Architecture guard: ui/new_benchmark/ restates no synthetic size-bucket token target
(STORY-092 Definition of Done).

The five §2.3 token targets live in exactly one place —
``backend/performance_task_generator/``'s published ``SIZE_BUCKETS`` table. A second copy
inside the widget is not a cosmetic duplication: if the two drift, the Performance Matrix
offers the user a size the generator no longer recognises, ``generate()`` raises the §8
"no matching size bucket" error, and run creation aborts. This scan is what stops that
copy coming back.

Modelled on ``tests/architecture/test_main_window_style_authority.py``'s literal scanners,
including their ``"tests" not in path.parts`` exclusion: the scope is deliberately
non-test files only. A test that independently restates the spec's numbers — STORY-071's
``assert widget.selected_input_sizes == (64, 256)``, STORY-092-AC-3's own case table — is
what makes those assertions real; deriving them from ``SIZE_BUCKETS`` would reduce them to
asserting ``x == x``.
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench
from ollama_llm_bench.backend.performance_task_generator import SIZE_BUCKETS

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_NEW_BENCHMARK_ROOT = _PACKAGE_ROOT / "ui" / "new_benchmark"
_BUCKET_TARGETS: frozenset[int] = frozenset(SIZE_BUCKETS)


def _iter_non_test_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "tests" not in path.parts)


def _embeds_bucket_target_literal(tree: ast.AST) -> bool:
    """Report whether the tree contains a bucket token target as a bare ``int`` literal.

    ``type(node.value) is int`` rather than ``isinstance`` on purpose: ``bool`` is a
    subclass of ``int``, and the captions carry their approximate token figures inside
    strings (``"MD — ~250 tok · 1 page · 380 words"``), which a constant-value check on
    ``int`` correctly ignores.
    """
    return any(
        isinstance(node, ast.Constant) and type(node.value) is int and node.value in _BUCKET_TARGETS
        for node in ast.walk(tree)
    )


def test_at_least_one_new_benchmark_source_file_discovered() -> None:
    """Sanity guard: an empty scan would make the drift check vacuously pass."""
    assert len(_iter_non_test_python_files(_NEW_BENCHMARK_ROOT)) > 0


def test_new_benchmark_restates_no_bucket_token_target() -> None:
    """Proves: STORY-092 Definition of Done

    No non-test file under ``ui/new_benchmark/`` writes a synthetic size-bucket
    token target as an integer literal; the widget takes those numbers from the
    Performance Task Generator's published ``SIZE_BUCKETS`` table instead.
    """
    # Arrange / Act
    offenders = [
        str(path.relative_to(_PACKAGE_ROOT))
        for path in _iter_non_test_python_files(_NEW_BENCHMARK_ROOT)
        if _embeds_bucket_target_literal(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        )
    ]
    # Assert
    assert offenders == []
