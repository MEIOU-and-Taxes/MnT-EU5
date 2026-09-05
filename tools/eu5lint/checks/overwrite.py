"""Check whole-file base-game overwrites and their declarations."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath

from baseindex import require_base_index
from findings import Finding, is_enabled, make_finding
from sources import Context, SourceFile, is_payload_path, tracked_names


def _mod_paths(files: Sequence[SourceFile]) -> set[str]:
    return {
        source.relpath
        for source in files
        if is_payload_path(source.relpath)
        and PurePosixPath(source.relpath).name != ".gitkeep"
    }


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    if not is_enabled(ctx.config, "EU5030"):
        # Nothing here can report, so do not request the base index -- asking for
        # it when it is unavailable raises EU5900, which would announce that a
        # switched-off check had been skipped. This is the only tier-0 consumer
        # of the index, so with EU5030 off a `check` run needs no install at all.
        return
    base_paths, availability_finding = require_base_index(ctx)
    if availability_finding is not None:
        yield availability_finding
    if base_paths is None:
        return

    mod_paths = _mod_paths(files)
    declared = {rule.path for rule in ctx.config.overwrites}
    for source in files:
        if (
            is_payload_path(source.relpath)
            and PurePosixPath(source.relpath).name != ".gitkeep"
            and source.relpath in base_paths
            and source.relpath not in declared
        ):
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5030",
                "this payload file shadows the complete base-game path, so the "
                "base file is never read; add an own-prefixed file in the same "
                "directory using INJECT: or REPLACE: when possible. If the "
                "whole-file overwrite is really necessary, declare this exact "
                "path in eu5lint.toml with a one-line reason to make it legal.",
            )
            if finding is not None:
                yield finding

    for rule in ctx.config.overwrites:
        if not rule.reason.strip():
            finding = make_finding(
                ctx.config,
                rule.path,
                0,
                0,
                "EU5032",
                "overwrite allowlist entry has an empty reason; add a one-line "
                "reason explaining why the complete base file must be replaced, "
                "or remove the declaration and use INJECT: or REPLACE:.",
            )
            if finding is not None:
                yield finding

        tracked = tracked_names(ctx.root, include_untracked=not ctx.staged)
        known = (
            {path for path in tracked if is_payload_path(path)}
            if tracked is not None
            else mod_paths
        )
        if tracked is None and (not ctx.whole_tree or ctx.staged):
            continue
        stale_reasons: list[str] = []
        if rule.path not in known:
            stale_reasons.append("no such payload file exists in the mod")
        if rule.path not in base_paths:
            stale_reasons.append("the path does not shadow a base-game file")
        if stale_reasons:
            finding = make_finding(
                ctx.config,
                rule.path,
                0,
                0,
                "EU5031",
                "overwrite allowlist entry is stale ("
                + "; ".join(stale_reasons)
                + "); remove it or correct the path, and keep a one-line reason "
                "only for a real complete base-file overwrite.",
            )
            if finding is not None:
                yield finding
