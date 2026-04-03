---
name: test-file
description: Run a specific test file or single test function with full traceback output and root cause analysis on failure.
allowed-tools: Read, Bash, Grep
---

## Usage

```
/test-file tests/unit/services/test_sq_lite_data_api.py
/test-file tests/unit/services/test_sq_lite_data_api.py::test_create_run_stores_correct_fields
```

## Execution

```bash
uv run pytest $ARGUMENTS -v --tb=long --no-header -p no:warnings
```

Using `--tb=long` here (unlike the default `--tb=short`) — full traceback is necessary for root cause analysis on a specific failing test.

## On Failure: Required Steps

1. **Show the complete pytest output** — do not truncate
2. **Identify root cause** — read the assertion and traceback; do not stop at the surface message
3. **Read both files**:
   - The failing test file (understand what it expects)
   - The implementation file under test (understand what it does)
4. **Identify the divergence** — mismatch in contract, wrong mock setup, incorrect assertion, or genuine bug
5. **Propose a fix** with exact `file_path:line_number` references

## On Pass

Report one line: "N tests passed in Xs"

## Common Failure Patterns in This Project

| Pattern | Likely Cause |
|---------|-------------|
| `AttributeError: Mock object has no attribute` | Mock created without `spec=` — add `spec=ConcreteClass` |
| `AssertionError` on signal emission | EventBus mock not called — check signal connection in controller |
| `TypeError: argument of type 'NoneType' is not iterable` | Missing fixture or None returned by mock |
| Import error on test file | Circular import or missing `__init__.py` in new package |
| `sqlite3.OperationalError` in integration test | Database file not cleaned up — use `tmp_path` fixture |
