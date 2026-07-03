---
name: block-secret-literal
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!.*/tests?/).*$
  - field: content
    operator: regex_match
    pattern: (sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9\-]{20,}|AIza[A-Za-z0-9_\-]{30,}|gh[po]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})
action: block
---

**Literal secret-shaped value detected.**

This project stores credentials as an environment-variable NAME only (e.g. `OPENAI_API_KEY`),
never a literal key value, never a wrapped `${VAR}` reference. A value that isn't a valid
env-var name is rejected inline at entry in the real application's Settings UI and import path —
the same discipline applies here. See `.claude/skills/secrets-and-provider-config/SKILL.md`.

If this is a genuine false positive (e.g. a redaction-pattern test fixture deliberately
containing a fake-shaped key), move it under a `tests/` directory, which this rule excludes.
