---
id: STORY-049
title: Provide the design-token containers, stylesheet generator, and palette builder for the theme module
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#1-token-system-and-non-negotiable-rules
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#3-dark-theme-colour-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#4-light-theme-colour-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#5-verdict-palette
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#6-health-palette
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#7-font-chains
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#8-font-size-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#9-spacing-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#10-radius-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#11-border-and-focus-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#12-shadow-and-motion-tokens
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/theme/
acceptance_criteria:
  - STORY-049-AC-1
  - STORY-049-AC-2
  - STORY-049-AC-3
  - STORY-049-AC-4
  - STORY-049-AC-5
  - STORY-049-AC-6
  - STORY-049-AC-7
depends_on: []
adrs:
  - ADR-0001
owner: coder
estimate: L
---

# STORY-049 — Provide the design-token containers, stylesheet generator, and palette builder for the theme module

## Goal

Deliver the foundation of the single styling authority: two immutable design-token containers
(Dark and Light), each carrying the full colour, verdict, health, typography, spacing, radius,
border, focus, shadow, and motion token set the interface is permitted to use, plus the QSS
generator and `QPalette` builder that compile those tokens into the application-level styling
the rest of the UI depends on. This is the hard gate every Phase 10 widget builds on: after
this story a widget can express appearance by naming a role, and exactly one module resolves
that role to a concrete value.

## In scope

- Two frozen token containers in `ui/theme/` — one Dark, one Light — carrying every token role
  from 08-D §3–§12: the 23 colour roles, the verdict and health semantic palettes, the
  platform-aware sans/mono font chains, the font-size and weight scale, and the spacing,
  radius, border, focus, shadow, and motion tokens.
- A `build_stylesheet(container)` QSS generator that compiles a container into the
  application-level Qt stylesheet, targeting dynamic-property role selectors (for example a
  `primary-button` role) rather than embedding per-widget literals.
- A `build_palette(container)` function that constructs the matching `QPalette`.
- A role-resolution accessor other modules (charts, badges, dots) use to read a colour by role
  for the active theme.
- The platform-aware font-chain selection at container-construction time.

## Out of scope

- Theme switching, live OS colour-scheme tracking, the theme-changed notification, the WCAG
  contrast verification, reduced-motion, and high-contrast handling — owned by STORY-050.
- The shared visual primitives (`BadgeLabel`, `HealthDot`, `MultiCheckFilterButton`) that
  consume these tokens — owned by STORY-051.
- Applying the compiled stylesheet/palette to the live `QApplication` at startup — wired by
  `compose.py` in a later phase; this story delivers the pure builders it will call.

## Spec inputs

- `08-D §1 (#1-token-system-and-non-negotiable-rules)` — tokens are immutable typed containers;
  one module owns all styling; no `.qss` files; widgets reference roles, never literals; both
  themes are mandatory and complete.
- `08-D §3 (#3-dark-theme-colour-tokens)` — the exact Dark value of every one of the 23 colour
  roles.
- `08-D §4 (#4-light-theme-colour-tokens)` — the exact Light value of every colour role (tuned
  independently, not an inversion of Dark).
- `08-D §5 (#5-verdict-palette)` and `08-D §6 (#6-health-palette)` — the verdict and health
  display states and the base colour role each maps to per theme.
- `08-D §7 (#7-font-chains)` — the per-`PlatformKind` sans/mono chains, the platform-aware
  selection rule, and the ban on `QFontDatabase` per-family probing.
- `08-D §8–§12 (#8-font-size-tokens, #9-spacing-tokens, #10-radius-tokens, #11-border-and-focus-tokens, #12-shadow-and-motion-tokens)` — the exact scalar values of the
  font-size, weight, spacing, radius, border, focus, shadow, and motion tokens.
- `08-D §16 (#16-the-theme-module-contract)` — the theme module's public obligations: hold the
  containers, resolve roles, build and apply styling, and be the only code permitted to call
  `setStyleSheet()`.

## Design constraints

- `ui/theme/` is the only module permitted to call `setStyleSheet()` and the only module
  permitted to build styling from raw tokens; an AST/`pytest-archon` architecture test fails the
  build on any `setStyleSheet` reference outside `ui/theme/` (ADR-0001, 08-D §16).
- Token containers are `msgspec.Struct(frozen=True, kw_only=True)`; there are no `.qss` files on
  disk anywhere in the source tree.
- Font-chain selection branches only on the platform (`sys.platform` / `QSysInfo`, equivalently
  the Platform Detector's `PlatformKind`); per-family probing through `QFontDatabase` is
  forbidden (08-D §7.1, §7.5). The `UNKNOWN` chain is a defensive fallback only.
- No `asyncio`; the module imports PySide6, the standard library, and `msgspec` only.

## Acceptance criteria

### STORY-049-AC-1

For each `(theme, colour role)` pair enumerated in 08-D §3 (Dark) and §4 (Light), the theme's
token container resolves that role to the exact value listed in the specification — every one of
the 23 colour roles, in both themes, with no substitution (table-driven, total over the §3 and
§4 role tables).

### STORY-049-AC-2

For each verdict display state in 08-D §5 and each health display state in 08-D §6, the token
container resolves the state to the base colour role the specification assigns it, in both the
Dark and the Light theme (table-driven, total over the §5 and §6 state rows).

### STORY-049-AC-3

For each `PlatformKind` value (`MACOS`, `WINDOWS`, `LINUX`, `UNKNOWN`), the container's resolved
`font.sans` and `font.mono` chains equal the ordered family list the 08-D §7.2 table prescribes
for that platform (table-driven, total over the four platform rows).

### STORY-049-AC-4

For each scalar token defined in 08-D §8–§12 — the font sizes `xs`–`xl`, the two weights
(`regular` = 400, `semibold` = 600), the spacing tokens `xs`–`2xl`, the radius tokens
`sm`/`md`/`lg`, `border.width`, and the motion tokens `fast` (120 ms) and `standard` (200 ms) —
the container resolves the token to the exact value the specification lists (table-driven, total
over the §8–§12 scalar tokens).

### STORY-049-AC-5

Given a token container, when `build_stylesheet(container)` is called, then it returns a QSS
string that selects on dynamic-property role selectors (for example the `primary-button` role)
and carries the container's role-resolved colour values, so a widget receives its appearance by
setting a role property rather than embedding any colour literal.

### STORY-049-AC-6

Given a token container, when `build_palette(container)` is called, then the returned `QPalette`
maps its `Window`, `Base`, `Text`, and `Highlight` roles to the container's resolved
`bg.window`, `bg.input`, `text.primary`, and `primary.base` values respectively.

### STORY-049-AC-7

For every colour role defined in either token container, both the Dark and the Light container
define that same role — the two containers have identical role coverage (theme parity), so no
role resolves in one theme and is absent in the other.

## Test plan

- STORY-049-AC-1 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/theme/tests/test_color_tokens.py`,
  `test_colour_role_resolves_to_spec_value_per_theme`.
- STORY-049-AC-2 — table-driven unit, same file,
  `test_verdict_and_health_states_map_to_spec_base_role`.
- STORY-049-AC-3 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/theme/tests/test_font_chains.py`,
  `test_font_chain_matches_spec_per_platform`.
- STORY-049-AC-4 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/theme/tests/test_scalar_tokens.py`,
  `test_scalar_token_resolves_to_spec_value`.
- STORY-049-AC-5 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py`,
  `test_stylesheet_targets_role_selectors_with_resolved_values`.
- STORY-049-AC-6 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/theme/tests/test_build_palette.py`,
  `test_palette_maps_core_roles_to_resolved_values`.
- STORY-049-AC-7 — unit (property/invariant), colocated
  `src/ollama_llm_bench/ui/theme/tests/test_theme_parity.py`,
  `test_dark_and_light_containers_have_identical_role_coverage`.

## Notes

- **AC-1's "23 colour roles" vs. the 30-row §3/§4 tables.** This story's AC-1 text (and the two
  other "23 colour roles" mentions above) undercounts the specification. `08-D §3` (Dark) and
  `08-D §4` (Light) each enumerate 30 colour roles per theme — 23 "base" roles plus the six
  `.fill` variants (`success.fill`, `warning.fill`, `error.fill`, `info.fill`, `muted.fill`, and
  the implicit sixth) plus `shadow`/`overlay`. AC-1's own operative clause — "table-driven,
  total over the §3 and §4 role tables" — is the authoritative instruction, so the
  implementation defines, resolves, and tests all 30 roles per theme (not a truncated 23), to
  avoid silently under-covering the spec. `ColorTokens` in
  `src/ollama_llm_bench/ui/theme/models.py` and the parametrized cases in
  `src/ollama_llm_bench/ui/theme/tests/test_color_tokens.py` (60 cases total: 30 roles × 2
  themes) reflect this. The "23" figure in this story's prose is stale and should be read as
  "30" wherever it appears.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-049.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/theme/`.
- [ ] An architecture test confirms `ui/theme/` is the only module referencing `setStyleSheet`,
  that the token containers are frozen `msgspec.Struct`, and that the module imports no
  `asyncio` and does no `QFontDatabase` per-family probing.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
