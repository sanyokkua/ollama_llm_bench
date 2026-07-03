#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to
# "*.yml" / "*.yaml". This hook BLOCKS on findings (exit 2) because malformed
# CI workflow YAML is a real operational risk, unlike markdown/toml formatting.
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

case "${FILE_PATH}" in
  *.yml|*.yaml) ;;
  *) exit 0 ;;
esac

if [[ -z "${FILE_PATH}" || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

if command -v uv >/dev/null 2>&1 && uv run yamllint --version >/dev/null 2>&1; then
  YAMLLINT_CMD=(uv run yamllint)
elif command -v yamllint >/dev/null 2>&1; then
  YAMLLINT_CMD=(yamllint)
else
  echo "yamllint not installed — skipping YAML lint for ${FILE_PATH}" >&2
  exit 0
fi

LINT_OUTPUT="$("${YAMLLINT_CMD[@]}" "${FILE_PATH}" 2>&1)"
LINT_STATUS=$?

if [[ ${LINT_STATUS} -ne 0 ]]; then
  echo "yamllint found issues in ${FILE_PATH} — fix before continuing:" >&2
  echo "${LINT_OUTPUT}" >&2
  exit 2
fi

exit 0
