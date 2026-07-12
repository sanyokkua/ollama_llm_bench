---
id: STORY-026
title: Provide the model-name parser, embedding-model classifier, and capability service
status: done
spec_clauses:
  - 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#47-modelnameparser
  - 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#48-modelcapabilityservice
  - 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#49-embeddingmodelclassifier
  - 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#3-master-service-table
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#75-modelcapabilitiesstore
modules:
  - backend/model_helpers/
acceptance_criteria:
  - STORY-026-AC-1
  - STORY-026-AC-2
  - STORY-026-AC-3
  - STORY-026-AC-4
  - STORY-026-AC-5
depends_on:
  - STORY-001
  - STORY-013
owner: coder
estimate: M
---

# STORY-026 — Provide the model-name parser, embedding-model classifier, and capability service

## Goal

Give the application its three model-identity helpers: a pure parser that splits a provider model
string into family, parameter count, and quantization for the parsed fields of a run's model
entry; a pure classifier that decides whether a model name denotes an embedding-only model so it
is kept out of inference/judge pickers; and a capability service that reads and persists the
observed streaming/reasoning/thinking capabilities of a `(provider, model)` pair through the
capability cache, so the pipeline can decide whether time-to-first-token is measurable without
re-probing every time.

## In scope

- **ModelNameParser** (pure, `backend.model_helpers.model_name`): `parse_model_name(model_string) -> ModelNameParsed`, extracting `model_family: str | None`, `model_params_b: int | None`, and
  `quantization: str | None`; it never raises — an unparseable component is returned as `None`.
  The `ModelNameParsed` result struct is owned by this module.
- **EmbeddingModelClassifier** (pure, `backend.model_helpers.classifier`):
  `is_embedding_model(model_name) -> bool`, deciding from a model name whether the model is an
  embedding-only model that must not be offered as an inference or judge target; never raises.
- **ModelCapabilityService** (`backend.model_helpers.protocols.ModelCapabilityService` Protocol +
  concrete impl + `backend/model_helpers/testing.py` fake): `get_capabilities(provider_id, model_name)`, `record_capability(provider_id, model_name, capability, source) -> None`, and
  `is_streaming_supported(provider_id, model_name) -> bool`, reading and writing
  `ModelCapabilityRecord` rows through the injected `ModelCapabilitiesStore` Protocol.
- The module's `api.py` factory for the capability service, guarded by `icontract` on programmer
  invariants only; the two pure helpers are exported as free functions with no Protocol.

## Out of scope

- The `ModelCapabilitiesStore` itself — the `model_capabilities` table, its schema, and its
  single-writer persistence — owned by STORY-013; this story consumes that store's Protocol and
  persists no rows of its own.
- The capability **probe** that produces fresh observations (a dedicated probe call or reading a
  live inference call's streaming behaviour) — owned by the provider adapters / benchmark pipeline
  in a later phase; this service records and reads already-observed capabilities.
- The provider/model dropdown filtering that consumes `is_embedding_model` to hide embedding-only
  models — owned by `ui/shared/model_dropdown/` in a later phase.
- Populating `BenchmarkRunModelEntry`'s parsed fields from `parse_model_name` — the run-creation
  use case's step in `backend/benchmark_pipeline/`.

## Spec inputs

- `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#47-modelnameparser` — the pure
  `parse_model_name` contract, the three extracted fields, and the never-raises /
  `None`-on-unparseable rule.
- `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#48-modelcapabilityservice` — the three
  capability-service methods, the `CapabilitySource` observation origins, and the read/write-
  through-`ModelCapabilitiesStore` rule.
- `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#49-embeddingmodelclassifier` — the pure
  `is_embedding_model` contract and its selection-exclusion purpose.
- `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#3-master-service-table` — the three module
  paths (`backend.model_helpers.model_name`,
  `backend.model_helpers.protocols.ModelCapabilityService`, `backend.model_helpers.classifier`)
  and their public surfaces and test-double convention.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#75-modelcapabilitiesstore` — the
  `ModelCapabilitiesStore` Protocol this service reads and writes through.

## Design constraints

- `backend/model_helpers/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`ModelCapabilityRecord`, `ModelCapability`, `CapabilitySource`, `ProviderId`, `ModelName`) and
  the `ModelCapabilitiesStore` Protocol (`01_MODULE_INVENTORY.md` §4.4). No PySide6.
- `ModelNameParsed` is owned by this module as a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`. `ModelCapabilityRecord`, `ModelCapability`, and `CapabilitySource` are consumed from
  `backend/domain/` (STORY-001). The `ModelCapabilityService` Protocol is defined in this module —
  it is not one of the `08-E` contract Protocols — following the Service Inventory §4.8 surface.
- ModelNameParser and EmbeddingModelClassifier are pure functions with no Protocol and no double,
  used directly in tests. ModelCapabilityService is a swap point over a store, so it carries a
  Protocol and a `testing.py` fake.
- All three are synchronous / fast-sync; the parser and classifier never raise. The capability
  service surfaces a `PersistenceError` from the store unchanged (it never swallows it into a
  silent default) but performs no I/O of its own beyond the store call.
- `icontract` on the `api.py` factory guards programmer invariants only — never a model string or
  a provider response.

## Acceptance criteria

### STORY-026-AC-1

Given a range of provider model strings, `parse_model_name` extracts `model_family`,
`model_params_b`, and `quantization` per this table, returning `None` for any component it cannot
parse and never raising:

| Model string       | `model_family`     | `model_params_b` | `quantization` |
| ------------------ | ------------------ | ---------------- | -------------- |
| `qwen3:8b-q4_K_M`  | `qwen3`            | `8`              | `q4_K_M`       |
| `llama3.1:70b`     | `llama3.1`         | `70`             | `None`         |
| `nomic-embed-text` | `nomic-embed-text` | `None`           | `None`         |
| \`\` (empty)       | `None`             | `None`           | `None`         |

### STORY-026-AC-2

For every model string, `parse_model_name` returns a `ModelNameParsed` value and never raises —
an unparseable or malformed string yields a result with `None` components rather than an exception.

### STORY-026-AC-3

Given a model name, `is_embedding_model` returns `True` for an embedding-only model name and
`False` for a chat-capable model name, per a table covering known embedding-model name patterns
and known chat-model name patterns, and never raises.

### STORY-026-AC-4

Given the capability cache holds a `ModelCapabilityRecord` for a `(provider_id, model_name)` pair,
when `get_capabilities` is called, then it returns exactly the records the injected
`ModelCapabilitiesStore` reports for that pair, and `is_streaming_supported` returns `True`
exactly when the streaming capability record's `supported` value is `1`.

### STORY-026-AC-5

Given `record_capability(provider_id, model_name, capability, source)` is called, when it
completes, then exactly one upsert is written through the `ModelCapabilitiesStore` for that
`(provider_id, model_name, capability)` triple carrying the given `CapabilitySource`, and a
subsequent `get_capabilities` for the pair reflects the recorded value.

## Test plan

- STORY-026-AC-1 — unit (table-driven over the model strings), colocated
  `src/ollama_llm_bench/backend/model_helpers/tests/test_model_name.py`,
  `test_parse_model_name_extracts_components`.
- STORY-026-AC-2 — property (Hypothesis over arbitrary strings), same file,
  `test_parse_model_name_never_raises`.
- STORY-026-AC-3 — unit (table-driven over embedding vs chat name patterns), colocated
  `src/ollama_llm_bench/backend/model_helpers/tests/test_classifier.py`,
  `test_is_embedding_model_classifies_name`.
- STORY-026-AC-4 — unit (against the `ModelCapabilitiesStore` fake), colocated
  `src/ollama_llm_bench/backend/model_helpers/tests/test_capability_service.py`,
  `test_get_capabilities_and_streaming_reflect_store`.
- STORY-026-AC-5 — unit (against the store fake, asserting one upsert), same file,
  `test_record_capability_writes_one_upsert_through_store`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-026.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/model_helpers/`.
- [ ] An architecture test confirms `backend/model_helpers/` imports no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-026.
- [ ] The module inventory is unchanged.
