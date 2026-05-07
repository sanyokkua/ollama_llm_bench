# Benchmark Task YAML Specification

This document defines the format and rules for benchmark task files used by Ollama LLM Bench.
Task files are the input to the benchmark pipeline: each task defines a prompt, a correct answer,
and grading criteria that drive a 4-layer automatic evaluation.

---

## File Format

Tasks are stored in YAML files, one file per task or multiple tasks per file.
The preferred top-level structure is a `tasks:` list:

```yaml
tasks:
  - task_id: "my_task_id"
    ...
  - task_id: "another_task_id"
    ...
```

Two alternative structures are also accepted:

- **Bare list** — top-level list with no wrapping key
- **Single dict** — top-level object (treated as one task)

Files must be UTF-8 encoded with `.yaml` or `.yml` extension.

### File Naming

Use descriptive `snake_case` names that reflect the task domain:

```
coding_java_two_sum_indices.yaml
text_operations_translation_ukrainian_to_english.yaml
general_knowledge_ai_transformer.yaml
```

### Deduplication

`task_id` must be unique across all loaded files. If the same `task_id` appears more than once,
the first occurrence is kept and subsequent duplicates are silently discarded.

---

## Field Reference

### Required Fields

The loader rejects a task entry (skips it with a warning) if any of these fields is missing or empty.

| Field | YAML type | Constraint |
|---|---|---|
| `task_id` | string | Non-empty. Unique across all files. |
| `task_type` | string (enum) | Must be one of the 8 values listed in [TaskType](#tasktype). |
| `question` | string | Non-empty. The exact prompt sent to the model under test. |
| `golden_answer` | string | Non-empty. The canonical correct answer used by Layer 3 (cosine) and Layer 4 (LLM judge). |

### Conditionally Required Fields

These fields are parsed but default to an empty string when absent. Omitting them is valid;
providing them improves Layer 4 judge accuracy.

| Field | YAML type | Default | Purpose |
|---|---|---|---|
| `category` | string | `""` | Top-level grouping label (e.g. `"Coding"`, `"General Knowledge"`). |
| `sub_category` | string | `""` | Second-level grouping label (e.g. `"Java"`, `"AI"`). |
| `pass_criteria` | string | `""` | Human-readable rules describing what a passing response must include. Injected into the Layer 4 judge prompt. |
| `fail_criteria` | string | `""` | Human-readable rules describing what makes a response fail. Injected into the Layer 4 judge prompt. |

### Optional Fields

Omitting these fields is safe; the pipeline handles `None` values gracefully.

| Field | YAML type | Default | Purpose |
|---|---|---|---|
| `difficulty` | string (enum) | `medium` | Metadata label: `easy`, `medium`, or `hard`. Not used in evaluation; used for results breakdown. |
| `response_scope` | string (enum) | `contains` | Selects cosine similarity thresholds in Layer 3. See [ResponseScope](#responsescope). Has no effect for `code_generation`, `code_review`, and `reasoning` (Layer 3 is skipped for those types). |
| `required_terms` | object | none | Keyword constraints for Layer 2. See [required_terms](#required_terms-object). When absent, Layer 2 is skipped entirely. |
| `source_language` | string | null | BCP-47 language code for the source text (e.g. `uk`, `hr`). Intended for `translation` tasks. |
| `target_language` | string | null | BCP-47 language code for the target language (e.g. `en`, `de`). Intended for `translation` tasks. |
| `source_material` | string | null | Reference document or background text. Include in `question` content when relevant. |
| `fail_example` | string | null | A known-bad model response. When present, the validation script verifies that this text produces a FAIL verdict through the pipeline. Strongly recommended. |

---

## Enum Values

### TaskType

`task_type` is the primary routing key. It determines which Layer 4 judge prompt template is used
and whether Layer 3 (cosine similarity) runs at all.

| Value | Layer 3 | Layer 4 judge style |
|---|---|---|
| `code_generation` | **Skipped** | Code quality and correctness |
| `code_review` | **Skipped** | Code quality and correctness |
| `reasoning` | **Skipped** | Logical reasoning and conclusion |
| `translation` | Evaluated | Translation accuracy and fluency |
| `factual_qa` | Evaluated | Factual accuracy |
| `text_rewrite` | Evaluated | Tone, clarity, and coverage |
| `data_extraction` | Evaluated | Structural accuracy and completeness |
| `summarization` | Evaluated | Coverage and conciseness |

### Difficulty

Metadata only. Does not affect evaluation or scoring.

| Value | Meaning |
|---|---|
| `easy` | Routine task; most capable models should answer correctly |
| `medium` | Moderate difficulty; some models may struggle (default when omitted) |
| `hard` | Requires precise recall, complex reasoning, or rare knowledge |

### ResponseScope

Controls the cosine similarity pass/fail thresholds in Layer 3.
Has no effect for `code_generation`, `code_review`, and `reasoning`.

| Value | Pass threshold | Fail threshold | Use when |
|---|---|---|---|
| `exact` | 0.92 | 0.30 | Response must reproduce the golden_answer almost verbatim (e.g. a specific JSON structure, a precise numeric answer) |
| `contains` | 0.85 | 0.25 | Response must contain the key information of golden_answer (default; suitable for most tasks) |
| `covers` | 0.75 | 0.20 | Response covers the same topic broadly; wording may differ substantially (e.g. open-ended rephrasing) |

A similarity score ≥ pass threshold → terminal **PASS**.
A similarity score ≤ fail threshold → terminal **FAIL**.
A score between the two thresholds → non-terminal **UNKNOWN**, pipeline continues to Layer 4.

---

## `required_terms` Object

The `required_terms` field enables Layer 2 keyword evaluation. It is a nested object with three
optional sub-lists. Any sub-list may be omitted or set to `[]`.

```yaml
required_terms:
  exact:
    - "HashMap"          # must appear verbatim in the response
  semantic:
    - "single pass"      # must match with embedding similarity ≥ 0.70
  forbidden:
    - "nested loop"      # must NOT appear in the response
```

| Sub-field | Type | Behavior on match failure |
|---|---|---|
| `exact` | list of strings | Any missing term → terminal **FAIL** |
| `semantic` | list of strings | Any term with embedding similarity < 0.70 → terminal **FAIL** |
| `forbidden` | list of strings | Any term present in the response → terminal **FAIL** |

If all `exact` terms are present, all `semantic` terms match above threshold, and no `forbidden`
terms appear, Layer 2 returns a terminal **PASS** and the pipeline stops.

If `required_terms` is absent, or all three sub-lists are empty, Layer 2 is skipped.

---

## 4-Layer Evaluation Pipeline

Layers execute in order. The first layer to produce a terminal verdict (PASS or FAIL) stops the
pipeline; remaining layers are not called.

| Layer | Name | Always runs | Terminal on |
|---|---|---|---|
| 1 | Rule-Based | Yes | Empty response, response that echoes the question, response below minimum length → FAIL |
| 2 | Keyword | Only if `required_terms` has at least one term | Missing `exact`, low-similarity `semantic`, or present `forbidden` → FAIL; all constraints met → PASS |
| 3 | Cosine Similarity | Only for task types **not** in `{code_generation, code_review, reasoning}` | Score ≥ pass threshold → PASS; score ≤ fail threshold → FAIL |
| 4 | LLM Judge | If no prior layer gave a terminal verdict | Structured JSON verdict from the judge model → PASS or FAIL |

Layer 4 uses `task_type` to select a system prompt template, and injects `question`,
`golden_answer`, `pass_criteria`, and `fail_criteria` into the user prompt.

---

## Validation Script Contract

Run `scripts/validate_tasks.py <file_or_dir>` to validate task files before committing.

- **`golden_answer`** must not produce a FAIL verdict when evaluated by the pipeline.
  A task whose golden_answer fails its own evaluation is malformed.
- **`fail_example`** (if present) must produce a FAIL verdict.
  If it does not, the task's grading criteria are not strict enough to catch bad answers.
- Malformed files (YAML parse errors, missing required fields, invalid enum values) are
  skipped with a warning. They do not cause a script error unless the entire file is invalid.

Exit codes: `0` = all tasks passed, `1` = at least one task failed or path error.

Flags:
- `--skip-llm-judge` — disables Layer 4; useful for offline validation
- `--providers-yaml <path>` — override the bundled `providers.yaml`

---

## Authoring Guidelines

**`task_id`**
Use `snake_case`. Build the ID from domain + sub-domain + task description:
`coding_java_two_sum_indices`, `text_operations_translation_ukrainian_to_english`.
Keep it globally unique across the entire dataset.

**`category` / `sub_category`**
Free text. Use consistent values within a domain so results can be grouped.
Examples: `"Coding"` / `"Java"`, `"Text Operations"` / `"Translation"`, `"General Knowledge"` / `"AI"`.

**`question`**
Write the exact prompt you want the model to receive. Use YAML block scalar (`|`) for multi-line
text or prompts that include code blocks.

**`golden_answer`**
Write a single, complete, correct answer. This is used both as the cosine reference (Layer 3)
and as the judge reference (Layer 4). For code tasks, include the working implementation.
Use YAML block scalar (`|`) for multi-line answers.

**`pass_criteria` / `fail_criteria`**
Be concrete and specific. List required elements by name:

```
# Good
pass_criteria: "Uses HashMap to find complements in O(n) time. Returns correct indices. Handles no-solution case."

# Too vague
pass_criteria: "Correct and efficient solution."
```

**`response_scope`**
- `data_extraction`, `translation` with a specific target text → `exact`
- `factual_qa`, general text tasks → `contains` (default; omit if unsure)
- `text_rewrite`, `summarization` → `covers`
- `code_generation`, `code_review`, `reasoning` → omit; Layer 3 does not run for these types

**`required_terms`**
- `exact`: terms that must appear literally (case-sensitive). Use for specific tokens like method
  names, numeric literals, or required syntax. Keep the list small — only the most discriminating terms.
- `semantic`: concepts that must appear in spirit. Use for domain vocabulary where paraphrasing is acceptable.
- `forbidden`: phrases that definitively indicate a wrong approach. Populate from the `fail_criteria`.

**`fail_example`**
Strongly recommended for every task. Write a realistic bad answer — not gibberish, but a plausible
incorrect response that a weak model might produce. This confirms that the forbidden terms and
fail_criteria actually cause a FAIL verdict.

**`source_language` / `target_language`**
Use BCP-47 codes: `en` (English), `uk` (Ukrainian), `hr` (Croatian), `de` (German), `fr` (French), etc.
Always provide both fields for `translation` tasks.

---

## Examples

### `code_generation`

```yaml
tasks:
  - task_id: "coding_java_two_sum_indices"
    category: "Coding"
    sub_category: "Java"
    task_type: code_generation
    difficulty: medium
    response_scope: covers
    question: "Write a Java function that, given an array of integers and a target sum, returns the indices of two distinct elements whose values add up to the target. The solution must run in O(n) time and use O(n) extra space. Handle cases where no valid pair exists and where duplicate values are present."
    golden_answer: |
      public int[] twoSum(int[] nums, int target) {
          Map<Integer, Integer> map = new HashMap<>();
          for (int i = 0; i < nums.length; i++) {
              int complement = target - nums[i];
              if (map.containsKey(complement)) {
                  return new int[] { map.get(complement), i };
              }
              map.put(nums[i], i);
          }
          return new int[0];
      }
    pass_criteria: "Uses a HashMap to store visited elements and find complements in a single pass, ensuring O(n) time and O(n) space complexity. Handles no-solution and duplicates correctly."
    fail_criteria: "The solution has worse than O(n) time complexity (e.g., nested loops), returns incorrect indices, fails on duplicate values, or is not implemented in valid Java."
    required_terms:
      exact:
        - "HashMap"
        - "containsKey"
      semantic:
        - "complement"
        - "single pass"
      forbidden:
        - "nested loop"
        - "O(n^2)"
        - "brute force"
```

### `code_review`

```yaml
tasks:
  - task_id: "coding_python_sql_injection_review"
    category: "Coding"
    sub_category: "Python"
    task_type: code_review
    difficulty: easy
    question: |
      Review the following Python function and identify any security issues:

      ```python
      def get_user(username):
          query = "SELECT * FROM users WHERE username = '" + username + "'"
          return db.execute(query)
      ```
    golden_answer: "The function is vulnerable to SQL injection. The username parameter is concatenated directly into the query string. Fix by using parameterized queries: `db.execute('SELECT * FROM users WHERE username = ?', (username,))`."
    pass_criteria: "Identifies SQL injection as the vulnerability. Explains that string concatenation allows arbitrary SQL input. Provides the parameterized query fix."
    fail_criteria: "Does not identify SQL injection. Suggests input sanitization (escaping) instead of parameterized queries. Misidentifies the problem as a logic error rather than a security vulnerability."
    required_terms:
      exact:
        - "SQL injection"
      semantic:
        - "parameterized query"
        - "string concatenation"
      forbidden:
        - "no security issues"
        - "code is safe"
```

### `reasoning`

```yaml
tasks:
  - task_id: "reasoning_probability_three_coin_flips"
    category: "Reasoning"
    sub_category: "Probability"
    task_type: reasoning
    difficulty: medium
    question: "A fair coin is flipped three times. What is the probability of getting at least two heads? Show your reasoning."
    golden_answer: "The probability is 1/2 (50%). There are 8 equally likely outcomes: HHH, HHT, HTH, THH, HTT, THT, TTH, TTT. Outcomes with at least two heads: HHH, HHT, HTH, THH — that is 4 outcomes. 4/8 = 1/2."
    pass_criteria: "Correctly enumerates outcomes or uses combinatorics to reach 1/2 (50%). Shows the favorable outcomes: HHH, HHT, HTH, THH. Reasoning is explicit and correct."
    fail_criteria: "Incorrect probability (not 1/2). Enumeration is incomplete or contains errors. Applies wrong probability formula."
    required_terms:
      exact:
        - "1/2"
      semantic:
        - "at least two heads"
        - "equally likely outcomes"
      forbidden:
        - "1/4"
        - "1/8"
        - "3/8"
```

### `translation`

```yaml
tasks:
  - task_id: "text_operations_translation_ukrainian_to_english"
    category: "Text Operations"
    sub_category: "Translation"
    task_type: translation
    difficulty: easy
    response_scope: contains
    source_language: uk
    target_language: en
    question: |
      Translate the following text to English:
      Добрий день. Я хотів би дізнатися чи можу зняти готівку з банківської карти? Потрібно зняти з картки тисячу двісті сімдесят девʼять євро.
    golden_answer: "Good day. I would like to know if I can withdraw cash from a bank card? I need to withdraw one thousand two hundred seventy-nine euros from the card."
    pass_criteria: "Translated into English. Key details preserved: polite greeting, question about withdrawing cash from a bank card, correct amount of 1279 euros."
    fail_criteria: "Translation inaccurate or not in English. Amount or currency incorrect. Important details omitted."
    required_terms:
      exact:
        - "1279"
      semantic:
        - "cash"
        - "bank card"
        - "withdraw"
      forbidden: []
```

### `factual_qa`

```yaml
tasks:
  - task_id: "general_knowledge_ai_llm_definition"
    category: "General Knowledge"
    sub_category: "AI"
    task_type: factual_qa
    difficulty: medium
    response_scope: contains
    question: |
      What is the precise technical definition of a Large Language Model (LLM) according to the 2023 ACM Computing Classification System, and what specific parameter threshold distinguishes LLMs from smaller language models in academic literature?
    golden_answer: "The 2023 ACM Computing Classification System defines a Large Language Model (LLM) as a neural network-based language model with more than 1 billion parameters, trained on extensive textual corpora using self-supervised learning."
    pass_criteria: "States that LLMs have more than 1 billion parameters as the distinguishing threshold. References neural network or transformer architecture. Mentions training on large text corpora."
    fail_criteria: "Incorrect parameter threshold (e.g., millions instead of billions). Vague definition not specifying the parameter count. Describes LLMs without mentioning the size threshold."
    required_terms:
      exact:
        - "1 billion"
      semantic:
        - "parameter threshold"
        - "language model"
      forbidden: []
```

### `text_rewrite`

```yaml
tasks:
  - task_id: "text_operations_rephrase_direct_english"
    category: "Text Operations"
    sub_category: "Rephrase"
    task_type: text_rewrite
    difficulty: medium
    response_scope: covers
    question: |
      Rephrase the following text into a direct tone while correcting grammar and word order:

      Me and my team is excited to presents the quarterly results. We wants to discusses how this effects the bottom line for next quarter. Please finds time for meeting us.
    golden_answer: "My team and I will present the quarterly results and discuss their impact on next quarter's bottom line. Please schedule a meeting with us."
    pass_criteria: "Direct, clear, concise tone. Grammar corrected. Covers: presenting quarterly results, discussing impact on bottom line, requesting a meeting."
    fail_criteria: "Vague or overly polite phrasing. Grammar errors remain. Missing the meeting request or bottom line discussion."
    required_terms:
      exact: []
      semantic:
        - "quarterly results"
        - "bottom line"
        - "meeting"
      forbidden:
        - "Me and my team is excited to presents"
        - "We wants to discusses"
        - "Please finds time"
```

### `data_extraction`

```yaml
tasks:
  - task_id: "data_extraction_transformation_product_catalog_text_to_json"
    category: "Data Extraction and Transformation"
    sub_category: "Text to JSON"
    task_type: data_extraction
    difficulty: easy
    response_scope: exact
    question: |
      Convert the following product description text into JSON format following these rules:
      - Use camelCase keys
      - Price should be a number without currency symbol
      - In Stock should be a boolean (true/false)
      - Tags should be an array of strings

      Product ID: PROD-1001
      Name: Wireless Bluetooth Headphones
      Price: $99.99
      Category: Electronics
      In Stock: Yes
      Tags: audio, bluetooth, noise-cancelling
    golden_answer: |
      {
        "productId": "PROD-1001",
        "name": "Wireless Bluetooth Headphones",
        "price": 99.99,
        "category": "Electronics",
        "inStock": true,
        "tags": ["audio", "bluetooth", "noise-cancelling"]
      }
    pass_criteria: "All keys in camelCase (productId, inStock). Price is numeric 99.99 without currency symbol. inStock is boolean true. Tags is an array of three strings. All six fields present."
    fail_criteria: "Price includes currency symbol ($). inStock is not boolean (e.g., 'Yes'). Tags are a single string. Keys not in camelCase."
    required_terms:
      exact:
        - "\"productId\""
        - "\"inStock\""
        - "99.99"
        - "true"
      semantic:
        - "camelCase"
        - "array"
      forbidden:
        - "$99"
        - "\"Yes\""
        - "\"in_stock\""
        - "\"in stock\""
```

### `summarization`

```yaml
tasks:
  - task_id: "summarization_release_notes_v2"
    category: "Summarization"
    sub_category: "Technical"
    task_type: summarization
    difficulty: easy
    response_scope: covers
    question: |
      Summarize the following release notes in 2-3 sentences for a non-technical audience:

      Version 2.0 introduces multi-provider support allowing connections to OpenAI, Anthropic, and
      Gemini in addition to local Ollama models. The evaluation pipeline now runs four automatic
      grading layers: rule-based checks, keyword matching, cosine similarity scoring, and an LLM
      judge. The UI has been redesigned with a three-panel layout and dark/light theme support.
      Performance benchmarks now capture time-to-first-token (TTFT) alongside total inference time.
    golden_answer: "Version 2.0 adds support for cloud AI providers alongside local models and introduces automatic multi-layer answer grading. The interface has been redesigned and now measures how quickly the model begins responding."
    pass_criteria: "Covers the key changes: multi-provider support, automatic grading, UI redesign, and TTFT metric. Written in plain language. Two to three sentences."
    fail_criteria: "Omits multi-provider support or automatic grading. Uses technical jargon (cosine similarity, TTFT) without explanation. Exceeds three sentences or copies text verbatim."
    required_terms:
      exact: []
      semantic:
        - "multi-provider"
        - "automatic grading"
        - "interface"
      forbidden:
        - "cosine similarity"
        - "TTFT"
```
