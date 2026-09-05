"""Report an event ID defined twice among the files that actually load.

An event is addressed by its fully qualified ID -- ``exploration_monthly.10`` --
not by the file it lives in. A prefixed mod file therefore does not replace the
base-game file it was copied from: both load, the ID is registered twice, and
which definition answers a ``trigger_event`` is decided by load order rather
than by anything the author wrote down.

Unlike most rules here the engine corroborates this one. It reports
``Duplicated event ID '<id>' found`` from ``jomini_eventmanager.cpp``, so a
finding can be checked against ``logs/error.log`` rather than taken on trust.

**No fix is prescribed.** The obvious advice -- rename the file to the base
game's name so it replaces it -- is wrong whenever the base file holds more
events than the mod's: on this tree it would replace a 37-event vanilla file
with a 1-event copy and delete 36 events other files still reference. Whether
to take a whole-file overwrite, re-home the event under an ID of the mod's own,
or leave the duplicate deliberately depends on what the author meant, so the
rule reports the ambiguity and stops there.

Needs an unpacked install to know the base game's IDs, so it is tier 1 and
silent where there is no game root.
"""

from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath
import re

from baseindex import require_base_index
from checks.braces import top_level_entries
from findings import Finding, is_enabled, make_finding
from sources import Context, SourceFile, is_payload_path, tracked_names

# A definition is `<namespace>.<number> = {`. Extraction is delegated to
# top_level_entries, which tracks comments, quoted strings and brace depth --
# a column-zero regex missed 88 indented definitions in vanilla's
# earthquake_events.txt alone, and would have counted text inside a multiline
# string.
_EVENT_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[0-9]+$")
_PHASE_ROOTS = ("in_game", "main_menu", "loading_screen")


def _is_event_file(relpath: str) -> bool:
    parts = PurePosixPath(relpath).parts
    return (
        is_payload_path(relpath)
        and len(parts) > 2
        and parts[1] == "events"
        and relpath.lower().endswith(".txt")
    )


def _ids_in(data: bytes) -> list[str]:
    """Event IDs in definition order, duplicates kept.

    This returned a set until 2026-09-06, which silently discarded the simplest
    collision of all: the same ID defined twice in one file. The engine reports
    that case exactly as it reports a cross-file one, so dropping it here made
    the check quieter than the log it is meant to agree with.
    """

    return [
        key
        for _, _, key, operation in top_level_entries(data)
        if not operation and _EVENT_ID.match(key)
    ]


def _surviving_base_files(ctx: Context) -> dict[str, Path] | None:
    """Resolve base-game event files to the copy that actually loads.

    The mount roots overlay in order and DLC layers sit above them, so a file at
    the same phase-relative path in a later layer replaces the earlier one.
    Unioning every layer instead would report definitions that no longer load.
    """

    layers = list(ctx.config.mount_roots)
    dlc_root = ctx.config.game_root / "game" / "dlc"
    # manifest.py wraps its copy of this listing; this one was missed, so an
    # unreadable DLC layer escaped as PermissionError from audit even after the
    # other was fixed. A partial layer list is not a usable fallback here: it
    # would silently drop a base file and turn a real duplicate into silence.
    try:
        if dlc_root.is_dir():
            layers.extend(
                f"game/dlc/{pack.name}"
                for pack in sorted(dlc_root.iterdir())
                if pack.is_dir()
            )
    except OSError:
        # None, not an empty dict and not a bare return: an empty dict reads as
        # "the base game defines no events", which would silence every real
        # collision, and a bare return hands the caller None against a signature
        # promising a dict. The caller turns this into the incomplete-scan
        # finding EU5092 already exists for.
        return None

    surviving: dict[str, Path] = {}
    for layer in layers:
        for phase in _PHASE_ROOTS:
            events = ctx.config.game_root / layer / phase / "events"
            if not events.is_dir():
                continue
            for path in sorted(events.rglob("*.txt")):
                relative = f"{phase}/events/{path.relative_to(events).as_posix()}"
                surviving[relative] = path
    return surviving


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    if not is_enabled(ctx.config, "EU5091") and not is_enabled(ctx.config, "EU5092"):
        # Nothing here can report, so do not walk the install or ask for the
        # base index -- that request raises EU5900 on a run that wanted neither.
        return

    event_files = [source for source in files if _is_event_file(source.relpath)]
    if not event_files:
        return

    base_paths, availability_finding = require_base_index(ctx)
    if availability_finding is not None:
        yield availability_finding
    if base_paths is None:
        return

    # Which base files a mod file replaces is a property of the whole mod, not of
    # the subset this run was handed, so ask Git rather than the scanned files.
    tracked = tracked_names(ctx.root, include_untracked=not ctx.staged)
    mod_paths = (
        {path for path in tracked if _is_event_file(path)}
        if tracked is not None
        else {source.relpath for source in event_files}
    )

    surviving = _surviving_base_files(ctx)
    if surviving is None:
        finding = make_finding(
            ctx.config,
            "",
            0,
            0,
            "EU5092",
            "the base game's DLC directory could not be listed, so which base "
            "event files survive is unknown and EU5091 is skipped rather than "
            "reported from a partial layer list.",
        )
        if finding is not None:
            yield finding
        return

    unreadable: list[str] = []
    base_ids: dict[str, str] = {}
    for relative, path in surviving.items():
        if relative in mod_paths:
            # Replaced outright by the mod, so its definitions are gone.
            continue
        try:
            data = path.read_bytes()
        except OSError:
            unreadable.append(relative)
            continue
        for event_id in set(_ids_in(data)):
            base_ids.setdefault(event_id, relative)

    if unreadable:
        finding = make_finding(
            ctx.config,
            "",
            0,
            0,
            "EU5092",
            f"{len(unreadable)} base-game event file(s) could not be read, so "
            f"this scan is incomplete and EU5091 may be missing duplicates. "
            f"First: {unreadable[0]}.",
        )
        if finding is not None:
            yield finding

    # A mod file replacing a base file still competes with every OTHER base file
    # and with the mod's own siblings, so no file is exempt as a whole.
    seen_in_mod: dict[str, str] = {}
    for source in sorted(event_files, key=lambda item: item.relpath):
        counts = Counter(_ids_in(source.data))
        for event_id in sorted(counts):
            if counts[event_id] > 1:
                finding = make_finding(
                    ctx.config,
                    source.relpath,
                    0,
                    0,
                    "EU5091",
                    f"event {event_id!r} is defined {counts[event_id]} times "
                    "in this file, so the ID is registered more than once from a "
                    "single source. Which definition answers a trigger_event is "
                    "decided by load order within the file rather than by "
                    'anything written down; the engine reports "Duplicated event '
                    'ID" for this in logs/error.log. No fix is suggested: which '
                    "of the definitions was meant to survive is not something a "
                    "filename comparison can tell.",
                )
                if finding is not None:
                    yield finding
            origin = base_ids.get(event_id)
            earlier = seen_in_mod.setdefault(event_id, source.relpath)
            if origin is None and earlier == source.relpath:
                continue
            other, whose = (
                (origin, "the base game") if origin is not None else (earlier, "this mod")
            )
            if other == source.relpath:
                continue
            finding = make_finding(
                ctx.config,
                source.relpath,
                0,
                0,
                "EU5091",
                f"event {event_id!r} is also defined by {whose} in {other!r}, "
                "and neither file replaces the other, so both load and the ID is "
                "registered twice. Which definition answers a trigger_event is "
                "decided by load order rather than by anything written down; the "
                'engine reports the same thing as "Duplicated event ID" in '
                "logs/error.log. No fix is suggested: replacing the other file "
                "wholesale means owning every event in it, and re-homing the "
                "event under a new ID means updating whatever triggers it.",
            )
            if finding is not None:
                yield finding
