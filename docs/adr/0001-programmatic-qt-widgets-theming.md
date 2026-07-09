# ADR-0001 — Build the UI programmatically with Qt Widgets and Python design tokens

**Status:** accepted
**Date:** 2026-07-09
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-P-001, decision D-020

## Context and problem statement

The application is a multi-pane desktop tool built on the Qt for Python binding. The user
interface must be themeable (at minimum a light and a dark theme), consistent across many
widgets, testable headlessly in CI, and maintainable by an AI implementation agent working
module by module. Qt offers two UI construction approaches — a declarative markup language and
programmatic widget construction — and two styling approaches — stylesheet text files and
programmatic styling. The entire binding research and technical-decision corpus that grounds
this project is built around programmatic Qt Widgets; the declarative markup path is
unsupported by that corpus. Styling needs a single source of truth so that themes stay
consistent and an agent cannot drift styling logic across the codebase. How should the UI be
constructed and styled?

## Decision drivers

- Headless testability in CI with no display.
- A single, type-checkable source of truth for visual design values.
- Predictable, non-drifting styling across many widgets maintained by an AI agent.
- Alignment with the project's grounding binding-research corpus.

## Considered options

- Option A — Declarative Qt markup (QML / Qt Quick) for the UI.
- Option B — Programmatic Qt Widgets with Python design tokens and a single theme module.
- Option C — Programmatic Qt Widgets with unrestricted per-widget stylesheet calls.

## Decision outcome

Chosen option: **Option B**, because it keeps one theme module as the sole generator and
applier of styling from typed Python design tokens, matches the project's grounding corpus, and
lets an architecture test forbid stylesheet drift. Build the user interface programmatically
with Qt Widgets. Do not use the declarative Qt markup language. Express all visual design
values — colours, spacing, typography, role definitions — as typed Python objects (design
tokens) in a single theme module. A single theme module is the only place that generates and
applies styling from those tokens; it compiles application-level styling at theme-switch time.
Direct per-widget stylesheet calls are forbidden outside the theme module; widgets express
their styling intent by setting a role property that the theme module interprets. Stylesheet
text files are not a source of truth — if any stylesheet text exists, it is generated from the
Python tokens by the theme module.

### Consequences

- Positive — One theme module owns all styling; themes stay internally consistent and a live
  theme switch is a single, well-defined operation. Design tokens as typed Python objects are
  checkable by the type checker and validatable at startup (for example for theme parity and
  contrast). The declarative-markup toolchain, its tooling, and its testing limitations are
  avoided; widgets are plain Python and test cleanly headlessly. An architecture test can forbid
  stylesheet calls outside the theme module, preventing styling drift.
- Negative — Programmatic widget construction is more verbose than declarative markup for large
  static layouts. All contributors must learn the role-property convention rather than writing
  inline styling. The theme module becomes a central, carefully reviewed component; changes to
  it are higher-impact.
- Neutral — Every widget module depends on `ui/theme` for role properties instead of authoring
  its own stylesheet fragment.

## Pros and cons of the options

### Option A — Declarative Qt markup (QML / Qt Quick)

- Good — Concise for large static layouts; a common Qt authoring style.
- Bad — Diverges from the project's entire grounding binding-research and technical-decision
  corpus, which is Qt-Widgets-based; its tooling and testing guidance would not transfer.

### Option B — Programmatic Qt Widgets with Python design tokens

- Good — One validated, type-checked source of styling truth; headless-testable; enforceable by
  an architecture test.
- Bad — More verbose for large static layouts; requires contributors to learn the role-property
  convention.

### Option C — Programmatic Qt Widgets with unrestricted per-widget stylesheet calls

- Good — No central theme module to maintain; each widget is locally self-contained.
- Bad — Scatters styling logic across the codebase, makes a consistent theme switch impossible
  to guarantee, and cannot be enforced by an architecture test.

## Links

- Related ADRs: —
- Spec clauses: `08_Cross_Cutting/08-A_architecture_principles.md`,
  `08_Cross_Cutting/08-D_color_palette_and_typography.md`,
  `15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md#adr-p-001--programmatic-qt-widgets-ui-with-python-design-tokens`
- Stories: —
