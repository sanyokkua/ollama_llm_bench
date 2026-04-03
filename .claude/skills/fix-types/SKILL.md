---
name: fix-types
description: Systematically fix all Mypy strict-mode type errors — group errors by file, fix each file completely, verify clean with per-file mypy, finish with full mypy run then pytest.
allowed-tools: Read, Edit, Bash, Grep, Glob
---

## Process

```bash
# Step 1: Get the full error list
uv run mypy src/ --no-error-summary --show-error-codes --show-column-numbers
```

Group errors by **file** then by **error code** within each file. Fix one file at a time.

**For each file with errors:**
1. Read the entire file first — never patch blindly
2. Fix all errors in that file before moving on
3. Verify: `uv run mypy src/path/to/file.py --no-error-summary --concise-errors`
4. Confirm zero errors before proceeding to the next file

```bash
# Step 5: Final full check
uv run mypy src/

# Step 6: Confirm tests still pass
uv run pytest -q --tb=short --no-header
```

## Rules

- **Never** use bare `# type: ignore` — always: `# type: ignore[error-code]  # reason: <why>`
- **Never** change function signatures solely to avoid type errors — fix the call site or the type hint
- **Prefer** proper annotations over suppressions for all new code
- When an untyped third-party library causes errors, add to `[[tool.mypy.overrides]]` in `pyproject.toml`

## Common Mypy Strict Errors in This Project

| Error Code | Typical Cause | Fix Pattern |
|------------|--------------|-------------|
| `[no-untyped-def]` | Missing return type or param type | Add `-> ReturnType` and param annotations |
| `[arg-type]` | Passing wrong type to function | Check ABC/Protocol signature in `core/interfaces.py` |
| `[return-value]` | Returning wrong type | Align return type with declared type |
| `[attr-defined]` | Attribute not on type | Verify class definition; may need cast or guard |
| `[override]` | Override signature mismatch | Match parent ABC signature exactly |
| `[misc]` | Various — check error message | Read specific error; often missing `@override` |

## Dependency Order

Fix `core/` errors before `services/` — ABCs cascade downward.
