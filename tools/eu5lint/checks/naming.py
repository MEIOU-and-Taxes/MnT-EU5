"""Check MEIOU & Taxes file-naming rules against the committed vanilla manifest.

Two facts decide whether a payload filename is right: whether it carries a
configured prefix, and whether the base game ships a file at the same
repo-relative path.

    prefixed + no vanilla twin -> a new file that edits base content with
                                  INJECT:/REPLACE:, which is correct
    bare     + vanilla twin    -> a deliberate whole-file override, correct
    bare     + no vanilla twin -> probably a forgotten prefix, advisory
    prefixed + vanilla twin    -> the file claims both at once, and the engine
                                  reports neither

The last row has no hits against M&T's tree or its history, because no vanilla
basename begins with any of their prefixes; it is a guard, and the detector for
configuring a prefix the base game itself uses. The reading under which that row
would be busy — strip the prefix, then look for a vanilla twin — was measured at
84 findings on M&T's develop, essentially all of them correct files, and
rejected. See docs/DEFERRED.md.

A file with an exact vanilla twin and no prefix is a whole-file override, so its
filename is the base game's and none of the prefix rules judge it. That matters:
the base game ships rgo_mesh_lists.txt, which a configured RGO_ would otherwise
read as a near miss.

Filenames come from Git, never from the filesystem, because every rule here is
case-sensitive and a case-insensitive filesystem cannot be asked about case.
"""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath

import manifest as manifest_module
from findings import Finding, make_finding
from sources import Context, SourceFile, tracked_names


_ENGINE_PAYLOAD_ROOTS = frozenset({"in_game", "main_menu", "loading_screen"})

EXACT = "exact"
NEAR_MISS = "near_miss"
NONE = "none"


def is_checkable(relpath: str) -> bool:
    """Only engine payload the manifest can actually answer questions about.

    Extensions outside the manifest's scope are skipped rather than guessed at:
    the manifest cannot say whether a ``.dds`` has a vanilla twin, so claiming
    it has none would invent findings.
    """

    posix_path = PurePosixPath(relpath)
    parts = posix_path.parts
    return (
        bool(parts)
        and parts[0] in _ENGINE_PAYLOAD_ROOTS
        and parts[-1] != ".gitkeep"
        and posix_path.suffix.lower() in manifest_module.EXTENSIONS
    )


def prefix_state(name: str, prefixes: Sequence[str]) -> tuple[str, str]:
    """Classify a basename as carrying a prefix exactly, nearly, or not at all.

    ``prefixes`` is expected longest-first so a longer configured prefix always
    wins over a shorter one it contains.
    """

    for prefix in prefixes:
        if name.startswith(prefix):
            return EXACT, prefix
    lowered = name.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            return NEAR_MISS, prefix
    return NONE, ""


def double_prefix(name: str, prefixes: Sequence[str]) -> tuple[str, str] | None:
    """Return the two stacked prefixes when a basename carries a prefix twice."""

    state, first = prefix_state(name, prefixes)
    if state != EXACT:
        return None
    second_state, second = prefix_state(name[len(first) :], prefixes)
    if second_state != EXACT:
        return None
    return first, second


def is_lowercase_forced(relpath: str, globs: Sequence[str]) -> bool:
    posix_path = PurePosixPath(relpath)
    return any(posix_path.full_match(glob) for glob in globs)


def suggest_name(
    relpath: str,
    name: str,
    state: str,
    matched: str,
    globs: Sequence[str],
) -> str | None:
    """Return the name this file should carry, or None when that is a judgement.

    Only two situations have one computable right answer: a directory that
    requires lowercase, and a prefix spelled in the wrong case. Which subsystem
    prefix a genuinely new file deserves is a human decision and gets no
    suggestion -- a confidently wrong rename is worse than none, because a
    reader acts on an exact name without re-deriving it, and the engine
    reports neither the old name nor the new one being wrong.

    The lowercase rule is tested first: where a directory forces lowercase it
    outranks the prefix's capitalization, so `Mnt_` there becomes `mnt_`, not
    `MnT_`.
    """

    if is_lowercase_forced(relpath, globs):
        lowered = name.lower()
        return lowered if lowered != name else None
    if state == NEAR_MISS and matched:
        corrected = matched + name[len(matched) :]
        return corrected if corrected != name else None
    return None


def resolve_names(files: Sequence[SourceFile], ctx: Context) -> list[str]:
    """Return each source's Git-recorded spelling, falling back to its own.

    A case-insensitive filesystem answers ``MnT_x.txt`` and ``mnt_x.txt`` with
    whichever one happens to be on disk, so the shipped spelling is taken from
    Git's index. Discovery still decides *which* files are in scope, so
    ``--staged`` and explicit path arguments keep their existing meaning.
    """

    tracked = tracked_names(ctx.root, include_untracked=not ctx.staged)
    if tracked is None:
        return [source.relpath for source in files]

    by_key: dict[str, list[str]] = {}
    for name in tracked:
        by_key.setdefault(name.lower(), []).append(name)

    resolved: list[str] = []
    for source in files:
        candidates = by_key.get(source.relpath.lower(), [])
        # Two tracked names differing only by case cannot be disambiguated from
        # one filesystem path; keep the discovered spelling rather than guess.
        resolved.append(candidates[0] if len(candidates) == 1 else source.relpath)
    return resolved


def _exception_findings(
    ctx: Context, checkable_paths: set[str]
) -> Iterator[Finding]:
    # Whether a file exists is a REPOSITORY question, not a scope question. Asking
    # it of the scoped set made the staleness half unfirable wherever the linter is
    # given an explicit path list -- which is exactly how CI invokes it, so the half
    # that catches a rotted exception could never fire there. Git answers for the
    # whole tree at no extra cost, and this widens nothing: it validates the shared
    # config's own list, never another author's files.
    tracked = tracked_names(ctx.root, include_untracked=not ctx.staged)
    known = (
        {path for path in tracked if is_checkable(path)}
        if tracked is not None
        else checkable_paths
    )
    # A root with no payload at all is a misconfigured root, not a tree whose
    # every exception has rotted. Reporting six confident staleness errors
    # because the linter was pointed one directory off is worse than silence.
    scoped_only = not known or (
        tracked is None and not (ctx.whole_tree and not ctx.staged)
    )

    for exception in ctx.config.naming.exceptions:
        stale_reasons: list[str] = []
        if not scoped_only and exception.path not in known:
            stale_reasons.append(
                "no such checked payload file exists in the mod"
            )
        if not exception.reason.strip():
            stale_reasons.append("the reason is empty")
        if not stale_reasons:
            continue
        finding = make_finding(
            ctx.config,
            exception.path,
            0,
            0,
            "EU5085",
            "naming exception is invalid ("
            + "; ".join(stale_reasons)
            + "); remove it or correct the path, and give a one-line reason "
            "naming the deliberate convention break it records.",
        )
        if finding is not None:
            yield finding


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    naming = ctx.config.naming
    names = [
        relpath for relpath in resolve_names(files, ctx) if is_checkable(relpath)
    ]
    yield from _exception_findings(ctx, set(names))

    if not naming.prefixes:
        # No owner prefix has been decided yet; EU5051 already reports that.
        return

    vanilla_paths = manifest_module.load(naming.manifest_path)
    yield from _manifest_drift(vanilla_paths, ctx)
    if vanilla_paths is None:
        finding = make_finding(
            ctx.config,
            "",
            0,
            0,
            "EU5086",
            "the committed vanilla path manifest at "
            f"{naming.manifest_path} is missing or unreadable, so the checks "
            "that need to know whether a base-game file exists at a mod path "
            "are skipped. Restore the file from Git or regenerate it with "
            "`make vanilla-manifest EU5_VERSION=<version>`.",
        )
        if finding is not None:
            yield finding

    excepted = {exception.path for exception in naming.exceptions}
    for relpath in names:
        if relpath in excepted:
            continue
        yield from _file_findings(relpath, ctx, vanilla_paths)


def _manifest_drift(
    vanilla_paths: frozenset[str] | None, ctx: Context
) -> Iterator[Finding]:
    """Report a committed manifest that no longer matches the installed game.

    The manifest is a snapshot, and its game-version header is a string whoever
    regenerated it typed in -- nothing verifies it. After a game patch the
    naming rules keep answering "does the base game ship this path?" from the
    old file list, silently and with no sign that anything is wrong.

    The comparison regenerates the manifest with the same collector
    `make vanilla-manifest` uses, because the committed file is deliberately
    narrower than the full install: five extensions, one content root. Comparing
    against the raw base index instead reports tens of thousands of phantom
    additions. CI has no install and is unaffected; this only speaks when a real
    one is present and genuinely disagrees.
    """

    if vanilla_paths is None:
        return
    try:
        live = frozenset(
            manifest_module.collect(ctx.config.game_root, ctx.config.mount_roots)
        )
    except manifest_module.ManifestError:
        # No usable install here. EU5900 already covers the checks that need one.
        return
    if live == vanilla_paths:
        return
    added = len(live - vanilla_paths)
    removed = len(vanilla_paths - live)
    finding = make_finding(
        ctx.config,
        "",
        0,
        0,
        "EU5087",
        f"the committed vanilla path manifest no longer matches the installed "
        f"game: {added} path(s) the install has that it lacks, {removed} it "
        f"lists that the install no longer has. The naming rules answer "
        f'"does the base game ship this path?" from the manifest, so they are '
        f"reasoning about a stale file list. Regenerate with "
        f"`make vanilla-manifest EU5_VERSION=<version>` and commit the diff.",
    )
    if finding is not None:
        yield finding


def _file_findings(
    relpath: str, ctx: Context, vanilla_paths: frozenset[str] | None
) -> Iterator[Finding]:
    naming = ctx.config.naming
    name = PurePosixPath(relpath).name
    state, matched = prefix_state(name, naming.prefixes)
    has_twin = vanilla_paths is not None and relpath in vanilla_paths

    if has_twin:
        # A whole-file override has to sit at the base path, so the filename is
        # the base game's and none of the prefix rules get a say about it. The
        # base game really does ship names that collide with plausible prefixes
        # (rgo_mesh_lists.txt against a configured RGO_), and judging those
        # would punish a correct override.
        if state == EXACT:
            finding = make_finding(
                ctx.config,
                relpath,
                0,
                0,
                "EU5080",
                "this filename is prefixed AND shadows a base-game path, which "
                "is the one combination that fails silently: the prefix marks "
                "the file as this mod's own while the path claims a whole-file "
                "override of the base file, and the engine reports neither. "
                "Drop the prefix if a real whole-file override is intended, or "
                "rename the file off the base path and edit the base content "
                f"with INJECT: or REPLACE:. If {matched!r} is simply a prefix "
                "the base game also uses, stop configuring it as one.",
            )
            if finding is not None:
                yield finding
        return

    if is_lowercase_forced(relpath, naming.lowercase_globs) and name != name.lower():
        target = suggest_name(relpath, name, state, matched, naming.lowercase_globs)
        finding = make_finding(
            ctx.config,
            relpath,
            0,
            0,
            "EU5082",
            "this directory requires an all-lowercase filename and this one "
            f"carries capitals ({name}); the base game keeps 3/3 files under "
            "modifier_type_definitions/ and 53/53 under cultures/ lowercase, "
            "and M&T has had to rename a capitalized name back down four "
            f"times. Rename it to {target!r}, prefix included.",
        )
        if finding is not None:
            yield finding

    if state == NEAR_MISS:
        if is_lowercase_forced(relpath, naming.lowercase_globs):
            # Prefix capitalization is not this rule's business in a directory that
            # forces lowercase: the directory rule outranks it, EU5082 above owns the
            # casing, and EU5083's advice ("correct the capitalization") would break
            # the file. Guarding the whole directory rather than only the
            # already-lowercase name keeps the two rules from proposing opposite
            # renames of one file. M&T renamed MnT_modifier_types.txt down to mnt_
            # twice, then wrote the reason into the file: "IMPORTANT, this file needs
            # to be named in all lowercase, otherwise it doesn't work at all!"
            # (their 3a436ae).
            return
        target = suggest_name(relpath, name, state, matched, naming.lowercase_globs)
        finding = make_finding(
            ctx.config,
            relpath,
            0,
            0,
            "EU5083",
            f"filename prefix differs from the configured {matched!r} only by "
            "case, so it claims no subsystem and sorts on its own. Prefix "
            "matching is exact and case-sensitive by design; rename it to "
            f"{target!r}.",
        )
        if finding is not None:
            yield finding
        return

    stacked = double_prefix(name, naming.prefixes)
    if stacked is not None:
        first, second = stacked
        finding = make_finding(
            ctx.config,
            relpath,
            0,
            0,
            "EU5084",
            f"filename stacks two configured prefixes ({first!r} then "
            f"{second!r}); one file has one owner. Drop whichever prefix is "
            "not the owning one unless the second is genuinely part of the "
            "content name, in which case record a [[naming_exception]].",
        )
        if finding is not None:
            yield finding

    if vanilla_paths is None:
        # Without the manifest there is no way to tell a forgotten prefix from
        # a deliberate whole-file override, so this row stays silent.
        return

    if state == NONE:
        finding = make_finding(
            ctx.config,
            relpath,
            0,
            0,
            "EU5081",
            "this filename carries no configured prefix and overrides no "
            "base-game path, so nothing marks who owns it and its load order "
            "is accidental. Add the ownership prefix, or record a "
            "[[naming_exception]] when the file really is an unprefixed "
            "mod original.",
        )
        if finding is not None:
            yield finding
