# Constraints

**Status:** Draft
**Owner:** human-reviewer
**Audience:** all
**Last Updated:** 2026-06-06
**Cross-references:** 00_Foundation/03_VISION.md; 08_Cross_Cutting/08-A_architecture_principles.md; 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md; 16_Engineering_Standards/

This document records, in writing, everything Ollama LLM Bench deliberately does not do. Each constraint has a statement, a reason, and a pointer to where it is enforced. The list is append-only — a constraint is added when a decision is made, and is only ever removed by an explicit, recorded reversal.

---

## Table of Contents

1. Hard constraints
2. Soft constraints

---

## 1. Hard constraints

### No data migration or conversion — additive structural steps only (DD-53)

The application has **no data-migration framework**: existing rows are never updated,
backfilled, transformed, or rewritten by an upgrade — ever. Within one major version the
schema may evolve through purely structural additive steps (`ADD COLUMN` with
`NULL`/default, new tables/indexes, new settings keys), applied automatically at startup so
user run history survives normal evolution. A new major version installs against a fresh
database; a cross-major or newer-than-app schema version on startup is a clear, hard error,
never an automatic in-place upgrade.
**Reason:** data-transforming migration code is a permanent maintenance and correctness burden for a single-user local tool; purely structural additive steps carry none of that burden while protecting the user's accumulated benchmark history — the application's core data.
**Enforced in:** `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`; `16_Engineering_Standards/` persistence standard.

### Single user, single machine, single window

There is no multi-user mode, no accounts, no server component, no concurrent access, and no second application window for the main shell. Detached chart and table views are the only additional windows.
**Reason:** the product serves one practitioner on one machine; concurrency and access control would be pure overhead.
**Enforced in:** `08_Cross_Cutting/08-A_architecture_principles.md`; `01_Main_Window/description.md`.

### No telemetry, no analytics, no network calls except to LLM providers

The application makes no outbound network request other than to the LLM and embedding providers the user has configured. It collects no usage data and phones no home.
**Reason:** privacy is a core value of the local-LLM audience.
**Enforced in:** `12_Quality_and_NFRs/09_PRIVACY_POLICY.md`; `12_Quality_and_NFRs/02_SECURITY_MODEL.md`.

### No automatic update mechanism

The application makes no update check — not on startup, not on a schedule, and not on a user action. It fetches no remote version manifest, reads no update feed, and offers no UI affordance to check for, download, or apply updates. New versions are obtained by the user manually downloading the next release artifact from the project's GitHub Releases page and replacing the existing installation; the application data directory survives untouched (DD-36).
**Reason:** an auto-update channel would add a recurring outbound network call, a signing-key topology, and update-verification UI for a single-user local tool whose users already track releases out of band; removing it sharpens the no-telemetry guarantee and shrinks the attack surface.
**Enforced in:** `16_Engineering_Standards/08_CICD_AND_PACKAGING.md` §10; `13_Distribution_and_Release/02_INSTALLATION.md` (Updating); `08_Cross_Cutting/08-F_spec_issues_log.md` DD-36.

### No plugin or extension system

The application is a monolith. New providers, charts, evaluators, or task types are added by editing the codebase, not by loading third-party plugins at runtime.
**Reason:** a plugin API is a large, security-sensitive surface that the audience does not need.
**Enforced in:** `08_Cross_Cutting/08-A_architecture_principles.md` (single composition root).

### No internationalisation or localisation

The user interface, messages, and documentation are English only. There is no locale framework and no translated resources.
**Reason:** the audience is English-reading technical users; a localisation framework would not earn its cost.
**Enforced in:** `16_Engineering_Standards/` coding standards.

### No code signing, no notarisation, no paid developer accounts

Distributed binaries are unsigned. The application ships through ordinary file downloads. No paid Apple, Microsoft, or other developer account is used.
**Reason:** the project is a solo, no-budget effort; signing costs money and recurring administration.
**Enforced in:** `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`.

### No automated model management

The application does not download, install, update, quantize, or delete LLMs. It benchmarks whatever the user's configured providers already expose.
**Reason:** model lifecycle is the job of Ollama, LM Studio, and llama.cpp; duplicating it adds risk and scope.
**Enforced in:** `08_Cross_Cutting/08-E_interfaces_contracts.md` (Provider Registry contract).

### No mobile, web, or SaaS deployment

The application targets desktop operating systems (macOS, Windows, Linux) only. There is no browser, mobile, or hosted version.
**Reason:** the product depends on local hardware and local providers.
**Enforced in:** `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`.

### No onboarding wizard

On first launch the application creates its data directory and sensible defaults silently and opens ready to use. There is no multi-step setup wizard.
**Reason:** the audience is technical and prefers sensible defaults over guided setup.
**Enforced in:** `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md`.

### No placeholder or inactive UI

The interface contains no stubbed, dead, or "coming soon" elements. The hidden-vs-disabled rule is by **applicability, not duration** (SPEC-076): a control that is **not applicable** to the current mode or structure is **hidden** (e.g. the grading columns in a non-graded run, the performance matrix outside Synthetic Benchmark); a control that **is** applicable but is **gated by the current run/app state** is **shown disabled with a tooltip stating why**, regardless of how long that state lasts (e.g. the Settings action and the export buttons during an active run — disabled for the run's full duration, which may be hours; the Start button disabled until the selection is valid). "Not applicable → hidden; applicable-but-currently-unavailable → disabled-with-reason" is the dividing line; there are no inert placeholder controls either way.
**Reason:** placeholder UI erodes trust and confuses testers.
**Enforced in:** `08_Cross_Cutting/08-L_ui_standardization.md`.

### Mouse-only operation; no keyboard shortcuts or required keyboard paths

The application is operated by mouse only — through buttons, widgets, menu entries, and toolbar controls. There are no **custom** keyboard shortcuts, no accelerators, no Ctrl/Cmd/Alt key bindings, no F-keys, no mnemonics, and no required keyboard-navigation paths. The one permitted exception is the host toolkit's **built-in modal-dialog defaults** — pressing Enter activates a dialog's default button and pressing Esc triggers its Cancel/Close — which count as the "incidental focus/host-toolkit behaviour" this constraint allows (D-R-07). These defaults are never the *only* way to do anything: every dialog can always be dismissed by clicking the close (X) or the cancel button, and primary buttons are activated by clicking. Throughout the rest of this specification, "there are no keyboard shortcuts or accelerators" means **no custom** shortcuts/accelerators; it does not forbid these toolkit modal defaults. The accessibility floor's release check is correspondingly a grep that **no custom shortcut/accelerator/mnemonic is registered** (`12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §10). Like the modal defaults, the toolkit's built-in `Tab`/`Shift+Tab` focus traversal is incidental host-toolkit behaviour that is **never actively suppressed** (no `NoFocus` policy on interactive controls — DD-52); it is not a supported or tested input path.
**Reason:** a strictly click-driven UI removes a whole class of platform-specific bindings, accessibility commitments around tab order, and undocumented hidden affordances; every action a user can take is visible on screen.
**Enforced in:** `08_Cross_Cutting/08-L_ui_standardization.md`; `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md`.

### Fixed technology stack

The application is built with Python 3.13 and PySide6 (Qt Widgets). The toolchain (`uv`, `ruff`, `mypy --strict`, `pytest`/`pytest-qt`) and the architecture (hexagonal, feature-first modules, manual composition root) are binding.
**Reason:** a fixed stack lets the entire specification be concrete and lets architecture be enforced mechanically.
**Enforced in:** `16_Engineering_Standards/`.

### The judge produces no numeric score; the final verdict is binary

The LLM judge returns PASS or FAIL with an explanation and never a number. The only numeric quality figure is the cosine similarity ("Cosine Score"). A completed task's verdict is binary — PASS or FAIL — never an "unknown" outcome.
**Reason:** numeric judge scores are unstable and invite false precision; a binary verdict is what the user acts on.
**Enforced in:** `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md`; `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`.

## 2. Soft constraints

Soft constraints are out of scope for this release but could be reconsidered later. They are recorded so that contributors do not assume they were overlooked.

### Accessibility beyond the defined floor

The application meets a defined accessibility floor — WCAG AA colour contrast, visible focus indicator, sufficient click-target size, colour-independent state encoding, and reduced-motion respect — but does not pursue screen-reader optimisation or assistive-technology certification.
**Status:** revisitable. See `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md`.

### In-application log viewer

Application (system) logs are written to files for inspection outside the application. There is no in-application application-log viewer. (The benchmark **event log** shown live in the Progress panel is a separate, in-scope feature.)
**Status:** revisitable. See `12_Quality_and_NFRs/03_OBSERVABILITY.md`.

### Signed and notarised distribution

If the application's audience grows substantially, code signing and notarisation could be reconsidered to remove the operating-system security prompts.
**Status:** revisitable. See `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`.

### Visual-regression (pixel-diff) UI testing

UI testing verifies behaviour and structure, not pixel-level appearance. Screenshot-diff regression testing is not part of the test strategy.
**Status:** revisitable. See `16_Engineering_Standards/` testing standard.
