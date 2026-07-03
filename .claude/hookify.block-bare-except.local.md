---
name: block-bare-except
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/.*\.py$
  - field: content
    operator: regex_match
    pattern: except\s*:
action: block
---

**Bare `except:` detected.**

Catch only specific exception types — never a bare `except:` and never `except Exception: pass`.
Every error in this app should be an instance of the categorized error taxonomy
(`.claude/skills/error-taxonomy-and-redaction/SKILL.md`,
`.claude/rules/error-handling-standard.md`). If you truly need a last-resort handler at a
process boundary, catch a specific, named exception type and either log it or re-raise it —
never both, never silently.
