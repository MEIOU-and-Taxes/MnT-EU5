"""Check brace balance in GUI payload files as an advisory audit."""

from collections.abc import Iterator, Sequence

from checks.braces import scan
from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


def _is_gui(source: SourceFile) -> bool:
    return is_payload_path(source.relpath) and source.relpath.lower().endswith(
        ".gui"
    )


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    for source in files:
        if not _is_gui(source):
            continue
        result = scan(source.data)
        for line, issue in result.issues:
            finding = make_finding(
                ctx.config,
                source.relpath,
                line,
                0,
                "EU5130",
                f"{issue}; this .gui brace check is advisory because the base "
                "game has the same real brace asymmetry in 5 of 483 files "
                "(1.04%), not a parser gap. Inspect the file and correct a real "
                "imbalance, or document why it matches a base-compatible "
                "construct; do not promote this warning to a blocking rule.",
            )
            if finding is not None:
                yield finding
