# Vision

**Status:** Draft
**Owner:** human-reviewer
**Audience:** human, architect
**Last Updated:** 2026-06-06
**Cross-references:** 00_Foundation/04_PERSONAS.md; 00_Foundation/05_CONSTRAINTS.md; 10_Functionality referenced throughout 01–05 widget folders

This one-page document states what Ollama LLM Bench exists to do, who it serves, and how success is measured. It exists to prevent scope creep: any proposed feature that does not serve this vision belongs in `15_Risks_and_Open_Questions/` or is rejected.

---

## Table of Contents

1. Problem statement
2. Who it is for
3. Primary value proposition
4. Success criteria
5. Non-goals
6. Time horizon

---

## 1. Problem statement

People who run Large Language Models on their own hardware cannot easily tell, before committing to a model, whether it is fast enough and good enough for their real work. Public leaderboards measure models on someone else's hardware and someone else's tasks. Ollama LLM Bench closes that gap: it measures the models the user actually has, on the hardware the user actually owns, against the tasks the user actually cares about — reporting both raw performance (latency, throughput) and answer quality (graded by keyword, similarity, and an LLM judge).

## 2. Who it is for

The application serves a small number of technically capable individuals who run local LLMs and want evidence-based model selection. The detailed personas — their goals, tools, and frustrations — are defined in `00_Foundation/04_PERSONAS.md`.

## 3. Primary value proposition

Ollama LLM Bench turns "which local model should I use?" from a guess into a measured, repeatable, side-by-side comparison the user runs in minutes on their own machine.

## 4. Success criteria

The product is successful when each of the following holds:

1. **Speed comparison is fast to obtain.** A user can compare at least five models on a Synthetic Benchmark run and read a ranked speed table within five minutes of opening the application, excluding model download and load time.
2. **Quality comparison is trustworthy.** A user can run a Graded Benchmark over their own task files and receive per-task PASS/FAIL verdicts plus a written analysis whose conclusions they can trace to specific keyword, cosine, and judge evidence on the Details tab.
3. **Long runs are safe.** A benchmark of any size can be paused, resumed, stopped, retried, or continued after an application restart without losing completed results and without leaving the application in a broken state.

## 5. Non-goals

Everything the application deliberately does not do is enumerated in `00_Foundation/05_CONSTRAINTS.md`. In summary: no multi-user or server deployment, no telemetry, no plugin system, no internationalisation, no automated model installation, and no paid or cloud-hosted components.

## 6. Time horizon

This specification defines the complete product. It is scoped as a single, coherent release with no planned successor at specification time. Should a future release be undertaken, it starts from a fresh installation — there is no in-place upgrade or data migration path (see `00_Foundation/05_CONSTRAINTS.md`).
