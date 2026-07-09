# Ollama LLM Bench

A single-window, single-user desktop application that benchmarks Large Language Models running
locally (Ollama, LM Studio, llama.cpp) or in the cloud (OpenAI, Anthropic, Gemini, Azure).

Configure providers and models, author benchmark task files, and run a **benchmark run** in one
of three modes:

- **Synthetic Benchmark** — synthetic prompts measuring raw speed.
- **Task Benchmark** — real task files, timing only.
- **Graded Benchmark** — real task files plus a batched evaluation pipeline that grades each
  response by keyword match, cosine similarity, and an LLM judge.

Watch progress live; pause, resume, stop, retry, or continue runs; inspect results across
summary tables, detailed task views, charts, and a judge-written narrative analysis. Everything
is stored locally in an embedded SQLite database — no telemetry, no multi-user capability, no
auto-update.

This is a from-scratch rewrite against a complete, binding specification at
[`docs/v3_specification/`](docs/v3_specification/); see that folder's
[reading guide](docs/v3_specification/00_Foundation/01_README.md) for the full product
definition.

## Tech stack

Python 3.13 and PySide6 6.8+ (Qt Widgets, built programmatically — no QML), a synchronous
Qt-free backend with a `QThreadPool`-backed worker layer (no `asyncio`/`anyio`/`qasync`),
`msgspec` for all cross-boundary data, `psygnal` for reactive state stores, `structlog` for
logging, `icontract` for design-by-contract, and an embedded SQLite database with no migrations.
Managed end to end with `uv`; linted and formatted with `ruff`; type-checked with
`mypy --strict`; module boundaries enforced with `import-linter`; tested with `pytest` and
`pytest-qt`. Full toolchain and dependency policy:
[`docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md`](docs/v3_specification/16_Engineering_Standards/02_TOOLCHAIN.md).

## Quick start

```bash
uv sync                        # install dependencies (respects uv.lock)
uv run python -m ollama_llm_bench
```

## Development

```bash
just setup          # uv sync --frozen --all-extras --dev
just check          # full local CI mirror: lint, format-check, typecheck, import-check, arch-test, test
just test            # pytest
```

See `justfile` for every local task, and
[`CLAUDE.md`](CLAUDE.md) plus [`docs/development/`](docs/development/) for the full contributor
workflow, including the story-and-traceability process under
[`docs/v3_specification/14_Process_and_Traceability/`](docs/v3_specification/14_Process_and_Traceability/).

## Documentation

- [`docs/v3_specification/`](docs/v3_specification/) — the vendored, binding specification (the
  single source of truth for application behaviour).
- [`docs/adr/`](docs/adr/) — accepted Architecture Decision Records.
- [`docs/architecture/`](docs/architecture/) — this project's own architecture documentation.
- [`docs/stories/`](docs/stories/) — implementation stories.
- [`CHANGELOG.md`](CHANGELOG.md) — Keep a Changelog format.

## License

MIT — see [`LICENSE`](LICENSE).
