# STORY-088 — Test Debt Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three unrelated test debts — a stale contract-suite docstring, the never-implemented
≤ 90-day run-log age rule, and a `compose_filename` test fake copy-pasted into three files.

**Architecture:** Three independent slices, one per acceptance criterion, sharing no code. AC-1 is a
docstring correction in `tests/contract/` plus a guard test that makes the rot impossible to repeat.
AC-2 adds real production behaviour to `backend/log_file_writer/`: the age rule joins the existing
count rule inside `_internal/run_log_cleanup.py`, reading "now" through the injected `Clock` Protocol
(never `datetime.now()`), and surfaces through the existing public `cleanup_run_logs` in `api.py`.
AC-3 creates the first `conftest.py` under `src/ollama_llm_bench/ui/resume_benchmark/tests/` and
threads a single shared fake through the three test modules that each define their own copy today.

**Tech Stack:** Python 3.13, pytest, pytest-qt, icontract, ruff, mypy --strict, import-linter, uv,
just.

## Global Constraints

- `backend/log_file_writer/` is Qt-free and asyncio-free — it imports no PySide6 and no `asyncio`.
- Backend time is read **only** through the injected `Clock` Protocol
  (`ollama_llm_bench.backend.infra.protocols.Clock`). Never `datetime.now()` / `time.time()` in the
  age rule; `freezegun` is not used here because a clock *can* be injected.
- Every public function in an `api.py` carries at least one `@icontract.require` or
  `@icontract.ensure`, and contracts guard **programmer invariants only, never user input**.
- Function parameter hard maximum is **4**. `cleanup_run_logs` lands at exactly 4 — do not add a
  fifth.
- Every test function is fully annotated, returns `-> None`, follows Arrange-Act-Assert, asserts one
  logical concept, and contains no `if` and no `for` in its body (seeding loops go in a module-level
  helper).
- Every test proving an acceptance criterion declares it on the **first line of its docstring** in
  the exact form `"""Proves: STORY-088-AC-N`.
- Every `# noqa` / `# type: ignore` carries its specific code and a justification. Bare ones are
  rejected by `RUF100` / `warn_unused_ignores`.
- Absolute imports only. Annotation-only imports go under `if TYPE_CHECKING:` (ruff `TC` rules).
- Retention numbers come from the spec, not from the current constants: **≤ 200 files, ≤ 90 days**
  (`12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` §5 and §7).
- Never `git commit --no-verify`, never `git push --force`. Stay on
  `feature/spec-v3-implementation`; do not create a sub-branch.

## Spec facts this plan is built on

Read directly from `docs/v3_specification/`, not from the story's paraphrase:

| Clause                                                | What it fixes                                                                                                                                                                                                                                   |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` §5        | Per-run logs: "At most 200 files; none older than 90 days; no orphan (a log whose run was deleted)", pruned "At startup, after the recovery sweep. The age rule and the count rule are **both applied; whichever removes more files governs**." |
| `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` §7        | Summary row: "≤ 200 files, ≤ 90 days, no orphans", "Oldest-first / age-based prune at startup", enforced by "Startup cleanup; integration test".                                                                                                |
| `16_Engineering_Standards/07_TESTING_STANDARD.md` §6a | One shared contract suite per swap-point Protocol, parametrized over real + fake, both legs passing in the gate.                                                                                                                                |
| `16_Engineering_Standards/07_TESTING_STANDARD.md` §7a | The `LLMClient` real leg runs against the `pytest-httpserver` wire stub on `127.0.0.1` via the SDK base-URL override — never a live model. AC-1 must not change this.                                                                           |

### Decisions taken while planning (and why)

1. **"Whichever removes more files governs" is implemented as the union of the two deletion sets,
   which is provably identical to `max()` of the two.** Both rules delete a *prefix* of the same
   ascending-timestamp-sorted list — the count rule deletes the oldest `len - 200`, the age rule
   deletes every entry with `unix_ts < cutoff`, which is also a prefix. The union of two prefixes of
   the same list is the longer prefix. So `delete_count = max(excess_by_count, expired_count)`
   satisfies both §5's wording and AC-2's "every file that violated either rule removed and every
   file that violated neither retained". The literal alternative reading — "compute both sets, apply
   only the larger, discard the smaller" — is wrong: it would leave >90-day files alive whenever the
   count rule happened to delete more, contradicting §5's own limit column.
1. **Age is measured from the `unix_ts` encoded in the filename, not from the run's finish time.**
   §5 and §7 (the clauses this story cites) speak of the *file's* age — "none older than 90 days".
   §3.2 phrases it as "a run log whose run finished more than 90 days ago", which would require the
   runs store — precisely the dependency this module deliberately does not have, and precisely what
   STORY-115 owns. The filename timestamp is the run's start time, so a run that started 91 days ago
   and finished 89 days ago would be pruned a day early. Runs last hours, so the divergence is
   immaterial; it is recorded here rather than buried.
1. **The comparison is strict (`unix_ts < cutoff`).** A file exactly 90 days old is retained; "none
   *older than* 90 days" is the limit.
1. **`Clock.now_utc()` returns an ISO-8601 string, not epoch seconds.** The Protocol
   (`backend/infra/protocols.py:27`) offers only `now_utc() -> Iso8601Utc` and `monotonic_ms()`.
   Widening that Protocol would touch its real implementation plus eleven `FakeClock` doubles — an
   architecturally significant change well outside an `M` story. Instead the age rule parses the ISO
   string with `datetime.fromisoformat` and takes `.timestamp()`. A naive (tz-less) string is
   defensively stamped `UTC` before conversion, because `.timestamp()` on a naive datetime silently
   assumes *local* time and would shift the cutoff by hours on a developer machine.
1. **AC-3 threads a real pytest fixture through all three files**, rather than merely moving the
   class into `conftest.py` and importing it. AC-3's wording is explicit ("each obtain that fake from
   the single shared fixture"), and a spec-conformance reviewer reads the AC. The cost is ~30
   mechanical edits in `test_controller_menu_actions.py`; none of them changes behaviour, because the
   fake is stateless and the fixture is function-scoped, so each test still gets exactly one instance.

### Verified starting state

- `tests/contract/test_llm_client_contract.py` already runs all six legs: `_make_gemini_real_client`
  (line 287), `_make_gemini_fake_client` (line 322), `_build_llm_client` dispatch (lines 366–368),
  `llm_client` fixture params (lines 371–380). Only the docstring is wrong (line 19 lists four legs;
  lines 21–27 call `embed`/`list_models` "OpenAI-only" although `embedding_capable_llm_client` at
  line 388 covers `openai_real`, `openai_fake`, `gemini_real`, `gemini_fake`).
- `cleanup_run_logs` is called from **no production code** — only from
  `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py:33`. Wiring it into
  startup is STORY-115's job, not this story's.
- The three resume fakes are textually different but behaviourally identical: `test_actions.py:528`
  delegates to a `_sanitize` helper that truncates to 80 characters after stripping;
  `test_controller.py:187` and `test_controller_menu_actions.py:214` inline the same steps. All three
  use the same `_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]")`.
- `src/ollama_llm_bench/ui/resume_benchmark/tests/` has `__init__.py` but **no** `conftest.py`.
- Removing the fakes makes `_SANITIZE_RE` and `import re` dead in all three files — they have no
  other use (`test_actions.py:5,45`; `test_controller.py:4,36`; `test_controller_menu_actions.py:14,48`).

## File Structure

**Created**

| Path                                                         | Responsibility                                                                                          |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `tests/integration/test_run_log_retention.py`                | The AC-2 proving test: both rules applied together against a `tmp_path` directory and a pinned `Clock`. |
| `src/ollama_llm_bench/ui/resume_benchmark/tests/conftest.py` | The single `FakeExportFilenameHelper` definition plus the `export_filename_helper` fixture.             |

**Modified**

| Path                                                                             | Change                                                                                                               |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `tests/contract/test_llm_client_contract.py`                                     | Corrected module docstring; a `_LLM_CLIENT_LEGS` constant feeding the fixture; the AC-1 guard test.                  |
| `src/ollama_llm_bench/backend/log_file_writer/_internal/run_log_cleanup.py`      | Shared scan/delete helpers; the cutoff computation; `cleanup_run_logs_by_count_and_age`; corrected module docstring. |
| `src/ollama_llm_bench/backend/log_file_writer/api.py`                            | `cleanup_run_logs` gains `clock` and `max_age_days`, a second contract, and a corrected docstring.                   |
| `src/ollama_llm_bench/backend/log_file_writer/tests/conftest.py`                 | Adds `FakeClock` and the `fake_clock` fixture.                                                                       |
| `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py`     | Existing call site passes the clock; adds age-rule unit tests.                                                       |
| `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py`                 | Fake and `_sanitize` deleted; helper takes `export_filenames`; AC-3 test added.                                      |
| `src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller.py`              | Fake deleted; four tests consume the fixture.                                                                        |
| `src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller_menu_actions.py` | Fake deleted; `_make_controller` takes `export_filenames`; 14 tests consume the fixture.                             |
| `docs/stories/story-088-test-debt-closure.md`                                    | `status: ready` → `done`.                                                                                            |
| `docs/stories/story-115-run-log-retention-orphan-rule-and-startup-wiring.md`     | `status: draft` → `ready`.                                                                                           |
| `traceability.yaml`                                                              | Regenerated by `just trace`.                                                                                         |

______________________________________________________________________

## Task 1: AC-1 — correct the contract-suite docstring and guard it

**Files:**

- Modify: `tests/contract/test_llm_client_contract.py:1-37` (module docstring), `:371-380`
  (fixture params)
- Test: `tests/contract/test_llm_client_contract.py` (new test appended after the fixtures)

**Interfaces:**

- Consumes: nothing from other tasks.
- Produces: `_LLM_CLIENT_LEGS: Final[tuple[str, ...]]` — the single source of the six leg names, used
  both by the `llm_client` fixture's `params` and by the guard test. No later task depends on it.

**Why a constant rather than reading the fixture's params at runtime:** pytest stores params on an
untyped `_pytestfixturefunction` attribute, which `mypy --strict` rejects without a `type: ignore`.
Feeding `params=` from a module-level constant makes drift impossible by construction and keeps the
module fully typed.

- [ ] **Step 1: Add the constant and point the fixture at it**

In `tests/contract/test_llm_client_contract.py`, add `Final` to the `typing` imports and `re` to the
stdlib imports (check whether they are already present before adding a duplicate), then insert the
constant just above the `llm_client` fixture (currently line 371):

```python
_LLM_CLIENT_LEGS: Final[tuple[str, ...]] = (
    "openai_real",
    "openai_fake",
    "anthropic_real",
    "anthropic_fake",
    "gemini_real",
    "gemini_fake",
)
```

Replace the fixture's inline params list (lines 371–380) with:

```python
@pytest.fixture(params=list(_LLM_CLIENT_LEGS))
def llm_client(request: pytest.FixtureRequest, httpserver: HTTPServer) -> LLMClient:
    """Parametrized ``LLMClient`` under test: each real wire-stub-backed
    adapter and its ``testing.py`` fake — every leg runs every test below."""
    param: str = request.param
    return _build_llm_client(param, httpserver)
```

- [ ] **Step 2: Write the failing guard test**

Append after the `embedding_capable_llm_client` fixture:

```python
def test_module_docstring_lists_every_registered_leg() -> None:
    """Proves: STORY-088-AC-1

    The module docstring names exactly the legs the ``llm_client`` fixture is
    parametrized over — no documented leg missing from the fixture, no fixture
    leg missing from the docstring — so the docstring cannot silently rot the
    next time a provider adapter is added.
    """
    # Arrange
    docstring = __doc__ or ""
    # Act
    documented = set(re.findall(r"``([a-z]+_(?:real|fake))``", docstring))
    # Assert
    assert documented == set(_LLM_CLIENT_LEGS)
```

- [ ] **Step 3: Run it and confirm it fails for the right reason**

```bash
uv run pytest tests/contract/test_llm_client_contract.py::test_module_docstring_lists_every_registered_leg -v
```

Expected: **FAIL**, an `AssertionError` whose diff shows the docstring set missing `gemini_real` and
`gemini_fake` (the current docstring writes the four names inside a `params=[...]` literal with plain
double quotes, so the double-backtick regex finds none of them and `documented` is empty). Either
shape of failure is correct — what matters is that it fails before the docstring is fixed.

- [ ] **Step 4: Replace the module docstring (lines 1–37)**

```python
"""The shared ``LLMClient`` contract-test suite (§6a) — runs against both real
provider adapters (wire-stub-backed, §7a) and their ``testing.py`` fakes,
proving each fake is a faithful stand-in for its real adapter.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md``
§6a; ``docs/stories/story-018-openai-compatible-provider-adapter.md``,
``docs/stories/story-019-anthropic-provider-adapter.md`` and
``docs/stories/story-020-gemini-provider-adapter.md`` Definition of Done
("The ``LLMClient`` shared contract-test suite (§6a) runs against both the real
adapter (wire stub, §7a) and the module's ``testing.py`` fake, and both legs
pass.").

This is the **first** contract suite in the codebase — STORY-018 shipped the
first concrete ``LLMClient`` provider adapter alongside its ``testing.py``
fake; STORY-019 and STORY-020 added the Anthropic and Gemini legs onto the same
suite. Every assertion below is a genuine ``LLMClient`` Protocol-level
behavioural contract (``08_Cross_Cutting/08-E_interfaces_contracts.md`` §10:
return shapes, the never-raises rules for ``probe_health``/``test_inference``)
— never a provider-specific wire detail.

The ``llm_client`` fixture is parametrized over six legs: ``openai_real``,
``openai_fake``, ``anthropic_real``, ``anthropic_fake``, ``gemini_real`` and
``gemini_fake``. Every leg must pass in the pull-request gate.
``test_module_docstring_lists_every_registered_leg`` (STORY-088-AC-1) asserts
this paragraph and the fixture's registered legs stay in step.

``embed`` and ``list_models`` are asserted on the embedding/discovery-capable
legs only, through the separate ``embedding_capable_llm_client`` fixture —
``openai_real``, ``openai_fake``, ``gemini_real`` and ``gemini_fake``.
Anthropic's ``LLMClient`` deliberately raises immediately from both, which is
per-provider-type behaviour (§6.9), not a Protocol-level contract every
implementation shares; STORY-019's own colocated
``tests/test_probe_and_embed.py`` proves the Anthropic raise-immediately
contract instead.

The real legs reuse the wire-stub fixture patterns already established in
``src/ollama_llm_bench/backend/provider_openai_compatible/tests/conftest.py``,
``src/ollama_llm_bench/backend/provider_anthropic/tests/conftest.py`` and
``src/ollama_llm_bench/backend/provider_gemini/tests/conftest.py``
(``FakeClock``, ``FakeEventBus``, the ``threaded=True`` httpserver override)
rather than duplicating them — this module imports those helpers directly.
Each fake leg constructs the module's own fake from its ``testing.py`` and
configures its canned responses to be shape-comparable with the real leg's
wire-stub responses (non-empty ``text``, a populated embedding vector, etc.).
"""
```

Note: the docstring names all six legs in double backticks and names the four embedding-capable legs
in double backticks too — those four are a subset of the six, so the guard test's set equality still
holds exactly.

- [ ] **Step 5: Run the guard test and confirm it passes**

```bash
uv run pytest tests/contract/test_llm_client_contract.py::test_module_docstring_lists_every_registered_leg -v
```

Expected: **PASS**.

- [ ] **Step 6: Run the whole contract suite — no leg may have been disturbed**

```bash
uv run pytest tests/contract/test_llm_client_contract.py -q
```

Expected: every test passes, and the count is unchanged apart from the one new test. In particular,
`gemini_real` must still hit the `pytest-httpserver` stub on `127.0.0.1` — no network access, per §7a.

- [ ] **Step 7: Lint and typecheck the touched file**

```bash
uv run ruff check tests/contract/test_llm_client_contract.py
uv run ruff format --check tests/contract/test_llm_client_contract.py
uv run mypy --strict tests/contract/test_llm_client_contract.py
```

Expected: all clean. If `re` or `Final` was already imported and you added a duplicate, ruff `F811`
will say so here.

- [ ] **Step 8: Commit**

```bash
git add tests/contract/test_llm_client_contract.py
git commit -m "test(story-088): document all six LLMClient contract legs and guard the docstring"
```

______________________________________________________________________

## Task 2: AC-2 (part 1) — the age rule inside `_internal/run_log_cleanup.py`

**Files:**

- Modify: `src/ollama_llm_bench/backend/log_file_writer/_internal/run_log_cleanup.py` (whole file)
- Modify: `src/ollama_llm_bench/backend/log_file_writer/tests/conftest.py` (add `FakeClock`)
- Test: `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py`

**Interfaces:**

- Consumes: `Clock` from `ollama_llm_bench.backend.infra.protocols` (`now_utc() -> Iso8601Utc`,
  `monotonic_ms() -> int`); `Iso8601Utc` (a `str` alias) from `ollama_llm_bench.backend.domain`.

- Produces, for Task 3:

  - `DEFAULT_RUN_LOG_KEEP_COUNT: Final[int] = 200` (unchanged)
  - `DEFAULT_RUN_LOG_MAX_AGE_DAYS: Final[int] = 90` (new)
  - `cleanup_run_logs_by_count(*, run_log_dir: Path, keep_count: int) -> int` (unchanged signature
    and behaviour — three existing tests depend on it)
  - `cleanup_run_logs_by_count_and_age(*, run_log_dir: Path, keep_count: int, clock: Clock, max_age_days: int) -> int`

- [ ] **Step 1: Add a pinned `FakeClock` to the colocated conftest**

The existing count-rule test seeds files at `base_ts = 1_700_000_000` (14 Nov 2023). Once the age
rule exists, a real-time clock would judge every one of those files ~2.7 years old and delete all 205
— so the clock the existing test injects must sit near the seeded timestamps, not in the present.

Append to `src/ollama_llm_bench/backend/log_file_writer/tests/conftest.py`:

```python
from datetime import UTC, datetime
from typing import Final

FAKE_NOW_UNIX_TS: Final[int] = 1_700_100_000
"""~28 hours after the ``base_ts`` the count-rule tests seed, so nothing in
those fixtures is age-expired and the count rule is measured in isolation."""


class FakeClock:
    """A ``Clock`` pinned to ``FAKE_NOW_UNIX_TS`` so age assertions are exact."""

    def now_utc(self) -> str:
        return datetime.fromtimestamp(FAKE_NOW_UNIX_TS, UTC).isoformat()

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def fake_clock() -> FakeClock:
    """A ``Clock`` fake pinned just after the run-log timestamps these tests seed."""
    return FakeClock()
```

Keep the existing `from pathlib import Path`, `import pytest`, `FakePlatformDetector` and
`fake_platform_detector` exactly as they are, and place the new stdlib imports in the correct sorted
block at the top of the file.

- [ ] **Step 2: Write the failing age-rule unit tests**

Append to `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py`. Add the
imports it needs at the top of the file — `cleanup_run_logs_by_count_and_age` and
`DEFAULT_RUN_LOG_MAX_AGE_DAYS` from
`ollama_llm_bench.backend.log_file_writer._internal.run_log_cleanup`, and `FakeClock` plus
`FAKE_NOW_UNIX_TS` from `ollama_llm_bench.backend.log_file_writer.tests.conftest` (the file already
imports `FakePlatformDetector` from there, so follow that same import line).

```python
_DAY_SECONDS = 86_400
_AGE_CUTOFF_TS = FAKE_NOW_UNIX_TS - DEFAULT_RUN_LOG_MAX_AGE_DAYS * _DAY_SECONDS


def _seed_run_log(run_log_dir: Path, *, run_id: int, unix_ts: int) -> Path:
    """Create one ``run_<run_id>_<unix_ts>.log`` file and return its path."""
    path = run_log_dir / f"run_{run_id}_{unix_ts}.log"
    path.write_text("x", encoding="utf-8")
    return path


def test_age_rule_deletes_only_files_older_than_the_cutoff(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    """Proves: STORY-088-AC-2

    With the count rule slack (far fewer than 200 files), a run log whose
    encoded timestamp predates the 90-day cutoff is deleted and one that does
    not is retained.
    """
    # Arrange
    run_log_dir = tmp_path / "run"
    run_log_dir.mkdir()
    expired = _seed_run_log(run_log_dir, run_id=1, unix_ts=_AGE_CUTOFF_TS - 1)
    fresh = _seed_run_log(run_log_dir, run_id=2, unix_ts=_AGE_CUTOFF_TS + 1)

    # Act
    deleted_count = cleanup_run_logs_by_count_and_age(
        run_log_dir=run_log_dir,
        keep_count=_KEEP_COUNT,
        clock=fake_clock,
        max_age_days=DEFAULT_RUN_LOG_MAX_AGE_DAYS,
    )

    # Assert
    assert (deleted_count, expired.exists(), fresh.exists()) == (1, False, True)


def test_age_rule_retains_a_file_exactly_at_the_cutoff(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    """Proves: STORY-088-AC-2

    The limit is "none older than 90 days" — a run log whose timestamp lands
    exactly on the cutoff is not yet older than 90 days and survives.
    """
    # Arrange
    run_log_dir = tmp_path / "run"
    run_log_dir.mkdir()
    boundary = _seed_run_log(run_log_dir, run_id=1, unix_ts=_AGE_CUTOFF_TS)

    # Act
    deleted_count = cleanup_run_logs_by_count_and_age(
        run_log_dir=run_log_dir,
        keep_count=_KEEP_COUNT,
        clock=fake_clock,
        max_age_days=DEFAULT_RUN_LOG_MAX_AGE_DAYS,
    )

    # Assert
    assert (deleted_count, boundary.exists()) == (0, True)


def test_age_rule_on_missing_directory_returns_zero(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    """Proves: STORY-088-AC-2

    A ``logs/run/`` directory that does not yet exist is not an error under the
    age rule either — cleanup reports zero deletions.
    """
    # Arrange
    missing_dir = tmp_path / "does" / "not" / "exist"

    # Act
    deleted_count = cleanup_run_logs_by_count_and_age(
        run_log_dir=missing_dir,
        keep_count=_KEEP_COUNT,
        clock=fake_clock,
        max_age_days=DEFAULT_RUN_LOG_MAX_AGE_DAYS,
    )

    # Assert
    assert deleted_count == 0
```

- [ ] **Step 3: Run them and confirm they fail**

```bash
uv run pytest src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py -v
```

Expected: **collection error** — `ImportError: cannot import name 'cleanup_run_logs_by_count_and_age'`.
That is the correct first failure.

- [ ] **Step 4: Rewrite `_internal/run_log_cleanup.py`**

```python
"""Startup run-log retention cleanup (STORY-037-AC-2, STORY-088-AC-2, EC-FL-10, §8.2).

Both retention rules from ``12_Quality_and_NFRs/07_RESOURCE_LIMITS.md`` §5 live
here: the count rule (at most 200 files) and the age rule (none older than 90
days). §5 requires both to be applied, "whichever removes more files governs" —
and because each rule deletes a prefix of the same ascending-timestamp-sorted
list, the union of the two deletion sets is exactly the longer prefix, so
``max()`` of the two prefix lengths implements the rule faithfully.

The orphan rule stays out of scope: §5 defines an orphan as "a log whose run was
deleted", which requires knowing which run ids still exist — a dependency on the
runs store that this module deliberately does not have. STORY-115 owns it,
together with wiring the prune into application startup.
"""

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from ollama_llm_bench.backend.domain import Iso8601Utc
    from ollama_llm_bench.backend.infra.protocols import Clock

_RUN_LOG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^run_.+_(?P<unix_ts>\d+)\.log$")
_SECONDS_PER_DAY: Final[int] = 86_400

DEFAULT_RUN_LOG_KEEP_COUNT: Final[int] = 200
DEFAULT_RUN_LOG_MAX_AGE_DAYS: Final[int] = 90


def _scan_run_logs(run_log_dir: Path) -> list[tuple[int, Path]]:
    """Return every run-log file as ``(unix_ts, path)``, oldest timestamp first.

    A file not matching the ``run_<run_id>_<unix_ts>.log`` template is skipped,
    as is any non-file entry. A missing directory yields an empty list.
    """
    if not run_log_dir.is_dir():
        return []

    matched: list[tuple[int, Path]] = []
    for candidate in run_log_dir.iterdir():
        if not candidate.is_file():
            continue
        match = _RUN_LOG_PATTERN.match(candidate.name)
        if match is None:
            continue
        matched.append((int(match.group("unix_ts")), candidate))

    matched.sort(key=lambda entry: entry[0])
    return matched


def _delete_oldest(matched: list[tuple[int, Path]], delete_count: int) -> int:
    """Delete the first ``delete_count`` entries of an oldest-first list."""
    for _, path in matched[:delete_count]:
        path.unlink()
    return delete_count


def age_cutoff_unix_ts(*, now_utc: "Iso8601Utc", max_age_days: int) -> int:
    """Return the oldest ``unix_ts`` a run log may carry and still be retained.

    A run log whose timestamp is strictly below the returned value is older than
    ``max_age_days`` and is pruned; one exactly on it is not yet older and stays.

    Args:
        now_utc: The current instant as read from the injected ``Clock``. A
            timezone-naive value is treated as UTC — ``datetime.timestamp()``
            would otherwise silently assume local time and shift the cutoff.
        max_age_days: The retention window in days (90 per §5).

    Returns:
        The cutoff as a Unix timestamp in seconds.
    """
    moment = datetime.fromisoformat(now_utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp()) - max_age_days * _SECONDS_PER_DAY


def cleanup_run_logs_by_count(*, run_log_dir: Path, keep_count: int) -> int:
    """Delete the oldest run-log files beyond ``keep_count``, oldest-timestamp first.

    The count rule in isolation. Production callers use
    ``cleanup_run_logs_by_count_and_age``; this remains the unit under test for
    the count rule on its own.

    Args:
        run_log_dir: The ``<app-data>/logs/run/`` directory to prune.
        keep_count: How many run-log files to retain (200 default per §5).

    Returns:
        The number of files deleted.
    """
    matched = _scan_run_logs(run_log_dir)
    return _delete_oldest(matched, max(0, len(matched) - keep_count))


def cleanup_run_logs_by_count_and_age(
    *, run_log_dir: Path, keep_count: int, clock: "Clock", max_age_days: int
) -> int:
    """Apply both §5 retention rules, oldest-timestamp first.

    Deletes the oldest files until at most ``keep_count`` remain **and** none is
    older than ``max_age_days``. Both rules delete a prefix of the same sorted
    list, so the governing deletion is the longer of the two prefixes — §5's
    "whichever removes more files governs".

    Args:
        run_log_dir: The ``<app-data>/logs/run/`` directory to prune.
        keep_count: How many run-log files to retain (200 default per §5).
        clock: The injected time source; its ``now_utc()`` anchors the age cutoff.
        max_age_days: The retention window in days (90 default per §5).

    Returns:
        The number of files deleted.
    """
    matched = _scan_run_logs(run_log_dir)
    excess_by_count = max(0, len(matched) - keep_count)
    cutoff = age_cutoff_unix_ts(now_utc=clock.now_utc(), max_age_days=max_age_days)
    expired_count = sum(1 for unix_ts, _ in matched if unix_ts < cutoff)
    return _delete_oldest(matched, max(excess_by_count, expired_count))
```

If ruff's `TC` rules disagree about which imports belong under `TYPE_CHECKING`, follow ruff — but
note that `datetime`, `UTC`, `re` and `Path` are used at runtime and must stay as plain imports.

- [ ] **Step 5: Run the colocated tests**

```bash
uv run pytest src/ollama_llm_bench/backend/log_file_writer/tests/ -v
```

Expected: **PASS**, including the three pre-existing `cleanup_run_logs_by_count` tests, which are
untouched. `test_startup_cleanup_prunes_oldest_to_200` still calls `cleanup_run_logs` with only
`platform_detector=` at this point and will fail in Task 3 — leave it; Task 3 fixes it.

- [ ] **Step 6: Prove the negative control — falsify the boundary, do not delete it**

Temporarily change `unix_ts < cutoff` to `unix_ts <= cutoff` in
`cleanup_run_logs_by_count_and_age`, re-run
`test_age_rule_retains_a_file_exactly_at_the_cutoff`, and confirm it **fails**. Then revert. This
proves the boundary test has teeth rather than passing vacuously.

- [ ] **Step 7: Lint and typecheck**

```bash
uv run ruff check src/ollama_llm_bench/backend/log_file_writer/
uv run ruff format --check src/ollama_llm_bench/backend/log_file_writer/
uv run mypy --strict src/ollama_llm_bench/backend/log_file_writer/
```

Expected: all clean.

- [ ] **Step 8: Commit**

```bash
git add src/ollama_llm_bench/backend/log_file_writer/_internal/run_log_cleanup.py \
        src/ollama_llm_bench/backend/log_file_writer/tests/conftest.py \
        src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py
git commit -m "feat(story-088): apply the 90-day run-log age rule alongside the count rule"
```

______________________________________________________________________

## Task 3: AC-2 (part 2) — expose the age rule through `api.cleanup_run_logs`

**Files:**

- Modify: `src/ollama_llm_bench/backend/log_file_writer/api.py:17-20,75-92`
- Modify: `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py:16-40`
- Create: `tests/integration/test_run_log_retention.py`

**Interfaces:**

- Consumes: `cleanup_run_logs_by_count_and_age`, `DEFAULT_RUN_LOG_KEEP_COUNT`,
  `DEFAULT_RUN_LOG_MAX_AGE_DAYS` from Task 2.

- Produces:
  `cleanup_run_logs(*, platform_detector: PlatformDetector, clock: Clock, keep_count: int = 200, max_age_days: int = 90) -> int`
  — exactly four parameters, the hard maximum. STORY-115 will call this from `compose.py`; nothing
  calls it today.

- [ ] **Step 1: Write the failing AC-2 integration test**

Create `tests/integration/test_run_log_retention.py`:

```python
"""Startup run-log retention — both §5 rules applied together (STORY-088-AC-2).

Source of truth: ``docs/v3_specification/12_Quality_and_NFRs/07_RESOURCE_LIMITS.md``
§5 ("At most 200 files; none older than 90 days ... The age rule and the count
rule are both applied; whichever removes more files governs") and §7 (enforced by
"Startup cleanup; integration test").
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ollama_llm_bench.backend.log_file_writer import cleanup_run_logs

_KEEP_COUNT = 200
_MAX_AGE_DAYS = 90
_DAY_SECONDS = 86_400
_HOUR_SECONDS = 3_600
_NOW_UNIX_TS = 1_800_000_000
_AGE_CUTOFF_TS = _NOW_UNIX_TS - _MAX_AGE_DAYS * _DAY_SECONDS


class _FakePlatformDetector:
    """A minimal fake satisfying the ``PlatformDetector`` Protocol structurally."""

    def __init__(self, app_data_root: Path) -> None:
        self._app_data_root = app_data_root

    @property
    def app_data_root(self) -> Path:
        return self._app_data_root


class _FakeClock:
    """A ``Clock`` pinned to ``_NOW_UNIX_TS`` so the 90-day cutoff is exact."""

    def now_utc(self) -> str:
        return datetime.fromtimestamp(_NOW_UNIX_TS, UTC).isoformat()

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def run_log_dir(tmp_path: Path) -> Path:
    """A fresh, empty ``<app-data>/logs/run/`` directory."""
    directory = tmp_path / "logs" / "run"
    directory.mkdir(parents=True)
    return directory


def _seed(run_log_dir: Path, *, count: int, first_run_id: int, first_ts: int, step: int) -> None:
    """Create ``count`` run-log files with timestamps ``first_ts + i * step``."""
    for offset in range(count):
        path = run_log_dir / f"run_{first_run_id + offset}_{first_ts + offset * step}.log"
        path.write_text("x", encoding="utf-8")


def _surviving_timestamps(run_log_dir: Path) -> set[int]:
    """Return the encoded timestamp of every run log still on disk."""
    return {int(path.stem.rsplit("_", 1)[1]) for path in run_log_dir.glob("run_*.log")}


def test_startup_prune_caps_run_logs_to_200_files_and_90_days(
    tmp_path: Path, run_log_dir: Path
) -> None:
    """Proves: STORY-088-AC-2

    Given a directory holding more than 200 run logs of which 20 predate the
    90-day cutoff, the prune leaves at most 200 files, all at most 90 days old,
    having deleted oldest-timestamp-first every file that violated either rule
    and retained every file that violated neither — the age rule governing here
    because it removes more (20) than the count rule would (10).
    """
    # Arrange
    _seed(run_log_dir, count=20, first_run_id=1, first_ts=_AGE_CUTOFF_TS - 20 * _DAY_SECONDS,
          step=_DAY_SECONDS)
    _seed(run_log_dir, count=190, first_run_id=101, first_ts=_AGE_CUTOFF_TS + _HOUR_SECONDS,
          step=_HOUR_SECONDS)
    expected_survivors = {
        _AGE_CUTOFF_TS + offset * _HOUR_SECONDS for offset in range(1, 191)
    }

    # Act
    deleted_count = cleanup_run_logs(
        platform_detector=_FakePlatformDetector(tmp_path),
        clock=_FakeClock(),
        keep_count=_KEEP_COUNT,
        max_age_days=_MAX_AGE_DAYS,
    )

    # Assert
    assert (deleted_count, _surviving_timestamps(run_log_dir)) == (20, expected_survivors)


def test_startup_prune_lets_the_count_rule_govern_when_it_removes_more(
    tmp_path: Path, run_log_dir: Path
) -> None:
    """Proves: STORY-088-AC-2

    The converse direction of §5's "whichever removes more files governs": with
    210 files of which only 3 predate the cutoff, the count rule's 10 deletions
    govern, and those 10 include the 3 expired files.
    """
    # Arrange
    _seed(run_log_dir, count=3, first_run_id=1, first_ts=_AGE_CUTOFF_TS - 3 * _DAY_SECONDS,
          step=_DAY_SECONDS)
    _seed(run_log_dir, count=207, first_run_id=101, first_ts=_AGE_CUTOFF_TS + _HOUR_SECONDS,
          step=_HOUR_SECONDS)
    expected_survivors = {
        _AGE_CUTOFF_TS + offset * _HOUR_SECONDS for offset in range(8, 208)
    }

    # Act
    deleted_count = cleanup_run_logs(
        platform_detector=_FakePlatformDetector(tmp_path),
        clock=_FakeClock(),
        keep_count=_KEEP_COUNT,
        max_age_days=_MAX_AGE_DAYS,
    )

    # Assert
    assert (deleted_count, _surviving_timestamps(run_log_dir)) == (10, expected_survivors)
```

Arithmetic check for the second test: 210 files total, `keep_count=200` → count rule deletes 10. The
oldest 10 are the 3 expired ones plus the 7 earliest fresh ones (`offset` 1–7), leaving `offset` 8–207
— exactly 200 survivors. The age rule alone would delete 3, so `max(10, 3) == 10` governs.

- [ ] **Step 2: Run it and confirm it fails**

```bash
uv run pytest tests/integration/test_run_log_retention.py -v
```

Expected: **FAIL** — `TypeError: cleanup_run_logs() got an unexpected keyword argument 'clock'`.

- [ ] **Step 3: Update `api.py`**

Change the import block (lines 17–20) to pull in the new symbols:

```python
from ollama_llm_bench.backend.log_file_writer._internal.run_log_cleanup import (
    DEFAULT_RUN_LOG_KEEP_COUNT,
    DEFAULT_RUN_LOG_MAX_AGE_DAYS,
    cleanup_run_logs_by_count_and_age,
)
```

Add `Clock` to the existing `PlatformDetector` import line:

```python
from ollama_llm_bench.backend.infra.protocols import Clock, PlatformDetector
```

Replace `cleanup_run_logs` (lines 75–92) with:

```python
@icontract.require(lambda keep_count: keep_count >= 0, "keep_count must be non-negative")
@icontract.require(lambda max_age_days: max_age_days >= 0, "max_age_days must be non-negative")
@icontract.ensure(lambda result: result >= 0)
def cleanup_run_logs(
    *,
    platform_detector: PlatformDetector,
    clock: Clock,
    keep_count: int = DEFAULT_RUN_LOG_KEEP_COUNT,
    max_age_days: int = DEFAULT_RUN_LOG_MAX_AGE_DAYS,
) -> int:
    """Prune ``<app-data>/logs/run/`` to the §5 retention limits, oldest first.

    Applies both rules §5 requires — at most ``keep_count`` files and none older
    than ``max_age_days`` — deleting oldest-timestamp-first until both hold. The
    orphan rule is not applied here: identifying a log whose run was deleted
    needs the runs store, which this module deliberately does not depend on
    (STORY-115).

    Args:
        platform_detector: Supplies the resolved application-data root.
        clock: The injected time source anchoring the age cutoff.
        keep_count: How many run-log files to retain (200 default).
        max_age_days: The retention window in days (90 default).

    Returns:
        The number of files deleted.
    """
    log_dir: Path = run_log_dir(platform_detector)
    return cleanup_run_logs_by_count_and_age(
        run_log_dir=log_dir, keep_count=keep_count, clock=clock, max_age_days=max_age_days
    )
```

Both contracts guard programmer invariants: `keep_count` and `max_age_days` are constants supplied by
the composition root, never a user-typed value. Leave `__all__` unchanged.

- [ ] **Step 4: Fix the existing colocated call site**

In `src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py`, change
`test_startup_cleanup_prunes_oldest_to_200` (line 16) to take the clock fixture and pass it:

```python
def test_startup_cleanup_prunes_oldest_to_200(
    tmp_path: Path, fake_platform_detector: FakePlatformDetector, fake_clock: FakeClock
) -> None:
```

and at line 33:

```python
    deleted_count = cleanup_run_logs(platform_detector=fake_platform_detector, clock=fake_clock)
```

Its assertions do not change: with `FAKE_NOW_UNIX_TS = 1_700_100_000` and files seeded at
`1_700_000_000 … 1_700_000_204`, every file is roughly a day old, so the age rule deletes nothing and
the count rule's 5 deletions still govern.

- [ ] **Step 5: Run both test files**

```bash
uv run pytest tests/integration/test_run_log_retention.py src/ollama_llm_bench/backend/log_file_writer/tests/ -v
```

Expected: **PASS** — all of them.

- [ ] **Step 6: Lint, typecheck, and check the import boundary**

```bash
uv run ruff check src/ollama_llm_bench/backend/log_file_writer/ tests/integration/test_run_log_retention.py
uv run ruff format --check src/ollama_llm_bench/backend/log_file_writer/ tests/integration/test_run_log_retention.py
uv run mypy --strict src/ollama_llm_bench/backend/log_file_writer/ tests/integration/test_run_log_retention.py
uv run lint-imports
```

Expected: all clean. `lint-imports` matters here because `_internal/run_log_cleanup.py` now imports
`backend.infra.protocols` and `backend.domain` — both permitted, but confirm rather than assume.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/backend/log_file_writer/api.py \
        src/ollama_llm_bench/backend/log_file_writer/tests/test_run_log_cleanup.py \
        tests/integration/test_run_log_retention.py
git commit -m "feat(story-088): expose the run-log age rule through cleanup_run_logs"
```

______________________________________________________________________

## Task 4: AC-3 — one shared `compose_filename` fake behind a fixture

**Files:**

- Create: `src/ollama_llm_bench/ui/resume_benchmark/tests/conftest.py`
- Modify: `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py` (lines 5, 45, 528–541,
  553–566, and the four `_make_export_collaborators` call sites at 584, 623, 670, 699)
- Modify: `src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller.py` (lines 4, 36, 187–195,
  and tests at 213, 254, 279, 307)
- Modify: `src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller_menu_actions.py` (lines 14,
  48, 214–223, `_make_controller` at 263, its 14 call sites, and the inline construction at ~336)

**Interfaces:**

- Produces:
  - `FakeExportFilenameHelper` — a class with
    `compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str`
  - `export_filename_helper` — a function-scoped fixture returning one `FakeExportFilenameHelper`
- Consumes: nothing from Tasks 1–3.

**Behaviour must not change.** All three current copies are behaviourally identical — sanitize with
`[^A-Za-z0-9._-]` → collapse runs of `_` → strip leading/trailing `_` and leading `.` → truncate to
80 characters → fall back to `Run_<run_id>` when empty → return `f"{base}_{kind}.{ext}"`. Every
filename the existing tests assert on must stay byte-identical.

- [ ] **Step 1: Create the shared conftest**

Create `src/ollama_llm_bench/ui/resume_benchmark/tests/conftest.py`:

```python
"""Shared fixtures for ``ui/resume_benchmark/`` colocated tests."""

import re
from typing import Final

import pytest

from ollama_llm_bench.backend.domain import BenchmarkRun

_SANITIZE_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")
_MAX_BASE_LENGTH: Final[int] = 80


class FakeExportFilenameHelper:
    """An ``ExportFilenameHelper`` fake: real sanitisation plus the
    ``Run_<run_id>`` fallback (``05_EXPORT_FORMATS.md`` §2).

    STORY-088-AC-3 consolidated the three byte-identical copies that previously
    lived one apiece in ``test_actions.py``, ``test_controller.py`` and
    ``test_controller_menu_actions.py``.
    """

    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        sanitized = _SANITIZE_RE.sub("_", run.run_name or "")
        collapsed = re.sub(r"_+", "_", sanitized)
        stripped = collapsed.strip("_").lstrip(".")[:_MAX_BASE_LENGTH]
        base = stripped or f"Run_{run.run_id}"
        return f"{base}_{kind}.{ext}"


@pytest.fixture
def export_filename_helper() -> FakeExportFilenameHelper:
    """The shared ``ExportFilenameHelper`` fake — one fresh instance per test."""
    return FakeExportFilenameHelper()
```

- [ ] **Step 2: Write the failing AC-3 test in `test_actions.py`**

Append to `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py`, importing
`FakeExportFilenameHelper` from
`ollama_llm_bench.ui.resume_benchmark.tests.conftest` for the type annotation:

```python
def test_export_uses_shared_compose_filename_fixture(
    tmp_path: Path, export_filename_helper: FakeExportFilenameHelper
) -> None:
    """Proves: STORY-088-AC-3

    The export action's suggested target filename is exactly what the shared
    ``conftest.py`` fixture's ``compose_filename`` returns, so the three resume
    test modules can consume one fake instead of each defining a copy.
    """
    # Arrange
    run = _run(1, status=RunStatus.COMPLETED)
    target = str(tmp_path / "summary.csv")
    gateway = _FakeResumeGateway(run=run, tasks=(), results=())
    native_pickers = _FakeNativePickers(save_path=target)
    collaborators = _make_export_collaborators(
        gateway=gateway,
        native_pickers=native_pickers,
        file_system_actions=_FakeFileSystemActions(),
        event_bus=_RecordingEventBus(),
        export_filenames=export_filename_helper,
    )
    request = TableExportRequest(run_id=1, table="summary", fmt="csv")
    expected = export_filename_helper.compose_filename(run=run, kind="summary", ext="csv")

    # Act
    export_table(collaborators=collaborators, request=request)

    # Assert
    assert native_pickers.last_options is not None
    assert native_pickers.last_options.suggested_name == expected
```

This needs no new recording on the fake: `_FakeNativePickers.save_file` (line 413) already stores the
`SavePickerOptions` it was handed on `self.last_options`, and `actions.export_table` (line 303–309)
passes `compose_filename(...)`'s result straight into that struct's `suggested_name` field. The
`assert ... is not None` line is a type narrowing for `mypy --strict`, not a second logical concept —
`last_options` is declared `SavePickerOptions | None`.

- [ ] **Step 3: Run it and confirm it fails**

```bash
uv run pytest "src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py::test_export_uses_shared_compose_filename_fixture" -v
```

Expected: **FAIL** — `TypeError: _make_export_collaborators() got an unexpected keyword argument 'export_filenames'`.

- [ ] **Step 4: Rewire `test_actions.py`**

Delete `_FakeExportFilenameHelper` (lines 528–534), `_sanitize` (lines 537–541), `_SANITIZE_RE`
(line 45) and `import re` (line 5) — none has any other use in the file.

Change `_make_export_collaborators` (line 553) to take the helper:

```python
def _make_export_collaborators(
    *,
    gateway: _FakeResumeGateway,
    native_pickers: _FakeNativePickers,
    file_system_actions: _FakeFileSystemActions,
    event_bus: _RecordingEventBus,
    export_filenames: FakeExportFilenameHelper,
) -> ResumeBenchmarkCollaborators:
    return ResumeBenchmarkCollaborators(
        gateway=gateway,
        event_bus=event_bus,
        native_pickers=native_pickers,
        file_system_actions=file_system_actions,
        export_filenames=export_filenames,
    )
```

That is five keyword arguments on a test helper. This is fine and needs no restructuring: the
≤ 4-parameter limit in `coding-style.md` governs production code, and ruff's `PLR0913` is left at its
default `max-args = 5` in `pyproject.toml`, so it fires only above five.

At each of the four existing call sites (lines 584, 623, 670, 699), add
`export_filenames=export_filename_helper,` as the final argument, and add
`export_filename_helper: FakeExportFilenameHelper` to that test's signature.

- [ ] **Step 5: Run `test_actions.py`**

```bash
uv run pytest src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py -v
```

Expected: **PASS**, including every pre-existing export assertion — the filenames must be unchanged.

- [ ] **Step 6: Rewire `test_controller.py`**

Delete `_FakeExportFilenameHelper` (lines 187–195), `_SANITIZE_RE` (line 36) and `import re`
(line 4). All four construction sites sit directly inside test bodies, so no helper changes are
needed: add `export_filename_helper: FakeExportFilenameHelper` to the signatures of the tests at
lines 213, 254, 279 and 307, and replace each `export_filenames=_FakeExportFilenameHelper(),` with
`export_filenames=export_filename_helper,`. Import `FakeExportFilenameHelper` from
`ollama_llm_bench.ui.resume_benchmark.tests.conftest` for the annotations.

```bash
uv run pytest src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller.py -v
```

Expected: **PASS**.

- [ ] **Step 7: Rewire `test_controller_menu_actions.py`**

Delete `_FakeExportFilenameHelper` (lines 214–223), `_SANITIZE_RE` (line 48) and `import re`
(line 14). Import `FakeExportFilenameHelper` from
`ollama_llm_bench.ui.resume_benchmark.tests.conftest`.

Change `_make_controller` (line 263) to:

```python
def _make_controller(
    gateway: _FakeResumeGateway,
    *,
    bus: _RecordingEventBus,
    export_filenames: FakeExportFilenameHelper,
) -> tuple[ResumeBenchmarkController, QWidget]:
    controller = ResumeBenchmarkController(
        collaborators=ResumeBenchmarkCollaborators(
            gateway=gateway,
            event_bus=bus,
            native_pickers=_FakeNativePickers(),
            file_system_actions=_FakeFileSystemActions(),
            export_filenames=export_filenames,
        )
    )
    view = _StubResumeView()
    controller.bind(view)
    controller.load_initial_rows()
    return controller, view
```

Then apply the same identical two-part edit to each of the 14 call sites — lines **290, 305, 354,
384, 443, 472, 496, 521, 544, 564, 579, 601, 624, 643**:

```python
# before
    controller, view = _make_controller(gateway, bus=bus)
# after
    controller, view = _make_controller(gateway, bus=bus, export_filenames=export_filename_helper)
```

and add `export_filename_helper: FakeExportFilenameHelper` to the signature of the test function
enclosing each of those call sites. Finally, the one inline construction (around line 336, inside the
test that calls `controller.on_context_menu_requested(0, QPoint(0, 0))`) becomes
`export_filenames=export_filename_helper,` with the same fixture added to that test's signature.

Line numbers shift as you edit. Work bottom-up, or re-grep after each batch:

```bash
grep -n "_make_controller(\|_FakeExportFilenameHelper" src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller_menu_actions.py
```

- [ ] **Step 8: Run the whole resume-widget colocated suite**

```bash
uv run pytest src/ollama_llm_bench/ui/resume_benchmark/tests/ -v
```

Expected: **PASS**, with the same test count as before plus the one new AC-3 test.

- [ ] **Step 9: Verify no copy of the fake survives**

```bash
grep -rn "compose_filename" src/ollama_llm_bench/ui/resume_benchmark/tests/
```

Expected: exactly two kinds of hit — the definition in `conftest.py`, and the AC-3 test's call to
`export_filename_helper.compose_filename(...)`. **No** `def compose_filename` inside any `test_*.py`.
This is the story's Definition-of-Done checkbox, checked directly.

- [ ] **Step 10: Lint and typecheck**

```bash
uv run ruff check src/ollama_llm_bench/ui/resume_benchmark/
uv run ruff format --check src/ollama_llm_bench/ui/resume_benchmark/
uv run mypy --strict src/ollama_llm_bench/ui/resume_benchmark/
```

Expected: all clean. Watch specifically for `F401` on a now-unused `re` import — that means a
`_SANITIZE_RE` deletion was missed.

- [ ] **Step 11: Commit**

```bash
git add src/ollama_llm_bench/ui/resume_benchmark/tests/
git commit -m "test(story-088): share one compose_filename fake across the resume tests"
```

______________________________________________________________________

## Task 5: Verify, trace, and close

**Files:**

- Modify: `docs/stories/story-088-test-debt-closure.md` (front-matter `status`)
- Modify: `docs/stories/story-115-run-log-retention-orphan-rule-and-startup-wiring.md` (front-matter
  `status`)
- Modify: `traceability.yaml` (generated)

**Why the full gate, not just the touched modules:** this story changes a `conftest.py` and adds
another. A shared fixture file is one of the named blast-radius triggers — a mistake there fails
modules whose own tests you never ran. It also changes a public `api.py` signature.

- [ ] **Step 1: Run the full gate, redirected to a file**

Never pipe a long run through `tail` — `tail` buffers until the process exits, which has already
hidden a finished gate's result for hours in this repo.

```bash
just check > /tmp/story088-gate.log 2>&1; echo "exit=$?"
```

Expected: `exit=0` in roughly 2 minutes. Materially longer means it is hung, not slow — kill it and
diagnose, because no `pytest-timeout` is configured and a blocking dialog produces no output at all.
Read the tail of the log afterwards with `Read`, not `tail -f`.

- [ ] **Step 2: Diff against the baseline**

Compare the failure list against a clean-tree baseline. If anything fails, do **not** accept
"pre-existing and unrelated" without the exclusion test: re-run with only the suspect file ignored,
compare the two failure lists, and record that output beside the claim.

Also do not run a second full-suite verification concurrently with this one — two concurrent runs
manufacture timing failures in Qt tests that are indistinguishable from real regressions.

- [ ] **Step 3: Regenerate and validate traceability**

```bash
just trace
just trace-check
```

Expected: `trace-check` passes with zero failures — every one of `STORY-088-AC-1`, `-AC-2` and
`-AC-3` mapped to at least one test, no orphan clause, no orphan test.

- [ ] **Step 4: Flip the story statuses**

In `docs/stories/story-088-test-debt-closure.md`, set `status: done`.

In `docs/stories/story-115-run-log-retention-orphan-rule-and-startup-wiring.md`, set `status: ready`
— STORY-088 is its only dependency, so it flips unconditionally.

Then check STORY-093: leave it `draft` and name the outstanding dependencies in the closing report
unless every one of STORY-076…089, 091, 092 and 114 is already `done`.

```bash
grep -l "^status: " docs/stories/story-0{76,77,78,79,80,81,82,83,84,85,86,87,88,89,91,92}-*.md docs/stories/story-114-*.md | xargs grep -H "^status:"
```

- [ ] **Step 5: Re-run trace after the status change**

`traceability.yaml` embeds each story's `status`, so it goes stale the moment one changes.

```bash
just trace
just trace-check
```

Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add docs/stories/story-088-test-debt-closure.md \
        docs/stories/story-115-run-log-retention-orphan-rule-and-startup-wiring.md \
        traceability.yaml
git commit -m "docs(story-088): close the story and flip STORY-115 to ready"
```

______________________________________________________________________

## Closing report — state these explicitly

- Each acceptance criterion named with the test that proves it.
- The `just check` tail, pasted, diffed against baseline.
- `just trace-check` passing.
- STORY-115 flipped to `ready`; STORY-093's remaining blockers named if it stayed `draft`.
- The two items this story deliberately leaves open — the run-log **orphan** rule and wiring
  `cleanup_run_logs` into application startup — are both already owned by **STORY-115**. Name it as
  the immediate follow-on; do not re-raise them as unowned.
- Ranked next picks. The natural candidates are the other independently-`ready` finalization stories
  that also gate STORY-093 and do not depend on this one: **STORY-084**, **STORY-085**, **STORY-092**.
