---
description: "External library governance — standard library preference, approved dependencies, license rules, evaluation criteria"
globs: "pyproject.toml,src/**/*.py"
alwaysApply: false
---

# Python External Libraries

## Critical Rules

- MUST prefer Python's standard library before introducing any third-party package — every new dependency requires justification
- MUST use Pydantic v2 (`BaseModel`) for all data arriving from external sources (API responses, file parsing, config)
- MUST NOT introduce any dependency with a banned license (`GPL-2.0`, `GPL-3.0`, `AGPL-3.0`, `SSPL`, `BSL`)
- MUST NOT import or use any library from the Banned Library List
- MUST use `frozen=True` in Pydantic `model_config` unless mutation is explicitly required

## Standard Library Preference

- MUST use `pathlib` for file paths, `collections` for specialized containers, `datetime` for dates, `re` for regex, `json` for basic JSON, `dataclasses` for simple internal data
- Third-party alternatives are justified only when stdlib is materially deficient

## New Dependency Evaluation

Every new dependency MUST meet ALL thresholds:

| Criterion | Minimum Threshold |
|---|---|
| Last release | Within 12 months |
| Critical CVEs | Zero |
| Core maintainers | >= 2 |
| License | Approved list |
| Transitive dependencies | <= 15 (prefer <= 5) |
| Python version support | Must support project minimum |

### Approved Licenses

MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF-2.0, Unlicense, CC0-1.0

### Conditionally Approved (requires sign-off)

MPL-2.0, LGPL-2.1, LGPL-3.0

## Project-Specific Approved Dependencies

| Library | Status | Min Version | Notes |
|---|---|---|---|
| `PySide6` | Recommended | 6.0 | Qt framework (migration target) |
| `ollama` | Recommended | 0.5.1 | Ollama Python client |
| `PyYAML` | Recommended | 6.0 | YAML parsing for dataset |
| `pydantic` | Recommended | 2.0 | External data validation |
| `structlog` | Recommended | — | Logging facade (migration target) |
| `httpx` | Recommended | 0.27 | HTTP client |
| `pytest` | Recommended | 8.0 | Testing |
| `pytest-cov` | Recommended | 4.0 | Coverage |
| `pytest-mock` | Recommended | 3.12 | Mocking |
| `ruff` | Recommended | 0.9.0 | Formatter + linter |
| `mypy` | Recommended | — | Type checking (migration target) |

## Banned Libraries

| Library | Migration Target |
|---|---|
| `PyQt6` | PySide6 (migration in progress) |
| `marshmallow` | Pydantic v2 |
| `pendulum` | `datetime` + `python-dateutil` |
| `loguru` | `structlog` |
| `black` / `autopep8` / `yapf` | `ruff` |
| `isort` | `ruff` (I rule) |

## Wrapper Policy

MUST wrap a third-party library behind an internal interface when ANY of:
- Used across >= 3 modules
- Realistic replacement candidate within 24 months
- < 20% of surface area used
- Handles cross-cutting concern (logging, metrics)

MUST NOT wrap libraries used in only one file with trivial surface area.
