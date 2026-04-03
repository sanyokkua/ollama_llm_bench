---
name: create-mermaid-diagrams
description: Mermaid diagram syntax rules and patterns for architecture docs. Use when creating or updating any Mermaid diagram in documentation files.
allowed-tools: Read, Write, Edit
---

# Create Mermaid Diagrams

Invoke when creating or updating Mermaid diagrams — architecture overviews, sequence diagrams, class hierarchies, state machines, pipeline flows.

---

## Golden Rules

1. **Never put comments inline** — `%%` comments must be on their own line
2. **IDs are alphanumeric only** — no spaces, hyphens, or special chars in IDs
3. **Quote labels with special chars** — `["Step 1: Init"]` not `[Step 1: Init]`
4. **Never use reserved words as IDs** — `end`, `class`, `subgraph`, `graph`, `default`
5. **IDs never start with numbers** — use `step1` not `1stStep`

```
CORRECT:
%% This is a comment
A["Step 1: Init"] --> B["Step 2: Process"]

WRONG (inline comment causes parse error):
A --> B %% This breaks rendering
```

---

## Diagram Type Quick Pick

| Goal | Use |
|------|-----|
| Process flow / pipeline | `flowchart TD` or `flowchart LR` |
| Class hierarchy / interfaces | `classDiagram` |
| Method call sequence | `sequenceDiagram` |
| State machine / lifecycle | `stateDiagram-v2` |
| Project timeline | `gantt` |

---

## Flowchart (Most Common)

```mermaid
flowchart TD
    %% Node shapes
    A[Rectangle]
    B(Rounded)
    C{Diamond decision}
    D[(Database)]
    E((Circle))

    %% Connections
    A --> B
    B --> C
    C -->|Yes| D
    C -->|No| E

    %% Subgraph grouping
    subgraph phase1["Phase 1: Input"]
        A
        B
    end
```

---

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as PySide6 UI
    participant Ctrl as Controller
    participant Svc as BenchmarkFlowApi
    participant LLM as OllamaApi

    U->>UI: Start benchmark
    UI->>+Ctrl: on_start_clicked()
    Ctrl->>+Svc: start_execution(run_id)
    Svc->>+LLM: inference(model, prompt)
    LLM-->>-Svc: InferenceResponse
    Svc-->>-Ctrl: emit progress
    Ctrl-->>-UI: update table
    UI-->>U: Show results
```

---

## Class Diagram

```mermaid
classDiagram
    class DataApi {
        <<abstract>>
        +create_benchmark_run(BenchmarkRun) int
        +retrieve_benchmark_runs() list
        +update_benchmark_result(BenchmarkResult) None
    }

    class SqLiteDataApi {
        +create_benchmark_run(BenchmarkRun) int
        +retrieve_benchmark_runs() list
    }

    DataApi <|-- SqLiteDataApi : implements
```

---

## State Diagram

```mermaid
stateDiagram-v2
    direction LR
    [*] --> NotCompleted
    NotCompleted --> Benchmarking: start_execution
    Benchmarking --> WaitingForJudge: inference done
    WaitingForJudge --> Completed: judging done
    Benchmarking --> Failed: error
    WaitingForJudge --> Failed: error
    Completed --> [*]
```

---

## Special Characters in Labels

```mermaid
flowchart LR
    A["Function#40;param#41;"]
    B["Array#91;0#93;"]
    C["Map#123;key#125;"]
```

| Character | Entity |
|-----------|--------|
| `(` `)` | `#40;` `#41;` |
| `[` `]` | `#91;` `#93;` |
| `{` `}` | `#123;` `#125;` |

---

## Project-Specific Diagrams

### System Context

```mermaid
flowchart TD
    User((User))
    App["Ollama LLM Bench<br/>PySide6 Desktop App"]
    Ollama["Ollama Server<br/>localhost:11434"]
    DB[(SQLite Database)]
    Dataset["YAML Dataset<br/>Benchmark Tasks"]

    User -->|interact| App
    App -->|inference requests| Ollama
    App -->|read/write results| DB
    App -->|load tasks| Dataset
    Ollama -->|LLM responses| App
```

### Benchmark Pipeline

```mermaid
flowchart LR
    subgraph init["Initialize"]
        LoadTasks["Load Tasks"]
        CreateRun["Create Run"]
    end

    subgraph bench["Benchmark Stage"]
        WarmUp["Warm Up Model"]
        Inference["Run Inference"]
    end

    subgraph judge["Judge Stage"]
        JudgeWarmUp["Warm Up Judge"]
        Evaluate["Evaluate Response"]
    end

    subgraph results["Results"]
        Score["Compute Scores"]
        Display["Display Summary"]
    end

    init --> bench --> judge --> results
```

---

## Validation Checklist

- [ ] No inline `%%` comments (all on own lines)
- [ ] All IDs alphanumeric, no reserved words
- [ ] Labels with `:`, `-`, `(`, etc. are quoted
- [ ] `subgraph` blocks have matching `end`
- [ ] Direction declared (`TD`, `LR`, etc.) for flowcharts

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Parse error after `-->` | Inline comment | Move `%%` to its own line |
| Diagram doesn't render | Reserved word as ID | `end` → `endNode`, `class` → `classNode` |
| Syntax error on `(` | Unquoted parens in label | `["text(x)"]` or `["text#40;x#41;"]` |
| "end" breaks diagram | Reserved word | Use `["end"]` in label instead |
