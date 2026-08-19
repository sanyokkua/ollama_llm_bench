# STORY-086 — Opt-in, env-gated live smoke tier Implementation Plan

## Context

Every test in this repository is deliberately offline. Provider adapters are exercised against a
`pytest-httpserver` wire stub that replays canned bytes, so the whole suite is deterministic and CI
never needs a model server. That is the right default, and it stays.

What it cannot tell you is whether the app actually works against the Ollama or LM Studio you have
installed on your own machine. STORY-085 landed the offline end-to-end run
(`tests/e2e/test_full_run_from_ui_smoke.py`); this story adds the live counterpart: a separate test
tier that runs *only* when you ask for it, talks to real local servers, and stays completely invisible
to `just check` and to both CI workflows.

ADR-0011 (accepted 2026-07-23) is the authority for the tier existing at all — the testing standard
does not describe one. The spec is cited only for the constraints the tier must not break: CI stays
offline (§12), the `LLMClient` contract suite keeps its wire-stub-only real leg (§6a), cross-cutting
tiers live in the top-level `tests/` tree with every marker registered under `--strict-markers` (§3),
and the readiness probe checks each enabled provider for reachability and at least one model
(`08-M` §5).

**Goal:** A `tests/live_local/` tier that, per local provider, probes health, discovers models, and
runs one tiny real benchmark to `COMPLETED` — gated behind `OLLAMA_BENCH_LIVE_LOCAL_TESTS=1` and the
`live_local` marker, skipping cleanly when either the opt-in or the server is absent.

**Architecture:** Three moving parts. (1) `pyproject.toml` registers the `live_local` marker and adds
`addopts = ["-m", "not live_local"]`, which deselects the tier from every bare `pytest` invocation at
once. (2) `tests/live_local/conftest.py` holds the opt-in gate, a bounded-timeout reachability check,
a live-seeded composed-app rig adapted from `tests/e2e/conftest.py`, and the shared
probe→discover→tiny-run driver. (3) One thin test module per provider calls that driver and asserts
its outcome.

**Tech Stack:** Python 3.13, pytest + pytest-qt, PySide6, msgspec, `httpx`, the `openai` SDK, `uv`, `just`.

## Global Constraints

- Every test is fully annotated and returns `-> None`; Arrange-Act-Assert; one logical assertion per
  test; no `if` and no `for` in a test body (use `@pytest.mark.parametrize`).
- A test proving an acceptance criterion declares it on the **first line of its docstring**, exactly:
  `"""Proves: STORY-086-AC-N`.
- `--strict-markers` is on. An unregistered marker is a **collection error**, not a warning.
- **pytest honours only the last `-m` it is given.** `addopts` must carry exactly one `-m` entry.
  STORY-094 will later extend it to `-m "not live_local and not packaging"` — it must never append a
  second `-m`.
- `just lint` and `just format-check` run `ruff` over `src tests scripts`, so every new file under
  `tests/` must be ruff-clean and ruff-formatted. `mypy --strict` does **not** cover `tests/live_local/`.
- The tier adds **no** change under `src/`.
- No `pytest-timeout` is configured. Every wait must carry its own bound, or a hung live server hangs
  the whole run with no output.
- Any test that shows the real main window needs `@pytest.mark.allow_qt_warnings` (the root
  `_qt_parity_rig` fixture fails on any Qt warning otherwise).
- `AppHandle.shutdown()` is **not idempotent** and `build_app` starts a **non-daemon**
  `pipeline-dispatcher` thread. Skipping shutdown hangs the pytest process at interpreter exit.
- Secrets rule: `api_key_raw` stores only a bare env-var **name**, never a value. Local Ollama and
  LM Studio are keyless — leave it empty (`""`), never invent a placeholder key.

______________________________________________________________________

## The three things that will break the build if you get them wrong

### 1. `just trace` must still see the live tests, or the story cannot be marked `done`

`scripts/_traceability_lib.py::_run_pytest_collect_only` runs a **bare** `pytest --collect-only -q`.
It therefore inherits `addopts`, so once `-m "not live_local"` lands, the live tests are deselected,
never enter `proves_index`, and `traceability.yaml` records AC-1/AC-2 with empty `tests` lists.
`scripts/validate_traceability.py::check_acceptance_criteria_proven` then fails the moment the
story's `status` flips to `done`.

The fix is one line: pass `-m ""` on the command line, which overrides the `addopts` entry and
disables mark filtering entirely. Verified empirically in this repo:

```
$ uv run pytest --collect-only -q tests/architecture              -> 1363 tests collected
$ uv run pytest --collect-only -q -m "unit" tests/architecture    -> no tests collected (1363 deselected)
$ uv run pytest --collect-only -q -m "unit" -m "" tests/architecture -> 1363 tests collected
```

Collection only imports modules; it contacts no server. This is Task 2 and it is not optional.

### 2. The tier must skip at **fixture** time, never at collection time

If `tests/live_local/conftest.py` uses `collect_ignore` or `pytest.skip(allow_module_level=True)`, the
node IDs never exist and problem 1 returns by a different route. Gate with an **autouse fixture** that
calls `pytest.skip(...)` during setup. The tests are always collected; they just do not run.

### 3. Never `from conftest import ...` — it silently binds the wrong module

The controller proved this empirically in this repo before execution began. Under
`--import-mode=importlib`, pytest still registers a plain `conftest.py` in `sys.modules` under the
bare name `conftest`. With more than one conftest collected — this repo has four, and runs
`pytest-randomly` — the name resolves to whichever was imported **last**:

```
$ pytest tests_probe                                  -> live_probe's `from conftest import SHARED`
                                                         returned other_probe's value. FAILED.
$ pytest tests_probe/other_probe tests_probe/live_probe  -> passed (opposite collection order)
```

It does not raise; it returns the wrong module's symbols. Share code between the tier's modules via
**fixtures** (resolved by name, no import) — never by importing `conftest`. Where a non-fixture load
is genuinely required (Task 6, which runs outside the tier), use
`importlib.util.spec_from_file_location` with a **unique** module name, which sidesteps the collision.

______________________________________________________________________

## File structure

| File                                                               | Responsibility                                                                            |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `pyproject.toml` (modify)                                          | Register the `live_local` marker; add the single `-m "not live_local"` entry to `addopts` |
| `scripts/_traceability_lib.py` (modify)                            | Pass `-m ""` in `_run_pytest_collect_only` so trace collection sees the tier              |
| `tests/live_local/conftest.py` (create)                            | Opt-in gate, reachability helper, live app rig, shared smoke driver                       |
| `tests/live_local/test_ollama_live_smoke.py` (create)              | AC-1 — Ollama probe + discover + tiny run                                                 |
| `tests/live_local/test_lmstudio_live_smoke.py` (create)            | AC-2 — LM Studio probe + discover + tiny run                                              |
| `tests/unit/test_live_tier_gating.py` (create)                     | AC-3 — the gating helpers skip cleanly; runs in the offline gate                          |
| `tests/architecture/test_live_tier_excluded_from_gate.py` (create) | AC-4 — `pyproject.toml` registers and deselects the marker                                |
| `justfile` (modify)                                                | `test-live` recipe                                                                        |
| `.github/workflows/pr-gate.yml`, `release.yml` (modify)            | Clarifying comments only — see Task 7                                                     |
| `docs/stories/story-086-*.md` (modify)                             | Correct the AC-3 Test-plan line to its new home; mark `done` at close                     |

### Two deliberate deviations from the story's Test plan

**(a) AC-3's test moves out of the tier.** The story places it at
`tests/live_local/test_live_tier_gating.py` with the `live_local` marker. That is circular: a
criterion asserting *"these tests skip on a machine with no server"* would then itself only run on a
machine where an operator opted in. **Decision (confirmed with the owner): AC-3's test lives at
`tests/unit/test_live_tier_gating.py`**, unmarked, loading the conftest's gating helpers by file
location, so it runs in the offline gate on exactly the machines the claim is about. Task 8 corrects
the story's Test-plan line to match.

**(b) The two provider modules share one driver fixture.** The controller's pre-flight scan found
that the shared probe→discover→run body cannot be shared by import (see mechanic 3 above) and must
not be restated verbatim in both modules. **Decision (confirmed with the owner): the driver and the
base URLs live in `tests/live_local/conftest.py` as fixtures**; each provider module is a thin test
that requests `live_smoke` plus its own base-URL fixture. This kills the unsafe import and the
duplication in one move.

______________________________________________________________________

## Task 1: Register the marker and deselect the tier

**Files:**

- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`)
- Test: `tests/architecture/test_live_tier_excluded_from_gate.py` (create)

**Interfaces:**

- Produces: the `live_local` marker name and the `addopts` `-m` expression that every later task relies on.

- [ ] **Step 1: Write the failing test**

Create `tests/architecture/test_live_tier_excluded_from_gate.py`:

```python
"""Architecture test: the `live_local` tier is registered and deselected by default (STORY-086).

Source of truth: ADR-0011 Decision outcome §1 (the tier is excluded from `just check` and
from CI) and ``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md`` §3
(every pytest marker is declared in ``[tool.pytest.ini_options]`` under ``--strict-markers``).

This is the one STORY-086 guard that runs in the offline gate, on a machine with no Ollama
and no LM Studio installed.
"""

import tomllib
from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MARKER: Final[str] = "live_local"


def _pytest_ini_options() -> dict[str, object]:
    raw = (_REPO_ROOT / "pyproject.toml").read_bytes()
    tool = tomllib.loads(raw.decode("utf-8"))["tool"]
    assert isinstance(tool, dict)
    options = tool["pytest"]["ini_options"]
    assert isinstance(options, dict)
    return options


def test_live_local_marker_excluded_from_default_selection() -> None:
    """Proves: STORY-086-AC-4

    A bare ``uv run pytest`` -- the shape used by ``just test``, ``just coverage-layers``,
    ``release.yml``'s quality gate and ``pr-gate.yml``'s coverage step -- selects no test
    carrying the ``live_local`` marker, and the marker is registered so ``--strict-markers``
    does not turn the tier into a collection error.
    """
    # Arrange
    options = _pytest_ini_options()
    markers = options["markers"]
    addopts = options["addopts"]
    assert isinstance(markers, list)
    assert isinstance(addopts, list)

    # Act
    declared = [entry for entry in markers if str(entry).startswith(f"{_MARKER}:")]
    marker_expressions = [
        str(addopts[index + 1])
        for index, entry in enumerate(addopts)
        if entry == "-m" and index + 1 < len(addopts)
    ]

    # Assert
    assert declared, f"{_MARKER} is not declared in [tool.pytest.ini_options].markers"
    assert len(marker_expressions) == 1, (
        "addopts must carry exactly one -m entry -- pytest honours only the last one, so a "
        "second entry (e.g. STORY-094's packaging tier) would silently disable this one; "
        f"found {marker_expressions}"
    )
    assert f"not {_MARKER}" in marker_expressions[0]
```

- [ ] **Step 2: Run it and verify it fails**

```bash
uv run pytest tests/architecture/test_live_tier_excluded_from_gate.py -q
```

Expected: FAIL on `assert declared` (the marker is not declared yet).

- [ ] **Step 3: Edit `pyproject.toml`**

In `[tool.pytest.ini_options]`, change `addopts` and `markers` to:

```toml
addopts = [
  "--import-mode=importlib",
  "--strict-markers",
  "--strict-config",
  "-ra",
  # ADR-0011: the opt-in live tier never runs in `just check` or CI. pytest honours only
  # the LAST -m it is given, so this must stay a single entry -- STORY-094's packaging
  # tier extends this expression rather than appending its own -m.
  "-m",
  "not live_local",
]
markers = [
  "unit: Fast isolated unit tests",
  "integration: Tests requiring real local resources",
  "slow: Tests exceeding the standard time budget",
  "property: Hypothesis-driven property tests",
  "allow_qt_warnings: Test may emit Qt warnings without failing",
  "live_local: Opt-in tests against a real local Ollama / LM Studio server (ADR-0011); never run in CI",
]
```

- [ ] **Step 4: Run the test and the formatter**

```bash
uv run pytest tests/architecture/test_live_tier_excluded_from_gate.py -q
uv run ruff check --fix tests/architecture/test_live_tier_excluded_from_gate.py
uv run ruff format tests/architecture/test_live_tier_excluded_from_gate.py
```

Expected: `1 passed`, then clean lint/format. (If `taplo` is available in this repo's tooling, also
run `uv run taplo fmt pyproject.toml`; if it is not installed, skip it — do not add the dependency.)

- [ ] **Step 5: Verify nothing else regressed**

```bash
uv run pytest tests/architecture -q
```

Expected: the previous count (1363) **+1** = 1364 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/architecture/test_live_tier_excluded_from_gate.py
git commit -m "feat(story-086): register the live_local marker and deselect it by default"
```

______________________________________________________________________

## Task 2: Keep the traceability generator collecting the tier

**Files:**

- Modify: `scripts/_traceability_lib.py` (`_run_pytest_collect_only`, ~line 452)

**Interfaces:**

- Consumes: the `addopts` `-m` entry from Task 1.

- Produces: a `just trace` / `just trace-check` run that still sees `live_local` node IDs.

- [ ] **Step 1: Record the mechanism**

```bash
uv run pytest --collect-only -q 2>&1 | tail -2
uv run pytest --collect-only -q -m "" 2>&1 | tail -2
```

Expected: identical counts today (no live test exists yet); they will diverge the moment Task 3/4/5
land. Record both numbers in your report.

- [ ] **Step 2: Apply the fix**

In `scripts/_traceability_lib.py`, replace `_run_pytest_collect_only` with:

```python
def _run_pytest_collect_only() -> subprocess.CompletedProcess[str]:
    """Collect every test, including tiers `addopts` deselects by default.

    `pyproject.toml`'s `addopts` carries `-m "not live_local"` so a bare `pytest` never
    runs ADR-0011's opt-in live tier. Traceability is a different question from selection:
    a live test still proves an acceptance criterion, and a `done` story whose AC has an
    empty `tests` list fails `validate_traceability.py`. pytest honours only the last `-m`
    it is given and treats an empty expression as "no filtering", so the trailing `-m ""`
    below overrides `addopts` and restores full discovery. Collection imports test modules;
    it contacts no server (STORY-086).
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", ""],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
```

- [ ] **Step 3: Verify both scripts still work**

```bash
uv run python scripts/trace.py
uv run python scripts/validate_traceability.py
```

Expected: `trace.py` reports the same collected count as before, then
`validate_traceability.py` reports zero gaps.

- [ ] **Step 4: Commit**

```bash
uv run ruff check --fix scripts/_traceability_lib.py && uv run ruff format scripts/_traceability_lib.py
git add scripts/_traceability_lib.py traceability.yaml
git commit -m "fix(story-086): collect deselected tiers when generating traceability"
```

______________________________________________________________________

## Task 3: The tier's conftest — gate, reachability, live app rig, smoke driver

**Files:**

- Create: `tests/live_local/conftest.py`

**Interfaces produced** (Tasks 4/5 consume ONLY the fixtures; Task 6 consumes the two module-level
functions and three constants by path-load):

Module-level (path-loaded by Task 6 only):

- `OPT_IN_ENV_VAR: Final[str] = "OLLAMA_BENCH_LIVE_LOCAL_TESTS"`
- `OPT_IN_ENABLED_VALUE: Final[str] = "1"`
- `REACHABILITY_TIMEOUT_S: Final[float] = 2.0`
- `def live_local_opt_in_enabled(environ: Mapping[str, str]) -> bool`
- `def server_reachable(base_url: str, *, timeout_s: float = REACHABILITY_TIMEOUT_S) -> bool`

Fixtures (the ONLY surface Tasks 4/5 may use):

- `ollama_base_url` -> `str`
- `lmstudio_base_url` -> `str`
- `live_smoke` -> `Callable[[str], LiveSmokeOutcome]`

Plus the public result type `LiveSmokeOutcome` — Tasks 4/5 must NOT import it; they compare against
the value returned by a second fixture, `expected_live_smoke_outcome`, so no cross-module import is
needed anywhere in the tier.

**Note on duplication.** `tests/` contains **zero `__init__.py` files** and pytest runs under
`--import-mode=importlib`, so no shared helper module is importable across tiers.
`tests/e2e/conftest.py` and `tests/integration/conftest.py` already restate the same app rig for
exactly this reason. Restating the *rig* a third time here is the established convention — say so in
the module docstring. Restating the *smoke body* across the two provider modules is NOT: that is what
the `live_smoke` fixture exists to prevent.

- [ ] **Step 1: Read the real sources first, then write**

Before writing a line, read and copy from the real files rather than paraphrasing:

- `tests/e2e/conftest.py` — the authoritative `isolated_home`, `_create_app_data_root_with_schema`,
  `_disconnect_and_discard_warning`, `_disconnect_os_color_scheme_signal`, `_dismiss_message_box`,
  the Show-event modal filter, `build_*_app` and `shutdown_handle`. Match its guard structure exactly;
  `shutdown_handle` in particular has a `try/finally` and a `shiboken6.isValid` guard that are
  load-bearing (STORY-091 spent three review rounds on them).
- `tests/e2e/test_full_run_from_ui_smoke.py` — the health-dot reader and the store construction.
- `src/ollama_llm_bench/compose.py` — the authoritative wiring for `make_system_clock`, `EventBus`,
  and `make_inference_activity_store`; use it to confirm every constructor's real keyword names.
- `src/ollama_llm_bench/backend/provider_openai_compatible/` — confirm the real import path and
  signature of `OpenAICompatibleClient`, `OpenAICompatibleClientCollaborators`, and
  `OpenAICompatibleClientSettings`, and the real names of the probe/list-models methods.
- `src/ollama_llm_bench/backend/persistence/providers/` — confirm `seed_builtin_providers`,
  `create_providers_store`, `replace_providers`, and that `ProviderConfig.provider_order` exists.
- `src/ollama_llm_bench/backend/domain/` — confirm `ProviderType`, `RunMode`, `RunStatus`,
  `ResultStatus`, `ModelDescriptor`, `RunStartRequest`, `ProviderIdStr`.

The code below is a specification of behaviour, not a transcript to paste blind. Where it disagrees
with the real modules, **the real modules win** — correct the code and note the correction in your report.

- [ ] **Step 2: Write the gate and the reachability check**

```python
"""Fixtures for the opt-in live tier: a real composed app against a real local server.

Authority: ADR-0011 Decision outcome §1. Nothing in
``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md`` describes a live
tier -- §12 fixes CI as fully offline with no scheduled workflow (DD-36), and §6a fixes the
``LLMClient`` contract suite's real leg to the wire stub. This tier is a separate surface
that leaves both untouched: it is selected only when ``OLLAMA_BENCH_LIVE_LOCAL_TESTS=1`` and
carries the ``live_local`` marker, which ``pyproject.toml``'s ``addopts`` deselects from every
bare ``pytest`` invocation.

``tests/e2e/conftest.py`` holds an equivalent offline rig, but a conftest applies only to
descendants of its own directory and there are no ``__init__.py`` files under ``tests/`` to
import a shared helper through, so the rig is restated here -- a deliberate duplication
matching what ``tests/e2e/`` and ``tests/integration/`` already do.

Everything the two provider test modules need is exposed as a **fixture**. They must never do
``from conftest import ...``: pytest registers a plain ``conftest.py`` in ``sys.modules`` under
the bare name ``conftest``, so with several conftests collected the name silently resolves to
whichever was imported last -- returning another directory's symbols without raising
(STORY-086).
"""

import functools
import os
import socket
import warnings
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import httpx
import msgspec
import pytest
import shiboken6
from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer, SignalInstance
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

# ... project imports, verified against the real modules in Step 1 ...

OPT_IN_ENV_VAR: Final[str] = "OLLAMA_BENCH_LIVE_LOCAL_TESTS"
"""Set this to ``OPT_IN_ENABLED_VALUE`` to run the tier. Named to match the ``live_local``
marker and to stay unmistakably distinct from STORY-094's packaging variable."""

OPT_IN_ENABLED_VALUE: Final[str] = "1"

REACHABILITY_TIMEOUT_S: Final[float] = 2.0
"""The bounded connection timeout ADR-0011 requires: an absent server must skip, never hang."""

OLLAMA_BASE_URL: Final[str] = "http://localhost:11434/v1"
LMSTUDIO_BASE_URL: Final[str] = "http://localhost:1234/v1"
"""The two built-in local providers' seeded base URLs, matching the ``_BUILTIN_PROVIDER_SEEDS``
in ``backend/persistence/providers`` (``provider_order`` 0 and 1). Verify both against the real
seed table before relying on them."""

PROBE_TIMEOUT_MS: Final[int] = 5_000
INFERENCE_TIMEOUT_MS: Final[int] = 120_000
"""A real model is far slower than the wire stub's canned bytes; STORY-085's 30s ceiling is
not enough for a cold first token on a freshly loaded model."""

READINESS_TIMEOUT_MS: Final[int] = 30_000
RUN_TIMEOUT_MS: Final[int] = 300_000
SHUTDOWN_TIMEOUT_MS: Final[int] = 2_000
GEOMETRY_DEBOUNCE_DRAIN_MS: Final[int] = 300
MODAL_DISMISS_DELAY_MS: Final[int] = 100

TINY_TASK_FILE_BODY: Final[str] = """schema_version: 1
tasks:
  - task_id: live-smoke-1
    question: Reply with the single word OK.
    golden_answer: OK
"""


def live_local_opt_in_enabled(environ: Mapping[str, str]) -> bool:
    """Return whether the tier's opt-in variable is set to its enabling value.

    Takes the environment as an argument (rather than reading ``os.environ``) so the
    offline gating test in ``tests/unit/`` can exercise both branches without mutating
    process state.
    """
    return environ.get(OPT_IN_ENV_VAR) == OPT_IN_ENABLED_VALUE


def server_reachable(base_url: str, *, timeout_s: float = REACHABILITY_TIMEOUT_S) -> bool:
    """Return whether a TCP connection to ``base_url``'s host:port succeeds within the bound.

    A plain socket connect, not an HTTP request: it is the cheapest thing that distinguishes
    "no server here" from "server here but slow", and it cannot hang past ``timeout_s``.
    Never raises -- every failure mode (refused, unresolvable host, timed out) is a `False`.
    """
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _require_live_local_opt_in() -> None:
    """Skip every test in this directory unless the opt-in variable is set.

    A fixture, deliberately -- not ``collect_ignore`` and not a module-level skip. Both of
    those remove the node IDs from ``pytest --collect-only``, which is how
    ``scripts/trace.py`` builds the acceptance-criterion-to-test index; the tests would then
    have no proving test on record and ``just trace-check`` would fail the moment STORY-086
    is marked ``done``. Skipping at setup keeps the nodes collected and simply does not run
    them.
    """
    if not live_local_opt_in_enabled(os.environ):
        pytest.skip(f"{OPT_IN_ENV_VAR} is not set to {OPT_IN_ENABLED_VALUE!r}")


@pytest.fixture
def ollama_base_url() -> str:
    """Ollama's seeded local base URL, handed to tests as a fixture so no test module ever
    needs to import from this conftest."""
    return OLLAMA_BASE_URL


@pytest.fixture
def lmstudio_base_url() -> str:
    """LM Studio's seeded local base URL. See ``ollama_base_url``."""
    return LMSTUDIO_BASE_URL
```

- [ ] **Step 3: Add the app rig** (restated from `tests/e2e/conftest.py` — read it and match it)

```python
LIVE_PROVIDER_ORDER_BY_BASE_URL: Final[dict[str, int]] = {
    OLLAMA_BASE_URL: 0,
    LMSTUDIO_BASE_URL: 1,
}
"""``seed_builtin_providers`` inserts Ollama/LM Studio/llama.cpp at ``provider_order`` 0/1/2
with a fresh UUID on each call, so the order column is the only stable handle on a row."""

_NO_MODELS_GUIDANCE: Final[dict[str, str]] = {
    OLLAMA_BASE_URL: "Ollama is running but exposes no model -- run `ollama pull <model>` first",
    LMSTUDIO_BASE_URL: (
        "LM Studio is running but exposes no model -- load one in its Developer tab first"
    ),
}


class LiveAppRig(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """A built live app plus the provider id its enabled row was assigned."""

    handle: AppHandle
    provider_id: ProviderIdStr


class LiveSmokeOutcome(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The four facts AC-1 and AC-2 assert, in one comparable value.

    Deliberately normalised (``discovered_any: bool``, not a model count) so a test can assert
    the whole outcome in a single equality against ``expected_live_smoke_outcome`` -- one
    logical assertion, and a failure prints a full struct diff naming exactly which of the four
    facts broke.
    """

    reachable: bool
    discovered_any: bool
    run_status: RunStatus
    first_result_status: ResultStatus
```

Then, restated from `tests/e2e/conftest.py`, add: `isolated_home`,
`_create_app_data_root_with_schema`, `_seed_single_live_provider`,
`_disconnect_and_discard_warning`, `_disconnect_os_color_scheme_signal`, `_dismiss_message_box`,
`_DismissReadinessModalOnShow`, `build_live_app`, `shutdown_handle`, and `tiny_task_file`.

`_seed_single_live_provider(*, base_url, model_name) -> ProviderIdStr` must enable exactly the
built-in row whose seeded `base_url` matches and disable the rest, so the startup readiness probe
dials one server and no other. Note: leaving the catalog empty does not work — `build_app` re-seeds
the builtins whenever it finds `providers` empty. Seed first, then rewrite, keeping the catalog
non-empty so the re-seed never fires.

`_DismissReadinessModalOnShow` is load-bearing here in a way it is not in the e2e tier: if the live
server degrades mid-test, production opens a blocking `QMessageBox.critical` via `.exec()`, and with
no `pytest-timeout` configured that hangs the whole run with no output. A pre-armed one-shot timer is
not a substitute — the readiness tick stays pending until something pumps the event loop, so a fixed
delay can fire before the modal exists. Only a Show-event filter catches it reliably.

- [ ] **Step 4: Add the shared smoke driver**

This is the body Tasks 4 and 5 share. It lives here and nowhere else.

```python
@pytest.fixture
def live_client_factory() -> Generator[Callable[[str], OpenAICompatibleClient]]:
    """Build a real ``OpenAICompatibleClient`` against a real local base URL.

    Every collaborator is the production one -- ``make_system_clock``, a real ``EventBus``, a
    real inference-activity store, a real ``httpx.Client``. No fake and no wire stub stands in
    for the provider here; that is the entire point of this tier (ADR-0011).

    ``api_key_raw`` is ``""``: Ollama and LM Studio are keyless, and the field holds only a bare
    env-var NAME when it holds anything at all -- never a key value, and never an invented
    placeholder.
    """
    # build a shared httpx.Client, yield a factory, close every built client then the http client


@pytest.fixture
def live_smoke(
    qtbot: QtBot,
    live_client_factory: Callable[[str], OpenAICompatibleClient],
    build_live_app: Callable[[str, str], LiveAppRig],
    shutdown_handle: Callable[[AppHandle], None],
    tiny_task_file: Path,
) -> Callable[[str], LiveSmokeOutcome]:
    """Probe, discover, and run one tiny real benchmark against ``base_url``.

    The shared body of AC-1 and AC-2. It lives in this conftest rather than in one provider
    module because the tier's modules cannot import from each other (no ``__init__.py`` under
    ``tests/``) and must not restate it -- a fixture is resolved by name, so it needs no import
    at all.

    Skips (never fails) when the server is unreachable within the bounded timeout, or when it is
    reachable but exposes no model: both are "this machine is not set up for the live tier",
    which ADR-0011 requires to be a clean skip. A skipped result is honest evidence, not a pass.

    Discovery and the run are one operation rather than two tests because the model to run
    against is whatever the operator happens to have pulled -- it must be discovered at runtime
    and fed straight into the run. Hardcoding a model name would fail on every machine but one.
    """

    def _run(base_url: str) -> LiveSmokeOutcome:
        if not server_reachable(base_url):
            pytest.skip(
                f"no live server reachable at {base_url} within {REACHABILITY_TIMEOUT_S}s"
            )
        client = live_client_factory(base_url)
        health = client.probe_health()
        models = client.list_models()
        if not models:
            pytest.skip(_NO_MODELS_GUIDANCE[base_url])

        model_name = str(models[0])
        rig = build_live_app(base_url, model_name)
        try:
            rig.handle.window.show()
            qtbot.waitUntil(
                lambda: _health_dot_label(rig) != _CHECKING_HEALTH_LABEL,
                timeout=READINESS_TIMEOUT_MS,
            )
            run_id = rig.handle.flow.start(
                RunStartRequest(
                    run_mode=RunMode.TASKS,
                    test_models=(
                        ModelDescriptor(provider_id=rig.provider_id, model_name=model_name),
                    ),
                    task_paths=(str(tiny_task_file),),
                )
            )
            qtbot.waitUntil(lambda: not rig.handle.flow.is_running(), timeout=RUN_TIMEOUT_MS)
            runs_store, results_store = _stores(rig)
            rows = results_store.list_results(run_id)
            return LiveSmokeOutcome(
                reachable=health.reachable,
                discovered_any=True,
                run_status=runs_store.get_run(run_id).status,
                first_result_status=rows[0].status if rows else ResultStatus.FAILED,
            )
        finally:
            shutdown_handle(rig.handle)

    return _run


@pytest.fixture
def expected_live_smoke_outcome() -> LiveSmokeOutcome:
    """The outcome a healthy live provider must produce: reachable, at least one model, and a
    run that reached ``COMPLETED`` with a completed first result row.

    Handed over as a fixture so a provider test module never imports ``LiveSmokeOutcome``.
    """
    return LiveSmokeOutcome(
        reachable=True,
        discovered_any=True,
        run_status=RunStatus.COMPLETED,
        first_result_status=ResultStatus.COMPLETED,
    )
```

**Why `RunMode.TASKS` and not `GRADED`.** `benchmark_pipeline`'s phase grouping runs only
`INITIALIZATION` and `INFERENCE` for any non-`GRADED` mode, so a `TASKS` run needs no judge model and
no embedding model, and its rows land directly on `ResultStatus.COMPLETED`. That is the smallest real
run this app can perform — exactly one live inference call. **Verify this against the real
`benchmark_pipeline/_internal/grouping.py` and `units.py` before relying on it.**

Also add the two module-local helpers `_health_dot_label(rig)` and `_stores(rig)`, copied from
`tests/e2e/test_full_run_from_ui_smoke.py` (the health dot is rebuilt on every render, so it must be
re-located on each poll), plus `_CHECKING_HEALTH_LABEL`.

- [ ] **Step 5: Verify the directory collects and skips cleanly**

```bash
uv run pytest tests/live_local -m live_local -q
```

Expected: `no tests ran` (no test modules yet) — but **no collection error**.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix tests/live_local && uv run ruff format tests/live_local
git add tests/live_local/conftest.py
git commit -m "test(story-086): add the live-tier opt-in gate, app rig, and smoke driver"
```

______________________________________________________________________

## Task 4: The Ollama live smoke test (AC-1)

**Files:**

- Create: `tests/live_local/test_ollama_live_smoke.py`

**Interfaces:**

- Consumes: the `live_smoke`, `ollama_base_url`, and `expected_live_smoke_outcome` fixtures from Task 3.
- Produces: nothing Task 5 imports — Task 5 requests the same fixtures independently.

**This module must contain no `import` from `conftest`, and no probe/discover/run logic.** All of
that lives in the `live_smoke` fixture. If you find yourself writing more than about fifteen lines of
body here, something belongs in the conftest instead.

- [ ] **Step 1: Write the test**

```python
"""STORY-086 live smoke: a real local Ollama server.

Runs only under ``OLLAMA_BENCH_LIVE_LOCAL_TESTS=1`` with a reachable server -- both gates live
in ``conftest.py``. Authority for this tier existing: ADR-0011 Decision outcome §1.

The probe, the discovery and the tiny run share one driver with the LM Studio module; it is the
``live_smoke`` fixture. Fixtures are resolved by name, so nothing here imports anything from the
sibling conftest -- ``from conftest import ...`` silently binds whichever conftest pytest
imported last.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from conftest import LiveSmokeOutcome  # only for annotations; never imported at runtime


@pytest.mark.live_local
@pytest.mark.slow
@pytest.mark.allow_qt_warnings
def test_ollama_probe_discover_and_tiny_run(
    live_smoke: "Callable[[str], LiveSmokeOutcome]",
    ollama_base_url: str,
    expected_live_smoke_outcome: "LiveSmokeOutcome",
) -> None:
    """Proves: STORY-086-AC-1

    Against a real local Ollama: the health probe reports the server reachable, discovery
    returns at least one model, and one tiny real benchmark run reaches ``COMPLETED`` with a
    completed result row.
    """
    # Arrange / Act
    outcome = live_smoke(ollama_base_url)

    # Assert
    assert outcome == expected_live_smoke_outcome
```

> **Note on the `TYPE_CHECKING` import.** `mypy --strict` does not cover `tests/live_local/`, and a
> `TYPE_CHECKING`-only import is never executed, so it cannot trip the `sys.modules["conftest"]`
> collision. If ruff objects to it, or if it reads as more confusing than it is worth, drop the
> annotations to a plain `object`/`Callable[[str], object]` and say so in your report — the
> assertion is what matters, not the annotation's precision. Do **not** promote it to a runtime import.

- [ ] **Step 2: Verify it skips with the opt-in unset**

```bash
uv run pytest tests/live_local -m live_local -q
```

Expected: `1 skipped` with reason `OLLAMA_BENCH_LIVE_LOCAL_TESTS is not set to '1'`.

- [ ] **Step 3: Verify it is deselected from a bare run**

```bash
uv run pytest tests/live_local -q
```

Expected: `no tests ran` / `1 deselected`.

- [ ] **Step 4: Run it for real** (a local Ollama with at least one model pulled is running on this machine)

```bash
OLLAMA_BENCH_LIVE_LOCAL_TESTS=1 uv run pytest tests/live_local/test_ollama_live_smoke.py -m live_local -q
```

Expected: `1 passed`. If Ollama were not running, expected instead: `1 skipped` with the
`no live server reachable at http://localhost:11434/v1` reason, returning in about two seconds, not hanging.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix tests/live_local && uv run ruff format tests/live_local
git add tests/live_local/test_ollama_live_smoke.py
git commit -m "test(story-086): live Ollama probe, discovery, and tiny run smoke"
```

______________________________________________________________________

## Task 5: The LM Studio live smoke test (AC-2)

**Files:**

- Create: `tests/live_local/test_lmstudio_live_smoke.py`

**Interfaces:**

- Consumes: the same three fixtures as Task 4, requested independently.

Structurally identical to Task 4's module — but that is now four lines of body, not a restated test.
The substitutions:

| Task 4                                        | Task 5                                      |
| --------------------------------------------- | ------------------------------------------- |
| `ollama_base_url` fixture                     | `lmstudio_base_url` fixture                 |
| `test_ollama_probe_discover_and_tiny_run`     | `test_lmstudio_probe_discover_and_tiny_run` |
| `"""Proves: STORY-086-AC-1`                   | `"""Proves: STORY-086-AC-2`                 |
| module docstring "a real local Ollama server" | "a real local LM Studio server"             |

- [ ] **Step 1: Create the module** with those substitutions applied.

- [ ] **Step 2: Verify skip and deselection**

```bash
uv run pytest tests/live_local -m live_local -q          # expect: 2 skipped
uv run pytest tests/live_local -q                        # expect: 2 deselected
```

- [ ] **Step 3: Run it for real** (LM Studio is serving on port 1234 on this machine)

```bash
OLLAMA_BENCH_LIVE_LOCAL_TESTS=1 uv run pytest tests/live_local/test_lmstudio_live_smoke.py -m live_local -q
```

Expected: `1 passed`, or `1 skipped` within ~2s if its server is off.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix tests/live_local && uv run ruff format tests/live_local
git add tests/live_local/test_lmstudio_live_smoke.py
git commit -m "test(story-086): live LM Studio probe, discovery, and tiny run smoke"
```

______________________________________________________________________

## Task 6: The always-run gating test (AC-3)

**Files:**

- Create: `tests/unit/test_live_tier_gating.py`

**Rationale for the placement.** AC-3 claims the tier skips cleanly on a machine with no opt-in and
no server. That claim is about machines like the CI runners — so its proving test must run on them. A
test living inside the tier would itself be skipped there, proving nothing. This module therefore
lives in `tests/unit/`, carries **no** `live_local` marker, and loads the conftest's helpers by file
location under a **unique** module name (there are no `__init__.py` files under `tests/`, so a normal
import is not available, and the bare name `conftest` would collide with every other conftest in
`sys.modules`).

- [ ] **Step 1: Write the test**

```python
"""The live tier's opt-in gate and reachability bound (STORY-086).

Deliberately in ``tests/unit/`` rather than in ``tests/live_local/``: this criterion is about
what happens on a machine with no opt-in and no server -- exactly the machines that never run
the live tier -- so a proving test inside that tier would itself be skipped and prove nothing.

Loads the tier's conftest by file location because ``tests/`` has no ``__init__.py`` files and
therefore no importable package path. The loader registers it under the unique name
``live_local_conftest``, never the bare ``conftest`` that pytest itself uses -- that name is
shared by every conftest in the run and resolves to whichever was imported last (ADR-0011).
"""

import importlib.util
import socket
import time
import types
from pathlib import Path
from typing import Final

import pytest

_CONFTEST_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "live_local" / "conftest.py"
)
_CLOSED_PORT_URL: Final[str] = "http://127.0.0.1:1/v1"
"""Port 1 is privileged and never bound by this project's tooling, so a connect there is
refused immediately -- the deterministic stand-in for 'no server installed'."""

_REACHABILITY_BOUND_S: Final[float] = 2.0
_BOUND_TOLERANCE_S: Final[float] = 3.0


def _load_live_local_conftest() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("live_local_conftest", _CONFTEST_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_live_tests_skip_when_opt_in_unset_or_server_absent() -> None:
    """Proves: STORY-086-AC-3

    With the opt-in variable unset (or set to anything but ``1``) the tier's gate reports
    disabled, and an unreachable target resolves to "not reachable" within the bounded
    connection timeout rather than raising or hanging -- so every test in
    ``tests/live_local/`` skips and no live server is contacted.
    """
    # Arrange
    conftest = _load_live_local_conftest()

    # Act
    opt_in_unset = conftest.live_local_opt_in_enabled({})
    opt_in_wrong_value = conftest.live_local_opt_in_enabled({conftest.OPT_IN_ENV_VAR: "0"})
    opt_in_enabled = conftest.live_local_opt_in_enabled(
        {conftest.OPT_IN_ENV_VAR: conftest.OPT_IN_ENABLED_VALUE}
    )
    started = time.monotonic()
    reachable = conftest.server_reachable(_CLOSED_PORT_URL, timeout_s=_REACHABILITY_BOUND_S)
    elapsed = time.monotonic() - started

    # Assert
    assert (opt_in_unset, opt_in_wrong_value, opt_in_enabled, reachable, elapsed < _BOUND_TOLERANCE_S) == (
        False,
        False,
        True,
        False,
        True,
    ), f"gate/reachability contract broken; reachability took {elapsed:.1f}s"
```

Note: `_load_live_local_conftest` executes the conftest module at import time, which means every
import at the top of that file must resolve on a machine with no server — they are all pure module
imports, so they do. If executing it turns out to have a side effect, say so in your report rather
than working around it.

- [ ] **Step 2: Run it**

```bash
uv run pytest tests/unit/test_live_tier_gating.py -q
```

Expected: `1 passed`.

- [ ] **Step 3: Falsify it — negative control. Do NOT delete the assertion; break the condition.**

Temporarily change `_CLOSED_PORT_URL` to `"http://localhost:11434/v1"` (Ollama is running on this
machine) and confirm the test **fails** on the reachability element. Revert.

Expected: FAIL, then PASS after reverting. If it passes both ways the test proves nothing. Paste both
outputs into your report.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix tests/unit/test_live_tier_gating.py && uv run ruff format tests/unit/test_live_tier_gating.py
git add tests/unit/test_live_tier_gating.py
git commit -m "test(story-086): prove the live tier's opt-in gate and bounded reachability check"
```

______________________________________________________________________

## Task 7: The `just` recipe and the workflow verification

**Files:**

- Modify: `justfile` (after the `test-e2e` recipe)
- Modify: `.github/workflows/pr-gate.yml` (coverage step) and `.github/workflows/release.yml`
  (`uv run pytest -q` step) — comments only

**Why comments and not `-m` in the workflows.** `addopts` already carries `-m "not live_local"`, and
every bare invocation inherits it — the workflows are functionally covered with no edit. Adding an
explicit `-m` to each step would put the marker expression in three places, all of which STORY-094
would then have to keep in sync, and pytest honours only the last `-m` anyway. So: a comment naming
why no flag is needed, plus recorded verification evidence, satisfies the story's "updated and
verified" without creating the sync hazard.

- [ ] **Step 1: Add the `justfile` recipe** (match the file's existing recipe style and indentation)

```make
# The opt-in live tier alone (ADR-0011). Requires a local Ollama and/or LM Studio; each
# provider's test skips cleanly within a bounded connection timeout when its server is
# absent. Never part of `just check` or CI -- `pyproject.toml`'s addopts deselects it.
# The command-line -m overrides that addopts entry.
test-live:
    OLLAMA_BENCH_LIVE_LOCAL_TESTS=1 uv run pytest tests/live_local -m live_local -q
```

- [ ] **Step 2: Add the workflow comments**

In `.github/workflows/pr-gate.yml`, above the coverage step:

```yaml
      # This step names no paths, so it collects `src` + `tests` including
      # `tests/live_local/`. No `-m` flag is needed: `pyproject.toml`'s addopts already
      # carries `-m "not live_local"`, which every bare pytest invocation inherits
      # (ADR-0011, STORY-086). CI stays fully offline.
```

In `.github/workflows/release.yml`, above the `uv run pytest -q` step:

```yaml
      # Bare invocation: `pyproject.toml`'s addopts `-m "not live_local"` keeps ADR-0011's
      # opt-in live tier out of the release quality gate (STORY-086).
```

- [ ] **Step 3: Verify both CI commands select no live test, locally, by running them verbatim**

```bash
uv run pytest --collect-only -q --cov=ollama_llm_bench --cov-report=term-missing 2>&1 | grep -c "live_local/" || echo "0 live_local nodes selected"
uv run pytest --collect-only -q 2>&1 | grep -c "live_local/" || echo "0 live_local nodes selected"
uv run pytest --collect-only -q 2>&1 | tail -2
```

Expected: zero `live_local/` node IDs in both, and the tail line reports a deselected count of
exactly 2 (the Ollama and LM Studio tests). Paste that tail into your report — that is the "verified"
half of the Definition of Done.

- [ ] **Step 4: Verify the YAML still lints**

```bash
uv run yamllint .github
```

Expected: no output. (If `yamllint` is not part of this repo's tooling, say so and skip — do not add it.)

- [ ] **Step 5: Verify `just test-live` runs**

```bash
just test-live
```

Expected on this machine (both servers up): `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add justfile .github/workflows/pr-gate.yml .github/workflows/release.yml
git commit -m "chore(story-086): add just test-live and document the CI live-tier exclusion"
```

______________________________________________________________________

## Task 8: Story correction, traceability, and the full gate

**Files:**

- Modify: `docs/stories/story-086-opt-in-live-smoke-tier.md`

- Regenerate: `traceability.yaml`

- [ ] **Step 1: Correct the story's Test plan line for AC-3**

Replace:

```markdown
- STORY-086-AC-3 — live (`live_local` marker), `tests/live_local/test_live_tier_gating.py`,
  `test_live_tests_skip_when_opt_in_unset_or_server_absent`.
```

with:

```markdown
- STORY-086-AC-3 — unit, `tests/unit/test_live_tier_gating.py`,
  `test_live_tests_skip_when_opt_in_unset_or_server_absent` — deliberately **outside** the
  tier and unmarked, so it runs in the offline gate. A criterion asserting "these tests skip
  on a machine with no server" must be proven on machines with no server; a proving test
  inside the tier would itself be skipped there.
```

Also add two lines to **In scope** recording the two mechanics the story text does not yet mention:

```markdown
- `scripts/_traceability_lib.py` passes `-m ""` when collecting, so `just trace` still sees
  the deselected live tests and `just trace-check` does not report their acceptance criteria
  as unproven.
- The two provider modules share their probe/discover/run body through a `live_smoke` fixture
  in `tests/live_local/conftest.py`. They cannot share it by import: pytest registers a plain
  `conftest.py` under the bare name `conftest`, so with several conftests collected
  `from conftest import ...` silently returns whichever was imported last.
```

- [ ] **Step 2: Regenerate and validate traceability**

```bash
uv run python scripts/trace.py
uv run python scripts/validate_traceability.py
```

Expected: the collected-test count rises by 4 (three new tests + the arch test), and
`validate_traceability.py` reports zero gaps. Confirm `traceability.yaml`'s `STORY-086` entry lists a
test under each of AC-1..AC-4.

- [ ] **Step 3: Run the full gate — once, alone, redirected to a file**

Never run two full-suite verifications concurrently, and never pipe a long run through `tail` (it
buffers until exit; a finished run stayed invisible for 11 hours once). Redirect and poll:

```bash
just check > /tmp/story-086-gate.log 2>&1; echo "exit=$?"; tail -40 /tmp/story-086-gate.log
```

Expected: exit 0. Baseline caveats, both pre-existing — diff against the baseline rather than
treating either as new: `just check` does not pin `QT_QPA_PLATFORM`, so two focus-ring e2e tests fail
natively and pass offscreen; and the gate has an intermittent native crash flake under
`pytest-randomly`. The gate normally takes far longer than the AGENTS.md "~2 minutes" figure on this
machine — a recent full run took 30 minutes. Do not kill it before ~50 minutes.

- [ ] **Step 4: Verify the tier is genuinely absent from the gate**

```bash
grep -c "live_local/" /tmp/story-086-gate.log || echo "0 -- tier absent from the gate, as required"
```

Expected: `0`.

- [ ] **Step 5: Run the live tier for real, both providers**

```bash
just test-live > /tmp/story-086-live.log 2>&1; echo "exit=$?"; tail -20 /tmp/story-086-live.log
```

Expected on this machine: `2 passed`. Paste the result into the closing report — a skipped result
would be honest evidence, not a pass.

- [ ] **Step 6: Flip the story to `done` and re-validate**

Set `status: done` in the story front-matter, tick the Definition-of-done boxes with the evidence
gathered above, then:

```bash
uv run python scripts/trace.py
uv run python scripts/validate_traceability.py
```

Expected: zero gaps. (This is the run that would have failed without Task 2.)

- [ ] **Step 7: Check the Unblocks list**

STORY-093 depends on STORY-076..089, 091, 092, and 114 — 17 entries. Check each one's `status:`; flip
STORY-093 `draft` → `ready` **only if every one is now `done`**, otherwise leave it and name the
outstanding dependencies in the closing report. (As of STORY-091's closeout, six were outstanding,
one of them `superseded` and therefore never reachable — expect this to stay `draft`.)

- [ ] **Step 8: Commit**

```bash
uv run mdformat docs/stories docs/superpowers/plans
git add docs/stories/story-086-opt-in-live-smoke-tier.md traceability.yaml docs/superpowers/plans
git commit -m "docs(story-086): close the story, correct the AC-3 test home, regenerate traceability"
```

______________________________________________________________________

## Verification summary

| Claim                                | How it is verified                                                                                                                             |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| AC-1 Ollama probe/discover/run       | `just test-live` against the running Ollama → `test_ollama_probe_discover_and_tiny_run` passes                                                 |
| AC-2 LM Studio probe/discover/run    | same command against the running LM Studio → `test_lmstudio_probe_discover_and_tiny_run` passes                                                |
| AC-3 clean skip, no server contacted | `uv run pytest tests/unit/test_live_tier_gating.py` passes in the offline gate; falsified in Task 6 Step 3                                     |
| AC-4 deselected from every bare run  | `uv run pytest tests/architecture/test_live_tier_excluded_from_gate.py` passes; plus the verbatim CI-command collection check in Task 7 Step 3 |
| Gate stays green                     | `just check` exit 0, diffed against baseline                                                                                                   |
| Traceability intact                  | `just trace` then `just trace-check` → zero gaps with `status: done`                                                                           |
| No hang on an absent server          | Task 6's bounded-timeout assertion; plus the tier's skip path                                                                                  |

## Things that go wrong here

- **A second `-m` in `addopts`.** pytest silently honours only the last one. The Task 1 arch test
  asserts there is exactly one, which is the guard STORY-094 will trip over rather than discover in
  production.
- **`from conftest import ...`.** Proven in this repo to bind the wrong module silently. Fixtures, always.
- **A blocking modal.** A live server that degrades mid-test opens `QMessageBox.critical` via
  `.exec()`. Without the Show-event dismisser installed, the run hangs with no output and no
  `pytest-timeout` to save it.
- **A skipped `shutdown_handle`.** `build_app` starts a non-daemon dispatcher thread; the pytest
  process then hangs at interpreter exit *after* printing its summary, which reads like success.
  Register it so it runs even if fixture setup raises after the app is built.
- **Module-level skip or `collect_ignore`.** Either removes the node IDs and breaks traceability. Use
  the autouse fixture.
- **Asserting a hardcoded model name.** The operator's machine has whatever they pulled. Discover the
  model at runtime and feed it into the run — that is why discovery and the run are one operation.
