---
description: "Repository documentation standards — README structure, ADRs, Mermaid diagrams, CODEOWNERS, changelog"
globs: "*.md,docs/**/*.md,CODEOWNERS"
alwaysApply: false
---

# Repository Documentation Standards

## Critical Rules

- MUST create `README.md` at root answering Five Questions: What Is This?, How Does It Fit In?, Tech Stack, Quick Start, Documentation
- MUST NOT exceed 300 lines in `README.md` — move details to `docs/`
- MUST include a Mermaid diagram showing system context in `README.md`
- MUST classify project as **Desktop/Mobile App**
- MUST create `CODEOWNERS` file at root
- MUST use Mermaid.js for all diagrams — MUST NOT commit PNG/JPEG for anything expressible as Mermaid
- MUST update documentation in every PR that changes behavior
- MUST organize `docs/` by audience concern, not file type
- MUST use strict heading hierarchy — never skip levels
- MUST specify language in fenced code blocks
- MUST use imperative voice ("Run the command", "Create the file")
- MUST NOT duplicate information across files

## README Structure

```markdown
# Project Name

## What Is This?
**Type:** Desktop/Mobile App

[One paragraph: what it does, what problem it solves]

## How Does It Fit In?
[Mermaid diagram: triggers, outputs, consumers]

## Tech Stack
| Component | Technology |
|-----------|-----------|
| Language  | Python 3.13+ |
| UI        | PySide6 |

## Quick Start
[Max 10 lines of shell commands]

## Documentation
| Topic | Link |
|-------|------|
| Architecture | [docs/...] |
```

## Desktop/Mobile App Required Docs

**MUST**: `README.md`, `CODEOWNERS`, `CHANGELOG.md`, `architecture/overview.md`, `architecture/data-model.md`, `development/local-setup.md`, `development/project-structure.md`, `development/testing.md`, `operations/deployment.md`, `usage/getting-started.md`

**PREFER**: `LLM.md`, `CONTRIBUTING.md`, `architecture/adrs/`, `architecture/data-flow.md`, `development/ci-cd-pipeline.md`, `reference/glossary.md`

## `docs/` Organization

| Section | Reader's Question |
|---|---|
| `architecture/` | "What does this system look like?" |
| `development/` | "How do I build, test, modify?" |
| `operations/` | "How do I deploy and troubleshoot?" |
| `reference/` | "What is the exact specification?" |
| `usage/` | "How do I use this?" |

## Architecture Decision Records

Store in `docs/adr/` as `NNNN-short-title.md`. Required sections:

| Section | Obligation |
|---|---|
| Title | MUST |
| Status | MUST — Proposed, Accepted, Deprecated, Superseded by ADR-NNNN |
| Date | MUST — YYYY-MM-DD |
| Context | MUST |
| Decision | MUST |
| Consequences | MUST |
| Alternatives | SHOULD |

MUST NOT delete ADRs — mark superseded as "Deprecated" with link.

## Changelog

- MUST follow [Keep a Changelog](https://keepachangelog.com/) format
- Entries grouped under: Added, Changed, Deprecated, Removed, Fixed, Security
- Entries under `[Unreleased]` until release tagged
- Generate entry when: public API added/changed/deprecated/removed, bug fix, security patch
- MUST NOT generate for: internal refactors, CI changes, dev-dependency updates

## Writing Standards

- MUST use imperative mood in active voice
- MUST be specific ("Use `snake_case`") — MUST NOT be vague ("use good naming")
- MUST state exact versions in setup docs
- MUST use real field names, not `foo`/`bar`
- PREFER tables for structured data over bullet lists
- PREFER one sentence per line for cleaner Git diffs
- PREFER limiting code blocks to 3-7 lines
