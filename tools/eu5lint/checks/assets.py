"""Check cheap literal texture and image references against mod and base paths."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath
import posixpath
import re

from baseindex import require_asset_index
from checks.braces import strip_comments
from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


_REFERENCE = re.compile(
    rb"(?P<attribute>texture|texture_file|image|picture|icon|sprite)"
    rb"\s*=\s*\"(?P<reference>[^\"]+\.(?:dds|png))\""
)
_REFERENCE_EXTENSIONS = frozenset({".gui", ".asset", ".txt"})


def _is_reference_file(source: SourceFile) -> bool:
    return (
        is_payload_path(source.relpath)
        and PurePosixPath(source.relpath).suffix.lower()
        in _REFERENCE_EXTENSIONS
    )


def _line_col(data: bytes, offset: int) -> tuple[int, int]:
    line = 1
    column = 1
    index = 0
    while index < offset:
        byte = data[index]
        if byte == 10:
            line += 1
            column = 1
        elif byte == 13:
            if index + 1 >= offset or data[index + 1] != 10:
                line += 1
                column = 1
        else:
            column += 1
        index += 1
    return line, column


def _resolved_path(reference: str) -> str:
    return posixpath.normpath(reference)


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    asset_paths, availability_finding = require_asset_index(ctx)
    if availability_finding is not None:
        yield availability_finding
    if asset_paths is None:
        return

    for source in files:
        if not _is_reference_file(source):
            continue
        stripped = strip_comments(source.data)
        for match in _REFERENCE.finditer(stripped):
            reference_bytes = match.group("reference")
            if not reference_bytes.startswith(b"gfx/"):
                continue
            if b"[" in reference_bytes:
                continue
            reference = reference_bytes.decode("utf-8", errors="replace")
            resolved = _resolved_path(reference)
            if resolved in asset_paths:
                continue
            line, column = _line_col(stripped, match.start("reference"))
            attribute = match.group("attribute").decode("ascii")
            finding = make_finding(
                ctx.config,
                source.relpath,
                line,
                column,
                "EU5110",
                f"literal {attribute} reference {reference!r} resolves to the "
                f"phase-relative path {resolved!r}, but that .dds/.png is absent "
                "from the mod and all base mount layers; add the asset at that "
                "phase-relative path or correct the reference. This advisory "
                "skips bare filenames and dynamic paths containing '[', which "
                "are not statically checkable.",
            )
            if finding is not None:
                yield finding
