# Open Questions

**Status:** Draft
**Owner:** human-reviewer
**Audience:** human, architect
**Last Updated:** 2026-06-06
**Cross-references:** [01_RISK_REGISTER.md](01_RISK_REGISTER.md), [03_PROPOSED_ADRS.md](03_PROPOSED_ADRS.md), [../08_Cross_Cutting/08-F_spec_issues_log.md](../08_Cross_Cutting/08-F_spec_issues_log.md), [../10_Domain_and_Data/02_DTOS_AND_ENUMS.md](../10_Domain_and_Data/02_DTOS_AND_ENUMS.md), [../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md](../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md)

This document records the questions that were previously open against the specification. As of 2026-06-03, **all open questions are resolved**. Both prior deferred entries — Q-001 (refined per-task status enum names) and Q-002 (anyio inclusion) — are now closed. The question entries below are retained for historical record; each carries its resolving decision identifier and a Resolution subsection summarising the outcome.

---

## Table of Contents

1. [Status of Prior Open Questions](#1-status-of-prior-open-questions)
2. [Resolved Questions (historical record)](#2-resolved-questions-historical-record)
   - [Q-001 — Refined per-task status enum names (RESOLVED — see D-016 + D-047 / DD-37)](#q-001--refined-per-task-status-enum-names-resolved--see-d-016--d-047--dd-37)
   - [Q-002 — Inclusion of the anyio library (RESOLVED — see D-027 / DD-37)](#q-002--inclusion-of-the-anyio-library-resolved--see-d-027--dd-37)
3. [Resolution Process](#3-resolution-process)

---

## 1. Status of Prior Open Questions

All previously catalogued open questions for this specification — twenty-seven in total — were resolved during the project interview. Their resolutions are recorded as decisions D-005 through D-029 in the project decision log and are reflected throughout the specification. The full catalogue of source-document conflicts, contradictions, and the decisions that closed them is maintained in [../08_Cross_Cutting/08-F_spec_issues_log.md](../08_Cross_Cutting/08-F_spec_issues_log.md).

The two items previously deferred — Q-001 and Q-002 below — are now also resolved (closed 2026-06-03; see DD-37 in the decisions log). **No interview-stage open questions remain against this specification.** This document tracks only the interview-stage `Q-NNN` questions; *implementation-time* spec issues found during the pre-implementation review (and their resolutions) are tracked separately in `SPEC_REVIEW/11_REVIEW_BACKLOG.yaml` and the in-tree decision log `08_Cross_Cutting/08-F_spec_issues_log.md` (decisions DD-38 onward). New questions arising during implementation are added here with the next free `Q-NNN` identifier.

## 2. Resolved Questions (historical record)

### Q-001 — Refined per-task status enum names (RESOLVED — see D-016 + D-047 / DD-37)

**Status.** RESOLVED.
**Resolved on.** 2026-06-03.
**Resolving decisions.** D-016 (froze the initial ten names), D-047 (added `FAILED_JUDGE_TIMEOUT`), and DD-37 (closeout entry).

**Question (historical).** The per-task status enumeration currently has ten provisional names. These names are being refined so that each clearly reflects its purpose and is unambiguous to both implementers and readers. What is the final, confirmed set of per-task status enum names?

**Background (historical).** The decision to refine the provisional names rather than keep them is settled (decision D-016). What remains open is the specific refined set. The refined names are best chosen alongside the full domain model, where every status, transition, and persisted shape is specified together — so the proposal is produced during the domain-model work rather than in advance.

**Owner (historical).** Architecture lead proposes the refined set; the project owner confirms it.

**Decision deadline (historical).** Before [../10_Domain_and_Data/02_DTOS_AND_ENUMS.md](../10_Domain_and_Data/02_DTOS_AND_ENUMS.md) is marked Accepted.

**Options under consideration (historical).**
- **A — Refine in place.** Keep ten distinct statuses but rename each provisional name to a clearer, purpose-reflecting name. This is the expected direction per D-016.
- **B — Refine and consolidate.** Rename and, where two provisional statuses are not behaviourally distinct, merge them — reducing the count below ten if the domain model shows no transition or UX depends on the distinction.
- **C — Refine and split.** Rename and, if the domain model reveals a state the provisional set conflates, add a status — raising the count above ten.

**Resolution.** Option C was effectively taken: ten names were frozen by D-016 (`PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`, `COMPLETED`, `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `ERRORED`); D-047 then added an eleventh member, `FAILED_JUDGE_TIMEOUT`, to distinguish a per-task judge-call timeout (or a judge-model exclusion) from a plain inference timeout. The final 11-member set is therefore:

`PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`, `COMPLETED`, `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`.

The verdict (`PASS` / `FAIL`) is a separate field, set only when status equals `COMPLETED`. The five retryable terminal states are `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, and `ERRORED`. The authoritative declaration lives in [../10_Domain_and_Data/02_DTOS_AND_ENUMS.md](../10_Domain_and_Data/02_DTOS_AND_ENUMS.md) §4.3 (`ResultStatus`); the closeout rationale is recorded as DD-37 in [../08_Cross_Cutting/08-F_spec_issues_log.md](../08_Cross_Cutting/08-F_spec_issues_log.md). This entry was stale — the names had already been frozen by the two earlier decisions — and is now closed.

---

### Q-002 — Inclusion of the anyio library (RESOLVED — see D-027 / DD-37)

**Status.** RESOLVED — **stdlib only; anyio NOT adopted.**
**Resolved on.** 2026-06-03.
**Resolving decisions.** D-027 (promoted from DEFERRED to RESOLVED — stdlib only) and DD-37 (closeout entry).

**Question (historical).** Should the `anyio` library be included in the dependency set to provide fine-grained, shielded cancellation scopes, or is the standard-library asyncio toolset sufficient?

**Background (historical).** The concurrency model uses a single asyncio loop on the Qt main thread via qasync, with an explicit application-defined `CancellationToken` for pause and stop. The question is whether shielded cleanup — guaranteeing that teardown work completes even while a cancellation is propagating — needs `anyio`'s cancel-scope primitive, or whether standard-library asyncio shielding plus the custom token is enough. The decision is deferred to the implementation-model design (decision D-027).

**Owner (historical).** Concurrency lead proposes; architecture lead confirms.

**Decision deadline (historical).** Before [../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md](../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md) is marked Accepted.

**Options under consideration (historical).**
- **A — Standard library only (default lean).** Use standard-library asyncio plus qasync plus the custom `CancellationToken`. Achieve shielded cleanup with standard-library shielding constructs. This is the default position: it keeps the dependency surface minimal and is preferred unless a concrete need is demonstrated.
- **B — Add anyio for shielded scopes.** Include `anyio` solely for its cancel-scope primitive, used where teardown must be shielded from an in-flight cancellation. Adopt this only if the concurrency-model design shows that standard-library shielding cannot cleanly express a required shielded-cleanup path.

> **SUPERSEDED by D-R-01 (2026-06-04).** The `asyncio` + `qasync` model in the historical resolution below has been replaced by a synchronous, Qt-free backend driven by a `QThreadPool` `TaskRunner`, with a `threading.Event`-backed `CancellationToken`. `asyncio`, `qasync`, and `anyio` are all absent from the project, so the anyio-vs-stdlib question (Q-002) is moot. Authoritative: `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` and `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`.

**Resolution (historical).** **Option A — standard library only.** The concurrency model uses standard-library `asyncio` plus `qasync` plus the application-defined `CancellationToken`. Shielded cleanup is expressed with `asyncio.shield`, `try` / `finally` blocks, and `asyncio.TaskGroup` with shielded subroutines — not with anyio cancel-scopes. `anyio` is **NOT** added to the dependency set. The authoritative concurrency model lives in [../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md](../11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md) and is binding; the binding rules and anti-patterns are in [../16_Engineering_Standards/04_CONCURRENCY_STANDARD.md](../16_Engineering_Standards/04_CONCURRENCY_STANDARD.md). The closeout rationale is recorded as DD-37 in [../08_Cross_Cutting/08-F_spec_issues_log.md](../08_Cross_Cutting/08-F_spec_issues_log.md). Decision D-027 is hereby promoted from DEFERRED to RESOLVED — stdlib only.

## 3. Resolution Process

- An open question is resolved by the named owner securing confirmation from the project owner, then recording the outcome here and in the project decision log with a new decision identifier.
- The affected specification file may not be marked Accepted until its blocking question is resolved.
- If new open questions arise during later phases, they are added here with the next free `Q-NNN` identifier; identifiers are never reused.
- A question that turns out to require an architectural choice is also recorded as a proposed ADR in [03_PROPOSED_ADRS.md](03_PROPOSED_ADRS.md).
