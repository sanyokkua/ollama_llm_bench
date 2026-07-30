"""Architecture guard: ``ResultGateway``'s two mirrored ``Protocol`` declarations stay in sync
(STORY-108 spec-conformance fix).

``adapters/ui_gateways/protocols.py`` and ``ui/results/protocols.py`` each declare their own
copy of ``ResultGateway`` (by design -- ``import-linter``'s "Adapters never import the UI
layer" contract forbids the adapters copy from ever importing the UI copy directly, so no
single source of truth can exist as an import; see either module's own docstring for the full
rationale). Both docstrings state the same invariant: "Any change to one side of a pair must be
mirrored in the other." This test enforces that invariant for the one method the STORY-108
spec-conformance review found had drifted (``chart_data``'s return type) and would have caught
that regression before it shipped.

This file lives under ``tests/architecture/`` -- not colocated under either module's own
``tests/`` directory -- because it is inherently a cross-module (``adapters`` + ``ui``) check;
``testing.md``'s "colocated tests test only their own module" rule places a check like this at
the top level, and because this file's own module name (``tests.architecture.*``) falls outside
the ``ollama_llm_bench.adapters``/``ollama_llm_bench.ui`` namespaces the import-linter contracts
match, importing both Protocol modules together here is legal, unlike doing so from
``adapters/ui_gateways/tests/`` (forbidden) or production code in either module.
"""

import typing

from ollama_llm_bench.adapters.ui_gateways.protocols import ResultGateway as AdapterResultGateway
from ollama_llm_bench.ui.results.protocols import ResultGateway as UiResultGateway


def test_chart_data_return_type_matches_across_both_protocol_copies() -> None:
    """Proves: the two ``ResultGateway.chart_data`` mirrors declare the identical return type.

    A prior regression had ``ui/results/protocols.py`` declare the narrower ``ChartData``
    while ``adapters/ui_gateways/protocols.py`` declared the correct ``ChartData | HeatmapData``
    (what ``ChartAggregator.compute`` actually returns) -- meaning the concrete
    ``_ResultGateway`` did not structurally satisfy the UI-owned Protocol under
    ``mypy --strict``, even though nothing caught it at the ``pytest`` layer. Comparing the
    resolved type hints (not the raw annotation strings) proves the two declarations denote the
    same runtime type, not merely textually identical spelling.
    """
    adapter_hints = typing.get_type_hints(AdapterResultGateway.chart_data)
    ui_hints = typing.get_type_hints(UiResultGateway.chart_data)

    assert adapter_hints["return"] == ui_hints["return"]
