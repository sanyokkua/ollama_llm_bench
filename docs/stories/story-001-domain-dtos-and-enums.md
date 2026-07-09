---
id: STORY-001
title: Define the shared domain DTOs, enums, type aliases, and constrained types
status: done
spec_clauses:
  - 10_Domain_and_Data/02_DTOS_AND_ENUMS.md#2-type-aliases
  - 10_Domain_and_Data/02_DTOS_AND_ENUMS.md#3-reusable-constrained-types
  - 10_Domain_and_Data/02_DTOS_AND_ENUMS.md#4-enumerations
  - 10_Domain_and_Data/02_DTOS_AND_ENUMS.md#7-domain-records--runtime-and-service-dtos
  - 10_Domain_and_Data/01_DOMAIN_MODEL.md#315-in-memory-only-entities
modules:
  - backend/domain/
acceptance_criteria:
  - STORY-001-AC-1
  - STORY-001-AC-2
  - STORY-001-AC-3
  - STORY-001-AC-4
  - STORY-001-AC-5
depends_on: []
owner: coder
estimate: L
---

# STORY-001 — Define the shared domain DTOs, enums, type aliases, and constrained types

## Goal

Establish the foundational, Qt-free domain vocabulary that every other module of the
application imports: the closed enumerations, the type aliases, the reusable constrained
types, and the cross-boundary records. This is the base of the Phase 1 dependency graph;
no other module can be built until these types exist and are re-exported from the module's
public surface.

## In scope

- Every `StrEnum` in `02_DTOS_AND_ENUMS.md` §4 (`RunMode`, `RunStatus`, `ResultStatus`,
  `Verdict`, `ResolutionLayer`, `Difficulty`, `ProviderType`, `ProviderTestStatus`,
  `ModelRole`, `AdaptiveTimeoutRole`, `TaskOrigin`, `TaskTermKind`, `ResultTermKind`,
  `ModelCapability`, `CapabilitySource`, `ErrorKind`, `AttemptOutcome`, `InferenceActivity`,
  `ChartKind`, `InferenceContext`, `InferenceTestOutcome`, `CancelLevel`, `CancelReason`).
- Every type alias in §2 (`RunId`, `ResultId`, `TaskId`, `ProviderId`, `ModelName`,
  `SettingKey`, `Iso8601Utc`) and every constrained type in §3 (`ProviderIdStr`,
  `ModelNameStr`, `TaskIdStr`, `NonNegativeFloat`, `PositiveFloat`, `NonEmptyStr`,
  `CosineScore`, `CosineThreshold`, `RetryCount`, `TimeoutSeconds`, `PositiveInt`,
  `NonNegativeInt`, `DurationMs`, `RepeatCount`).
- The cross-boundary records catalogued in §5–§7 as `msgspec.Struct(frozen=True, kw_only=True, gc=False)`, including the in-memory-only `ProviderHealth` and
  `AppReadinessSnapshot` records (`01_DOMAIN_MODEL.md` §3.15) and the
  `InferenceActivityContext` / `InferenceActivityState` runtime records (§7.8).
- Re-export of every public symbol above from `backend/domain/models.py` and the module's
  `__init__.py`.

## Out of scope

- The `EventBus` Protocol and the event payload Structs — owned by STORY-003.
- The error hierarchy classes and `ErrorContext` — owned by STORY-002.
- The persistence-schema SQLite mapping of these records — a later phase.
- Any behaviour or algorithm over these types (validation cascades, pipeline logic).

## Spec inputs

- `10_Domain_and_Data/02_DTOS_AND_ENUMS.md#2-type-aliases` — the exact type aliases and
  their documented semantics (`ProviderId` is an internal UUID4, never displayed).
- `10_Domain_and_Data/02_DTOS_AND_ENUMS.md#3-reusable-constrained-types` — each
  `Annotated[..., msgspec.Meta(...)]` constrained type and its bound; a constraint
  violation must raise at construction.
- `10_Domain_and_Data/02_DTOS_AND_ENUMS.md#4-enumerations` — the total member set of every
  `StrEnum` and its string value; the checklist for AC-2.
- `10_Domain_and_Data/02_DTOS_AND_ENUMS.md#7-domain-records--runtime-and-service-dtos` — the
  runtime/service records including `InferenceActivityContext` / `InferenceActivityState`.
- `10_Domain_and_Data/01_DOMAIN_MODEL.md#315-in-memory-only-entities` — `ProviderHealth`
  and `AppReadinessSnapshot` are in-memory-only domain entities defined here (resolving the
  investigator's ProviderHealth-location ambiguity in favour of `backend/domain/`).

## Design constraints

- `backend/domain/` is Qt-free and imports nothing project-internal: standard library and
  `msgspec` only (`01_MODULE_INVENTORY.md` §4.1).
- Every cross-boundary record is `msgspec.Struct(frozen=True, kw_only=True, gc=False)`;
  never `@dataclass`. Every closed value domain is a `StrEnum`. Verified by the
  `test_dtos_are_frozen_kw_only` AST architecture test.
- **Ambiguity resolution — `ProviderHealth` location.** `ProviderHealth` and
  `AppReadinessSnapshot` are defined in `backend/domain/` as in-memory-only entities; the
  `ReadinessService` that produces them is out of scope for Phase 1 and consumes these
  types from `backend/domain/`.
- No secret value or `dict[str, Any]` for structured data; `ProviderConfig.api_key_raw`
  stores only an environment-variable name, never a resolved secret.
- The judge produces no numeric score: `Verdict` has exactly `PASS`/`FAIL` and no
  `UNKNOWN` member; `cosine_similarity`/`CosineScore` is the only numeric quality value.

## Acceptance criteria

### STORY-001-AC-1

For every constrained type in §3, constructing a record field with a value outside the
declared `msgspec.Meta` bound raises at construction, and a value inside the bound
constructs successfully.

### STORY-001-AC-2

Each `StrEnum` in §4 has exactly the members and string values listed for it in the
following table — no member is missing and none is added:

| Enum                | Member count | Notable value invariant                                                       |
| ------------------- | ------------ | ----------------------------------------------------------------------------- |
| `RunMode`           | 3            | `synthetic`, `tasks`, `graded`                                                |
| `RunStatus`         | 4            | no `RUNNING`/`PAUSED` member (in-memory-only, excluded)                       |
| `ResultStatus`      | 11           | eleven members across pipeline-position and terminal groups                   |
| `Verdict`           | 2            | `pass`, `fail` — no `UNKNOWN`                                                 |
| `ResolutionLayer`   | 4            | `keyword`, `cosine`, `judge`, `skip`                                          |
| `ProviderType`      | 3            | `openai_compatible`, `anthropic`, `gemini`                                    |
| `ErrorKind`         | 5            | `llm`, `provider`, `timeout`, `judge_timeout`, `other`                        |
| `InferenceActivity` | 5            | `idle`, `benchmark_run`, `judge_analysis`, `provider_test`, `readiness_probe` |
| `CancelLevel`       | 3            | `none`, `soft`, `hard`                                                        |
| `CancelReason`      | 4            | `user_pause`, `auto_pause`, `user_stop`, `app_shutdown`                       |

### STORY-001-AC-3

For every cross-boundary record defined by this story, the type is a `msgspec.Struct`
declared `frozen=True, kw_only=True, gc=False`: positional construction is rejected, an
instance is immutable (attribute assignment raises), and each declared default matches the
spec's documented default.

### STORY-001-AC-4

Every enum, type alias, constrained type, and record named in the In-scope list is
importable directly from the `backend/domain/` package root (re-exported from
`__init__.py`).

### STORY-001-AC-5

Given a `ProviderConfig` and its matching `ProviderConfigDraft`, the draft carries every
field of `ProviderConfig` except `provider_id`, and the `provider_id` field of
`ProviderConfig` accepts only a value matching the UUID4 `ProviderIdStr` pattern.

## Test plan

- STORY-001-AC-1 — property, colocated
  `src/ollama_llm_bench/backend/domain/tests/test_constrained_types.py`,
  `test_constrained_type_bounds_enforced_at_construction`.
- STORY-001-AC-2 — table-driven unit, same directory
  `src/ollama_llm_bench/backend/domain/tests/test_enums.py`,
  `test_enum_members_and_values_are_total`.
- STORY-001-AC-3 — architecture, `tests/architecture/test_dtos.py`,
  `test_dtos_are_frozen_kw_only`.
- STORY-001-AC-4 — unit, `src/ollama_llm_bench/backend/domain/tests/test_public_surface.py`,
  `test_domain_public_symbols_are_reexported`.
- STORY-001-AC-5 — unit,
  `src/ollama_llm_bench/backend/domain/tests/test_provider_config.py`,
  `test_provider_config_draft_omits_provider_id_and_validates_uuid`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-001.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/domain/`.
- [x] `test_dtos_are_frozen_kw_only` passes for every Struct this story adds.
- [x] Backend branch coverage for `backend/domain/` meets the Phase 1 ≥90% gate.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.
