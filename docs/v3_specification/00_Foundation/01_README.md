# Specification — Reading Guide

**Status:** Draft
**Owner:** architect
**Audience:** all
**Last Updated:** 2026-06-06
**Cross-references:** every folder of this specification; `00_Foundation/02_GLOSSARY.md`; `00_Foundation/05_CONSTRAINTS.md`; `00_Foundation/06_CROSS_REF.md`

This is the single landing page for the **Ollama LLM Bench** specification. It defines what the specification is, how it is organised, and the order in which each kind of reader should consume it. Start here, then continue to `02_GLOSSARY.md`.

---

## Table of Contents

1. What this spec is
2. What this spec is not
3. The application in one paragraph
4. Folder structure
5. How to read by role
6. Conventions
7. Related material inside this specification

---

## 1. What this spec is

This specification is a **complete, implementation-ready definition** of the Ollama LLM Bench desktop application. It is written so that an AI implementation agent and human developers can build the application end to end without consulting any other document. Every UI surface, every service contract, every data structure, every state machine, every algorithm, every edge case, and every quality requirement is contained within this folder.

The specification is **self-contained**. It references no file or folder outside `App_Specification_Ollama_Bench_Final/`. Engineering standards, project structure, and tooling are defined inside it (folder `16_Engineering_Standards/`).

The specification targets a fixed technology stack: **Python 3.13 and PySide6 (Qt Widgets)**, built with `uv`, checked with `ruff` and `mypy --strict`, tested with `pytest` and `pytest-qt`. The stack is binding and is defined in folder `16_Engineering_Standards/`.

## 2. What this spec is not

- It is not a user manual. Its tone describes application behaviour, not how to operate the app. End-user-facing material is confined to folder `13_Distribution_and_Release/`.
- It is not source code. It defines *what* every component does and the public contract it exposes — not the line-by-line implementation. Algorithms and logic are described where useful; concrete code is not.
- It is not a record of any prior work. The application is specified as a new product. There is no version history, no migration story, and no comparison to earlier attempts.
- It is not a backlog. Risks and any genuinely deferred questions live in folder `15_Risks_and_Open_Questions/`; everything else in the specification is decided.

## 3. The application in one paragraph

Ollama LLM Bench is a single-window, single-user desktop application that benchmarks Large Language Models running locally (Ollama, LM Studio, llama.cpp) or in the cloud (OpenAI, Anthropic, Gemini, Azure). The user configures providers and models, authors benchmark task files, and starts a **benchmark run** in one of three modes — Synthetic Benchmark (synthetic prompts measuring speed), Task Benchmark (real task files, timing only), or Graded Benchmark (real task files plus a batched evaluation pipeline that grades each response by keyword, cosine similarity, and an LLM judge). The user watches progress live, can pause, resume, stop, retry, or continue runs, and inspects results across summary tables, detailed task views, charts, and a judge-written narrative analysis. Everything is stored locally in an embedded SQLite database. There is no telemetry and no multi-user capability.

## 4. Folder structure

```
App_Specification_Ollama_Bench_Final/
├── 00_Foundation/            orientation: reading guide, glossary, vision, personas, constraints, cross-reference
├── 01_Main_Window/           the application shell and workspace switcher
├── 02_New_Benchmark_Widget/  Benchmark workspace · left panel · New tab (+ per-mode specifics)
├── 03_Resume_Benchmark_Widget/ Benchmark workspace · left panel · Resume tab (run management)
├── 04_Progress_Widget/       Benchmark workspace · centre panel · live run progress
├── 05_Result_Widget/         Benchmark workspace · right panel · results (4 tabs)
├── 06_Settings_Dialog/       configuration dialog (Providers + General) and its sub-dialogs
├── 07_Common_Dialogs/        shared confirmation and summary dialogs
├── 08_Cross_Cutting/         app-wide contracts: architecture, modes, events, data model, edge cases
├── 09_Task_Editor/           the Task Editor workspace and the task-file field reference
├── 10_Domain_and_Data/       domain model, DTOs/enums, persistence schema, file formats
├── 11_Services_and_Algorithms/ service inventory and every non-trivial algorithm
├── 12_Quality_and_NFRs/      security, observability, error recovery, concurrency guarantees, data integrity, resource limits, accessibility, privacy
├── 13_Distribution_and_Release/ packaging, installation, updates, bug reporting and diagnostics (end-user facing)
├── 14_Process_and_Traceability/ module inventory, story/ADR formats, traceability, test mapping
├── 15_Risks_and_Open_Questions/ risk register and any genuinely deferred questions
└── 16_Engineering_Standards/ project structure, toolchain, coding standards, CI/CD, packaging
```

## 5. How to read by role

### Architect (drafting implementation notes)

1. `00_Foundation/01_README.md` — orient (this file).
2. `00_Foundation/02_GLOSSARY.md` — vocabulary.
3. `08_Cross_Cutting/08-A_architecture_principles.md` — the binding architecture.
4. `08_Cross_Cutting/08-E_interfaces_contracts.md` — service contracts.
5. The widget folder for the feature in hand (`01`–`07`, `09`).
6. `10_Domain_and_Data/01_DOMAIN_MODEL.md` — entity relationships.
7. `11_Services_and_Algorithms/` — the specific algorithms touched.
8. `16_Engineering_Standards/` — module framework and standards.

### Coder (implementing)

1. The relevant story (`14_Process_and_Traceability/02_STORY_FORMAT.md`).
2. `14_Process_and_Traceability/01_MODULE_INVENTORY.md` — the module being built.
3. The widget folder's `description.md`, `state_machine.md`, `implementation_structure.md`.
4. `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` if the work touches the database.
5. `11_Services_and_Algorithms/` files matching the modules.
6. `16_Engineering_Standards/` for layout, coding standards, error handling, concurrency.

### Tester (writing tests)

1. The story's acceptance criteria.
2. The widget folder's `description.md`.
3. `08_Cross_Cutting/08-I_edge_cases.md` — edge-case test ideas.
4. `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` — the pattern per edge case.
5. `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` — error scenarios.

### Human reviewer

1. `00_Foundation/03_VISION.md` — refresh intent.
2. `08_Cross_Cutting/08-F_spec_issues_log.md` — decisions made.
3. `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` — open risks.
4. The widget folder under review.

### End user

1. `13_Distribution_and_Release/02_INSTALLATION.md`
2. `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md`
3. `13_Distribution_and_Release/07_CRASH_REPORTING.md`
4. `09_Task_Editor/field_reference.md` — the task-file reference.

## 6. Conventions

- **File naming.** Foundation and numbered folders use a two-digit prefix (`01_README.md`). Cross-cutting documents use a letter suffix (`08-A_architecture_principles.md`). Widget folders use fixed file names (`description.md`, `state_machine.md`, `flow_diagram.md`, `mockup.html`, `implementation_structure.md`). Names are lowercase with underscores; never spaces.
- **Front-matter.** Every document opens with Status, Owner, Audience, Last Updated, Cross-references, a one-paragraph purpose, and a table of contents.
- **Status lifecycle.** `Draft` → `In Review` → `Accepted` → `Superseded by NNN`. A document is never deleted; an obsolete one is marked superseded.
- **Voice.** Imperative mood ("Display the menu bar"), specific over abstract ("the run logger does not propagate to root" not "logging is clean"), no marketing language.
- **Diagrams.** All technical diagrams (flow, state, sequence, entity-relationship, component) are **Mermaid**. All UI surfaces (windows, widgets, dialogs, in-app charts) are **HTML mockups**.
- **Contracts.** DTOs, enums, SQL DDL, regex patterns, and YAML examples appear in fenced code blocks using Python and SQL syntax.
- **Cross-references.** Every cross-reference points to a file inside this specification. There are no external references.

## 7. Related material inside this specification

- **Engineering standards, project structure, toolchain, CI/CD, packaging:** `16_Engineering_Standards/`.
- **Story format, ADR format, traceability:** `14_Process_and_Traceability/`.
- **Architecture, data model, event catalog, edge cases:** `08_Cross_Cutting/`.
- **Glossary of every term:** `00_Foundation/02_GLOSSARY.md`.
- **Hard and soft constraints (non-goals):** `00_Foundation/05_CONSTRAINTS.md`.
