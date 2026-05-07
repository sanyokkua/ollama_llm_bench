---
name: Provider abort + graceful shutdown design (2026-04-22)
description: abort() on LLMProviderApi closes HTTP client to interrupt in-flight requests; MainWindow.closeEvent with 10s drain; BenchmarkFlowApi gains wait_for_completion()
type: project
---

Selected client-close-and-recreate as the abort strategy for all three LLM providers
(OpenAI-compatible, Anthropic, Gemini).

**Why:** `threading.Timer` cannot interrupt a blocking HTTP call — only closing the
underlying `httpx.Client` can. Client recreation is ~1 ms and providers remain
reusable afterward. The existing `except` blocks in each provider already catch
connection errors and return error `InferenceResponse` objects, so the no-throw
pipeline contract is preserved automatically.

**How to apply:**
- Every `LLMProviderApi` concrete class must implement `abort()` = close client +
  recreate client.
- `BenchmarkExecutionTask` tracks the active provider under `_abort_lock`; `stop()`
  calls `abort()` on it immediately.
- `BenchmarkFlowApi` ABC gains `wait_for_completion(timeout_ms: int) -> bool`;
  `QtBenchmarkFlowApi` delegates to `_thread_pool.waitForDone(timeout_ms)`.
- `MainWindow.closeEvent` orchestrates: confirm → `stop_execution()` →
  `wait_for_completion(10_000)` → `event.accept()`.
- Timeout constants standardized: OpenAI-compatible read 660→330 s; Anthropic and
  Gemini now have `httpx.Timeout(connect=10, read=330, write=10, pool=5)`;
  EmbeddingProvider gets read=30 s.
- SIGTERM handler added to `main.py` calling `QApplication.instance().quit()`.
