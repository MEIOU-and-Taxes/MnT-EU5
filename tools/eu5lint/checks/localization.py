"""Check localization filenames, headers, and entry-line shape."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath
import re

from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


_LOCALIZATION_GLOB = "**/localization/**/*.yml"
_FILENAME = re.compile(r"^.+_l_(?P<lang>[A-Za-z0-9_-]+)\.yml$")
ENTRY = re.compile(r'^\s*(?P<key>[^\s:#]+):(?P<version>\d*)\s+".*"\s*(?:#.*)?$')


def _is_localization(source: SourceFile) -> bool:
    path = PurePosixPath(source.relpath)
    return is_payload_path(source.relpath) and path.full_match(_LOCALIZATION_GLOB)


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    for source in files:
        if not _is_localization(source):
            continue

        lines = source.data.decode("utf-8-sig", errors="replace").splitlines()
        meaningful: list[tuple[int, str]] = []
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            meaningful.append((line_number, line))

        filename_match = _FILENAME.fullmatch(PurePosixPath(source.relpath).name)
        if filename_match is None:
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5060",
                "localization filename must end in _l_<lang>.yml; rename it "
                "to include the language suffix, then rerun the linter.",
            )
            if finding is not None:
                yield finding

        header_line_number = meaningful[0][0] if meaningful else None
        if filename_match is not None:
            language = filename_match.group("lang")
            expected_header = f"l_{language}:"
            if not meaningful or meaningful[0][1] != expected_header:
                line_number = header_line_number or 0
                finding = make_finding(
                    ctx.config,
                    source.relpath,
                    line_number,
                    0,
                    "EU5061",
                    f"the first non-blank, non-comment line must be "
                    f"{expected_header}; correct the header or rename the file "
                    "so the language values match.",
                )
                if finding is not None:
                    yield finding

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("#")
                or line_number == header_line_number
            ):
                continue
            if ENTRY.fullmatch(line) is not None:
                continue
            finding = make_finding(
                ctx.config,
                source.relpath,
                line_number,
                0,
                "EU5062",
                "localization entry does not match key:<optional digits> "
                '"value" with an optional trailing # comment; repair this line '
                "or remove it if it is not an entry.",
            )
            if finding is not None:
                yield finding
