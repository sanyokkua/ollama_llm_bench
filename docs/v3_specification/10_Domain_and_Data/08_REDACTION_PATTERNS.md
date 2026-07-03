# Redaction Patterns

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** 10_Domain_and_Data/05_EXPORT_FORMATS.md, 10_Domain_and_Data/06_IMPORT_FORMATS.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 11_Services_and_Algorithms/15_LOG_FORMATTING.md, 11_Services_and_Algorithms/17_ERROR_TAXONOMY.md, 12_Quality_and_NFRs/02_SECURITY_MODEL.md, 12_Quality_and_NFRs/09_PRIVACY_POLICY.md, 13_Distribution_and_Release/07_CRASH_REPORTING.md, 16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md, 16_Engineering_Standards/06_LOGGING_STANDARD.md, 08_Cross_Cutting/08-F_spec_issues_log.md

This document specifies the single redaction module that removes secrets from text on the two surfaces where text could otherwise leak a credential out of the application. The module owns one secret denylist and one never-log key-name list. It exposes a single text-cleaning function plus a structlog processor. This document defines the two surfaces that apply redaction, the regex denylist, the never-log key names, the length cap, the API surface, and the test cases for every pattern.

---

## Table of Contents

1. Architectural rule — two surfaces, one module
2. What counts as a secret
3. The regex denylist
4. The never-log key-name list
5. The length cap
6. The placeholder token
7. The API surface
8. Order of operations inside a redaction pass
9. Worked examples
10. Test cases
11. Edge cases

---

## 1. Architectural rule — two surfaces, one module

Ollama LLM Bench is a single-user desktop application. The user runs it on their own machine, types their own prompts, and watches their own model produce its own responses. The user's prompts and the model's responses are **the user's own data on the user's own machine**; redacting them on display, in logs, or in exports would be theatre — the user is the only person who sees them, and the only person who could ever leak them is the user themselves, deliberately. The threat model (`12_Quality_and_NFRs/02_SECURITY_MODEL.md`) treats user-authored prompts and user-machine model responses as **trusted data** that does not require redaction at the application's display, export, clipboard, or per-run-log surfaces.

Redaction is therefore scoped to exactly **two** surfaces. These are the only places a provider credential could realistically end up in a file or a string the user did not author themselves:

1. **App log records — the `app.*` log namespace.** The system/debug log file (`<app-data>/logs/app/app.log` and its rotation files). A structlog processor passes every record through `redact_for_log` before it is written. **Rationale:** third-party SDKs in the dependency tree (`httpx`, `openai`, `anthropic`, `google-genai`) may dump raw HTTP request/response bodies — including `Authorization: Bearer …` headers — when their own log level is DEBUG/TRACE. The processor is the catch-all that scrubs anything the adapter wrapping (surface 2 below) missed.
2. **Provider SDK error-message wrapping at the adapter boundary.** When a provider adapter catches an SDK exception and constructs the app-typed `AppError` (`16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md`, `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`), `redact(exc_message)` is applied to the exception's message string before it is placed in `AppError.message`. **Rationale:** SDK exception messages occasionally echo back URL query strings, request headers, or partial request payloads that may carry the API key. From the moment the message is wrapped, it flows through display, log, CSV, and clipboard surfaces **without further redaction** — the wrap point is the canonicalisation point.

Redaction is **NOT applied** to the following surfaces — they handle user-authored prompts and user-machine model responses, which are the user's own data:

- The **Run-log panel display** of prompts and responses (the Progress widget's run-log panel, `04_Progress_Widget/description.md` §8). The user authored the prompts and the user's machine produced the responses; the user knows what is there.
- The **Run-log file** — the `run.*` log namespace, the per-run plain-text log file at `<app-data>/logs/run/run_<run_id>_<unix_ts>.log`. The content is the same as the panel display.
- **CSV / Markdown table exports** (Summary, Details — `10_Domain_and_Data/05_EXPORT_FORMATS.md`, `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`). The exports are the user's own data the user chose to write to a file they control.
- The **Run-analysis Markdown export** (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`, `10_Domain_and_Data/05_EXPORT_FORMATS.md` §10). The narrative is a model-produced summary of the user's own data.
- **HTML rendering** of the task-detail panel and the Result widget content (`11_Services_and_Algorithms/20_HTML_RENDERING.md`). HTML-escaped, not redacted.
- **Clipboard copy** of any of the above.
- The **Generate Analysis dialog's response excerpt preview** and the Test Inference outcome's `response_excerpt` (`07_Common_Dialogs/generate_analysis_dialog.md`, `06_Settings_Dialog/sub_dialogs/provider_edit.md`).

The reason for the narrower scope is the local-app threat model. The earlier specification rule that named the redaction module "the sole egress path" and routed every UI display, every export, every clipboard action through it has been **retired** in favour of the two-surface rule (see the decision-log entry in `08_Cross_Cutting/08-F_spec_issues_log.md`). The retired purpose-specific egress wrappers `redact_for_display` and `redact_for_csv` are removed from this document and from the application surface.

## 2. What counts as a secret

A secret is any value that grants access to a provider, or any text from which such a value could be reconstructed. In this application that is:

- The **resolved value** of a provider API key — the value obtained by reading the environment variable whose name is stored on the provider (`10_Domain_and_Data/06_IMPORT_FORMATS.md`). The resolved value lives only in memory; it is a secret.
- An authorization header value or bearer token that an HTTP client would send.
- Any vendor-formatted key string (for example an OpenAI-style or Anthropic-style key) found loose in free text such as an error message or a stack trace.

An environment-variable **name** — the bare string stored on the provider, for example `OPENAI_API_KEY` — is **not** a secret; it names a secret without containing one, so it is never masked. The *resolved value* of that variable is a secret (D-R-18, superseding D-R-09).

## 3. The regex denylist

The denylist is an ordered list of regular expressions. Each pattern matches a span of text that is a secret; the redaction function replaces every match with the placeholder token (§6). Patterns are matched case-sensitively unless noted, and the list is applied in order.

| # | Name | Pattern | Matches |
|---|---|---|---|
| 1 | `openai_key` | `sk-[A-Za-z0-9_-]{20,}` | OpenAI-style API keys, including project keys (`sk-proj-...`). |
| 2 | `anthropic_key` | `sk-ant-[A-Za-z0-9_-]{20,}` | Anthropic API keys. |
| 3 | `google_key` | `AIza[A-Za-z0-9_-]{30,}` | Google / Gemini API keys. |
| 4 | `github_token` | `gho_[A-Za-z0-9]{20,}` | GitHub-style OAuth tokens (`gho_…`). Mentioned for completeness even though the application itself does not call GitHub. |
| 5 | `azure_key` | `\b[A-Fa-f0-9]{32}\b` | Azure OpenAI 32-hex-character keys. |
| 6 | `bearer_token` | `(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*` | HTTP `Authorization: Bearer ...` values. |
| 7 | `authorization_header` | `(?i)\bAuthorization\s*[:=]\s*\S+` | A whole `Authorization` header line, key and value. Also matches a high-entropy 24+ char token following an `Authorization:` header. |
| 8 | `api_key_kv` | `(?i)\b(api[_-]?key|apikey|access[_-]?token|secret[_-]?key|client[_-]?secret)\b\s*[:=]\s*("[^"]*"|'[^']*'|\S+)` | Any `key: value` or `key=value` pair whose key name signals a secret; the value side is redacted — **unless** the value matches the env-var-name exception (Rules below), in which case it is left intact. |
| 9 | `jwt` | `\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` | JSON Web Tokens (three dot-separated base64url segments starting with `eyJ`). |
| 10 | `generic_long_token` | `\b[A-Za-z0-9_-]{40,}\b` | A high-entropy unbroken token of 40 or more characters not already matched above; a catch-all for vendor key formats not individually listed. |

Rules for the denylist:

- Patterns 1 through 9 target known shapes. Pattern 10 is a deliberate catch-all so that a key format the list does not name individually is still caught by its length and character class.
- For the `key: value` patterns (7 and 8) only the value side is replaced; the key name is kept so the redacted text remains readable (`api_key=<redacted>`).
- **Env-var-name exception (pattern 8 only).** If pattern 8's captured value matches `^["']?[A-Z][A-Z0-9]*(_[A-Z0-9]+)+["']?$` — an UPPER_SNAKE identifier with **at least one underscore**, the stored credential form (D-R-18) — the value is left intact instead of replaced. The exception lives *inside* the pattern-8 substitution, so list ordering cannot defeat it. It is safe because any **resolved** secret value has already been scrubbed by the shape-independent known-value masking (§8 step 1) before any regex runs — a real secret that happened to look name-shaped is gone before pattern 8 ever sees the text. The at-least-one-underscore requirement keeps underscore-free look-alike vendor tokens (for example AWS `AKIA…` access-key IDs) on the redaction path. A single-word variable name (`TOKEN`) is masked — an accepted false positive; multi-word names are the norm.
- A stored credential is a bare environment-variable **name** (e.g. `OPENAI_API_KEY`), which is not a secret. In free prose a bare name matches none of the patterns (it is shorter than the pattern-10 floor and not vendor-shaped); after a secret-signalling key (`api_key:`) it is preserved by the pattern-8 exception above.
- The denylist is a single ordered constant inside the redaction module. Adding a provider key format means adding one pattern here and nowhere else.

## 4. The never-log key-name list

Independently of the regex denylist, the redaction module owns a list of **key names that must never be logged with a value**, used by the structlog processor (§7) when structured records (log events, error context, event payloads) are serialised to the `app.*` stream. When a record contains a field whose name, compared case-insensitively, is on this list, its value is replaced with the placeholder token regardless of what the value looks like.

```
api_key, apikey, access_token, secret_key, secret, client_secret,
authorization, auth, bearer, password, passwd, token, x-api-key
```

This is a name-based defence that catches a secret even when the value does not match any regex — for example a short or oddly formatted key. The check is applied to field names in structured payloads; it does not replace occurrences of these words in free prose.

## 5. The length cap

After pattern substitution, the redaction function caps the length of the text it returns.

| Parameter | Value |
|---|---|
| Cap | 4000 characters. |
| Action when exceeded | The text is truncated to the cap and the suffix ` …[truncated, N more characters]` is appended, where `N` is the number of characters removed. |
| Rationale | Bounds log lines and error-message strings, and ensures an undetected high-entropy secret cannot be exfiltrated in bulk through an unbounded field. |

The length cap applies only to the redaction function's output. It is the last step of a redaction pass (§8) so that the count `N` reflects the post-substitution text. The cap is not applied to user-authored prompts, model responses, or table-cell content (which never pass through the redaction function in the new model).

## 6. The placeholder token

Every match and every never-log field value is replaced with the single fixed token:

```
<redacted>
```

The token is identical across the structlog processor and the `redact` function. A reader who sees `<redacted>` knows a secret was removed at that position. The token is not configurable; a stable token keeps logs diff-friendly and predictable for tests.

## 7. The API surface

The redaction module exposes exactly two callables. They share the same denylist, the same never-log list, the same placeholder, and the same length cap.

### 7.1 `redact(text: str) -> str`

The single text-cleaning function. Takes a string, applies the regex denylist (§3) in order, applies the length cap (§5), and returns the cleaned string.

- Used by the **provider adapter boundary** (surface 2 above) when wrapping an SDK exception into `AppError.message`. The pass first masks any currently-resolved provider secret value (shape-independent, §8 step 1) and then applies the regex denylist, so even a short/odd-shaped key in the SDK message is removed. Once the adapter has applied `redact` to the message string, the resulting `AppError` is canonically safe and flows through display, log, CSV, and clipboard surfaces without further redaction.
- Returns plain text; the caller is responsible for any further formatting or escaping needed by its surface.

### 7.2 `redact_for_log(record) -> dict | str`

The structlog processor. Installed in the `app.*` namespace's processor pipeline (`16_Engineering_Standards/06_LOGGING_STANDARD.md` §7) so **every** record written to the application log passes through it. Two-step behaviour:

1. **Never-log field replacement.** Walk the record's fields; for each field whose name (case-insensitively) is on the never-log list (§4), replace the value with `<redacted>` regardless of what the value looks like.
2. **Free-text scrubbing.** Render the record to its log-line form (the structured-logging stack's normal serialisation), then apply the regex denylist (§3) to the serialised line to catch secrets sitting in free-text fields such as a message or an exception string. Apply the length cap (§5) to the final line.

The processor is attached to the `app.*` namespace **only**, NOT to `run.*`. The `run.*` namespace logs user prompts and model responses as plain text without redaction. This split is the binding rule in `16_Engineering_Standards/06_LOGGING_STANDARD.md` §7.

### 7.3 What was retired

The earlier specification exposed `redact_for_display`, `redact_for_csv`, and `redact_for_log` as a three-function "egress" API. The first two were applied to UI labels, table cells, tooltips, CSV cells, Markdown cells, clipboard content, and run-analysis bodies — every text surface the application produced. They are **retired** in this revision:

- `redact_for_display` — **removed**. UI surfaces, run-log panels, run-analysis displays, response excerpts, and clipboard copies no longer apply redaction. The user is reading their own data.
- `redact_for_csv` — **removed**. CSV and Markdown exports of the user's own table data no longer apply redaction.

The retirement is recorded in `08_Cross_Cutting/08-F_spec_issues_log.md`; cross-references in other spec files have been updated to match this contract. A historical reference to either function in this document or in the decision-log entry is allowed; an active call to either in any spec section is not.

## 8. Order of operations inside a redaction pass

`redact(text)` performs its pass in this fixed order:

1. **Known-value masking (D-R-18, SPEC-070; provisioning SPEC-059).** Before any regex runs, replace every occurrence of a **currently-resolved provider secret value** with `<redacted>`. The set of live resolved credential values (obtained by reading the environment variables whose **names** are stored on the configured providers, held only in memory) is published as an **immutable frozenset snapshot**, refreshed at startup and on **every provider-registry reload** (`_provider_registry_reloaded`) by an atomic reference swap — the same publish pattern as the registry's own map (DD-50/DD-41). The `redact_for_log` structlog processor and the adapter-boundary `redact()` read the *current* snapshot reference with a lock-free, GIL-atomic read from any thread; a key added or rotated mid-session is therefore masked from the next reload onward, never only those known at startup. The values exist only in memory and are never persisted. This masking is **shape-independent**: it scrubs the real secret even when it is shorter than every regex floor or has an unusual format — closing the gap where a short/odd key in an SDK error message would otherwise survive the regex-only pass. (Because literal secrets are forbidden at rest — D-R-18 — the only secret value that can appear in text is a resolved env-var value, and this step targets exactly those.)
2. **Regex substitution.** Apply denylist patterns 1 through 10 in order; replace every match with `<redacted>`. After a higher-priority pattern has replaced a span, later patterns cannot re-match inside the placeholder, which is why the specific patterns precede the generic catch-all. A bare environment-variable name needs no pattern of its own: in free prose it matches nothing, and on the value side of `api_key:`-style pairs it is preserved by pattern 8's built-in env-var-name exception (§3 Rules).
3. **Length cap.** If the result exceeds 4000 characters, truncate and append the truncation suffix.

**Safe-field exemption (D-R-18, SPEC-072).** A small set of known-safe diagnostic identifiers — `correlation_id`, `run_id`, `result_id`, `task_id`, and model-digest fields — are exempt from the value-shape patterns (`azure_key` §3 pattern 5 and `generic_long_token` §3 pattern 10) when they appear as a **named structured field** (the `redact_for_log` processor recognises the field name and passes its value through). This prevents a 32-hex model digest, a dashless UUID, or a long correlation id from being redacted out of the `app.*` log — preserving the cross-referencing those identifiers exist for. The exemption is by field name only; the same value appearing as free text in an SDK error message is still subject to the patterns.

`redact_for_log(record)` performs its pass as:

1. **Never-log field replacement** (§4).
2. **Serialisation** to the log-line form.
3. **Regex substitution** as above.
4. **Length cap** as above.

The order guarantees that field-name defence runs before value-shape defence, and that the catch-all pattern runs after the specific ones.

## 9. Worked examples

### 9.1 An SDK exception message containing an `Authorization` header

Input message attached to a provider SDK exception (caught at the adapter boundary):

```
HTTP 401 Unauthorized — request was: GET /v1/chat/completions Authorization: Bearer sk-ant-api03-Xy12Zz34Aa56Bb78Cc90Dd12
```

`redact(message)` output, placed on `AppError.message`:

```
HTTP 401 Unauthorized — request was: GET /v1/chat/completions Authorization: <redacted>
```

The `AppError` then flows through the error dialog, the application log, and any caller surface unchanged — no further redaction is applied.

### 9.2 An environment-variable name is left intact

Input cell value or settings line:

```
api_key: OPENAI_API_KEY
```

`redact` output (unchanged — a name is not a secret: pattern 8 matches the pair but its env-var-name exception sees the UPPER_SNAKE value `OPENAI_API_KEY` and leaves it intact; §3 Rules):

```
api_key: OPENAI_API_KEY
```

### 9.3 A long error message is capped

A 6200-character SDK exception message passed to `redact` returns the first 4000 characters followed by:

```
 …[truncated, 2200 more characters]
```

### 9.4 A user-authored prompt is NOT redacted on display

A run's task carries `question = "Please summarise the attached email: From: alice@example.com..."`. The Result widget's Task Detail Panel renders the prompt verbatim (HTML-escaped, but not redacted). The user authored the prompt; there is no surface on which the application would redact it. The same prompt appears unredacted in the CSV export, the Markdown export, the run-log panel, the run-log file, the clipboard, and the run-analysis narrative.

## 10. Test cases

Each denylist pattern, the never-log list, the env-var exemption, and the length cap have at least one positive test. A test passes when `redact`'s output contains `<redacted>` in place of the secret (and, for the negative cases, when the input is returned unchanged).

| ID | Pattern / rule | Input fragment | Expected in output |
|---|---|---|---|
| RT-01 | `openai_key` | `key is sk-proj-AB12cd34EF56gh78IJ90kl12MN` | `key is <redacted>` |
| RT-02 | `anthropic_key` | `sk-ant-api03-Zz99Yy88Xx77Ww66Vv55Uu44` | `<redacted>` |
| RT-03 | `google_key` | `AIzaSyA1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7` | `<redacted>` |
| RT-04 | `github_token` | `gho_abcdefghij1234567890ABCDEFGH` | `<redacted>` |
| RT-05 | `azure_key` | `azure key 0123456789abcdef0123456789abcdef` | `azure key <redacted>` |
| RT-06 | `bearer_token` | `Bearer abcdEFGH1234ijklMNOP5678` | `<redacted>` |
| RT-07 | `authorization_header` | `Authorization: Token qwertyuiopasdfgh` | `Authorization: <redacted>` (whole value) |
| RT-08 | `api_key_kv` | `client_secret = "hunter2hunter2hunter2"` | `client_secret = <redacted>` |
| RT-09 | `jwt` | `token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk` | `token <redacted>` |
| RT-10 | `generic_long_token` | `value Zk39Lp02Qr85Tx47Bw61Ny38Mc04Hd29Fg77 Js` | `<redacted>` for the token |
| RT-11 | never-log list (processor) | a log record with field `password` set to `s3cr3tValue` | the `password` field serialises as `<redacted>` |
| RT-12 | never-log list, odd value | a log record with field `api_key` set to `12345` (too short for any regex) | `<redacted>` — caught by the field name, not the regex |
| RT-13 | env-var-name exception (pattern 8) | `api_key=ANTHROPIC_API_KEY` | unchanged — the value matches the UPPER_SNAKE-with-underscore exception; no `<redacted>` |
| RT-13a | underscore-free look-alike still redacted | `api_key=AKIAIOSFODNN7EXAMPLE` | `api_key=<redacted>` — no underscore, the exception does not apply |
| RT-14 | env-var name in prose | `set the variable MY_TOKEN before launch` | unchanged |
| RT-15 | length cap | a 9000-character string with no secret | output is 4000 chars plus ` …[truncated, 5000 more characters]` |
| RT-16 | ordering | `sk-ant-api03-Xy12Zz34Aa56Bb78Cc90Dd12` | matched once by `anthropic_key`; `generic_long_token` does not re-match inside the placeholder |
| RT-17 | clean text passthrough | `Run finished with 10 passes and 0 errors` | unchanged — no `<redacted>` |
| RT-18 | multiple secrets in one line | `keys sk-AAAAAAAAAAAAAAAAAAAA and AIzaBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB` | both replaced with `<redacted>` |
| RT-19 | display surfaces unaffected | a user-authored prompt `"Summarise the email from alice"` rendered in the Task Detail Panel, the CSV export, the run-log panel, the run-log file, and the run-analysis narrative | unchanged in every surface (no redaction applied to user content) |

## 11. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-RD-1 | A secret spans a structured field whose name is not on the never-log list | The serialised-line regex pass (`redact_for_log` step 3) still catches it by shape. |
| EC-RD-2 | A secret value is shorter than every regex's minimum length and is in a field with a benign name | Not detectable by shape; this is an accepted residual risk — the never-log list and the known-value masking of resolved secrets (§8 step 1) are the primary defences, and credentials are stored only as environment-variable names, so a literal secret is never at rest. |
| EC-RD-3 | The same secret appears many times in one text | Every occurrence is replaced; the global substitution does not stop at the first match. |
| EC-RD-4 | A secret is split across two log records | Each record is redacted independently; a secret reconstructable only by concatenating records across the cap boundary is bounded by the 4000-character cap per record. |
| EC-RD-5 | Redaction is asked to process `None` or an empty string | Returns an empty string; no error. |
| EC-RD-6 | A legitimate 40+ character identifier (for example a long model name) trips `generic_long_token` | The known-safe diagnostic identifiers — `correlation_id`, `run_id`, `result_id`, `task_id`, model-digest fields — are **exempt** when they appear as a named structured field (§8 safe-field exemption, D-R-18/SPEC-072), so they are not redacted out of the `app.*` log. For any *other* 40+ char free-text token the catch-all still favours safety over precision: a false `<redacted>` is preferable to a leaked key, and it only affects the two redaction surfaces (display and exports are unaffected). |
| EC-RD-7 | A model response contains text that matches a redaction pattern | Not redacted on display, in the run-log panel/file, in exports, or in the clipboard — the new threat model treats user-machine model responses as the user's own data (§1). The pattern is only redacted if the same text reaches the `app.*` log stream or a wrapped `AppError.message`. |
