#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to "*.toml".
# Soft/non-blocking formatter hook: taplo is treated as an optional convenience tool.
# See rules/uv-project.md for this project's pyproject.toml conventions.
#
# Note on `set`: deliberately NOT using `-u` (nounset) — see lint_and_block_python.sh
# for rationale.

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

if [[ -z "${FILE_PATH}" || "${FILE_PATH}" != *.toml || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

if ! command -v taplo >/dev/null 2>&1; then
  echo "taplo not installed — see rules/uv-project.md" >&2
  exit 0
fi

FMT_OUTPUT="$(taplo fmt "${FILE_PATH}" 2>&1)"
FMT_STATUS=$?

CHECK_OUTPUT="$(taplo check "${FILE_PATH}" 2>&1)"
CHECK_STATUS=$?

if [[ ${FMT_STATUS} -ne 0 || ${CHECK_STATUS} -ne 0 ]]; then
  echo "taplo reported an issue with ${FILE_PATH} (non-blocking):" >&2
  echo "${FMT_OUTPUT}" >&2
  echo "${CHECK_OUTPUT}" >&2
fi

exit 0
