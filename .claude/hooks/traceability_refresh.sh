#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to
# "docs/stories/*.md". Regenerates traceability artifacts via `just trace` so
# story edits stay reflected in generated docs. BLOCKS (exit 2) only when the
# justfile exists AND the trace target actually fails — a missing justfile
# (e.g. pre-Phase-0, before the toolchain is fully scaffolded) is a silent no-op.
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
  docs/stories/*.md|*/docs/stories/*.md) ;;
  *) exit 0 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-.}"
fi

if [[ ! -f "${REPO_ROOT}/justfile" && ! -f "${REPO_ROOT}/Justfile" ]]; then
  # No justfile yet (e.g. early Phase 0) — nothing to regenerate.
  exit 0
fi

cd "${REPO_ROOT}" || exit 0

if command -v uv >/dev/null 2>&1 && uv run just --version >/dev/null 2>&1; then
  JUST_CMD=(uv run just)
elif command -v just >/dev/null 2>&1; then
  JUST_CMD=(just)
else
  echo "justfile present but \`just\` is not runnable — skipping traceability refresh." >&2
  exit 0
fi

TRACE_OUTPUT="$("${JUST_CMD[@]}" trace 2>&1)"
TRACE_STATUS=$?

if [[ ${TRACE_STATUS} -ne 0 ]]; then
  echo "traceability regeneration failed — see output above" >&2
  echo "${TRACE_OUTPUT}" >&2
  exit 2
fi

exit 0
