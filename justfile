default:
    @just --list

setup:
    uv sync --frozen --all-extras --dev

lint:
    uv run ruff check src tests scripts

format:
    uv run ruff check --fix src tests scripts
    uv run ruff format src tests scripts
    uv run mdformat README.md CHANGELOG.md docs/adr docs/architecture docs/development docs/stories
    uv run taplo fmt pyproject.toml
    find . -name '*.sql' -not -path './docs/v3_specification/*' -not -path './.venv/*' | xargs -r uv run sqlfluff fix --dialect sqlite

format-check:
    uv run ruff format --check src tests scripts
    uv run mdformat --check README.md CHANGELOG.md docs/adr docs/architecture docs/development docs/stories
    uv run taplo fmt --check pyproject.toml
    uv run yamllint .github
    find . -name '*.sql' -not -path './docs/v3_specification/*' -not -path './.venv/*' | xargs -r uv run sqlfluff lint --dialect sqlite

typecheck:
    uv run mypy --strict src

import-check:
    uv run lint-imports

arch-test:
    uv run pytest tests/architecture -q

test:
    uv run pytest

coverage-layers:
    # per-layer branch-coverage gate — see docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md §11
    uv run pytest --cov=ollama_llm_bench --cov-report=
    uv run coverage report --include='src/ollama_llm_bench/backend/*' --fail-under=90
    uv run coverage report --include='src/ollama_llm_bench/ui/*/_internal/controller.py,src/ollama_llm_bench/ui/*/_internal/view_model_select.py' --fail-under=85
    uv run coverage report --include='src/ollama_llm_bench/ui/*/_internal/view.py' --fail-under=60

trace:
    uv run python scripts/trace.py

trace-check:
    uv run python scripts/validate_traceability.py

check: lint format-check typecheck import-check arch-test
    uv run pytest tests/unit tests/integration -q
