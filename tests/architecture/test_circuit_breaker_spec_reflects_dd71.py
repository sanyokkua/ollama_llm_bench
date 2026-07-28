"""Guard test: `08_CIRCUIT_BREAKER.md` describes the dedicated-lightweight-probe design
(DD-71, ADR-0013), not the retired real-task-probe design (STORY-103).

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`
(the corrected document itself), `docs/adr/0013-dedicated-lightweight-circuit-breaker-probe.md`
(the outcome map this correction restates), and `docs/stories/story-102-pin-per-task-timeout-contract.md`
Notes (the nine stale sites this test guards, first catalogued there).

STORY-102's Notes catalogued nine sites in `08_CIRCUIT_BREAKER.md` that still described the
pre-DD-71 model — PROBING lazily admitting exactly one real benchmark task as its liveness
probe — after DD-71 (2026-06-06) replaced that design with a dedicated, single-attempt,
lightweight warmup-style call the pipeline issues before each row. STORY-103 corrects the
document; this test is the only artifact a documentation-only story can attach a passing test
to (`02_STORY_FORMAT.md`/`03_TRACEABILITY.md` require every `done` story's acceptance
criterion to have a non-empty `tests:` list), and it exists specifically to guard the
correction against a silent revert — the same failure mode that let DD-71 go half-propagated
for six weeks in the first place.

This module reads the document's *content* only. It does not shell out to
`scripts/validate_traceability.py` or invoke `mdformat` — those are separate
definition-of-done steps run by hand, not something a pytest test should do.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_PATH = (
    _REPO_ROOT
    / "docs"
    / "v3_specification"
    / "11_Services_and_Algorithms"
    / "08_CIRCUIT_BREAKER.md"
)

_SITE_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "6.2-should_skip-column",
        "`False` for the first query after the cooldown elapses; `True` for subsequent "
        "queries until the probe resolves",
        "before the next row instead of admitting any task through `should_skip`",
    ),
    (
        "6.3-state-diagram-note",
        "Exactly one task is\n        admitted as the probe.",
        "dedicated\n        lightweight probe call",
    ),
    (
        "6.5-cooldown-and-transition-to-probing",
        "it lets exactly that one task through as the probe",
        "no task is ever admitted through `should_skip` as a probe",
    ),
    (
        "6.6-probe-behaviour",
        'The "probe" is simply the next real benchmark task the pipeline routes to the provider',
        "dedicated lightweight warmup-style call",
    ),
    (
        "10.2-worked-example-recovery-step",
        "Task 41 runs against the provider as the probe and completes.",
        "the pipeline issues the dedicated lightweight probe call instead of routing task 41 "
        "itself",
    ),
    (
        "10.3-worked-example-failed-recovery-step",
        "task 41 is admitted as the probe",
        "Task 41 itself was never dispatched",
    ),
    (
        "CB-05",
        "the first query returns `False`",
        "the pipeline issues the dedicated probe call on the next row instead of admitting a task",
    ),
    (
        "CB-06",
        "only one task is admitted as the probe",
        "`should_skip` is `True` unconditionally throughout `PROBING`",
    ),
    (
        "CB-14",
        "Counts as a provider-attributable failure toward the threshold",
        "Never counts toward the breaker's failure threshold",
    ),
)
"""One entry per site STORY-102's Notes catalogued as stale: `(site_id, stale_substring,
corrected_substring)`. `stale_substring` is the exact pre-DD-71 wording that must no longer
appear anywhere in the document; `corrected_substring` is wording unique to the
dedicated-lightweight-probe correction that must now appear. `site_id` is only used as the
parametrize id, so a failure names which of the nine sites regressed."""

_SITE_IDS = [site_id for site_id, _, _ in _SITE_CASES]


@pytest.mark.parametrize(
    ("site_id", "stale_substring", "corrected_substring"), _SITE_CASES, ids=_SITE_IDS
)
def test_circuit_breaker_spec_reflects_dd71(
    site_id: str, stale_substring: str, corrected_substring: str
) -> None:
    """Proves: STORY-103-AC-1

    For each of the nine sites STORY-102's Notes catalogued as still describing the
    retired real-task-probe design (PROBING lazily admitting exactly one real benchmark
    task as its liveness probe), the corrected `08_CIRCUIT_BREAKER.md` no longer contains
    that site's stale wording and does contain wording unique to the design the code
    (STORY-100/STORY-101) actually implements: `should_skip` returns `True`
    unconditionally throughout `PROBING`, and liveness is decided by one dedicated,
    single-attempt, lightweight warmup-style call the pipeline issues before each row —
    never a real task admitted through `should_skip`. The `CB-14` case additionally
    proves the document no longer states that a per-task timeout counts toward the
    breaker's failure threshold, resolving its contradiction with §6.4/§6.9.
    """
    # Arrange
    text = _SPEC_PATH.read_text(encoding="utf-8")

    # Act / Assert
    assert stale_substring not in text, f"{site_id}: stale real-task-probe wording still present"
    assert corrected_substring in text, f"{site_id}: dedicated-probe wording still missing"
