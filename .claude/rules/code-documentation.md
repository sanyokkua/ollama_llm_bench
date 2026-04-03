---
description: "Python code documentation rules — Google-style docstrings, type hint synergy, module docstrings, TODO format"
globs: "src/**/*.py"
alwaysApply: false
---

# Python Code Documentation

## Critical Rules

- MUST document the **why** and the **public contract** — MUST NOT narrate what code does step-by-step
- MUST use **Google-style docstrings** (`Args:`, `Returns:`, `Raises:`)
- MUST use type hints on all signatures — MUST NOT duplicate type information inside docstrings
- MUST NOT include commented-out code under any circumstance
- MUST use **imperative mood** in summary lines ("Return", "Calculate") — NOT third-person ("Returns")
- MUST update documentation in the **same commit** as corresponding code changes
- MUST delete stale or orphaned documentation immediately

## Documentation Philosophy

Before writing any comment, exhaust this hierarchy:
1. Name it clearly — choose meaningful, descriptive names
2. Refactor for clarity — restructure until self-evident
3. Comment as a last resort — only after both prior options exhausted

Inline comments MUST explain **reasoning or intent**, MUST NOT describe what code literally does.

## Docstring Format

- MUST use triple double-quotes (`"""`) — single quotes forbidden
- One-liner: opening and closing `"""` on same line, end with period
- Multi-line: summary on same line as opening `"""`, blank line before body, closing `"""` on own line

### Required Section Order

```
Summary line                    (MUST)
Extended description            (MAY)
Args:                           (MUST — if parameters exist)
Returns: / Yields:              (MUST — if non-None return)
Raises:                         (MUST — if caller-catchable exceptions)
Note:                           (MAY)
Example:                        (SHOULD — for public API)
```

- `Args:` — describe meaning and constraints, NOT type (already in signature)
- `Returns:` — describe both success and failure/edge-case values
- `Raises:` — state specific trigger condition for each exception
- MUST NOT document internal system errors (`MemoryError`, `SystemError`)

## Documentation Obligation Levels

### Public API — Mandatory

| Component | Required Content |
|---|---|
| Modules (`.py` files) | Purpose, exported elements |
| Packages (`__init__.py`) | Package purpose, public API summary |
| Classes | Responsibility, public attributes, constructor args (in ONE location only) |
| Public functions/methods | Summary, Args, Returns, Raises, side effects |
| Constants | Business meaning |
| Enums | Class purpose + per-member business meaning |

### Private Code — Conditional

- SHOULD add docstring to private methods when: logic exceeds 15 lines, contains workaround/hack, called from multiple internal locations
- MAY omit for trivially simple private helpers (< 5 lines with obvious purpose)

### Explicitly Skipped

- Trivial property getters MAY omit docstring
- Standard dunder methods MAY omit unless behavior deviates from expectations
- Private functions under 5 lines with self-describing name MAY omit

## Type Hints & Docstring Synergy

- MUST NOT duplicate type info from signature inside docstring sections
- SHOULD document internal structure of complex types (`dict[str, Any]`, nested dicts) even when hint present

## TODO / FIXME / HACK Format

```
# TODO(owner): Description of work [TICKET-ID]
# FIXME(owner): Description of defect [TICKET-ID]
# HACK(owner): Description of workaround [TICKET-ID]
```

- `FIXME` MUST NOT exist without a ticket reference
- `HACK` MUST include rationale and ticket for removal
- Marker comments whose ticket is closed MUST be removed

## Prohibited Content

- MUST NOT restate what code already expresses through names and types
- MUST NOT include commented-out code
- MUST NOT duplicate `__init__` args in both class docstring AND method docstring
- MUST NOT copy-paste content between documents — link to authoritative source
- MUST NOT leave module files without module docstrings

## Writing Style

- MUST use imperative mood in active voice: "Return the user ID." not "Returns the user ID."
- Numeric thresholds MUST be stated explicitly, never qualitatively
