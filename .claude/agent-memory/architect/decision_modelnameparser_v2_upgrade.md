---
name: ModelNameParser V2 upgrade decision (2026-04-16)
description: Decided to replace parse() signature rather than add an overload; family version stripping removed; returns ModelDescriptor not ParsedModelName
type: project
---

On 2026-04-16, designed the Task 4 upgrade for ModelNameParser in the V2 provider abstraction layer.

**Decision**: Replace the single `parse(self, model_name: str) -> ParsedModelName` method wholesale with `parse(self, *, provider_id: str, provider_type: str, model_name: str) -> ModelDescriptor`. No overload, no backward-compat shim.

**Why:** There are zero V2 callers of the old method. The only consumer was the test file. A shim would introduce dead code and make ModelNameParserApi Protocol ambiguous.

**Key behaviour change vs old implementation:**
- Old code stripped the version number from family: `llama3.1` → `llama3` via `_FAMILY_VERSION_RE`.
- New code keeps the full family string: `llama3.1` stays `llama3.1`.
- For names without `:` (cloud models like `gpt-4o`): `model_family = model_name` (not all-None as in old code).
- Return type changes from `ParsedModelName` to `ModelDescriptor`.

**How to apply:** When any future task needs to parse model names, always use the new keyword-only signature and expect ModelDescriptor back. ParsedModelName is retained in models.py for now but has no active V2 callers.

**Open question carried forward:** `qat` quantization matching — the new `_QUANT_PATTERN` (`q\d+...`) may not match `qat`. Add test case or extend regex.
