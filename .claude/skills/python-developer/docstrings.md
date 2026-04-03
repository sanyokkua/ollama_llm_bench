# Python Developer — Docstring Standards

Google-style docstring rules for Ollama LLM Bench. See [SKILL.md](SKILL.md) for general Python rules.

---

## Critical Rules

- MUST provide Google-style docstrings on every `public` class, method, and function
- Docstrings = contract documentation only (what, inputs, outputs, errors) — MUST NOT describe implementation details
- Implementation comments (`#`) = internal logic explanations
- MUST NOT write noise: no restating what code expresses, no empty `Args`/`Returns` entries
- MUST NOT use `:param:` or `:returns:` reST style — use Google style exclusively
- Delete stale documentation in the same commit as behavioral changes

---

## Block Structure

Order in every docstring:
1. Summary line (imperative verb phrase: "Retrieve all benchmark runs…")
2. Extended description (if needed, separated by blank line)
3. Sections: `Args`, `Returns`, `Raises`, `Note`, `Example`

Summary line rules:
- MUST NOT begin with "This method…", "This class…", "A…", or "The…"
- MUST be a complete sentence ending with a period
- MUST use imperative mood: "Retrieve the run." not "Retrieves the run."

---

## Section Rules

### Args
- MUST provide for every parameter; include constraints (nullability, range, valid values)
- MUST NOT leave empty or restate the parameter name
- Format: `name: Description starting with lowercase.`

```python
def inference(self, *, model_name: str, user_prompt: str) -> InferenceResponse:
    """Perform inference using the specified model.

    Args:
        model_name: Name of the model to use; must be a valid Ollama model.
        user_prompt: Input prompt; must not be empty.

    Returns:
        Response containing generated text and performance metrics.

    Raises:
        ConnectionError: If the Ollama server is unreachable.
    """
```

### Returns
- Every non-`None` returning function MUST have `Returns`
- Describe both success AND failure/empty states
- `Optional[T]`: "The X if found, or None if not found."
- Collection: "List of X; empty if none found."
- Boolean: "True if X, False otherwise."

### Raises
- MUST document all significant exceptions
- Every `Raises` entry MUST specify the **condition** that causes it

```python
"""
Raises:
    RuntimeError: If context has already been initialized.
    FileNotFoundError: If the dataset path does not exist.
"""
```

---

## Documentation Obligation Levels

| Component | Level |
|-----------|-------|
| Public classes | MUST — full docstring |
| Public methods | MUST — all applicable sections |
| ABCs / Protocols | MUST — highest priority; include thread-safety notes |
| Constants | MUST — business meaning if not self-evident |
| Private methods | Only if complex (>10 lines) — use `#` comments |
| Properties | MUST NOT document unless they contain logic |
| Overriding methods | MUST NOT duplicate parent docstring — omit or use brief note |
| `@dataclass` fields | Document in class docstring, not per-field |

---

## Enum Documentation

```python
class BenchmarkRunStatus(StrEnum):
    """Status of a benchmark run indicating completion or failure state."""

    NOT_COMPLETED = "NOT_COMPLETED"
    """Run has pending tasks remaining."""

    COMPLETED = "COMPLETED"
    """All tasks finished successfully."""

    FAILED = "FAILED"
    """Run terminated due to an unrecoverable error."""
```

---

## Prohibited Practices

- MUST NOT restate what the code expresses through name, type, or structure
- MUST NOT leave `Args`, `Returns`, `Raises` sections empty
- MUST NOT use `@author` — Git history is authoritative
- MUST NOT have `@deprecated` without explaining the migration path
- MUST NOT leave stale documentation (deleted parameters, removed exceptions, changed return types)
- MUST NOT use marketing language ("powerful", "robust", "blazing fast")

---

## TODO / FIXME / HACK Format

```python
# TODO(owner): description [TICKET-ID]
# FIXME(owner): description [TICKET-ID]
# HACK(owner): description [TICKET-ID]
```

- `FIXME` and `HACK` MUST NOT exist without a linked ticket
- `TODO` without a ticket MUST be resolved or ticketed within 30 days
