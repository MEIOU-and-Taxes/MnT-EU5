"""Payload source discovery for worktrees and staged Git blobs."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import os
import subprocess

from config import Config
from baseindex import BaseIndexCache


_PAYLOAD_ROOTS = frozenset({"in_game", "main_menu", "loading_screen", ".metadata"})
_TEXT_EXTENSIONS = frozenset(
    {".txt", ".yml", ".yaml", ".gui", ".info", ".csv", ".asset", ".json"}
)


class SourceError(RuntimeError):
    """A source file set could not be discovered."""


@dataclass(frozen=True)
class SourceFile:
    relpath: str
    data: bytes
    origin: str


@dataclass(frozen=True)
class Context:
    config: Config
    root: Path
    tier: int
    staged: bool = False
    whole_tree: bool = True
    base_index: BaseIndexCache = field(default_factory=BaseIndexCache)


def is_payload_path(relpath: str) -> bool:
    parts = PurePosixPath(relpath).parts
    return bool(parts) and parts[0] in _PAYLOAD_ROOTS


def is_text_path(relpath: str) -> bool:
    return PurePosixPath(relpath).suffix.lower() in _TEXT_EXTENSIONS


def _is_ignored(relpath: str) -> bool:
    return PurePosixPath(relpath).name == ".gitkeep"


def _relative_path(root: Path, file_path: Path) -> str:
    try:
        return file_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = os.path.relpath(file_path, root)
        return relative.replace(os.sep, "/")


def _walk_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    result: list[Path] = []

    def fail(error: OSError) -> None:
        # os.walk discards errors unless given this hook, so an unreadable
        # subtree simply disappears from the result and a caller cannot tell
        # that from an empty directory. deadreplace.py builds its "nothing in
        # this mod reads the key" evidence from this list, and a silently short
        # list there becomes confident advice to delete live content. Raising
        # makes the gap visible to callers that already handle SourceError.
        raise SourceError(f"cannot walk {directory}: {error}") from error

    for current, directories, filenames in os.walk(
        directory, topdown=True, followlinks=False, onerror=fail
    ):
        directories[:] = sorted(
            name for name in directories if name not in {".git", "__pycache__"}
        )
        for filename in sorted(filenames):
            result.append(Path(current) / filename)
    return result


def _read_worktree_file(root: Path, file_path: Path) -> SourceFile:
    relpath = _relative_path(root, file_path)
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise SourceError(f"cannot read {relpath}: {exc}") from exc
    return SourceFile(relpath=relpath, data=data, origin="worktree")


def _explicit_files(root: Path, paths: Sequence[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for argument in paths:
        selected = Path(argument).expanduser()
        if not selected.is_absolute():
            selected = root / selected
        if not selected.exists():
            raise SourceError(f"path does not exist: {argument}")
        candidates = _walk_files(selected) if selected.is_dir() else [selected]
        for candidate in candidates:
            relpath = _relative_path(root, candidate)
            if _is_ignored(relpath) or relpath in seen:
                continue
            seen.add(relpath)
            result.append(candidate)
    return sorted(result, key=lambda item: _relative_path(root, item))


def discover_worktree(root: Path, paths: Sequence[str] = ()) -> list[SourceFile]:
    try:
        root_path = root.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SourceError(f"invalid mod root {root!s}: {exc}") from exc
    if not root_path.is_dir():
        raise SourceError(f"mod root is not a directory: {root_path}")

    if paths:
        file_paths = _explicit_files(root_path, paths)
    else:
        file_paths = []
        for directory_name in sorted(_PAYLOAD_ROOTS):
            file_paths.extend(_walk_files(root_path / directory_name))

    sources = [
        _read_worktree_file(root_path, file_path)
        for file_path in file_paths
        if not _is_ignored(_relative_path(root_path, file_path))
    ]
    return sorted(sources, key=lambda source: source.relpath)


def _staged_names(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRT"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceError(f"cannot list staged files: {exc}") from exc

    names: list[str] = []
    for raw_name in result.stdout.split(b"\0"):
        if not raw_name:
            continue
        names.append(os.fsdecode(raw_name).replace(os.sep, "/"))
    return names


def _staged_file(root: Path, relpath: str) -> SourceFile | None:
    try:
        result = subprocess.run(
            ["git", "show", f":{relpath}"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    try:
        kind = subprocess.run(
            ["git", "cat-file", "-t", f":{relpath}"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    if kind != b"blob":
        return None
    return SourceFile(relpath=relpath, data=result.stdout, origin="staged")


def discover_staged(root: Path) -> list[SourceFile]:
    try:
        root_path = root.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SourceError(f"invalid mod root {root!s}: {exc}") from exc
    if not root_path.is_dir():
        raise SourceError(f"mod root is not a directory: {root_path}")

    sources: list[SourceFile] = []
    for relpath in _staged_names(root_path):
        if _is_ignored(relpath) or not is_payload_path(relpath):
            continue
        source = _staged_file(root_path, relpath)
        if source is not None:
            sources.append(source)
    return sorted(sources, key=lambda source: source.relpath)


def tracked_names(root: Path, include_untracked: bool = True) -> frozenset[str] | None:
    """Return Git's case-exact, forward-slash names under ``root``.

    Git is the only portable source of a filename's real spelling: the working
    tree answers with backslashes on Windows and case-folds on Windows and
    macOS, and case is exactly what the naming rules turn on. ``None`` means
    Git could not answer — no repository, no ``git`` on PATH — and the caller
    must fall back to the discovered paths.
    """

    command = ["git", "ls-files", "-z", "--cached"]
    if include_untracked:
        command.extend(["--others", "--exclude-standard"])
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    names = {
        os.fsdecode(raw_name)
        for raw_name in result.stdout.split(b"\0")
        if raw_name
    }
    return frozenset(names) if names else None


def discover(
    root: Path, paths: Sequence[str] = (), staged: bool = False
) -> list[SourceFile]:
    if staged:
        return discover_staged(root)
    return discover_worktree(root, paths)
