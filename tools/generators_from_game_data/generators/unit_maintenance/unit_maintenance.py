"""
UNIT MAINTENANCE

Reads two settings files and writes each unit type's maintenance: its goods demand, its food, and its
gold, manpower and sailor prices.

    unit_settings.txt     a section for each unit category, and one for each unit type. A unit type
                          takes what its own section leaves out from its category's section.
    demand_settings.txt   a section for each maintenance demand: its goods and its food a day per
                          strength. Any number of unit types can use one demand.

Land unit gold follows the goods. The game scales the goods demand and the gold price with the
regiment's men: the demand per 1,000 men, and the price per BASE_REGIMENT_PRICE_SCALE thousand men
(1 in MnT_Defines.txt). So the price is the goods value times that define, and the base cost in the
game equals the value of the unit's maintenance goods at default market prices, in every age.
soldier_salary adds gold a month for each soldier. sailor_salary adds gold a month for each sailor of a
ship's crew. The game multiplies ship gold by BASE_SCALE_SHIP_DOUBLE_PER_AGE times 2 for each age after the
first, by the unit type's own age, so the script divides the salary by that factor. The game adds
<category>_maintenance and <unit type>_maintenance, so a unit type whose total differs from its
category's gets its own price with the difference. Ship gold is the game's value plus the salary.

    python3 unit_maintenance.py              write the files
    python3 unit_maintenance.py --dry-run    report what would change, and write nothing
    python3 unit_maintenance.py --import     write the settings files from the game files as they are now
    python3 unit_maintenance.py --backups    list the backups
    python3 unit_maintenance.py --restore    put the files back as they were before the newest backup

[all_land_units] and [all_ships] in unit_settings.txt set game defines, such as the share of maintenance that levies
pay. The script writes them to MnT_Defines.txt.

Writing, --import and --restore save a backup first. The newest 5 are kept in the backups folder.
"""

import argparse
import collections
import importlib.util
import re
import sys
from pathlib import Path

SCRIPT_FOLDER = Path(__file__).resolve().parent
MOD_FOLDER = SCRIPT_FOLDER.parents[3]
sys.path.insert(0, str(MOD_FOLDER))
sys.path.insert(0, str(MOD_FOLDER / "tools" / "recipe_ledger"))
from pdx_tree import get, parse, read  # noqa: E402


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The settings format, the backups and the change summary are the building setup generator's
setup = load_module(SCRIPT_FOLDER.parent / "building_setup" / "building_setup.py", "building_setup_for_units")
Problem = setup.Problem

UNIT_SETTINGS_FILE = SCRIPT_FOLDER / "unit_settings.txt"
DEMAND_SETTINGS_FILE = SCRIPT_FOLDER / "demand_settings.txt"
SETTINGS_READ = {UNIT_SETTINGS_FILE: UNIT_SETTINGS_FILE, DEMAND_SETTINGS_FILE: DEMAND_SETTINGS_FILE}
setup.BACKUP_FOLDER = SCRIPT_FOLDER / "backups"
backups, backup_files = setup.backups, setup.backup_files  # The window lists the backups through these

CATEGORY_PRICE_FILE = MOD_FOLDER / "in_game/common/prices/MnT_02_units.txt"
# This script writes these files whole. It reads the game without them, to see what they change.
UNIT_PRICE_FILE = MOD_FOLDER / "in_game/common/prices/MnT_unit_maintenance_prices.txt"
UNIT_TYPE_FILE = MOD_FOLDER / "in_game/common/unit_types/MnT_unit_type_changes.txt"
DEMAND_FILE = MOD_FOLDER / "in_game/common/goods_demand/MnT_unit_maintenance_demands.txt"
MODIFIER_TYPE_FILE = MOD_FOLDER / "main_menu/common/modifier_type_definitions/MnT_unit_maintenance_modifier_types.txt"
MODIFIER_ICON_FILE = MOD_FOLDER / "main_menu/common/modifier_icons/MnT_unit_maintenance_modifier_icons.txt"
MODIFIER_LOC_FILE = MOD_FOLDER / "main_menu/localization/english/MnT_unit_maintenance_modifiers_l_english.yml"
DEFINES_FILE = MOD_FOLDER / "loading_screen/common/defines/MnT_Defines.txt"
WRITTEN_FILES = {UNIT_PRICE_FILE.name, UNIT_TYPE_FILE.name, DEMAND_FILE.name, MODIFIER_TYPE_FILE.name, MODIFIER_ICON_FILE.name}

HEADER = "# Written by MnT Unit Maintenance.bat in tools. Change the settings there, not this file.\n"
PROVISIONS = "provisions"
DAYS_PER_MONTH = 30
GOLD_DECIMALS = 4
AMOUNT_DECIMALS = 5

CATEGORY_SETTINGS = {"army": ["maintenance_demand", "manpower_maintenance", "soldier_salary"],
                     "navy": ["maintenance_demand", "sailor_maintenance", "sailor_salary"]}
UNIT_SETTINGS = CATEGORY_SETTINGS
DEMAND_SETTINGS = {"army": ["goods", "food_per_strength"], "navy": ["goods", "food_per_strength"]}
RESOURCE_SETTING = {"army": "manpower_maintenance", "navy": "sailor_maintenance"}
SALARY_SETTING = {"army": "soldier_salary", "navy": "sailor_salary"}
PRICE_FIELD = {"manpower_maintenance": "manpower", "sailor_maintenance": "sailors"}
MEN_PER_STRENGTH = 1000  # max_strength and crew_size count in thousands
# The defines that the sections [all_land_units] and [all_ships] set: {section: {setting: define namespace}}
GLOBAL_SECTIONS = {
    "all_land_units": {"base_regiment_price_scale": "NUnit", "levy_maintenance_factor": "NUnit", "max_food_consumption_penalty": "NUnit",
                       "mercenary_monthly_maintenance_multiplier": "NMercenary",
                       "mercenary_prisoner_monthly_maintenance_multiplier": "NMercenary"},
    "all_ships": {"base_scale_ship_double_per_age": "NUnit", "mothball_maintenance_factor": "NEconomy", "mothball_percent": "NUnit"},
}
GLOBAL_DEFINES = {key: namespace for settings in GLOBAL_SECTIONS.values() for key, namespace in settings.items()}


def number(value, decimals=AMOUNT_DECIMALS):
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def same(old, new, decimals=AMOUNT_DECIMALS):
    return old is not None and abs(old - new) < 0.5 * 10 ** -decimals


def to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ game data

def database(relative, game, skip=()):
    """{key: (block, file name, origin)} as the game loads one folder: the DLC and game files, a mod file in place
    of the game file with its name, then the mod's own files. REPLACE:x replaces x, INJECT:x sets x's keys.
    Files named in skip are left out."""
    files = {}
    for root in sorted((Path(game) / "dlc").glob("*")) + [Path(game)]:
        for path in sorted((root / relative).glob("*.txt")):
            files[path.name] = (path, "game")
    for path in sorted((MOD_FOLDER / relative).glob("*.txt")):
        if path.name not in skip:
            files[path.name] = (path, "mod")
    entries = {}
    for name in sorted(files, key=lambda name: (files[name][1] == "mod", name)):
        path, origin = files[name]
        for key, _, value in parse(read(str(path))):
            if key is None or not isinstance(value, list):
                continue
            mode, _, base = key.rpartition(":")
            mode = mode.upper()
            if mode in ("INJECT", "TRY_INJECT", "INJECT_OR_CREATE") and base in entries:
                merged = list(entries[base][0])
                for child in value:
                    at = next((index for index, old in enumerate(merged) if old[0] == child[0] and child[0] is not None), None)
                    if at is None:
                        merged.append(child)
                    else:
                        merged[at] = child
                entries[base] = (merged, name, entries[base][2])
            elif mode in ("", "REPLACE", "TRY_REPLACE", "REPLACE_OR_CREATE", "INJECT", "TRY_INJECT", "INJECT_OR_CREATE"):
                entries[base] = (value, name, origin)
    return entries


def read_define(game, name, default, mod=True):
    """The define's value in the game files, then in the mod's files unless mod is False."""
    for path in [*sorted((Path(game) / "loading_screen/common/defines").glob("*.txt")),
                 *(sorted((MOD_FOLDER / "loading_screen/common/defines").glob("*.txt")) if mod else [])]:
        match = re.search(rf"(?m)^\s*{name}\s*=\s*(-?[0-9.]+)", path.read_text(encoding="utf-8-sig", errors="replace"))
        if match:
            default = float(match[1])
    return default


def read_game(written=True):
    """The game data this script needs. written=False leaves out the files this script writes, which shows what
    the game would be without them."""
    game = setup.find_game_folder()
    skip = () if written else WRITTEN_FILES
    data = {folder: database(f"in_game/common/{folder}", game, skip)
            for folder in ("unit_types", "unit_categories", "goods_demand", "prices", "goods")}
    data["modifier_types"] = database("main_menu/common/modifier_type_definitions", game, skip)
    data["modifier_icons"] = database("main_menu/common/modifier_icons", game, skip)
    data["defines"] = {key: read_define(game, key.upper(), None) for key in GLOBAL_DEFINES}
    data["game_defines"] = {key: read_define(game, key.upper(), None, mod=False) for key in GLOBAL_DEFINES}
    data["define_namespaces"] = [name for path in sorted((Path(game) / "loading_screen/common/defines").glob("*.txt"))
                                 for name in re.findall(r"(?m)^(N\w+)\s*=\s*\{", path.read_text(encoding="utf-8-sig", errors="replace"))]
    data["prices_of_goods"] = {good: to_float(get(block, "default_market_price")) or 0 for good, (block, _, _) in data["goods"].items()}
    provisions = data["goods"].get(PROVISIONS)
    data["food_per_provisions"] = to_float(get(provisions[0], "food")) if provisions else None
    if not data["food_per_provisions"]:
        raise Problem("The provisions good has no food value, so the provisions for food cannot be worked out.")
    data["units"] = unit_types(data)
    return data


def unit_types(data):
    """{unit type: facts} for every unit type with a category."""
    types, categories = data["unit_types"], data["unit_categories"]

    def values_of(name, seen=()):
        # A type takes its copy_from type's values, then its own values win
        block = types[name][0]
        base = get(block, "copy_from")
        values = values_of(base, seen + (name,)) if base in types and base not in seen else {}
        values.update({key: value for key, _, value in block if isinstance(value, str)})
        return values

    def crew_of(name, seen=()):
        # crew_size adds to the copy_from type's crew; the game shows n_long_fada with 30 - 10 = 20 sailors
        block = types[name][0]
        base = get(block, "copy_from")
        own = to_float(get(block, "crew_size")) or 0
        return own + (crew_of(base, seen + (name,)) if base in types and base not in seen else 0)

    units = {}
    for name in types:
        values = values_of(name)
        category = values.get("category")
        if category not in categories:
            continue
        block = categories[category][0]
        units[name] = {
            "category": category, "army": get(block, "is_army") == "yes", "copy_from": get(types[name][0], "copy_from"),
            "own_keys": {key for key, _, _ in types[name][0]},
            "demand": values.get("maintenance_demand") or get(block, "maintenance_demand"),
            "own_food": to_float(values.get("food_consumption_per_strength")) or 0,
            "category_food": to_float(get(block, "food_consumption_per_strength")) or 0,
            "max_strength": (to_float(values.get("max_strength")) or 0) + (to_float(get(block, "max_strength")) or 0),
            "crew": round((crew_of(name) + (to_float(get(block, "crew_size")) or 0)) * MEN_PER_STRENGTH),
            "age": (values.get("age") or "").strip('"') or None,
        }
    return units


def ship_age_factor(scale, age):
    """The game's multiplier on ship gold: BASE_SCALE_SHIP_DOUBLE_PER_AGE shifted left by the age's index (age_1 is 0).
    No age counts as the first."""
    match = re.match(r"age_(\d+)_", age or "")
    return int(scale) << (int(match[1]) - 1 if match else 0)


def price_value(data, key, field):
    entry = data["prices"].get(key)
    return to_float(get(entry[0], field)) if entry else None


def demand_goods(data, demand):
    """{good: amount} of a demand in the game files. None when the game has no such demand."""
    if demand not in data["goods_demand"]:
        return None
    return {key: to_float(value) for key, _, value in data["goods_demand"][demand][0]
            if key in data["goods"] and to_float(value) is not None}


# ------------------------------------------------------------------ settings

def read_settings(path):
    return setup.in_file(path, setup.read_settings_file, path)


def kind_of(army):
    return "army" if army else "navy"


def category_kinds(data):
    """{category: army or navy} for the categories that have unit types."""
    return {unit["category"]: kind_of(unit["army"]) for unit in data["units"].values()}


def check_settings(data, unit_sections, demand_sections):
    """Raises Problem for a section or setting the settings files cannot have."""
    kinds = category_kinds(data)
    for name, section in unit_sections.items():
        if name in GLOBAL_SECTIONS:
            for key in section:
                if key not in GLOBAL_SECTIONS[name]:
                    raise Problem(f"{UNIT_SETTINGS_FILE.name}: [{name}] cannot have {key}. It can have: {', '.join(GLOBAL_SECTIONS[name])}.")
            continue
        if name in kinds:
            allowed, kind = CATEGORY_SETTINGS[kinds[name]], kinds[name]
        elif name in data["units"]:
            kind = kind_of(data["units"][name]["army"])
            allowed = UNIT_SETTINGS[kind]
        else:
            raise Problem(f"{UNIT_SETTINGS_FILE.name}: [{name}] is not a unit type or unit category in the game.")
        for key in section:
            if key not in allowed:
                raise Problem(f"{UNIT_SETTINGS_FILE.name}: [{name}] is {'an' if kind == 'army' else 'a'} {kind} section, so it cannot have {key}. "
                              f"It can have: {', '.join(allowed)}.")
    for name, section in demand_sections.items():
        for key in section:
            if key not in DEMAND_SETTINGS["army"]:
                raise Problem(f"{DEMAND_SETTINGS_FILE.name}: [{name}] cannot have {key}. It can have: goods, food_per_strength.")


def setting(sections, name, key):
    """The text of one setting, or None when it is missing or None."""
    text = sections.get(name, {}).get(key)
    return None if text is None or text.strip().lower() in ("", "none") else text.strip()


def read_demands(data, demand_sections):
    """{demand: {"goods": {good: amount}, "food": food a day per strength}}."""
    demands = {}
    for name, section in demand_sections.items():
        goods = setup.read_multipliers(name, "goods", section.get("goods", ""))
        unknown = [good for good in goods if good not in data["goods"]]
        if unknown:
            raise Problem(f"{DEMAND_SETTINGS_FILE.name}: In [{name}], goods has {', '.join(unknown)}, which is not a good in the game.")
        if PROVISIONS in goods:
            raise Problem(f"{DEMAND_SETTINGS_FILE.name}: In [{name}], goods has provisions. Set food_per_strength instead; "
                          "the provisions follow from it.")
        food = setup.read_number(name, "food_per_strength", section.get("food_per_strength", ""))
        if food is None:
            raise Problem(f"{DEMAND_SETTINGS_FILE.name}: [{name}] needs food_per_strength. Its provisions follow from it, "
                          "and every unit type that uses the demand eats that much.")
        demands[name] = {"goods": goods, "food": food}
    return demands


# ------------------------------------------------------------------ plan

def plan(data, unit_sections, demand_sections):
    """What the settings ask for. base is the game data without the files this script writes."""
    check_settings(data, unit_sections, demand_sections)
    defines = {}
    for section, keys in GLOBAL_SECTIONS.items():
        for key in keys:
            text = setting(unit_sections, section, key)
            defines[key] = setup.read_number(section, key, text) if text else data["defines"][key]
    demands = read_demands(data, demand_sections)
    prices, food_per_provisions = data["prices_of_goods"], data["food_per_provisions"]

    def provisions_of(demand):
        return round(demands[demand]["food"] * DAYS_PER_MONTH / food_per_provisions, AMOUNT_DECIMALS)

    def value_of(demand):
        goods = dict(demands[demand]["goods"])
        provisions = provisions_of(demand)
        if provisions:
            goods[PROVISIONS] = provisions
        return sum(amount * prices.get(good, 0) for good, amount in goods.items())

    units = {}
    for name, unit in sorted(data["units"].items()):
        category = unit["category"]
        demand = setting(unit_sections, name, "maintenance_demand") or setting(unit_sections, category, "maintenance_demand")
        if demand is None:
            raise Problem(f"{UNIT_SETTINGS_FILE.name}: [{category}] needs maintenance_demand.")
        if demand not in demands:
            where = name if setting(unit_sections, name, "maintenance_demand") else category
            raise Problem(f"{UNIT_SETTINGS_FILE.name}: [{where}] uses the demand {demand}, which has no section in {DEMAND_SETTINGS_FILE.name}.")
        item = {"category": category, "army": unit["army"], "demand": demand, "max_strength": unit["max_strength"], "crew": unit["crew"]}
        for key in UNIT_SETTINGS[kind_of(unit["army"])][1:]:
            text = setting(unit_sections, name, key) or setting(unit_sections, category, key)
            item[key] = setup.read_number(name if setting(unit_sections, name, key) else category, key, text) if text else None
        item["food"] = demands[demand]["food"]
        if unit["army"]:
            item["value"] = value_of(demand)
            item["salary"] = (item["soldier_salary"] or 0) * MEN_PER_STRENGTH
            item["gold"] = round((item["value"] + item["salary"]) * defines["base_regiment_price_scale"], GOLD_DECIMALS)
        else:
            # The game's ship gold, without this script's prices, plus the salary of the crew
            # The game multiplies the whole price by the age factor of the unit type's own age, so the salary is divided by it
            item["age"], item["age_factor"] = unit["age"], ship_age_factor(defines["base_scale_ship_double_per_age"], unit["age"])
            item["base_gold"] = sum(price_value(data, key, "gold") or 0 for key in (f"{category}_maintenance", f"{name}_maintenance"))
            item["salary"] = (item["sailor_salary"] or 0) * unit["crew"]
            item["gold"] = round(item["base_gold"] + item["salary"] / (item["age_factor"] or 1), GOLD_DECIMALS)
            item["game_gold"] = item["gold"] * item["age_factor"]
        units[name] = item

    categories = {}
    for category, kind in sorted(category_kinds(data).items()):
        members = {name: item for name, item in units.items() if item["category"] == category}
        entry = {"kind": kind, "units": sorted(members), "gold": price_value(data, f"{category}_maintenance", "gold")}
        if kind == "army":
            # The most common total needs no unit price, so the fewest unit types get one
            golds = collections.Counter(item["gold"] for item in members.values() if item["gold"] is not None)
            if golds:
                entry["gold"] = min(golds, key=lambda gold: (-golds[gold], gold))
        for key in CATEGORY_SETTINGS[kind][1:]:
            text = setting(unit_sections, category, key)
            entry[key] = setup.read_number(category, key, text) if text else price_value(data, f"{category}_maintenance", PRICE_FIELD[key]) if key in PRICE_FIELD else None
        categories[category] = entry
    return {"units": units, "categories": categories, "demands": demands, "defines": defines,
            "provisions": {name: provisions_of(name) for name in demands}}


# ------------------------------------------------------------------ the files

def block_span(text, name):
    """(start, end) of the block name = { ... } in text, or None."""
    match = re.search(r"(?m)^[ \t]*" + re.escape(name) + r"[ \t]*=[ \t]*\{", text)
    if not match:
        return None
    depth = 0
    for index in range(match.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return match.start(), index + 1
    raise Problem(f"{name} has no closing brace.")


def set_lines(block, values, remove=()):
    """The block with each key = value line set, keys in remove taken out. A new line goes before the closing brace.
    Notes after a value stay."""
    for key in remove:
        block = re.sub(r"(?m)^[ \t]*" + re.escape(key) + r"[ \t]*=[^\n]*\n?", "", block)
    for key, value in values.items():
        # The key starts a line, or follows a { or a space in a block on one line. Not in a note after a #.
        line = re.compile(r"(?m)^((?:[^#\n]*[\s{])?[ \t]*" + re.escape(key) + r"[ \t]*=[ \t]*)[^\s#}]+")
        if line.search(block):
            block = line.sub(lambda match: match[1] + value, block, count=1)
        else:
            close = block.rstrip().rfind("}")
            body = block[:close].rstrip(" \t")
            if "\n" not in block:  # A block on one line opens up
                body = body.rstrip() + "\n"
            block = body + f"\t{key} = {value}\n" + block[close:]
    return block


def demand_files(base, the_plan):
    """{path: text} of the goods demand files: demands the mod already has change where they are, the others go into
    DEMAND_FILE, as REPLACE: when the game has them."""
    texts, written = {}, []
    for name in sorted(the_plan["demands"]):
        goods = {good: amount for good, amount in the_plan["demands"][name]["goods"].items()}
        provisions = the_plan["provisions"][name]
        if provisions:
            goods[PROVISIONS] = provisions
        old = demand_goods(base, name)
        if old is not None and set(old) == set(goods) and all(same(old[good], goods[good]) for good in goods):
            continue
        entry = base["goods_demand"].get(name)
        values = {good: number(amount) for good, amount in goods.items()}
        if entry and entry[2] == "mod":
            path = MOD_FOLDER / "in_game/common/goods_demand" / entry[1]
            text = texts.get(path) or path.read_text(encoding="utf-8-sig")
            span = block_span(text, name) or block_span(text, "REPLACE:" + name)
            if span:
                start, end = span
                removed = [good for good in (old or {}) if good not in goods]
                texts[path] = text[:start] + set_lines(text[start:end], values, removed) + text[end:]
                continue
        others = [f"\t{key} = {value}" for key, _, value in (entry[0] if entry else [])
                  if key not in base["goods"] and isinstance(value, str)]
        if not others:
            army = any(unit["demand"] == name and unit["army"] for unit in the_plan["units"].values())
            others = [f"\tcategory = {'regiment_maintenance' if army else 'ship_maintenance'}"]
        prefix = "REPLACE:" if entry else ""
        written.append(f"{prefix}{name} = {{\n" + "".join(f"\t{good} = {value}\n" for good, value in values.items())
                       + "\n".join(others) + "\n}\n")
    texts[DEMAND_FILE] = HEADER + "\n" + "\n".join(written)
    return texts


def unit_type_text(base, the_plan):
    """INJECT blocks for each unit type whose demand or food differs from the game without this script's files."""
    changes = {}
    for name, item in the_plan["units"].items():
        unit = base["units"].get(name)
        if unit is None:
            continue
        if item["demand"] != unit["demand"]:
            changes.setdefault(name, {})["maintenance_demand"] = item["demand"]
        own = round(item["food"] - unit["category_food"], AMOUNT_DECIMALS)
        if not same(own, unit["own_food"]):
            changes.setdefault(name, {})["food_consumption_per_strength"] = number(own)
    # A unit type that takes a changed key from its copy_from type gets the key itself, so it keeps its own value
    for key in ("maintenance_demand", "food_consumption_per_strength"):
        for name, unit in base["units"].items():
            if key in changes.get(name, {}) or name not in the_plan["units"]:
                continue
            source = unit
            while key not in source["own_keys"] and source["copy_from"] in base["units"]:
                source_name = source["copy_from"]
                if key in changes.get(source_name, {}):
                    item = the_plan["units"][name]
                    value = item["demand"] if key == "maintenance_demand" else number(round(item["food"] - unit["category_food"], AMOUNT_DECIMALS))
                    changes.setdefault(name, {})[key] = value
                    break
                source = base["units"][source_name]
    parts = [HEADER]
    for name in sorted(changes, key=lambda name: (the_plan["units"][name]["category"], name)):
        parts.append(f"\nINJECT:{name} = {{\n" + "".join(f"\t{key} = {value}\n" for key, value in changes[name].items()) + "}\n")
    return "".join(parts), changes


def category_price_text(the_plan):
    """MnT_02_units.txt with each category's maintenance gold, manpower and sailors set."""
    text = CATEGORY_PRICE_FILE.read_text(encoding="utf-8-sig")
    for category, entry in the_plan["categories"].items():
        key = f"{category}_maintenance"
        values = {PRICE_FIELD[setting_key]: number(entry[setting_key], GOLD_DECIMALS)
                  for setting_key in [RESOURCE_SETTING[entry["kind"]]] if entry[setting_key] is not None}
        if entry["gold"] is not None:
            values = {"gold": number(entry["gold"], GOLD_DECIMALS), **values}
        span = block_span(text, "REPLACE:" + key) or block_span(text, key)
        if span:
            start, end = span
            text = text[:start] + set_lines(text[start:end], values) + text[end:]
        else:
            text = text.rstrip("\n") + f"\n\nREPLACE:{key} = {{\n" + "".join(f"\t{field} = {value}\n" for field, value in values.items()) + "}\n"
    return text


def defines_text(base, the_plan):
    """MnT_Defines.txt with each define of [all_land_units] and [all_ships]. The script changes the value of a line the
    file has. It adds a line only for a value that differs from the game's. A new namespace block goes before the
    first block that comes after it in the game's defines."""
    text = DEFINES_FILE.read_text(encoding="utf-8-sig")
    for key, namespace in GLOBAL_DEFINES.items():
        value = the_plan["defines"][key]
        if value is None:
            continue
        line = re.search(rf"(?m)^([ \t]*{key.upper()}[ \t]*=[ \t]*)(-?[0-9.]+)", text)
        if line:
            if not same(float(line[2]), value):
                text = text[:line.start(2)] + number(value) + text[line.end(2):]
            continue
        if same(base["game_defines"][key], value):
            continue
        if not block_span(text, namespace):
            game_order = base["define_namespaces"]
            later = [name for name in game_order[game_order.index(namespace) + 1:] if block_span(text, name)] if namespace in game_order else []
            at = block_span(text, later[0])[0] if later else len(text.rstrip("\n")) + 1
            text = text[:at].rstrip("\n") + f"\n\n{namespace} = {{\n}}\n\n" + text[at:].lstrip("\n")
        end = block_span(text, namespace)[1] - 1
        text = text[:end] + f"\t{key.upper()} = {number(value)}\n" + text[end:]
    return text


def unit_prices(base, the_plan):
    """{unit type: {field: value}} of the unit type prices: what each unit type's total differs by from its category's.
    A unit type the game gives a price keeps one, so the game's value is replaced."""
    result = {}
    for name, item in the_plan["units"].items():
        category = the_plan["categories"][item["category"]]
        key = f"{name}_maintenance"
        fields = {}
        if item["gold"] is not None and category["gold"] is not None:
            fields["gold"] = round(item["gold"] - category["gold"], GOLD_DECIMALS)
        elif price_value(base, key, "gold") is not None:
            fields["gold"] = price_value(base, key, "gold")
        for setting_key in [RESOURCE_SETTING[category["kind"]]]:
            field = PRICE_FIELD[setting_key]
            if item[setting_key] is not None and category[setting_key] is not None:
                extra = round(item[setting_key] - category[setting_key], GOLD_DECIMALS)
                if extra or price_value(base, key, field) is not None:
                    fields[field] = extra
        if any(value for value in fields.values()) or key in base["prices"]:
            result[name] = fields
    return result


def unit_price_text(base, the_plan, prices):
    parts, last = [HEADER], None
    for name in sorted(prices, key=lambda name: (the_plan["units"][name]["category"], the_plan["units"][name]["demand"], name)):
        if the_plan["units"][name]["category"] != last:
            parts.append("\n")
            last = the_plan["units"][name]["category"]
        key = f"{name}_maintenance"
        prefix = "REPLACE:" if key in base["prices"] else ""
        fields = " ".join(f"{field} = {number(value, GOLD_DECIMALS)}" for field, value in prices[name].items())
        parts.append(f"{prefix}{key} = {{ {fields} }}\n")
    return "".join(parts)


def modifier_texts(base, the_plan, prices):
    """The modifier type, icon and English name of each unit type price the game has no modifier type for. The game
    looks for <price>_cost_modifier for every price."""
    types, icons, names = [HEADER], [HEADER], ["﻿l_english:\n"]
    for name in sorted(prices):
        modifier = f"{name}_maintenance_cost_modifier"
        if modifier in base["modifier_types"]:
            continue
        category = the_plan["units"][name]["category"]
        types.append(f"\n{modifier} = {{\n\tcolor = bad\n\tpercent = yes\n\tgame_data = {{\n\t\tcategory = country\n\t}}\n}}\n")
        icon = base["modifier_icons"].get(f"{category}_maintenance_cost_modifier")
        if icon and get(icon[0], "positive"):
            path = get(icon[0], "positive").strip('"')
            icons.append(f'{modifier} = {{\n\tpositive = "{path}"\n}}\n')
        names.append(f' MODIFIER_TYPE_NAME_{modifier}: "${name}$ Maintenance Cost"\n')
        names.append(f" MODIFIER_TYPE_DESC_{modifier}: \"This impacts how much it costs to [maintain|e] a "
                     f"[ShowUnitDefinitionName('{name}')].\"\n")
    return "".join(types), "".join(icons), "".join(names)


def script_bytes(text):
    return ("﻿" + text.lstrip("﻿")).encode("utf-8")


def file_contents(base, the_plan):
    """{path: bytes} of every file the settings write."""
    contents = {path: script_bytes(text) for path, text in demand_files(base, the_plan).items()}
    unit_text, _ = unit_type_text(base, the_plan)
    prices = unit_prices(base, the_plan)
    types, icons, names = modifier_texts(base, the_plan, prices)
    contents.update({
        UNIT_TYPE_FILE: script_bytes(unit_text),
        CATEGORY_PRICE_FILE: script_bytes(category_price_text(the_plan)),
        DEFINES_FILE: script_bytes(defines_text(base, the_plan)),
        UNIT_PRICE_FILE: script_bytes(unit_price_text(base, the_plan, prices)),
        MODIFIER_TYPE_FILE: script_bytes(types),
        MODIFIER_ICON_FILE: script_bytes(icons),
        MODIFIER_LOC_FILE: names.encode("utf-8"),
    })
    return contents


# ------------------------------------------------------------------ report

def report(data, the_plan):
    """Prints each category's gold and its unit types' gold. Land gold per 1,000 men is the value of the goods."""
    units, categories = the_plan["units"], the_plan["categories"]
    for category, entry in categories.items():
        print()
        old = price_value(data, f"{category}_maintenance", "gold")
        line = f"{category}  {len(entry['units'])} unit types  price {number(entry['gold'] or 0, GOLD_DECIMALS)}"
        if old is not None and entry["gold"] is not None and not same(old, entry["gold"], GOLD_DECIMALS):
            line += f"  (was {number(old, GOLD_DECIMALS)})"
        print(line)
        if entry["kind"] != "army":
            continue
        groups = collections.defaultdict(list)
        for name in entry["units"]:
            groups[(units[name]["demand"], units[name]["gold"])].append(name)
        for (demand, gold), names in sorted(groups.items(), key=lambda group: -len(group[1])):
            item = units[names[0]]
            print(f"    {demand:40} {len(names):3} unit types  goods {number(item['value'], 3):7} + salary {number(item['salary'], 3)} "
                  f"gold a month, food {number(item['food'], 3)}")


def main(dry_run=False, preview_folder=None):
    data = read_game()
    base = read_game(written=False)
    unit_sections = read_settings(SETTINGS_READ[UNIT_SETTINGS_FILE])
    demand_sections = read_settings(SETTINGS_READ[DEMAND_SETTINGS_FILE])
    the_plan = plan(base, unit_sections, demand_sections)
    report(data, the_plan)
    contents = file_contents(base, the_plan)
    for real, read_from in SETTINGS_READ.items():
        if read_from != real:
            contents[real] = read_from.read_bytes()
    contents = {path: content for path, content in contents.items() if not path.is_file() or path.read_bytes() != content}
    print()
    for path in sorted(contents):
        print(("would change " if dry_run else "changes ") + setup.shown_path(path))
    if dry_run:
        if preview_folder:
            for path, content in contents.items():
                saved = preview_folder / path.relative_to(MOD_FOLDER)
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(content)
        print(f"\n{len(contents)} files would change. Nothing was written.")
        return
    if contents:
        folder = setup.write_with_backup(contents, "apply")
        print(f"\nWrote {len(contents)} files. Backup {folder.name}.")
    else:
        print("\nNo files change.")


# ------------------------------------------------------------------ import

def settings_text(title, notes, sections):
    """A settings file: notes at the top, then [section] blocks of key = value lines."""
    lines = [f"# {title}", "#"] + [f"# {note}" if note else "#" for note in notes] + [""]
    for name, settings, _ in sections:
        lines.append("")
        lines.append(f"[{name}]")
        lines += [f"{key} = {value}" for key, value in settings]
    return "\n".join(lines) + "\n"


def goods_map(goods):
    return "{ " + ", ".join(f'"{good}": {number(amount)}' for good, amount in goods.items()) + " }" if goods else "None"


UNIT_NOTES = [
    "[all_land_units] and [all_ships] set game defines. Apply writes them to MnT_Defines.txt.",
    "Then a section for each unit category, then one for each of its unit types. A unit type takes what its own",
    "section leaves out from its category's section.",
    "    maintenance_demand    the demand in demand_settings.txt the unit type uses",
    "    manpower_maintenance  manpower a month per strength (land units)",
    "    sailor_maintenance    sailors a month per crew (ships)",
    "    soldier_salary        gold a month per soldier, on top of the goods (land units)",
    "    sailor_salary         gold a month per sailor of the crew (ships)",
    "Land unit gold is the value of the demand's goods plus the salary. Ship gold is the game's value plus the salary.",
]
DEMAND_NOTES = [
    "Maintenance demands. Any number of unit types can use one demand, so a change here changes all of them.",
    "    goods              goods a month, without provisions",
    "    food_per_strength  food a day per strength. The provisions line follows from it.",
]


def import_settings():
    """Settings files that describe the game files as they are now."""
    data = read_game()
    units = data["units"]
    kinds = category_kinds(data)
    unit_sections, used = [], collections.defaultdict(list)
    for section, keys in GLOBAL_SECTIONS.items():
        unit_sections.append((section, [(key, number(data["defines"][key])) for key in keys if data["defines"][key] is not None], None))
    for category in sorted(kinds, key=lambda name: (kinds[name] == "navy", name)):
        key = RESOURCE_SETTING[kinds[category]]
        block = data["unit_categories"][category][0]
        default = get(block, "maintenance_demand")
        own_value = price_value(data, f"{category}_maintenance", PRICE_FIELD[key]) or 0
        unit_sections.append((category, [("maintenance_demand", default), (key, number(own_value)),
                                         (SALARY_SETTING[kinds[category]], "0")], None))
        for name in sorted(name for name, unit in units.items() if unit["category"] == category):
            unit = units[name]
            used[unit["demand"]].append(name)
            settings = []
            if unit["demand"] != default:
                settings.append(("maintenance_demand", unit["demand"]))
            extra = price_value(data, f"{name}_maintenance", PRICE_FIELD[key])
            if extra:
                settings.append((key, number(own_value + extra)))
            unit_sections.append((name, settings, None))

    demand_sections, mixed = [], []
    army_demands = {demand for demand, names in used.items() if any(units[name]["army"] for name in names)}
    for demand in sorted(used, key=lambda name: (name not in army_demands, name)):
        goods = demand_goods(data, demand)
        if goods is None:
            raise Problem(f"Unit types use the demand {demand}, but the game has no such demand: {', '.join(used[demand])}.")
        settings = [("goods", goods_map({good: amount for good, amount in goods.items() if good != PROVISIONS}))]
        foods = collections.Counter(round(units[name]["category_food"] + units[name]["own_food"], AMOUNT_DECIMALS)
                                    for name in used[demand])
        food = min(foods, key=lambda value: (-foods[value], value))
        settings.append(("food_per_strength", number(food)))
        if len(foods) > 1:
            mixed.append(f"{demand}: " + ", ".join(f"{number(value)} food for {count} unit types" for value, count in foods.items()))
        demand_sections.append((demand, settings, None))

    contents = {
        UNIT_SETTINGS_FILE: script_bytes(settings_text("UNIT MAINTENANCE SETTINGS", UNIT_NOTES, unit_sections)),
        DEMAND_SETTINGS_FILE: script_bytes(settings_text("MAINTENANCE DEMAND SETTINGS", DEMAND_NOTES, demand_sections)),
    }
    folder = setup.write_with_backup(contents, "import")
    print(f"Wrote {UNIT_SETTINGS_FILE.name} ({len(unit_sections)} sections) and {DEMAND_SETTINGS_FILE.name} "
          f"({len(demand_sections)} demands). Backup {folder.name}.")
    if mixed:
        print("\nThese demands are shared by unit types that eat different amounts of food. The setting takes the most common "
              "amount, so Apply gives all of them that food. Give the others their own demand to keep their food:")
        for line in mixed:
            print("  " + line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Writes each unit type's maintenance from the settings files.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--dry-run", nargs="?", type=Path, const=False, default=None, metavar="FOLDER",
                        help="report what would change and write nothing. With FOLDER, put the files it would write there")
    action.add_argument("--import", dest="import_", action="store_true", help="write the settings files from the game files")
    action.add_argument("--backups", action="store_true", help="list the backups")
    action.add_argument("--restore", nargs="?", type=int, const=1, metavar="N", help="undo to backup N (1 is the newest)")
    parser.add_argument("--force", action="store_true", help="with --restore: restore files that changed after the backup")
    parser.add_argument("--unit-settings", type=Path, metavar="FILE", help="read the unit settings from FILE")
    parser.add_argument("--demand-settings", type=Path, metavar="FILE", help="read the demand settings from FILE")
    arguments = parser.parse_args()
    if arguments.unit_settings:
        SETTINGS_READ[UNIT_SETTINGS_FILE] = arguments.unit_settings
    if arguments.demand_settings:
        SETTINGS_READ[DEMAND_SETTINGS_FILE] = arguments.demand_settings
    try:
        if arguments.backups:
            setup.list_backups()
        elif arguments.restore is not None:
            setup.restore(arguments.restore, arguments.force)
        elif arguments.import_:
            import_settings()
        else:
            main(arguments.dry_run is not None, arguments.dry_run or None)
    except Problem as problem:
        print(f"\nPROBLEM: {problem}\n")
        sys.exit(1)
