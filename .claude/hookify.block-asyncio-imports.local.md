---
name: block-asyncio-imports
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: src/.*\.py$
  - field: content
    operator: regex_match
    pattern: ^\s*(import\s+(asyncio|anyio|qasync)\b|from\s+(asyncio|anyio|qasync)\s+import)
action: block
---

**`asyncio`/`anyio`/`qasync` import detected.**

This project's backend is deliberately synchronous and Qt-free. There is no event loop
anywhere in the app besides the single Qt event loop in `__main__.py`. Background work runs as
blocking units on a `QThreadPool`-backed `TaskRunner`, orchestrated by one dedicated dispatcher
thread — see `.claude/skills/concurrency-and-cancellation/SKILL.md` and
`.claude/rules/concurrency-standard.md` before reintroducing any async primitive here.
