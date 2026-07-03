# Claude Code Setup Recommendations — Spec v3 Rewrite

**Status:** Draft — for review and approval before anything is generated.
**Scope:** this document covers ONLY the `.claude/` configuration (CLAUDE.md, agents, skills,
rules, hooks) and which marketplace plugins/MCPs to install. It does not cover the
implementation plan itself (phases/stories — see `01_PHASE_BREAKDOWN.md`/`02_STORY_PROCESS.md`)
or the spec-vendoring location. Assumes the workflow you described: new branch
`feature/v3-redesign`, repo emptied, spec copied to `docs/v3_specification/`.

Sources: Claude Code's own docs (`code.claude.com/docs`), the "Steering Claude Code" framework
Anthropic published, the current (stale) `.claude/` setup in this repo, and the full
`App_Specification_Ollama_Bench_Final/` spec content already analyzed in this session
(particularly `16_Engineering_Standards/`, `14_Process_and_Traceability/`,
`08_Cross_Cutting/08-E_interfaces_contracts.md`).

## 0. The mental model (why each category exists)

| Mechanism | Nature | When it fires | Use it for |
|---|---|---|---|
| `CLAUDE.md` | Deterministic, always loaded | Every single turn | Things that must be true every turn — short, ruthlessly pruned |
| `.claude/rules/*.md` | Deterministic-ish, path-filtered (`paths:`/glob frontmatter) | Loaded only when Claude touches a matching file | Domain-specific detail that doesn't belong in every turn's context |
| `.claude/skills/*/SKILL.md` | Probabilistic — Claude decides to invoke based on description match (or explicit `/skill`) | On demand | Procedural playbooks, reference material, "how we do X" — costs ~0 context until invoked |
| `.claude/agents/*.md` | Isolated context window, returns a summary | Delegated explicitly via the `Agent`/Task mechanism | Work that benefits from a clean context or independent judgment (research, review, long implementation) |
| `.claude/hooks` (in `settings.json`) or a hooks-generator plugin | Deterministic code, cannot hallucinate | On a lifecycle event (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, ...) | Enforcement that must never depend on the model remembering — formatting, banned patterns, auto-checks |
| Plugins / MCP servers | External capability or bundled agents+skills+hooks | Installed once, available every session | Reuse instead of reinventing — only when a real gap exists |

The current repo's setup already uses CLAUDE.md + rules + skills + agents correctly in shape;
it's the *content* that's stale (describes the old dataclass/ABC/`backend/core+services`
architecture). The plan below keeps the shape, replaces the content, and adds hooks (currently
unused) plus a small number of plugins where they cover a real gap.

---

## 1. CLAUDE.md — required sections

Keep it short — the framework guidance is explicit that an over-long CLAUDE.md gets partially
ignored. Target: similar length to the current one (~150 lines), not the ~600 a naive
spec-dump would produce.

| Section | Reasoning | Logic / content | Location |
|---|---|---|---|
| One-paragraph project pitch + spec authority statement | Orients every fresh session in one breath; states that `docs/v3_specification/` is the single source of truth and any behavior not traceable to it must not be invented | "This app is being rewritten from scratch per `docs/v3_specification/`. Never invent behavior — every non-trivial decision must cite a spec file. If the spec is silent, stop and ask rather than guess." | Top of `CLAUDE.md` |
| AI config locations table | Same convention as today — tells Claude where its own config lives | Unchanged from current pattern, update paths if anything moves | `CLAUDE.md` |
| Non-negotiable architecture constraints (one screen, bullets only, no explanation) | These are the constraints that recur across nearly every spec file (confirmed by the DD-log cross-reference index) — they must be true on every single turn, so they belong here, not in a rule | 3-layer `backend/`(Qt-free)→`adapters/`→`ui/`; `msgspec.Struct(frozen=True, kw_only=True, gc=False)` for all cross-boundary data, never `@dataclass`; `Protocol` is the default interface, no god-interfaces file; no `asyncio`/`qasync`/`anyio` anywhere (D-R-01); one dispatcher thread + `TaskRunner` over `QThreadPool`; single-inference gate (`InferenceActivityStore`); single DB writer, no migrations (additive-only schema, DD-53); `provider_id` is an internal UUID4, `name` is the display field (DD-33); `icontract` on every public `api.py` function, guarding programmer invariants only, never user input | `CLAUDE.md`, near the top |
| Commands | Every session needs these | `uv sync`, `just check`, `just trace`, `just trace-check`, `just coverage-layers` | `CLAUDE.md` |
| Story/traceability workflow, one paragraph | Tells every session how work is tracked, so it doesn't freelance a different task system | "Work is tracked as stories under `docs/stories/` (format: `docs/v3_specification/14_Process_and_Traceability/02_STORY_FORMAT.md`). One story per coding session. Never mark a story done without `just trace-check` passing." | `CLAUDE.md` |
| Rules Reference table | Discoverability without bloating context — same pattern as today | Table: rule file, glob, one-line description | `CLAUDE.md` |
| Skills Reference table | Discoverability | Table: skill name, one-line description, when to use | `CLAUDE.md` |
| Agents Reference table | Discoverability + model assignment visible up front | Table: agent, model, use-after | `CLAUDE.md` |
| "Never do this" shortlist | The highest-frequency mistake a model makes is reverting to familiar patterns (dataclass, ABC-everywhere, bare except, asyncio) instead of the spec's actual conventions — a short explicit ban list is cheap insurance | 6-10 bullets, each naming the banned pattern and its replacement | `CLAUDE.md` |
| Context-management note | Already present today — keep | What to preserve across compaction (modified files, mypy errors, test failures, current phase/story) | `CLAUDE.md` |
| Self-discovery instruction for agents/skills | Directly answers your requirement that agents self-discover what's available rather than being told everything by the orchestrator | One paragraph: "Every agent and skill should check `.claude/skills/` (via the Skill tool) and the MCP tools available to it before assuming something doesn't exist, rather than relying solely on what's spelled out in its own prompt." | `CLAUDE.md`, near Agents Reference |
| Subagent orchestration discipline (NEW — your note) | You asked explicitly for this: don't spawn a subagent per tool call; delegate substantial batches of work and keep the orchestrating session's own context clean | "The top-level session orchestrates — it delegates a phase/story's substantial work to `Agent` calls and waits for a concise returned summary; it does not do large amounts of file-by-file editing in its own context when a subagent could do it instead. Don't spawn a subagent for a single trivial lookup. Keep any one batch of parallel subagents to roughly ≤8 — beyond that, coordination overhead exceeds the benefit. Ask every subagent to return structured output (a short summary + what changed), not a transcript." | `CLAUDE.md`, new "Orchestration discipline" section |
| "Don't ignore lint/type errors" rule (NEW — your note) | Directly addresses the failure mode you described — models rationalizing a reported issue as "pre-existing" and moving on. Since this is a from-scratch rewrite there's no large inherited legacy debt to use as an excuse, so this can be enforced strictly | "A `ruff`/`mypy` issue reported by a hook in a file you touched must be fixed before you consider the story done — 'pre-existing' is not a valid reason to leave it, since hooks only fire on files you've edited. If something is genuinely out of scope, say so explicitly in the story's notes instead of silently skipping it." Backed by the hooks in §5, which make this close to mechanically enforced rather than just requested | `CLAUDE.md`, near the hooks/commands sections |
| "Never bypass quality gates" rule (NEW — your note) | Backstops the pre-commit setup in §5a — without this, a frustrated session could just use `--no-verify` to get past a blocking hook | "Never run `git commit --no-verify`/`-n`, never delete or comment out a failing test to make a suite pass, never weaken a `ruff`/`mypy` rule to silence a finding without discussing it first." | `CLAUDE.md` |

---

## 2. Agents (`.claude/agents/*.md`)

**Orchestration discipline** (addresses your note about context cleanliness): the top-level
Claude Code session for a phase should behave as an orchestrator, not an implementer — it
delegates an investigation, a story's implementation, or a review to one `Agent` call and lets
that subagent make as many internal tool calls as it needs in its own isolated context, rather
than the orchestrator looping `Read`/`Edit` itself or spinning up a subagent for every single
file. Concretely: one `Agent` call per story (not per file within a story), structured-output
return expected from every subagent, and parallel subagent batches kept to roughly ≤8 to avoid
coordination overhead outweighing the benefit. This is the same discipline already implicit in
"one story per coding session" — stated explicitly here because you asked for it as an
independent rule, since it also applies to `investigator`/review work that isn't a "story" per se.

Keep the existing 6-agent shape (it already maps cleanly onto the story workflow) and refine
their model assignment and prompts; add one new agent.

| Agent | Model | Reasoning | Tools | Self-discovery instruction baked into the prompt | File |
|---|---|---|---|---|---|
| `investigator` | Haiku | Pure read-only mapping (what exists vs. what a phase needs) — cheap, low-risk, current default is right | Read, Glob, Grep | "Check `docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md` for the module list before concluding something is missing; check `.claude/skills/` for a relevant skill before improvising a convention." | `.claude/agents/investigator.md` |
| `architect` | **Opus** (upgraded from Sonnet) for Phase 0–1 work and any new story pattern; Sonnet acceptable once a pattern repeats | Highest-leverage step — misreading the spec here propagates into every downstream story; this is exactly where the better reasoning model earns its cost | Read, Glob, Grep, Write (stories only) | "Cite `spec_clauses:` from real anchors in `docs/v3_specification/`; check `02_STORY_FORMAT.md` and `05_ACCEPTANCE_CRITERIA_PATTERNS.md` skills before free-styling a story shape; check existing `docs/stories/` for an established pattern before inventing a new one." | `.claude/agents/architect.md` |
| `coder` | Sonnet | Implements one story at a time against an already-precise contract — mechanical relative to architecture | Read, Edit, Write, Bash, Glob, Grep | "Before writing code, load the relevant skill(s) from `.claude/skills/` for the layer you're touching (e.g. `msgspec-domain-modeling`, `concurrency-and-cancellation`) rather than relying on memory of the spec." | `.claude/agents/coder.md` |
| `tester` | Sonnet | Table-driven/Hypothesis/pytest-qt authoring from a precise AC is mechanical once the AC is right | Read, Edit, Write, Bash | "Use the `acceptance-criteria-authoring` and `testing-standard-pyqt` skills to pick the right test pattern (GWT / table / invariant) per AC rather than defaulting to one style." | `.claude/agents/tester.md` |
| `debugger` | Sonnet, escalate to Opus after 2 failed attempts on the same bug | Most failures are mundane; reserve the expensive model for genuinely confusing ones | Read, Edit, Bash, Grep | "Check `docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` and the `error-taxonomy-and-redaction` skill before guessing at error category/handling." | `.claude/agents/debugger.md` |
| `docs-writer` | Haiku | Mechanical, low-risk, current default is right | Read, Edit, Write | "Use the `adr-authoring` skill when writing an ADR; otherwise follow `repository-documentation.md`." | `.claude/agents/docs-writer.md` |
| **`spec-conformance-reviewer`** (NEW) | **Opus** | Addresses the gap identified earlier: generic code review catches bad code, not code that's good Python but silently wrong against the spec. Runs in a **fresh, isolated context** — given only the story file + the exact spec files it cites (not the implementing session's conversation) — and is asked to independently re-derive the acceptance criteria and verify the diff against them line by line | Read, Glob, Grep (read-only — it should never edit) | "Read only the story's cited `spec_clauses:` and the diff under review — deliberately do not load prior conversation context, that's the point of this agent." | `.claude/agents/spec-conformance-reviewer.md` |

Why no separate "architecture-boundary" agent: that job is better done deterministically by
`import-linter` + `pytest-archon` + a hook (see §5) than by another probabilistic agent —
mechanical checks should be mechanical.

---

## 3. Skills (`.claude/skills/*/SKILL.md`)

Retire the 5 current skills' content (keep the names where the topic still exists) and add the
spec-specific ones. Each is "a set of rules + examples Claude loads on demand" per your
description — that matches how Skills actually work (probabilistic trigger via description
match, near-zero cost until invoked).

| Skill | Replaces | Reasoning | Trigger description (for SKILL.md frontmatter) | Location |
|---|---|---|---|---|
| `msgspec-domain-modeling` | (new) | The single most-repeated convention across the whole spec (`Struct(frozen=True, kw_only=True, gc=False)`, `Annotated[..., msgspec.Meta(...)]` constraints, no `dict[str, Any]`) — worth a dedicated, example-heavy skill rather than relying on CLAUDE.md's one-line mention | "Use when defining or modifying any cross-boundary data structure, DTO, or enum in `backend/domain` or any module's `models.py`." | `.claude/skills/msgspec-domain-modeling/` |
| `protocol-first-interfaces` | (new) | The Protocol-vs-ABC decision, the per-module `protocols.py` pattern, and the Gateway pattern (D-R-06 — UI controllers may only hold a per-widget Gateway Protocol) are easy to get subtly wrong | "Use when defining a new interface/Protocol, or when a UI controller needs a backend capability." | `.claude/skills/protocol-first-interfaces/` |
| `three-layer-architecture` | `project-structure.md` rule content (split: see §4) | Where new code belongs (`backend/`/`adapters/`/`ui/`), the import-linter contracts, the `compose.py` rule (only file allowed to wire concrete adapters) | "Use when creating a new module/package, or when unsure which layer a piece of code belongs in." | `.claude/skills/three-layer-architecture/` |
| `concurrency-and-cancellation` | (new) | The single highest-risk area in the whole spec (dispatcher thread, two-level `CancellationToken`, single-inference gate, the "no Qt signal in the Future-completion path" anti-pattern) — worth its own skill given how easy it is to silently reintroduce a deadlock | "Use when touching `backend/benchmark_pipeline`, `backend/concurrency`, `adapters/qt_runnables`, or anything involving `TaskRunner`/cancellation/the inference gate." | `.claude/skills/concurrency-and-cancellation/` |
| `icontract-design-by-contract` | (new) | New, non-trivial requirement (every public `api.py` needs ≥1 contract); the spec is explicit that contracts guard programmer invariants only, never user input — an easy rule to get backwards | "Use when writing or reviewing any module's `api.py` public function." | `.claude/skills/icontract-design-by-contract/` |
| `error-taxonomy-and-redaction` | (new) | The 4-category exception hierarchy + the exactly-two-surfaces redaction rule is referenced constantly and easy to over- or under-apply (e.g. redacting exports, which the spec explicitly forbids) | "Use when raising, catching, or wrapping an exception, or when touching anything secret-adjacent (provider credentials, logs)." | `.claude/skills/error-taxonomy-and-redaction/` |
| `pyside6-spec-ui` | `pyside6-ui` | Same topic, new rules: the `ui/theme` single-stylesheet-authority rule, the MVC-family per-widget module layout, the Gateway-only dependency rule, design tokens instead of literals | "Use when writing or reviewing any PySide6 widget, dialog, or theming code." | `.claude/skills/pyside6-spec-ui/` |
| `story-and-traceability-workflow` | (new, procedural) | Operationalizes `02_STORY_PROCESS.md` so every session writes/updates stories the same way and knows to run `just trace`/`just trace-check` | "Use when creating a story file, or when finishing implementation work that should update traceability." | `.claude/skills/story-and-traceability-workflow/` |
| `acceptance-criteria-authoring` | (new) | The 3 sanctioned AC patterns (GWT / table-driven / invariant) and their anti-patterns | "Use when writing acceptance criteria for a story or tests for an AC." | `.claude/skills/acceptance-criteria-authoring/` |
| `edge-case-coverage` | (new) | Maps `08-I_edge_cases.md` (and the scoped catalogs IMP/EXP/FL/RD/M) to the test tier/pattern each needs, per `06_EDGE_CASE_TO_TEST_MAPPING.md` | "Use when a story cites an `EC-` id, or when deciding what edge-case tests a module needs." | `.claude/skills/edge-case-coverage/` |
| `testing-standard-pyqt` | `write-pytest-tests` | Updated for `pytest-qt`, the shared contract-test-suite pattern (real impl + fake tested against one suite), the `pytest-httpserver` provider wire-stub pattern, per-layer coverage targets | "Use when writing any test." | `.claude/skills/testing-standard-pyqt/` |
| `adr-authoring` | (new) | MADR format, when an ADR is warranted vs. just a story note | "Use when a decision is architecturally significant and costly to reverse." | `.claude/skills/adr-authoring/` |
| `secrets-and-provider-config` | (new) | D-R-18 (env-var-name-only, literal secrets rejected inline) is the single most load-bearing security rule in the app — worth isolating from the general error-taxonomy skill | "Use when touching provider credentials, `ProviderConfig`, Settings import/export, or anything named `api_key`." | `.claude/skills/secrets-and-provider-config/` |
| `sqlite-persistence-conventions` | (new) | Single-writer discipline, additive-only schema evolution, no-JSON-blobs, the crash-recovery sweep pattern | "Use when touching any `backend/persistence/*` store or the SQLite schema." | `.claude/skills/sqlite-persistence-conventions/` |
| `create-mermaid-diagrams` | (unchanged) | Still applicable, spec uses Mermaid throughout | (keep existing trigger) | `.claude/skills/create-mermaid-diagrams/` |
| `project-docs` | `repository-documentation.md`-adjacent | Update for the `docs/stories/`+`docs/adr/`+`docs/v3_specification/` structure | "Use when writing or updating project documentation outside a story file." | `.claude/skills/project-docs/` |

Use the **`skill-creator`** plugin/skill (already available in this environment) to actually
author each `SKILL.md` once this table is approved — it knows the correct frontmatter/structure
conventions, so generation should go through it rather than hand-rolled files.

---

## 4. Rules (`.claude/rules/*.md`)

Rules use path-frontmatter (`paths:`/glob) so they load only when Claude touches matching
files — keep using that mechanism, it's a real Claude Code feature, not a convention you
invented.

| Rule file | Path scope | Reasoning | Replaces |
|---|---|---|---|
| `coding-style.md` | `src/**/*.py` | Full rewrite: msgspec/Protocol conventions, complexity limits, naming — same shape as today, new content | current `coding-style.md` |
| `project-structure.md` | `src/**/*.py`, `pyproject.toml` | The verbatim new `src/` tree, the 3-layer dependency direction, the 5-file module public-surface contract | current `project-structure.md` |
| `concurrency-standard.md` | `src/ollama_llm_bench/backend/**`, `src/ollama_llm_bench/adapters/qt_runnables/**` | New rule — didn't exist before because the old architecture didn't have a dispatcher-thread model | (new) |
| `error-handling-standard.md` | `src/**/*.py` | New rule — the 4-category taxonomy, 3 sanctioned handling shapes, adapter-boundary translation steps | partially overlaps old exception-handling guidance in `coding-style.md`; split out since it's now this detailed |
| `logging.md` | `src/**/*.py` | Rewrite for `structlog`, two-namespace (`run.*`/`app.*`) split, replacing stdlib `logging.getLogger` | current `logging.md` |
| `testing.md` | `tests/**/*.py`, `src/**/tests/**/*.py` | Rewrite: hybrid colocated+top-level layout, contract-test-suite convention, per-layer coverage targets, `pytest-archon`/`import-linter` architecture-test tier | current `testing.md` |
| `external-libraries.md` | `pyproject.toml`, `src/**/*.py` | New approved/banned table: msgspec/psygnal/structlog/icontract/ruamel.yaml/platformdirs/click approved; `pydantic`-on-hot-path, `@dataclass`-for-cross-boundary, `asyncio`/`anyio`/`qasync`, `tenacity`/`stamina`/`purgatory` banned | current `external-libraries.md` |
| `formatting.md` | `*.py`, `pyproject.toml` | Mostly unchanged mechanics, update line-length to 100 and the new rule-set list from `02_TOOLCHAIN.md` | current `formatting.md` |
| `linting.md` | `*.py`, `pyproject.toml` | Add `import-linter` contracts and `pytest-archon` as hard gates, plus `icontract` requirement | current `linting.md` |
| `uv-project.md` | `pyproject.toml`, `uv.lock` | Update build backend to `uv_build`, new dependency table | current `uv-project.md` |
| `pyside6-app-development.md` | `qt_classes/**/*.py`, `ui/**/*.py`, `adapters/**/*.py` | Update for the theme-token system, the Gateway-only dependency rule, `QRunnable`-sets-Future-directly pattern (no Qt signal in the completion path) | current `pyside6-app-development.md` |
| `repository-documentation.md` | `*.md`, `docs/**/*.md` | Update for `docs/stories/`+`docs/adr/`+`docs/v3_specification/` structure, drop references to the old doc set | current `repository-documentation.md` |
| `code-documentation.md` | `src/**/*.py` | Largely unchanged (Google-style docstrings still apply) — minor updates for `icontract` interplay | current `code-documentation.md`, light edit |
| `traceability-and-stories.md` | `docs/stories/**/*.md`, `docs/adr/**/*.md` | New rule — makes the "every story must cite real spec anchors, every story has exactly one coding session" discipline enforceable even when the `story-and-traceability-workflow` skill isn't explicitly invoked | (new) |

---

## 5. Hooks (deterministic enforcement — currently unused in this repo)

Hooks are the one category the current setup doesn't use at all. Given how many of the spec's
rules are exactly the kind of thing a hook enforces better than a prompt ("never do X"), this is
worth adding for this rewrite specifically — and your note about models rationalizing lint
issues as "pre-existing" is precisely the failure mode hooks exist to close, because a hook
can't be talked out of doing its job the way a prompt instruction can.

**The mechanism that actually works for lint/type enforcement** (confirmed against Claude
Code's hook docs, not just assumed): a `PostToolUse` hook should return JSON
`{"decision": "block", "reason": "<the ruff/mypy output>"}` on stdout with exit code `0` —
this is what reliably gets the *reason* back in front of Claude so it makes another edit to
address it, looping until the file is clean. (Plain non-zero exit codes on `PreToolUse` are
reported as less reliable for this — they can just stop Claude rather than prompting it to
fix; reserve bare exit-code-2 for the `Stop` hook below, where it's documented to force
continued work.) Scope every lint/format hook to the file(s) the triggering tool call actually
touched, never the whole repo — that's what keeps "pre-existing issue" from being a legitimate
excuse in the first place, since the hook simply never reports on files you didn't touch.

| Hook | Event | Reasoning | Implementation |
|---|---|---|---|
| Lint-and-block (Python) | `PostToolUse` on `Edit`/`Write` matching `*.py` | Forces fixes rather than allowing silent "pre-existing, skipping" rationalization (your note) — runs `ruff check` (not just `--fix`) and `mypy --strict` on the touched file(s) and blocks with the output as the reason until both are clean | native `settings.json` hook, JSON `decision:block` pattern above |
| Auto-format (Python) | `PostToolUse` on `Edit`/`Write` matching `*.py`, runs after the lint-and-block hook clears | Deterministic formatting should never depend on the model remembering to run it | native hook running `ruff format` |
| Auto-format/lint (Markdown) | `PostToolUse` on `Edit`/`Write` matching `*.md` | Your note: formatting shouldn't be Python-only — keeps `docs/stories/`, `docs/adr/`, and any README content consistent | native hook running `mdformat` (Python-installable, fits the `uv` toolchain) — add as a `uv add --dev` dependency |
| Format/lint (TOML) | `PostToolUse` on `Edit`/`Write` matching `*.toml` | `pyproject.toml` correctness matters a lot in this rewrite (full dependency table, ruff/mypy config) | native hook running `taplo fmt` + `taplo check` |
| Format/lint (YAML) | `PostToolUse` on `Edit`/`Write` matching `*.yml`/`*.yaml` | CI workflow files and any YAML fixtures need the same discipline | native hook running `yamllint` |
| Lint (SQL) | `PostToolUse` on `Edit`/`Write` matching `*.sql` | If the persistence-schema DDL is extracted into versioned `.sql` files (recommended — see `01_PHASE_BREAKDOWN.md` Phase 2) rather than left as inline Python strings, it can be linted the same way as everything else | native hook running `sqlfluff lint`/`sqlfluff format` (dialect `sqlite`) |
| Banned-pattern blocker | `PreToolUse` on `Edit`/`Write` matching `src/**/*.py` | Mechanically blocks the highest-frequency regressions: `@dataclass` in a cross-boundary module, `import asyncio`/`import anyio`/`qasync`, `setStyleSheet(` outside `ui/theme/`, bare `except:` | **hookify** plugin — describe each pattern as a markdown rule with regex, no hand-rolled `hooks.json` needed |
| Secret-literal blocker | `PreToolUse` on `Edit`/`Write` matching files touching provider config | Mechanical backstop for D-R-18 (env-var-NAME-only) — catches a literal `sk-...`/`AIza...`-shaped string before it's ever written | **hookify** plugin, regex rule |
| Spec-folder protection | `PreToolUse` on `Bash` matching `rm`/`git rm` against `docs/v3_specification/**` | The vendored spec must never be touched after Phase 0 — accidental deletion would be catastrophic for this whole process | **hookify** plugin, path-pattern rule |
| Quality-gate bypass blocker (NEW — your note) | `PreToolUse` on `Bash` matching `git commit` with `--no-verify`/`-n`, or matching `git push --force` to a shared branch | Defense in depth for the "never bypass quality gates" CLAUDE.md rule — a frustrated session shouldn't be able to route around a failing hook this way | **hookify** plugin, regex rule on the bash command string |
| Pre-commit-from-hook (NEW — your note) | `PreToolUse` on `Bash` matching `git commit` | Surfaces the same checks the real git pre-commit hook will run (§5a) *during the session*, before the commit is even attempted, rather than letting Claude discover the failure only after — the documented pattern for combining the two systems | native hook running `pre-commit run --files $(git diff --cached --name-only)` and blocking the commit attempt with the output if it fails |
| Traceability auto-refresh | `PostToolUse` on `Edit`/`Write` matching `docs/stories/*.md` | Surfaces a trace gap immediately (while the architect session is still live) instead of discovering it later | native hook running `just trace` |
| Documentation-sync reminder (NEW — your note) | `PostToolUse` on `Edit`/`Write` matching `docs/stories/*.md` where the edit changes `status:` to `done` | Addresses "auto management of CLAUDE.md and all the created documentation" — can't mechanically verify docs are *correct*, but can mechanically remind at the one moment it matters (a story just finished) rather than relying on the session to remember | native hook injecting feedback: "Story marked done — before finishing, update `README.md`/`docs/architecture.md` if the public surface changed, and consider running the `claude-md-management` audit (`/revise-claude-md`) if a new convention was established this story." This is also baked into the `story-and-traceability-workflow` skill's definition-of-done checklist as a non-skippable item, not just the hook |
| End-of-turn check | `Stop` | Runs `ruff check && mypy --strict && import-linter` (fast subset, not full `just check`) before a coding session ends; exit code 2 here is the documented, reliable way to force Claude to keep working rather than stopping with known-broken code | native hook, exit-2-to-continue pattern; guard against infinite loops on out-of-scope failures using the `stop_hook_active` flag the hook payload provides |
| Fresh-session orientation | `SessionStart` | Injects current branch, current phase marker, and open `docs/stories/*.md` with `status: in-progress` — keeps every new session oriented without growing CLAUDE.md | native hook (small script reading a phase-marker file + `git branch --show-current` + a `docs/stories/` scan) |

---

## 5a. Git-level pre-commit framework (separate system from Claude Code hooks)

You're right that this is partly outside "Claude setup" proper, but Claude needs to know it
exists and never route around it — so it's specified here even though the actual
`.pre-commit-config.yaml` gets generated alongside the Phase 0 toolchain work, not the
`.claude/` config itself.

| Concern | Recommendation | Reasoning |
|---|---|---|
| Framework | The standard Python `pre-commit` tool (`pre-commit-config.yaml` + `pre-commit install`), not a hand-rolled `.git/hooks/pre-commit` script | Well-understood, already implied by this project's Python toolchain, easy for a human contributor to reason about too |
| What runs at commit time (fast tier) | `ruff check`, `ruff format --check`, `mypy --strict` (on staged files), `import-linter`, plus the new multi-format linters from §5 (`mdformat --check`, `taplo check`, `yamllint`, `sqlfluff lint`) | Keeps commits fast (seconds, not minutes) — this is the standard fast/slow split for pre-commit setups |
| What runs at push time, not commit time | The full `pytest` suite (incl. `pytest-archon` architecture tests) and `just trace-check` | Full suite is too slow to run on every single commit; a `pre-push` hook (also installed via the `pre-commit` framework's `--hook-type pre-push` support) is the right place for it, so nothing reaches the remote/PR untested |
| Two systems working together | Claude Code's own `PreToolUse(git commit)` hook (§5, "Pre-commit-from-hook" row) calls the *same* `pre-commit run` Claude would otherwise discover failing only after attempting the commit — the git-level hook is still installed and is the actual backstop (it fires even for a manual `git commit` outside any Claude session) | Per the documented pattern: "the useful pattern is to run pre-commit from a Claude Code hook, so issues surface immediately during the session" — the two are complementary, neither replaces the other |
| Bypass policy | `--no-verify` is banned (CLAUDE.md rule + the hookify blocker in §5) | Otherwise the whole point of this section is moot |

---

## 6. Plugins and MCP servers — what to install vs. skip

Cross-referencing your pasted marketplace list against this project's actual needs (Python +
PySide6 desktop app, no web frontend, no cloud-platform integration, no CRM/ticketing need).

### Recommended

| Plugin/MCP | What it gives you | Why it fits this project | Install |
|---|---|---|---|
| `claude-md-management` | `claude-md-improver` skill (audits CLAUDE.md quality) + `/revise-claude-md` (captures session learnings) | Keeps CLAUDE.md from bloating back up over a many-month, many-phase rewrite — directly addresses the "over-specified CLAUDE.md gets ignored" failure mode | `/plugin install claude-md-management@claude-plugins-official` |
| `hookify` | Markdown-rule-driven hook generator (no hand-written `hooks.json`) | The implementation mechanism for §5's banned-pattern/secret/spec-folder hooks | `/plugin install hookify@claude-plugins-official` |
| `security-guidance` | 3-layer security review (pattern match on edit, model review per turn, deep agentic review on commit) | This app's central security concern is exactly what this plugin targets: secret handling, the env-var-only credential rule, the redaction boundary | `/plugin install security-guidance@claude-plugins-official` |
| `pr-review-toolkit` | 6 specialized review agents — notably `silent-failure-hunter` and `type-design-analyzer` | Directly matches the spec's strict error-handling standard (no silent catches) and strict typing standard (mypy --strict, msgspec constraints) | `/plugin install pr-review-toolkit@claude-plugins-official` |
| `context7` (MCP) | Live, version-current docs for any library, on request ("use context7") | This stack leans on libraries the base model may know shallowly or have stale knowledge of (`msgspec`, `psygnal`, `icontract`, `ruamel.yaml`, `pytest-archon`, `import-linter`, `pytest-qt`) — and the toolchain doc mandates tracking latest-stable versions, so current docs matter more than usual | add to `.mcp.json`: `npx -y @upstash/context7-mcp` |
| `skill-creator` | Scaffolds correctly-structured `SKILL.md` files | Already available in this environment — use it to generate §3's skills rather than hand-writing frontmatter | already installed |
| `commit-commands` | `/commit`, `/push`, PR-creation workflow commands | Convenience for the per-story/per-phase commit cadence the plan already prescribes | `/plugin install commit-commands@claude-plugins-official` |
| `superpowers` (upgraded from "trial" — your note) | TDD red-green-refactor discipline + "subagent-driven development with built-in code review" | You've used it successfully on another project and report it gets invoked more reliably than custom skills/agents — that's a real, observed signal worth acting on rather than my earlier abstract caution. Install from the start; use its subagent-driven-development-with-review skill as the actual mechanism inside the `coder`→`tester` loop (it's spec-agnostic, so it composes with the story/traceability process rather than competing with it the way Spec Kit would). Still worth a quick check after Phase 0 that its instructions don't pull against the "one story per session" / "cite spec_clauses" discipline — but start with it on, not off. | `/plugin marketplace add obra/superpowers-marketplace` then `/plugin install superpowers@superpowers-marketplace` |
| `pyright-lsp` (upgraded — your question) | Real-time type diagnostics + semantic go-to-definition/find-references, replacing grep-based code search | Direct answer to your question: yes, this is worth using, and it's not the kind of thing Claude "ignores" the way an optional skill can be — Claude Code added **native LSP protocol support** (official changelog, v2.0.74); the plugin installs the `pyright` binary and wires it in, after which diagnostics-after-edit and reference lookups happen as part of Claude's normal tool use, not as a skill it has to remember to invoke. Given this rewrite spans 62 modules across 3 layers, reliable find-references/go-to-definition meaningfully reduces the chance of an inconsistent multi-file refactor — worth installing from Phase 0. It complements, not replaces, `mypy --strict` (still the CI authority per the toolchain doc) | `/plugin install pyright-lsp@claude-plugins-official` (requires `pyright` itself available, e.g. `uv add --dev pyright`) |

### Optional / trial only

| Plugin | Why it's not an automatic yes |
|---|---|
| `code-simplifier` | Good for a periodic cleanup pass, but running it mid-story risks scope creep beyond the story's diff — use it as an explicit end-of-phase pass, not per-story. |
| `github` (MCP) | Only useful if you want Claude Code itself opening PRs/issues; not required for a solo-dev branch workflow. |
| `session-report` | Pure observability into token/cost usage — convenient, not load-bearing. |

### CLI tools needed for the multi-format hooks (not Claude plugins — regular dev dependencies)

| Tool | Used by | Install |
|---|---|---|
| `mdformat` | Markdown auto-format hook (§5) | `uv add --dev mdformat` |
| `taplo` | TOML format/lint hook (§5) | install the `taplo` CLI binary (Rust, via `cargo install taplo-cli` or a release binary — not a `uv` package) |
| `yamllint` | YAML lint hook (§5) | `uv add --dev yamllint` |
| `sqlfluff` | SQL lint/format hook (§5), if/when DDL is extracted into `.sql` files | `uv add --dev sqlfluff` |
| `pre-commit` | The git-level framework (§5a) | `uv add --dev pre-commit`, then `pre-commit install --hook-type pre-commit --hook-type pre-push` |

### Not recommended

| Plugin | Reason |
|---|---|
| `feature-dev` | Its `/feature-dev` 7-phase workflow (explore→architect→implement→review) duplicates the bespoke `investigator→architect→coder→tester→spec-conformance-reviewer` pipeline already designed around this exact spec's story format — running both in parallel reintroduces the "two competing frameworks" risk already flagged for Spec Kit. |
| `ralph-loop` | Encourages autonomous repeat-until-done looping; the plan deliberately wants a human checkpoint at every phase boundary and one-story-per-session discipline — this plugin's whole premise cuts against that. |
| `qt-development-skills` | Targets Qt **C++/QML** code review and QML authoring — this app is Python + PySide6 **Qt Widgets**, a different binding and a different UI paradigm entirely; not applicable. |
| `explanatory-output-style` / `learning-output-style` | Educational/teaching modes — irrelevant to unattended implementation work. |
| `claude-code-setup` | Could not confirm this plugin exists or what it does via search — skip until/unless you can point me at it directly. |
| Everything else in your pasted list (chrome-devtools, playwright, frontend-design, all non-Python LSPs, every SaaS/CRM/cloud-platform/payments/data-warehouse connector) | No surface area in this project — a single-window offline-first PySide6 desktop app with no web frontend, no cloud infra, and no third-party SaaS integration. |

---

## Next step

Once you approve/edit this table, I'll generate, in order: the rewritten `CLAUDE.md` → the
rules (§4) → the skills (§3, via `skill-creator`) → the agent definitions (§2) → the
`settings.json` hooks + hookify rule files (§5) → the `.pre-commit-config.yaml` (§5a) → the
`.mcp.json` entry for `context7`. I won't start on `docs/stories/` content itself (that's the
separate implementation-plan work in `01_PHASE_BREAKDOWN.md`/`02_STORY_PROCESS.md`), and I
won't run `pre-commit install` or any plugin-install commands myself — those are local commands
you run, I'll just leave the config files ready for them.
