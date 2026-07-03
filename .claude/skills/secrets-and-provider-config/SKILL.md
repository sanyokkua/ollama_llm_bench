---
name: secrets-and-provider-config
description: Use when touching provider credentials, ProviderConfig, Settings import/export, or anything named api_key.
---

# Secrets and Provider Config

This is the single most load-bearing security rule in the application. Get it wrong and a literal API key
ends up on disk. Read this skill in full before touching `api_key`, `api_key_raw`, `ProviderConfig`, the
Provider Edit dialog, or the Settings/provider import-export path.

Sources of truth:
- `docs/v3_specification/12_Quality_and_NFRs/02_SECURITY_MODEL.md`
- `docs/v3_specification/10_Domain_and_Data/06_IMPORT_FORMATS.md` §5, §6 (the `api_key` validation rules)

## The one rule

**`api_key_raw` (and its run-snapshot column `benchmark_run_providers.api_key_raw`) stores ONLY the bare
NAME of an environment variable.** Nothing else is ever valid:

- It is **never a literal secret value** — not even briefly, not even encrypted.
- It is **never a wrapped reference** of any kind — not `${OPENAI_API_KEY}`, not `env:OPENAI_API_KEY`, not
  any other decorated form. The bare name, and only the bare name, is the stored value.
- It matches the regex `[A-Za-z_][A-Za-z0-9_]*` — a valid Python/shell identifier shape. Anything with
  spaces, `=`, `$`, `{`, `}`, or other punctuation is not a name and must be rejected.
- **Empty is allowed**, but only for a keyless local provider (for example a local `llama.cpp` endpoint
  that needs no credential).

This is D-R-18 (superseding the older D-R-09 "wrapped reference" design — do not implement the wrapped
form even if you find it referenced in older notes).

## Rejection happens inline, at entry, in two places

A value that is not a valid environment-variable name (and not empty) is **rejected inline at the point of
entry** — there is no conversion dialog, no "save plain anyway" escape hatch, and no deferred validation:

1. **The Settings provider editor** — typing a literal key into the api-key field is rejected before the
   field can be saved; the form shows an inline error guiding the user to enter the NAME of an environment
   variable, not the key itself.
2. **The import path** — a literal value in an `api_key` field of an imported provider-configuration file
   is a **hard error for that entry** (`EC-IMP-9`). The preview flags the entry as needing an
   environment-variable name; nothing literal is ever persisted. There is no conversion offer — the file
   itself must be corrected.

An environment-variable name for a variable that happens to be **unset** is not an entry-time error — it
is accepted as a name (it might be set later, or on a different machine). At import time this becomes a
**soft warning** (`EC-IMP-10`): "Environment variable `<NAME>` is not currently set" — the name still
imports. At use/readiness-probe time an unset/empty named variable surfaces as `MISSING_ENV` (`EC-PROV-6`)
— diagnosable, never a silent inference failure.

## Resolution happens only in memory, only at use time

The application **never** resolves an environment variable before storing a provider's configuration.

- Resolution happens **in memory**, at the moment a provider client is actually constructed — for a
  readiness probe, a Provider Edit "Test reachability"/"Run inference test" call, or a real inference call
  during a run.
- The resolved value lives only in process memory for the lifetime of that client. It is **never** written
  back to the database, a log file, or a run snapshot.
- When a run freezes its provider snapshot (`benchmark_run_providers`), it copies the **environment-variable
  name verbatim** — not the resolved value. Resuming the run later re-reads the variable of that name
  against the environment at resume time, which may have changed.
- Environment variables are read once at process startup from the launching shell's environment; a newly
  set or changed variable requires an application restart to be picked up.

## No OS keychain integration — and that's by design, not an oversight

The application does **not** integrate with the macOS Keychain, Windows Credential Manager, or any other
OS secret store, and it does not need to: **because the database never holds a secret value, there is
nothing at rest to protect with a keychain.** The `0600`/owner-only file permission on the database file
(and on `backups/settings_*.yaml`, which also stores only names) is defence in depth, not the primary
control — the primary control is that no secret value ever reaches disk in the first place. Do not add
keychain integration "for extra safety" without a formal ADR; it would be solving a problem the design
already eliminated.

## Import validation is correctness-only, not a security boundary

Provider import/export is a **same-user backup/restore feature** (DD-55) — the user exports their own
configuration and later restores it, typically across an OS reinstall, app reinstall, or device move. It is
**explicitly not a security boundary** and must never be treated as one:

- Import validation checks **schema shape, required fields, and value validity** — including the
  env-var-name-syntax check above — exactly the same kind of validation you'd apply to any of the user's
  own data.
- It is **not** defending against a malicious or adversarial import file, because the import file is the
  user's own previously exported data, not third-party untrusted input. (YAML is still parsed in
  safe-load mode as ordinary engineering hygiene — that's unrelated to the security-boundary question.)
- Do not add signature verification, encryption, or an "untrusted file" warning flow to the import feature
  — that would misrepresent what the feature is for.

Azure-specific fields (`azure_endpoint`, `azure_deployment`, `azure_api_version`) are **plain literal
configuration values**, not secrets — they import and export verbatim, with no name-validation applied to
them.

## Code-shaped example: correct vs incorrect

```python
# CORRECT — accepted: a bare environment-variable name.
provider_draft = ProviderDraft(
    name="OpenAI",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    base_url="https://api.openai.com/v1",
    api_key_raw="OPENAI_API_KEY",   # a NAME, validated against [A-Za-z_][A-Za-z0-9_]*
)

# CORRECT — accepted: empty, for a keyless local provider.
provider_draft = ProviderDraft(
    name="Ollama (local)",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    base_url="http://localhost:11434/v1",
    api_key_raw="",
)

# INCORRECT — must be rejected inline at entry, never persisted.
provider_draft = ProviderDraft(
    name="OpenAI",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    base_url="https://api.openai.com/v1",
    api_key_raw="sk-proj-AbCdEf1234567890",   # a literal key value — hard reject
)

# INCORRECT — must be rejected inline at entry: a wrapped reference is not a name either.
provider_draft = ProviderDraft(
    name="OpenAI",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    base_url="https://api.openai.com/v1",
    api_key_raw="${OPENAI_API_KEY}",   # not a bare name — the braces fail the regex
)


# CORRECT — resolution happens only here, in memory, at client-construction time.
def build_llm_client(provider: ProviderConfig) -> LLMClient:
    resolved_key: str | None = None
    if provider.api_key_raw:
        resolved_key = os.environ.get(provider.api_key_raw)  # may be None -> MISSING_ENV
    return OpenAICompatibleClient(base_url=provider.base_url, api_key=resolved_key)
    # `resolved_key` is never written to provider, never logged, never snapshotted.


# INCORRECT — never resolve before storing; never persist a resolved value anywhere.
def build_llm_client_wrong(provider: ProviderConfig) -> LLMClient:
    resolved_key = os.environ.get(provider.api_key_raw, "")
    provider.api_key_raw = resolved_key  # WRONG: overwrites the name with the live secret
    persist_provider(provider)            # WRONG: a secret value now reaches the database
    return OpenAICompatibleClient(base_url=provider.base_url, api_key=resolved_key)
```

## Validation regex (verbatim)

```text
[A-Za-z_][A-Za-z0-9_]*
```

Apply it identically in the Settings provider editor and the import path. Empty string is a separate,
explicitly allowed case — do not fold it into the regex with `*` at the top level in a way that silently
also accepts other "falsy-looking" values; check for empty explicitly, then apply the regex.

## Cross-references

- `docs/v3_specification/12_Quality_and_NFRs/02_SECURITY_MODEL.md` §§2-4 — threat model, what counts as a secret, storage and resolution rules in full.
- `docs/v3_specification/10_Domain_and_Data/06_IMPORT_FORMATS.md` §5-6 — the import-time validation table, including `EC-IMP-9` and `EC-IMP-10`.
- `docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §4.2 — the `providers.api_key_raw` column definition.
- `docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md` — what happens if a resolved secret value accidentally reaches a log or error message (the redaction egress path; a separate, secondary control).
- The `sqlite-persistence-conventions` skill — general persistence-layer rules that also apply to the `providers` table.
