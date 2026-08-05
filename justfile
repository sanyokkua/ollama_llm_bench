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

# the two gateway-protocol-assignability proof files carry no runtime check of their own
# claim (a wrong Protocol binding is only caught by mypy) so they ride the standing
# strict-mypy gate alongside src/, not left to a one-time, commit-time-only verification
# (STORY-113)
typecheck:
    uv run mypy --strict src \
        tests/architecture/test_gateway_protocol_assignability.py \
        tests/unit/test_common_dialog_gateway_structural_satisfaction.py

import-check:
    uv run lint-imports

arch-test:
    uv run pytest tests/architecture -q

test:
    uv run pytest

# The e2e tier alone. Pins the offscreen Qt platform plugin so a local run matches CI —
# nothing outside the CI workflows sets QT_QPA_PLATFORM, and these tests build and show
# the real main window (docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md §12).
test-e2e:
    QT_QPA_PLATFORM=offscreen uv run pytest tests/e2e -q

coverage-layers:
    # per-layer branch-coverage gate — see docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md §11
    uv run pytest --cov=ollama_llm_bench --cov-report=
    uv run coverage report --include='src/ollama_llm_bench/backend/*' --fail-under=90
    uv run coverage report --include='src/ollama_llm_bench/ui/*/_internal/controller.py,src/ollama_llm_bench/ui/*/_internal/view_model_select.py' --fail-under=85
    uv run coverage report --include='src/ollama_llm_bench/ui/*/_internal/view.py' --fail-under=60

# Capture every spec screen in both themes into artifacts/ for the mockup-conformance review (STORY-087).
screenshots:
    QT_QPA_PLATFORM=offscreen SCREENSHOT_ARTIFACTS_DIR=artifacts/screenshots uv run pytest tests/integration/test_screenshot_harness.py -q

trace:
    uv run python scripts/trace.py

trace-check:
    uv run python scripts/validate_traceability.py

check: lint format-check typecheck import-check arch-test
    uv run pytest tests/unit tests/integration tests/e2e src -q
