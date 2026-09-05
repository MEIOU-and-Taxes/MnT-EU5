"""Check unsafe and nested override keywords in .txt payloads."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath
import re

from checks.braces import scan
from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


_SCRIPTED_DIRECTORIES = frozenset(
    {
        "in_game/common/scripted_effects",
        "in_game/common/scripted_triggers",
        "main_menu/common/scripted_triggers",
    }
)
_OVERRIDE_KEYWORDS = (
    b"INJECT:",
    b"REPLACE:",
    b"TRY_INJECT:",
    b"TRY_REPLACE:",
    b"INJECT_OR_CREATE:",
    b"REPLACE_OR_CREATE:",
)
_INJECT_LINE = re.compile(r"^\s*INJECT:")


def _is_txt_payload(source: SourceFile) -> bool:
    return is_payload_path(source.relpath) and source.relpath.lower().endswith(
        ".txt"
    )


def _in_scripted_directory(source: SourceFile) -> bool:
    relative = PurePosixPath(source.relpath).as_posix()
    return any(
        relative.startswith(f"{directory}/")
        for directory in _SCRIPTED_DIRECTORIES
    )


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    for source in files:
        if not _is_txt_payload(source):
            continue

        result = scan(source.data, _OVERRIDE_KEYWORDS)
        if _in_scripted_directory(source):
            text = source.data.decode("utf-8-sig", errors="replace")
            lines = re.split(r"\r\n|\r|\n", text)
            inject_lines = {
                line_number
                for line_number, _, keyword, _ in result.keyword_hits
                if keyword == b"INJECT:"
            }
            for line_number in sorted(inject_lines):
                if _INJECT_LINE.match(lines[line_number - 1]) is None:
                    continue
                finding = make_finding(
                    ctx.config,
                    source.relpath,
                    line_number,
                    0,
                    "EU5040",
                    "INJECT: silently behaves as REPLACE: in scripted_effects "
                    "and scripted_triggers and destroys the shared effect or "
                    "trigger; REPLACE: is what you write when you mean to "
                    "replace. Remove INJECT: and rerun the linter. M&T uses "
                    "REPLACE: there 8 times and INJECT: zero times.",
                )
                if finding is not None:
                    yield finding

        if result.issues or result.quote_line is not None:
            continue
        for line_number, column, keyword, depth in result.keyword_hits:
            if depth <= 0:
                continue
            keyword_text = keyword.decode("ascii")
            finding = make_finding(
                ctx.config,
                source.relpath,
                line_number,
                column,
                "EU5041",
                f"override keyword {keyword_text!r} is at brace depth {depth}, "
                "but override keywords are top-level-only; move it to a "
                "top-level block in an own-prefixed file or express the nested "
                "data with ordinary supported syntax.",
            )
            if finding is not None:
                yield finding
