"""Command-line entry point for the stdlib-only eu5lint tool."""

from collections.abc import Sequence
import argparse
import datetime
import os
from pathlib import Path, PurePosixPath
import stat
import sys

# pathlib's full_match(), used by the glob rules, arrives in 3.13. Without this
# the failure is an AttributeError from deep inside a check, which reads like a
# linter bug rather than an environment one.
REQUIRED_PYTHON = (3, 13)
if sys.version_info < REQUIRED_PYTHON:
    raise SystemExit(
        "eu5lint needs Python "
        f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} or newer; this is "
        f"{sys.version_info.major}.{sys.version_info.minor}."
    )
import tempfile

import config as config_module
import manifest as manifest_module
from checks import TIER0, TIER1, Check
from findings import Finding, Severity, format_json, format_text
from sources import Context, SourceError, SourceFile, discover


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eu5lint")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="run tier-0 checks")
    _add_scan_options(check, game_root=True, output=True, staged=True)

    audit = subparsers.add_parser("audit", help="run tier-0 and tier-1 checks")
    _add_scan_options(audit, game_root=True, output=True, staged=False)

    fix_bom = subparsers.add_parser("fix-bom", help="fix required and forbidden BOMs")
    _add_root_options(fix_bom)
    fix_bom.add_argument("--dry-run", action="store_true", help="only report changes")
    fix_bom.add_argument("paths", nargs="*", metavar="PATH")

    prefix = subparsers.add_parser("prefix", help="print the configured file prefix")
    _add_root_options(prefix)

    vanilla_manifest = subparsers.add_parser(
        "vanilla-manifest",
        help="regenerate the committed vanilla path manifest from an install",
    )
    _add_root_options(vanilla_manifest)
    vanilla_manifest.add_argument(
        "--game-root", metavar="DIR", help="base-game install root"
    )
    vanilla_manifest.add_argument(
        "--game-version",
        metavar="VERSION",
        required=True,
        help="base-game version to record in the header, e.g. 1.3.11",
    )
    vanilla_manifest.add_argument(
        "--output", metavar="FILE", help="manifest path (default: the packaged one)"
    )

    return parser


def _add_root_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", metavar="DIR", help="mod root")
    parser.add_argument("--config", metavar="FILE", help="eu5lint.toml path")


def _add_scan_options(
    parser: argparse.ArgumentParser,
    *,
    game_root: bool,
    output: bool,
    staged: bool,
) -> None:
    _add_root_options(parser)
    if game_root:
        parser.add_argument("--game-root", metavar="DIR", help="base-game install root")
        parser.add_argument(
            "--manifest",
            metavar="FILE",
            help="vanilla path manifest to compare filenames against",
        )
    if output:
        parser.add_argument(
            "--format",
            dest="output_format",
            choices=("text", "json"),
            default="text",
            help="finding output format",
        )
    if staged:
        parser.add_argument(
            "--staged",
            action="store_true",
            help="check staged Git blob bytes instead of the worktree",
        )
    parser.add_argument("paths", nargs="*", metavar="PATH")


def _find_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / "eu5lint.toml").is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise config_module.ConfigError(
        f"could not find eu5lint.toml above {start.expanduser().resolve()}"
    )


def _paths(args: argparse.Namespace) -> tuple[Path, Path]:
    root = (
        Path(args.root).expanduser().resolve()
        if args.root is not None
        else _find_root(Path.cwd())
    )
    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config is not None
        else root / "eu5lint.toml"
    )
    return root, config_path


def _load_config(args: argparse.Namespace) -> tuple[Path, config_module.Config]:
    root, config_path = _paths(args)
    game_root_value = getattr(args, "game_root", None)
    game_root = Path(game_root_value).expanduser() if game_root_value else None
    manifest_value = getattr(args, "manifest", None)
    manifest_path = (
        Path(manifest_value).expanduser().resolve() if manifest_value else None
    )
    return root, config_module.load_config(
        config_path,
        game_root_override=game_root,
        manifest_override=manifest_path,
    )


def _sorted_findings(findings: Sequence[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda finding: (
            finding.path,
            finding.line,
            finding.col,
            finding.code,
            finding.message,
        ),
    )


def _run_checks(
    checkers: Sequence[Check], files: Sequence[SourceFile], ctx: Context
) -> list[Finding]:
    findings: list[Finding] = []
    for checker in checkers:
        findings.extend(checker(files, ctx))
    return findings


def _print_findings(
    findings: Sequence[Finding], output_format: str, checked_count: int
) -> None:
    ordered = _sorted_findings(findings)
    if output_format == "json":
        for finding in ordered:
            print(format_json(finding))
        return

    for finding in ordered:
        print(format_text(finding))
    errors = sum(finding.severity is Severity.ERROR for finding in ordered)
    warnings = sum(finding.severity is Severity.WARN for finding in ordered)
    print(
        f"{errors} error(s), {warnings} warning(s) in "
        f"{checked_count} file(s) checked"
    )


def _scan(args: argparse.Namespace, audit: bool) -> int:
    if getattr(args, "staged", False) and args.paths:
        print("eu5lint: --staged cannot be combined with PATH arguments", file=sys.stderr)
        return 2
    try:
        root, config = _load_config(args)
        staged = getattr(args, "staged", False)
        files = discover(root, args.paths, staged=staged)
    except config_module.ConfigError as exc:
        print(f"eu5lint: EU5901 error: {exc}", file=sys.stderr)
        return 2
    except SourceError as exc:
        print(f"eu5lint: source error: {exc}", file=sys.stderr)
        return 2

    ctx = Context(
        config=config,
        root=root,
        tier=0,
        staged=staged,
        whole_tree=not bool(args.paths),
    )
    tier0_findings = _run_checks(TIER0, files, ctx)
    all_findings = list(tier0_findings)
    if audit:
        tier1_ctx = Context(
            config=config,
            root=root,
            tier=1,
            staged=False,
            whole_tree=not bool(args.paths),
            base_index=ctx.base_index,
        )
        all_findings.extend(_run_checks(TIER1, files, tier1_ctx))

    _print_findings(all_findings, args.output_format, len(files))
    if any(finding.severity is Severity.ERROR for finding in tier0_findings):
        return 1
    return 0


def _atomic_write(file_path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(file_path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{file_path.name}.eu5lint-", dir=file_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, file_path)
    except OSError:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def _fix_bom(args: argparse.Namespace) -> int:
    try:
        root, config = _load_config(args)
        files = discover(root, args.paths)
    except config_module.ConfigError as exc:
        print(f"eu5lint: EU5901 error: {exc}", file=sys.stderr)
        return 2
    except SourceError as exc:
        print(f"eu5lint: source error: {exc}", file=sys.stderr)
        return 2

    bom = b"\xef\xbb\xbf"
    changes: list[tuple[Path, bytes, str]] = []
    for source in files:
        rule = config_module.matching_bom_rule(config, source.relpath)
        if rule is None or rule.policy not in {"required", "forbidden"}:
            continue
        has_bom = source.data.startswith(bom)
        if rule.policy == "required" and not has_bom:
            changes.append(
                (root / Path(*PurePosixPath(source.relpath).parts), bom + source.data, "add")
            )
        elif rule.policy == "forbidden" and has_bom:
            changes.append(
                (
                    root / Path(*PurePosixPath(source.relpath).parts),
                    source.data[len(bom) :],
                    "remove",
                )
            )

    for file_path, data, action in changes:
        relative = file_path.relative_to(root).as_posix()
        if args.dry_run:
            print(f"{action} BOM: {relative}")
            continue
        try:
            _atomic_write(file_path, data)
        except OSError as exc:
            print(f"eu5lint: cannot rewrite {relative}: {exc}", file=sys.stderr)
            return 2
        print(f"{action} BOM: {relative}")
    return 0


def _prefix(args: argparse.Namespace) -> int:
    try:
        _, config = _load_config(args)
    except config_module.ConfigError as exc:
        print(f"eu5lint: EU5901 config problem: {exc}", file=sys.stderr)
        return 2
    print(config.prefix)
    return 1 if config.prefix == "PREFIX_UNSET" else 0


def _vanilla_manifest(args: argparse.Namespace) -> int:
    try:
        _, config = _load_config(args)
    except config_module.ConfigError as exc:
        print(f"eu5lint: EU5901 error: {exc}", file=sys.stderr)
        return 2

    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else config.naming.manifest_path
    )
    try:
        paths = manifest_module.collect(config.game_root, config.mount_roots)
    except manifest_module.ManifestError as exc:
        print(f"eu5lint: cannot generate the vanilla manifest: {exc}", file=sys.stderr)
        return 2

    text = manifest_module.render(
        paths, args.game_version, datetime.date.today()
    )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"eu5lint: cannot write {output}: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(paths)} vanilla paths to {output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return _scan(args, audit=False)
    if args.command == "audit":
        return _scan(args, audit=True)
    if args.command == "fix-bom":
        return _fix_bom(args)
    if args.command == "vanilla-manifest":
        return _vanilla_manifest(args)
    return _prefix(args)


if __name__ == "__main__":
    raise SystemExit(main())
