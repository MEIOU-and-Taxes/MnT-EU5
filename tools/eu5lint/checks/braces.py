"""Check structural brace and quoted-string balance in .txt payloads."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import re

from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


@dataclass(frozen=True)
class ScanResult:
    issues: tuple[tuple[int, str], ...]
    quote_line: int | None
    keyword_hits: tuple[tuple[int, int, bytes, int], ...]


_TOP_LEVEL_ENTRY = re.compile(
    rb"^[ \t]*(?:(?P<operation>INJECT|REPLACE|TRY_[A-Z_]+|[A-Z_]+_OR_CREATE):"
    rb"[ \t]*)?(?P<key>[^\s=]+)[ \t]*=[ \t]*(?=[^ \t\r\n])"
)


def _identifier_byte(value: int) -> bool:
    return (
        48 <= value <= 57
        or 65 <= value <= 90
        or 97 <= value <= 122
        or value == 95
    )


def scan(data: bytes, keywords: Sequence[bytes] = ()) -> ScanResult:
    line = 1
    column = 1
    index = 0
    in_quote = False
    quote_line = 0
    escaped = False
    comment = False
    openers: list[int] = []
    issues: list[tuple[int, str]] = []
    keyword_hits: list[tuple[int, int, bytes, int]] = []
    keyword_values = tuple(
        sorted({keyword for keyword in keywords if keyword}, key=len, reverse=True)
    )

    while index < len(data):
        byte = data[index]
        if byte == 13 or byte == 10:
            if byte == 13 and index + 1 < len(data) and data[index + 1] == 10:
                index += 2
            else:
                index += 1
            comment = False
            escaped = False if in_quote and escaped else escaped
            line += 1
            column = 1
            continue

        if comment:
            index += 1
            column += 1
            continue

        if in_quote:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_quote = False
            index += 1
            column += 1
            continue

        for keyword in keyword_values:
            previous = data[index - 1] if index else None
            if (
                data.startswith(keyword, index)
                and (previous is None or not _identifier_byte(previous))
            ):
                keyword_hits.append((line, column, keyword, len(openers)))
                break

        if byte == 35:
            comment = True
        elif byte == 34:
            in_quote = True
            quote_line = line
        elif byte == 123:
            openers.append(line)
        elif byte == 125:
            if openers:
                openers.pop()
            else:
                issues.append((line, "excess closing brace '}'"))
        index += 1
        column += 1

    for opener_line in openers:
        issues.append((opener_line, "unmatched opening brace '{'"))
    return ScanResult(
        issues=tuple(issues),
        quote_line=quote_line if in_quote else None,
        keyword_hits=tuple(keyword_hits),
    )


def strip_comments(data: bytes) -> bytes:
    """Replace # comments outside quotes while preserving line positions."""

    result = bytearray(data)
    index = 0
    in_quote = False
    escaped = False
    comment = False
    while index < len(data):
        byte = data[index]
        if byte == 13 or byte == 10:
            if byte == 13 and index + 1 < len(data) and data[index + 1] == 10:
                index += 2
            else:
                index += 1
            comment = False
            escaped = False if in_quote and escaped else escaped
            continue

        if comment:
            result[index] = 32
        elif in_quote:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_quote = False
        elif byte == 35:
            result[index] = 32
            comment = True
        elif byte == 34:
            in_quote = True
        index += 1
    return bytes(result)


def _line_depths(data: bytes) -> tuple[tuple[int, bool], ...]:
    """Return ``(brace_depth, starts_inside_a_string)`` for each line.

    The quote state is the load-bearing half. This scanner already tracked it to
    keep braces inside strings out of the depth count, but only the depth was
    returned, so a caller could not tell a real column-zero definition from a
    line of prose inside a multiline string. It could not, and
    ``probe_ns.1 = {}`` written inside a quoted block was extracted as a genuine
    top-level entry -- a fabricated definition that reached EU5091 and EU5120.
    """

    depths: list[tuple[int, bool]] = [(0, False)]
    index = 0
    in_quote = False
    escaped = False
    comment = False
    openers: list[int] = []
    while index < len(data):
        byte = data[index]
        if byte == 13 or byte == 10:
            if byte == 13 and index + 1 < len(data) and data[index + 1] == 10:
                index += 2
            else:
                index += 1
            comment = False
            escaped = False if in_quote and escaped else escaped
            depths.append((len(openers), in_quote))
            continue

        if comment:
            index += 1
            continue

        if in_quote:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_quote = False
            index += 1
            continue

        if byte == 35:
            comment = True
        elif byte == 34:
            in_quote = True
        elif byte == 123:
            openers.append(index)
        elif byte == 125 and openers:
            openers.pop()
        index += 1
    return tuple(depths)


def top_level_entries(data: bytes) -> tuple[tuple[int, int, str, str], ...]:
    """Return shallow top-level entries after comment stripping.

    Each tuple is ``(line, column, key, operation)``. ``operation`` is the
    top-level override keyword the entry was written with (``INJECT``,
    ``REPLACE``, ``TRY_*``, ``*_OR_CREATE``) or ``""`` for a bare
    ``key = value`` definition. Callers need the distinction: a keyword names
    an explicit operation on an entry defined elsewhere, so two of them on one
    key are not two definitions of it.
    """

    stripped = strip_comments(data)
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = b"   " + stripped[3:]
    depths = _line_depths(data)
    entries: list[tuple[int, int, str, str]] = []
    for line_number, line in enumerate(stripped.splitlines(), start=1):
        if line_number > len(depths):
            continue
        depth, inside_string = depths[line_number - 1]
        if depth != 0 or inside_string:
            continue
        match = _TOP_LEVEL_ENTRY.match(line)
        if match is None:
            continue
        key = match.group("key").decode("utf-8", errors="replace")
        raw_operation = match.group("operation")
        operation = (
            "" if raw_operation is None else raw_operation.decode("ascii", "replace")
        )
        entries.append((line_number, match.start("key") + 1, key, operation))
    return tuple(entries)


def grouped_entries(data: bytes) -> tuple[tuple[int, int, str, str], ...]:
    """Return one-level-nested entries as ``(line, column, "GROUP.KEY", op)``.

    Defines files are organized as groups, and the engine MERGES a group that
    several files contribute to: the base game's own NWeather is split across
    00_defines.txt and graphic/00_graphics.txt with disjoint keys, and both
    plainly apply. Comparing group names would therefore call the normal layout
    a duplicate. The competing definition is a leaf key set twice, one level
    down, which is what actually resolves silently by filename order.
    """

    stripped = strip_comments(data)
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = b"   " + stripped[3:]
    depths = _line_depths(data)
    entries: list[tuple[int, int, str, str]] = []
    group = ""
    for line_number, line in enumerate(stripped.splitlines(), start=1):
        if line_number > len(depths):
            continue
        depth, inside_string = depths[line_number - 1]
        if inside_string:
            continue
        match = _TOP_LEVEL_ENTRY.match(line)
        if match is None:
            continue
        key = match.group("key").decode("utf-8", errors="replace")
        if depth == 0:
            group = key
            continue
        if depth != 1 or not group:
            continue
        raw_operation = match.group("operation")
        operation = (
            "" if raw_operation is None else raw_operation.decode("ascii", "replace")
        )
        entries.append(
            (line_number, match.start("key") + 1, f"{group}.{key}", operation)
        )
    return tuple(entries)


def _scan(data: bytes) -> tuple[list[tuple[int, str]], int | None]:
    result = scan(data)
    return list(result.issues), result.quote_line


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    for source in files:
        if not is_payload_path(source.relpath) or not source.relpath.lower().endswith(
            ".txt"
        ):
            continue

        issues, quote_line = _scan(source.data)
        for issue_line, issue in issues:
            finding = make_finding(
                ctx.config,
                source.relpath,
                issue_line,
                0,
                "EU5020",
                f"{issue}; balance only structural '{{' and '}}' in this .txt "
                "file, then rerun the linter. Square brackets and parentheses are "
                "data-binding syntax and are not balanced here.",
            )
            if finding is not None:
                yield finding
        if quote_line is not None:
            finding = make_finding(
                ctx.config,
                source.relpath,
                quote_line,
                0,
                "EU5021",
                "quoted string opened here but is unterminated; close it at the "
                "intended value, keeping multiline text and escaping literal quotes.",
            )
            if finding is not None:
                yield finding
