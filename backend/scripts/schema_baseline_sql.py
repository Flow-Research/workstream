"""Split reviewed PostgreSQL baseline resources without parsing function bodies."""

from __future__ import annotations


def split_sql_statements(source: str) -> tuple[str, ...]:
    """Split SQL on top-level semicolons, preserving quoted and dollar bodies."""
    statements: list[str] = []
    start = 0
    index = 0
    single_quoted = False
    double_quoted = False
    dollar_tag: str | None = None

    while index < len(source):
        character = source[index]
        if dollar_tag is not None:
            if source.startswith(dollar_tag, index):
                index += len(dollar_tag)
                dollar_tag = None
                continue
            index += 1
            continue
        if single_quoted:
            if character == "'":
                if index + 1 < len(source) and source[index + 1] == "'":
                    index += 2
                    continue
                single_quoted = False
            index += 1
            continue
        if double_quoted:
            if character == '"':
                if index + 1 < len(source) and source[index + 1] == '"':
                    index += 2
                    continue
                double_quoted = False
            index += 1
            continue
        if character == "'":
            single_quoted = True
            index += 1
            continue
        if character == '"':
            double_quoted = True
            index += 1
            continue
        if character == "$":
            end = source.find("$", index + 1)
            if end != -1:
                candidate = source[index : end + 1]
                if candidate == "$$" or candidate[1:-1].replace("_", "a").isalnum():
                    dollar_tag = candidate
                    index = end + 1
                    continue
        if character == ";":
            statement = source[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1

    remainder = source[start:].strip()
    if remainder:
        statements.append(remainder)
    if single_quoted or double_quoted or dollar_tag is not None:
        raise ValueError("unterminated quoted value in baseline SQL")
    return tuple(statements)
