"""
RGO SETUP GENERATOR

Writes the setup file that places one RGO building in every owned location
at game start, so the engine creates the workers before day one. This
replaces the old game-start script that built them after the game began.

HOW TO RUN (from a terminal, any folder):

    python3 tools/generators_from_game_data/generators/rgo_setup/rgo_setup.py

The game path is read from tools/shared/config.ini (game_directory), like the
other generators. If that is not set, the GAME_FOLDERS list below is tried.
The setup file is written straight into the mod. Deploy as usual afterwards.
Rerun after a patch changes locations, raw materials, or starting pops.

HOW LEVELS ARE CHOSEN (same as the old script):

    level = peasants in the location / PEASANTS_PER_LEVEL, rounded up
    never below MIN_LEVEL, never above MAX_LEVEL (or the good's override)
    goods in DOUBLE_LEVEL_GOODS get twice that, rounded down

The old script also capped levels using each location's development,
which cannot be read from files. MAX_LEVEL stands in for that cap.

Everything you might want to change is in the SETTINGS block below.
"""

import math
import re
from pathlib import Path

# ============================== SETTINGS ==================================

# Fallback game install folders, used only when tools/shared/config.ini has
# no game_directory. The first folder that exists is used.
GAME_FOLDERS = [
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    "/mnt/c/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    "D:/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    "C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
]

# One building level per this many thousand peasants (10 = one level per 10,000).
PEASANTS_PER_LEVEL = 10

# Every location that gets a building gets at least this many levels.
MIN_LEVEL = 1

# No location gets more levels than this, unless its good is listed below.
MAX_LEVEL = 3

# Per-good caps that replace MAX_LEVEL. Example: {"wine": 5, "salt": 2}
MAX_LEVEL_BY_GOOD = {}

# Goods whose level is doubled (the old script doubled lumber).
DOUBLE_LEVEL_GOODS = ["lumber"]

# Goods that should get no building at all. Example: ["fish"]
SKIP_GOODS = []

# Only these country tags. Leave empty for every country. Example: ["FRA", "ENG"]
COUNTRIES = []

# Name of the file written into main_menu/setup/start. Keep the leading number
# high so it loads after vanilla's own setup files.
OUTPUT_FILE = "98_mnt_rgo_setup.txt"

# ========================== END OF SETTINGS ===============================


MOD_FOLDER = Path(__file__).resolve().parents[4]
TOOLS_FOLDER = MOD_FOLDER / "tools"

# The setup lists a location as owned under any of these keys.
OWNERSHIP_KEYS = [
    "own_control_core", "own_control_integrated", "own_control_conquered",
    "own_control_colony", "own_core", "own_conquered", "own_integrated", "own_colony",
]


def find_game_folder():
    """The game's 'game' folder: from tools/shared/config.ini first, then GAME_FOLDERS."""
    config_file = TOOLS_FOLDER / "shared" / "config.ini"
    if config_file.exists():
        import configparser
        config = configparser.ConfigParser()
        config.read(config_file)
        configured = config.get("Paths", "game_directory", fallback="").strip()
        if configured and (Path(configured) / "game").exists():
            return Path(configured) / "game"
    for folder in GAME_FOLDERS:
        if Path(folder).exists():
            return Path(folder)
    raise SystemExit("Game folder not found. Set game_directory in tools/shared/config.ini.")


def read_text_without_comments(path):
    text = path.read_text(encoding="utf-8-sig")
    return re.sub(r"#[^\n]*", "", text)


def read_owners(countries_setup_text):
    """Return {location: tag} for every location a country owns at start."""
    owners = {}
    # Walk the file keeping track of which country block we are inside.
    current_tag = None
    depth = 0
    for match in re.finditer(r"(\w+)\s*=\s*\{|\{|\}", countries_setup_text):
        token = match.group(0)
        if token == "}":
            depth -= 1
        elif token == "{":
            depth += 1
        else:
            depth += 1
            name = match.group(1)
            if depth == 3:
                current_tag = name
            elif depth == 4 and name in OWNERSHIP_KEYS and current_tag:
                # The list of location names runs up to the closing brace.
                end = countries_setup_text.index("}", match.end())
                for location in countries_setup_text[match.end():end].split():
                    owners[location] = current_tag
    return owners


def read_raw_materials(templates_text):
    """Return {location: good} from the location templates."""
    return dict(re.findall(r"^(\w+) = \{[^\n]*?raw_material = (\w+)", templates_text, re.M))


def read_peasants(pops_setup_text):
    """Return {location: thousands of peasants} from the pops setup."""
    peasants = {}
    for location, body in re.findall(r"^(\w+) = \{((?:[^{}]|\{[^{}]*\})*)\}", pops_setup_text, re.M):
        sizes = re.findall(r"define_pop = \{[^}]*type = peasants[^}]*size = ([0-9.]+)", body)
        peasants[location] = sum(float(s) for s in sizes)
    return peasants


def read_building_types(rgo_buildings_text):
    """Return the set of RGO building type names defined in the mod."""
    return set(re.findall(r"^(RGO_building_\w+)", rgo_buildings_text, re.M))


def choose_level(good, thousands_of_peasants):
    cap = MAX_LEVEL_BY_GOOD.get(good, MAX_LEVEL)
    level = math.ceil(thousands_of_peasants / PEASANTS_PER_LEVEL)
    if good in DOUBLE_LEVEL_GOODS:
        level = math.floor(2 * thousands_of_peasants / PEASANTS_PER_LEVEL)
    return max(MIN_LEVEL, min(cap, level))


def main():
    game = find_game_folder()
    setup = game / "main_menu" / "setup" / "start"

    # MnT replaces the location templates file, so prefer the mod's copy.
    templates_path = MOD_FOLDER / "in_game" / "map_data" / "location_templates.txt"
    if not templates_path.exists():
        templates_path = game / "in_game" / "map_data" / "location_templates.txt"

    owners = read_owners(read_text_without_comments(setup / "10_countries.txt"))
    raw_materials = read_raw_materials(read_text_without_comments(templates_path))
    peasants = read_peasants(read_text_without_comments(setup / "06_pops.txt"))
    building_types = read_building_types(
        (MOD_FOLDER / "in_game" / "common" / "building_types" / "RGO_buildings.txt").read_text(encoding="utf-8-sig")
    )

    lines = []
    missing_building_type = set()
    for location, tag in owners.items():
        if COUNTRIES and tag not in COUNTRIES:
            continue
        good = raw_materials.get(location)
        if not good or good in SKIP_GOODS:
            continue
        building = "RGO_building_" + good
        if building not in building_types:
            missing_building_type.add(good)
            continue
        level = choose_level(good, peasants.get(location, 0))
        lines.append(f"\t{building} = {{ tag = {tag} level = {level} location = {location} }}\n")

    output = MOD_FOLDER / "main_menu" / "setup" / "start" / OUTPUT_FILE
    output.parent.mkdir(parents=True, exist_ok=True)
    # Setup files can't carry a BOM encoding, so write plain UTF-8 bytes.
    output.write_bytes((
        "# GENERATED by tools/generators_from_game_data/generators/rgo_setup/rgo_setup.py.\n"
        "# Do not edit by hand, change the SETTINGS in that script and run it again.\n"
        "building_manager = {\n" + "".join(lines) + "}\n"
    ).encode("utf-8"))

    print(f"Wrote {len(lines)} RGO buildings to {output.relative_to(MOD_FOLDER)}")
    for good in sorted(missing_building_type):
        print(f"  no RGO building type for raw material '{good}', skipped")


if __name__ == "__main__":
    main()
