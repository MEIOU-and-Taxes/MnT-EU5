"""Report payload placed in a phase the base game never uses for it.

The engine mounts three separate trees -- ``in_game/``, ``main_menu/`` and
``loading_screen/``. A file in the wrong one is invisible rather than wrong: the
phase that wants it never mounted the tree it is in, nothing is logged, and the
mod behaves as though the work is not there. Every other check here catches
something the engine would eventually complain about; this covers the class
where nothing ever complains.

The base game is the only available authority, and it is nearly unambiguous.
Measured on 1.3.11, across the 12,797 manifest paths -- all three mount roots
plus every official DLC layer -- there are 2,368 directories and only 33 appear
under more than one phase.

**This rule states evidence, it does not prescribe a fix.** Observed vanilla
placement is not proof of engine visibility, and every attempt to turn it into
an instruction was wrong in some real case: a directory the base game barely
uses invites "move it to the other phase" when the actual defect is directory
depth, and one it uses as a container invites "descend a level" when the actual
defect is the phase. Both were tried and both misfired, so the message now says
what was observed and leaves the conclusion to a reader who can check the
engine. A finding here means *look at this*, never *do this*.

Known limits, all deliberate:

* Localization is exempt. All three phases mount a ``localization/`` tree and
  the loader matches on filename, so placement there is a real choice.
* A directory the base game does not ship draws no conclusion. Mods add their
  own directories legitimately, and telling those apart from a misplacement
  needs the engine, not a path comparison. This is the largest gap: a file one
  level shallower than vanilla's equivalent -- ``common/graphic/`` against
  ``common/defines/graphic/`` -- is missed, as is a new subdirectory below a
  known one, and so is an entire subsystem moved with its own folder.
* A directory the base game ships under *two* phases is not judged, so putting
  it in the third is missed.
* Only manifest extensions are seen, so binary payload such as ``.png`` under a
  recognised directory is skipped.
* Files sitting directly in a phase root are skipped.

So this fires once per mistake at best, and not at all for several shapes of
mistake. It is a tripwire, not coverage.
"""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath

import manifest as manifest_module
from findings import Finding, make_finding
from sources import Context, SourceFile, is_payload_path


def _phases_by_directory(paths: frozenset[str]) -> dict[str, set[str]]:
    """Map each base-game directory to the phases it is shipped under."""

    index: dict[str, set[str]] = {}
    for path in paths:
        phase, _, remainder = path.partition("/")
        if not remainder:
            continue
        index.setdefault(str(PurePosixPath(remainder).parent), set()).add(phase)
    return index


def _is_judgeable(relpath: str) -> bool:
    posix_path = PurePosixPath(relpath)
    return (
        is_payload_path(relpath)
        and len(posix_path.parts) > 2
        and "localization" not in posix_path.parts
        and posix_path.suffix.lower() in manifest_module.EXTENSIONS
    )


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    vanilla_paths = manifest_module.load(ctx.config.naming.manifest_path)
    if vanilla_paths is None:
        # EU5086 already reports an unreadable manifest; do not repeat it.
        return

    phases = _phases_by_directory(vanilla_paths)
    # The message tells the reader to record an exception when a placement is
    # deliberate, so the exception has to actually silence it. Reusing the
    # naming list keeps one mechanism rather than two: both answer "this path
    # breaks a convention on purpose, and here is why".
    excepted = {rule.path for rule in ctx.config.naming.exceptions}

    for source in files:
        relpath = source.relpath
        if relpath in excepted or not _is_judgeable(relpath):
            continue
        phase, _, remainder = relpath.partition("/")
        directory = str(PurePosixPath(remainder).parent)
        expected = phases.get(directory)
        if not expected or len(expected) != 1 or phase in expected:
            continue
        (only,) = tuple(expected)
        count = sum(
            1
            for path in vanilla_paths
            if str(PurePosixPath(path.partition("/")[2]).parent) == directory
        )
        finding = make_finding(
            ctx.config,
            relpath,
            0,
            0,
            "EU5090",
            f"this file is under {phase!r}, but every base-game file in "
            f"{directory!r} -- {count} of them, counting official DLC -- is "
            f"under {only!r}. The three phases are separate mounts and a file "
            "in the wrong one is invisible rather than wrong, so nothing is "
            "logged either way. This is evidence, not proof: check where the "
            "engine reads this content from, and record a [[naming_exception]] "
            "if the placement is deliberate.",
        )
        if finding is not None:
            yield finding
