"""RFC 4180 CSV escaping and document assembly (`19_TABLE_SERIALIZATION.md` §6.3).

There is **no** formula-injection guard: a field is quoted only when RFC 4180
structurally requires it, and content is never prefixed or altered (AC-3, AC-6,
EC-EXP-1). The CSV output carries no metadata header block.
"""

_QUOTE_TRIGGER_CHARS: frozenset[str] = frozenset({",", '"', "\n", "\r"})


def escape_csv_field(value: str) -> str:
    """Escape one CSV field per RFC 4180 (§6.3).

    Wraps the field in double quotes only when it contains a comma, a double
    quote, a line feed, or a carriage return; doubles any embedded double quote.
    """
    if any(char in value for char in _QUOTE_TRIGGER_CHARS):
        return '"' + value.replace('"', '""') + '"'
    return value


def build_csv_document(*, header: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> str:
    """Assemble a complete CSV document: header row, escaped data rows, one trailing LF.

    The header row is always present, even when ``rows`` is empty (§5, EC-RES-1).
    """
    lines = [",".join(escape_csv_field(cell) for cell in header)]
    lines.extend(",".join(escape_csv_field(cell) for cell in row) for row in rows)
    return "\n".join(lines) + "\n"
