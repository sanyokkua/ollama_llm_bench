#!/usr/bin/env bash
# Hook wiring (settings.json): PreToolUse, matcher "Bash" (the matcher may be a
# broad "Bash" match rather than something git-commit-specific, so this script
# self-filters on tool_input.command and no-ops for anything else).
# This hook BLOCKS (exit 2) when staged files fail pre-commit, surfacing the same
# failure the git-level pre-commit hook would produce anyway, just earlier — and
# for a PreToolUse hook, exit 2 also prevents the `git commit` Bash call itself
# from running.
#
# Note on `set`: deliberately NOT using `-u` (nounset) — see lint_and_block_python.sh
# for rationale.

set -o pipefail

PAYLOAD="$(cat)"

extract_command() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // empty' 2>/dev/null
  else
    printf '%s' "$PAYLOAD" \
      | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' \
      | head -1 \
      | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/'
  fi
}

COMMAND="$(extract_command)"

case "${COMMAND}" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-.}"
fi

if [[ ! -f "${REPO_ROOT}/.pre-commit-config.yaml" ]]; then
  # pre-commit not configured yet — nothing to gate on.
  exit 0
fi

cd "${REPO_ROOT}" || exit 0

STAGED_FILES="$(git diff --cached --name-only 2>/dev/null || true)"
if [[ -z "${STAGED_FILES}" ]]; then
  exit 0
fi

if command -v uv >/dev/null 2>&1 && uv run pre-commit --version >/dev/null 2>&1; then
  PRECOMMIT_CMD=(uv run pre-commit)
elif command -v pre-commit >/dev/null 2>&1; then
  PRECOMMIT_CMD=(pre-commit)
else
  echo "pre-commit not installed — skipping staged-file check before commit." >&2
  exit 0
fi

# Intentionally unquoted: word-splits STAGED_FILES into individual file
# arguments for `--files`. Filenames containing spaces are not expected in
# this codebase's tracked sources.
# shellcheck disable=SC2086
PRECOMMIT_OUTPUT="$("${PRECOMMIT_CMD[@]}" run --files ${STAGED_FILES} 2>&1)"
PRECOMMIT_STATUS=$?

if [[ ${PRECOMMIT_STATUS} -ne 0 ]]; then
  {
    echo "pre-commit checks failed on staged files — fix these before committing"
    echo "(the git-level pre-commit hook will block this commit anyway; this just"
    echo "surfaces it now):"
    echo
    echo "${PRECOMMIT_OUTPUT}"
  } >&2
  exit 2
fi

exit 0
