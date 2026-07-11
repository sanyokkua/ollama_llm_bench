# Architecture Decision Records

Index of all Architecture Decision Records (ADRs) for Ollama LLM Bench. Format and lifecycle:
`docs/v3_specification/14_Process_and_Traceability/04_ADR_FORMAT.md`.

| ADR                                                                   | Title                                                                                              | Status   | Supersedes | Superseded by |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | -------- | ---------- | ------------- |
| [ADR-0001](0001-programmatic-qt-widgets-theming.md)                   | Build the UI programmatically with Qt Widgets and Python design tokens                             | accepted | —          | —             |
| [ADR-0002](0002-scoped-reactive-stores-and-event-bus.md)              | Adopt scoped reactive state stores plus a typed event bus                                          | accepted | —          | —             |
| [ADR-0003](0003-uv-build-and-unsigned-distribution.md)                | Use the uv build backend and distribute unsigned, checksum-verified binaries                       | accepted | —          | —             |
| [ADR-0004](0004-single-db-writer-owned-by-app-settings-store.md)      | House the single-writer connection manager and schema lifecycle in app-settings                    | accepted | —          | —             |
| [ADR-0005](0005-llmclient-chat-takes-mandatory-cancellation-token.md) | Thread the CancellationToken into LLMClient.chat/chat_stream as a mandatory keyword-only parameter | accepted | —          | —             |
| </content>                                                            |                                                                                                    |          |            |               |
