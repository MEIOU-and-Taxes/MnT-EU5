"""Check that text payload files use LF line endings."""

from collections.abc import Iterator, Sequence

from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path, is_text_path


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    for source in files:
        if not is_payload_path(source.relpath) or not is_text_path(source.relpath):
            continue
        count = source.data.count(b"\r")
        if count == 0:
            continue
        first = source.data.find(b"\r")
        line = source.data[:first].count(b"\n") + 1
        finding = make_finding(
            ctx.config,
            source.relpath,
            line,
            0,
            "EU5010",
            "CRLF or lone CR line endings violate the house rule for clean diffs, "
            "not an engine requirement: the engine accepts both, the base game is "
            "pure LF, and M&T ships 213 CRLF files that work. Convert all "
            f"{count} offending line ending(s) to LF.",
        )
        if finding is not None:
            yield finding
