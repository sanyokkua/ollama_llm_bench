---
name: create-mermaid-diagrams
description: Use when creating or updating an architecture, flow, sequence, state-machine, or entity-relationship diagram.
---

# Creating Mermaid Diagrams

All technical diagrams in this project — flow, state, sequence, entity-relationship, component — are
Mermaid. (UI surfaces such as windows, widgets, and dialogs are HTML mockups instead; that's a separate
concern.) This skill covers the four diagram types most relevant here: flowcharts for use-case flows,
sequence diagrams for request/response interactions, `stateDiagram-v2` for lifecycle state machines, and
`erDiagram` sketches for related tables.

## Validation checklist

Before treating a diagram as done:

- [ ] **Does it parse?** Mentally (or actually) run it through a Mermaid renderer. A single stray
      unescaped character (an unquoted `(`, `|`, or `#` inside a label) is the most common parse failure.
- [ ] **Are node labels readable?** Use `["Quoted label text"]` for any label containing spaces, slashes,
      or punctuation. Keep labels short — wrap long ones with `<br/>` rather than letting them overflow.
- [ ] **Is direction sensible?** `TD`/`TB` (top-down) for hierarchies and most flows; `LR` (left-right) for
      pipelines and sequences of stages; pick whichever reads naturally for the content, not by habit.
- [ ] **No orphan nodes.** Every node declared has at least one edge in or out, unless it is deliberately a
      single isolated start/end marker.
- [ ] **No duplicate node IDs with different meanings.** Reusing an ID silently merges two concepts into
      one node.

## Flowchart — a use-case flow

```mermaid
flowchart TD
    START["User selects a STOPPED run<br/>in the Resume Widget"]
    CLICK["User clicks Resume"]
    GATE{"Gate acquired?<br/>(try_acquire BENCHMARK_RUN)"}
    REJECT["No-op — gate already held"]
    RESET["Reset RUNNING_INFERENCE rows<br/>to PENDING"]
    CONTINUE["Pipeline continues from<br/>first non-terminal row"]

    START --> CLICK --> GATE
    GATE -->|"None returned"| REJECT
    GATE -->|"lease acquired"| RESET --> CONTINUE
```

## Sequence diagram — a request/response interaction

```mermaid
sequenceDiagram
    participant UI as Provider Edit Dialog
    participant Client as LLMClient
    participant Stub as Provider HTTP endpoint

    UI->>Client: test_inference(model, prompt)
    Client->>Stub: POST /v1/chat/completions (stream=true)
    Stub-->>Client: SSE chunk 1 (delta)
    Stub-->>Client: SSE chunk N (delta)
    Stub-->>Client: SSE terminal sentinel
    Client-->>UI: InferenceTestResult(outcome=SUCCESS, latency_ms=842)
```

## State diagram — a lifecycle (e.g. the benchmark run state machine)

```mermaid
stateDiagram-v2
    [*] --> RUNNING: Start clicked, gate acquired
    RUNNING --> PAUSED: pause requested at a phase boundary
    PAUSED --> RUNNING: resume requested
    RUNNING --> STOPPED: stop requested, graceful shutdown completes
    RUNNING --> INCOMPLETE: process killed mid-run
    RUNNING --> COMPLETED: all tasks reach a terminal status
    RUNNING --> FAILED: fatal pipeline error
    STOPPED --> [*]
    COMPLETED --> [*]
    FAILED --> [*]
    INCOMPLETE --> RUNNING: resumed on next launch
```

## ER diagram — a couple of related tables

```mermaid
erDiagram
    BENCHMARK_RUNS ||--o{ BENCHMARK_RESULTS : "has many"
    BENCHMARK_RUNS ||--o{ BENCHMARK_TASKS : "snapshots"
    BENCHMARK_TASKS ||--o{ BENCHMARK_RESULTS : "graded by"

    BENCHMARK_RUNS {
        int run_id PK
        text run_mode
        text status
    }
    BENCHMARK_TASKS {
        int run_id FK
        text task_id PK
        text question
    }
    BENCHMARK_RESULTS {
        int result_id PK
        int run_id FK
        text task_id FK
        text status
        text verdict
    }
```

## Common pitfalls

| Pitfall | Fix |
|---|---|
| Unquoted label with parentheses or pipes breaks parsing | Wrap the label text in `"double quotes"` inside the brackets |
| A `stateDiagram-v2` transition with no label | Add a short label naming the trigger — an unlabeled arrow tells the reader nothing |
| Mixing diagram types in one block | One `mermaid` code fence per diagram; never combine `flowchart` and `sequenceDiagram` syntax |
| A flowchart that reads bottom-to-top because of `BT` direction by habit | Default to `TD` unless the content is genuinely a left-to-right pipeline (`LR`) |
| An `erDiagram` cardinality that doesn't match the actual foreign key | Match `||--o{` (one-to-many) vs `}o--o{` (many-to-many) to the real schema, not a guess |

## Cross-references

- The `project-docs` skill — where a Mermaid system-context diagram belongs in `README.md`.
- `docs/v3_specification/00_Foundation/01_README.md` — the documentation convention this project follows: all technical diagrams are Mermaid, all UI mockups are HTML.
