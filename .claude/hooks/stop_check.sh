#!/usr/bin/env bash
# Hook wiring (settings.json): Stop hook (fires when Claude finishes a turn,
# no matcher needed — Stop hooks apply session-wide).
# BLOCKS (exit 2) the stop to force continued work when fast quality checks fail —
# this is the documented exit-code-2-on-Stop pattern. Must stay fast: this fires
# on every single turn, so each check is wrapped with a short timeout.
#
# Note on `set`: deliberately NOT using `-u` (nounset) — see lint_and_block_python.sh
# for rationale (empty bash arrays + nounset misbehave on older bash, e.g. macOS's
# stock bash 3.2, which is relevant here for the optional TIMEOUT_CMD array).

set -o pipefail

PAYLOAD="$(cat)"

extract_stop_hook_active() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null
  else
    if printf '%s' "$PAYLOAD" | grep -o '"stop_hook_active"[[:space:]]*:[[:space:]]*true' >/dev/null 2>&1; then
      echo true
    else
      echo false
    fi
  fi
}

STOP_HOOK_ACTIVE="$(extract_stop_hook_active)"

# Loop guard: if Claude Code already re-invoked this Stop hook because a
# previous run of THIS SAME HOOK exited 2 (forcing continuation),
# stop_hook_active is true on the re-entrant call. Re-running the full check
# again here could loop forever if the failure isn't fixable in one pass, so
# just let the turn end this time instead of re-blocking indefinitely.
if [[ "${STOP_HOOK_ACTIVE}" == "true" ]]; then
  exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-.}"
fi

cd "${REPO_ROOT}" 2>/dev/null || exit 0

# Project doesn't exist yet (e.g. pre-Phase-0 scaffolding) — nothing to check.
if [[ ! -f pyproject.toml ]]; then
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  exit 0
fi

if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD=(timeout 60)
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD=(gtimeout 60)
else
  TIMEOUT_CMD=()
fi

FAILED=0
COMBINED_OUTPUT=""

run_check() {
  description="$1"
  shift
  output="$("${TIMEOUT_CMD[@]}" "$@" 2>&1)"
  status=$?
  if [[ ${status} -ne 0 ]]; then
    FAILED=1
    COMBINED_OUTPUT="${COMBINED_OUTPUT}
--- ${description} (exit ${status}) ---
${output}
"
  fi
}

if uv run ruff --version >/dev/null 2>&1; then
  run_check "uv run ruff check ." uv run ruff check .
fi

if [[ -d src ]] && uv run mypy --version >/dev/null 2>&1; then
  run_check "uv run mypy --strict src/" uv run mypy --strict src/
fi

if uv run lint-imports --help >/dev/null 2>&1; then
  run_check "uv run lint-imports" uv run lint-imports
fi

if [[ ${FAILED} -ne 0 ]]; then
  {
    echo "Quality gate failed at end of turn — fix before stopping (this is the"
    echo "documented exit-code-2-on-Stop pattern to force continued work, not a"
    echo "suggestion)."
    echo "${COMBINED_OUTPUT}"
  } >&2
  exit 2
fi

exit 0
