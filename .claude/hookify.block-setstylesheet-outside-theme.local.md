---
name: block-setstylesheet-outside-theme
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/ollama_llm_bench/(?!ui/theme/).*\.py$
  - field: content
    operator: contains
    pattern: "setStyleSheet("
action: block
---

**`setStyleSheet(` called outside `ui/theme/`.**

`src/ollama_llm_bench/ui/theme/` is the single styling authority in this app — the only place
allowed to call `setStyleSheet()` or assemble a stylesheet from raw design tokens. Widgets must
reference token ROLE NAMES via Qt dynamic properties instead. See
`.claude/skills/pyside6-spec-ui/SKILL.md` and `.claude/rules/pyside6-app-development.md`.
