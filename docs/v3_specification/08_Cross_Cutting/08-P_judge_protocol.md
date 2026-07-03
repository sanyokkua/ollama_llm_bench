# Judge Protocol

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-B_benchmark_state_machine.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`, `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md`, `05_Result_Widget/tabs/details_tab.md`

This document is the complete contract for the LLM-as-judge evaluation layer — the third evaluation phase of a graded benchmark run. It defines the prompt the judge model receives, the JSON schema it must return, how the application parses that response, how it recovers from malformed output, and how the judge's verdict combines with the keyword and cosine phases into a result's final binary verdict. The judge returns a binary verdict (`PASS` or `FAIL`) plus a free-text reasoning explanation. It returns no numeric score; the only numeric quality value in the application is the cosine similarity (the Cosine Score), produced by a different phase.

---

## Table of Contents

1. Scope and role of the judge
2. When the judge phase runs
3. Per-task judging
4. The judge prompt
5. Rubric selection by task type
6. The expected response JSON schema
7. Sampling and token budget
8. Parsing strategy
9. Malformed-response handling and retry
10. Recording the judge outcome
11. Final-verdict combination
12. The run-level judge analysis is out of scope here
13. Worked examples
14. Edge cases
15. Test cases

---

## 1. Scope and role of the judge

The judge is an LLM acting as an evaluator of another model's response. It is the third and final evaluation phase of a graded run, after the keyword phase and the cosine phase.

The keyword and cosine phases are mechanical validators. They can be misled by synonyms, paraphrasing, restructured-but-correct answers, or correct code that differs textually from the golden answer. The judge applies genuine language understanding to decide whether the response under test satisfies the task's stated pass and fail criteria. It is the verdict arbiter when the judge phase is enabled and the prior phases did not already produce a definitive failure (see §11 for the exact combination rule).

The judge produces exactly two outputs per task:

- a binary **verdict** — `PASS` or `FAIL`;
- a short **reasoning** string — one or two sentences explaining the verdict.

The judge produces **no numeric score**. Result tables and charts present the Cosine Score (from the cosine phase) as the only numeric quality metric; they never present a "judge score". The judge's contribution to the displayed data is the binary `judge_verdict` and the `judge_reasoning` text.

This document covers only the **per-task judge phase**. The separate run-level narrative analysis is a different feature; see §12.

## 2. When the judge phase runs

The judge model is invoked in **two distinct contexts**, with independent triggers:

1. **Per-task judge phase** (this document). Runs only in `GRADED`, only when `eval.phase_judge_enabled` is `true`, and only for results that have a model response. `TASKS` and `SYNTHETIC` never run the per-task judge phase.
2. **Run-level judge analysis** (separate concern; see §12 and `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`). Runs in any mode when `feature.judge_run_analysis_enabled` is `true` for the run. The "Generate run analysis" toggle is **visible in every mode** and **optional in every mode**: default ON in `GRADED`, default OFF in `SYNTHETIC` and `TASKS`, with the user able to override either default at run start. Uses the same judge model under the same protocol, but at a different point in the run.

The **per-task judge phase** runs when **all** of the following hold:

1. The run mode is `GRADED`. `TASKS` and `SYNTHETIC` never grade and never invoke the per-task judge phase.
2. The judge evaluation stage is enabled. The stage is controlled by a single setting, `eval.phase_judge_enabled` (default `true`), toggled in Settings → Evaluation. The toggle applies only in `GRADED`. A user may run a `GRADED` benchmark with only the keyword and cosine stages active.
3. A judge model is configured for the run. The run snapshot carries a `JUDGE`-role model (`BenchmarkRunModelEntry.role == JUDGE`). A judge model is required at run-creation time whenever either (a) the per-task judge phase is enabled (only possible in `GRADED`) OR (b) `feature.judge_run_analysis_enabled` is on for the run (any mode). When neither condition holds — for example a `GRADED` run configured with keyword+cosine only and the analysis toggle off, or a `TASKS`/`SYNTHETIC` run with the analysis toggle off — no judge model is required.

The judge phase processes the whole task set as one batch, after the keyword phase and the cosine phase have each completed for every task. It corresponds to the `JUDGE_CHECK` pipeline stage; a result enters it from the `AWAITING_JUDGE_CHECK` status. See `08-B_benchmark_state_machine.md`.

## 3. Per-task judging

When the judge phase runs, **the judge evaluates every task that reached the judge phase** — that is, every result that has a model response. This includes results that the keyword phase or the cosine phase already marked as passing and results they already marked as failing.

The judge is not a tie-breaker that runs only on undecided cases. It is a full independent pass over every result that has a response. This is precisely how it catches what the mechanical checks miss: a correct answer that used an unrecognised synonym fails the keyword check and may fall below the cosine threshold, yet the judge can still return `PASS`.

A result that has **no response** is not judged. A result whose status is one of the four terminal-failure statuses that mark an inference-or-earlier failure (`FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `ERRORED`) never reached the judge phase — there is nothing for the judge to evaluate, and `judge_verdict` stays `None`. A result whose status is `FAILED_JUDGE_TIMEOUT` (DD-34) DID complete inference (the response exists) but the judge call either exhausted its role=JUDGE adaptive-timeout ladder for that task OR was skipped because the judge model was already excluded for the rest of the run; `judge_verdict` stays `None` in this case too, but `sanitized_response`, `keyword_verdict`, and `cosine_verdict` (if those phases ran) carry their respective values normally.

There is no per-task gating sub-option. Whether the judge runs is decided entirely by the conditions in §2.

### 3.1 Force-judge

A force-judge flag exists for the verdict-combination logic in §11. It affects only how the judge's verdict combines with a prior **keyword/cosine** failure. When force-judge is off (the **default**, `false` — DD-62), a prior phase's definitive `FAIL` is the final verdict and no judge call is spent on that task. When force-judge is on, the judge's verdict is authoritative even over a prior-phase keyword/cosine failure: the judge is the final gate, and every result *with a gradeable response* is judged. **In either setting, a response that failed the sanity pre-check (empty / error-marker) is not sent to the judge** — there is nothing to grade, so the deterministic failure stands (DD-62). Force-judge is exposed as the setting `eval.force_judge_on_prior_failure` (default `false`).

## 4. The judge prompt

Each judge call is a single chat request (`ChatRequest`, see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.5) carrying one system message and one user message.

**Anonymous Judging — a named guarantee (SPEC-018).** The judge model receives **no provider
identity and no test-model identity, in any prompt field** — only the task context and the
response text. This is what makes self-judging safe in practice: the known self-preference
mechanisms of LLM-as-judge setups are structurally disabled here because (1) the grading is
**anonymous** (no name to favour), (2) it is **absolute, criteria-anchored** grading of a
single response — not the pairwise preference ranking where self-preference effects are
strongest — and (3) the verdict is **binary and criteria-decisive** (no score to nudge).
The same `(provider, model)` may therefore serve as both judge and test model without a
warning. *Residual, stated honestly:* unlabeled stylistic self-recognition on borderline
responses is a known second-order effect in the literature; a user wanting zero residual
simply chooses a judge outside the test set. The run-analysis step cannot reintroduce bias:
it summarises a pre-computed numeric digest and is forbidden from inventing data beyond it
(`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` §6.2).

### 4.1 System message

There is **one universal system message** (DD-46) — no per-task-type rubric exists. The judge's domain expertise is steered by the task's `category` / `sub_category`, and the decisive grading instructions are the task-authored pass/fail criteria carried in the user message. The template is:

```text
You are an impartial evaluation judge for an LLM benchmark. Your job is to decide
whether a candidate response correctly accomplishes a user task in the area of:
{category} / {sub_category}.
Apply the established best practices and quality standards of this area when judging
correctness.

Rules you must follow:
- Decide a single binary verdict: PASS or FAIL. There is no partial credit and no
  "unknown" option.
- The pass criteria and fail criteria, when provided, are decisive: PASS means the
  response satisfies the pass criteria and matches no fail criterion.
- The reference ("golden") answer is one acceptable answer, not the only one. Judge
  the substance of the response, not its surface form: a correct answer that uses
  different wording, structure, or approach than the reference answer is still
  correct.
- Check the response against the question's own instructions: requirements stated in
  the task prompt must be followed.
- Do not reward a response merely for being long, fluent, or confident.
- Base your decision only on the information given in the user message.

Respond with exactly one JSON object and nothing else. No prose before or after it,
no Markdown code fences. The object must have exactly two string fields:
  "verdict"  - the string "PASS" or the string "FAIL"
  "reasoning" - one or two sentences explaining the verdict
```

### 4.2 User message

The user message carries the task context and the response under test. Fields that the task does not declare are omitted entirely rather than sent empty. The template is:

```text
TASK AREA: {category} / {sub_category}

QUESTION:
{question}

{system_prompt_block}

{source_material_block}

REFERENCE ("GOLDEN") ANSWER:
{golden_answer}

PASS CRITERIA:
{pass_criteria}

FAIL CRITERIA:
{fail_criteria}

{required_keywords_block}

{fail_example_block}

CANDIDATE RESPONSE UNDER TEST:
{sanitized_response}

Decide the verdict for the candidate response and return the JSON object.
```

The judge is deliberately given the **full grading context** — the system prompt the candidate model received, the question, any supporting material, the reference (golden) answer, the pass/fail criteria, the required keywords, and the candidate response (D-R-04). The reference answer is included for **every** task type, by design: the judge is the final correctness gate, and withholding the golden answer would force it to decide from its own (possibly stale or biased) training knowledge — a real source of hallucinated verdicts. The golden answer is framed as **the most expected correct answer — the primary reference, but one example of a possible correct answer, not the only acceptable one** (SPEC-107). The judge grades correctness against the criteria, not literal closeness to the golden answer's wording: a response that is correct by other valid reasoning, phrasing, structure, or approach **passes**, and a response is **never failed solely for differing from the golden answer**. This deliberately tolerates a golden answer that is an acceptable variant (e.g. expected behaviour of a fine-tuned model) rather than a bit-exact match. A golden answer that is *genuinely wrong* is a task-file defect (the author's responsibility); it is not silently undetectable, though — see the all-models-fail signal below.

**Prior-stage results are deliberately excluded from the judge prompt (DD-46).** The keyword and cosine outcomes are never mentioned to the judge: the judge is the independent final gate, able to confirm or overturn the programmatic stages in either direction, and feeding it "cosine failed" or "keywords passed" would anchor the verdict and destroy exactly that corrective power. The stage results sit side by side in the Result widget for the user to compare.

Placeholder rules:

| Placeholder | Source field | Omission rule |
|---|---|---|
| `{category}` / `{sub_category}` | `BenchmarkTask.category` / `BenchmarkTask.sub_category` | When one is absent it is omitted; when both are absent the line reads `TASK AREA: (uncategorized)`. |
| `{question}` | `BenchmarkTask.question` | Always present. |
| `{system_prompt_block}` | `BenchmarkResult.system_prompt_sent` | The whole block, including its `SYSTEM PROMPT GIVEN TO THE MODEL:` heading, is omitted when no system prompt was sent. |
| `{source_material_block}` | `BenchmarkTask.source_material` | The whole block, including its `SUPPORTING MATERIAL:` heading, is omitted when the field is `None` or empty. |
| `{golden_answer}` | `BenchmarkTask.golden_answer` | When `None` or empty, the line reads `REFERENCE ("GOLDEN") ANSWER: (none provided)`. |
| `{pass_criteria}` | `BenchmarkTask.pass_criteria` | When empty, the line reads `PASS CRITERIA: (none provided — judge against the question and reference answer)`. |
| `{fail_criteria}` | `BenchmarkTask.fail_criteria` | When empty, the line reads `FAIL CRITERIA: (none provided)`. |
| `{required_keywords_block}` | `BenchmarkTask.required_terms` | The whole block, including its `REQUIRED KEYWORDS (the response is expected to address these):` heading, is omitted when no required terms are declared. Lists the `exact` / `semantic` terms; informational context for the judge, not a hard rule. |
| `{fail_example_block}` | `BenchmarkTask.fail_example` | The whole block, including its `EXAMPLE OF A WRONG ANSWER:` heading, is omitted when the field is `None` or empty. |
| `{sanitized_response}` | `BenchmarkResult.sanitized_response` | Always present. The sanitized response (reasoning blocks already stripped) is sent, never the raw response. |

The judge always evaluates the **sanitized** response — the text with any reasoning/thinking block already removed — so the judge grades the same text a human reader would see.

### 4.3 Judge context size and overflow (DD-46)

The judge prompt is **deliberately context-heavy**: it carries the question, the system
prompt the candidate model received, any source material, the golden answer, the pass and
fail criteria, the keyword lists, the fail example, and the full candidate response. The
application is not agentic — this is a single-shot prompt, so the judge must receive all
of the context in one call. Consequences:

- **The judge model must have a sufficient context window** for the run's largest task
  context plus its longest candidate response. The Settings judge-model help text and the
  New Benchmark judge picker tooltip state this explicitly so the user can choose
  accordingly.
- **Overflow is detected and reported, never silent.** When the provider rejects the call
  because the prompt exceeds the model's context window, the adapter translates the
  provider's response (most providers return a detailed context-length error) into
  `ProviderContextLengthError` (`11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`) — a
  **permanent** error: the call is not retried (no retry can shrink the prompt). The
  result settles `ERRORED` with `error_kind = provider_context_length` and a user-facing
  message that names the judge model, carries the provider's reported detail (redacted),
  and advises choosing a judge model with a larger context window (or shortening the
  task's context). The error is visible in the Details tab like any other result error
  and is counted in the run summary's error tally.
- The same leaf applies when a **test model's** inference prompt overflows (settling
  `FAILED_INFERENCE`); the judge path is called out here because the judge prompt is by
  construction the largest prompt the application builds.

## 5. (retired) — Rubric selection by task type

Removed by **DD-46**: there is no per-`task_type` rubric and no `{rubric_text}`
placeholder. One universal system message (§4.1) steers the judge's expertise through the
task's `category` / `sub_category`; the decisive instructions are the task-authored pass
and fail criteria in the user message (§4.2). The numbering slot is kept to avoid
cross-reference churn.

## 6. The expected response JSON schema

The judge must return exactly one JSON object with exactly two string fields and no others:

```json
{
  "verdict": "PASS",
  "reasoning": "The function returns the correct value for every listed input and uses recursion as required."
}
```

Field contract:

| Field | Type | Allowed values | Meaning |
|---|---|---|---|
| `verdict` | string | `"PASS"` or `"FAIL"` (case-insensitive on input; normalised to upper case) | The binary judge verdict. |
| `reasoning` | string | any non-empty string; truncated to 2000 characters on storage if longer | One or two sentences explaining the verdict. |

There is **no** `score` field, no numeric field of any kind, and no `layers` field. A response that contains additional fields is still accepted; the extra fields are ignored. A response missing `verdict` is malformed (see §9). A response missing `reasoning` but carrying a valid `verdict` is accepted with `reasoning` recorded as `"(no reasoning provided by judge)"`.

The `verdict` string maps directly onto the `Verdict` enum (`PASS` / `FAIL`). The enum has no `UNKNOWN` member; the judge is never permitted to return an undecided verdict, and the prompt forbids it explicitly.

## 7. Sampling and token budget

The judge model is called with the lowest-variance sampling settings. **This minimises
verdict variance; it does NOT guarantee bit-reproducibility (SPEC-019):** at temperature
`0.0`, GPU floating-point nondeterminism, server-side batching, and KV-cache effects can
still vary tokens between identical calls on local backends, and a re-pulled model served
under the same name (version drift) is invisible at the OpenAI-compatible surface. No
`seed` is sent — a recorded decision (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.5,
D-R-04): provider support is inconsistent, and a seed would suggest a determinism it cannot
deliver. Treat repeated verdicts as low-variance, not identical.

| Parameter | Value | Rationale |
|---|---|---|
| Temperature | `0.0` | Minimises sampling variance (not a bit-reproducibility guarantee — see above). |
| `response_format` | `JSON` when the judge provider supports a JSON/structured-output mode; otherwise `TEXT` (see §8). | Maximises the chance of a strictly parseable response. |
| `reasoning_effort` | `DEFAULT` | The judge prompt already constrains the output shape; no elevated reasoning budget is requested. |
| Maximum completion tokens | `eval.judge_max_completion_tokens` (default **4096**, DD-67) | The former fixed `512` cap could trap a **reasoning** judge model — which emits its chain-of-thought into the completion — in a permanent truncated-before-JSON loop. The default is raised to 4096 (a reasoning preamble plus the JSON verdict fits) and is configurable; it is also always sent because Anthropic mandates a `max_tokens` value. |
| Per-call timeout | The adaptive-timeout budget for the judge `(provider, model)` pair, identical to the inference-phase timeout policy. | One consistent timeout model across phases. |

`eval.judge_max_completion_tokens` (default 4096) is the judge-call token budget (DD-67). If a judge response is truncated by the cap before the JSON object closes, the response is treated as malformed and handled by §9 — but §9 additionally distinguishes the **budget-exhausted** case (see there) so a reasoning judge that simply needs more tokens gets an actionable message instead of an endless malformed-retry loop.

## 8. Parsing strategy

The application parses each judge response in two ordered steps. It always tries the strict step first.

### 8.1 Step 1 — strict JSON parse

Decode the response body as a single JSON object. If the judge provider supports a JSON/structured-output mode, the call already requested `response_format = JSON`, which makes a clean object the expected result.

The strict parse succeeds when the body decodes to a JSON object that contains a `verdict` field whose value, upper-cased and trimmed, is exactly `PASS` or `FAIL`. The `reasoning` field is read if present and valid; if absent, the default reasoning string from §6 is used.

### 8.2 Step 2 — lenient fallback extraction

If the strict parse fails — the body is not a clean JSON object, or it is wrapped in Markdown code fences, or it is surrounded by explanatory prose — apply lenient extraction:

1. Strip any Markdown code fences (` ```json ` … ` ``` ` or ` ``` ` … ` ``` `).
2. Locate the first `{` and the last `}` in the remaining text and attempt to JSON-decode that span as an object.
3. If that still fails, scan the text for a verdict token **adjacent to the literal key `verdict`** — a case-insensitive standalone `PASS` or `FAIL` within the same key/value vicinity (e.g. `"verdict": "PASS"`, `verdict: FAIL`, `verdict - PASS`). A bare `PASS`/`FAIL` appearing elsewhere in free-form prose is **NOT** accepted as the verdict (it too often appears inside reasoning such as "this does not fail to…"), to avoid manufacturing a confident verdict from ambiguous text (D-R-04, MISS-09). If exactly one key-adjacent token is found, take it as the verdict and the rest of the cleaned text (capped at 2000 characters) as the reasoning. If none is found, treat the response as malformed and retry per §9.1 rather than guessing.

Lenient extraction **succeeds** only when it yields an unambiguous verdict (`PASS` or `FAIL`). If the text contains both tokens with no clear `verdict`-key association, or contains neither, extraction fails and the response is malformed.

### 8.3 Same parser for every judge call

The per-task judge phase uses the parser defined here. The run-level analysis (§12) does not use this parser — its output is free-form narrative text, not a verdict object — so the two are deliberately separate.

## 9. Malformed-response handling and retry

A judge response is **malformed** when both Step 1 and Step 2 of §8 fail to yield an unambiguous verdict. On a malformed response the application retries the judge call for that task with a stricter prompt.

### 9.1 The stricter retry prompt

The retry uses the same task context as the original call (§4.2) but appends a corrective instruction to the system message:

```text
IMPORTANT: A previous attempt did not return a valid response. You must now reply
with exactly one JSON object and nothing else — no Markdown, no code fences, no
text before or after the object. The object must contain exactly the field
"verdict" set to the string "PASS" or "FAIL", and the field "reasoning" set to a
short string. Example of a valid reply:
{"verdict": "FAIL", "reasoning": "The response omits the required error handling."}
```

The retry uses the same sampling settings as §7.

### 9.2 Retry limit

The judge call for a task is retried on a malformed response up to a maximum number of attempts controlled by the setting `eval.judge_max_parse_retries` (default `2`). The default permits one initial call plus two stricter retries — three judge calls in the worst case for a single task.

**Budget-exhausted diagnostic (DD-67).** When the malformed responses across these attempts were **truncated at the completion-token cap** (the response hit `eval.judge_max_completion_tokens` without closing its JSON — characteristic of a reasoning judge model emitting reasoning into the completion), the exhaustion is reported with an actionable message — *"the judge model exhausted its completion-token budget before emitting a verdict; raise `eval.judge_max_completion_tokens` or choose a non-reasoning judge model"* — rather than a bare `ERRORED`. This stops a reasoning judge from looping to `ERRORED` on every task purely because its budget was too small; the user can fix it by raising the cap (Settings → Advanced) or picking a different judge.

A transport failure (timeout, provider unreachable, refused request) is **not** a parse retry. It is handled by the LLM client's own retry policy and the adaptive-timeout budget. The parse-retry count in this section applies only to a response that was received but could not be parsed into a verdict.

### 9.3 Outcome when retries are exhausted

If every attempt up to the limit still yields a malformed response, the judge could not produce a verdict for that task. The result is then handled as follows:

- The result's `status` is set to `ERRORED`.
- `judge_verdict` stays `None` — there is no `UNKNOWN` verdict and the judge produced none.
- `judge_reasoning` is set to a diagnostic string, for example `"Judge returned an unparseable response after 3 attempts."`.
- `error_kind` is set to `OTHER` and `error_message` records the parse failure.
- The result's combined `verdict` stays `None` (a terminal-failure result carries no verdict, per `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.4).
- The result is **retryable** — `ERRORED` is one of the five retryable terminal statuses, so a later Retry or Resume can re-run the task and re-attempt the judge.

A judge **transport** failure that the LLM client cannot recover (provider down, irrecoverable error) is recorded distinctly: the keyword and cosine outcomes for that task still stand, the result keeps whichever combined verdict the prior enabled phases produced, `judge_verdict` stays `None`, and `judge_reasoning` records the transport error. The result is not forced to `ERRORED` solely because the judge endpoint was unreachable — only an unparseable-after-retries response forces `ERRORED`. This distinction keeps a successful keyword+cosine grading usable even when the judge provider is temporarily offline.

## 10. Recording the judge outcome

For each judged task the judge phase writes the following fields onto the `BenchmarkResult` (see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §6.10):

| Field | Value written |
|---|---|
| `judge_verdict` | `PASS` or `FAIL` from the parsed response; `None` if the judge produced no verdict (transport failure or exhausted parse retries). |
| `judge_reasoning` | The parsed `reasoning` string (capped at 2000 characters), or the diagnostic string on failure. |
| `judge_time_ms` | The wall-clock duration of the judge call(s) for this task. |
| `judge_completion_tokens` | The completion-token count reported by the judge provider for the final call. |

The judge phase does not by itself set the result's combined `verdict` or `resolution_layer`; the verdict-combination step (§11) does, after the judge phase completes. The judge phase does not write any numeric quality field — `cosine_similarity` is owned by the cosine phase and never touched here.

## 11. Final-verdict combination

After the judge phase completes for every task, the pipeline computes each result's combined `verdict` (the binary `PASS` / `FAIL` shown to the user) and its `resolution_layer` (which phase decided it). The combination is a cascade over the **enabled** evaluation phases.

The final verdict is always binary — `PASS` or `FAIL`. There is no `UNKNOWN` final verdict; `UNKNOWN` is not a member of the `Verdict` enum. A pending result carries a `None` verdict while phases still run; once grading resolves, the verdict is one of the two binary values, and a terminal-failure result carries no verdict at all.

### 11.1 Deterministic failure short-circuit

Before the phase cascade, classify the deterministic outcome. A **sanity failure** (empty / error-marker response) is always definitive: the judge is **not** called and the result is `FAIL` (DD-62) — there is nothing to grade. A **keyword** failure (missing required exact term or present forbidden term) is a candidate `FAIL` whose finality depends on force-judge: with `eval.force_judge_on_prior_failure` at its **default `false`** (DD-62) the keyword `FAIL` stands as final with `resolution_layer = KEYWORD` and no judge call is spent; set to **`true`**, the judge phase becomes the authoritative final gate and its verdict (§11.4) decides even over the keyword `FAIL`, so the judge can rescue a paraphrased-but-correct answer. (When the judge phase is disabled entirely, the earlier enabled phases decide as before.)

### 11.2 Keyword-only

When the keyword phase is the only enabled grading phase, the keyword phase's binary outcome is the final verdict. `resolution_layer` is `KEYWORD`.

### 11.3 Keyword plus cosine, judge disabled

When the keyword and cosine phases are enabled and the judge phase is disabled:

- If the keyword phase produced a `FAIL`, the final verdict is `FAIL` and `resolution_layer` is `KEYWORD`.
- Otherwise the cosine phase decides: the Cosine Score is compared against the task's response-scope threshold, and the threshold result (`PASS` or `FAIL`) is the final verdict. `resolution_layer` is `COSINE`.

### 11.4 Judge enabled

When the judge phase is enabled, the judge is the verdict arbiter, subject to the prior-phase rule:

- If a prior phase produced a definitive failure (the deterministic `FAIL` of §11.1, or — when configured — a keyword/cosine `FAIL`) **and** force-judge is **off**, that failure is the final verdict; `resolution_layer` is the phase that produced it. The `judge_verdict` is still recorded for inspection but does not override the failure.
- Otherwise the judge's `judge_verdict` is the final verdict; `resolution_layer` is `JUDGE`.
- If the judge produced no verdict (transport failure, exhausted parse retries) the result does not resolve through the judge: a transport failure leaves the result with the verdict from the prior enabled phases (`resolution_layer` `COSINE` or `KEYWORD`), and an exhausted-parse-retries result is `ERRORED` with no verdict (§9.3).

Every phase's individual outcome (`keyword_verdict`, `cosine_verdict`, `judge_verdict`) is preserved on the result regardless of which phase decided the combined verdict, so the Result widget's detail panel can show the full per-phase breakdown.

### 11.5 Combination summary

| Enabled phases | Force-judge | Combined verdict source | `resolution_layer` |
|---|---|---|---|
| keyword only | n/a | keyword outcome | `KEYWORD` |
| keyword + cosine | n/a | keyword `FAIL` short-circuits; else cosine threshold | `KEYWORD` or `COSINE` |
| keyword + cosine + judge | off | prior-phase definitive `FAIL` stands; else judge verdict | `KEYWORD` / `COSINE` / `JUDGE` |
| keyword + cosine + judge | on | judge verdict always decides | `JUDGE` |
| run does not grade | n/a | no verdict produced | `SKIP` |

## 12. The run-level judge analysis is out of scope here

Separate from the per-task judge phase, the application generates one **run-level analysis** — a free-text narrative the judge model writes after the run finishes, comparing the models in the run (speed, accuracy, trade-offs, the effect of quantisation, differences between providers serving the same model). That narrative is stored in `BenchmarkRun.run_analysis`, is **optional in every mode** (default ON in `GRADED`, OFF in `SYNTHETIC` and `TASKS`, user-overridable in any mode), and can be regenerated on demand.

The run-level analysis is **not** governed by this document. It produces no verdict and no JSON object, so it does not use the §6 schema or the §8 parser. It is specified in `05_Result_Widget/tabs/run_analysis_tab.md` and `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md`. The per-task judge stage toggle (`eval.phase_judge_enabled`) does not control the run-level analysis; the two are independent.

## 13. Worked examples

### 13.1 Well-formed PASS

Task: a `code_generation` task asking for a recursive Fibonacci function. The model under test returned a correct recursive implementation that named the function `fibonacci` rather than the `fib` used in the golden answer. The keyword phase failed because the exact term `def fib` was absent.

Judge response body:

```json
{"verdict": "PASS", "reasoning": "The function is a correct recursive Fibonacci implementation and returns the right value for every listed input; the different function name does not affect correctness."}
```

Strict parse succeeds. `judge_verdict = PASS`, `judge_reasoning` stored. With the judge phase enabled and force-judge off, the keyword `FAIL` was a missing-exact-term failure; per §11.1 a missing exact term is a deterministic `FAIL` that stands unless force-judge is on. If force-judge is on, the final verdict is `PASS` via `JUDGE`. This example shows why a user who wants the judge to rescue paraphrased-but-correct answers enables force-judge.

### 13.2 Fenced JSON recovered by the lenient parser

Judge response body:

````text
Here is my evaluation:
```json
{"verdict": "FAIL", "reasoning": "The response omits the required input validation."}
```
````

Strict parse fails (prose before the object, code fences). Lenient extraction strips the fences, finds the object between the first `{` and last `}`, and decodes it. `judge_verdict = FAIL`. No retry is needed — lenient extraction succeeded.

### 13.3 Malformed response, recovered on retry

First judge response body:

```text
The candidate answer looks mostly right but I am not fully sure.
```

Strict parse fails; lenient extraction finds no `PASS`/`FAIL` token — malformed. The application retries with the stricter prompt (§9.1). Retry response body:

```json
{"verdict": "PASS", "reasoning": "The answer covers all required points."}
```

Strict parse succeeds on the retry. `judge_verdict = PASS`. Two judge calls were made for this task; `eval.judge_max_parse_retries` (default 2) was not exhausted.

### 13.4 Malformed response, retries exhausted

Every attempt up to `eval.judge_max_parse_retries + 1` total calls returns prose with no extractable verdict. Per §9.3 the result `status` becomes `ERRORED`, `judge_verdict` stays `None`, `judge_reasoning` records `"Judge returned an unparseable response after 3 attempts."`, `error_kind` is `OTHER`, the combined `verdict` is `None`, and the result is retryable.

## 14. Edge cases

| Edge case | Handling |
|---|---|
| Task has no `golden_answer` | The reference-answer line states `(none provided)`; the judge grades against the question and the pass/fail criteria. |
| Task has empty `pass_criteria` | The pass-criteria line states `(none provided — judge against the question and reference answer)`; judging proceeds. |
| Judge returns a verdict in lower case (`"pass"`) | Accepted; normalised to upper case before mapping to the `Verdict` enum. |
| Judge returns `verdict` but no `reasoning` | Accepted; `judge_reasoning` is set to `"(no reasoning provided by judge)"`. |
| Judge returns extra fields (e.g. a `score`) | Extra fields are ignored; only `verdict` and `reasoning` are read. Any numeric field the judge volunteers is discarded — the judge contributes no numeric value. |
| Judge returns both `PASS` and `FAIL` in free text with no clear `verdict` key | Treated as malformed; retried per §9. |
| Judge response truncated at the `eval.judge_max_completion_tokens` cap before the JSON closes | Treated as malformed; retried per §9, which surfaces the budget-exhausted diagnostic when the truncation recurs (DD-67). |
| Judge provider unreachable for the whole phase | Each task's judge call fails at transport; `judge_verdict` stays `None`; the combined verdict falls back to the prior enabled phases; the result is not `ERRORED` solely for this reason. |
| Judge phase disabled mid-configuration | The phase does not run; `judge_verdict` stays `None` for every result; the verdict cascade uses only keyword (and cosine). |
| Result has no response (terminal inference failure) | Not judged; `judge_verdict` stays `None`. |
| `category` / `sub_category` absent | The area line reads `TASK AREA: (uncategorized)`; judging proceeds normally (DD-46). |

## 15. Test cases

1. A well-formed `{"verdict": "PASS", "reasoning": ...}` body parses on the strict step with no retry.
2. A `FAIL` verdict body parses on the strict step and maps to `Verdict.FAIL`.
3. A body wrapped in ` ```json ` fences with surrounding prose parses on the lenient step with no retry.
4. A body with a leading sentence and a trailing sentence around a bare object parses on the lenient step.
5. A body with only the standalone word `FAIL` adjacent to the key `verdict` parses on the lenient step.
6. A body with neither `PASS` nor `FAIL` is malformed; exactly one stricter retry is issued; a valid retry response resolves the task.
7. With `eval.judge_max_parse_retries = 2`, three consecutive malformed responses set the result to `ERRORED`, leave `judge_verdict` `None`, set `error_kind` to `OTHER`, and leave the result retryable.
8. A judge transport timeout leaves `judge_verdict` `None`, does not set the result to `ERRORED`, and leaves the combined verdict equal to the prior enabled phases' result.
9. A verdict returned in lower case is normalised and accepted.
10. A response containing a `score` field is accepted; the score is ignored and no numeric judge value is stored.
11. With the judge phase enabled and force-judge off, a keyword missing-exact-term `FAIL` is the final verdict with `resolution_layer = KEYWORD`, and `judge_verdict` is still recorded.
12. With force-judge on, a judge `PASS` overrides a keyword missing-exact-term `FAIL`; the final verdict is `PASS` with `resolution_layer = JUDGE`.
13. The judge call is issued with temperature `0.0` and the `eval.judge_max_completion_tokens` completion cap (default 4096, DD-67).
14. The system message is identical for every task except the `{category} / {sub_category}` area line; no rubric text exists (DD-46). A task with neither field produces `TASK AREA: (uncategorized)`.
14a. The judge prompt contains no keyword-phase or cosine-phase outcome — prior-stage results are never mentioned to the judge (DD-46).
14b. A judge call that fails with `ProviderContextLengthError` is not retried; the result settles `ERRORED` with an error message that names the judge model, includes the provider's reported detail, and advises a larger-context judge model (DD-46).
15. **Anonymous Judging (SPEC-018).** For every task, the assembled judge prompt — system message AND user message — contains no provider identifier and no test-model name; asserted against prompts built for a run whose judge is also a test model.
16. A judged task that passed keyword and cosine is still sent to the judge (full per-task pass, not tie-breaker-only).
17. The judge always receives `sanitized_response`, never `raw_response`.
18. A task with no `golden_answer` produces a prompt whose reference-answer line reads `(none provided)`; the judge call still runs.
