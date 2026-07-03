# Personas

**Status:** Draft
**Owner:** human-reviewer
**Audience:** human, architect
**Last Updated:** 2026-06-06
**Cross-references:** 00_Foundation/03_VISION.md; 00_Foundation/05_CONSTRAINTS.md

This document defines the people Ollama LLM Bench is built for. When two requirements conflict, the architect resolves the conflict in favour of the primary persona. The anti-personas at the end state, explicitly, who the application is not for.

---

## Table of Contents

1. Persona 1 — The local-LLM practitioner
2. Persona 2 — The applied AI builder
3. Persona 3 — The model-curious power user
4. Anti-personas

---

## 1. Persona 1 — The local-LLM practitioner (primary)

### Profile

A software developer or ML-adjacent engineer who runs models locally through Ollama, LM Studio, or llama.cpp on a personal workstation or laptop. They are comfortable with the command line, with YAML, and with reading technical tables and charts. They run models locally for cost, privacy, and offline reasons, and they switch models often as new quantizations and releases appear. They work alone on this task; the application is a single-user desktop tool for them.

### Goals

- Decide which locally-installed model to use for a given kind of work.
- Quantify the speed cost of a larger or higher-quality model versus a smaller one.
- Understand how quantization level affects both speed and answer quality.
- Re-run the same benchmark after changing hardware, drivers, or model versions and compare.
- Keep all evaluation data on their own machine.

### Tools they use today

- Ollama / LM Studio / llama.cpp command-line interfaces and built-in chat UIs.
- Ad-hoc shell scripts and stopwatch timing.
- Public benchmark leaderboards (which do not reflect their hardware or tasks).
- Spreadsheets where they paste numbers by hand.

### Frustrations

- No tool measures their models on their hardware against their tasks.
- Manual timing is imprecise and not repeatable.
- Comparing quality across models is subjective and undocumented.
- Two providers can expose the "same" model with different performance, and nothing makes that distinction visible.

### Primary use cases

1. The practitioner has just installed three new quantizations of a model family. They open the application, select all three across their Ollama provider, choose Synthetic Benchmark mode with a spread of prompt and output sizes, and start the run. Five minutes later they read a ranked table of time-to-first-token and tokens-per-second and decide which quantization is worth its memory footprint.
2. The practitioner maintains a folder of YAML task files representing the coding and text work they actually do. They run a Graded Benchmark over those files across two models, then open the Details tab, sort by verdict, and read the judge's reasoning on the tasks one model failed and the other passed.
3. A run of forty tasks is partway done when the practitioner needs the RAM for something else. They press Pause, the in-flight task finishes and is saved, and the run halts cleanly. Hours later they reopen the application, find the run in the Resume list, and continue it from where it stopped.

---

## 2. Persona 2 — The applied AI builder

### Profile

A developer integrating an LLM into a product or internal tool. They care less about raw speed leaderboards and more about whether a given model reliably produces correct, well-formed output for the specific prompts their product issues. They author detailed task files with golden answers and grading criteria, and they treat the judge analysis as evidence for a model-selection decision they must justify to themselves or a small team.

### Goals

- Validate that a candidate model meets a quality bar on a representative task set.
- Detect quality regressions when they change models or quantizations.
- Produce exportable evidence (tables, charts, written analysis) for a decision record.
- Compare a cheap local model against a cloud model on the same tasks.

### Tools they use today

- Provider SDKs and their own evaluation scripts.
- Notebooks with hand-written assertion checks.
- Cloud provider playgrounds.

### Frustrations

- Writing and maintaining bespoke evaluation harnesses is repetitive overhead.
- Keyword checks alone are too brittle; pure LLM-judge checks alone are hard to trust.
- Results are hard to share or revisit later.

### Primary use cases

1. The builder writes a YAML task file with exact and forbidden keywords, a golden answer, and pass/fail criteria for each task, using the Task Editor. They run Graded Benchmark across a local model and a cloud model and compare pass rates on the Summary tab.
2. The builder exports the Details table and the judge analysis to files and attaches them to their own decision notes.

---

## 3. Persona 3 — The model-curious power user

### Profile

An enthusiast who follows the local-LLM space closely, enjoys measuring things, and wants a polished desktop tool rather than scripts. They may not author elaborate task files but will happily run the Synthetic Benchmark and Task Benchmark modes and read the charts.

### Goals

- Explore how models behave on their hardware.
- Generate charts worth sharing.
- Have a dependable, good-looking tool that does not require setup beyond pointing it at their providers.

### Frustrations

- Scripts feel fragile and unrewarding.
- They want immediate, visual feedback.

### Primary use cases

1. The power user runs a Synthetic Benchmark and browses the charts, detaching a chart into its own window and exporting it as an image.
2. They run a Task Benchmark over the bundled task set to see timing on real prompts without configuring grading.

---

## 4. Anti-personas

The application is explicitly **not** built for the following, and requirements that serve only them are rejected:

- **Teams and organisations.** There is no multi-user mode, no shared server, no accounts, and no concurrent access. The application is single-user and single-machine.
- **Production monitoring.** It is not a service-level monitoring or alerting tool. It runs benchmarks on demand; it does not watch a live system.
- **Non-technical users.** The application assumes familiarity with LLM providers, models, YAML, and reading technical tables. It does not provide a guided onboarding wizard.
- **Model trainers / fine-tuners.** It evaluates inference behaviour only. It does not train, fine-tune, or quantize models.
- **Mobile and web users.** It is a desktop application for macOS, Windows, and Linux only.
