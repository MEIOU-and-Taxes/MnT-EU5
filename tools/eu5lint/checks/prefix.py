"""Check the exact configured prefix on engine payload filenames."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath

from findings import Finding, make_finding
from sources import Context, SourceFile, tracked_names


_ENGINE_PAYLOAD_ROOTS = frozenset({"in_game", "main_menu", "loading_screen"})


def _is_engine_payload_path(relpath: str) -> bool:
    parts = PurePosixPath(relpath).parts
    return (
        bool(parts)
        and parts[0] in _ENGINE_PAYLOAD_ROOTS
        and parts[-1] != ".gitkeep"
    )


def _is_engine_payload(source: SourceFile) -> bool:
    return _is_engine_payload_path(source.relpath)


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    engine_files = [source for source in files if _is_engine_payload(source)]
    engine_paths = {source.relpath for source in engine_files}

    # Existence is a repository question, not a scope question -- see the same
    # reasoning in checks/naming.py. Git answers for the whole tree whatever
    # subset this run was given, so the staleness half no longer depends on how
    # the linter happened to be invoked.
    tracked = tracked_names(ctx.root, include_untracked=not ctx.staged)
    known = (
        {path for path in tracked if _is_engine_payload_path(path)}
        if tracked is not None
        else engine_paths
    )
    # A root with no payload at all is a misconfigured root, not a tree whose
    # every exception has rotted. Reporting six confident staleness errors
    # because the linter was pointed one directory off is worse than silence.
    scoped_only = not known or (
        tracked is None and not (ctx.whole_tree and not ctx.staged)
    )

    for exception in ctx.config.prefix_exceptions:
        stale_reasons: list[str] = []
        if not scoped_only and exception.path not in known:
            stale_reasons.append("no such engine payload file exists in the mod")
        if not exception.reason.strip():
            stale_reasons.append("the reason is empty")
        if stale_reasons:
            finding = make_finding(
                ctx.config,
                exception.path,
                0,
                0,
                "EU5052",
                "prefix exception is invalid ("
                + "; ".join(stale_reasons)
                + "); remove it or correct the path, and add a one-line reason "
                "only when that filename must sort specially.",
            )
            if finding is not None:
                yield finding

    if ctx.config.prefix == "PREFIX_UNSET":
        if engine_files:
            finding = make_finding(
                ctx.config,
                "",
                0,
                0,
                "EU5051",
                "mod.prefix is still PREFIX_UNSET while payload files exist; "
                "the prefix is a pending decision and is load-bearing for load "
                "order (filename order decides who wins a contested entry: zz_ "
                "beats aa_ under common/, but a GUI template is "
                "first-definition-wins and aa_ beats zz_) and for make errors. "
                "Set it in eu5lint.toml before any content lands, then rerun "
                "the linter.",
            )
            if finding is not None:
                yield finding
        return

    declared_overwrites = {rule.path for rule in ctx.config.overwrites}
    declared_exceptions = {
        exception.path for exception in ctx.config.prefix_exceptions
    }
    for source in engine_files:
        if (
            source.relpath in declared_overwrites
            or source.relpath in declared_exceptions
        ):
            continue
        if PurePosixPath(source.relpath).name.startswith(ctx.config.prefix):
            continue
        finding = make_finding(
            ctx.config,
            source.relpath,
            0,
            0,
            "EU5050",
            "payload filename does not start with the exact case-sensitive "
            "mod.prefix; rename the basename to carry the configured prefix, "
            "declare a complete base-path overwrite in [[overwrite]] with a "
            "one-line reason, or add a justified [[prefix_exception]] only when "
            "the filename must sort specially.",
        )
        if finding is not None:
            yield finding
