# Architecture

This directory holds the project's own architecture documentation, written as the
implementation proceeds.

Until that documentation exists, the authoritative architecture source is the vendored
specification at [`docs/v3_specification/`](../v3_specification/) — in particular
[`16_Engineering_Standards/01_PROJECT_STRUCTURE.md`](../v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md)
(repository layout, module framework, import boundaries) and
[`08_Cross_Cutting/08-A_architecture_principles.md`](../v3_specification/08_Cross_Cutting/08-A_architecture_principles.md)
(cross-cutting architectural rationale). Accepted architecture decisions are recorded in
[`docs/adr/`](../adr/).

This directory is populated with derived architecture documentation (diagrams, module maps) as
stories land; see `docs/v3_specification/14_Process_and_Traceability/` for how implementation
work is tracked. It starts empty at Phase 0 — see
`docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md` Section 2 for its place
in the `docs/` tree, and Phase 12 of
`docs/reference_planning_docs/01_PHASE_BREAKDOWN.md` for when this directory's own content is
first written.
