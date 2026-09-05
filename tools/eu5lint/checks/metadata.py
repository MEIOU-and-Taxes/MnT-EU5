"""Validate the mod descriptor in .metadata/metadata.json."""

from collections.abc import Iterator, Sequence
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess

from findings import Finding, make_finding
from sources import Context, SourceFile


_METADATA_PATH = ".metadata/metadata.json"
_REQUIRED_KEYS = ("name", "id", "version", "game_id", "supported_game_version")
_BOM = b"\xef\xbb\xbf"
_SUPPORTED_VERSION = re.compile(r"^\d+(\.\d+)*(\.\*)?$")


def _metadata_finding(
    ctx: Context,
    line: int,
    code: str,
    message: str,
) -> Finding | None:
    return make_finding(ctx.config, _METADATA_PATH, line, 0, code, message)


def _path_is_safe(picture: object) -> bool:
    if not isinstance(picture, str) or not picture:
        return False
    if "\x00" in picture:
        return False
    posix_picture = PurePosixPath(picture)
    windows_picture = PureWindowsPath(picture)
    if picture.startswith("/") or posix_picture.is_absolute():
        return False
    if windows_picture.is_absolute() or windows_picture.drive:
        return False
    if ".." in posix_picture.parts or ".." in windows_picture.parts:
        return False
    return True


def _worktree_picture_exists(root: Path, picture: str) -> bool:
    metadata_dir = (root / ".metadata").resolve()
    try:
        candidate = (metadata_dir / Path(*PurePosixPath(picture).parts)).resolve()
        candidate.relative_to(metadata_dir)
    except (OSError, ValueError):
        return False
    return candidate.is_file()


def _staged_picture_exists(root: Path, files: Sequence[SourceFile], picture: str) -> bool:
    picture_path = f".metadata/{PurePosixPath(picture).as_posix()}"
    if any(source.relpath == picture_path for source in files):
        return True
    try:
        result = subprocess.run(
            ["git", "cat-file", "-t", f":{picture_path}"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return result.stdout.strip() == b"blob"


def _picture_exists(
    ctx: Context, files: Sequence[SourceFile], picture: object
) -> bool:
    if not _path_is_safe(picture):
        return False
    if not isinstance(picture, str):
        return False
    if ctx.staged:
        return _staged_picture_exists(ctx.root, files, picture)
    return _worktree_picture_exists(ctx.root, picture)


def run(files: Sequence[SourceFile], ctx: Context) -> Iterator[Finding]:
    metadata_files = [source for source in files if source.relpath == _METADATA_PATH]
    if not metadata_files:
        if ctx.whole_tree and not ctx.staged:
            finding = _metadata_finding(
                ctx,
                0,
                "EU5070",
                "required metadata file .metadata/metadata.json is missing; "
                "create that file with the required descriptor fields.",
            )
            if finding is not None:
                yield finding
        return

    source = metadata_files[0]
    if not source.data.startswith(_BOM):
        finding = _metadata_finding(
            ctx,
            0,
            "EU5072",
            "metadata.json must carry a UTF-8 BOM; add bytes EF BB BF at the "
            "start without changing the JSON content.",
        )
        if finding is not None:
            yield finding

    try:
        decoded = source.data.decode("utf-8-sig")
        parsed: object = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        finding = _metadata_finding(
            ctx,
            0,
            "EU5073",
            "metadata.json is not valid UTF-8 JSON; repair its JSON syntax and "
            "preserve the required UTF-8 BOM.",
        )
        if finding is not None:
            yield finding
        return

    if not isinstance(parsed, dict):
        finding = _metadata_finding(
            ctx,
            0,
            "EU5073",
            "metadata.json must contain a JSON object at the top level; replace "
            "the top-level value with the descriptor object.",
        )
        if finding is not None:
            yield finding
        return

    for key in _REQUIRED_KEYS:
        value = parsed.get(key)
        if not isinstance(value, str) or not value.strip():
            finding = _metadata_finding(
                ctx,
                0,
                "EU5070",
                f"required metadata key '{key}' is missing or empty; add a "
                "non-empty string value for it.",
            )
            if finding is not None:
                yield finding

    game_id = parsed.get("game_id")
    if isinstance(game_id, str) and game_id.strip() and game_id != "eu5":
        finding = _metadata_finding(
            ctx,
            0,
            "EU5070",
            "metadata key 'game_id' must equal 'eu5'; change its value to 'eu5'.",
        )
        if finding is not None:
            yield finding

    supported_version = parsed.get("supported_game_version")
    if (
        isinstance(supported_version, str)
        and supported_version.strip()
        and _SUPPORTED_VERSION.fullmatch(supported_version) is None
    ):
        finding = _metadata_finding(
            ctx,
            0,
            "EU5070",
            "metadata key 'supported_game_version' has an invalid value; use "
            "the numeric form such as '1.3.*'.",
        )
        if finding is not None:
            yield finding

    if "picture" in parsed:
        picture = parsed.get("picture")
        if not _picture_exists(ctx, files, picture):
            finding = _metadata_finding(
                ctx,
                0,
                "EU5071",
                "metadata key 'picture' must be a relative existing file under "
                ".metadata/ with no '..' segment or leading '/'; place the image "
                "there or correct the path.",
            )
            if finding is not None:
                yield finding
