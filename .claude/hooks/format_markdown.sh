#!/usr/bin/env bash
# Hook wiring (settings.json): PostToolUse, matcher "Edit|Write", filtered to "*.md".
# Soft/non-blocking formatter hook: always degrades to exit 0 so a missing or
# misbehaving mdformat install never stalls a session over a non-critical formatter.
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

if [[ -z "${FILE_PATH}" || "${FILE_PATH}" != *.md || ! -f "${FILE_PATH}" ]]; then
  exit 0
fi

# hookify rule files (.claude/hookify.*.local.md) are YAML-frontmatter-plus-message
# files parsed by the hookify plugin's own hand-rolled frontmatter reader, which
# requires a literal leading "---" delimiter. mdformat treats them as plain prose,
# rewrites "---" to a "___" thematic break, and reflows the nested condition list —
# which makes the frontmatter delimiter unrecognizable and the rule silently stops
# loading. Skip mdformat for these.
case "$(basename "${FILE_PATH}")" in
  hookify.*.local.md)
    exit 0
    ;;
esac

if command -v mdformat >/dev/null 2>&1; then
  mdformat "${FILE_PATH}" >/dev/null 2>&1 \
    || echo "mdformat reported an issue formatting ${FILE_PATH} (non-blocking)." >&2
  exit 0
fi

if command -v uvx >/dev/null 2>&1; then
  uvx mdformat "${FILE_PATH}" >/dev/null 2>&1 \
    || echo "mdformat reported an issue formatting ${FILE_PATH} (non-blocking)." >&2
  exit 0
fi

echo "mdformat not installed — run \`uv add --dev mdformat\`" >&2
exit 0
