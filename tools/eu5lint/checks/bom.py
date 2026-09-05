"""Check per-path UTF-8 BOM policy."""

from collections.abc import Iterator, Sequence

from config import bom_policy, matching_bom_rule
from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path, is_text_path


_BOM = b"\xef\xbb\xbf"


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    for source in files:
        if (
            not is_payload_path(source.relpath)
            or not is_text_path(source.relpath)
            or source.relpath == ".metadata"
            or source.relpath.startswith(".metadata/")
        ):
            continue

        rule = matching_bom_rule(ctx.config, source.relpath)
        policy = bom_policy(ctx.config, source.relpath)
        has_bom = source.data.startswith(_BOM)
        finding: Finding | None = None
        rule_name = rule.glob if rule is not None else "the default BOM policy"

        if policy == "required" and not has_bom:
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5001",
                f"UTF-8 BOM is required by the {rule_name!r} rule; "
                "add bytes EF BB BF at the start of the file.",
            )
        elif policy == "forbidden" and has_bom:
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5002",
                f"UTF-8 BOM is forbidden by the {rule_name!r} rule; "
                "remove the first three bytes EF BB BF from the file.",
            )
        elif policy == "warn_required" and not has_bom:
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5003",
                f"UTF-8 BOM is advisory-required by the {rule_name!r} rule; "
                "add bytes EF BB BF if following the directory convention. "
                "This warning does not block.",
            )
        elif policy == "warn_only":
            state = "carries" if has_bom else "lacks"
            action = "keep it or remove it consistently with nearby files"
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5003",
                f"This file {state} a UTF-8 BOM under the {rule_name!r} "
                "warn-only rule; the base game does both. "
                f"{action}; this warning never blocks.",
            )

        if finding is not None:
            yield finding
