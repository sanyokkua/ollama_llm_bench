#!/usr/bin/env bash
# Hook wiring (settings.json): SessionStart hook (no matcher — fires once per
# new session). Always exits 0: this hook's only job is to inject orientation
# context, never to block a session from starting. Every command below is
# defensively guarded (`2>/dev/null || true` style) since this runs
# unconditionally, including in environments before any of this repo's
# scaffolding (git repo, docs/stories/, etc.) exists.
#
# Output channel note: SessionStart hooks support returning JSON with a
# `hookSpecificOutput.additionalContext` field, but plain stdout text is also
# documented as a supported, simpler path for SessionStart context injection.
# This script intentionally uses plain stdout for broader compatibility, since
# the exact JSON schema expectations can vary across Claude Code versions.
#
# Note on `set`: deliberately NOT using `-u` (nounset) — see
# lint_and_block_python.sh for rationale.

set -o pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-.}"
fi

cd "${REPO_ROOT}" 2>/dev/null || true

echo "## Session orientation"
echo

CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [[ -n "${CURRENT_BRANCH}" ]]; then
  echo "- Git branch: ${CURRENT_BRANCH}"
else
  echo "- Git branch: (not a git repo, or detached HEAD)"
fi

LAST_COMMIT="$(git log -1 --oneline 2>/dev/null || true)"
if [[ -n "${LAST_COMMIT}" ]]; then
  echo "- Last commit: ${LAST_COMMIT}"
else
  echo "- Last commit: (none found)"
fi

if [[ -d docs/stories ]]; then
  IN_PROGRESS="$(grep -El '^status:[[:space:]]*in-progress[[:space:]]*$' docs/stories/*.md 2>/dev/null || true)"
  if [[ -n "${IN_PROGRESS}" ]]; then
    echo "- Stories in progress:"
    while IFS= read -r story_file; do
      [[ -n "${story_file}" ]] && echo "  - ${story_file}"
    done <<< "${IN_PROGRESS}"
  else
    echo "- Stories in progress: none"
  fi
else
  echo "- docs/stories/ not present yet"
fi

exit 0
