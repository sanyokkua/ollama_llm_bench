"""Proves STORY-049-AC-7 (08-D §3-§4)."""

import msgspec

from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens, make_light_theme_tokens


def test_dark_and_light_containers_have_identical_role_coverage() -> None:
    """Proves: STORY-049-AC-7

    Every colour role defined in either token container is defined in both — the Dark and Light
    containers have identical role coverage, and no resolved value is empty.
    """
    dark = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)
    light = make_light_theme_tokens(platform_kind=PlatformKind.LINUX)

    dark_fields = {field.name for field in msgspec.structs.fields(dark.colors)}
    light_fields = {field.name for field in msgspec.structs.fields(light.colors)}

    assert dark_fields == light_fields
    assert all(getattr(dark.colors, name) for name in dark_fields)
    assert all(getattr(light.colors, name) for name in light_fields)
