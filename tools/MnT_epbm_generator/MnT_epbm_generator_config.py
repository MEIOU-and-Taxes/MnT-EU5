"""
Configuration for MnT_generate_building_hooks.py.

Edit the values below to retarget or retune the generator. This file is
imported as a module by the generator script; all paths may be absolute or
relative to this file.

Do NOT introduce new names here without also wiring them into the generator —
the script reads these attributes explicitly by name.
"""

from pathlib import Path

# ─────────────────────────────────────────────
# Identifier prefix
# ─────────────────────────────────────────────
# Applied to every generated identifier (IO type, effect name, variable list
# name, filename, etc.). Keep aligned with the MnT_epbm_ handwritten files so
# the generated code can reference them.
PREFIX = "MnT_epbm"

# ─────────────────────────────────────────────
# Vanilla game in_game/ candidates
# ─────────────────────────────────────────────
# The generator tries each path in order and uses the first one that exists.
# Add entries here if your install is in a different location. Paths are
# Path() objects so slashes are forward-slash on every platform.
VANILLA_IN_GAME_CANDIDATES = [
    # WSL2 mounts for Windows Steam installs
    Path("/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game/in_game"),
    Path("/mnt/c/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game/in_game"),
    Path("/mnt/c/SteamLibrary/steamapps/common/Europa Universalis V/game/in_game"),
    Path("/mnt/d/SteamLibrary/steamapps/common/Europa Universalis V/game/in_game"),
    Path("/mnt/e/SteamLibrary/steamapps/common/Europa Universalis V/game/in_game"),
    # Native Windows paths (run from a Windows Python interpreter)
    Path("D:/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game/in_game"),
    Path("C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game/in_game"),
    Path("C:/SteamLibrary/steamapps/common/Europa Universalis V/game/in_game"),
    # Linux native Steam install
    Path.home() / ".steam/steam/steamapps/common/Europa Universalis V/game/in_game",
]

# ─────────────────────────────────────────────
# Mod paths (resolved relative to this config file)
# ─────────────────────────────────────────────
# Directory layout:
#   .dev-mods/MnT-EU5 Development/           <- _MOD_ROOT
#   └── tools/
#       └── MnT_epbm_generator/              <- _HERE
#           ├── MnT_epbm_generator_config.py
#           ├── MnT_generate_building_hooks.py
#           └── MnT_generate_building_hooks.README.md
_HERE = Path(__file__).resolve().parent
_MOD_ROOT = _HERE.parent.parent  # MnT_epbm_generator -> tools -> mod root

# MnT dev mod in_game/ directory. Building files here are rewritten in place
# by the generator. MUST point at the dev-mod copy, never the deployed copy.
MOD_IN_GAME = _MOD_ROOT / "in_game"

# Destination root for generated non-building files (IOs, biases, init effects,
# localization, plus the INJECT/REPLACE files for vanilla-only buildings). The
# generator creates subdirectories like `OUTPUT_ROOT / "in_game" / "common" / ...`
# under this root.
OUTPUT_ROOT = _MOD_ROOT

# ─────────────────────────────────────────────
# Safety toggles
# ─────────────────────────────────────────────
# The generator rewrites files inside MOD_IN_GAME/common/building_types/ in
# place. These gates exist so you don't accidentally overwrite unsaved work.

# Prompt interactively before rewriting building files. Bypassed when the
# MNT_EPBM_CI environment variable is set to a non-empty value (for GitHub
# Actions / other headless runs).
REQUIRE_CONFIRMATION = True

# Refuse to run if `git status` reports uncommitted changes inside
# MOD_IN_GAME/common/building_types. Leave this True — it is the single
# biggest safeguard against losing hand-edits to the hooked files.
REQUIRE_CLEAN_GIT = True
