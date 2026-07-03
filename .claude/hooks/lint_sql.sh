#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to "*.sql".
# This hook BLOCKS on findings (exit 2) — schema/query mistakes caught here are
# cheaper to fix immediately than after they've propagated into migrations.
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

if [[ -z "${FILE_PATH}" || "${FILE_PATH}" != *.sql || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

if command -v uv >/dev/null 2>&1 && uv run sqlfluff --version >/dev/null 2>&1; then
  SQLFLUFF_CMD=(uv run sqlfluff)
elif command -v sqlfluff >/dev/null 2>&1; then
  SQLFLUFF_CMD=(sqlfluff)
else
  echo "sqlfluff not installed — skipping SQL lint for ${FILE_PATH}" >&2
  exit 0
fi

LINT_OUTPUT="$("${SQLFLUFF_CMD[@]}" lint --dialect sqlite "${FILE_PATH}" 2>&1)"
LINT_STATUS=$?

if [[ ${LINT_STATUS} -ne 0 ]]; then
  echo "sqlfluff found issues in ${FILE_PATH} — fix before continuing:" >&2
  echo "${LINT_OUTPUT}" >&2
  exit 2
fi

exit 0
