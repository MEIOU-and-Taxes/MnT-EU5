"""Build the mounted base-game path index on demand."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import re
from typing import TYPE_CHECKING

from findings import Finding, make_finding

if TYPE_CHECKING:
    from sources import Context


@dataclass
class BaseIndexCache:
    """Per-run lazy state shared by checks that need the base index."""

    built: bool = False
    paths: frozenset[str] | None = None
    asset_built: bool = False
    asset_paths: frozenset[str] | None = None
    localization_built: bool = False
    localization_keys: dict[str, frozenset[str]] | None = None
    warning_emitted: bool = False


_LOCALIZATION_FILENAME = re.compile(
    r"_l_(?P<language>[A-Za-z0-9_-]+)\.yml$"
)
_LOCALIZATION_HEADER = re.compile(
    r"^\s*l_(?P<language>[A-Za-z0-9_-]+):\s*(?:#.*)?$"
)
_LOCALIZATION_ENTRY = re.compile(
    r'^\s*(?P<key>[^\s:#]+):\d*\s+"'
)
_PHASE_ROOTS = ("in_game", "main_menu", "loading_screen")


def _is_game_install(game_root: Path, mount_roots: Sequence[str]) -> bool:
    """Is this directory actually a base-game install we can index?

    Existence is not enough. A blank or wrong ``[game].root`` still resolves to a
    real directory -- a blank one resolves against the config file's own folder,
    which is the repository -- and walking it finds none of the mount roots. The
    builders would then return an EMPTY index rather than ``None``, and every
    check that asks "does the base game define this?" answers no for everything:
    measured at 814 warnings against M&T instead of 28, with EU5900 never
    emitted because nothing looked unavailable. Requiring at least one mount root
    distinguishes "not an install" from "an install with nothing in it".
    """

    return game_root.is_dir() and any(
        (game_root / mount_root).is_dir() for mount_root in mount_roots
    )


def build_index(game_root: Path, mount_roots: Sequence[str]) -> frozenset[str] | None:
    """Return mounted base paths, or ``None`` when the root cannot be indexed."""

    if not _is_game_install(game_root, mount_roots):
        return None

    paths: set[str] = set()
    walk_failed = False

    def on_walk_error(_: OSError) -> None:
        nonlocal walk_failed
        walk_failed = True

    for mount_root in mount_roots:
        mount_path = game_root / mount_root
        if not mount_path.is_dir():
            continue
        for current, directories, filenames in os.walk(
            mount_path,
            topdown=True,
            followlinks=False,
            onerror=on_walk_error,
        ):
            directories.sort()
            for filename in filenames:
                file_path = Path(current) / filename
                relative = os.path.relpath(file_path, mount_path)
                paths.add(PurePosixPath(relative).as_posix())

    if walk_failed:
        return None
    return frozenset(paths)


def _add_phase_relative_paths(layer_root: Path, paths: set[str]) -> bool:
    """Add files below a layer's direct phase roots and report walk failures."""

    walk_failed = False

    def on_walk_error(_: OSError) -> None:
        nonlocal walk_failed
        walk_failed = True

    for phase_root_name in _PHASE_ROOTS:
        phase_root = layer_root / phase_root_name
        if not phase_root.is_dir():
            continue
        for current, directories, filenames in os.walk(
            phase_root,
            topdown=True,
            followlinks=False,
            onerror=on_walk_error,
        ):
            directories.sort()
            for filename in filenames:
                file_path = Path(current) / filename
                relative = os.path.relpath(file_path, phase_root)
                paths.add(PurePosixPath(relative).as_posix())

    return not walk_failed


def _dlc_layers(game_root: Path) -> list[Path] | None:
    """Return the immediate DLC layer directories, or ``None`` on a walk error."""

    dlc_root = game_root / "game" / "dlc"
    if not dlc_root.is_dir():
        return []
    try:
        return sorted(
            (child for child in dlc_root.iterdir() if child.is_dir()),
            key=lambda child: child.name,
        )
    except OSError:
        return None


def build_asset_index(
    game_root: Path,
    mount_roots: Sequence[str],
    mod_root: Path,
) -> frozenset[str] | None:
    """Return phase-relative paths from every base layer and the mod."""

    if not _is_game_install(game_root, mount_roots):
        return None

    paths: set[str] = set()
    for mount_root in mount_roots:
        if not _add_phase_relative_paths(game_root / mount_root, paths):
            return None

    dlc_layers = _dlc_layers(game_root)
    if dlc_layers is None:
        return None
    for dlc_layer in dlc_layers:
        if not _add_phase_relative_paths(dlc_layer, paths):
            return None

    if not _add_phase_relative_paths(mod_root, paths):
        return None
    return frozenset(paths)


def _localization_path(relative: str) -> tuple[str | None, bool]:
    parts = PurePosixPath(relative).parts
    try:
        localization_index = parts.index("localization")
    except ValueError:
        return None, False
    if localization_index + 1 >= len(parts):
        return None, False

    filename_match = _LOCALIZATION_FILENAME.fullmatch(parts[-1])
    if filename_match is not None:
        return filename_match.group("language"), True
    return parts[localization_index + 1], False


def _collect_localization_keys(
    text: str,
    default_language: str | None,
    use_headers: bool,
    keys_by_language: dict[str, set[str]],
) -> None:
    language = default_language
    for line in text.splitlines():
        header_match = _LOCALIZATION_HEADER.fullmatch(line)
        if use_headers and header_match is not None:
            language = header_match.group("language")
            keys_by_language.setdefault(language, set())
            continue
        if language is None:
            continue
        entry_match = _LOCALIZATION_ENTRY.match(line)
        if entry_match is not None:
            keys_by_language.setdefault(language, set()).add(
                entry_match.group("key")
            )


def build_localization_index(
    game_root: Path, mount_roots: Sequence[str]
) -> dict[str, frozenset[str]] | None:
    """Return mounted base localization keys grouped by language."""

    if not _is_game_install(game_root, mount_roots):
        return None

    keys_by_language: dict[str, set[str]] = {}
    walk_failed = False

    def on_walk_error(_: OSError) -> None:
        nonlocal walk_failed
        walk_failed = True

    for mount_root in mount_roots:
        mount_path = game_root / mount_root
        if not mount_path.is_dir():
            continue
        for current, directories, filenames in os.walk(
            mount_path,
            topdown=True,
            followlinks=False,
            onerror=on_walk_error,
        ):
            directories.sort()
            for filename in sorted(filenames):
                if not filename.lower().endswith(".yml"):
                    continue
                file_path = Path(current) / filename
                relative = os.path.relpath(file_path, mount_path)
                language, from_filename = _localization_path(relative)
                if language is None:
                    continue
                if "localization" not in PurePosixPath(relative).parts:
                    continue
                try:
                    text = file_path.read_bytes().decode(
                        "utf-8-sig", errors="replace"
                    )
                except OSError:
                    walk_failed = True
                    continue
                _collect_localization_keys(
                    text,
                    language,
                    not from_filename,
                    keys_by_language,
                )

    if walk_failed:
        return None
    return {
        language: frozenset(keys)
        for language, keys in keys_by_language.items()
    }


def get_base_index(ctx: "Context") -> frozenset[str] | None:
    """Build and retain the base index at most once for this lint run."""

    if not ctx.base_index.built:
        ctx.base_index.built = True
        ctx.base_index.paths = build_index(
            ctx.config.game_root,
            ctx.config.mount_roots,
        )
    return ctx.base_index.paths


def get_base_localization_index(
    ctx: "Context",
) -> dict[str, frozenset[str]] | None:
    """Build and retain base localization keys at most once per lint run."""

    if not ctx.base_index.built:
        get_base_index(ctx)
    if ctx.base_index.paths is None:
        return None
    if not ctx.base_index.localization_built:
        ctx.base_index.localization_built = True
        ctx.base_index.localization_keys = build_localization_index(
            ctx.config.game_root,
            ctx.config.mount_roots,
        )
    return ctx.base_index.localization_keys


def get_asset_index(ctx: "Context") -> frozenset[str] | None:
    """Build and retain the phase-relative asset index at most once per run."""

    if not ctx.base_index.built:
        get_base_index(ctx)
    if ctx.base_index.paths is None:
        return None
    if not ctx.base_index.asset_built:
        ctx.base_index.asset_built = True
        ctx.base_index.asset_paths = build_asset_index(
            ctx.config.game_root,
            ctx.config.mount_roots,
            ctx.root,
        )
    return ctx.base_index.asset_paths


def _unavailable_finding(ctx: "Context") -> Finding | None:
    return make_finding(
        ctx.config,
        "",
        0,
        0,
        "EU5900",
        "base-game index is unavailable because the configured game root does not "
        "exist or cannot be walked; checks 4, 9 and 10 are skipped. Set EU5_GAME, "
        "pass --game-root, or correct [game].root, then rerun the linter.",
    )


def require_base_index(
    ctx: "Context",
) -> tuple[frozenset[str] | None, Finding | None]:
    """Return the index and one advisory when the configured base is unavailable."""

    index = get_base_index(ctx)
    if index is not None or ctx.base_index.warning_emitted:
        return index, None

    ctx.base_index.warning_emitted = True
    finding = _unavailable_finding(ctx)
    return None, finding


def require_base_localization_index(
    ctx: "Context",
) -> tuple[dict[str, frozenset[str]] | None, Finding | None]:
    """Return base localization keys and one advisory when unavailable."""

    base_paths, availability_finding = require_base_index(ctx)
    if availability_finding is not None or base_paths is None:
        return None, availability_finding

    localization_keys = get_base_localization_index(ctx)
    if localization_keys is not None or ctx.base_index.warning_emitted:
        return localization_keys, None

    ctx.base_index.warning_emitted = True
    return None, _unavailable_finding(ctx)


def require_asset_index(
    ctx: "Context",
) -> tuple[frozenset[str] | None, Finding | None]:
    """Return phase-relative asset paths and one advisory when unavailable."""

    base_paths, availability_finding = require_base_index(ctx)
    if availability_finding is not None or base_paths is None:
        return None, availability_finding

    asset_paths = get_asset_index(ctx)
    if asset_paths is not None or ctx.base_index.warning_emitted:
        return asset_paths, None

    ctx.base_index.warning_emitted = True
    return None, _unavailable_finding(ctx)
