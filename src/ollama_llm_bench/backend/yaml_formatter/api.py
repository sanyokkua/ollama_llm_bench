"""Public factory for the YAML formatter — the single writer of task files."""

import icontract

from ollama_llm_bench.backend.yaml_formatter._internal.formatter_impl import _YamlFormatterImpl
from ollama_llm_bench.backend.yaml_formatter.protocols import YamlFormatter

__all__: list[str] = ["make_yaml_formatter"]


@icontract.ensure(lambda result: result is not None)
def make_yaml_formatter() -> YamlFormatter:
    """Construct the comment-preserving, atomically saving ``YamlFormatter`` (§6).

    Returns:
        A stateless, synchronous ``YamlFormatter``. Callers run its blocking
        methods off the UI thread.
    """
    return _YamlFormatterImpl()
