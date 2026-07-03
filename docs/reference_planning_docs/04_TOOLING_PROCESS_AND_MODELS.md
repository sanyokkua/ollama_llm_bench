# Tooling, Process Discipline, and Model Selection

Answers three follow-up questions: which SDD tooling to adopt, how to keep stories/ACs from
drifting away from the spec when Claude Code does the work, and which model for which stage.

## 1. Should you adopt a spec-driven-development tool/plugin?

You already have one — it's just bespoke rather than off-the-shelf. The plan in this folder
(stories with `spec_clauses:`/`modules:`/`acceptance_criteria:` front-matter, a generated
`traceability.yaml`, a `just trace-check` gate) **is** spec-driven development, built directly
from your spec's own `14_Process_and_Traceability/` format rather than a generic template.

Two named tools came up in your question — here's what they actually are and whether to add
them:

- **GitHub Spec Kit** (`github/spec-kit`) — a CLI that drives agents through
  constitution → specify → clarify → plan → tasks → analyze → implement, writing
  `spec.md`/`plan.md`/`tasks.md`. It's built for the case where *you don't have a spec yet* and
  want an agent to help you write one collaboratively. You already have a complete,
  implementation-ready 131-file spec — running Spec Kit on top would mean re-deriving a second,
  shallower spec artifact that competes with the one you already trust. **Don't bolt it on.**
  Two of its ideas are worth stealing directly into your existing process, though (folded into
  §2 below): an explicit **clarify** pass before story-writing, and an **analyze** pass that
  cross-checks artifacts for consistency before implementation starts.
- **Superpowers** (`obra/superpowers`, installed via Claude Code's own
  `/plugin marketplace add obra/superpowers-marketplace` + `/plugin install`) — a third-party
  (not Anthropic-authored, despite being listed in Anthropic's plugin directory) skills
  framework: enforced TDD red-green-refactor, a 4-phase debugging methodology, and
  "subagent-driven development with built-in code review." It is spec-agnostic — it doesn't
  know about `traceability.yaml` or your story format, it just disciplines *how* a coding
  session behaves once it's been told what to build. The TDD enforcement and the
  built-in-code-review pattern are both useful and don't conflict with your story structure.
  **Worth trying, but test it on one phase first** before trusting it across the whole rewrite —
  running two opinionated frameworks (your custom agents + Superpowers) at once is itself a
  drift risk if their instructions ever pull in different directions. If it doesn't fit, drop
  it — the story/traceability mechanism is the part doing the actual work of preventing
  requirement loss.

Net recommendation: **keep your custom agents and the story/traceability process as the
backbone; do not add Spec Kit; optionally trial Superpowers for its TDD/review discipline
inside individual coder sessions.**

## 2. Concrete drift-prevention mechanics (this is the part that actually matters)

The traceability check catches *missing* coverage. It does not catch a story that cites the
right spec clause but **misreads** it. That needs separate guardrails:

1. **Clarify pass before story-writing, per phase.** Before `architect` drafts stories for a
   phase, have it (or `investigator`) list every place the phase's spec files are ambiguous,
   underspecified relative to *this specific codebase*, or reference a DD-number/D-R-number it
   can't resolve from the files it read. Answer those explicitly — in chat is fine, but paste
   the resolution into the relevant story's "Design constraints" section so it's not re-litigated
   per story. This is Spec Kit's `/clarify` idea, just folded into your existing per-phase flow.
2. **Independent AC verification ("second opinion") before coding starts.** After `architect`
   writes a story, hand the story file (only the file — not the conversation that produced it)
   to a **fresh** agent with no other context, plus the exact spec files it cites, and ask it to
   re-derive the acceptance criteria from scratch and diff against what's written. Run this as
   its own `Agent` call with `isolation: "worktree"` not needed (it's read-only) — just a clean
   context window. This catches the single highest-risk failure mode: an architect
   session quietly misremembering a detail from a 2000-line contracts file it read 40 tool calls
   ago.
3. **One story per coding session, never more.** Already in `02_STORY_PROCESS.md` — repeating
   it because it's the single most effective lever. Context-window degradation over a long
   session is a bigger drift source than any individual model's reasoning quality.
4. **Spec-conformance code review, not just correctness review.** When a story's implementation
   is done, don't just run the generic `engineering:code-review` skill (security/performance/
   correctness) — explicitly also ask a reviewer pass "does this implementation match every
   acceptance criterion in the story, line by line, and does it introduce any behavior the cited
   spec clauses don't authorize?" Generic code review will pass code that's good Python but
   subtly wrong against the spec (e.g. uses `frozenset` for `setting_overrides` semantics close
   to but not identical to what `08-G_feature_flags.md` actually specifies).
5. **`just trace-check` is a hard gate, not a courtesy check.** Refuse to mark any story `done`
   — and refuse to move to the next phase — while it reports any gap. Treat a passing
   `trace-check` as necessary, not sufficient (it proves nothing was *skipped*; steps 1-4 are
   what catch something done *wrong*).
6. **Human checkpoint at every phase boundary**, per `03_CLAUDE_CODE_KICKOFF_PROMPT.md` — review
   the story list for completeness against the phase's module list before any `coder` session
   starts, and spot-check a sample of diffs against the spec after. Don't let a Claude Code
   session chain straight through multiple phases unattended; the plan is deliberately built to
   pause at each phase precisely so you stay in the loop on a rewrite this size.

## 3. Model selection per stage

Your existing `.claude/agents/*.md` already assign models reasonably (per this project's
`CLAUDE.md` agents table: investigator=haiku, architect=sonnet, coder=sonnet, debugger=sonnet,
tester=sonnet, docs-writer=haiku). For this specific rewrite, one change is worth making and
one new role is worth adding:

| Stage | Model | Why |
|---|---|---|
| `investigator` (read-only mapping) | **Haiku** | Pure retrieval/summarization, low risk, current default is right. |
| `architect` (story/AC authoring from spec) | **Opus**, at least for Phase 0–1 and any architecturally-significant story | This is the highest-leverage step in the whole plan — it's the one place spec meaning gets translated into a contract `coder` will trust verbatim. Sonnet is fine once a pattern is established and later stories are repeats of an already-validated shape (e.g. the 5th near-identical persistence-store story in Phase 2); use Opus for the *first* instance of each new kind of story. |
| **New: spec-conformance reviewer** (§2 step 2 and step 4) | **Opus** | Its entire job is catching subtle misinterpretation — pay for the better model here, it's cheap relative to the cost of a drifted requirement surviving into Phase 11. |
| `coder` (implementation) | **Sonnet** | ~90% of Opus's coding capability at meaningfully better speed/cost; the story it's given should already be precise enough that raw reasoning power matters less here than it does upstream. |
| `tester` | **Sonnet** | Same reasoning — table-driven/Hypothesis test authoring from a precise AC is mechanical enough for Sonnet once the AC is right. |
| `debugger` | **Sonnet**, escalate to **Opus** if a failure resists two Sonnet attempts | Most failures are mundane; reserve Opus for the genuinely confusing ones. |
| `docs-writer` | **Haiku** | Mechanical, low-risk, current default is right. |
| The orchestrating Claude Code session itself (you, kicking off each phase) | **Opus**, or Claude Code's `opusplan` mode if available in your CLI version | You're the one reading phase summaries and approving story lists — that's a planning/review role, which is exactly where Opus's reasoning edge pays off, and `opusplan` keeps Opus rates scoped to planning while execution still runs at Sonnet cost. |

Rule of thumb underlying the table: **Opus where a mistake is expensive to detect later
(spec interpretation, review), Sonnet where the task is mechanical and bounded by an
already-correct contract (writing code/tests to a precise story), Haiku where the task is pure
retrieval with no judgment call.**

## 4. What's left in Phase 0, given branch + delete + commit + spec copy are done

You've completed the branch (`feature/v3-redesign`) and spec-vendoring steps (decisions D1/D2
from `00_OVERVIEW_AND_DECISIONS.md` are now resolved by your actions — update that file's D1/D2
status if you want the package to reflect it). Remaining Phase 0 items from
`01_PHASE_BREAKDOWN.md`, in order:

1. Resolve D3 (rewrite `.claude/CLAUDE.md` + the conflicting rule files), D4 (ratify the 3
   proposed ADRs), D5 (confirm exact deletion scope was matched — `.claude/agents/*` should
   still exist; `LICENSE`/`.git*` should still exist).
2. `pyproject.toml` rewrite (`uv_build`, full dependency table, ruff/mypy config).
3. `justfile`, `import-linter` config.
4. Scaffold the empty `src/ollama_llm_bench/` package tree from
   `docs/spec/16_Engineering_Standards/01_PROJECT_STRUCTURE.md`'s verbatim tree.
5. Scaffold `tests/{architecture,unit,integration,e2e,perf,typing_negative}/`.
6. `docs/stories/`, `docs/adr/`, `scripts/trace.py`, `scripts/validate_traceability.py`.
7. New CI workflows (PR-gate + release-tag only, per DD-36 — no schedule/dispatch trigger).
8. `just sync && just check` green on the empty scaffold = Phase 0 done → start Phase 1 with a
   fresh session per `03_CLAUDE_CODE_KICKOFF_PROMPT.md`.
