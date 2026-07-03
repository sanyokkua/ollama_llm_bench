---
name: protocol-first-interfaces
description: Use when defining a new interface/Protocol, deciding between Protocol and ABC, placing a Protocol in the right module file, or when a UI widget controller needs to call into the backend through a Gateway.
---

# Protocol-First Interfaces and the Gateway Pattern

Source of truth: `docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md` (service contracts and the UI Adapter Gateway pattern, D-R-06) and `docs/v3_specification/16_Engineering_Standards/03_CODING_STANDARDS.md` §5 (Interfaces).

## `Protocol` is the default — always

`typing.Protocol` is the default interface mechanism in this codebase. It gives structural typing with no inheritance burden, which fits a composition root that wires concrete implementations behind abstractions without anyone subclassing anything.

```python
from typing import Protocol


class LLMClient(Protocol):
    def chat(self, *, prompt: str, model: str) -> ChatReply: ...        # blocking; runs on a worker thread
    def probe_health(self, *, model: str) -> HealthStatus: ...          # blocking; runs on a worker thread
```

A concrete implementation satisfies a Protocol **structurally** — it never subclasses it. This is what keeps the backend replaceable and lets every service be substituted by a test double with zero coupling to the Protocol's own module.

Every contract in `08-E` is declared this way: method names, full type annotations, an `...` body, a docstring stating the threading rule (*blocking* vs *fast-synchronous*) and the error categories the method may raise. No method on a Protocol has an implementation, ever.

## When `abc.ABC` is actually appropriate

`abc.ABC` is used **only** when a base class must provide shared implementation logic that subclasses inherit — i.e., you need real, non-trivial code in the base, not just a signature. In a Protocol-first, composition-root-wired codebase like this one, that need is rare by design: nearly every "interface" here is a pure contract with zero shared logic, so Protocol is correct nearly everywhere. If you find yourself reaching for ABC, first ask whether what you actually want is a free function or a small composition helper that two implementations both call — that is usually the right shape, not inheritance. A legitimate ABC case looks like a shared retry-loop skeleton that several provider adapters all need verbatim and that would otherwise be copy-pasted three times; even then, prefer composition (a shared helper function/class each adapter calls) over an abstract base class, per the "composition over inheritance, max depth 2" rule.

`@runtime_checkable` is added to a Protocol only when an `isinstance()` check against it is genuinely required — most Protocols in this codebase never need this, because callers receive the right type via constructor injection and never need to type-check it at runtime.

## One `protocols.py` per module — never a god-interfaces file

Protocols are kept **small and focused**: two callers that need different behavior get two Protocols, not one wide one. A Protocol is declared in its **owning module's** `protocols.py` and re-exported through that module's `api.py`. There is no project-wide `interfaces.py` collecting unrelated contracts — that pattern is explicitly called out as an anti-pattern in `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`: a file named `interfaces.py` collecting unrelated Protocols "becomes a god-interface; couples unrelated modules." The correct shape is one `protocols.py` per module, scoped to that module's own swap point.

```python
# Correct — owning module declares its own Protocol
# src/ollama_llm_bench/backend/persistence/runs/protocols.py
class RunsStore(Protocol):
    def create_run(self, run: BenchmarkRun) -> RunId: ...
    def get_run(self, run_id: RunId) -> BenchmarkRun: ...
```

```python
# Forbidden — a sprawling cross-cutting interfaces.py
# src/ollama_llm_bench/interfaces.py
class RunsStore(Protocol): ...
class TasksStore(Protocol): ...
class LLMClient(Protocol): ...
# ... fifteen unrelated contracts in one file
```

## The Gateway pattern (D-R-06) — the UI never holds a backend Protocol

This is the most commonly misapplied rule in the codebase, so read it carefully.

**The rule.** Per D-R-06 (`08-A_architecture_principles.md` §6, detailed in `08-E` §7b), the UI layer never holds a backend Protocol directly. The **adapter layer** is the exclusive UI↔backend boundary: it holds the backend Protocols (the persistence stores, services, `LLMClient`, etc.) and exposes, to each UI widget factory, exactly **one** UI-facing **gateway Protocol** per widget.

**What a gateway is.** A gateway is a **method-only** `Protocol` using stdlib + `msgspec` types only — no Qt symbol, no `psygnal` reference. The adapter implements it over one or more backend Protocols: a direct pass-through call, a converted command record, or a derived read.

**Why a gateway and not the store directly (SPEC-074).** The value of a gateway is *not* hiding store names — it is being the single place the Qt-specific concerns live: thread marshalling (a controller must never make a GIL-blocking backend call directly on the GUI thread), command-record construction, and view-model conversion. A gateway is a **purpose-built facade**, scoped to exactly the methods its controller calls — never a blanket 1:1 re-export of a store's full surface, and never a hand to the raw backend Protocol itself.

```python
# WRONG — UI controller holding a backend Protocol directly
class ResumeBenchmarkController:
    def __init__(self, *, runs_store: RunsStore, results_store: ResultsStore) -> None:
        ...  # the UI layer is never supposed to see RunsStore/ResultsStore at all
```

```python
# RIGHT — UI controller holds exactly one purpose-built Gateway
class ResumeBenchmarkController:
    def __init__(self, *, gateway: ResumeGateway) -> None:
        self._gateway = gateway

    def on_resume_clicked(self, run_id: RunId) -> None:
        self._gateway.resume_run(run_id)
```

```python
# RIGHT — the adapter implements the gateway over several backend Protocols,
# scoped to only what ResumeBenchmark's controller actually calls.
class ResumeGateway(Protocol):
    def list_runs(self) -> tuple[BenchmarkRun, ...]: ...
    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]: ...
    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int: ...
    def resume_run(self, run_id: RunId) -> None: ...
    # ... only the methods ResumeBenchmark's controller needs — not RunsStore's
    #     or ResultsStore's full surface.
```

**What a gateway is NOT for.** Gateways carry only the **immediate query/command** surface a controller needs in place. Push state still arrives separately as marshalled bus events (the event-bus catalog), never as a gateway return value. A gateway is a request/response facade, not a state channel.

**Where this fits the layering.** The module-inventory "Dependency Protocols" columns name the backend *capabilities* each widget needs — read those columns as "what the adapter wires behind this widget's gateway," never as "Protocols the widget itself holds."

### The known Gateway Protocols (`08-E` §7b)

Seven gateways exist today, one per top-level widget/dialog surface:

| Gateway | Backs | Wraps (backend Protocols/services) |
|---|---|---|
| `MainWindowGateway` | Main Window shell | `SettingsService` (window-shell keys), `ReadinessService` (status-bar health dot), `BenchmarkFlowApi` (quit decision, graceful shutdown) |
| `NewBenchmarkGateway` | New Benchmark widget | `SettingsStore`, `ProviderRegistry`, `ReadinessService`, the run-start command |
| `ResumeGateway` | Resume Benchmark widget | `RunsStore`, `ResultsStore`, `TasksStore`, `ReadinessService`, `SettingsService`, the resume command |
| `ProgressGateway` | Progress widget | `BenchmarkFlowService` (pause/resume/stop), `RunRegistryStore`, `RunsStore`, `ResultsStore`, `RunLogReader`, `SettingsStore` |
| `ResultGateway` | Result widget | `RunsStore`, `ResultsStore`, `TasksStore`, `SettingsStore`, `RunAnalysisService`, `ChartService`, `TableSerializationService` |
| `SettingsGateway` | Settings Dialog | `ProvidersStore`, `AppSettingsStore`, `ModelCapabilitiesStore`, `SettingsService`, `ProviderRegistry`, `ReadinessService` |
| `TaskEditorGateway` | Task Editor workspace | `SettingsStore`, `WorkspaceStore`, `RunRegistryStore` |

Each is declared as a `Protocol` in `08-E` §7b with full method signatures — copy the shape (method-only, stdlib + msgspec types, scoped to exactly what the controller calls) when a new top-level widget needs its own gateway.

## Where each Protocol lives — quick decision guide

| You are declaring... | It belongs in... |
|---|---|
| A backend service contract (`RunsStore`, `LLMClient`, `SettingsService`) | That backend module's own `protocols.py`, re-exported via `api.py` |
| A UI-facing facade for one widget's controller | A new entry in the adapter layer implementing a new `<Widget>Gateway` Protocol |
| A tiny contract-local type used by exactly one Protocol method and nowhere else | Declared inline in the section/file that introduces it — not promoted to a shared module just because it looks reusable |

## Document threading and error categories on every contract method

Every Protocol declared in the backend service-contract layer states, for each method, two things beyond its signature: which **threading context** it may be called from, and which **error categories** it may raise. This isn't optional documentation flavor — callers (and reviewers) rely on it to know whether a call site is safe.

- **`blocking`** — the method performs real I/O or pipeline work (network calls, the pipeline run loop) and may take a non-trivial amount of time. It is an ordinary synchronous `def`, but it is only ever invoked on a `TaskRunner` worker thread or, for the pipeline run loop itself, on the dispatcher thread — never directly on the GUI thread.
- **`fast-synchronous`** — the method returns quickly (an in-memory read, a fast SQLite read/write under WAL) and may be called from either the GUI thread or a worker thread.

```python
class LLMClient(Protocol):
    """A single provider's chat, embedding, and capability surface."""

    def chat_stream(self, request: ChatRequest) -> ChatStream:
        """blocking; invoked on a worker thread.

        Raises:
            ProviderError: the provider rejected the request or returned an
                unusable response.
            TimeoutError: the call exceeded `request.timeout_ms`.
        """
        ...

    def supports_streaming(self) -> bool:
        """fast-synchronous; callable from any context. Never raises."""
        ...
```

A method whose contract names **no** error category does not raise to its caller for an expected failure — it returns a value or a status instead. This is exactly how `probe_health()` and `test_inference()` are specified on `LLMClient`: both **never raise**, because every provider-side failure (auth rejected, model not found, rate-limited, timed out) is captured into the returned DTO (`ProviderHealth`, `InferenceTestResult`) instead — the caller branches on the result's outcome field rather than on a `try`/`except`. Don't add a `Raises: ProviderError` note to a method that is contractually non-throwing — check the existing Protocol's own docstring convention before guessing at one.

## Contract-local types stay inline, not promoted

When a Protocol method needs a small type that exists only to serve that one contract — and is not a general-purpose domain record — declare it inline, in the same file/section that introduces the Protocol, rather than promoting it to a shared `domain` module just because "it might be reused later." Promote a type to a shared module only once a second, genuinely independent consumer actually needs it. This keeps each module's `protocols.py` self-contained and avoids the same god-module gravity that the "no shared `interfaces.py`" rule guards against.

## A real multi-method contract, for shape reference

`LLMClient` is a good model to imitate when writing a new backend Protocol: every method states its threading rule, its error behavior (or explicit non-throwing guarantee), and its DTOs are all named in `02_DTOS_AND_ENUMS.md` rather than redefined inline.

```python
class LLMClient(Protocol):
    """A single provider's chat, embedding, and capability surface."""

    def list_models(self) -> tuple[ModelName, ...]:
        """blocking. May be empty for a reachable provider that exposes none.
        Raises ProviderError only when the listing call itself fails."""
        ...

    def probe_health(self) -> ProviderHealth:
        """blocking. Reachability + conditional model discovery; NEVER an
        inference call, NEVER raises — every failure mode is captured into
        the returned ProviderHealth."""
        ...

    def chat_stream(self, request: ChatRequest) -> ChatStream:
        """blocking; invoked on a worker thread. Raises ProviderError when the
        provider rejects the request; TimeoutError when the call exceeds
        request.timeout_ms. A non-throwing soft failure (a refusal that still
        returns text) is reported in ChatResponse.error instead."""
        ...

    def supports_streaming(self) -> bool:
        """fast-synchronous; callable from any context. Never raises."""
        ...
```

Notice the pattern: a *capability* check (`supports_streaming`) is always fast-synchronous and non-throwing — it is a cheap lookup, never a network probe. A *transport* call (`chat_stream`) is always blocking and carries explicit error categories. If you are writing a new Protocol method and find yourself unsure which bucket it falls into, ask whether the method could ever perform network I/O — if yes, it is blocking and worker-thread-only by construction.

## Common mistakes to avoid

- Declaring a Protocol in a shared `interfaces.py` instead of the owning module's `protocols.py`.
- Subclassing a Protocol (`class Foo(SomeProtocol): ...`) instead of satisfying it structurally — Protocols are never inherited from by concrete implementations.
- Giving a UI controller a backend Protocol (`RunsStore`, `LLMClient`, etc.) instead of a Gateway.
- Making a Gateway a 1:1 re-export of a store's entire method set instead of scoping it to what the controller actually calls.
- Using a Gateway return value to carry push/state updates instead of routing those through the event bus.
- Reaching for `ABC` out of habit (e.g., porting code from an ABC-based codebase) when the interface carries no shared implementation logic.
- Omitting the threading marker (`blocking` / `fast-synchronous`) or the error-category list from a new Protocol method's docstring.
