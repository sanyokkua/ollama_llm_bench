"""Deterministic synthetic prompt construction (spec §6.1 step 4).

Builds the synthetic ``question`` for one ``(input_size, output_size)`` pair: a
fixed neutral filler passage repeated/trimmed by word count to approximate the
input bucket's target token count, treating word count as a tokenizer-free proxy
for token count (this module may only import ``backend/domain`` — no tokenizer
dependency is available), followed by a fixed instruction line asking for a
continuation of approximately the output bucket's target token count. No
randomness, no timestamps — the same arguments always produce the same string.
"""

from typing import Final

__all__: list[str] = ["_build_question"]

_FILLER_PASSAGE: Final[str] = (
    "The quiet library stood at the edge of town, its shelves lined with books "
    "collected over generations. Every afternoon a handful of readers settled "
    "into the worn armchairs near the window, turning pages while rain traced "
    "slow paths down the glass. The librarian moved between the stacks, "
    "returning volumes to their proper places and noting which titles had gone "
    "unread for years. Outside, the town carried on at its usual unhurried "
    "pace, deliveries arriving at the bakery, children walking home from "
    "school, the clock tower marking each hour with a low, steady chime. "
    "Nothing about the scene demanded urgency; it simply continued, day after "
    "day, in the way small towns often do."
)

_FILLER_WORDS: Final[tuple[str, ...]] = tuple(_FILLER_PASSAGE.split())

_OUTPUT_INSTRUCTION_TEMPLATE: Final[str] = (
    "Continue this passage for approximately {tokens} tokens."
)


def _build_question(input_tokens: int, output_tokens: int, /) -> str:
    """Compose a deterministic synthetic prompt (spec §6.1 step 4).

    Args:
        input_tokens: The input bucket's target token count; used as the word
            count of the padded filler passage.
        output_tokens: The output bucket's target token count; interpolated
            into the fixed output-length instruction.

    Returns:
        The filler passage padded to approximately `input_tokens` words,
        followed by the output-length instruction line.
    """
    padded_words = [_FILLER_WORDS[i % len(_FILLER_WORDS)] for i in range(input_tokens)]
    filler = " ".join(padded_words)
    instruction = _OUTPUT_INSTRUCTION_TEMPLATE.format(tokens=output_tokens)
    return f"{filler}\n\n{instruction}"
