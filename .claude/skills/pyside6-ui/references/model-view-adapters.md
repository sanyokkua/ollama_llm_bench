# Qt Item Models as Adapters — Sort, Filter, Paging, Performance

`QAbstractItemModel` (and its subclasses `QAbstractTableModel`, `QAbstractListModel`) is **not your domain model**. It is an **adapter** that exposes domain objects as rows × columns × roles for `QTableView` / `QTreeView` / `QListView`.

This file covers:
- The adapter discipline (and why violating it is the #1 PySide architectural error).
- `QSortFilterProxyModel` for sorting and filtering.
- `canFetchMore` / `fetchMore` for paged datasets.
- Performance pitfalls in `flags()` / `data()` for large models.
- Threading rules.

See also:
- [../SKILL.md §8 Model/View for Tables](../SKILL.md) for the quick rules.
- [testing-pyside.md](testing-pyside.md) for `qtmodeltester` usage.

---

## 1. The Adapter Discipline

```
┌──────────────────────────────┐
│  Domain (backend/core/)      │
│                              │
│  @dataclass(frozen=True)     │
│  class BenchmarkResult:      │
│      result_id: int          │
│      score: float            │
│      ...                     │
└──────────────┬───────────────┘
               │ wraps
               ▼
┌──────────────────────────────┐
│  Item Model adapter (ui/)    │
│                              │
│  class ResultsTableModel(    │
│        QAbstractTableModel): │
│      _results: list[BenchmarkResult]  │
│                              │
│      data(idx, role) → str / QColor / ... │
└──────────────┬───────────────┘
               │ consumed by
               ▼
┌──────────────────────────────┐
│  View                        │
│  QTableView                  │
└──────────────────────────────┘
```

The adapter:

- **Holds a list (or other collection) of domain objects.** It does not duplicate the data into rows.
- **Translates domain → display format** in `data()`. A `BenchmarkResult.score` of `0.7234` becomes `"0.72"` for `Qt.DisplayRole`, and a `QColor` for `Qt.ForegroundRole` based on pass/fail.
- **Does NOT mutate domain objects.** Edits go through the presenter → use-case → repository, then back into the model via a `replace_all` or `update_row` call from the presenter.
- **Does NOT enforce business rules.** "An order must have ≥ 1 line item" lives in the domain. The model adapter only adapts shape.

### What the adapter must NOT do

- ❌ Put business validation in `setData()` (validation belongs in the domain or presenter)
- ❌ Call repositories / SDKs from `data()` or `setData()`
- ❌ Hold a `QObject` reference to a widget
- ❌ Be mutated from a background thread

### Why `QStandardItemModel` is discouraged

`QStandardItemModel` stores data inside the model itself (in `QStandardItem` instances). For anything beyond a quick prototype:

- It encourages mutation through the model API rather than through use-cases.
- It tightly couples the view layer to a specific row/column shape.
- It loses the connection to your domain objects.

Use `QStandardItemModel` for one-off dialogs (a 5-row pop-up). For anything stored in `backend/`, subclass `QAbstractTableModel` and store domain objects.

---

## 2. Canonical Item-Model Adapter

```python
# ui/widgets/result/model.py
from __future__ import annotations

from typing import override

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, Qt,
)
from PySide6.QtGui import QColor

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult, BenchmarkResultStatus,
)


class ResultsTableModel(QAbstractTableModel):
    """Table model adapting BenchmarkResult instances for QTableView."""

    HEADERS = ("Model", "Task", "Verdict", "Score", "Cosine")
    _COL_MODEL, _COL_TASK, _COL_VERDICT, _COL_SCORE, _COL_COSINE = range(5)

    # Custom roles for non-display data
    BENCHMARK_RESULT_ROLE = Qt.ItemDataRole.UserRole + 1
    SCORE_NUMERIC_ROLE = Qt.ItemDataRole.UserRole + 2  # for sorting

    def __init__(self, results: list[BenchmarkResult] | None = None) -> None:
        super().__init__()
        self._results: list[BenchmarkResult] = list(results or [])

    @override
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._results)

    @override
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    @override
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid() or index.row() >= len(self._results):
            return None
        result = self._results[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == self._COL_MODEL:
                return result.model_name
            if col == self._COL_TASK:
                return result.task_id
            if col == self._COL_VERDICT:
                return result.status.value
            if col == self._COL_SCORE:
                return f"{result.score:.2f}" if result.score is not None else "-"
            if col == self._COL_COSINE:
                return f"{result.cosine_score:.2f}" if result.cosine_score is not None else "-"

        if role == Qt.ForegroundRole and col == self._COL_VERDICT:
            if result.status == BenchmarkResultStatus.COMPLETED:
                return QColor("#34D399")
            if result.status == BenchmarkResultStatus.FAILED:
                return QColor("#F87171")

        if role == self.BENCHMARK_RESULT_ROLE:
            return result

        if role == self.SCORE_NUMERIC_ROLE and col == self._COL_SCORE:
            return result.score or 0.0

        return None

    @override
    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole,
    ) -> object:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    @override
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return _CACHED_FLAGS  # see "Performance" below

    # ---- Mutation API (called by presenter) -------------------------

    def replace_all(self, results: list[BenchmarkResult]) -> None:
        """Replace all rows. Use for bulk updates."""
        self.beginResetModel()
        self._results = list(results)
        self.endResetModel()

    def append(self, result: BenchmarkResult) -> None:
        """Append one row."""
        row = len(self._results)
        self.beginInsertRows(QModelIndex(), row, row)
        self._results.append(result)
        self.endInsertRows()

    def update_row(self, row: int, result: BenchmarkResult) -> None:
        """Replace a single row's data."""
        if not (0 <= row < len(self._results)):
            return
        self._results[row] = result
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)


_CACHED_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
```

### Why use custom roles (`UserRole + N`)

`Qt.DisplayRole` returns formatted strings ("0.72"). Sorting/filtering needs the numeric value, so a separate `SCORE_NUMERIC_ROLE` returns `0.7234`. Without this, sorting "0.72" vs "0.7" gives lexicographic (wrong) order.

### Pair `beginX` / `endX` ALWAYS

These come in pairs:

| Operation | Begin | End |
|---|---|---|
| Insert rows | `beginInsertRows(parent, first, last)` | `endInsertRows()` |
| Remove rows | `beginRemoveRows(parent, first, last)` | `endRemoveRows()` |
| Move rows | `beginMoveRows(...)` | `endMoveRows()` |
| Bulk reset | `beginResetModel()` | `endResetModel()` |
| Insert columns | `beginInsertColumns(...)` | `endInsertColumns()` |

Skipping the `beginX` call corrupts the view. Use `try/finally` if there's any chance of exception between begin and end:

```python
self.beginInsertRows(QModelIndex(), row, row)
try:
    self._results.append(result)
finally:
    self.endInsertRows()
```

Use `dataChanged.emit(topLeft, bottomRight, roles=[...])` for **in-place** cell changes (no row count change). Pass the `roles` list when you know which roles changed — Qt skips redrawing other roles.

---

## 3. Sorting and Filtering with `QSortFilterProxyModel`

Never modify the source model to sort/filter — wrap it with a proxy.

### Basic usage

```python
from PySide6.QtCore import QSortFilterProxyModel

# In the presenter:
self._source_model = ResultsTableModel()
self._proxy = QSortFilterProxyModel(self)
self._proxy.setSourceModel(self._source_model)
self._proxy.setFilterKeyColumn(ResultsTableModel._COL_MODEL)
self._proxy.setSortRole(ResultsTableModel.SCORE_NUMERIC_ROLE)  # numeric, not string
self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

# In the view (or via presenter pushing the model):
view.setModel(self._proxy)
view.setSortingEnabled(True)
```

The view consumes the proxy; the proxy maps row indexes to the source model. The source model never changes during sorting or filtering.

### Custom filter logic

For multi-column or composite filters, subclass and override `filterAcceptsRow`:

```python
class ResultsFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._verdict_filter: str | None = None
        self._text_filter: str = ""

    def set_verdict_filter(self, verdict: str | None) -> None:
        self._verdict_filter = verdict
        self.invalidateFilter()  # re-evaluate

    def set_text_filter(self, text: str) -> None:
        self._text_filter = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source = self.sourceModel()
        result = source.data(
            source.index(source_row, 0),
            ResultsTableModel.BENCHMARK_RESULT_ROLE,
        )
        if self._verdict_filter and result.status.value != self._verdict_filter:
            return False
        if self._text_filter and self._text_filter not in result.model_name.lower():
            return False
        return True
```

Always call `invalidateFilter()` (or `invalidateRowsFilter()`) when filter state changes.

### Custom sort logic (type-correct ordering)

For columns sorted by date, number, or any non-string value, override `lessThan`:

```python
class ResultsFilterProxyModel(QSortFilterProxyModel):
    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        col = left.column()
        if col == ResultsTableModel._COL_SCORE:
            left_score = self.sourceModel().data(left, ResultsTableModel.SCORE_NUMERIC_ROLE) or 0.0
            right_score = self.sourceModel().data(right, ResultsTableModel.SCORE_NUMERIC_ROLE) or 0.0
            return left_score < right_score
        return super().lessThan(left, right)
```

This avoids the "1, 10, 11, 2, 21, 3" string-sort surprise.

### Multiple views off one source model

Two views can show the same source through different proxies:

```python
self._source = ResultsTableModel()

self._left_proxy = ResultsFilterProxyModel()
self._left_proxy.setSourceModel(self._source)
self._left_proxy.set_verdict_filter("PASS")
left_view.setModel(self._left_proxy)

self._right_proxy = ResultsFilterProxyModel()
self._right_proxy.setSourceModel(self._source)
self._right_proxy.set_verdict_filter("FAIL")
right_view.setModel(self._right_proxy)
```

Update the source once; both views update via the proxies. No data duplication.

---

## 4. Large Datasets — `canFetchMore` / `fetchMore`

For datasets too large to load eagerly (≥ 10K rows from a repository), implement lazy paging.

```python
class LazyResultsTableModel(QAbstractTableModel):
    PAGE_SIZE = 500

    def __init__(self, *, repository: ResultsRepository, run_id: int) -> None:
        super().__init__()
        self._repo = repository
        self._run_id = run_id
        self._loaded: list[BenchmarkResult] = []
        self._total_known: int | None = None
        self._loaded_count: int = 0

    @override
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._loaded)

    @override
    def canFetchMore(self, parent: QModelIndex) -> bool:
        if parent.isValid():
            return False
        if self._total_known is None:
            self._total_known = self._repo.count_for_run(self._run_id)
        return self._loaded_count < self._total_known

    @override
    def fetchMore(self, parent: QModelIndex) -> None:
        if parent.isValid():
            return
        page = self._repo.page_for_run(
            self._run_id,
            offset=self._loaded_count,
            limit=self.PAGE_SIZE,
        )
        if not page:
            return
        first = self._loaded_count
        last = first + len(page) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._loaded.extend(page)
        self._loaded_count = len(self._loaded)
        self.endInsertRows()
```

### Threading rule for `fetchMore`

The repository call is synchronous. If it's slow (network DB), schedule it on a worker:

1. `canFetchMore` returns `True` and asks the presenter to fetch.
2. Presenter creates a `QRunnable` adapter that calls `repository.page_for_run` on a worker thread.
3. Worker emits a signal with the page data.
4. Main-thread slot updates the model: `beginInsertRows → extend → endInsertRows`.

`QAbstractItemModel` is a `QObject` — only the main thread may touch it.

---

## 5. Performance Pitfalls in Large Models

| Pitfall | Cause | Fix |
|---|---|---|
| Slow `selectAll` on 100K rows | `flags()` called per cell per repaint | Return a precomputed `Qt.ItemFlags` constant; don't rebuild it |
| Slow scrolling | `data(role=Qt.DisplayRole)` re-computes every cell every repaint | Cache computed display strings inside the model |
| `Qt.AlignRight \| Qt.AlignVCenter` showing in profiles | `IntFlag` enum-or operations are surprisingly slow | Compute once at module load: `_RIGHT_VCENTER = Qt.AlignRight \| Qt.AlignVCenter` |
| Insert one row at a time during bulk load | N pairs of `beginInsertRows` / `endInsertRows`, each with view notifications | Use `beginResetModel` / `endResetModel` for bulk |
| Stale display after mutation | Forgot `dataChanged.emit` | Emit `dataChanged` with the changed roles list |

### Performance template

```python
# Module-level, computed once
_DISPLAY_PASS = "PASS"
_DISPLAY_FAIL = "FAIL"
_COLOR_PASS = QColor("#34D399")
_COLOR_FAIL = QColor("#F87171")
_FLAGS_ENABLED_SELECTABLE = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class FastResultsModel(QAbstractTableModel):
    @override
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return _FLAGS_ENABLED_SELECTABLE  # constant, no per-call work

    @override
    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            # Pull from precomputed cache rather than reformat
            return self._display_cache[index.row()][index.column()]
        # ...
```

For very large models, also implement `dataChanged` with a narrowly-scoped `roles=[Qt.DisplayRole]` to let the view skip irrelevant repaints.

---

## 6. Threading Rules

| Operation | Allowed thread | Notes |
|---|---|---|
| Constructing the model | Main | The model lives on the main thread |
| Calling `data()`, `rowCount()`, etc. (view-driven) | Main | Qt's view machinery runs there |
| `beginInsertRows` / `endInsertRows` / `replace_all` | Main | Mutating the model |
| Fetching new pages from a repository | Worker | Yields plain Python data |
| Applying fetched data to the model | Main | Via queued signal from worker |
| `dataChanged.emit` | Main | Signals from the model |

**Never share a model between threads.** Worker threads produce plain Python data structures (`list[BenchmarkResult]`), emit them via queued signal, and the main-thread slot applies them to the model.

---

## 7. Anti-Patterns

| Anti-pattern | Symptom | Fix |
|---|---|---|
| Domain object is the model | `class BenchmarkRun(QAbstractTableModel)` | Domain is `@dataclass(frozen=True)`; model is a separate adapter class |
| Business validation in `setData` | "Save fails silently because invalid" | Validation in domain / presenter |
| Sort by display string | "1, 10, 11, 2, …" | Use a `SortRole`; override `lessThan` |
| Filter by mutating source data | Source loses rows that were filtered out | Use `QSortFilterProxyModel`; source is unchanged |
| `QStandardItemModel` for production data | Data duplicated, tightly coupled, no domain link | Subclass `QAbstractTableModel`, store domain objects |
| Insert rows without `begin/end` | View desyncs, may crash | Always pair `begin*` and `end*` |
| `flags()` rebuilds enum each call | Profile shows hot spot | Module-level constant |
| Background thread calls `model.appendRow` | Race conditions, crashes | Worker emits data; main-thread slot mutates model |
| Model has a use-case dependency | `class FooModel: __init__(self, save_uc)` | Model adapts; presenter coordinates |

---

## 8. Testing Item Models

Use `pytest-qt`'s `qtmodeltester` fixture to verify model protocol correctness:

```python
def test_results_model_passes_qt_model_tester(qtmodeltester):
    model = ResultsTableModel([sample_result()])
    qtmodeltester.check(model, force_py=True)
```

`qtmodeltester` runs the same battery as `QAbstractItemModelTester` from Qt — invalid indexes, role correctness, signal protocol, header data. If you have bugs in your model, this test catches them before they crash in production.

See [testing-pyside.md §"Item-model tests"](testing-pyside.md) for the full setup.
