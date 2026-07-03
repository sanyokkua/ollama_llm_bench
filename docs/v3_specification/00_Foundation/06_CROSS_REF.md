# Cross-Reference Index

**Status:** Draft
**Owner:** architect
**Audience:** all
**Last Updated:** 2026-06-06
**Cross-references:** all folders of this specification

This document is a mechanical lookup table. It maps every folder to its purpose, maps each major topic to the document that contracts it, and provides a "given X, find Y" matrix so that any reader can navigate from a question to the authoritative answer quickly. Every reference in this specification points to a file inside `App_Specification_Ollama_Bench_Final/`; there are no external references.

---

## Table of Contents

1. Folder-to-purpose map
2. Topic-to-document map
3. Story, ADR, and traceability references
4. How to find...

---

## 1. Folder-to-purpose map

| Folder | Purpose |
|---|---|
| `00_Foundation/` | Orientation: reading guide, glossary, vision, personas, constraints, this index. |
| `01_Main_Window/` | The application shell — menu bar, workspace switcher, status bar, window lifecycle. |
| `02_New_Benchmark_Widget/` | Benchmark workspace, left panel, New tab: configuring and starting a run; per-mode specifics. |
| `03_Resume_Benchmark_Widget/` | Benchmark workspace, left panel, Resume tab: listing, resuming, retrying, renaming, deleting, cloning, exporting runs. |
| `04_Progress_Widget/` | Benchmark workspace, centre panel: live run progress, counters, current task, event log. |
| `05_Result_Widget/` | Benchmark workspace, right panel: results across Summary, Details, Charts, Run Analysis tabs. |
| `06_Settings_Dialog/` | The Settings dialog (Providers and General tabs) and its sub-dialogs. |
| `07_Common_Dialogs/` | Shared confirmation and summary dialogs (rename, run summary, resume summary, retry selection, error, about). |
| `08_Cross_Cutting/` | App-wide contracts: architecture, UI standards, platform specifics, service interfaces, data model, feature flags, app modes, edge cases, event catalog, settings hierarchy, lifecycle, benchmark state machine, design tokens, decision log, and the new contract documents (implementation pointers, persistence schema, judge protocol, event payloads). |
| `09_Task_Editor/` | The Task Editor workspace and the authoritative task-file field reference. |
| `10_Domain_and_Data/` | Domain model, DTOs and enums, persistence schema, YAML task format, export/import formats, file layout, redaction patterns. |
| `11_Services_and_Algorithms/` | The service inventory and every non-trivial algorithm contract. |
| `12_Quality_and_NFRs/` | Non-functional requirements: security, observability, error recovery, concurrency guarantees, data integrity, resource limits, accessibility floor, privacy. |
| `13_Distribution_and_Release/` | Packaging, platform support, installation, unsigned distribution, first-run, versioning, bug reporting and diagnostics, uninstall. |
| `14_Process_and_Traceability/` | Module inventory, story format, traceability, ADR format, acceptance-criteria patterns, edge-case-to-test mapping. |
| `15_Risks_and_Open_Questions/` | The risk register, genuinely deferred questions, and proposed ADRs. |
| `16_Engineering_Standards/` | Project structure, toolchain, coding standards, module framework, concurrency standard, error-handling standard, CI/CD, packaging — the engineering rules the whole specification assumes. |

## 2. Topic-to-document map

| Topic | Authoritative document(s) |
|---|---|
| Vocabulary / definitions | `00_Foundation/02_GLOSSARY.md` |
| Non-goals / constraints | `00_Foundation/05_CONSTRAINTS.md` |
| Layering, module boundaries, composition root | `08_Cross_Cutting/08-A_architecture_principles.md`; `16_Engineering_Standards/` |
| Service interfaces / contracts | `08_Cross_Cutting/08-E_interfaces_contracts.md`; `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` |
| Domain entities and relationships | `10_Domain_and_Data/01_DOMAIN_MODEL.md` |
| DTOs and enums | `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` |
| Database schema (DDL) | `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`; `08_Cross_Cutting/08-O_persistence_schema.md` |
| Task-file YAML format | `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`; `09_Task_Editor/field_reference.md` |
| Run modes and what each shows | `08_Cross_Cutting/08-H_app_modes.md`; `02_New_Benchmark_Widget/mode_specifics/` |
| UI screen index, drawn states, and screen↔spec traceability | `08_Cross_Cutting/08-R_screen_index_and_traceability.md` |
| Benchmark pipeline and stages | `08_Cross_Cutting/08-B_benchmark_state_machine.md`; `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` |
| Evaluation: keyword, cosine, judge | `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`; `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md`; `08_Cross_Cutting/08-P_judge_protocol.md` |
| Event bus signals and payloads | `08_Cross_Cutting/08-J_event_bus_catalog.md`; `08_Cross_Cutting/08-Q_event_payload_schemas.md` |
| Feature flags / settings keys | `08_Cross_Cutting/08-G_feature_flags.md`; `08_Cross_Cutting/08-C_settings_hierarchy.md` |
| Edge cases | `08_Cross_Cutting/08-I_edge_cases.md` |
| Errors, retries, circuit breaker | `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`; `11_Services_and_Algorithms/18_RETRY_POLICY.md`; `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` |
| Concurrency model | `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`; `16_Engineering_Standards/` |
| Design tokens and theming | `08_Cross_Cutting/08-D_color_palette_and_typography.md` |
| Quality gates and non-functional requirements | `12_Quality_and_NFRs/` |
| Packaging and distribution | `13_Distribution_and_Release/`; `16_Engineering_Standards/` |
| Module list | `14_Process_and_Traceability/01_MODULE_INVENTORY.md` |

## 3. Story, ADR, and traceability references

- **Story format** — the template and frontmatter schema for implementation stories: `14_Process_and_Traceability/02_STORY_FORMAT.md`.
- **ADR format** — how Architecture Decision Records are written and superseded: `14_Process_and_Traceability/04_ADR_FORMAT.md`. Proposed ADRs awaiting acceptance live in `15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md`.
- **Traceability** — how the specification, stories, tests, and modules are linked and validated: `14_Process_and_Traceability/03_TRACEABILITY.md`.
- **Acceptance-criteria patterns** — `14_Process_and_Traceability/05_ACCEPTANCE_CRITERIA_PATTERNS.md`.
- **Edge-case-to-test mapping** — `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`.

## 4. How to find...

### The implementation contract for a behaviour described in a widget folder

1. Open the widget folder's `description.md` and read its front-matter cross-references.
2. Follow to the named `08_Cross_Cutting/` contract or `11_Services_and_Algorithms/` algorithm.
3. For data structures, follow to `10_Domain_and_Data/`.

### The engineering rule a module must follow

Open `16_Engineering_Standards/`. It contains the project structure, module framework, coding standards, concurrency standard, error-handling standard, and CI/CD rules. The widget folder's `implementation_structure.md` names the specific rules that apply.

### Every place a feature flag is consumed

Open `08_Cross_Cutting/08-G_feature_flags.md`; each flag entry lists its consumers.

### The test pattern for an edge case

Open `08_Cross_Cutting/08-I_edge_cases.md` for the edge case, then `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` for the test type and pattern.

### Why a decision was made

Open `08_Cross_Cutting/08-F_spec_issues_log.md` for resolved design decisions, and `15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md` / `14_Process_and_Traceability/04_ADR_FORMAT.md` for architecture decisions.
