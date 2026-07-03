# Proposed Architecture Decision Records

**Status:** Draft
**Owner:** human-reviewer
**Audience:** human, architect
**Last Updated:** 2026-06-06
**Cross-references:** [01_RISK_REGISTER.md](01_RISK_REGISTER.md), [02_OPEN_QUESTIONS.md](02_OPEN_QUESTIONS.md), [../14_Process_and_Traceability/](../14_Process_and_Traceability/), [../16_Engineering_Standards/](../16_Engineering_Standards/), [../13_Distribution_and_Release/](../13_Distribution_and_Release/)

This document holds the architecture decision records that are in `proposed` status. They capture architecturally significant decisions the project owner delegated for resolution within the specification work. Each record follows the MADR structure: context, decision, status, consequences, and the alternatives considered. These records are proposed, not yet accepted: once reviewed and approved by the project owner, each becomes a full, numbered ADR in [../14_Process_and_Traceability/](../14_Process_and_Traceability/) and is referenced from the affected specification files.

---

## Table of Contents

1. [Conventions](#1-conventions)
2. [ADR-P-001 — Programmatic Qt Widgets UI with Python design tokens](#adr-p-001--programmatic-qt-widgets-ui-with-python-design-tokens)
3. [ADR-P-002 — Scoped reactive state stores plus a typed event bus](#adr-p-002--scoped-reactive-state-stores-plus-a-typed-event-bus)
4. [ADR-P-003 — uv build backend and portable unsigned distribution](#adr-p-003--uv-build-backend-and-portable-unsigned-distribution)
5. [Promotion to Full ADRs](#5-promotion-to-full-adrs)

---

## 1. Conventions

- Each record carries a stable identifier `ADR-P-NNN`. On promotion to a full ADR, the record keeps a traceable link to its proposed-stage identifier.
- `Status: proposed` means the decision is recommended and reflected in the specification, but is not yet ratified by the project owner.
- The `Decision` section states what the project will do. The `Consequences` section states what follows — both the benefits and the costs. The `Alternatives considered` section records what was rejected and why, so the decision is auditable.

---

## ADR-P-001 — Programmatic Qt Widgets UI with Python design tokens

**Status:** proposed
**Relates to:** decision D-020

### Context

The application is a multi-pane desktop tool built on the Qt for Python binding. The user interface must be themeable (at minimum a light and a dark theme), consistent across many widgets, testable headlessly in CI, and maintainable by an AI implementation agent working module by module. Qt offers two UI construction approaches — a declarative markup language and programmatic widget construction — and two styling approaches — stylesheet text files and programmatic styling. The entire binding research and technical-decision corpus that grounds this project is built around programmatic Qt Widgets; the declarative markup path is unsupported by that corpus. Styling needs a single source of truth so that themes stay consistent and an agent cannot drift styling logic across the codebase.

### Decision

Build the user interface programmatically with Qt Widgets. Do not use the declarative Qt markup language. Express all visual design values — colours, spacing, typography, role definitions — as typed Python objects (design tokens) in a single theme module. A single theme module is the only place that generates and applies styling from those tokens; it compiles application-level styling at theme-switch time. Direct per-widget stylesheet calls are forbidden outside the theme module; widgets express their styling intent by setting a role property that the theme module interprets. Stylesheet text files are not a source of truth — if any stylesheet text exists, it is generated from the Python tokens by the theme module.

### Consequences

**Positive.**
- One theme module owns all styling; themes stay internally consistent and a live theme switch is a single, well-defined operation.
- Design tokens as typed Python objects are checkable by the type checker and validatable at startup (for example for theme parity and contrast).
- The declarative-markup toolchain, its tooling, and its testing limitations are avoided; widgets are plain Python and test cleanly headlessly.
- An architecture test can forbid stylesheet calls outside the theme module, preventing styling drift.

**Negative / costs.**
- Programmatic widget construction is more verbose than declarative markup for large static layouts.
- All contributors must learn the role-property convention rather than writing inline styling.
- The theme module becomes a central, carefully reviewed component; changes to it are higher-impact.

### Alternatives considered

- **Declarative Qt markup for the UI.** Rejected: the binding research and technical-decision corpus is entirely Qt-Widgets-based; adopting the declarative path would diverge from every grounding decision and its tooling and testing guidance.
- **Stylesheet text files as the styling source of truth.** Rejected: text stylesheets are untyped, cannot be validated by the type checker, and invite per-widget drift; tokens-in-Python with a single generator gives one validated source.
- **Unrestricted per-widget stylesheet calls.** Rejected: this scatters styling logic across the codebase, makes a consistent theme switch impossible to guarantee, and cannot be enforced by an architecture test.
- **A third-party theme-engine library as the styling layer.** Rejected: it would own the theme contract instead of the application, complicating live theme switching and token validation.

---

## ADR-P-002 — Scoped reactive state stores plus a typed event bus

**Status:** proposed
**Relates to:** decision D-021

### Context

The application has many widgets that must stay coordinated: run controls, progress, result tables, charts, and settings all reflect shared state. Some of that state is cross-cutting (the active run, the selected run, the current theme, table filters); some is purely local to one widget; and some interactions are one-shot intents rather than state (a run started, a chart drill-down requested). Backend work runs on `QThreadPool` worker threads via the adapter's `TaskRunner` (D-R-01), so updates frequently originate on a thread other than the one the widget runs on. The architecture needs one clear rule for where each kind of state lives and how cross-thread updates reach the UI, so that an AI implementation agent does not invent ad-hoc coupling.

### Decision

Adopt a hybrid pattern with three clearly separated mechanisms:

- **Cross-cutting state lives in scoped reactive state stores.** Each store holds a frozen snapshot of one slice of state and emits a change signal when the snapshot is atomically swapped. Stores are constructed and wired by the composition root; there are no global state singletons.
- **Purely local widget state lives in a frozen view-model object inside the widget's own module** and never becomes a store.
- **One-shot domain events travel on a typed event bus.** Events are frozen typed objects owned by the publishing module; the bus carries intents and notifications, not durable state.

The adapter layer marshals cross-thread signals onto the Qt main thread; backend code never touches a widget directly. This split — stores for state, the event bus for one-shot intents, the adapter layer for the thread boundary — is the application's cross-widget and UI-to-backend communication contract.

### Consequences

**Positive.**
- A single, testable rule decides where any piece of state or interaction belongs, removing a common source of ad-hoc coupling.
- Frozen snapshots with atomic swaps make state transitions explicit and make stale reads detectable.
- The event bus keeps one-shot intents out of stores, so stores never accumulate transient flags.
- The adapter-layer thread boundary is one place to audit for cross-thread correctness, supporting an architecture test.

**Negative / costs.**
- Two coordination mechanisms exist; contributors must internalize the state-versus-intent rule, and a wrong choice produces awkward code.
- Scoped stores plus per-widget view models is more structure than a single shared state object, with more wiring in the composition root.
- The reactive store layer is an additional dependency whose behaviour the team must understand.

### Alternatives considered

- **A single global application state object.** Rejected: a god-store couples unrelated widgets, makes change-tracking coarse, and accumulates transient flags that belong on an event bus.
- **Plain binding signals for all cross-widget coordination.** Rejected: loosely typed signals give weak compile-time guarantees and no consistent snapshot/atomic-swap discipline.
- **An event bus for everything, including durable state.** Rejected: modelling durable state as a stream of events forces every consumer to rebuild current state from history and loses a single authoritative snapshot.
- **A reactive-extensions style library as the coordination layer.** Rejected: known thread-scheduling pitfalls with the binding's threading model and unnecessary conceptual weight for this application's needs.

---

## ADR-P-003 — uv build backend and portable unsigned distribution

**Status:** proposed
**Relates to:** decisions D-028, D-029

### Context

The application is a solo-maintained, cross-platform desktop tool distributed through public releases. Two distribution-shaping choices were delegated: which Python build backend to use, and how to distribute on Windows. The project already standardizes on the uv package manager and an exact pinned interpreter, and the application is distributed unsigned — macOS builds are ad-hoc signed only, with no paid certificates. The build backend and the Windows distribution form must fit a zero-paid-tooling, reproducible-build, single-maintainer workflow.

### Decision

Use `uv_build`, uv's native build backend, as the Python build backend for the project. Distribute the Windows build as a portable `.zip` archive only — no installer is provided. Continue to distribute all binaries unsigned: macOS builds are ad-hoc signed only, with no Developer ID and no notarization, and Windows binaries carry no Authenticode certificate. Release integrity is established by publishing an unsigned `SHA256SUMS` checksum file alongside the artifacts on each GitHub Release rather than by OS code-signing or any cryptographic signing. The checksums provide integrity (corruption detection), not authenticity; the trust anchor is the HTTPS GitHub Releases page itself (D-R-11b). There is no GPG, Ed25519, or Sigstore signing of checksums or artifacts. A user who wants stronger assurance can build from source. The application has no auto-update mechanism (DD-36); updates are manual user actions performed against the GitHub Releases page.

### Consequences

**Positive.**
- `uv_build` keeps the build backend within the same tool that already manages packaging and the locked dependency set, simplifying the toolchain for a solo maintainer.
- A portable Windows `.zip` requires no installer authoring or maintenance and lets users run the application without administrative rights.
- Avoiding paid code-signing certificates keeps distribution cost at zero.
- The published `SHA256SUMS` file lets a user verify a download is intact (corruption detection) without OS code-signing, at zero tooling and key-management cost.

**Negative / costs.**
- Unsigned binaries trigger first-run operating-system warnings and possible antivirus false positives; this is tracked as a distribution risk and mitigated with clear unblock documentation.
- The unsigned checksums are not an authenticity guarantee: an actor who controlled the GitHub Releases page could replace artifacts and checksums together. This residual risk is accepted (D-R-11b); cryptographic signing is an explicitly deferred option, re-evaluated only at a sustained user-base milestone.
- A portable `.zip` offers no start-menu integration, no uninstaller, and no file-association registration on Windows.
- `uv_build` is a comparatively young build backend; the project accepts tracking its maturity and treating backend upgrades as deliberate changes.

### Alternatives considered

- **A conventional general-purpose build backend.** Rejected as the default: it would add a second packaging tool alongside uv; `uv_build` keeps the toolchain unified. It remains a fallback if `uv_build` proves insufficient.
- **A Windows installer.** Rejected: an installer adds authoring and maintenance burden and provides little benefit for a portable single-folder application; the `.zip` is simpler for both maintainer and user.
- **Paid code-signing certificates (Apple Developer ID, Windows Authenticode).** Rejected for now: they carry recurring cost disproportionate to the current user base; this choice is explicitly revisited only at a sustained user-base milestone.
- **A self-contained single-file Windows executable.** Rejected: single-file packaging incurs slow startup and temporary-extraction behaviour; a portable folder distribution is preferred.

---

## 5. Promotion to Full ADRs

Each record above is promoted to a full, numbered ADR in [../14_Process_and_Traceability/](../14_Process_and_Traceability/) once the project owner ratifies it. On promotion:

- The proposed record's status changes from `proposed` to `accepted` and it receives its final ADR number.
- The full ADR retains a reference to its `ADR-P-NNN` identifier so the proposal stage stays traceable.
- The affected specification files — UI standards, state-management contracts, engineering standards, and distribution and release — add a cross-reference to the accepted ADR.
- If a record is rejected or materially changed during review, the change is recorded as a new decision in the project decision log and this document is updated to match.
