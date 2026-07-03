---
name: block-dataclass-cross-boundary
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/ollama_llm_bench/(backend|adapters)/(?!.*_internal/).*\.py$
  - field: content
    operator: regex_match
    pattern: "@dataclass"
action: block
---

**`@dataclass` used outside `_internal/` in a backend/adapters module.**

Every cross-boundary data structure in this project must be a
`msgspec.Struct(frozen=True, kw_only=True, gc=False)`, not `@dataclass`. `@dataclass` is
permitted only for a type that is strictly private to one module's own `_internal/` package
and never crosses that module's boundary.

See `.claude/skills/msgspec-domain-modeling/SKILL.md` before proceeding. If this really is a
strictly-private `_internal/`-confined type, move the file under that module's `_internal/`
directory rather than overriding this rule.
