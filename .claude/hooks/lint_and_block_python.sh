#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to
# files matching "*.py" (scope via the matcher config and/or this script's own
# defensive file-extension check below).
# This hook BLOCKS: exit 2 + stderr feeds actionable lint/type errors back to Claude.
#
# Order note: this script is intended to run BEFORE format_python.sh in the
# PostToolUse hooks array for *.py files, so lint/type findings are reported
# against the file as Claude last wrote it, before formatting touches it.
#
# Note on `set`: deliberately NOT using `-u` (nounset). PostToolUse/Stop hooks
# must control their own exit codes precisely, and `-u` combined with empty
# bash arrays misbehaves on older bash (e.g. macOS's stock bash 3.2).

set -o pipefail

PAYLOAD="$(cat)"

extract_file_path() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null
  else
    printf '%s' "$PAYLOAD" \
      | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
      | head -1 \
      | sed -E 's/.*"file_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/'
  fi
}

FILE_PATH="$(extract_file_path)"

# No file path, not a Python file, or file no longer exists — defensive
# no-op. The settings.json matcher should already scope this, but a hook
# script must never crash a session over a malformed/unexpected payload.
if [[ -z "${FILE_PATH}" || "${FILE_PATH}" != *.py || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

if command -v uv >/dev/null 2>&1 && uv run ruff --version >/dev/null 2>&1 && uv run mypy --version >/dev/null 2>&1; then
  RUFF_CMD=(uv run ruff)
  MYPY_CMD=(uv run mypy)
elif command -v ruff >/dev/null 2>&1 && command -v mypy >/dev/null 2>&1; then
  RUFF_CMD=(ruff)
  MYPY_CMD=(mypy)
else
  # Neither uv-wrapped nor plain ruff/mypy are available — nothing we can check.
  exit 0
fi

RUFF_OUTPUT="$("${RUFF_CMD[@]}" check "${FILE_PATH}" 2>&1)"
RUFF_STATUS=$?

MYPY_OUTPUT="$("${MYPY_CMD[@]}" --strict "${FILE_PATH}" 2>&1)"
MYPY_STATUS=$?

if [[ ${RUFF_STATUS} -ne 0 || ${MYPY_STATUS} -ne 0 ]]; then
  {
    echo "Lint/type issues in a file you just edited — fix these before continuing"
    echo "(do not skip as 'pre-existing', this hook only fires on files you touched):"
    echo
    echo "--- ruff check ${FILE_PATH} ---"
    echo "${RUFF_OUTPUT}"
    echo
    echo "--- mypy --strict ${FILE_PATH} ---"
    echo "${MYPY_OUTPUT}"
  } >&2
  exit 2
fi

exit 0
