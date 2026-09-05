"""Configuration loading and BOM-policy lookup for eu5lint."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import tomllib

import manifest as manifest_module


_DEFAULT_GAME_ROOT = "~/.steam/steam/steamapps/common/Europa Universalis V"
_VALID_BOM_POLICIES = frozenset(
    {"required", "forbidden", "warn_required", "warn_only", "ignore"}
)
_VALID_SEVERITIES = frozenset({"error", "warn", "off"})
# Directories whose filenames the base game keeps entirely lowercase: 3/3 files
# under modifier_type_definitions/ and 53/53 under cultures/ in EU5 1.3.11.
_DEFAULT_LOWERCASE_GLOBS = (
    "**/modifier_type_definitions/**",
    "**/cultures/**",
)


class ConfigError(ValueError):
    """The linter configuration cannot be used safely."""


@dataclass(frozen=True)
class BomRule:
    glob: str
    policy: str


@dataclass(frozen=True)
class OverwriteRule:
    path: str
    reason: str


@dataclass(frozen=True)
class PrefixExceptionRule:
    path: str
    reason: str


@dataclass(frozen=True)
class NamingExceptionRule:
    path: str
    reason: str


@dataclass(frozen=True)
class NamingConfig:
    """Naming-convention policy: the prefixes, the forced-lowercase directories,
    the vanilla manifest to compare against, and the justified exceptions."""

    prefixes: tuple[str, ...]
    lowercase_globs: tuple[str, ...]
    manifest_path: Path
    exceptions: tuple[NamingExceptionRule, ...]


@dataclass(frozen=True)
class Config:
    path: Path
    prefix: str
    game_root: Path
    mount_roots: tuple[str, ...]
    bom_default: str
    bom_rules: tuple[BomRule, ...]
    overwrites: tuple[OverwriteRule, ...]
    prefix_exceptions: tuple[PrefixExceptionRule, ...]
    naming: NamingConfig
    severity: dict[str, str]


def _table(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a TOML table")
    table: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"{name} contains a non-string key")
        table[key] = item
    return table


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a string")
    return value


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{name} must be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{name}[{index}]"))
    return tuple(result)


def _table_list(value: object, name: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ConfigError(f"{name} must be an array of tables")
    result: list[dict[str, object]] = []
    for index, item in enumerate(value):
        result.append(_table(item, f"{name}[{index}]"))
    return result


def _check_glob(glob: str, name: str) -> str:
    try:
        PurePosixPath("eu5lint-glob-probe").full_match(glob)
    except ValueError as exc:
        raise ConfigError(f"{name} is invalid: {exc}") from exc
    return glob


def _resolve_path(value: str, base: Path) -> Path:
    try:
        selected = Path(value).expanduser()
        if not selected.is_absolute():
            selected = base / selected
        return selected.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ConfigError(f"invalid path {value!r}: {exc}") from exc


def load_config(
    path: Path,
    game_root_override: Path | None = None,
    manifest_override: Path | None = None,
) -> Config:
    """Read and validate one eu5lint.toml file."""

    try:
        config_path = path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ConfigError(f"invalid configuration path {path!s}: {exc}") from exc
    try:
        with config_path.open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {config_path}: {exc}") from exc

    mod = _table(raw.get("mod"), "[mod]")
    prefix = _string(mod.get("prefix"), "mod.prefix")
    if "extra_prefixes" in mod:
        raise ConfigError(
            "mod.extra_prefixes is unsupported; configure exactly one value in "
            "mod.prefix"
        )

    game = _table(raw.get("game", {}), "[game]")
    configured_game_root = _string(
        game.get("root", _DEFAULT_GAME_ROOT), "game.root"
    )
    environment_game_root = os.environ.get("EU5_GAME")
    if environment_game_root:
        configured_game_root = environment_game_root
    if game_root_override is not None:
        configured_game_root = str(game_root_override)
    game_root = _resolve_path(configured_game_root, config_path.parent)
    mount_roots = _string_list(
        game.get("mount_roots", ["clausewitz", "jomini", "game"]),
        "game.mount_roots",
    )

    bom = _table(raw.get("bom"), "[bom]")
    bom_default = _string(bom.get("default"), "bom.default")
    if bom_default not in _VALID_BOM_POLICIES:
        raise ConfigError(f"bom.default has unsupported policy {bom_default!r}")
    bom_rules: list[BomRule] = []
    for index, rule_table in enumerate(_table_list(bom.get("rules", []), "bom.rules")):
        glob = _string(rule_table.get("glob"), f"bom.rules[{index}].glob")
        policy = _string(rule_table.get("policy"), f"bom.rules[{index}].policy")
        if policy not in _VALID_BOM_POLICIES:
            raise ConfigError(
                f"bom.rules[{index}].policy has unsupported policy {policy!r}"
            )
        _check_glob(glob, f"bom.rules[{index}].glob")
        bom_rules.append(BomRule(glob=glob, policy=policy))

    overwrites: list[OverwriteRule] = []
    for index, overwrite_table in enumerate(
        _table_list(raw.get("overwrite", []), "overwrite")
    ):
        overwrites.append(
            OverwriteRule(
                path=_string(overwrite_table.get("path"), f"overwrite[{index}].path"),
                reason=_string(
                    overwrite_table.get("reason", ""),
                    f"overwrite[{index}].reason",
                ),
            )
        )

    prefix_exceptions: list[PrefixExceptionRule] = []
    for index, exception_table in enumerate(
        _table_list(raw.get("prefix_exception", []), "prefix_exception")
    ):
        prefix_exceptions.append(
            PrefixExceptionRule(
                path=_string(
                    exception_table.get("path"),
                    f"prefix_exception[{index}].path",
                ),
                reason=_string(
                    exception_table.get("reason", ""),
                    f"prefix_exception[{index}].reason",
                ),
            )
        )

    naming = _naming_config(raw, prefix, config_path.parent, manifest_override)

    severity_table = _table(raw.get("severity", {}), "[severity]")
    severity: dict[str, str] = {}
    for code, value in severity_table.items():
        severity_value = _string(value, f"severity.{code}")
        if severity_value not in _VALID_SEVERITIES:
            raise ConfigError(
                f"severity.{code} has unsupported severity {severity_value!r}"
            )
        severity[code] = severity_value

    return Config(
        path=config_path,
        prefix=prefix,
        game_root=game_root,
        mount_roots=mount_roots,
        bom_default=bom_default,
        bom_rules=tuple(bom_rules),
        overwrites=tuple(overwrites),
        prefix_exceptions=tuple(prefix_exceptions),
        naming=naming,
        severity=severity,
    )


def _naming_config(
    raw: dict[str, object],
    mod_prefix: str,
    config_dir: Path,
    manifest_override: Path | None = None,
) -> NamingConfig:
    """Build [naming] policy, defaulting the owner prefix to mod.prefix."""

    naming = _table(raw.get("naming", {}), "[naming]")
    owner_prefix = _string(
        naming.get("owner_prefix", mod_prefix), "naming.owner_prefix"
    )
    subsystem_prefixes = _string_list(
        naming.get("subsystem_prefixes", []), "naming.subsystem_prefixes"
    )

    prefixes: list[str] = []
    for index, candidate in enumerate((owner_prefix, *subsystem_prefixes)):
        name = (
            "naming.owner_prefix"
            if index == 0
            else f"naming.subsystem_prefixes[{index - 1}]"
        )
        if candidate == "PREFIX_UNSET":
            # mod.prefix is still the pending-decision sentinel; EU5051 already
            # reports that, so the naming check simply has no owner prefix yet.
            continue
        if not candidate:
            raise ConfigError(f"{name} must not be empty")
        if candidate not in prefixes:
            prefixes.append(candidate)
    # Longest first, so an exact match never loses to a shorter configured
    # prefix that happens to be a prefix of it.
    prefixes.sort(key=lambda value: (-len(value), value))

    lowercase_globs: list[str] = []
    for index, glob in enumerate(
        _string_list(
            naming.get("lowercase_dirs", list(_DEFAULT_LOWERCASE_GLOBS)),
            "naming.lowercase_dirs",
        )
    ):
        lowercase_globs.append(
            _check_glob(glob, f"naming.lowercase_dirs[{index}]")
        )

    manifest_value = naming.get("manifest")
    if manifest_override is not None:
        manifest_path = manifest_override
    elif manifest_value is None:
        manifest_path = manifest_module.DEFAULT_PATH
    else:
        manifest_path = _resolve_path(
            _string(manifest_value, "naming.manifest"), config_dir
        )

    exceptions: list[NamingExceptionRule] = []
    for index, exception_table in enumerate(
        _table_list(raw.get("naming_exception", []), "naming_exception")
    ):
        exceptions.append(
            NamingExceptionRule(
                path=_string(
                    exception_table.get("path"), f"naming_exception[{index}].path"
                ),
                reason=_string(
                    exception_table.get("reason", ""),
                    f"naming_exception[{index}].reason",
                ),
            )
        )

    return NamingConfig(
        prefixes=tuple(prefixes),
        lowercase_globs=tuple(lowercase_globs),
        manifest_path=manifest_path,
        exceptions=tuple(exceptions),
    )


def matching_bom_rule(config: Config, relpath: str) -> BomRule | None:
    """Return the first configured BOM rule matching a POSIX mod path."""

    posix_path = PurePosixPath(relpath)
    for rule in config.bom_rules:
        if posix_path.full_match(rule.glob):
            return rule
    return None


def bom_policy(config: Config, relpath: str) -> str:
    rule = matching_bom_rule(config, relpath)
    if rule is None:
        return config.bom_default
    return rule.policy
