---
name: clear-and-execute
description: After plan approval, restart context and execute the saved plan stage-by-stage with explicit check-ins. Use after the user has run /clear (or wants you to remind them to). Looks for the plan in ~/.claude/plans/ unless a path is passed as args.
allowed-tools: Read, Bash, Edit, Write, Grep, Glob, TaskCreate, TaskUpdate, TaskList
---

# clear-and-execute

The user has approved a plan via `ExitPlanMode` and now wants to execute it cleanly without dragging along the planning conversation context.

## Critical pre-condition

Claude Code's `/clear` command can only be issued by the user. **You cannot clear your own context.** If invoked in a conversation that still contains the planning history, your first action is:

> "Plan execution requested. To start with a clean context, please run `/clear` and then re-invoke me with `/clear-and-execute <plan-path>`. I'll wait."

…and stop. Do not start executing inside a polluted context.

If the conversation already looks fresh (no prior planning content visible), proceed.

## Plan resolution

1. If `args` contains a file path, that is the plan file.
2. Otherwise, list `~/.claude/plans/*.md` sorted by mtime descending and pick the newest.
3. If multiple recent plans exist (within 24h of each other), ask the user which to execute.
4. If none exist, report "No plan found under ~/.claude/plans/" and exit.

## Execution loop

1. Read the plan file in full.
2. Print a one-line summary of what the plan accomplishes (extract from the `## Context` section).
3. Use `TaskCreate` to register one task per stage (stages are top-level `## Stage N — Title` headings).
4. For each stage in order:
   - Mark task `in_progress`.
   - Print: "Starting Stage N: <title>. Will run <verification commands> at the end. Proceed? (y / skip / abort)".
   - Wait for user confirmation.
   - Execute the stage steps as specified.
   - Run the stage's verification block exactly as written.
   - If verification fails: stop, surface the failure, ask the user how to proceed.
   - If verification passes: mark task `completed`, move to the next stage.
5. After the last stage, run the global verification block (Stage 9 in most plans), produce a final delta summary against `.AdditionalDocs/baseline/` if present.

## Reporting rules

- One sentence between stages — no preamble.
- Verification output: only show failures, never passing-stage noise.
- Never bundle multiple stages into one commit unless the plan explicitly says so.
- Never ask "should I proceed" unless the plan calls for an interactive checkpoint or a stage's verification fails.

## When NOT to use

- Trivial single-step changes — just do them.
- Mid-stage retries — that's a debugging task, not plan execution.
- Plans you wrote yourself in the same conversation — context is already loaded; just execute.
