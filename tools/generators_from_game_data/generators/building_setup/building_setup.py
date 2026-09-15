"""
BUILDING SETUP GENERATOR

Writes two setup files that place buildings in owned locations at game start:
  main_menu/setup/start/98_mnt_rgo_setup.txt       RGO buildings, from rgo_setup_settings.txt
  main_menu/setup/start/98_mnt_building_setup.txt  other building types, from building_setup_settings.txt
Both settings files sit next to this script and explain how to run it. They do not depend on each other.

It works from what the game reported about every location, through the mnt_rgo_setup_dump effect this
script also writes. The report is saved to building_setup_locations.csv and building_setup_countries.csv,
so the game only has to be started again after a patch, a change to locations, starting pops or where
buildings can be built, or a new building type in the settings.

The game and its logs are found in the usual places, or read from game_directory and log_directory in
tools/shared/config.ini.

To change the setup, edit the settings files. Nothing in this script needs editing.
"""

import collections
import configparser
import csv
import glob
import math
import re
import sys
from pathlib import Path

SCRIPT_FOLDER = Path(__file__).resolve().parent
MOD_FOLDER = SCRIPT_FOLDER.parents[3]
RGO_SETTINGS_FILE = SCRIPT_FOLDER / "rgo_setup_settings.txt"
BUILDING_SETTINGS_FILE = SCRIPT_FOLDER / "building_setup_settings.txt"
# The saved game data: one row per location, and one row per country for the building types it cannot build yet
LOCATIONS_FILE = SCRIPT_FOLDER / "building_setup_locations.csv"
COUNTRIES_FILE = SCRIPT_FOLDER / "building_setup_countries.csv"
# The locations file has two columns per building type: its max level there, empty where it cannot be built,
# and the levels already there at game start, empty where there are none
MAX_LEVEL_COLUMN = "max_level_"
LEVEL_COLUMN = "level_"
RGO_OUTPUT_FILE = MOD_FOLDER / "main_menu" / "setup" / "start" / "98_mnt_rgo_setup.txt"
BUILDING_OUTPUT_FILE = MOD_FOLDER / "main_menu" / "setup" / "start" / "98_mnt_building_setup.txt"
DUMP_EFFECT_FILE = MOD_FOLDER / "in_game" / "common" / "scripted_effects" / "MnT_setup_generated_loc_data_dump.txt"
# Removes the starting levels of building types set to destroy_vanilla_building_levels_before_counting, at game start
REMOVALS_EFFECT_FILE = MOD_FOLDER / "in_game" / "common" / "scripted_effects" / "MnT_setup_generated_building_removals.txt"
CONFIG_FILE = MOD_FOLDER / "tools" / "shared" / "config.ini"

DUMP_PREFIX = "MNT_RGO_DUMP "
# Raised whenever the dump's records change, so an older dump in debug.log is not read
DUMP_VERSION = 6
RGO_PREFIX = "RGO_building_"

# Where the game is usually installed, tried when tools/shared/config.ini has no game_directory
GAME_FOLDER_GUESSES = [
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    "/mnt/c/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    "D:/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    "C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game",
    str(Path.home() / ".steam" / "steam" / "steamapps" / "common" / "Europa Universalis V" / "game"),
]
# Where the game keeps its logs on Windows, Linux and WSL, tried when tools/shared/config.ini has no log_directory.
# The newest debug.log found wins.
LOG_FOLDER_GUESSES = [
    str(Path.home() / "Documents" / "Paradox Interactive" / "Europa Universalis V" / "logs"),
    str(Path.home() / "OneDrive" / "Documents" / "Paradox Interactive" / "Europa Universalis V" / "logs"),
    str(Path.home() / ".local" / "share" / "Paradox Interactive" / "Europa Universalis V" / "logs"),
    "/mnt/c/Users/*/Documents/Paradox Interactive/Europa Universalis V/logs",
    "/mnt/c/Users/*/OneDrive/Documents/Paradox Interactive/Europa Universalis V/logs",
]

# The [general] settings each settings file takes
RGO_GENERAL_SETTINGS = [
    "countries", "pop_types_for_levels", "respect_technology", "place_secondary_rgos", "max_secondary_rgos_per_location",
]
BUILDING_GENERAL_SETTINGS = ["countries", "report_building_types", "pop_types_for_levels", "respect_technology"]
# [general] settings that may be left out or set to None
OPTIONAL_SETTINGS = {"countries", "report_building_types"}
# The location multiplier lists, and the location fact each one looks up
LIST_SETTINGS = {
    "river_multiplier": "river",
    "location_rank_multiplier": "location_rank",
    "topography_multiplier": "topography",
    "vegetation_multiplier": "vegetation",
    "climate_multiplier": "climate",
}
RIVER_SIZES = ["none", "1", "2", "3", "4", "5"]
# The location facts the dump reports as keys, and the folder in in_game/common that defines them
FACT_FOLDERS = {"topography": "topography", "vegetation": "vegetation", "climate": "climates", "location_rank": "location_ranks"}
# How the dump checks each fact. The game rejects topography:<key>, vegetation:<key> and climate:<key> here, but needs location_rank:<key>.
FACT_CHECKS = {
    "topography": "topography = {key}",
    "vegetation": "vegetation = {key}",
    "climate": "climate = {key}",
    "location_rank": "location_rank = location_rank:{key}",
}
# The settings that add up a base level
BASE_LEVEL_SETTINGS = ["peasants_per_level", "development_per_level", "base_level_by_location_rank"]
# The settings that work a level out from the location. fixed_level replaces all of them.
POP_STEP_SETTINGS = (BASE_LEVEL_SETTINGS + ["final_level_multiplier", "additive_multiplier_per_development", "additive_multiplier_per_population",
                                            "lake_multiplier", "coastal_multiplier"]
                     + list(LIST_SETTINGS) + ["round_levels", "percentage_of_building_max_level"])
LEVEL_SETTINGS = POP_STEP_SETTINGS + ["fixed_level", "fixed_level_floor", "fixed_level_ceiling"]
# The settings a building type's section takes in each settings file. Only RGO buildings are picked as secondary buildings.
RGO_BUILDING_SETTINGS = ["place", "place_as_secondary", "secondary_priority", "ideal_rgo_multiplier", "destroy_vanilla_building_levels_before_counting"] + LEVEL_SETTINGS
OTHER_BUILDING_SETTINGS = ["place", "destroy_vanilla_building_levels_before_counting"] + LEVEL_SETTINGS
# A distribution group's section takes the building settings and its list of building types. A building type in a group
# only takes the settings that limit it alone, since the group works out the level.
GROUP_SETTING = "distribution_group"
GROUP_SETTINGS = [GROUP_SETTING] + OTHER_BUILDING_SETTINGS
GROUP_MEMBER_SETTINGS = ["place", "destroy_vanilla_building_levels_before_counting", "round_levels", "percentage_of_building_max_level"]
# Settings that cannot be used together. A section may fill in one side of a pair, not both, and the
# most specific section that fills in either side decides which side a building type uses.
CONFLICTING_SETTINGS = [
    (["fixed_level"], POP_STEP_SETTINGS, "fixed_level gives the level directly, so steps 1 to 4 would do nothing"),
]
# The default section of each settings file, and how messages write the sections that are not building types
RGO_DEFAULT_SECTION = "all rgo buildings"
BUILDING_DEFAULT_SECTION = "all buildings"
SPECIAL_SECTIONS = {"general": "general", RGO_DEFAULT_SECTION: "all RGO buildings", BUILDING_DEFAULT_SECTION: "all buildings"}

ROUNDING = {
    "up": math.ceil,
    "down": math.floor,
    "nearest": lambda value: math.floor(value + 0.5),
}

# The engine buffers debug_log writes and only flushes when the buffer is full.
# Without padding the dump can be incomplete until several months of game time pass.
# These lines overflow the buffer so the data above is flushed immediately.
FILLER_LINE = "MNT_RGO_FLUSH" + " padding" * 120


class Problem(Exception):
    """A mistake the person running the script can fix. Printed without a traceback."""


def shown(section_name):
    return SPECIAL_SECTIONS.get(section_name, section_name)


def shown_path(path):
    """The path from the mod's folder when it is inside it, otherwise the full path."""
    return path.relative_to(MOD_FOLDER) if path.is_relative_to(MOD_FOLDER) else path


def in_file(path, function, *arguments):
    """Runs function, naming the settings file in any problem it finds."""
    try:
        return function(*arguments)
    except Problem as problem:
        raise Problem(f"{path.name}: {problem}") from None


# ------------------------------------------------------------------ settings

def read_yes_no(section, key, text):
    value = text.strip().lower()
    if value in ("yes", "true"):
        return True
    if value in ("no", "false"):
        return False
    raise Problem(f'In [{section}], {key} must be yes or no, but it is "{text.strip()}".')


def read_number(section, key, text, whole=False, above_zero=False):
    """Returns None for None or a blank value. Accepts 25 and 25%."""
    value = text.strip().rstrip("%").strip()
    if value.lower() in ("", "none"):
        return None
    try:
        result = float(value)
    except ValueError:
        raise Problem(f'In [{section}], {key} must be a number, but it is "{text.strip()}".')
    if whole and result != int(result):
        raise Problem(f'In [{section}], {key} must be a whole number, but it is "{text.strip()}".')
    if result < 0 or (above_zero and result == 0):
        rule = "above 0" if above_zero else "0 or more"
        raise Problem(f'In [{section}], {key} must be {rule}, but it is "{text.strip()}".')
    return int(result) if whole else result


def read_multipliers(section, key, text):
    """Reads { "flatland": 1, "hills": 0.5 } into {"flatland": 1.0, "hills": 0.5}. None or blank gives {}."""
    text = text.strip()
    if text.lower() in ("", "none"):
        return {}
    if not (text.startswith("{") and text.endswith("}")):
        raise Problem(f'In [{section}], {key} must be a list in braces, like {{ "flatland": 1, "hills": 0.5 }}, but it is "{text}".')
    result = {}
    for part in text[1:-1].replace("\n", ",").split(","):
        if not part.strip():
            continue
        name, colon, number = part.partition(":")
        name = name.strip().strip("\"'").lower()
        if not colon or not name:
            raise Problem(f'In [{section}], {key} must be a list in braces, like {{ "flatland": 1, "hills": 0.5 }}, but it has "{part.strip()}".')
        value = read_number(section, f"{key} for {name}", number)
        if value is None:
            raise Problem(f"In [{section}], {key} needs a number for {name}.")
        result[name] = value
    return result


def read_name_list(section, key, text):
    """Reads [ "SWE", "DAN" ] into ["SWE", "DAN"]. None or blank gives []."""
    text = text.strip()
    if text.lower() in ("", "none"):
        return []
    if not (text.startswith("[") and text.endswith("]")):
        raise Problem(f'In [{section}], {key} must be a list in square brackets, like [ "SWE", "DAN" ], but it is "{text}".')
    return [name.strip().strip("\"'") for name in text[1:-1].replace("\n", ",").split(",") if name.strip().strip("\"'")]


def read_settings_file(path):
    """Returns {section: {setting: text}}. A value that opens with { runs on to the line that ends with }."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        raise Problem(f"The settings file is missing. It should be here:\n  {path}")
    sections, section_name, open_list = {}, None, None
    for number, line in enumerate(lines, 1):
        # A note starts at a # at the start of a line or after a space
        text = re.sub(r"(^|\s)#.*", "", line).strip()
        if open_list is not None:
            key, start, parts, closer = open_list
            if (text.startswith("[") and not text.startswith('["')) or re.match(r"\w+\s*=", text):
                raise Problem(f"In [{section_name}], the list for {key} that starts on line {start} needs a closing {closer} before line {number}.")
            parts.append(text)
            if text.endswith(closer):
                sections[section_name][key] = "\n".join(parts)
                open_list = None
            continue
        if not text:
            continue
        if text.startswith("[") and text.endswith("]"):
            section_name = text[1:-1].strip()
            if section_name.lower() in (name.lower() for name in sections):
                raise Problem(f"Line {number}: [{section_name}] is already used further up.")
            sections[section_name] = {}
            continue
        key, equals, value = text.partition("=")
        key, value = key.strip().lower(), value.strip()
        if not equals or not key:
            raise Problem(f"Line {number} is not a setting, a [section] or a note:\n  {line.strip()}")
        if section_name is None:
            raise Problem(f"Line {number}: {key} comes before any [section].")
        if key in sections[section_name]:
            raise Problem(f"Line {number}: {key} is already set further up in [{section_name}].")
        closer = {"{": "}", "[": "]"}.get(value[:1])
        if closer and not value.endswith(closer):
            open_list = (key, number, [value], closer)
        else:
            sections[section_name][key] = value
    if open_list is not None:
        raise Problem(f"In [{section_name}], the list for {open_list[0]} that starts on line {open_list[1]} is never closed with a {open_list[3]}.")
    return sections


def read_general(sections, allowed):
    general_section = next((section for name, section in sections.items() if name.lower() == "general"), None)
    if general_section is None:
        raise Problem("The file needs a [general] section.")
    for key in general_section:
        if key not in allowed:
            raise Problem(f'In [general], "{key}" is not a setting. Settings you can use there:\n  ' + ", ".join(allowed))

    def text_of(key):
        if key in general_section:
            return "" if general_section[key].strip().lower() == "none" else general_section[key]
        if key in OPTIONAL_SETTINGS:
            return ""
        raise Problem(f"[general] is missing the {key} setting.")

    def required_number(key, **rules):
        value = read_number("general", key, text_of(key), **rules)
        if value is None:
            raise Problem(f"In [general], {key} needs a number.")
        return value

    general = {
        "countries": {tag.upper() for tag in read_name_list("general", "countries", text_of("countries"))},
        # all counts every pop type, filled in once the game data is loaded
        "pop_types_for_levels": ["all"] if text_of("pop_types_for_levels").strip().lower() == "all" else
                                [pop_type.lower() for pop_type in read_name_list("general", "pop_types_for_levels", text_of("pop_types_for_levels"))],
        "respect_technology": read_yes_no("general", "respect_technology", text_of("respect_technology")),
    }
    if not general["pop_types_for_levels"]:
        raise Problem("In [general], pop_types_for_levels needs at least one pop type, for example: peasants")
    if "report_building_types" in allowed:
        general["report_building_types"] = read_name_list("general", "report_building_types", text_of("report_building_types"))
    if "place_secondary_rgos" in allowed:
        general.update({
            "place_secondary_rgos": read_yes_no("general", "place_secondary_rgos", text_of("place_secondary_rgos")),
            "max_secondary_rgos_per_location": required_number("max_secondary_rgos_per_location", whole=True),
        })
    return general


def name_sections(sections, building_types, for_rgo_buildings):
    """The sections keyed by general, the default section or the building type's own key."""
    default_section = RGO_DEFAULT_SECTION if for_rgo_buildings else BUILDING_DEFAULT_SECTION
    allowed = RGO_BUILDING_SETTINGS if for_rgo_buildings else OTHER_BUILDING_SETTINGS
    keys_by_lower = {key.lower(): key for key in building_types}
    named = {}
    for name, section in sections.items():
        lower = name.lower()
        if lower in ("general", default_section):
            named[lower] = section
        elif lower in keys_by_lower:
            key = keys_by_lower[lower]
            if for_rgo_buildings and not key.startswith(RGO_PREFIX):
                raise Problem(f"[{name}] is not an RGO building. Other building types go in {BUILDING_SETTINGS_FILE.name}.")
            if not for_rgo_buildings and key.startswith(RGO_PREFIX):
                raise Problem(f"[{name}] is an RGO building. RGO buildings go in {RGO_SETTINGS_FILE.name}.")
            named[key] = section
        elif not for_rgo_buildings and GROUP_SETTING in section:
            named[name] = section
        else:
            example = "[RGO_building_lumber]" if for_rgo_buildings else "[victualling_house]"
            group = "" if for_rgo_buildings else f", or is a distribution group with a {GROUP_SETTING} list"
            raise Problem(f"[{name}] is not a building type in the mod or the game. A section is named with a building type's key, "
                          f"like {example}, or is [general] or [{shown(default_section)}]{group}.")
    if default_section not in named:
        raise Problem(f"The file needs an [{shown(default_section)}] section.")
    for name, section in named.items():
        if name != "general":
            allowed_here = GROUP_SETTINGS if name not in building_types and name not in (default_section, "general") else allowed
            for key in section:
                if key not in allowed_here:
                    raise Problem(f'In [{shown(name)}], "{key}" is not a setting. Settings you can use there:\n  ' + ", ".join(allowed_here))
    return named


def distribution_groups(sections, building_types):
    """{group: [building types]} for every distribution group, in the order its list gives, and {building type: group}."""
    keys_by_lower = {key.lower(): key for key in building_types}
    groups, group_of = {}, {}
    for name, section in sections.items():
        if GROUP_SETTING not in section:
            continue
        members = []
        for listed in read_name_list(name, GROUP_SETTING, section[GROUP_SETTING]):
            key = keys_by_lower.get(listed.lower())
            if key is None:
                raise Problem(f'In [{name}], {GROUP_SETTING} has "{listed}", which is not a building type in the mod or the game.')
            if key.startswith(RGO_PREFIX):
                raise Problem(f"In [{name}], {key} is an RGO building. RGO buildings go in {RGO_SETTINGS_FILE.name}.")
            if key in group_of:
                raise Problem(f"{key} is in both [{group_of[key]}] and [{name}]. A building type can only be in one distribution group.")
            group_of[key] = name
            members.append(key)
        if not members:
            raise Problem(f"In [{name}], {GROUP_SETTING} needs at least one building type.")
        groups[name] = members
    for key, group in group_of.items():
        extra = [setting for setting in sections.get(key, {}) if setting not in GROUP_MEMBER_SETTINGS]
        if extra:
            raise Problem(f"[{key}] is in the distribution group [{group}], which works out its level, so its own section can only have "
                          + ", ".join(GROUP_MEMBER_SETTINGS) + f". Move {', '.join(extra)} to [{group}].")
    return groups, group_of


def building_rules(sections, placeable, default_section, group_of=None):
    """The settings each building type and distribution group ends up with, and every name the lists use."""
    group_of = group_of or {}
    def filled(section_name, key):
        return section_name in sections and sections[section_name].get(key, "").strip().lower() not in ("", "none")

    for section_name in sections:
        if section_name == "general":
            continue
        for side_a, side_b, reason in CONFLICTING_SETTINGS:
            used_a = [key for key in side_a if filled(section_name, key)]
            used_b = [key for key in side_b if filled(section_name, key)]
            if used_a and used_b:
                raise Problem(f"In [{shown(section_name)}], {' and '.join(used_a)} cannot be used together with "
                              f"{' and '.join(used_b)}: {reason}. Set one side to None.")

    # Every name a list uses, checked against the game's definitions later
    listed = []
    for section_name, section in sections.items():
        if section_name != "general":
            for setting in LIST_SETTINGS:
                listed += [(shown(section_name), setting, name) for name in read_multipliers(shown(section_name), setting, section.get(setting, ""))]
            for setting in ("fixed_level", "base_level_by_location_rank"):
                if section.get(setting, "").strip().startswith("{"):
                    listed += [(shown(section_name), setting, name) for name in read_multipliers(shown(section_name), setting, section[setting])]

    rules_by_building = {}
    for building in placeable:
        # The building type's own section first, then its distribution group's, then the default section
        chain = ([building] if building in sections else []) + ([group_of[building]] if building in group_of else []) + [default_section]

        not_used = set()
        for side_a, side_b, _ in CONFLICTING_SETTINGS:
            for section_name in chain:
                if any(filled(section_name, key) for key in side_a):
                    not_used.update(side_b)
                    break
                if any(filled(section_name, key) for key in side_b):
                    not_used.update(side_a)
                    break
            else:
                not_used.update(side_a)

        def where(key):
            # The nearest section that has the setting decides, so None in a building type's section turns it off there
            return next((name for name in chain if key in sections.get(name, {})), default_section)

        def text_for(key):
            return "" if key in not_used else sections[where(key)].get(key, "").strip()

        def yes_no_for(key):
            if text_for(key) == "":
                raise Problem(f"[{shown(default_section)}] needs {key} = yes or no.")
            return read_yes_no(shown(where(key)), key, text_for(key))

        def number_for(key, required, **rules):
            value = read_number(shown(where(key)), key, text_for(key), **rules)
            if value is None and required:
                raise Problem(f"[{building}] has no {key}. Fill it in under [{shown(default_section)}], or use fixed_level instead of steps 1 to 4.")
            return value

        def multipliers_for(key):
            # A building type's own list adds to the default section's, replacing only the names it lists
            if key in not_used:
                return {}
            # None in a section drops the lists of the sections under it
            used = []
            for section_name in chain:
                if key in sections.get(section_name, {}):
                    if not filled(section_name, key):
                        break
                    used.append(section_name)
            merged = {}
            for section_name in reversed(used):
                merged.update(read_multipliers(shown(section_name), key, sections[section_name][key]))
            return merged

        def fixed_level_for():
            # One whole number for every location, or a list of whole numbers by location rank
            text = text_for("fixed_level")
            if not text.startswith("{"):
                return number_for("fixed_level", False, whole=True)
            levels = read_multipliers(shown(where("fixed_level")), "fixed_level", text)
            for rank, level in levels.items():
                if level != int(level):
                    raise Problem(f"In [{shown(where('fixed_level'))}], fixed_level for {rank} must be a whole number, but it is {level:g}.")
            return {rank: int(level) for rank, level in levels.items()}

        uses_pop_steps = "fixed_level" in not_used
        round_levels = text_for("round_levels").lower() if uses_pop_steps else "down"
        if round_levels not in ROUNDING:
            raise Problem(f'In [{shown(where("round_levels"))}], round_levels must be up, down or nearest, but it is "{round_levels}".')
        rules = {
            "place": yes_no_for("place"),
            "destroy_vanilla_building_levels_before_counting": yes_no_for("destroy_vanilla_building_levels_before_counting"),
            "peasants_per_level": number_for("peasants_per_level", False, above_zero=True),
            "development_per_level": number_for("development_per_level", False, above_zero=True),
            "base_level_by_location_rank": multipliers_for("base_level_by_location_rank"),
            "final_level_multiplier": number_for("final_level_multiplier", uses_pop_steps),
            "additive_multiplier_per_development": number_for("additive_multiplier_per_development", False),
            "additive_multiplier_per_population": number_for("additive_multiplier_per_population", False),
            "lake_multiplier": number_for("lake_multiplier", False),
            "coastal_multiplier": number_for("coastal_multiplier", False),
            **{setting: multipliers_for(setting) for setting in LIST_SETTINGS},
            "round_levels": round_levels,
            "percentage_of_building_max_level": number_for("percentage_of_building_max_level", False),
            "fixed_level": fixed_level_for(),
            "fixed_level_floor": number_for("fixed_level_floor", False, whole=True),
            "fixed_level_ceiling": number_for("fixed_level_ceiling", False, whole=True),
        }
        # A building type in a distribution group gets its level from the group
        if uses_pop_steps and rules["place"] and building not in group_of and rules["peasants_per_level"] is None and rules["development_per_level"] is None and not rules["base_level_by_location_rank"]:
            raise Problem(f"[{building}] has no base level. Fill in peasants_per_level, development_per_level or base_level_by_location_rank, "
                          f"or use fixed_level instead of steps 1 to 4.")
        if default_section == RGO_DEFAULT_SECTION:
            rules["place_as_secondary"] = yes_no_for("place_as_secondary")
            rules["secondary_priority"] = number_for("secondary_priority", False) or 0
            ideal_rgo_multiplier = number_for("ideal_rgo_multiplier", False)
            rules["ideal_rgo_multiplier"] = 1 if ideal_rgo_multiplier is None else ideal_rgo_multiplier
        rules_by_building[building] = rules
    return rules_by_building, listed


# ------------------------------------------------------------- game files

def read_config_path(key):
    """A path from the [Paths] section of tools/shared/config.ini, or blank."""
    if not CONFIG_FILE.is_file():
        return ""
    config = configparser.ConfigParser(inline_comment_prefixes=("#",))
    config.read(CONFIG_FILE)
    return config.get("Paths", key, fallback="").strip()


def find_game_folder():
    """The game's 'game' folder: from game_directory in tools/shared/config.ini, or the usual install folders."""
    configured = read_config_path("game_directory")
    candidates = [Path(configured).expanduser()] if configured else [Path(folder) for folder in GAME_FOLDER_GUESSES]
    for folder in candidates:
        for game in (folder, folder / "game"):
            if (game / "in_game" / "common" / "building_types").is_dir():
                return game
    if configured:
        raise Problem(f"game_directory in tools/shared/config.ini points to\n  {configured}\nbut the game is not there.")
    raise Problem("The game was not found. Set game_directory in tools/shared/config.ini to the folder the game is installed in. "
                  "If there is no config.ini, copy example_config.ini next to it and name the copy config.ini.")


def text_without_notes(path):
    return re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig", errors="replace"))


def game_files(game, folder):
    """The .txt files the game loads from one folder, a mod file replacing the game's file of the same name."""
    files = {path.name: path for path in (game / folder).glob("*.txt")}
    files.update({path.name: path for path in (MOD_FOLDER / folder).glob("*.txt")})
    return [files[name] for name in sorted(files) if name.lower() != "readme.txt"]


def top_level_blocks(text):
    """[(name, body)] for every name = { ... } at the outermost level of the text."""
    blocks, depth, name, start = [], 0, None, 0
    for match in re.finditer(r"([A-Za-z0-9_:.@-]+)\s*=\s*\{|\{|\}", text):
        if match.group(0) == "}":
            depth -= 1
            if depth == 0 and name:
                blocks.append((name, text[start:match.start()]))
                name = None
        else:
            if depth == 0:
                name, start = match.group(1), match.end()
            depth += 1
    return blocks


def block_after(text, open_brace_end):
    """The text between a { that ends at open_brace_end and its closing }."""
    depth, index = 1, open_brace_end
    while depth and index < len(text):
        depth += (text[index] == "{") - (text[index] == "}")
        index += 1
    return text[open_brace_end:index - 1]


def read_definition_keys(game, folder):
    keys = set()
    for path in game_files(game, Path("in_game") / "common" / folder):
        keys.update(name.rpartition(":")[2] for name, _ in top_level_blocks(text_without_notes(path)) if not name.startswith("@"))
    return sorted(keys)


def read_building_max_levels(game):
    """{building type: its max_levels as a number, a script value name, a { } calculation, or None}."""
    max_levels = {}
    for path in game_files(game, Path("in_game") / "common" / "building_types"):
        for name, body in top_level_blocks(text_without_notes(path)):
            prefix, _, key = name.rpartition(":")
            found = re.search(r"(?:^|\s)max_levels\s*=\s*(\{|[^\s{}]+)", body)
            value = None
            if found:
                value = found.group(1) if found.group(1) != "{" else "{ " + " ".join(block_after(body, found.end()).split()) + " }"
            if prefix.startswith("INJECT"):
                if value is not None or key not in max_levels:
                    max_levels[key] = value if value is not None else max_levels.get(key)
            else:
                max_levels[key] = value
    return max_levels


def read_can_extract_goods(game):
    """The goods that have a can_extract_<good> modifier."""
    goods = set()
    for path in game_files(game, Path("main_menu") / "common" / "modifier_type_definitions"):
        goods.update(re.findall(r"^(?:[A-Z_]+:)?can_extract_(\w+)\s*=", text_without_notes(path), re.M))
    return goods


# ------------------------------------------------------------- the dump effect

def dump_effect_text(covered, max_levels, can_extract_goods, fact_keys, pop_types):
    local = lambda name, decimals: f"[SCOPE.GetLocalVariable('mnt_rgo_dump_{name}').GetValue|{decimals}]"
    lines = [
        "# GENERATED by tools/generators_from_game_data/generators/building_setup/building_setup.py for the building types its settings cover.",
        "# Do not edit by hand. Runs at game start when mnt_rgo_setup_dump_on_start is uncommented in on_game_start (MnT_pulse.txt).",
        "mnt_rgo_setup_dump = {",
        "\t# The generator only reads a dump that has both the start and the end line",
        f'\tdebug_log = "{DUMP_PREFIX}record=start;version={DUMP_VERSION}"',
    ]
    lines += [f'\tdebug_log = "{DUMP_PREFIX}record=covered;building={building}"' for building in covered]

    lines += ["", "\tevery_country = {", "\t\tlimit = { num_locations > 0 }",
              "\t\t# One line per building type this country cannot build yet, with each check the game makes: 1 passes, 0 fails"]
    for building in covered:
        # The country's can_build_building covers the advance that unlocks a building, but not can_extract for RGO buildings
        checks = [("can_build_building", f"can_build_building = building_type:{building}")]
        good = building[len(RGO_PREFIX):] if building.startswith(RGO_PREFIX) else None
        if good in can_extract_goods:
            checks.append(("can_extract", f"modifier:can_extract_{good} = yes"))
        any_fails = " ".join(f"NOT = {{ {trigger} }}" for _, trigger in checks)
        flags = " ".join(f"set_local_variable = {{ name = mnt_rgo_dump_{flag} value = 0 }} "
                         f"if = {{ limit = {{ {trigger} }} set_local_variable = {{ name = mnt_rgo_dump_{flag} value = 1 }} }}" for flag, trigger in checks)
        fields = ";".join(f"{flag}={local(flag, 0)}" for flag, _ in checks)
        lines.append(f'\t\tif = {{ limit = {{ OR = {{ {any_fails} }} }} {flags} '
                     f'debug_log = "{DUMP_PREFIX}record=cannot_build;country=[THIS.GetCountry.GetDebugTag];building={building};{fields}" }}')
    lines.append("\t}")

    # Only owned locations get buildings, and the RGO buildings' allow reads the owner
    lines += ["", "\tevery_ownable_location = {",
              "\t\tlimit = { has_owner = yes }",
              "\t\tset_local_variable = { name = mnt_rgo_dump_development value = development }",
              "\t\tset_local_variable = { name = mnt_rgo_dump_population value = population }"]
    lines += [f"\t\tset_local_variable = {{ name = mnt_rgo_dump_pop_{pop_type} value = num_pop_type:{pop_type} }}" for pop_type in pop_types]
    for flag, trigger in (("has_river", "has_river"), ("adjacent_to_lake", "is_adjacent_to_lake"), ("is_coastal", "is_coastal")):
        lines.append(f"\t\tset_local_variable = {{ name = mnt_rgo_dump_{flag} value = 0 }}")
        lines.append(f"\t\tif = {{ limit = {{ {trigger} = yes }} set_local_variable = {{ name = mnt_rgo_dump_{flag} value = 1 }} }}")
    fields = (f"raw_material=[THIS.GetLocation.GetRawMaterial.GetKey];is_coastal={local('is_coastal', 0)};has_river={local('has_river', 0)};"
              + "".join(f"river_size_{size}=[THIS.GetLocation.HasRiverSize{size}];" for size in range(1, 6))
              + f"adjacent_to_lake={local('adjacent_to_lake', 0)};development={local('development', 5)};population={local('population', 5)}"
              + "".join(f";pop_{pop_type}={local('pop_' + pop_type, 5)}" for pop_type in pop_types))
    lines += ["",
              f'\t\tdebug_log = "{DUMP_PREFIX}record=location;location=[THIS.GetLocation.GetTag];has_owner=yes;owner=[THIS.GetLocation.GetOwner.GetDebugTag];{fields}"']

    lines += ["", "\t\t# One line each for the topography, vegetation, climate and location rank, as the keys the settings use"]
    for fact, keys in fact_keys.items():
        for index, key in enumerate(keys):
            word = "if" if index == 0 else "else_if"
            lines.append(f'\t\t{word} = {{ limit = {{ {FACT_CHECKS[fact].format(key=key)} }} debug_log = "{DUMP_PREFIX}record={fact};location=[THIS.GetLocation.GetTag];key={key}" }}')
        lines.append(f'\t\telse = {{ debug_log = "{DUMP_PREFIX}record={fact};location=[THIS.GetLocation.GetTag];key=unknown" }}')

    lines += ["", "\t\t# One line per building type this location can build or already has, and for the RGO building of its raw material:",
              "\t\t# whether it can build it, its max level and the levels already there"]
    for building in covered:
        set_max_level = "" if max_levels[building] is None else f"set_local_variable = {{ name = mnt_rgo_dump_max_level value = {max_levels[building]} }} "
        max_level = "None" if max_levels[building] is None else local("max_level", 5)
        # The RGO building for the location's raw material is reported even where it cannot be built, because its level is the
        # baseline for the secondary RGO buildings. Every good has a can_extract modifier, which tells goods from keys like bad_sand
        good = building[len(RGO_PREFIX):] if building.startswith(RGO_PREFIX) else None
        own_raw_material = f" raw_material = goods:{good}" if good in can_extract_goods else ""
        lines.append(
            f"\t\tif = {{ limit = {{ OR = {{ can_build_building = building_type:{building} has_building_with_at_least_one_level = {building}{own_raw_material} }} }} "
            f"set_local_variable = {{ name = mnt_rgo_dump_can_build value = 0 }} "
            f"if = {{ limit = {{ can_build_building = building_type:{building} }} set_local_variable = {{ name = mnt_rgo_dump_can_build value = 1 }} }} "
            f"{set_max_level}"
            f'set_local_variable = {{ name = mnt_rgo_dump_level value = "location_building_level(building_type:{building})" }} '
            f'debug_log = "{DUMP_PREFIX}record=building;location=[THIS.GetLocation.GetTag];building={building};'
            f'can_build={local("can_build", 0)};max_level={max_level};level={local("level", 0)}" }}'
        )
    lines += ["\t}", "", f'\tdebug_log = "{DUMP_PREFIX}record=end"', "",
              "\t# The engine buffers debug_log writes and only flushes when the buffer is full.",
              "\t# Without padding the dump can be incomplete until several months of game time pass.",
              "\t# These lines overflow the buffer so the data above is flushed immediately.",
              "\twhile = {", "\t\tcount = 1000", f'\t\tdebug_log = "{FILLER_LINE}"', "\t}", "}", ""]
    return "\n".join(lines)


def write_dump_effect(text):
    """Writes the dump effect when it changed. Returns a note for the person running the script, or None."""
    if DUMP_EFFECT_FILE.is_file() and DUMP_EFFECT_FILE.read_text(encoding="utf-8-sig") == text:
        return None
    DUMP_EFFECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Script files need a BOM
    DUMP_EFFECT_FILE.write_text(text, encoding="utf-8-sig", newline="\n")
    return (f"Updated {shown_path(DUMP_EFFECT_FILE)} for the building types the settings cover.\n"
            "The game data only changes after a new dump: see TO UPDATE THE GAME DATA at the bottom of either settings file.")


# ----------------------------------------------------------------- game data

def find_debug_log():
    """The debug.log to look for a new dump in, or None when there is none."""
    configured = read_config_path("log_directory")
    if configured:
        path = Path(configured).expanduser()
        if path.is_dir():
            path = path / "debug.log"
        if not path.is_file():
            raise Problem(f"log_directory in tools/shared/config.ini points to\n  {configured}\nbut there is no debug.log there.")
        return path
    found = [Path(folder) / "debug.log" for guess in LOG_FOLDER_GUESSES for folder in glob.glob(guess)]
    found = [path for path in found if path.is_file()]
    return max(found, key=lambda path: path.stat().st_mtime) if found else None


def read_value(text):
    """Numbers become numbers, None becomes None, anything else stays text."""
    if text == "None":
        return None
    try:
        return float(text)
    except ValueError:
        return text


def read_dump(log_path):
    """Returns ("none", None), ("unfinished", None) or ("complete", game data)."""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    start = text.rfind(f"{DUMP_PREFIX}record=start;version={DUMP_VERSION}")
    if start < 0:
        return "none", None
    end = text.find(DUMP_PREFIX + "record=end", start)
    if end < 0:
        return "unfinished", None

    needed = {
        "location": ["location", "has_owner", "owner", "raw_material", "development", "is_coastal", "adjacent_to_lake",
                     "river_size_1", "river_size_5", "pop_peasants"],
        "covered": ["building"],
        "building": ["location", "building", "can_build", "max_level", "level"],
        "cannot_build": ["country", "building"],
        **{fact: ["location", "key"] for fact in FACT_FOLDERS},
    }
    covered, locations, cannot_build = [], {}, {}
    for line in text[start:end].splitlines():
        at = line.find(DUMP_PREFIX)
        if at < 0:
            continue
        fields = dict(part.split("=", 1) for part in line[at + len(DUMP_PREFIX):].split(";") if "=" in part)
        kind = fields.get("record")
        if kind not in needed:
            continue
        if any(key not in fields for key in needed[kind]):
            raise Problem("The dump in debug.log was made with an older version of the dump effect. "
                          "Make a new dump: see TO UPDATE THE GAME DATA at the bottom of either settings file.")
        if kind == "location":
            facts = {key: read_value(value) for key, value in fields.items() if key not in ("record", "location")}
            # The max level of the RGO building for the location's raw material, filled in from its building line
            facts["main_rgo_max_level"] = None
            facts["buildings"] = {}
            locations[fields["location"]] = facts
        elif kind == "covered":
            covered.append(fields["building"])
        elif kind == "building":
            can_build = read_value(fields["can_build"]) == 1
            locations[fields["location"]]["buildings"][fields["building"]] = {
                "can_build": can_build,
                # A max level only matters where the building can be built
                "max_level": read_value(fields["max_level"]) if can_build else None,
                "level": read_value(fields["level"]),
            }
            facts = locations[fields["location"]]
            if fields["building"] == RGO_PREFIX + str(facts["raw_material"]):
                facts["main_rgo_max_level"] = read_value(fields["max_level"])
        elif kind == "cannot_build":
            cannot_build.setdefault(fields["country"], []).append(fields["building"])
        else:
            locations[fields["location"]][kind] = fields["key"]
    if not locations:
        raise Problem("The dump in debug.log has no locations in it. Make a new dump.")
    for facts in locations.values():
        # The river multiplier looks up the river size, or none
        facts["river"] = next((str(size) for size in range(1, 6) if facts.get(f"river_size_{size}")), "none")
    return "complete", {"covered": covered, "locations": locations,
                        "cannot_build": {tag: sorted(buildings) for tag, buildings in cannot_build.items()}}


def csv_cell(value):
    """None as None, whole numbers without .0, other numbers in full."""
    if value is None:
        return "None"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def save_game_data(data):
    # One row per location and per country, so the files open in a spreadsheet and compare well in git
    fact_columns = [key for key in next(iter(data["locations"].values())) if key != "buildings"]
    building_columns = [column + building for building in data["covered"] for column in (MAX_LEVEL_COLUMN, LEVEL_COLUMN)]
    with open(LOCATIONS_FILE, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["location"] + fact_columns + building_columns)
        for location, facts in data["locations"].items():
            cells = []
            for building in data["covered"]:
                found = facts["buildings"].get(building)
                cells.append(csv_cell(found["max_level"]) if found and found["can_build"] else "")
                cells.append(csv_cell(found["level"]) if found and found["level"] else "")
            writer.writerow([location] + [csv_cell(facts[key]) for key in fact_columns] + cells)
    with open(COUNTRIES_FILE, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["country", "cannot_build"])
        for tag, buildings in sorted(data["cannot_build"].items()):
            writer.writerow([tag, " ".join(buildings)])


def load_game_data():
    """The game data saved in the two CSV files, or None when they are not there."""
    if not (LOCATIONS_FILE.is_file() and COUNTRIES_FILE.is_file()):
        return None
    locations = {}
    with open(LOCATIONS_FILE, encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        covered = [column[len(MAX_LEVEL_COLUMN):] for column in reader.fieldnames if column.startswith(MAX_LEVEL_COLUMN)]
        for row in reader:
            facts = {"buildings": {}}
            for column, cell in row.items():
                if column == "location" or column.startswith((MAX_LEVEL_COLUMN, LEVEL_COLUMN)):
                    continue
                # River sizes are names like 1 or none, the way the river_multiplier list writes them
                facts[column] = cell if column == "river" else read_value(cell)
            for building in covered:
                max_level_cell, level_cell = row[MAX_LEVEL_COLUMN + building], row[LEVEL_COLUMN + building]
                if max_level_cell != "" or level_cell != "":
                    facts["buildings"][building] = {
                        "can_build": max_level_cell != "",
                        "max_level": read_value(max_level_cell) if max_level_cell != "" else None,
                        "level": read_value(level_cell) if level_cell != "" else 0.0,
                    }
            locations[row["location"]] = facts
    cannot_build = {}
    with open(COUNTRIES_FILE, encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            cannot_build[row["country"]] = row["cannot_build"].split()
    return {"covered": covered, "locations": locations, "cannot_build": cannot_build}


def get_game_data():
    """The saved game data, replaced first by a new complete dump from debug.log if there is one."""
    saved = load_game_data()
    log_path = find_debug_log()
    status, dumped = read_dump(log_path) if log_path else ("none", None)

    if status == "complete":
        if saved == dumped:
            return saved, "Using the saved game data (the dump in debug.log is the same)."
        save_game_data(dumped)
        return dumped, f"Read a new dump from {log_path}\nand saved it to {LOCATIONS_FILE.name} and {COUNTRIES_FILE.name}."
    if saved is None:
        if status == "unfinished":
            raise Problem("The dump in debug.log is not finished yet. Let the game run a few more days so it "
                          "writes the rest of the log, then run this again.")
        raise Problem("There is no saved game data yet and no dump in debug.log. "
                      "Make one first: see TO UPDATE THE GAME DATA at the bottom of either settings file.")
    if status == "unfinished":
        return saved, ("debug.log has a dump that is not finished yet, so the saved game data was used.\n"
                       "To use the new dump, let the game run a few more days and run this again.")
    return saved, "Using the saved game data."


# ---------------------------------------------------------------- the setup

def check_list_names(listed, fact_keys):
    """Stops on a name a list uses that the game does not define."""
    choices = {"river_multiplier": RIVER_SIZES, "fixed_level": fact_keys["location_rank"], "base_level_by_location_rank": fact_keys["location_rank"]}
    for setting, fact in LIST_SETTINGS.items():
        if setting not in choices:
            choices[setting] = fact_keys[fact]
    for section_name, setting, name in listed:
        if name not in choices[setting]:
            raise Problem(f'In [{section_name}], {setting} lists "{name}", which the game does not define. Names you can use:\n  '
                          + " ".join(choices[setting]))


def check_pop_types(general, locations):
    """Stops on a pop type the game data does not have, and turns all into every pop type it has."""
    known_pop_types = sorted(key[len("pop_"):] for key in next(iter(locations.values())) if key.startswith("pop_"))
    if "all" in general["pop_types_for_levels"]:
        general["pop_types_for_levels"] = known_pop_types
        return
    for pop_type in general["pop_types_for_levels"]:
        if pop_type not in known_pop_types:
            raise Problem(f'In [general], pop_types_for_levels has "{pop_type}", which is not a pop type. Pop types you can use:\n  ' + " ".join(known_pop_types))


def check_named_locations(locations):
    """Stops on an owned location the dump could not name a fact for."""
    for fact in FACT_FOLDERS:
        unnamed = [location for location, facts in locations.items() if facts["owner"] is not None and facts[fact] == "unknown"]
        if unnamed:
            raise Problem(f"The dump could not name the {fact} of {len(unnamed)} owned locations, for example: {', '.join(unnamed[:5])}.\n"
                          "Make a new dump with the current mod.")


def location_multiplier(rules, facts, pops):
    """final_level_multiplier times every location multiplier that applies to this location."""
    if rules["fixed_level"] is not None:
        # fixed_level replaces steps 1 to 4, the multipliers included
        return 1
    multiplier = rules["final_level_multiplier"]
    if rules["additive_multiplier_per_development"] is not None:
        multiplier *= 1 + facts["development"] * rules["additive_multiplier_per_development"]
    if rules["additive_multiplier_per_population"] is not None:
        multiplier *= 1 + pops * rules["additive_multiplier_per_population"]
    if facts["adjacent_to_lake"] and rules["lake_multiplier"] is not None:
        multiplier *= rules["lake_multiplier"]
    if facts["is_coastal"] and rules["coastal_multiplier"] is not None:
        multiplier *= rules["coastal_multiplier"]
    for setting, fact in LIST_SETTINGS.items():
        # A name the list leaves out counts as 1
        multiplier *= rules[setting].get(facts[fact], 1)
    return multiplier


def round_level(rules, value):
    # Rounded to 6 places first so 2.0000000001 does not round up to 3
    return ROUNDING[rules["round_levels"]](round(value, 6))


def base_level(rules, pops, facts):
    """The base level from pops, development and rank, whichever are set."""
    base = rules["base_level_by_location_rank"].get(facts["location_rank"], 0)
    if rules["peasants_per_level"] is not None:
        base += pops / rules["peasants_per_level"]
    if rules["development_per_level"] is not None:
        base += facts["development"] / rules["development_per_level"]
    return base


def building_level(rules, pops, facts, multiplier, game_max_level, existing):
    """How many levels to add on top of the levels already in the location. 0 means none."""
    if isinstance(rules["fixed_level"], dict):
        # A rank the list leaves out gets no building, whatever the floor says
        if facts["location_rank"] not in rules["fixed_level"]:
            return 0
        added = rules["fixed_level"][facts["location_rank"]]
    elif rules["fixed_level"] is not None:
        added = rules["fixed_level"]
    else:
        added = round_level(rules, base_level(rules, pops, facts) * multiplier)
    # The limits apply to the total, so the levels already there count against them
    total = existing + added
    if rules["fixed_level"] is None and rules["percentage_of_building_max_level"] is not None and game_max_level is not None:
        total = min(total, round_level(rules, game_max_level * rules["percentage_of_building_max_level"] / 100))
    # The floor and ceiling come after the percentage, so they override it
    if rules["fixed_level_floor"] is not None:
        total = max(total, rules["fixed_level_floor"])
    if rules["fixed_level_ceiling"] is not None:
        total = min(total, rules["fixed_level_ceiling"])
    # The game only allows whole levels up to its max, so its max is rounded down
    if game_max_level is not None:
        total = min(total, math.floor(game_max_level))
    return max(total - existing, 0)


def owned_locations(game_data, general, cannot_build):
    """(location, facts, owner, counted pops, building types the owner cannot build) for every location the settings give buildings to."""
    for location, facts in game_data["locations"].items():
        owner = facts["owner"]
        if owner is None or (general["countries"] and owner not in general["countries"]):
            continue
        pops = sum(facts[f"pop_{pop_type}"] for pop_type in general["pop_types_for_levels"])
        blocked = cannot_build.get(owner, set()) if general["respect_technology"] else set()
        yield location, facts, owner, pops, blocked


def existing_levels(facts, building):
    """The levels of the building already in the location at game start."""
    found = facts["buildings"].get(building)
    return int(found["level"] or 0) if found else 0


def settle(lines, counts, removals, settled, rules, facts, owner, location, building, level):
    """Adds the setup line for a building type in a location. With destroy_vanilla_building_levels_before_counting,
    level is the whole level: setup adds what the starting levels lack and the removal effect takes away any above it."""
    existing = existing_levels(facts, building)
    if rules["destroy_vanilla_building_levels_before_counting"]:
        settled.add((location, building))
        added = max(level - existing, 0)
        if existing > level:
            removals[(location, building)] = existing - level
    else:
        added = level
        counts["placed on top of levels already there"] += existing > 0
    if added >= 1:
        lines.append(f"\t{building} = {{ tag = {owner} level = {added} location = {location} }}\n")


def remove_starting_levels_left(game_data, general, rules, cannot_build, removals, settled):
    """A location that gets none of a building type set to destroy_vanilla_building_levels_before_counting loses all its starting levels."""
    destroyed = [building for building, building_rules_here in rules.items() if building_rules_here["destroy_vanilla_building_levels_before_counting"]]
    for location, facts, _, _, _ in owned_locations(game_data, general, cannot_build):
        for building in destroyed:
            existing = existing_levels(facts, building)
            if existing > 0 and (location, building) not in settled:
                removals[(location, building)] = existing


def place_rgo_buildings(game_data, general, rules, cannot_build):
    lines, counts, removals, settled = [], collections.Counter(), {}, set()
    for location, facts, owner, pops, blocked in owned_locations(game_data, general, cannot_build):
        buildable = {building: found["max_level"] for building, found in facts["buildings"].items() if building in rules and found["can_build"]}

        def counted(building):
            # The starting levels only count toward the limits when they are kept
            return 0 if rules[building]["destroy_vanilla_building_levels_before_counting"] else existing_levels(facts, building)

        def place(building, level):
            settle(lines, counts, removals, settled, rules[building], facts, owner, location, building, level)

        # The main building. Its level caps the secondary buildings even where it cannot be built or is not placed.
        main_building = RGO_PREFIX + str(facts["raw_material"])
        main_level = 0
        if main_building in rules:
            # The main building is the ideal RGO building for the location's raw material
            ideal_multiplier = location_multiplier(rules[main_building], facts, pops) * rules[main_building]["ideal_rgo_multiplier"]
            main_level = building_level(rules[main_building], pops, facts, ideal_multiplier, facts["main_rgo_max_level"], counted(main_building))
            if rules[main_building]["place"] and main_level >= 1:
                if main_building in blocked:
                    counts["main buildings skipped by technology"] += 1
                elif main_building not in buildable:
                    counts["main buildings that cannot be built there"] += 1
                else:
                    place(main_building, main_level)
                    counts["main buildings"] += 1

        if not general["place_secondary_rgos"]:
            continue
        # Every other RGO building gets its own level, kept at least one level below the main building's
        candidates = []
        for building in buildable:
            if building == main_building or not rules[building]["place"] or not rules[building]["place_as_secondary"] or building in blocked:
                continue
            multiplier = location_multiplier(rules[building], facts, pops)
            level = min(building_level(rules[building], pops, facts, multiplier, buildable[building], counted(building)), main_level - 1)
            if level >= 1:
                # Picked by the level before rounding and limits, so the multipliers decide between buildings that round to the same level
                fixed = rules[building]["fixed_level"]
                unrounded = level if fixed is not None else base_level(rules[building], pops, facts) * multiplier
                candidates.append((building, level, unrounded))
        # The largest come first, then the highest secondary_priority, then the key in alphabetical order. Nothing is random.
        candidates.sort(key=lambda candidate: (-candidate[2], -rules[candidate[0]]["secondary_priority"], candidate[0]))
        for building, level, _ in candidates[:general["max_secondary_rgos_per_location"]]:
            place(building, level)
            counts["secondary buildings"] += 1
    remove_starting_levels_left(game_data, general, rules, cannot_build, removals, settled)
    return lines, counts, removals


def group_member_room(rules, game_max_level, counted):
    """How many levels a building type in a distribution group can still take, or None when nothing limits it."""
    limits = []
    if rules["fixed_level"] is None and rules["percentage_of_building_max_level"] is not None and game_max_level is not None:
        limits.append(round_level(rules, game_max_level * rules["percentage_of_building_max_level"] / 100))
    if game_max_level is not None:
        limits.append(math.floor(game_max_level))
    return max(min(limits) - counted, 0) if limits else None


def place_other_buildings(game_data, general, rules, groups, cannot_build):
    """Every building type with a section in every owned location that can build it, and every distribution group."""
    lines, counts, removals, settled = [], collections.Counter(), {}, set()
    grouped = {member for members in groups.values() for member in members}
    for location, facts, owner, pops, blocked in owned_locations(game_data, general, cannot_build):
        for group, members in groups.items():
            if not rules[group]["place"]:
                continue
            # Each building type in the group the location can build, with the levels its own limits still allow
            choices = []
            for member in members:
                found = facts["buildings"].get(member)
                if not rules[member]["place"] or not found or not found["can_build"]:
                    continue
                if member in blocked:
                    counts[f"{member} skipped by technology"] += 1
                    continue
                counted = 0 if rules[member]["destroy_vanilla_building_levels_before_counting"] else existing_levels(facts, member)
                choices.append({"building": member, "counted": counted, "room": group_member_room(rules[member], found["max_level"], counted), "added": 0})
            if not choices:
                continue
            # The group's level counts the levels already there, like a single building type's would
            left = building_level(rules[group], pops, facts, location_multiplier(rules[group], facts, pops), None, 0) - sum(choice["counted"] for choice in choices)
            # One level at a time to each building type in the group's order, skipping any at its limit, until the group's level runs out
            while left > 0:
                open_choices = [choice for choice in choices if choice["room"] is None or choice["added"] < choice["room"]]
                if not open_choices:
                    break
                for choice in open_choices[:left]:
                    choice["added"] += 1
                left -= min(left, len(open_choices))
            counts[f"{group} levels no building had room for"] += max(left, 0)
            for choice in choices:
                if choice["added"] >= 1:
                    settle(lines, counts, removals, settled, rules[choice["building"]], facts, owner, location, choice["building"], choice["added"])
                    counts[choice["building"]] += 1

        for building, building_rules_here in rules.items():
            if building in groups or building in grouped:
                continue
            found = facts["buildings"].get(building)
            if not building_rules_here["place"] or not found or not found["can_build"]:
                continue
            # The starting levels only count toward the limits when they are kept
            counted = 0 if building_rules_here["destroy_vanilla_building_levels_before_counting"] else existing_levels(facts, building)
            level = building_level(building_rules_here, pops, facts, location_multiplier(building_rules_here, facts, pops), found["max_level"], counted)
            if level < 1:
                continue
            if building in blocked:
                counts[f"{building} skipped by technology"] += 1
                continue
            settle(lines, counts, removals, settled, building_rules_here, facts, owner, location, building, level)
            counts[building] += 1
    remove_starting_levels_left(game_data, general, rules, cannot_build, removals, settled)
    return lines, counts, removals


def removals_effect_text(removals):
    lines = [
        "# GENERATED by tools/generators_from_game_data/generators/building_setup/building_setup.py from destroy_vanilla_building_levels_before_counting.",
        "# Do not edit by hand. Runs at game start through mnt_building_setup_removals_on_start in on_game_start (MnT_pulse.txt).",
        "mnt_remove_starting_building_levels = {",
    ]
    for (location, building), levels in sorted(removals.items()):
        lines.append(f"\tlocation:{location} = {{ change_building_level_in_location = {{ building = building_type:{building} value = -{levels} }} }}")
    lines += ["}", ""]
    return "\n".join(lines)


def write_removals_effect(text):
    if REMOVALS_EFFECT_FILE.is_file() and REMOVALS_EFFECT_FILE.read_text(encoding="utf-8-sig") == text:
        return
    # Script files need a BOM
    REMOVALS_EFFECT_FILE.write_text(text, encoding="utf-8-sig", newline="\n")


def write_setup_file(path, settings_file, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Setup files can't carry a BOM, so write plain UTF-8 bytes
    path.write_bytes((
        "# GENERATED by tools/generators_from_game_data/generators/building_setup/building_setup.py.\n"
        f"# Do not edit by hand. Change {settings_file.name} next to that script and run it again.\n"
        "building_manager = {\n" + "".join(lines) + "}\n"
    ).encode("utf-8"))


def main():
    rgo_general = in_file(RGO_SETTINGS_FILE, lambda: read_general(read_settings_file(RGO_SETTINGS_FILE), RGO_GENERAL_SETTINGS))
    other_general = in_file(BUILDING_SETTINGS_FILE, lambda: read_general(read_settings_file(BUILDING_SETTINGS_FILE), BUILDING_GENERAL_SETTINGS))
    game = find_game_folder()
    max_levels = read_building_max_levels(game)
    rgo_sections = in_file(RGO_SETTINGS_FILE, lambda: name_sections(read_settings_file(RGO_SETTINGS_FILE), max_levels, True))
    other_sections = in_file(BUILDING_SETTINGS_FILE, lambda: name_sections(read_settings_file(BUILDING_SETTINGS_FILE), max_levels, False))

    # Every RGO building can be placed; other building types only when they have a section
    rgo_placeable = sorted(key for key in max_levels if key.startswith(RGO_PREFIX))
    other_groups, group_of = in_file(BUILDING_SETTINGS_FILE, distribution_groups, other_sections, max_levels)
    other_placeable = sorted({name for name in other_sections if name in max_levels} | set(group_of))
    keys_by_lower = {key.lower(): key for key in max_levels}
    unknown = [name for name in other_general["report_building_types"] if name.lower() not in keys_by_lower]
    if unknown:
        raise Problem(f"{BUILDING_SETTINGS_FILE.name}: In [general], report_building_types has " + ", ".join(unknown)
                      + ", which is not a building type in the mod or the game.")
    # The dump also reports the building types in report_building_types, without placing them
    placeable = rgo_placeable + other_placeable
    covered = placeable + sorted({keys_by_lower[name.lower()] for name in other_general["report_building_types"]} - set(placeable))
    rgo_rules, rgo_listed = in_file(RGO_SETTINGS_FILE, building_rules, rgo_sections, rgo_placeable, RGO_DEFAULT_SECTION)
    other_rules, other_listed = in_file(BUILDING_SETTINGS_FILE, building_rules, other_sections, other_placeable + sorted(other_groups),
                                        BUILDING_DEFAULT_SECTION, group_of)

    fact_keys = {fact: read_definition_keys(game, folder) for fact, folder in FACT_FOLDERS.items()}
    dump_note = write_dump_effect(dump_effect_text(covered, max_levels, read_can_extract_goods(game), fact_keys,
                                                   read_definition_keys(game, "pop_types")))
    if dump_note:
        print(dump_note)

    game_data, data_note = get_game_data()
    missing = [building for building in covered if building not in game_data["covered"]]
    if missing:
        raise Problem("The game data has nothing yet for " + ", ".join(missing) + ".\n"
                      "The dump effect covers them now, so make a new dump: see TO UPDATE THE GAME DATA at the bottom of either settings file.")
    in_file(RGO_SETTINGS_FILE, check_list_names, rgo_listed, fact_keys)
    in_file(BUILDING_SETTINGS_FILE, check_list_names, other_listed, fact_keys)
    in_file(RGO_SETTINGS_FILE, check_pop_types, rgo_general, game_data["locations"])
    in_file(BUILDING_SETTINGS_FILE, check_pop_types, other_general, game_data["locations"])
    check_named_locations(game_data["locations"])
    cannot_build = {tag: set(buildings) for tag, buildings in game_data["cannot_build"].items()}

    rgo_lines, rgo_counts, rgo_removals = place_rgo_buildings(game_data, rgo_general, rgo_rules, cannot_build)
    other_lines, other_counts, other_removals = place_other_buildings(game_data, other_general, other_rules, other_groups, cannot_build)
    write_setup_file(RGO_OUTPUT_FILE, RGO_SETTINGS_FILE, rgo_lines)
    write_setup_file(BUILDING_OUTPUT_FILE, BUILDING_SETTINGS_FILE, other_lines)
    removals = {**rgo_removals, **other_removals}
    write_removals_effect(removals_effect_text(removals))

    print(data_note)
    print(f"Wrote {len(rgo_lines)} RGO buildings to {shown_path(RGO_OUTPUT_FILE)}")
    for label in ("main buildings", "secondary buildings", "main buildings skipped by technology", "placed on top of levels already there"):
        print(f"  {label + ':':<40}{rgo_counts[label]}")
    print(f"Wrote {len(other_lines)} other buildings to {shown_path(BUILDING_OUTPUT_FILE)}")
    for label, count in sorted(other_counts.items()):
        print(f"  {label + ':':<40}{count}")
    print(f"Wrote {len(removals)} removals of starting levels, {sum(removals.values())} levels in all, to {shown_path(REMOVALS_EFFECT_FILE)}")


if __name__ == "__main__":
    try:
        main()
    except Problem as problem:
        print(f"\nPROBLEM: {problem}\n")
        sys.exit(1)
