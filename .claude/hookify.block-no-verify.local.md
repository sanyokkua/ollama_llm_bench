---
name: block-no-verify
enabled: true
event: bash
pattern: git\s+commit\b[^\n]*(--no-verify|\s-n(\s|$))|git\s+push\b[^\n]*(--force\b|\s-f(\s|$))
action: block
---

**Attempt to bypass a git quality gate detected (`--no-verify`/`-n` on commit, or
`--force`/`-f` on push).**

Never bypass the pre-commit hook or force-push over shared history. If `pre-commit` is
reporting a failure, fix the underlying issue (see `.claude/hooks/precommit_from_hook.sh` and
`.pre-commit-config.yaml`) rather than skipping it. If you believe the check itself is wrong,
raise it with the user before overriding — see the "Never bypass quality gates" rule in
`CLAUDE.md`.
