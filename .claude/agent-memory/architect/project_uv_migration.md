---
name: Poetry to UV migration — decision and state
description: Architectural decision to migrate from poetry-core to hatchling+uv, including pyproject.toml shape and dataset packaging constraint
type: project
---

**Decision (2026-04-03):** Migrate build backend from `poetry-core` to `hatchling`, package manager from `poetry` to `uv`, dev deps from `[tool.poetry.group.dev.dependencies]` to PEP 735 `[dependency-groups]`.

**Why:** Project rules explicitly target UV+hatchling. Poetry syntax in `dependencies` (`"pkg (>=x,<y)"`) is rejected by `uv`. `uv.lock`, `.python-version`, `.editorconfig`, `.gitattributes` were all absent.

**Key constraints discovered:**
- Dataset YAML files at `src/ollama_llm_bench/dataset/*.yaml` must be included in the wheel. Poetry handled this via `[tool.poetry].include`. With hatchling the equivalent is `[tool.hatch.build.targets.wheel.force-include]`.
- `pyright` was retained in `[dependency-groups]` dev (not dropped) because `scripts/ai-check.sh` calls `uv run pyright src/` and removing it silently breaks the local dev workflow.
- The full clean migration (Option B) was chosen over a minimal patch to avoid leaving dead Poetry sections that confuse tooling.

**How to apply:** When touching pyproject.toml or build config in future sessions, the expected shape is hatchling + `[dependency-groups]` — never re-introduce `[tool.poetry.*]` sections.
