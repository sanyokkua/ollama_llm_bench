---
paths:
  - "pyproject.toml"
  - "src/**/*.py"
---

# External Libraries

Source of truth: `docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md`. The
application targets Python 3.13 and PySide6 6.8+ Qt Widgets (no QML), built with `uv_build`, as
a hexagonal monolith with a single manual composition root and no dependency-injection
container.

## Dependency-version policy — always latest stable, no long-term freezing

The policy is **always the latest stable release at the time of work**. When a module is
implemented or revised, dependencies are taken at the newest stable version, the lockfile is
refreshed with `uv lock --upgrade`, and the version table below is updated. The lower bounds in
`pyproject.toml` express the floor the code is known to require — they are not pins; `uv.lock`
is the reproducibility anchor.

**`psygnal` is the sole pinned exception** — its minor releases have historically renamed
public symbols, so it is constrained to a single minor series (`==0.15.*`) advanced
deliberately.

A new dependency is admissible only if it has a recent release, no known critical
vulnerabilities, more than one maintainer, a permissive license (MIT, BSD, Apache-2.0, ISC,
PSF), and a small transitive footprint. Failing any criterion requires a recorded ADR (see
`traceability-and-stories.md`).

## Runtime dependencies

| Package | Floor | Role |
|---|---|---|
| `PySide6` | `>=6.8,<6.9` | Qt 6 binding; UI layer (Qt Widgets, programmatic); `QThreadPool` worker execution in the adapter (D-R-01) |
| `msgspec` | `>=0.21.0` | All DTOs and cross-boundary data; serialization |
| `psygnal` | `==0.15.*` | Reactive signals for the store layer (upper bound deliberate) |
| `structlog` | `>=25.5.0` | Structured logging over the standard library `logging` |
| `icontract` | `>=2.7.3` | Design-by-contract decorators on public APIs |
| `ruamel.yaml` | `>=0.18` | Comment-preserving YAML for benchmark task files |
| `platformdirs` | `>=4.0` | Cross-platform application-data directory resolution |
| `click` | `>=8.1` | Command-line interface for the diagnostic doctor commands |
| `typing-extensions` | `>=4.5.0` | `@deprecated` (PEP 702) runtime support |

## Development dependencies

| Package | Floor | Role |
|---|---|---|
| `pytest` | `>=8.0` | Test framework |
| `pytest-qt` | `>=4.5` | Widget tests; `qtbot`; `QAbstractItemModelTester` |
| `pytest-cov` | `>=4.0` | Coverage measurement |
| `pytest-mock` | `>=3.12` | `mocker` fixture with `spec=` enforcement |
| `pytest-archon` | `>=0.0.7` | Architecture tests at the import and symbol level |
| `pytest-randomly` | `>=3.15` | Test-order randomization |
| `pytest-rerunfailures` | latest | Flake detection for opt-in local slow-test runs |
| `pytest-httpserver` | latest | Provider wire stub — local HTTP server for transport-level adapter tests |
| `hypothesis` | latest | Property-based and stateful testing |
| `icontract-hypothesis` | latest | Property tests inferred from `icontract` contracts |
| `freezegun` | `>=1.4` | Deterministic time in tests |
| `ruff` | `>=0.9.0` | Linter and formatter |
| `mypy` | `>=1.16` | Static type checker (`mypy 1.16+` required for PEP 702 `@deprecated` on `@property`) |
| `import-linter` | `>=2.11` | Module-boundary contracts |
| `pip-audit` | `>=2.10` | Dependency vulnerability scanning |

## Build dependencies

| Package | Floor | Role |
|---|---|---|
| `uv_build` | `>=0.9.0,<0.10.0` | Build backend |
| `pyinstaller` | `>=6.0` | Produces the per-OS desktop binaries (`--onedir`) |

## Banned tools and libraries

| Banned | Reason | Replacement |
|---|---|---|
| `pip`, `poetry`, `pipenv`, `pip-tools` | Superseded by a single unified manager | `uv` |
| `pyenv`, `virtualenv` | `uv` manages interpreters and environments | `uv` |
| `black`, `autopep8`, `yapf` | Superseded by one formatter | `ruff format` |
| `flake8`, `pylint`, `isort`, `pycodestyle` | Superseded by one linter | `ruff` |
| `PyQt6`, `PyQt5`, `PySide2` | Project standardizes on one current Qt binding | `PySide6` |
| QML / Qt Quick | UI is built programmatically with Qt Widgets | Hand-written `QWidget` code |
| `pydantic` on hot paths | Slower than `msgspec`; external files (imports, task YAML) use safe-load parsing plus explicit per-field validation | `msgspec.Struct` |
| `dataclasses` for cross-boundary data | No immutability or validation guarantees | `msgspec.Struct(frozen, kw_only, gc=False)` |
| `tenacity` | The project uses its own cooperative `CancellationToken`-aware retry policy | The in-house retry wrapper |
| `stamina` | Async-oriented; the backend has no event loop (D-R-01); removed by DD-43 | The in-house retry wrapper |
| `purgatory` | Asyncio-native circuit breaker; needs an event loop the app forbids; removed by DD-43 | The in-house `backend/circuit_breaker/` |
| A blocking HTTP client on the GUI thread | Stalls the UI | A synchronous HTTP client (e.g. `httpx.Client`) called only on `TaskRunner` worker threads |
| Any dependency-injection container | Reflection-based wiring defeats `mypy` and the composition root | Manual wiring in `compose.py` |
| `loguru`, `picologging` | Project standardizes on structured logging over the standard library | `structlog` |
| `asyncio` / `qasync` / `anyio` | Per D-R-01 the app uses a synchronous backend + Qt `QThreadPool` `TaskRunner`; no event loop or structured-concurrency runtime | `threading` / `concurrent.futures` + `QThreadPool`; `CancellationToken` (`threading.Event`); `try`/`finally` cleanup |
| GPL / AGPL / SSPL / BSL licensed dependencies | License incompatibility | A permissively licensed alternative |

## Standard library preference

Use `pathlib` for file paths, `collections` for specialized containers, `datetime` for dates,
`re` for regex, `json` for basic JSON. Third-party alternatives are justified only when stdlib
is materially deficient. `msgspec.Struct` replaces `dataclasses` for any cross-boundary data
(see `coding-style.md`).
