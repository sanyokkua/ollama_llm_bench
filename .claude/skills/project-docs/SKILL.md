---
name: project-docs
description: Documentation standards for Ollama LLM Bench — README structure, ADR format, diagram standards, inline comment rules, and documentation lifecycle. Use when writing or updating project documentation.
paths: docs/**/*.md, *.md
allowed-tools: Read, Write, Edit
---

# Project Documentation Standards — Ollama LLM Bench

## Critical Rules

- MUST NOT include commented-out code under any circumstance — use Git history
- MUST update documentation in the same commit as the corresponding code change
- MUST delete stale documentation immediately upon discovery
- MUST NOT duplicate content from another document — link to the authoritative source
- Comments explain **why**, not **what** — never paraphrase what the code literally does

---

## Documentation Philosophy

- Document **why** code exists and **what** its public contract is — never narrate implementation steps
- Before writing a comment, ask: can a rename or refactor make this self-evident?
- Inline comments explain intent, warn about non-obvious edge cases, or reference business rules

```python
# QThreadPool max count set to 1 — serial execution avoids Ollama server
# contention when running inference for multiple models sequentially.
thread_pool.setMaxThreadCount(1)
```

---

## README Structure

The repository `README.md` MUST contain these sections in order:

| # | Section | Content |
|---|---------|---------|
| 1 | **What Is This?** | Type (Desktop App), what it does, what problem it solves |
| 2 | **How Does It Fit In?** | Mermaid diagram: triggers, outputs, consumers |
| 3 | **Tech Stack** | Table of components and technologies |
| 4 | **Quick Start** | Max 10 lines of shell commands |
| 5 | **Documentation** | Table linking to `docs/` subdocuments |

MUST NOT exceed 300 lines. Move details to `docs/`.

---

## Architecture Decision Records (ADRs)

### When to Create an ADR

- A technology, framework, or major library is adopted or replaced
- A system boundary or data-flow topology changes
- A decision constrains future technical choices
- Trade-off analysis is needed that future developers will question

### Format and Storage

Store in `docs/adr/` as `NNNN-short-title.md` (e.g., `0001-use-pyqt6-for-ui.md`).

Every ADR MUST contain:

| # | Section | Requirement |
|---|---------|------------|
| 1 | **Title** | Short descriptive title prefixed with sequence number |
| 2 | **Status** | `Proposed` / `Accepted` / `Deprecated` / `Superseded by ADR-NNNN` |
| 3 | **Date** | `YYYY-MM-DD` of the decision |
| 4 | **Context** | The situation that forced a decision; state neutrally |
| 5 | **Decision** | The decision taken, stated clearly and directly |
| 6 | **Consequences** | Both positive and negative anticipated outcomes |
| 7 | **Alternatives** | Other options evaluated and why rejected |

MUST NOT delete ADRs — mark superseded as "Deprecated" with link to successor.

---

## Diagram Standards

- MUST use **Mermaid.js** for all diagrams — MUST NOT commit PNG/JPEG for anything expressible as Mermaid
- Store diagram source alongside the documents they illustrate
- See `/create-mermaid-diagrams` for Mermaid syntax rules and common errors

Required diagrams for this project:
1. **System context diagram** — the app, Ollama server, SQLite, benchmark dataset
2. **Data flow diagram** — benchmark execution pipeline (inference → judging → results)

---

## Inline Comment Rules

- Inline comments MUST explain reasoning or intent — never restate what the code does
- Use `#` for single-line explanations
- Docstrings (`"""`) are for public API contract only — see `/python-developer` for docstring standards

### TODO / FIXME / HACK Format

```python
# TODO(owner): description [TICKET-ID]
# FIXME(owner): description [TICKET-ID]
# HACK(owner): description [TICKET-ID]
```

- `FIXME` and `HACK` MUST NOT exist without a linked ticket
- `TODO` without a ticket MUST be resolved or ticketed within 30 days

---

## Documentation Lifecycle

- All source documentation MUST be in the same repository as the code
- When code behavior changes, update corresponding documentation in the **same commit**
- When code is deleted, delete its documentation in the same commit
- Reviewers MUST verify: new/changed public APIs have complete docs, no orphaned docs remain

---

## Writing Style

- Use imperative mood and active voice: "Return the user ID." — not "Returns the user ID."
- State numeric thresholds explicitly — never "a few", "some", "reasonable"
- Use real field names in examples, not `foo`/`bar`
- PREFER tables for structured data over bullet lists
- PREFER one sentence per line for cleaner Git diffs

---

## Anti-Duplication

- Every discrete piece of information MUST have exactly one canonical location
- If the same information exists in two places, choose one canonical source and link the other
- MUST NOT copy-paste content between documents
