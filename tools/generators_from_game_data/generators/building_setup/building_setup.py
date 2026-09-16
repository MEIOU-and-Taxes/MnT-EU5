"""
BUILDING SETUP GENERATOR

Reads two settings files (rgo_setup_settings.txt and building_setup_settings.txt) and writes setup
files that place buildings in owned locations at game start. The settings control which buildings go
where and at what level; the game data (CSV files next to this script) tells the generator what each
location looks like. Nothing in this script needs editing; change the settings files instead.

The game data comes from a dump effect this script also generates. The dump runs once at game start,
reports every location's pops, terrain and buildable buildings to debug.log, and the generator saves
that to CSV. The CSV is reused until a patch or mod change invalidates it; --setup-data-dump starts
that refresh cycle. See the settings file headers for the steps.
"""

import argparse
import collections
import csv
import math
import re
import sys
from pathlib import Path

SCRIPT_FOLDER = Path(__file__).resolve().parent
MOD_FOLDER = SCRIPT_FOLDER.parents[3]

# The mod's folder has to be importable before the shared tools are, whatever folder this is run from
sys.path.insert(0, str(MOD_FOLDER))
from tools.shared.fetch_logs import CONFIG_FILE, get_from_config  # noqa: E402
RGO_SETTINGS_FILE = SCRIPT_FOLDER / "rgo_setup_settings.txt"
BUILDING_SETTINGS_FILE = SCRIPT_FOLDER / "building_setup_settings.txt"
LOCATIONS_FILE = SCRIPT_FOLDER / "building_setup_locations.csv"
COUNTRIES_FILE = SCRIPT_FOLDER / "building_setup_countries.csv"
# CSV column prefixes: each building type has a max_level (what the game caps it at) and a level (what it starts with)
MAX_LEVEL_COLUMN = "max_level_"
LEVEL_COLUMN = "level_"
RGO_OUTPUT_FILE = MOD_FOLDER / "main_menu" / "setup" / "start" / "98_mnt_rgo_setup.txt"
BUILDING_OUTPUT_FILE = MOD_FOLDER / "main_menu" / "setup" / "start" / "98_mnt_building_setup.txt"
DUMP_EFFECT_FILE = MOD_FOLDER / "in_game" / "common" / "scripted_effects" / "MnT_setup_generated_loc_data_dump.txt"
REMOVALS_EFFECT_FILE = MOD_FOLDER / "in_game" / "common" / "scripted_effects" / "MnT_setup_generated_building_removals.txt"

DUMP_PREFIX = "MNT_RGO_DUMP "
# Raised whenever the dump's records change, so an older dump in debug.log is not read
DUMP_VERSION = 6
RGO_PREFIX = "RGO_building_"

# The [general] settings each settings file takes
RGO_GENERAL_SETTINGS = [
    "countries", "pop_types_for_levels", "respect_technology", "place_secondary_rgos", "max_secondary_rgos_per_location",
]
BUILDING_GENERAL_SETTINGS = ["countries", "report_building_types", "pop_types_for_levels", "respect_technology"]
# [general] settings that may be left out or set to None
OPTIONAL_SETTINGS = {"countries", "report_building_types"}
# Each multiplier setting maps to the location fact it looks up
LIST_SETTINGS = {
    "river_multiplier": "river",
    "location_rank_multiplier": "location_rank",
    "topography_multiplier": "topography",
    "vegetation_multiplier": "vegetation",
    "climate_multiplier": "climate",
}
RIVER_SIZES = ["none", "1", "2", "3", "4", "5"]
# Where the game defines each location fact, so the generator can read the valid keys
FACT_FOLDERS = {"topography": "topography", "vegetation": "vegetation", "climate": "climates", "location_rank": "location_ranks"}
# The trigger syntax the dump uses to identify each fact; location_rank needs a prefix, the others do not
FACT_CHECKS = {
    "topography": "topography = {key}",
    "vegetation": "vegetation = {key}",
    "climate": "climate = {key}",
    "location_rank": "location_rank = location_rank:{key}",
}
# Setting names grouped by role in the level calculation. fixed_level is an alternative to the
# base+multiplier pipeline; when it is set, the pipeline settings are ignored.
BASE_LEVEL_SETTINGS = ["pops_per_level", "development_per_level", "base_level_by_location_rank"]
POP_STEP_SETTINGS = (BASE_LEVEL_SETTINGS + ["final_level_multiplier", "additive_multiplier_per_development", "additive_multiplier_per_population",
                                            "lake_multiplier", "coastal_multiplier"]
                     + list(LIST_SETTINGS) + ["round_levels", "percentage_of_building_max_level"])
LEVEL_SETTINGS = POP_STEP_SETTINGS + ["fixed_level", "fixed_level_floor", "fixed_level_ceiling"]
# Which settings are valid in each kind of section, used to catch typos and misplaced settings
RGO_BUILDING_SETTINGS = ["place", "place_as_secondary", "secondary_priority", "ideal_rgo_multiplier", "destroy_vanilla_building_levels_before_counting"] + LEVEL_SETTINGS
OTHER_BUILDING_SETTINGS = ["place", "destroy_vanilla_building_levels_before_counting"] + LEVEL_SETTINGS
# A building in a distribution group gets its level from the group, so it can only set its own limits
GROUP_SETTING = "distribution_group"
GROUP_SETTINGS = [GROUP_SETTING] + OTHER_BUILDING_SETTINGS
GROUP_MEMBER_SETTINGS = ["place", "destroy_vanilla_building_levels_before_counting", "round_levels", "percentage_of_building_max_level"]
NEW_DUMP_HINT = ("To make one, run this script with --setup-data-dump, start a new game, close it once the "
                 "country selection screen shows, and run this script again.")
# Section names for error messages and lookup
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
# Parsing the settings files. They use a simple ini-like format (sections, key = value pairs, # comments)
# with multi-line values for lists and maps. Each parser returns a typed Python value and raises
# Problem with the section name and setting name on anything it cannot read.

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
    """Maps each section name to a building type key, the default section, or a distribution group.
    Validates that every section name is something the game recognizes and that its settings are valid."""
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


def filled(sections, section_name, key):
    """Whether a section gives the setting a value, rather than leaving it out or setting it to None."""
    return section_name in sections and sections[section_name].get(key, "").strip().lower() not in ("", "none")


def check_conflicting_settings(sections):
    """Stops on a section that sets fixed_level as well as the settings fixed_level replaces."""
    for section_name in sections:
        if section_name == "general" or not filled(sections, section_name, "fixed_level"):
            continue
        replaced = [key for key in POP_STEP_SETTINGS if filled(sections, section_name, key)]
        if replaced:
            raise Problem(f"In [{shown(section_name)}], fixed_level cannot be used together with {' and '.join(replaced)}: "
                          "fixed_level gives the level directly, so steps 1 to 3 would do nothing. Set one side to None.")


def listed_names(sections):
    """(section, setting, name) for every name the lists use, checked against the game's definitions later."""
    listed = []
    for section_name, section in sections.items():
        if section_name == "general":
            continue
        where = shown(section_name)
        for setting in LIST_SETTINGS:
            listed += [(where, setting, name) for name in read_multipliers(where, setting, section.get(setting, ""))]
        for setting in ("fixed_level", "base_level_by_location_rank"):
            if section.get(setting, "").strip().startswith("{"):
                listed += [(where, setting, name) for name in read_multipliers(where, setting, section[setting])]
    return listed


class SectionChain:
    """The sections one building type reads its settings from, nearest first: its own section, then its
    distribution group's, then the default section. The nearest section that has a setting decides, so
    None in a building type's own section turns that setting off for it."""

    def __init__(self, sections, building, default_section, group_of):
        self.sections = sections
        self.building = building
        self.default_section = default_section
        self.chain = (([building] if building in sections else [])
                      + ([group_of[building]] if building in group_of else [])
                      + [default_section])
        self.not_used = self.settings_turned_off()

    def settings_turned_off(self):
        """fixed_level replaces the settings that work a level out from the location, so the nearest section to
        set either side decides which side this building type uses. With neither set, fixed_level is dropped."""
        for section_name in self.chain:
            if filled(self.sections, section_name, "fixed_level"):
                return set(POP_STEP_SETTINGS)
            if any(filled(self.sections, section_name, key) for key in POP_STEP_SETTINGS):
                return {"fixed_level"}
        return {"fixed_level"}

    def where(self, key):
        return next((name for name in self.chain if key in self.sections.get(name, {})), self.default_section)

    def text(self, key):
        return "" if key in self.not_used else self.sections[self.where(key)].get(key, "").strip()

    def yes_no(self, key):
        if self.text(key) == "":
            raise Problem(f"[{shown(self.default_section)}] needs {key} = yes or no.")
        return read_yes_no(shown(self.where(key)), key, self.text(key))

    def number(self, key, required=False, **rules):
        value = read_number(shown(self.where(key)), key, self.text(key), **rules)
        if value is None and required:
            raise Problem(f"[{self.building}] has no {key}. Fill it in under [{shown(self.default_section)}], "
                          "or use fixed_level instead of steps 1 to 3.")
        return value

    def multipliers(self, key):
        """Merges multiplier maps down the chain. When two sections name the same key, the nearer one wins.
        None in a section drops all maps below it."""
        if key in self.not_used:
            return {}
        used = []
        for section_name in self.chain:
            if key in self.sections.get(section_name, {}):
                if not filled(self.sections, section_name, key):
                    break
                used.append(section_name)
        merged = {}
        for section_name in reversed(used):
            merged.update(read_multipliers(shown(section_name), key, self.sections[section_name][key]))
        return merged

    def fixed_level(self):
        """One whole number for every location, or a list of whole numbers by location rank."""
        text = self.text("fixed_level")
        if not text.startswith("{"):
            return self.number("fixed_level", whole=True)
        levels = read_multipliers(shown(self.where("fixed_level")), "fixed_level", text)
        for rank, level in levels.items():
            if level != int(level):
                raise Problem(f"In [{shown(self.where('fixed_level'))}], fixed_level for {rank} must be a whole number, but it is {level:g}.")
        return {rank: int(level) for rank, level in levels.items()}

    def rounding(self, uses_pop_steps):
        round_levels = self.text("round_levels").lower() if uses_pop_steps else "down"
        if round_levels not in ROUNDING:
            raise Problem(f'In [{shown(self.where("round_levels"))}], round_levels must be up, down or nearest, but it is "{round_levels}".')
        return round_levels


def building_rules(sections, placeable, default_section, group_of=None):
    """Resolves the inheritance chain for each building type into a flat dict of final settings.
    Also collects every name used in multiplier maps so they can be checked against the game later."""
    group_of = group_of or {}
    check_conflicting_settings(sections)

    rules_by_building = {}
    for building in placeable:
        chain = SectionChain(sections, building, default_section, group_of)
        uses_pop_steps = "fixed_level" in chain.not_used
        rules = {
            "place": chain.yes_no("place"),
            "destroy_vanilla_building_levels_before_counting": chain.yes_no("destroy_vanilla_building_levels_before_counting"),
            "pops_per_level": chain.number("pops_per_level", above_zero=True),
            "development_per_level": chain.number("development_per_level", above_zero=True),
            "base_level_by_location_rank": chain.multipliers("base_level_by_location_rank"),
            "final_level_multiplier": chain.number("final_level_multiplier", required=uses_pop_steps),
            "additive_multiplier_per_development": chain.number("additive_multiplier_per_development"),
            "additive_multiplier_per_population": chain.number("additive_multiplier_per_population"),
            "lake_multiplier": chain.number("lake_multiplier"),
            "coastal_multiplier": chain.number("coastal_multiplier"),
            **{setting: chain.multipliers(setting) for setting in LIST_SETTINGS},
            "round_levels": chain.rounding(uses_pop_steps),
            "percentage_of_building_max_level": chain.number("percentage_of_building_max_level"),
            "fixed_level": chain.fixed_level(),
            "fixed_level_floor": chain.number("fixed_level_floor", whole=True),
            "fixed_level_ceiling": chain.number("fixed_level_ceiling", whole=True),
        }
        # A building type in a distribution group gets its level from the group
        if (uses_pop_steps and rules["place"] and building not in group_of and rules["pops_per_level"] is None
                and rules["development_per_level"] is None and not rules["base_level_by_location_rank"]):
            raise Problem(f"[{building}] has no base level. Fill in pops_per_level, development_per_level or base_level_by_location_rank, "
                          f"or use fixed_level instead of steps 1 to 3.")
        if default_section == RGO_DEFAULT_SECTION:
            rules["place_as_secondary"] = chain.yes_no("place_as_secondary")
            rules["secondary_priority"] = chain.number("secondary_priority") or 0
            ideal_rgo_multiplier = chain.number("ideal_rgo_multiplier")
            rules["ideal_rgo_multiplier"] = 1 if ideal_rgo_multiplier is None else ideal_rgo_multiplier
        rules_by_building[building] = rules
    return rules_by_building, listed_names(sections)


# ------------------------------------------------------------- game files
# Reading the vanilla game and mod definitions to learn what building types exist, what their max
# levels are, and what location facts (topography, vegetation, climate, rank) the game defines.
# Mod files override vanilla files of the same name, matching how the engine loads them.

def find_game_folder():
    """The game's 'game' folder, from game_directory in the shared config. Either the folder itself or its
    parent is accepted, since the setting is written both ways."""
    configured = Path(get_from_config("Paths", "game_directory")).expanduser()
    for game in (configured, configured / "game"):
        if (game / "in_game" / "common" / "building_types").is_dir():
            return game
    raise Problem(f"game_directory points to\n  {configured}\nbut the game is not there. Fix it here:\n  {CONFIG_FILE}")


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
# Generates the pdx-script effect that runs at game start and writes location data to debug.log.
# The generator cannot read the game's binary state directly, so it gets the game to report it:
# each location's pops, terrain, buildable buildings and their max levels, all as parseable log lines.

def dump_effect_text(covered, max_levels, can_extract_goods, fact_keys, pop_types, making_game_data=False):
    """Builds the full scripted effect as a string. The effect iterates every owned location and
    logs its facts, then iterates every country to log which buildings it lacks the technology for."""
    local = lambda name, decimals: f"[SCOPE.GetLocalVariable('mnt_rgo_dump_{name}').GetValue|{decimals}]"
    lines = [
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
              "\twhile = {", "\t\tcount = 1000", f'\t\tdebug_log = "{FILLER_LINE}"', "\t}"]
    # on_game_start always calls this effect, so the gate below is what decides whether it reports anything
    return "\n".join([
        "# GENERATED by tools/generators_from_game_data/generators/building_setup/building_setup.py for the building types its settings cover.",
        "# Do not edit by hand. Runs at game start through mnt_rgo_setup_dump_on_start in on_game_start (MnT_pulse.txt).",
        "mnt_rgo_setup_dump = {",
        "\tif = {",
        f"\t\tlimit = {{ always = {'yes' if making_game_data else 'no'} }} # yes only between a --setup-data-dump run and the run that reads the dump",
    ] + [f"\t{line}" if line else "" for line in lines] + ["\t}", "}", ""])


def write_script_file(path, text):
    """Writes a generated script file when it changed, and says whether it did. Script files need a BOM."""
    if path.is_file() and path.read_text(encoding="utf-8-sig") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig", newline="\n")
    return True


def clear_setup_for_new_game_data():
    """Takes away the three files this script writes, so the dump reports a game start without them."""
    for path in (RGO_OUTPUT_FILE, BUILDING_OUTPUT_FILE, REMOVALS_EFFECT_FILE):
        if path.is_file():
            path.unlink()
            print(f"Deleted {shown_path(path)}")
    print(f"\nThe dump in {shown_path(DUMP_EFFECT_FILE)} is on and now runs at game start.\n"
          "Deploy the mod, start a new game, and close it once the country selection screen shows.\n"
          "Then run this script again. It reads the dump, writes the three files back and turns the dump off.")


# ----------------------------------------------------------------- game data
# Loading the location and country data the generator works from. The data lives in two CSV files
# saved next to the script. When debug.log has a newer complete dump, the CSVs are replaced.
# This lets the generator run without starting the game every time.

def find_debug_log():
    """The debug.log to look for a new dump in, from log_directory in the shared config. None when the folder
    is there but holds no debug.log yet, so the saved game data is used instead."""
    configured = Path(get_from_config("Paths", "log_directory")).expanduser()
    if not configured.exists():
        raise Problem(f"log_directory points to\n  {configured}\nwhich is not there. Fix it here:\n  {CONFIG_FILE}")
    path = configured / "debug.log" if configured.is_dir() else configured
    return path if path.is_file() else None


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
            raise Problem("The dump in debug.log was made with an older version of the dump effect. " + NEW_DUMP_HINT)
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
        raise Problem("There is no saved game data yet and no dump in debug.log. " + NEW_DUMP_HINT)
    if status == "unfinished":
        return saved, ("debug.log has a dump that is not finished yet, so the saved game data was used.\n"
                       "To use the new dump, let the game run a few more days and run this again.")
    return saved, "Using the saved game data."


# ---------------------------------------------------------------- the setup
# Calculating building levels and writing the setup files. For each owned location, the generator
# works out a level from the settings (base level from pops/dev/rank, multiplied by terrain and
# other factors, then clamped), and emits a setup line that the game reads at start. Buildings
# whose vanilla starting levels are being replaced also get a removal effect that strips the old levels.

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
    if rules["pops_per_level"] is not None:
        base += pops / rules["pops_per_level"]
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
    """Yields each owned location that the settings apply to, with its facts, owner, counted pops
    and the building types the owner lacks the technology for."""
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


class Placement:
    """Collects the setup lines, the level removals and the counts while buildings are placed."""

    def __init__(self, rules):
        self.rules = rules
        self.lines = []
        self.counts = collections.Counter()
        self.removals = {}
        self.settled = set()

    def counted_levels(self, facts, building):
        """The starting levels that count toward the limits. None of them count when they are about to be removed."""
        if self.rules[building]["destroy_vanilla_building_levels_before_counting"]:
            return 0
        return existing_levels(facts, building)

    def settle(self, facts, owner, location, building, level):
        """Adds the setup line for a building type in a location. With destroy_vanilla_building_levels_before_counting,
        level is the whole level: setup adds what the starting levels lack and the removal effect takes away any above it."""
        existing = existing_levels(facts, building)
        if self.rules[building]["destroy_vanilla_building_levels_before_counting"]:
            self.settled.add((location, building))
            added = max(level - existing, 0)
            if existing > level:
                self.removals[(location, building)] = existing - level
        else:
            added = level
            self.counts["placed on top of levels already there"] += existing > 0
        if added >= 1:
            self.lines.append(f"\t{building} = {{ tag = {owner} level = {added} location = {location} }}\n")

    def strip_untouched_locations(self, game_data, general, cannot_build):
        """A location that gets none of a building type set to destroy_vanilla_building_levels_before_counting
        loses all its starting levels."""
        destroyed = [building for building, rules in self.rules.items() if rules["destroy_vanilla_building_levels_before_counting"]]
        for location, facts, _, _, _ in owned_locations(game_data, general, cannot_build):
            for building in destroyed:
                existing = existing_levels(facts, building)
                if existing > 0 and (location, building) not in self.settled:
                    self.removals[(location, building)] = existing
        return self.lines, self.counts, self.removals


def place_rgo_buildings(game_data, general, rules, cannot_build):
    """Places the main RGO building (matching the location's raw material, boosted by ideal_rgo_multiplier)
    and then picks the best secondary RGO buildings, each capped one level below the main."""
    setup = Placement(rules)
    for location, facts, owner, pops, blocked in owned_locations(game_data, general, cannot_build):
        buildable = {building: found["max_level"] for building, found in facts["buildings"].items() if building in rules and found["can_build"]}

        # The main building. Its level caps the secondary buildings even where it cannot be built or is not placed.
        main_building = RGO_PREFIX + str(facts["raw_material"])
        main_level = 0
        if main_building in rules:
            # The main building is the ideal RGO building for the location's raw material
            ideal_multiplier = location_multiplier(rules[main_building], facts, pops) * rules[main_building]["ideal_rgo_multiplier"]
            main_level = building_level(rules[main_building], pops, facts, ideal_multiplier, facts["main_rgo_max_level"],
                                        setup.counted_levels(facts, main_building))
            if rules[main_building]["place"] and main_level >= 1:
                if main_building in blocked:
                    setup.counts["main buildings skipped by technology"] += 1
                elif main_building not in buildable:
                    setup.counts["main buildings that cannot be built there"] += 1
                else:
                    setup.settle(facts, owner, location, main_building, main_level)
                    setup.counts["main buildings"] += 1

        if not general["place_secondary_rgos"]:
            continue
        # Every other RGO building gets its own level, kept at least one level below the main building's
        candidates = []
        for building in buildable:
            if building == main_building or not rules[building]["place"] or not rules[building]["place_as_secondary"] or building in blocked:
                continue
            multiplier = location_multiplier(rules[building], facts, pops)
            level = min(building_level(rules[building], pops, facts, multiplier, buildable[building],
                                       setup.counted_levels(facts, building)), main_level - 1)
            if level >= 1:
                # Picked by the level before rounding and limits, so the multipliers decide between buildings that round to the same level
                fixed = rules[building]["fixed_level"]
                unrounded = level if fixed is not None else base_level(rules[building], pops, facts) * multiplier
                candidates.append((building, level, unrounded))
        # The largest come first, then the highest secondary_priority, then the key in alphabetical order. Nothing is random.
        candidates.sort(key=lambda candidate: (-candidate[2], -rules[candidate[0]]["secondary_priority"], candidate[0]))
        for building, level, _ in candidates[:general["max_secondary_rgos_per_location"]]:
            setup.settle(facts, owner, location, building, level)
            setup.counts["secondary buildings"] += 1
    return setup.strip_untouched_locations(game_data, general, cannot_build)


def group_member_room(rules, game_max_level, counted):
    """How many levels a building type in a distribution group can still take, or None when nothing limits it."""
    limits = []
    if rules["fixed_level"] is None and rules["percentage_of_building_max_level"] is not None and game_max_level is not None:
        limits.append(round_level(rules, game_max_level * rules["percentage_of_building_max_level"] / 100))
    if game_max_level is not None:
        limits.append(math.floor(game_max_level))
    return max(min(limits) - counted, 0) if limits else None


def place_other_buildings(game_data, general, rules, groups, cannot_build):
    """Places non-RGO buildings. Distribution groups are handled first: the group's level is split
    round-robin among its members. Standalone building types are placed individually after."""
    setup = Placement(rules)
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
                    setup.counts[f"{member} skipped by technology"] += 1
                    continue
                counted = setup.counted_levels(facts, member)
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
            setup.counts[f"{group} levels no building had room for"] += max(left, 0)
            for choice in choices:
                if choice["added"] >= 1:
                    setup.settle(facts, owner, location, choice["building"], choice["added"])
                    setup.counts[choice["building"]] += 1

        for building, building_rules_here in rules.items():
            if building in groups or building in grouped:
                continue
            found = facts["buildings"].get(building)
            if not building_rules_here["place"] or not found or not found["can_build"]:
                continue
            level = building_level(building_rules_here, pops, facts, location_multiplier(building_rules_here, facts, pops),
                                   found["max_level"], setup.counted_levels(facts, building))
            if level < 1:
                continue
            if building in blocked:
                setup.counts[f"{building} skipped by technology"] += 1
                continue
            setup.settle(facts, owner, location, building, level)
            setup.counts[building] += 1
    return setup.strip_untouched_locations(game_data, general, cannot_build)


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


def write_setup_file(path, settings_file, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Setup files can't carry a BOM, so write plain UTF-8 bytes
    path.write_bytes((
        "# GENERATED by tools/generators_from_game_data/generators/building_setup/building_setup.py.\n"
        f"# Do not edit by hand. Change {settings_file.name} next to that script and run it again.\n"
        "building_manager = {\n" + "".join(lines) + "}\n"
    ).encode("utf-8"))


class SettingsFile:
    """One settings file, read once: its [general] settings, its sections keyed by building type, and the
    rules those sections give each building type. Every problem it raises names the file."""

    def __init__(self, path, general_settings, for_rgo_buildings):
        self.path = path
        self.for_rgo_buildings = for_rgo_buildings
        self.text_sections = self.check(read_settings_file, path)
        self.general = self.check(read_general, self.text_sections, general_settings)
        self.groups, self.group_of = {}, {}

    def check(self, function, *arguments):
        return in_file(self.path, function, *arguments)

    def read_sections(self, max_levels):
        self.sections = self.check(name_sections, self.text_sections, max_levels, self.for_rgo_buildings)
        if not self.for_rgo_buildings:
            self.groups, self.group_of = self.check(distribution_groups, self.sections, max_levels)

    def read_rules(self, placeable, default_section):
        """placeable is every building type this file places, its distribution groups included."""
        self.placeable = placeable
        self.rules, self.listed = self.check(building_rules, self.sections, placeable, default_section, self.group_of)


def main(making_game_data=False):
    """Orchestrates the full pipeline: read settings, read game definitions, update the dump effect,
    load game data, calculate levels and write the setup files."""

    # Read both settings files and learn what building types exist in the game
    rgo = SettingsFile(RGO_SETTINGS_FILE, RGO_GENERAL_SETTINGS, for_rgo_buildings=True)
    other = SettingsFile(BUILDING_SETTINGS_FILE, BUILDING_GENERAL_SETTINGS, for_rgo_buildings=False)
    game = find_game_folder()
    max_levels = read_building_max_levels(game)
    rgo.read_sections(max_levels)
    other.read_sections(max_levels)

    # Decide which building types to place and which to just report in the dump
    rgo_placeable = sorted(key for key in max_levels if key.startswith(RGO_PREFIX))
    other_placeable = sorted({name for name in other.sections if name in max_levels} | set(other.group_of))
    keys_by_lower = {key.lower(): key for key in max_levels}
    unknown = [name for name in other.general["report_building_types"] if name.lower() not in keys_by_lower]
    if unknown:
        raise Problem(f"{BUILDING_SETTINGS_FILE.name}: In [general], report_building_types has " + ", ".join(unknown)
                      + ", which is not a building type in the mod or the game.")
    placeable = rgo_placeable + other_placeable
    covered = placeable + sorted({keys_by_lower[name.lower()] for name in other.general["report_building_types"]} - set(placeable))
    rgo.read_rules(rgo_placeable, RGO_DEFAULT_SECTION)
    other.read_rules(other_placeable + sorted(other.groups), BUILDING_DEFAULT_SECTION)

    # Update the dump effect to cover whatever building types the settings mention
    fact_keys = {fact: read_definition_keys(game, folder) for fact, folder in FACT_FOLDERS.items()}
    dump_note = write_script_file(DUMP_EFFECT_FILE,
                                  dump_effect_text(covered, max_levels, read_can_extract_goods(game), fact_keys,
                                                   read_definition_keys(game, "pop_types"), making_game_data))
    if making_game_data:
        clear_setup_for_new_game_data()
        return
    if dump_note:
        print(f"Updated {shown_path(DUMP_EFFECT_FILE)} for the building types the settings cover.\n"
              "The game data itself only changes after a new dump. " + NEW_DUMP_HINT)

    # Load game data, validate the settings against it, and place buildings
    game_data, data_note = get_game_data()
    missing = [building for building in covered if building not in game_data["covered"]]
    if missing:
        raise Problem("The game data has nothing yet for " + ", ".join(missing) + ".\n"
                      "The dump effect covers them now, so a new dump is needed. " + NEW_DUMP_HINT)
    for settings in (rgo, other):
        settings.check(check_list_names, settings.listed, fact_keys)
        settings.check(check_pop_types, settings.general, game_data["locations"])
    check_named_locations(game_data["locations"])
    cannot_build = {tag: set(buildings) for tag, buildings in game_data["cannot_build"].items()}

    rgo_lines, rgo_counts, rgo_removals = place_rgo_buildings(game_data, rgo.general, rgo.rules, cannot_build)
    other_lines, other_counts, other_removals = place_other_buildings(game_data, other.general, other.rules, other.groups, cannot_build)

    # Write the three output files and print a summary
    write_setup_file(RGO_OUTPUT_FILE, RGO_SETTINGS_FILE, rgo_lines)
    write_setup_file(BUILDING_OUTPUT_FILE, BUILDING_SETTINGS_FILE, other_lines)
    removals = {**rgo_removals, **other_removals}
    write_script_file(REMOVALS_EFFECT_FILE, removals_effect_text(removals))

    print(data_note)
    print(f"Wrote {len(rgo_lines)} RGO buildings to {shown_path(RGO_OUTPUT_FILE)}")
    for label in ("main buildings", "secondary buildings", "main buildings skipped by technology", "placed on top of levels already there"):
        print(f"  {label + ':':<40}{rgo_counts[label]}")
    print(f"Wrote {len(other_lines)} other buildings to {shown_path(BUILDING_OUTPUT_FILE)}")
    for label, count in sorted(other_counts.items()):
        print(f"  {label + ':':<40}{count}")
    print(f"Wrote {len(removals)} removals of starting levels, {sum(removals.values())} levels in all, to {shown_path(REMOVALS_EFFECT_FILE)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Writes the setup files that place buildings at game start.")
    parser.add_argument("--setup-data-dump", action="store_true",
                        help="turn the dump on and take away the files this script writes, so the next game start "
                             "reports a clean state. Run this script again afterwards to make everything fresh.")
    try:
        main(parser.parse_args().setup_data_dump)
    except Problem as problem:
        print(f"\nPROBLEM: {problem}\n")
        sys.exit(1)
