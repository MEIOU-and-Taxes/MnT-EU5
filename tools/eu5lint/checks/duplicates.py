"""Check duplicate shallow top-level entries in common .txt files."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath

from checks.braces import grouped_entries, scan, top_level_entries
from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


def _is_common_txt(source: SourceFile) -> bool:
    parts = PurePosixPath(source.relpath).parts
    return (
        is_payload_path(source.relpath)
        and source.relpath.lower().endswith(".txt")
        and "common" in parts
    )


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    first_seen: dict[tuple[str, str], tuple[str, int]] = {}
    for source in files:
        if not _is_common_txt(source):
            continue
        result = scan(source.data)
        if result.issues or result.quote_line is not None:
            continue
        directory = PurePosixPath(source.relpath).parent.as_posix()
        # Under common/defines/ the top level is a group name, and groups are
        # merged across files by design, so compare the leaf keys instead.
        entries = (
            grouped_entries(source.data)
            if directory.endswith("common/defines")
            else top_level_entries(source.data)
        )
        for line, column, key, operation in entries:
            if operation:
                # INJECT:/REPLACE:/TRY_*:/*_OR_CREATE: name an explicit operation
                # on an entry defined elsewhere -- usually a base-game one -- so
                # they are not competing definitions of the key. Two files that
                # both INJECT: into the same vanilla entry each contribute their
                # own sub-blocks and both apply; reporting that as a duplicate
                # would advise the author to do what they already did.
                continue
            identity = (directory, key)
            first = first_seen.get(identity)
            if first is None:
                first_seen[identity] = (source.relpath, line)
                continue
            finding = make_finding(
                ctx.config,
                source.relpath,
                line,
                column,
                "EU5120",
                f"entry key {key!r} is duplicated in {directory!r}; "
                f"the first definition is in {first[0]}:{first[1]}. Merge or "
                "rename the entries, or make the intended operation explicit "
                "with a supported top-level override keyword. This is advisory "
                "because the shallow tokenizer can misjudge a few EU5 data "
                "directories.",
            )
            if finding is not None:
                yield finding
