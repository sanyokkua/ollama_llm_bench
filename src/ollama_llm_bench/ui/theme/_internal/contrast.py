"""WCAG 2.1 relative-luminance contrast-ratio calculation (08-D §14)."""

_LINEAR_THRESHOLD = 0.03928


def _srgb_channel_to_linear(channel_value: int) -> float:
    normalized = channel_value / 255.0
    if normalized <= _LINEAR_THRESHOLD:
        return normalized / 12.92
    return float(((normalized + 0.055) / 1.055) ** 2.4)


def _relative_luminance(hex_color: str) -> float:
    hex_digits = hex_color.lstrip("#")
    red_int, green_int, blue_int = (int(hex_digits[i : i + 2], 16) for i in (0, 2, 4))
    red = _srgb_channel_to_linear(red_int)
    green = _srgb_channel_to_linear(green_int)
    blue = _srgb_channel_to_linear(blue_int)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground_hex: str, background_hex: str) -> float:
    """Compute the WCAG 2.1 contrast ratio between two `#rrggbb` colours."""
    foreground_luminance = _relative_luminance(foreground_hex)
    background_luminance = _relative_luminance(background_hex)
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)
