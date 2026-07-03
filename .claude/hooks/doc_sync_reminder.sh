#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to
# "docs/stories/*.md". Reads the touched file from disk (not just the hook
# payload diff) so it sees the final on-disk state regardless of how the edit
# was made. BLOCKS (exit 2) only when the story's frontmatter status is "done",
# to surface a reminder Claude should act on before ending the turn.
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

if [[ -z "${FILE_PATH}" || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

if grep -Eq '^status:[[:space:]]*done[[:space:]]*$' "${FILE_PATH}" 2>/dev/null; then
  {
    echo "Story marked done — before finishing this turn:"
    echo "(1) update README.md/docs/architecture.md if this story changed a public surface,"
    echo "(2) consider running the claude-md-management plugin's /revise-claude-md if a new"
    echo "    convention was established this story."
    echo "This is not optional busywork — stale docs compound across a 13-phase rewrite."
  } >&2
  exit 2
fi

exit 0
