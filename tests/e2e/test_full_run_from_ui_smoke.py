"""End-to-end: a whole benchmark driven from the New Benchmark UI, fully offline.

The real composed application, the real `pipeline-dispatcher` thread, the real
five-phase pipeline including the judge, the real provider adapter and the real
`openai` SDK -- against a `pytest-httpserver` wire stub bound to `127.0.0.1`
(`07_TESTING_STANDARD.md` §7a). Nothing is monkeypatched and no live model is
contacted.

Platform-agnostic by construction (§12): no `QT_QPA_PLATFORM` is set here, and
every assertion is on widget state or persisted data -- never geometry, focus,
or activation -- so the same tests pass under `just check` (native) and
`just test-e2e` (offscreen).
"""

from collections.abc import Callable
import functools
import json
from pathlib import Path
import sqlite3
from typing import Final, cast
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton, QTableView, QWidget
import pytest
from pytest_httpserver import HTTPServer
from pytestqt.qtbot import QtBot
from werkzeug import Request, Response

from ollama_llm_bench.backend.domain import (
    ResolutionLayer,
    RunId,
    RunMode,
    RunStatus,
    Verdict,
)
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    open_read_connection,
)
from ollama_llm_bench.backend.persistence.providers import create_providers_store
from ollama_llm_bench.backend.persistence.results import create_results_store
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.platform import make_platform_detector
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget

_READINESS_TIMEOUT_MS = 15_000
_RUN_TIMEOUT_MS = 30_000
_UI_REFRESH_TIMEOUT_MS = 5000
_SHUTDOWN_TIMEOUT_MS = 2000
_CHECKING_HEALTH_LABEL: Final[str] = "Checking"

_TEST_MODEL_NAME: Final[str] = "test-model"
_JUDGE_MODEL_NAME: Final[str] = "judge-model"
_EMBEDDING_MODEL_NAME: Final[str] = "embed-model"

_GOLDEN_ANSWER: Final[str] = "Paris"
_TEST_MODEL_ANSWER: Final[str] = "The seat of government of the French Republic sits on the Seine."
"""The canned answer the test model streams.

Deliberately does NOT contain the golden answer as a substring: a keyword match
would resolve the verdict at the KEYWORD layer and the judge -- the layer this
story exists to exercise end to end -- would never be called.
"""

_TASK_FILE_BODY: Final[str] = f"""schema_version: 1
tasks:
  - task_id: t1
    question: What is the capital of France?
    golden_answer: {_GOLDEN_ANSWER}
"""

_EMBEDDING_VECTOR: Final[tuple[float, ...]] = (0.1, 0.2, 0.3, 0.4)

_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})
"""`pytest-httpserver` reports itself as `localhost`, so a literal `127.0.0.1`
substring check would reject its own address."""


def _is_loopback_host(netloc: str) -> bool:
    """Whether `netloc` (`host` or `host:port`) names the loopback interface."""
    return netloc.rsplit(":", 1)[0].strip("[]") in _LOOPBACK_HOSTS


def _sse_body(chunks: list[dict[str, object]]) -> str:
    """Assemble a canned SSE stream body, terminal sentinel included.

    Restated from `backend/provider_openai_compatible/tests/test_chat_stream.py`
    -- no importable shared home exists under `tests/` (see `conftest.py`).
    """
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


def _chat_stream_body(*, model: str, content: str) -> str:
    """One content chunk, one finish chunk carrying usage."""
    return _sse_body(
        [
            {
                "id": "1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
            },
            {
                "id": "1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        ]
    )


def _chat_completions_handler(request: Request) -> Response:
    """Branch on the request body's `model`, so inference and judging differ.

    The judge parses a JSON object out of the response text, while the test
    model must return ordinary prose. One shared body would force a single
    payload into both roles and make the verdict depend on whichever way the
    judge's parser happened to read the prose.
    """
    payload = cast("dict[str, object]", request.get_json())
    model = str(payload.get("model", ""))
    content = (
        json.dumps({"verdict": "PASS", "reasoning": "The answer names the right city."})
        if model == _JUDGE_MODEL_NAME
        else _TEST_MODEL_ANSWER
    )
    return Response(
        _chat_stream_body(model=model, content=content), content_type="text/event-stream"
    )


def _register_wire_stub_routes(httpserver: HTTPServer) -> None:
    """Serve every route a full run actually calls.

    `_probe_reachable` issues a bare `GET` against the SDK's normalised base URL
    (which gains a trailing slash), so both spellings of the base path are
    registered.
    """
    for base in ("/v1", "/v1/"):
        httpserver.expect_request(base, method="GET").respond_with_json({"status": "ok"})
    httpserver.expect_request("/v1/models", method="GET").respond_with_json(
        {
            "object": "list",
            "data": [
                {"id": name, "object": "model", "created": 0, "owned_by": "wire-stub"}
                for name in (_TEST_MODEL_NAME, _JUDGE_MODEL_NAME, _EMBEDDING_MODEL_NAME)
            ],
        }
    )
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_handler(
        _chat_completions_handler
    )
    httpserver.expect_request("/v1/embeddings", method="POST").respond_with_json(
        {
            "object": "list",
            "model": _EMBEDDING_MODEL_NAME,
            "data": [{"object": "embedding", "index": 0, "embedding": list(_EMBEDDING_VECTOR)}],
            "usage": {"prompt_tokens": 4, "total_tokens": 4},
        }
    )


def _details_row_count(handle: AppHandle) -> int:
    """The Details table's current row count; -1 when it has no model yet.

    Read through a bounded `waitUntil` rather than once, because the terminal
    refresh is genuinely asynchronous: `flow.is_running()` flips false on the
    dispatcher thread immediately after the terminal event is *emitted*, and the
    real `QtEventBusDeliverer` queues that event onto the GUI thread. Polling is
    not a weakened assertion -- if the refresh never happens the wait times out
    and the test fails, which is exactly what the negative control (deleting the
    three `recompute_and_push()` calls) produces.
    """
    table = cast("QTableView", handle.window.findChild(QTableView, "details_tab.table"))
    model = table.model()
    return -1 if model is None else model.rowCount()


def _health_dot(handle: AppHandle) -> HealthDotWidget:
    """Locate the status bar's health dot.

    Restated from `test_launch_idle_shutdown_smoke.py`'s identical helper. The dot
    is rebuilt on every render (`StatusBarWidget._rebuild_health_dot`), so it must
    be re-located on each poll rather than resolved once.
    """
    health_region = cast("QWidget", handle.window.findChild(QWidget, "health_region"))
    layout = health_region.layout()
    assert layout is not None
    item = layout.itemAt(0)
    assert item is not None
    dot = cast("HealthDotWidget", item.widget())
    assert dot is not None
    return dot


def _confirm_run_summary_dialog(qtbot: QtBot) -> None:
    """Find the modal Run Summary dialog opened by Start and click its Start button.

    Restated from `tests/integration/test_new_benchmark_start.py`. Must be armed
    with `QTimer.singleShot` *before* the Start click: the dialog runs its own
    nested event loop, and with no `pytest-timeout` configured an unconfirmed
    modal hangs the whole suite with no output.
    """
    dialog = cast("QDialog", QApplication.activeModalWidget())
    start_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "common_dialogs.run_summary.start_button")
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        start_button, Qt.MouseButton.LeftButton
    )


def _new_benchmark_view(handle: AppHandle) -> NewBenchmarkView:
    return cast("NewBenchmarkView", handle.window.findChild(QWidget, "new_benchmark.view"))


def _reselect_first_provider(dropdown: QComboBox) -> None:
    """Force the provider dropdown to re-emit its selection.

    `ProviderDropdownWidget` populates itself and auto-selects index 0 under a
    `QSignalBlocker`, so the initial selection never reaches `provider_changed`
    and the dependent model list stays empty. Setting the index away and back
    drives the same `currentIndexChanged` -> `provider_changed` path a real user
    click does.
    """
    dropdown.setCurrentIndex(-1)
    dropdown.setCurrentIndex(0)


def _configure_graded_run(view: NewBenchmarkView, *, task_file: Path) -> None:
    """Drive the widget into a startable GRADED configuration.

    Uses the sections' own test affordances rather than the native Add File
    dialog, which would open a real modal file picker.
    """
    view.mode_selector.select_mode_for_test(RunMode.GRADED)
    _reselect_first_provider(
        cast(
            "QComboBox",
            view.test_models_section.findChild(
                QComboBox, "new_benchmark.test_models.provider_dropdown"
            ),
        )
    )
    view.test_models_section.toggle_model_for_test(_TEST_MODEL_NAME)
    view.task_files_section.add_files_for_test((str(task_file),))
    judge_models = cast(
        "QComboBox", view.judge_section.findChild(QComboBox, "new_benchmark.judge.model_dropdown")
    )
    judge_models.setCurrentIndex(judge_models.findText(_JUDGE_MODEL_NAME))


def _start_run_and_wait(handle: AppHandle, view: NewBenchmarkView, qtbot: QtBot) -> None:
    """Click Start, confirm the Run Summary modal, and wait for the run to settle.

    Polls `flow.is_running()` -- the repo's established idiom -- rather than
    subscribing to `_run_finished`: the real `QtEventBusDeliverer` queues delivery
    onto the GUI thread, while `is_running()` flips false only once the terminal
    status has been persisted.
    """
    QTimer.singleShot(0, lambda: _confirm_run_summary_dialog(qtbot))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        view.start_button, Qt.MouseButton.LeftButton
    )
    qtbot.waitUntil(lambda: not handle.flow.is_running(), timeout=_RUN_TIMEOUT_MS)


def _run_a_graded_benchmark(
    *,
    qtbot: QtBot,
    httpserver: HTTPServer,
    build_wire_stub_app: Callable[[], AppHandle],
    task_file: Path,
) -> AppHandle:
    """Launch the app, configure a GRADED run, start it, and wait for it to settle.

    Returns the still-live handle: the caller asserts against it and is
    responsible for calling `shutdown_handle` exactly once.
    """
    _register_wire_stub_routes(httpserver)
    handle = build_wire_stub_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    # Start is gated on the single-inference gate, which the startup readiness
    # probe itself holds; clicking before it settles produces a rejected run that
    # reads like a pipeline bug.
    qtbot.waitUntil(
        lambda: _health_dot(handle).text_label != _CHECKING_HEALTH_LABEL,
        timeout=_READINESS_TIMEOUT_MS,
    )
    view = _new_benchmark_view(handle)
    _configure_graded_run(view, task_file=task_file)
    _start_run_and_wait(handle, view, qtbot)
    return handle


@pytest.fixture
def task_file(tmp_path: Path) -> Path:
    """One graded task whose golden answer the canned model answer does not contain."""
    path = tmp_path / "graded_tasks.yaml"
    path.write_text(_TASK_FILE_BODY, encoding="utf-8")
    return path


def _read_conn_factory() -> Callable[[], sqlite3.Connection]:
    """A fresh read-only connection onto the same on-disk database `build_app` opened.

    Resolved through the same platform detector production uses, so this reads
    the real `tmp_path`-backed file rather than an in-memory stand-in.
    """
    db_path = make_platform_detector().detect().app_data_root / DB_FILENAME
    return functools.partial(open_read_connection, db_path)


def _runs_store(handle: AppHandle) -> RunsStore:
    return create_runs_store(handle.write_conn, handle.write_lock, _read_conn_factory())


def _results_store(handle: AppHandle) -> ResultsStore:
    return create_results_store(handle.write_conn, handle.write_lock, _read_conn_factory())


def _latest_run_id(handle: AppHandle) -> RunId:
    """The newest persisted run, read from the real on-disk database."""
    runs = _runs_store(handle).list_runs()
    assert runs, "no run was persisted"
    return max(run.run_id for run in runs)


def test_run_started_from_ui_completes_and_persists_results(
    qtbot: QtBot,
    httpserver: HTTPServer,
    build_wire_stub_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
    task_file: Path,
) -> None:
    """Proves: STORY-085-AC-1

    A run started from the New Benchmark UI against the wire stub is executed by
    the real dispatcher thread and the real pipeline to a terminal COMPLETED run
    whose result rows are persisted in the real on-disk database.
    """
    # Arrange + Act
    handle = _run_a_graded_benchmark(
        qtbot=qtbot,
        httpserver=httpserver,
        build_wire_stub_app=build_wire_stub_app,
        task_file=task_file,
    )
    try:
        run_id = _latest_run_id(handle)
        results_store = _results_store(handle)
        runs_store = _runs_store(handle)

        # Assert
        assert runs_store.get_run(run_id).status is RunStatus.COMPLETED
        assert results_store.list_results(run_id) != ()
    finally:
        shutdown_handle(handle)


def test_graded_run_produces_binary_verdicts(
    qtbot: QtBot,
    httpserver: HTTPServer,
    build_wire_stub_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
    task_file: Path,
) -> None:
    """Proves: STORY-085-AC-2

    Every graded result carries a binary PASS/FAIL verdict, persisted. `Verdict`
    has no UNKNOWN member, so an ungraded row is `None` -- that, not a third enum
    value, is the real failure mode. The canned answer keyword-misses the golden
    answer on purpose, so the verdict resolves through the judge layer.
    """
    # Arrange + Act
    handle = _run_a_graded_benchmark(
        qtbot=qtbot,
        httpserver=httpserver,
        build_wire_stub_app=build_wire_stub_app,
        task_file=task_file,
    )
    try:
        run_id = _latest_run_id(handle)
        results_store = _results_store(handle)
        rows = results_store.list_results(run_id)

        # Assert
        assert rows != ()
        assert all(row.verdict in {Verdict.PASS, Verdict.FAIL} for row in rows)
        assert any(row.resolution_layer is ResolutionLayer.JUDGE for row in rows)
    finally:
        shutdown_handle(handle)


def test_result_widget_reflects_persisted_results(
    qtbot: QtBot,
    httpserver: HTTPServer,
    build_wire_stub_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
    task_file: Path,
) -> None:
    """Proves: STORY-085-AC-3

    Once the run settles, the Result widget's Details table renders one row per
    persisted result with no further user action -- the terminal-refresh path.
    """
    # Arrange + Act
    handle = _run_a_graded_benchmark(
        qtbot=qtbot,
        httpserver=httpserver,
        build_wire_stub_app=build_wire_stub_app,
        task_file=task_file,
    )
    try:
        run_id = _latest_run_id(handle)
        results_store = _results_store(handle)
        persisted = results_store.list_results(run_id)
        # Assert -- see `_details_row_count` on why this waits rather than reads once
        assert persisted != ()
        qtbot.waitUntil(
            lambda: _details_row_count(handle) == len(persisted), timeout=_UI_REFRESH_TIMEOUT_MS
        )
        assert _details_row_count(handle) == len(persisted)
    finally:
        shutdown_handle(handle)


def test_full_run_contacts_no_live_server(
    qtbot: QtBot,
    httpserver: HTTPServer,
    build_wire_stub_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
    task_file: Path,
) -> None:
    """Proves: STORY-085-AC-4

    Every request the application issued reached the local wire stub on
    `127.0.0.1`, and no enabled provider row carries a non-loopback base URL. The
    chat-request floor is what stops this passing vacuously: a run that staged no
    tasks contacts nothing at all, which would otherwise read as a clean pass.
    """
    # Arrange + Act
    handle = _run_a_graded_benchmark(
        qtbot=qtbot,
        httpserver=httpserver,
        build_wire_stub_app=build_wire_stub_app,
        task_file=task_file,
    )
    try:
        served = [request for request, _response in httpserver.log]
        chat_requests = [r for r in served if r.path == "/v1/chat/completions"]
        providers_store = create_providers_store(
            handle.write_conn, handle.write_lock, _read_conn_factory()
        )
        enabled_base_urls = [
            config.base_url
            for config in providers_store.list_providers()
            if config.enabled and config.base_url is not None
        ]

        # Assert
        assert chat_requests != []
        assert all(_is_loopback_host(r.host) for r in served)
        assert enabled_base_urls != []
        assert all(_is_loopback_host(urlparse(url).netloc) for url in enabled_base_urls)
    finally:
        shutdown_handle(handle)
