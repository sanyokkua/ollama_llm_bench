# ADR-0020 — Move off the `PySide6 <6.9` pin to fix the connection-registry use-after-free

**Status:** accepted
**Date:** 2026-08-19
**Deciders:** project owner, architect
**Supersedes:** —
**Superseded by:** —
**Relates to:** ADR-0001, STORY-117, STORY-121

## Context and problem statement

Since at least 2026-08-05 this repository's full gate (`just check`) has failed intermittently —
roughly one full run in three — with a native fault and **no failing test**: the process dies with
`Fatal Python error: Segmentation fault` (or `Bus error`) and exits 139, 138, or 134. The Python
frame printed in the fault dump moves between runs (`QWidget.__init__`,
`FieldEditorWidget._build_row`, `ProgressView._build_current_task_panel`,
`openai/_models.py::construct`, a pytest fixture teardown), always immediately under
`Garbage-collecting`. Because the reported site moved, the failure looked unattributable and was
repeatedly mistaken for whichever story happened to be in flight.

A dedicated investigation on 2026-08-19 root-caused it. Its findings, in the order that matters:

**The Python-level crash site is a bystander; the guilty native frame is inside PySide6.** macOS
wrote 24 `python3.13-*.ips` crash reports during the investigation. **15 of the 24** name the same
faulting frame:

```text
libpyside6.abi3.6.8.dylib  QHashPrivate::Data<QHashPrivate::Node<PySide::ConnectionKey,
                                                QMetaObject::Connection>>::erase(...Bucket)
libpyside6.abi3.6.8.dylib  PySide::onPysideReceiverSlotDestroyed(void*)
libpyside6.abi3.6.8.dylib  CallableObject_call(_object*, _object*, _object*)
libpython3.13.dylib        PyObject_CallOneArg
libpython3.13.dylib        gc_collect_main
libpython3.13.dylib        _Py_HandlePending
libpython3.13.dylib        _PyEval_EvalFrameDefault
```

Read bottom-up: ordinary Python code allocates, CPython's eval breaker runs a cyclic-GC pass, the
GC invokes the weakref-death callbacks of the objects it is collecting, one of those callbacks is
PySide6's C function `PySide::onPysideReceiverSlotDestroyed`, and that function erases an entry
from PySide6's process-global `ConnectionKey -> QMetaObject::Connection` `QHash` — through storage
that has already been freed.

**The fault addresses prove heap corruption, not a null dereference.**
`KERN_INVALID_ADDRESS at 0xaaaaaaaaaaaaaaf2` — `0xaa` is macOS `MallocPreScribble`'s
freshly-allocated-but-uninitialised fill, so the hash's bucket storage had been freed and the block
handed back out. `KERN_INVALID_ADDRESS at 0x65746176697270d8` (from an *unamplified* run) — the low
bytes spell `"private"` in ASCII, so the freed block had already been reused to hold a path string.

**The remaining 9 reports are the same bug one step downstream.** Once that `erase()` has written
through a stale pointer, the next large piece of work dies on the heap it corrupted:

| Downstream faulting frame                                                      | Reports |
| ------------------------------------------------------------------------------ | ------- |
| `dict_traverse` / `set_traverse` under `deduce_unreachable` (the next GC pass) | 3       |
| `QApplication::setStyleSheet` walking Qt's widget registry                     | 3       |
| `Shiboken::Object::deallocData` / `Shiboken::Object::recursive_invalidate`     | 2       |
| `abort()` from inside QtCore (unsymbolised)                                    | 1       |

This matters for reading the earlier evidence: the crashes previously attributed to
`tests/conftest.py:144 _isolate_qapp_appearance` are **not a second bug**. `setStyleSheet` walks
Qt's widget registry in C++, so it is simply the next operation big enough to trip over
already-corrupted memory.

**Why the precondition is common here.** `onPysideReceiverSlotDestroyed` is the weakref callback
PySide6 registers when a Qt signal is connected to a plain Python callable rather than to another
`QObject` (the `GlobalReceiverV2` path). When the sender `QObject` and the Python receiver both
become unreachable **in the same cyclic-GC pass**, the sender's C++ destruction has already torn
the connection registry down by the time the receiver's weakref callback tries to erase from it.
This suite builds and abandons thousands of widget trees, and `connect(partial(...))` /
`connect(lambda ...)` create Python reference cycles, so those trees can only ever be reclaimed by
the cyclic collector — never by refcounting.
`src/ollama_llm_bench/ui/task_editor/_internal/field_editor.py:242`
(`help_button.clicked.connect(partial(self._show_help, ...))`) is the representative example, and
`field_editor.py` is the single most frequent Python-level crash site.

**It is pre-existing, and it is not `test_deadline.py`.** Measured on the colocated `src` suite
(`uv run pytest src -q`, ~60 s, 2347 passed):

| Arm                                                | Crashes / runs |
| -------------------------------------------------- | -------------- |
| Branch `43b198e`, normal                           | 1 / 11         |
| BASE `4f01baa`, normal                             | 1 / 21         |
| Branch, amplified                                  | 6 / 12         |
| Branch, amplified, only `test_deadline.py` ignored | 6 / 12         |
| BASE `4f01baa`, amplified                          | 6 / 12         |

BASE and branch are indistinguishable, and the BASE crash's Python-level site is
character-for-character the site the branch crashes landed on. Removing
`backend/provider_openai_compatible/tests/test_deadline.py` entirely does not move the rate, so
that file — and STORY-086's read-timeout change behind it (ADR-0019) — is cleared.

**The amplifier is the single most useful artifact.** Under CPython's `pymalloc`, a freed object's
memory stays mapped, so the dangling pointer usually reads stale-but-valid bytes and the corruption
stays silent. Switching to the system allocator with macOS's scribble patterns turns the latent
use-after-free into a hard, immediate fault:

```bash
PYTHONMALLOC=malloc MallocScribble=1 MallocPreScribble=1 uv run pytest src -q
```

Per-run time rises to ~70–110 s and the crash rate rises from roughly 7 % to roughly 50 %. It is
trustworthy as a proxy because it produces the same faulting frame as an original, unamplified
`just check` segfault (`python3.13-2026-08-19-180314.ips`) — it is not an artifact of the
diagnostic configuration.

The installed binding is **PySide6 6.8.3**; `pyproject.toml` requires `PySide6>=6.8,<6.9`, matching
the version table at `16_Engineering_Standards/02_TOOLCHAIN.md` §8. So: given that the defective
code is inside `libpyside6` and not inside this application, which remediation is attempted first?

## Decision drivers

- **Only one candidate addresses the defect; the others avoid its trigger.** The faulting code is
  in `libpyside6`, so anything done in `src/` reduces how often the precondition arises without
  removing the use-after-free.
- **Cost of the experiment.** `16_Engineering_Standards/02_TOOLCHAIN.md` §7 already sets the
  dependency policy as "always the latest stable release at the time of work", with no long-term
  version freezing, so raising the binding is the repository's default posture rather than an
  exception. With the amplified reproducer in hand, testing 6.9.x is a measurement of tens of
  minutes, not a day.
- **Size and reversibility of the diff.** A pin change is one line in `pyproject.toml` plus a
  refreshed `uv.lock`, and reverting it is one line. Removing every `connect(partial(...))` /
  `connect(lambda ...)` across `ui/` is a broad refactor of code that is currently correct.
- **The gate must stay trustworthy.** A gate that is red one run in three for reasons unrelated to
  the change under test trains sessions to ignore red, which is how a real regression gets shipped.
- **No fix may work by hiding the crash.** `gc.disable()`, `-p no:randomly`, or skipping the
  crashing tests would leave a live use-after-free in a shipped desktop application.

## Considered options

- Option A — Move off the `<6.9` binding pin: raise the `PySide6` requirement so a 6.9.x build
  resolves, then re-measure against the amplified reproducer.
- Option B — Remove the `connect(partial(...))` / `connect(lambda ...)` reference cycles in `ui/`,
  so widget trees are reclaimed by refcounting instead of by the cyclic collector.
- Option C — Introduce a shared deterministic-widget-teardown fixture for Qt tests, generalising
  `tests/integration/test_theme_reapply_on_save.py::_flush_pending_widget_deletions`.
- Option D — Suppress the symptom: `gc.disable()`, `-p no:randomly`, or skipping the tests that
  happen to be running when the fault lands.

## Decision outcome

Chosen option: **Option A, attempted first**, with **Option B** as the first fallback and
**Option C** as the second. Option D is rejected outright and is never an acceptable outcome of
this work.

The rationale is that Option A is the only candidate that targets the actual defect. The
use-after-free lives in `libpyside6`'s global connection registry; Options B and C both work by
making the precondition rarer, so even a successful result from either leaves the bug present and
reachable — in the shipped application as well as in the suite. Option A is also now cheap to
falsify: a 24-run amplified arm settles it in well under an hour, against a background arm that
produced 6 crashes in 12 runs.

Option B ranks second because it is a real reduction in exposure and a defensible change on its own
terms, but it is a broad diff across correct UI code and it does not fix the defect. Option C ranks
last because it is the weakest of the three on its own logic: the flush it generalises performs a
`gc.collect()`, which is precisely the operation that triggers the fault — it makes the collection
deterministic without making it safe. Option D is rejected because every variant of it leaves a
live memory-corruption bug in a desktop application and merely stops the suite from noticing.

STORY-121 executes this ladder and records the measured evidence at each rung.

### Consequences

- **Positive — the remediation is aimed at the defect, not the trigger.** If a 6.9.x build fixes
  the registry lifetime bug, the crash is gone for every consumer of the binding, including the
  shipped application, not just for the test suite.
- **Positive — the diagnosis is now cheap to re-run.** The amplified reproducer
  (`PYTHONMALLOC=malloc MallocScribble=1 MallocPreScribble=1 uv run pytest src -q`) converts a
  30-plus-minute full-gate coin flip into a ~90-second measurement with a ~50 % per-run hit rate.
  Any future session evaluating a candidate fix has a decisive 12-to-24-run arm available.
- **Negative — until this lands, `just check` stays intermittently red at roughly one full run in
  three.** That is the recorded background rate for the full gate and it is not improved by
  anything in this decision.
- **Negative — the recognition signature must be learned, or sessions will keep chasing it.** A
  gate failure caused by this bug has **zero `FAILED` and zero `ERROR` lines** and ends with
  `Fatal Python error: Segmentation fault` (or `Bus error`), exiting 139, 138, or 134. That
  combination is this bug, not a regression in the change under test: re-run the gate rather than
  bisecting. A gate failure with even one `FAILED` line is something else and must be diagnosed
  normally.
- **Negative — a minor-version bump of the Qt binding can have its own fallout.** This is a
  Qt-heavy codebase with ~2350 colocated tests plus integration and e2e tiers, and the parity rig
  at `16_Engineering_Standards/07_TESTING_STANDARD.md` §12 fails any test that emits a Qt or PySide
  warning. Deprecations, enum moves, or stricter signal-signature checks in 6.9.x would surface as
  gate failures. The bump is therefore never validated by the reproducer alone; the full gate is
  part of the acceptance, and reverting the pin is the fallback if the fallout outweighs the fix.
- **Neutral — whether 6.9.x actually fixes it is untested.** Nothing in the investigation says it
  does. The decision is about which remediation is attempted first and at what cost, not about the
  outcome; STORY-121 supplies the outcome.
- **Neutral — the PySide6 defect is inferred from symbolised frames, not read from PySide6
  source.** The `libpyside6` sources are not vendored here, so the exact lifetime rule
  `onPysideReceiverSlotDestroyed` violates was not read from code. The *location* is certain
  (15 independent reports naming the frame, plus 9 downstream); the internal mechanism is a strong
  inference.
- **Neutral — every rate quoted under the amplifier is a proxy rate, not the gate's rate.** All 68
  runs behind those numbers are the `src` tier alone. The full gate exercises far more widgets, so
  its true rate is higher.
- **Neutral — STORY-117's premise is explained rather than falsified.** That story reduces Qt
  object churn in the accessibility tests on the theory that churn raises the flake rate. This
  decision confirms churn is the *precondition* — more abandoned widget trees means more chances
  for sender and receiver to die in one GC pass — while identifying the defect as PySide6's. Both
  can proceed; neither blocks the other.

## Recommendation to the owner — the version table will diverge until it is refreshed

`docs/v3_specification/` is read-only for automated sessions and **this ADR changes none of it.**
`16_Engineering_Standards/02_TOOLCHAIN.md` §8 records the `PySide6` floor as `>=6.8,<6.9`. Once
STORY-121 raises the requirement in `pyproject.toml`, that table row is stale. This is a
documentation refresh, not a spec conflict: §7 of the same document already states that each
dependency refresh advances the table and that the specification is a living document on this
point. The recommendation is that the owner authorise the §8 row update at the same time the pin
change lands, so the two do not drift.

## Pros and cons of the options

### Option A — Move off the `<6.9` binding pin

- Good — The only candidate that addresses the defect itself rather than its trigger; fixes the
  crash for the shipped application, not just the suite.
- Good — One line in `pyproject.toml` plus `uv lock --upgrade-package PySide6`; trivially
  revertible.
- Good — Aligned with the standing dependency policy (`02_TOOLCHAIN.md` §7): latest stable, no
  long-term freezing.
- Bad — Unproven. If 6.9.x carries the same registry lifetime bug, the arm comes back dirty and the
  time is spent for a negative result (a useful one, but not a fix).
- Bad — Minor-version Qt-binding fallout is possible across a large Qt surface and is only
  discoverable by running the full gate.

### Option B — Remove the `connect(partial(...))` / `connect(lambda ...)` cycles in `ui/`

- Good — Reduces real exposure: trees reclaimed by refcounting never reach the cyclic collector, so
  the precondition largely disappears.
- Good — Independently defensible; bound-method connections are the more conventional Qt pattern.
- Bad — Does not fix the defect. A single remaining cycle anywhere — including inside a third-party
  or test-only widget — re-arms it.
- Bad — A broad diff across correct code in multiple UI modules, with its own regression risk in
  exactly the widgets that are hardest to test.

### Option C — A shared deterministic-widget-teardown fixture

- Good — Makes widget destruction happen at a known point rather than at an arbitrary allocation,
  which would at least stabilise *where* the crash appears.
- Bad — Weakest of the three on its own logic: the flush it generalises calls `gc.collect()`, the
  very operation that triggers the fault. Making the trigger deterministic is not the same as
  removing it.
- Bad — Documented real cost to suite runtime, and an autouse teardown across every Qt test is
  precisely the kind of shared-fixture change that has previously produced session-wide
  contamination here.

### Option D — Suppress the symptom

- Good — Would make the gate green immediately.
- Bad — Leaves a live use-after-free in a shipped desktop application, now invisible. `gc.disable()`
  changes the application's memory behaviour globally; `-p no:randomly` is already measured not to
  prevent the crash; skipping tests deletes coverage to hide a real defect. Not acceptable under any
  reading of the project's Definition of Done.

## Links

- Related ADRs: ADR-0001 (chose programmatic Qt Widgets via PySide6, which is the binding this
  decision moves), ADR-0019 (the read-timeout change this investigation cleared of any role).
- Spec clauses: `docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md` §7
  (dependency-version policy) and §8 (consolidated version table, the `PySide6 >=6.8,<6.9` row);
  `docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md` §8 (testing PySide6
  widgets), §11 (time budgets — the four-minute full-suite target), §12 (the CI test environment
  and the Qt parity rig that fails on any Qt/PySide warning).
- Stories: STORY-121 (executes the remediation ladder and records the measured evidence),
  STORY-117 (reduces Qt object churn in the accessibility tests — the same precondition, a
  different lever).
- Investigation: `.superpowers/sdd/segfault-debug-report.md`, with raw per-run exit codes in
  `.superpowers/sdd/baseline-summary.txt`, `basesrc2-summary.txt`, `scribble-summary.txt`, and
  `arm-summary.txt`. Native crash reports:
  `~/Library/Logs/DiagnosticReports/python3.13-2026-08-19-*.ips`, starting with
  `python3.13-2026-08-19-180314.ips`. This directory is git-ignored, so these artifacts are local
  to the machine that produced them.
