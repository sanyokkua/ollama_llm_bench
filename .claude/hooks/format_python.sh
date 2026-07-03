#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to "*.py".
# Intended to run AFTER lint_and_block_python.sh in the same hooks array entry so
# lint/type findings are reported before formatting silently rewrites the file.
# This hook does NOT block on style — formatting is auto-applied, not a judgment call.
# It only exits 2 if the `ruff format` invocation itself errors out (tool crash,
# unparsable file, etc.), so Claude sees that something is actually broken.
#
# Note on `set`: deliberately NOT using `-u` (nounset) — see lint_and_block_python.sh
# for rationale (empty bash arrays + nounset misbehave on older bash).

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

if [[ -z "${FILE_PATH}" || "${FILE_PATH}" != *.py || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

if command -v uv >/dev/null 2>&1 && uv run ruff --version >/dev/null 2>&1; then
  FORMAT_CMD=(uv run ruff)
elif command -v ruff >/dev/null 2>&1; then
  FORMAT_CMD=(ruff)
else
  # No formatter available — nothing to do, don't block the session over it.
  exit 0
fi

FORMAT_OUTPUT="$("${FORMAT_CMD[@]}" format "${FILE_PATH}" 2>&1)"
FORMAT_STATUS=$?

if [[ ${FORMAT_STATUS} -ne 0 ]]; then
  echo "ruff format failed on ${FILE_PATH}:" >&2
  echo "${FORMAT_OUTPUT}" >&2
  exit 2
fi

exit 0
