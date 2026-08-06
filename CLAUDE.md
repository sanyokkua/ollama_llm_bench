@AGENTS.md

<!-- AGENTS.md is the single source of truth. Add rules there, not here.
     This file exists only because Claude Code does not read AGENTS.md natively.
     Below this line: Claude-Code-specific mechanics only (skills, hooks, subagents). -->

Claude-Code-only mechanics, with no meaning under Codex:

- `.claude/hookify.*.local.md` — PreToolUse rules that enforce several of AGENTS.md's
  Non-negotiables by blocking the tool call outright, not just advising against it.
- `.claude/agents/*.md` — the subagent roster Claude Code loads for the Agent tool
  (`investigator`, `architect`, `coder`, `tester`, `debugger`, `docs-writer`,
  `spec-conformance-reviewer`). Mirrored for Codex as generated `.codex/agents/*.toml` — edit
  the `.claude/` source, then run `python3 scripts/sync-agent-files.py --apply`.
- `.claude/rules/*.md` — path-scoped conventions, loaded automatically when a matching file is
  read; not reproduced in AGENTS.md.

## Context management

When compacting, preserve: the current phase/story being worked, the list of modified file
paths, any outstanding `mypy`/`ruff`/`import-linter` failures by file, current `pytest` failure
count and names, and any `# type: ignore[code]` decisions made and why.
