"""Generation and lookup for the committed vanilla-path manifest.

The naming check needs one fact the mod tree cannot supply: does the base game
ship a file at this repo-relative path? Asking a live install would make the
check unrunnable on a fresh clone, in CI, and on any machine without the game,
so the answer is committed instead.

The manifest is plain sorted text, not a compressed blob, for three reasons.
A game patch has to surface as a readable diff — that is the whole point of the
regeneration target, and Git reports a changed ``.gz`` as "binary files
differ". Git already zlib-compresses every blob, so a committed ``.gz`` would
save nothing in the object store while defeating delta compression between
regenerations. And a text file needs no decompression step on the lint path.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path, PurePosixPath
import os


PHASE_ROOTS: tuple[str, ...] = ("in_game", "main_menu", "loading_screen")
EXTENSIONS: frozenset[str] = frozenset({".txt", ".yml", ".gui", ".gfx", ".asset"})
# Only the `game` mount root is walked, not the `clausewitz` and `jomini` roots that
# `[game] mount_roots` also declares: those two serve 487 further overridable paths that
# this manifest therefore does not list, so a mod file placed at one of them is told it
# overrides no base-game path. No tracked file lands there today. Widening this means
# regenerating the manifest, not changing a check.
CONTENT_ROOT = "game"
# The engine overlays these into one namespace; the manifest must cover all of
# them, not only the largest. Mirrors [game] mount_roots.
DEFAULT_MOUNT_ROOTS: tuple[str, ...] = ("clausewitz", "jomini", "game")

DEFAULT_PATH: Path = Path(__file__).resolve().parent / "data" / "vanilla_paths.txt"


class ManifestError(RuntimeError):
    """The vanilla manifest could not be generated."""


def collect(
    game_root: Path, mount_roots: Sequence[str] = DEFAULT_MOUNT_ROOTS
) -> list[str]:
    """Return sorted repo-relative vanilla paths below every mounted root.

    All of ``mount_roots`` are walked, not just ``game``. They overlay into one
    namespace, so a path present in any of them is a path the base game ships,
    and asking only ``game`` left 487 of them invisible: a mod file placed at
    ``in_game/common/trigger_localization/00_logic_triggers.txt`` would have
    been told it overrides no base-game file, which is the exact wrong advice.

    Only the three mounted phase roots are walked, and only the extensions the
    naming check can reason about are recorded. Paths are emitted with forward
    slashes on every platform.
    """

    def _is_dir(path: Path) -> bool:
        """``is_dir`` that reports failure instead of answering ``False``.

        A stat that fails is not the same answer as "not a directory", but
        ``Path.is_dir`` collapses the two. Left uncaught that dropped an entire
        phase root from the walk, and because the collector is also what EU5087
        compares the committed manifest against, the result was a drift report
        naming paths that had not moved.
        """

        try:
            return path.is_dir()
        except OSError as error:
            raise ManifestError(f"cannot stat {path}: {error}") from error

    present = [root for root in mount_roots if _is_dir(game_root / root)]
    # Official DLC are further layers over the same namespace, each with its own
    # phase roots, and a mod overriding DLC content sits at the DLC's own
    # phase-relative path. Omitting them made 13 gfx/map/city_data files look
    # main_menu-only when D008, D015 and D017 all ship them under in_game.
    dlc_root = game_root / CONTENT_ROOT / "dlc"
    # Enumerating the DLC directory can fail the same ways walking it can -- an
    # unreadable mode, a broken mount -- and those raise here rather than through
    # os.walk's onerror hook. Uncaught, a PermissionError on this one directory
    # crashed the whole run instead of degrading to the unavailable-index notice
    # the caller already handles. A partial DLC list is not an acceptable
    # fallback: it is what made 13 city_data files look main_menu-only, so an
    # unreadable layer has to be an error rather than a silent omission.
    try:
        if _is_dir(dlc_root):
            present.extend(
                f"{CONTENT_ROOT}/dlc/{pack.name}"
                for pack in sorted(dlc_root.iterdir())
                if pack.is_dir()
            )
    except OSError as error:
        raise ManifestError(f"cannot list {dlc_root}: {error}") from error
    if not present:
        raise ManifestError(
            f"no base-game content root under {game_root}; set EU5_GAME, pass "
            "--game-root, or correct [game].root to a directory containing "
            f"{'/'.join(mount_roots)}/"
        )

    walk_failed: list[str] = []

    def on_walk_error(error: OSError) -> None:
        walk_failed.append(str(error))

    paths: set[str] = set()
    for content_root_name in present:
        content_root = game_root / content_root_name
        for phase_root_name in PHASE_ROOTS:
            phase_root = content_root / phase_root_name
            if not _is_dir(phase_root):
                continue
            for current, directories, filenames in os.walk(
                phase_root, topdown=True, followlinks=False, onerror=on_walk_error
            ):
                directories.sort()
                for filename in filenames:
                    if PurePosixPath(filename).suffix.lower() not in EXTENSIONS:
                        continue
                    relative = os.path.relpath(
                        Path(current) / filename, content_root
                    )
                    paths.add(Path(relative).as_posix())

    if walk_failed:
        raise ManifestError(f"cannot walk {game_root}: {walk_failed[0]}")
    if not paths:
        raise ManifestError(
            f"walked {game_root} and found no {'/'.join(sorted(EXTENSIONS))} "
            "files below its phase roots; the install looks empty or partial"
        )
    return sorted(paths)


def render(paths: Sequence[str], game_version: str, generated: date) -> str:
    """Return the full manifest text, header included."""

    extensions = " ".join(sorted(EXTENSIONS))
    header = (
        "# eu5lint vanilla path manifest\n"
        f"# game-version: {game_version}\n"
        f"# generated: {generated.isoformat()}\n"
        f"# source: {{{','.join(DEFAULT_MOUNT_ROOTS)}}}/"
        f"{{{','.join(PHASE_ROOTS)}}}, plus every {CONTENT_ROOT}/dlc/* layer\n"
        f"# extensions: {extensions}\n"
        f"# paths: {len(paths)}\n"
        "#\n"
        "# Repo-relative, forward-slash, sorted, one per line. The game install\n"
        "# carries no machine-readable version, so game-version above is asserted\n"
        "# by whoever regenerated this file. Regenerate with\n"
        "# `make vanilla-manifest EU5_VERSION=<version>`: a game patch then shows\n"
        "# up as a diff here instead of drifting silently.\n"
    )
    return header + "".join(f"{path}\n" for path in paths)


def load(path: Path) -> frozenset[str] | None:
    """Return the manifest's paths, or ``None`` when it cannot be read."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return frozenset(
        line
        for raw_line in text.splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    )
