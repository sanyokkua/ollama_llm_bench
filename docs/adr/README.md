# Architecture Decision Records

Index of all Architecture Decision Records (ADRs) for Ollama LLM Bench. Format and lifecycle:
`docs/v3_specification/14_Process_and_Traceability/04_ADR_FORMAT.md`.

| ADR                                                                                 | Title                                                                                                      | Status     | Supersedes | Superseded by |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------- | ---------- | ------------- |
| [ADR-0001](0001-programmatic-qt-widgets-theming.md)                                 | Build the UI programmatically with Qt Widgets and Python design tokens                                     | accepted   | —          | —             |
| [ADR-0002](0002-scoped-reactive-stores-and-event-bus.md)                            | Adopt scoped reactive state stores plus a typed event bus                                                  | accepted   | —          | —             |
| [ADR-0003](0003-uv-build-and-unsigned-distribution.md)                              | Use the uv build backend and distribute unsigned, checksum-verified binaries                               | accepted   | —          | —             |
| [ADR-0004](0004-single-db-writer-owned-by-app-settings-store.md)                    | House the single-writer connection manager and schema lifecycle in app-settings                            | accepted   | —          | —             |
| [ADR-0005](0005-llmclient-chat-takes-mandatory-cancellation-token.md)               | Thread the CancellationToken into LLMClient.chat/chat_stream as a mandatory keyword-only parameter         | accepted   | —          | —             |
| [ADR-0006](0006-shared-inference-progress-helper.md)                                | Extract the shared inference-progress helper into backend/inference_progress/                              | accepted   | —          | —             |
| [ADR-0007](0007-derive-run-registry-and-workspace-store-surfaces-from-consumers.md) | Derive the RunRegistryStore and WorkspaceStore protocol surfaces from their Phase-8 consumers              | accepted   | —          | —             |
| [ADR-0008](0008-exclude-reduced-motion-and-high-contrast-preferences.md)            | Exclude OS reduced-motion and high-contrast preferences from the theme module                              | superseded | —          | ADR-0012      |
| [ADR-0009](0009-inference-progress-event-tokens-estimated-field.md)                 | Add `tokens_estimated` to `InferenceProgressEvent` as an additive DTO field                                | accepted   | —          | —             |
| [ADR-0010](0010-phase-11-composition-root-and-entry-point-structure.md)             | Structure the Phase-11 composition root, entry point, and launch/quit sequencing                           | accepted   | —          | —             |
| [ADR-0011](0011-testing-standard-extensions-live-tier-and-screenshot-harness.md)    | Extend the testing standard with an env-gated live tier and a screenshot/mockup-review harness             | accepted   | —          | —             |
| [ADR-0012](0012-honor-os-reduced-motion-and-high-contrast-preferences.md)           | Honor the OS reduced-motion and high-contrast preferences to meet the release-blocking floor               | accepted   | ADR-0008   | —             |
| [ADR-0013](0013-dedicated-lightweight-circuit-breaker-probe.md)                     | Issue a dedicated lightweight liveness call as the circuit breaker's post-cooldown probe                   | accepted   | —          | —             |
| [ADR-0014](0014-house-ui-adapter-gateways-in-one-adapters-module.md)                | House the seven concrete UI adapter gateways in one new `adapters/ui_gateways/` module                     | accepted   | —          | —             |
| [ADR-0015](0015-deliver-blocking-settings-gateway-results-via-callback.md)          | Return immediately from every network-bound `SettingsGateway` method and deliver its result asynchronously | accepted   | —          | —             |
| [ADR-0016](0016-probe-embedding-completion-callback.md)                             | Give `probe_embedding()` a completion callback alongside `ReadinessService`'s emit-on-change state update  | accepted   | —          | —             |
| [ADR-0017](0017-canonical-gateway-boundary-dtos-in-adapters-ui-gateways.md)         | Make `adapters/ui_gateways/` the single declaration point for the gateway-boundary DTOs                    | accepted   | —          | —             |
