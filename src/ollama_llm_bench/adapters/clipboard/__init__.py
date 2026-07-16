"""System clipboard write surface (08-E §21b). Places text on the OS clipboard
unchanged -- the local-app threat model does not redact user-owned clipboard content.
"""

from ollama_llm_bench.adapters.clipboard.api import Clipboard, make_clipboard

__all__: list[str] = ["Clipboard", "make_clipboard"]
