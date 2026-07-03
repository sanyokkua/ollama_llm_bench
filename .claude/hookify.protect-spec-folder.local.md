---
name: protect-spec-folder
enabled: true
event: bash
pattern: (^|[;&|]\s*)(rm\b|git\s+rm\b)[^\n]*\bdocs/v3_specification\b
action: block
---

**Command targets `docs/v3_specification/` for deletion.**

The vendored specification is the single source of truth for this entire rewrite and must
never be modified or deleted by an automated session. If you genuinely need to do this
(e.g. a deliberate, human-approved spec relocation), ask the user to run the command manually
outside Claude Code rather than overriding this rule.
