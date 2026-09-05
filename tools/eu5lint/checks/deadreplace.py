"""Check replacement localization keys against the mounted base index."""

from collections.abc import Iterator, Sequence
from pathlib import PurePosixPath
import re

from baseindex import require_base_localization_index
from checks.braces import strip_comments
from findings import Finding, make_finding
from sources import Context, SourceError, SourceFile, discover_worktree, is_payload_path


_REPLACE_GLOB = "**/localization/*/replace/**/*.yml"
_ENTRY = re.compile(r'^\s*(?P<key>[^\s:#]+):\d*\s+"')
# Identifier-shaped tokens, used to ask whether anything else in the mod names a key.
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# Only text carries references; decoding binary payload invents them.
_TEXT_SUFFIXES = frozenset({".txt", ".yml", ".gui", ".gfx", ".asset", ".info", ".csv"})
_LOCALIZATION_FILE = re.compile(r"_l_[A-Za-z0-9_-]+\.yml$")


# Suffixes the engine appends by convention, so the key is never named anywhere:
# the base game's advances_l_english.yml pairs 591 of 591 `*_advance` keys with a
# `*_advance_desc`, and no `_desc` key is referenced from script anywhere in the
# install -- only from the other languages' translations of the same file. That
# census is install-wide only for THAT file: across every `*_l_english.yml` the
# pairing is 609 of 618, with 9 `enable_*_advance` keys carrying no description.
# Add a suffix here only with that kind of census behind it; a wrong entry
# silences a real finding. Count with this module's own _ENTRY regex, not a
# `[a-z_]+` grep -- that pattern drops digit-bearing keys such as
# fort_limit_1_advance and undercounts by 7.
_CONVENTION_SUFFIXES = ("_desc",)


def _is_read(key: str, references: dict[str, set[str]]) -> bool:
    """Does anything name this key, or the stem the engine appends a suffix to?

    The index holds references only, never definitions, so a hit is a read no
    matter which file it came from -- including another entry in the key's own
    file, where ``$other_key$`` interpolation is the normal way strings compose.
    """

    if key in references:
        return True
    for suffix in _CONVENTION_SUFFIXES:
        if key.endswith(suffix) and key[: -len(suffix)] in references:
            return True
    return False


def _reference_index(files: Sequence[SourceFile]) -> dict[str, set[str]]:
    """Map identifier-shaped tokens that READ a key to the files reading it.

    A key under replace/ that the base game does not define is not automatically
    a mistake: the loader creates a missing key rather than discarding it, so the
    mod may simply be defining its own string in the wrong folder. The two cases
    are told apart by whether anything reads the key -- which makes what counts
    as a read the whole rule, and three things do not count:

    * A comment. ``# TODO: remove not_in_base`` is a note, not a consumer, so
      comments are stripped with the same quote-aware helper assets.py uses.
    * A definition in another language. ``not_in_base`` defined in both an
      English and a French file is two unread definitions, not one read; without
      this, a dead key silences the finding for every language at once. Only the
      value side of a localization entry is indexed, so ``$other_key$`` and
      ``[Scope.Custom('other_key')]`` still count -- those are real reads.
    * Bytes that are not text. Decoding a .dds and tokenising the result invents
      references from image data.
    """

    index: dict[str, set[str]] = {}
    for source in files:
        if not is_payload_path(source.relpath):
            continue
        if PurePosixPath(source.relpath).suffix.lower() not in _TEXT_SUFFIXES:
            continue
        text = strip_comments(source.data).decode("utf-8-sig", errors="replace")
        if _LOCALIZATION_FILE.search(source.relpath):
            text = "\n".join(_ENTRY.sub("", line) for line in text.splitlines())
        for token in set(_TOKEN.findall(text)):
            index.setdefault(token, set()).add(source.relpath)
    return index


def _language(source: SourceFile) -> str | None:
    parts = PurePosixPath(source.relpath).parts
    try:
        localization_index = parts.index("localization")
    except ValueError:
        return None
    if localization_index + 1 >= len(parts):
        return None
    return parts[localization_index + 1]


def _is_replace_localization(source: SourceFile) -> bool:
    return is_payload_path(source.relpath) and PurePosixPath(
        source.relpath
    ).full_match(_REPLACE_GLOB)


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    base_keys, availability_finding = require_base_localization_index(ctx)
    if availability_finding is not None:
        yield availability_finding
    if base_keys is None:
        return

    # Answering "does anything read this key" needs the whole payload, and the
    # subset a run was handed cannot answer it. Earlier this left the question
    # open in the message and still said "remove it" -- advice to delete live
    # content on evidence the check itself called unknown. So read the whole
    # worktree for references however the run was scoped, the way eventids.py
    # asks Git rather than trusting its own file list. The worktree is a superset
    # of a staged run's corpus, which errs toward finding a reference and
    # therefore toward silence: the safe direction for a rule whose only advice
    # is deletion.
    if ctx.whole_tree and not ctx.staged:
        corpus: Sequence[SourceFile] | None = files
    else:
        try:
            corpus = discover_worktree(ctx.root)
        except (SourceError, OSError):
            corpus = None
    if corpus is None:
        # No corpus, no answer, no finding. A rule that cannot check its own
        # premise reports nothing rather than guessing.
        return
    references = _reference_index(corpus)

    for source in files:
        if not _is_replace_localization(source):
            continue
        language = _language(source)
        if language is None:
            continue
        known_keys = base_keys.get(language, frozenset())
        for line_number, line in enumerate(
            source.data.decode("utf-8-sig", errors="replace").splitlines(),
            start=1,
        ):
            match = _ENTRY.match(line)
            if match is None:
                continue
            key = match.group("key")
            if key in known_keys:
                continue
            if _is_read(key, references):
                # The mod defines and reads this string itself. It overrides
                # nothing, but it is live content and the loader creates it,
                # so there is no defect here -- at most it sits in a folder
                # whose name suggests an override. Not worth a finding.
                continue
            finding = make_finding(
                ctx.config,
                source.relpath,
                line_number,
                0,
                "EU5100",
                f"replacement localization key {key!r} for language "
                f"{language!r} does not exist in the base localization index, "
                "and nothing else in this mod reads it either, so it overrides nothing "
                "and no text uses it. A missing key here is created rather than "
                "discarded, so this is dead weight rather than a broken "
                "override: remove it, correct its spelling, or point it at the "
                "key it was meant to replace. This report is advisory.",
            )
            if finding is not None:
                yield finding
