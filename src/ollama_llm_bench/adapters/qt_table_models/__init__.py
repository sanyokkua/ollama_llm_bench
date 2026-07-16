"""QAbstractTableModel adapters (summary, details, providers)."""

from ollama_llm_bench.adapters.qt_table_models.api import (
    make_details_table_model,
    make_providers_table_model,
    make_summary_table_model,
)
from ollama_llm_bench.adapters.qt_table_models.models import (
    DetailsTableRow,
    ProviderTableRow,
    SummaryTableRow,
)

__all__: list[str] = [
    "DetailsTableRow",
    "ProviderTableRow",
    "SummaryTableRow",
    "make_details_table_model",
    "make_providers_table_model",
    "make_summary_table_model",
]
