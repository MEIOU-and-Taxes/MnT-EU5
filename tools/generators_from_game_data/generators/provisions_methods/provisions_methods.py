"""
PROVISIONS METHODS GENERATOR

Keeps every production method that makes provisions in line with one settings file,
provisions_methods_settings.txt. For each method the settings give the food it makes, the
each good's percent of the input food, and the percent of the input food that becomes output food.
The script works out the amounts. It writes only the input amounts, the output line,
debug_max_profit and a short note on the method's first line; everything else in the building
files stays as written by hand.

    python3 provisions_methods.py              report only, changes nothing
    python3 provisions_methods.py --import     add every method missing from the settings, with today's numbers
    python3 provisions_methods.py --apply      write the settings into the building files
    python3 provisions_methods.py --backups    list the backups
    python3 provisions_methods.py --restore    put the files back as they were before the newest backup
    python3 provisions_methods.py --restore 3  the same for the third newest backup

--apply and --restore save a backup first. The newest 5 are kept in the backups folder.
Nothing in this script needs editing; change the settings file instead.
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_FOLDER = Path(__file__).resolve().parent
MOD_FOLDER = SCRIPT_FOLDER.parents[3]

# The mod's folder has to be importable before the shared tools are, whatever folder this is run from
sys.path.insert(0, str(MOD_FOLDER))
sys.path.insert(0, str(MOD_FOLDER / "tools" / "recipe_ledger"))
from tools.generators_from_game_data.generators.building_setup.building_setup import (  # noqa: E402
    Problem, long_path, read_multipliers, read_number, read_settings_file)
from tools.shared.fetch_logs import get_from_config  # noqa: E402
from pdx_tree import get, load_folder  # noqa: E402

SETTINGS_FILE = SCRIPT_FOLDER / "provisions_methods_settings.txt"
BACKUP_FOLDER = SCRIPT_FOLDER / "backups"
BACKUPS_KEPT = 5
BACKUP_NAME = re.compile(r"\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d(_\d+)?")
# Folders searched for method blocks, in the mod and in the game
METHOD_FOLDERS = ["in_game/common/building_types", "in_game/common/production_methods"]
SCRIPT_VALUE_FOLDERS = ["main_menu/common/script_values", "in_game/common/script_values"]
PROVISIONS = "provisions"
# A recipe entry with no input good: food the method makes from nothing, such as milk
MILK = "milk"
GENERAL_SETTINGS = ("food_per_unit", "milk_food", "efficiency", "min_profit", "max_profit", "round_food_inputs", "round_percent_inputs", "fixed",
                    "spare_labor_output")
SPARE_LABOR = "spare_labor"
BUILDING_SETTINGS = ("efficiency", SPARE_LABOR)
METHOD_SETTINGS = ("food_out", "recipe", "recipe_fixed", "other", "other_percent", "efficiency", "min_profit", "max_profit", "fixed")
MAX_PROFIT_LINE = "debug_max_profit"
# Written on the first line of every method the script manages
NOTE = "# generated: tools/generators_from_game_data/generators/provisions_methods"
# Amounts that differ by less than this share are the same. Input food and output food use it too.
SAME = 0.001

SETTINGS_HEADER = """\
# PROVISIONS METHODS SETTINGS
#
# Every production method that makes provisions. The script works out each method's input amounts
# from these settings.
# Run after editing (py on Windows):
#     python3 tools/generators_from_game_data/generators/provisions_methods/provisions_methods.py
# That only reports. Add --apply to write the changes into the building files.
# Add --import to add methods that are not in this file yet, with the numbers they have today.
# --apply saves a backup first. --backups lists them, --restore undoes the newest one.
#
# [general]
#     food_per_unit   Food in one unit of each good.
#     milk_food       Optional. Food in one unit of each milk type, like { "camels": 5 }. A recipe names a type
#                     as "milk_camels". Milk is not written as an input and costs nothing.
#     efficiency      Food conversion efficiency. Optional, 100 when left out. Percent of the input food
#                     that becomes output food.
#     min_profit      Optional. The min_profit for every method that does not set its own.
#     max_profit      Optional. The max_profit for every method that does not set its own.
#     round_food_inputs  Optional, 5 when left out. Decimals the food input amounts round to.
#                     With fewer decimals the input food can be a little off the output food.
#     round_percent_inputs  Optional, 5 when left out. Decimals the other_percent amounts round to.
#     spare_labor_output  Output of every spare_labor method. Needed when a building sets spare_labor.
#     fixed           Optional, output when left out. Which side stays when food values change:
#                     output keeps food_out and works out the inputs, inputs keeps the inputs and works
#                     out food_out. A method can set its own.
# A section named like a building sets that building's methods:
#     efficiency      Food conversion efficiency for the building's methods that do not set their own.
#     spare_labor     Optional. A method name, like wheat_no_provisions. The script writes that method into the
#                     provisions slot: the building's own good with no inputs, at spare_labor_output from
#                     [general]. It adds the method when it is missing.
# One section per method, named like the method:
#     food_out        Food the method makes per building level. 10 food is 1 provisions.
#     recipe          Each good's percent of the input food. The total must be 100.
#                     With fixed = inputs: each good's amount, like { "fish": 0.2 }. food_out then comes from the inputs and is not read.
#                     "milk" needs no input good. A method with no recipe and no food_out makes nothing.
#     recipe_fixed    Food goods at a fixed amount, like { "milk_wool": 0.1 }. With fixed = output, the recipe percents share the food these goods leave.
#     other           Other inputs as plain amounts, like { "salt": 0.004 }. The food does not change them.
#     other_percent   Other inputs as a percent of the provisions made, like { "salt": 2 }.
#     efficiency      Food conversion efficiency. Optional. Overrides the building's and the general one.
#     min_profit      Optional. The report flags the method when its profit is lower.
#     max_profit      Optional. The report flags the method when its profit is higher. The script writes it
#                     into the method as debug_max_profit.
# Profit is the percent of the output's value left after buying the inputs at base prices.
# A profit is a percent (20 = 20%, -10 = -10%) or a script value name like rural_profit_margin.
# A method you remove from this file is no longer managed; the report lists it as not in settings.

"""


# ------------------------------------------------------------------ terminal output

# FORCE_COLOR asks for color when a window, not a terminal, shows the output
# The settings window imports this file without a console, so stdout can be None
IN_TERMINAL = sys.stdout is not None and sys.stdout.isatty()
COLOR = (IN_TERMINAL or bool(os.environ.get("FORCE_COLOR"))) and "NO_COLOR" not in os.environ
if os.name == "nt" and IN_TERMINAL:
    os.system("")  # Turns on color codes in the Windows console


def press(button, flag):
    """The settings window has buttons where the terminal has flags."""
    return f"press {button}" if os.environ.get("MNT_GENERATORS_WINDOW") else f"run with {flag}"


def paint(code):
    return (lambda text: f"\033[{code}m{text}\033[0m") if COLOR else str


title = paint("1")
building_name = paint("1;34")
method_name = paint("32")
warning = paint("33")
bad = paint("91")
missing = paint("35")
quiet = paint("2")


def visible_length(text):
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def pad(text, width):
    return text + " " * max(0, width - visible_length(text))


def number(value):
    text = f"{value:.5f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def methods_text(count):
    return f"{count} method" + ("s" if count != 1 else "")


def files_text(count):
    return f"{count} file" + ("s" if count != 1 else "")


def percent(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def shown_path(path):
    return path.relative_to(MOD_FOLDER).as_posix()


# ------------------------------------------------------------------ game data

def read_game():
    """Goods, building names, and every provisions method the game loads with the buildings that use it."""
    game = get_from_config("Paths", "game_directory")
    mod = str(MOD_FOLDER)
    goods = load_folder("in_game/common/goods", game, mod)
    buildings = load_folder("in_game/common/building_types", game, mod)
    shared = load_folder("in_game/common/production_methods", game, mod)
    if PROVISIONS not in goods:
        raise Problem("The goods files have no provisions good.")

    methods = {}

    def add(name, block, owner):
        if isinstance(block, list) and get(block, "produced") == PROVISIONS:
            entry = methods.setdefault(name, {"block": block, "owners": []})
            if owner:
                entry["owners"].append(owner)

    for building, (block, _, _) in buildings.items():
        for key, _, value in block:
            if key == "unique_production_methods" and isinstance(value, list):
                for name, _, method in value:
                    add(name, method, building)
            elif key == "possible_production_methods" and isinstance(value, list):
                for name, _, _ in value:
                    if name in shared:
                        add(name, shared[name][0], building)
    for name, (block, _, _) in shared.items():
        add(name, block, None)

    prices = {name: float(get(block, "default_market_price") or 0) for name, (block, _, _) in goods.items()}
    food_per_provisions = float(get(goods[PROVISIONS][0], "food") or 0)
    if not food_per_provisions:
        raise Problem("The provisions good has no food value.")
    for entry in methods.values():
        entry["inputs"] = {key: float(value) for key, _, value in entry["block"]
                           if key in goods and isinstance(value, str) and re.fullmatch(r"[0-9.]+", value)}
        entry["output"] = float(get(entry["block"], "output") or 0)
        entry["max_profit"] = get(entry["block"], MAX_PROFIT_LINE)
    return set(goods), buildings, prices, food_per_provisions, methods


def read_script_values():
    """Script values that are plain numbers, such as rural_profit_margin = 0.2. The mod's win over the game's."""
    values = {}
    for root in (Path(get_from_config("Paths", "game_directory")), MOD_FOLDER):
        for folder in SCRIPT_VALUE_FOLDERS:
            for path in sorted((root / folder).glob("*.txt")) if (root / folder).is_dir() else []:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                for name, value in re.findall(r"(?m)^(\w+)[ \t]*=[ \t]*(-?[0-9.]+)[ \t]*(?:#.*)?$", text):
                    values[name] = float(value)
    return values


def profit_value(text, script_values):
    """A debug_max_profit value as a share: a number, or a script value name. None when it cannot be read."""
    if text is None:
        return None
    if re.fullmatch(r"-?[0-9.]+", text):
        return float(text)
    return script_values.get(text)


def block_span(text, name):
    """Start and end of every `name = { ... }` block in text. Braces inside notes do not count."""
    spans = []
    for match in re.finditer(r"(?m)^[ \t]*" + re.escape(name) + r"[ \t]*=[ \t]*\{", text):
        depth, index = 0, match.end() - 1
        while index < len(text):
            character = text[index]
            if character == "#":
                index = text.find("\n", index)
                if index < 0:
                    break
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    spans.append((match.start(), index + 1))
                    break
            index += 1
    return spans


def mod_files():
    files = []
    for folder in METHOD_FOLDERS:
        path = MOD_FOLDER / folder
        if path.is_dir():
            files += sorted(path.glob("*.txt"))
    return files


def locate(names):
    """For each method name, every (file, position, first line) in the mod's files that defines it."""
    found = {name: [] for name in names}
    for path in mod_files():
        text = path.read_text(encoding="utf-8-sig")
        for name in names:
            if name in text:
                found[name] += [(path, start, text[start:text.find("\n", start)]) for start, _ in block_span(text, name)]
    return found


# ------------------------------------------------------------------ settings

def read_profit(section, key, text, script_values):
    """A profit setting: a percent or a script value name. Returns the text for debug_max_profit and the share."""
    text = (text or "").strip()
    if text.lower() in ("", "none"):
        return None
    if re.fullmatch(r"[A-Za-z_]\w*", text):
        if text not in script_values:
            raise Problem(f'In [{section}], {key} is "{text}", which is not a script value with a number.')
        return {"file": text, "share": script_values[text]}
    try:
        value = float(text.rstrip("%"))
    except ValueError:
        raise Problem(f'In [{section}], {key} must be a percent or a script value name, but it is "{text}".')
    return {"file": number(value / 100), "share": value / 100}


def read_efficiency(section, text):
    value = read_number(section, "efficiency", text or "", above_zero=True)
    return None if value is None else value / 100


def read_decimals(general, key):
    """A rounding setting in [general]: 0 to 5 decimals, 5 when not set."""
    text = general.get(key, "").strip()
    text = "5" if text.lower() in ("", "none") else text
    if not re.fullmatch(r"[0-5]", text):
        raise Problem(f'In [general], {key} must be a whole number from 0 to 5, but it is "{text}".')
    return int(text)


def is_milk_type(good):
    """A milk type from milk_food, such as "milk_camels": food in the recipe with no input good."""
    return good.startswith(MILK + "_")


def read_fixed(section, text):
    """Which side of a method stays when food values change: "output" or "inputs". None when not set."""
    text = (text or "").strip().lower()
    if text in ("", "none"):
        return None
    if text not in ("output", "inputs"):
        raise Problem(f'In [{section}], fixed must be output or inputs, but it is "{text}".')
    return text


def check_keys(name, section, allowed):
    for key in section:
        if key not in allowed:
            raise Problem(f'In [{name}], "{key}" is not a setting. Settings you can use there: ' + ", ".join(allowed))


def read_settings(goods, building_names, methods, script_values):
    sections = read_settings_file(SETTINGS_FILE)
    general = next((section for name, section in sections.items() if name.lower() == "general"), None)
    if general is None:
        raise Problem("The settings file needs a [general] section.")
    check_keys("general", general, GENERAL_SETTINGS)
    default_min_profit = read_profit("general", "min_profit", general.get("min_profit"), script_values)
    default_max_profit = read_profit("general", "max_profit", general.get("max_profit"), script_values)
    default_efficiency = read_efficiency("general", general.get("efficiency")) or 1.0
    food_decimals, percent_decimals = (read_decimals(general, key) for key in ("round_food_inputs", "round_percent_inputs"))
    default_fixed = read_fixed("general", general.get("fixed")) or "output"
    food_per_unit = read_multipliers("general", "food_per_unit", general.get("food_per_unit", ""))
    for good in food_per_unit:
        if good not in goods:
            raise Problem(f'In [general], food_per_unit names "{good}", which is not a good.')
    # Milk types count as goods with a food value, but they are never inputs
    for source, food in read_multipliers("general", "milk_food", general.get("milk_food", "")).items():
        food_per_unit[f"{MILK}_{source}"] = food

    building_efficiency, method_sections = {}, {}
    for name, section in sections.items():
        # [pop demands] belongs to the window's Pop Demands page
        if name.lower() in ("general", "pop demands"):
            continue
        if name not in methods and name in building_names:
            check_keys(name, section, BUILDING_SETTINGS)
            building_efficiency[name] = read_efficiency(name, section.get("efficiency"))
        else:
            check_keys(name, section, METHOD_SETTINGS)
            method_sections[name] = section

    settings = {}
    for name, section in method_sections.items():
        recipe = read_multipliers(name, "recipe", section.get("recipe", ""))
        recipe_fixed = read_multipliers(name, "recipe_fixed", section.get("recipe_fixed", ""))
        other = read_multipliers(name, "other", section.get("other", ""))
        other_percent = read_multipliers(name, "other_percent", section.get("other_percent", ""))
        fixed = read_fixed(name, section.get("fixed")) or default_fixed
        if fixed == "inputs" and MILK in recipe:
            raise Problem(f"In [{name}], plain milk has no amount to fix. Add milk types to milk_food in [general], "
                          "then use one, like milk_camels.")
        # A blank method has no recipe and makes no food. With fixed inputs, food_out comes from the recipe.
        blank = not recipe and not recipe_fixed and (fixed == "inputs" or section.get("food_out", "").strip().lower() in ("", "none", "0"))
        food_out = 0.0 if blank or fixed == "inputs" else read_number(name, "food_out", section.get("food_out", ""), above_zero=True)
        if food_out is None:
            raise Problem(f"In [{name}], food_out needs a number.")
        if not blank and fixed == "output" and not recipe:
            raise Problem(f"In [{name}], the recipe needs a good to fill the food that recipe_fixed leaves. Or use fixed = inputs.")
        if not blank and fixed == "output" and abs(sum(recipe.values()) - 100) > 0.05:
            raise Problem(f"In [{name}], the recipe percents add up to {percent(sum(recipe.values()))}, not 100.")
        for good in list(recipe) + list(recipe_fixed):
            if good != MILK and good not in food_per_unit:
                raise Problem(f"In [{name}], {good} has no food value. Add it to food_per_unit in [general].")
        if MILK in recipe_fixed:
            raise Problem(f"In [{name}], milk has no amount to fix. Use a milk type from milk_food.")
        for good in list(recipe) + list(recipe_fixed) + list(other) + list(other_percent):
            if good != MILK and good not in goods and not (good in food_per_unit and good not in other and good not in other_percent):
                raise Problem(f'In [{name}], "{good}" is not a good.')
            if (good in recipe) + (good in recipe_fixed) + (good in other) + (good in other_percent) > 1:
                raise Problem(f"In [{name}], {good} is in more than one of recipe, recipe_fixed, other and other_percent. "
                              "Put it in one of them.")
        efficiency = read_efficiency(name, section.get("efficiency"))
        if efficiency is None:
            owners = methods[name]["owners"] if name in methods else []
            from_buildings = {building_efficiency[owner] for owner in owners if building_efficiency.get(owner)}
            if len(from_buildings) > 1:
                raise Problem(f"[{name}] is used by buildings with different efficiencies. Give it its own efficiency.")
            efficiency = from_buildings.pop() if from_buildings else default_efficiency
        fixed_food = sum(amount * food_per_unit[good] for good, amount in recipe_fixed.items())
        if fixed == "inputs":
            food_out = (sum(amount * food_per_unit[good] for good, amount in recipe.items()) + fixed_food) * efficiency
        elif not blank and fixed_food > food_out / efficiency + 1e-9:
            raise Problem(f"In [{name}], recipe_fixed holds {number(fixed_food)} food, more than the "
                          f"{number(food_out / efficiency)} input food. Lower the amounts or raise food_out.")
        settings[name] = {"fixed": fixed,"food_out": food_out, "recipe": recipe, "recipe_fixed": recipe_fixed, "other": other, "other_percent": other_percent,
                          "efficiency": efficiency, "round_food": food_decimals, "round_percent": percent_decimals,
                          "min_profit": read_profit(name, "min_profit", section.get("min_profit"), script_values) or default_min_profit,
                          "max_profit": read_profit(name, "max_profit", section.get("max_profit"), script_values) or default_max_profit}
    return food_per_unit, settings


def food_goods(setting):
    """The recipe goods: the ones with a share and the ones at a fixed amount."""
    return set(setting["recipe"]) | set(setting.get("recipe_fixed", {}))


def food_left(setting, food_per_unit):
    """The input food the recipe shares divide: all of it, less the food of the fixed goods."""
    fixed_food = sum(amount * food_per_unit[good] for good, amount in setting.get("recipe_fixed", {}).items())
    return setting["food_out"] / setting["efficiency"] - fixed_food


def target(setting, food_per_unit, food_per_provisions):
    """The input amounts and output the settings ask for."""
    food_in = food_left(setting, food_per_unit)
    amounts = {good: round(amount, setting.get("round_food", 5))
               for good, amount in setting.get("recipe_fixed", {}).items() if amount > 0}
    for good, share in setting["recipe"].items():
        if good != MILK and share > 0:
            # Fixed inputs: the number is the amount. Fixed output: a percent of the input food.
            amount = share if setting.get("fixed") == "inputs" else food_in * share / 100 / food_per_unit[good]
            amounts[good] = round(amount, setting.get("round_food", 5))
    amounts.update({good: round(amount, 5) for good, amount in setting["other"].items() if amount > 0})
    output = setting["food_out"] / food_per_provisions
    amounts.update({good: round(output * share / 100, setting.get("round_percent", 5))
                    for good, share in setting.get("other_percent", {}).items() if share > 0})
    return amounts, round(output, 5)


# ------------------------------------------------------------------ checks

def differs(old, new):
    return abs(old - new) > SAME * max(abs(old), abs(new), 1e-9)


def margin(inputs, output, prices):
    """Share of the output's value left after paying for the inputs. None when the output is worth nothing."""
    value_out = output * prices.get(PROVISIONS, 0)
    if value_out <= 0:
        return None
    return 1 - sum(prices.get(good, 0) * amount for good, amount in inputs.items()) / value_out


def same_profit(old, new):
    if old is None or new is None:
        return old == new
    if re.fullmatch(r"-?[0-9.]+", old) and re.fullmatch(r"-?[0-9.]+", new):
        return not differs(float(old), float(new))
    return old == new


def check(name, method, setting, places, food_per_unit, food_per_provisions, prices, script_values):
    """Findings for one method: food match, pending changes, margin and its profit range."""
    inputs, output = method["inputs"], method["output"]
    result = {"name": name, "inputs": inputs, "output": output, "changes": [], "mismatch": None,
              "min_profit": None, "max_profit": profit_value(method["max_profit"], script_values),
              "setting": setting, "places": places, "owners": method["owners"], "efficiency": 1.0}
    food_out = output * food_per_provisions
    if setting is None:
        result["food_out"] = food_out
        result["margin"] = margin(inputs, output, prices)
        return result
    efficiency = result["efficiency"] = setting["efficiency"]
    for key in ("min_profit", "max_profit"):
        result[key] = setting[key]["share"] if setting[key] else None
    new_max = setting["max_profit"]["file"] if setting["max_profit"] else None
    if not same_profit(method["max_profit"], new_max):
        result["changes"].append((MAX_PROFIT_LINE, method["max_profit"], new_max))
    milk = setting["recipe"].get(MILK, 0) / 100 * food_left(setting, food_per_unit)
    food_in = milk + sum(amount * food_per_unit[good] for good, amount in inputs.items()
                         if good in food_goods(setting))
    amounts, new_output = target(setting, food_per_unit, food_per_provisions)
    # Milk types make food but are not inputs in the building file
    milk_types = {good: amount for good, amount in amounts.items() if is_milk_type(good)}
    amounts = {good: amount for good, amount in amounts.items() if good not in milk_types}
    milk += sum(amount * food_per_unit[good] for good, amount in milk_types.items())
    food_in += sum(amount * food_per_unit[good] for good, amount in milk_types.items())
    # The rounded amounts set the food to match, so a rounding difference is not a mismatch.
    # Half the change tolerance, so a change that comes from the food always shows as a mismatch too.
    food_wanted = milk + sum(amount * food_per_unit[good] for good, amount in amounts.items() if good in food_goods(setting))
    if abs(food_in - food_wanted) * efficiency > SAME / 2 * max(food_out, 1e-9):
        result["mismatch"] = (food_in, food_out)
    for good in sorted(set(inputs) | set(amounts)):
        old, new = inputs.get(good), amounts.get(good)
        # A method whose food does not match is written exactly, however small the change
        if old is None or new is None or differs(old, new) or (result["mismatch"] and old != new):
            result["changes"].append((good, old, new))
    if differs(output, new_output):
        result["changes"].append(("output", output, new_output))
    # The note alone is not a change. It goes in with the next real one.
    if result["changes"] and len(places) == 1 and NOTE not in places[0][2]:
        result["changes"].append(("generator note", None, ""))
    result["amounts"], result["new_output"], result["milk"] = amounts, new_output, milk_types
    result["food_out"] = setting["food_out"]
    result["margin"] = margin(amounts, new_output, prices)
    return result


def recipe_text(setting, inputs, food_per_unit):
    fixed = " ".join(f"{good} {number(amount)} fixed" for good, amount in (setting or {}).get("recipe_fixed", {}).items())
    if setting is not None and setting.get("fixed") == "inputs":
        return " ".join(f"{good} {number(amount)}" for good, amount in setting["recipe"].items()) + " fixed" + (" " + fixed if fixed else "")
    if setting is not None:
        shares = setting["recipe"]
    else:
        food = {good: amount * food_per_unit[good] for good, amount in inputs.items() if good in food_per_unit}
        total = sum(food.values())
        shares = {good: 100 * value / total for good, value in food.items()} if total else {}
    parts = sorted(shares.items(), key=lambda item: -item[1])
    return " ".join([f"{good} {percent(share)}%" for good, share in parts] + ([fixed] if fixed else [])) or "no food input"


def below_min(result):
    return result["margin"] is not None and result["min_profit"] is not None and result["margin"] < result["min_profit"] - 1e-9


def above_max(result):
    return result["margin"] is not None and result["max_profit"] is not None and result["margin"] > result["max_profit"] + 1e-9


# ------------------------------------------------------------------ report

def report(prices, food_per_provisions, methods, food_per_unit, settings, script_values):
    places = locate(list(set(methods) | set(settings)))
    results, groups = [], {}
    for name, method in methods.items():
        result = check(name, method, settings.get(name), places[name], food_per_unit, food_per_provisions, prices, script_values)
        results.append(result)
        place = places[name][0] if places[name] else (None, 0)
        owner = method["owners"][0] if method["owners"] else "no building uses it"
        groups.setdefault((owner, place[0]), []).append((place[1], result))

    not_found = [name for name in settings if name not in methods]
    not_in_settings = [result for result in results if result["setting"] is None]
    to_change = [result for result in results if result["setting"] is not None and result["changes"] and len(result["places"]) == 1]
    mismatched = [result for result in results if result["mismatch"]]
    unprofitable = [result for result in results if result["margin"] is not None and result["margin"] < 0]
    blocked = [result for result in results if result["setting"] is not None and len(result["places"]) != 1]
    low = [result for result in results if below_min(result)]
    high = [result for result in results if above_max(result)]

    counts = [f"{len(methods)} found", f"{len(settings)} in settings"]
    for items, text, colour in ((to_change, "to change", warning), (mismatched, "food mismatch", warning),
                                (unprofitable, "unprofitable", bad), (low, "below min profit", warning),
                                (high, "above max profit", warning), (not_in_settings, "not in settings", missing),
                                (not_found, "not found", bad), (blocked, "cannot write", bad)):
        if items:
            counts.append(colour(f"{len(items)} {text}"))
    print(title("provisions methods") + "   " + quiet(" · ").join(counts))

    width = max((len(name) for name in methods), default=0) + 2
    order = sorted(groups.items(), key=lambda item: (str(item[0][1] or "~"), min(position for position, _ in item[1])))
    changing = {id(result) for result in to_change}
    problems = {id(result) for result in results if id(result) not in changing and (details(result) or result["setting"] is None)}
    # Three parts, so what Apply writes never mixes with what stays: changes, then no change, then problems
    for heading, picked, colour in ((f"WILL CHANGE  {methods_text(len(changing))}", changing, warning),
                                    (f"NO CHANGE  {methods_text(len(results) - len(changing) - len(problems))}", None, quiet),
                                    (f"NEEDS A LOOK  {methods_text(len(problems))}", problems, bad)):
        chosen = [(owner, path, sorted((entry for entry in entries if (id(entry[1]) in picked if picked is not None else
                                                                      id(entry[1]) not in changing | problems)),
                                       key=lambda entry: entry[0]))
                  for (owner, path), entries in order]
        chosen = [group for group in chosen if group[2]]
        if not chosen:
            continue
        print()
        print(colour(heading))
        for owner, path, entries in chosen:
            print()
            print(building_name(owner) + "  " + quiet(shown_path(path) if path else "game files only"))
            for index, (_, result) in enumerate(entries):
                last = index == len(entries) - 1
                branch, stem = ("└── ", "    ") if last else ("├── ", "│   ")
                print(quiet(branch) + method_line(result, width, food_per_unit))
                lines = change_lines(result) if picked is changing else details(result) if picked is problems else []
                for line in lines:
                    print(quiet(stem + "  ") + line)

    if not_found:
        print()
        print(bad("no method with this name:"))
        for name in not_found:
            print("  " + name)
    print()
    if not_in_settings:
        print(missing(f"{press('Import new methods', '--import')} to add {methods_text(len(not_in_settings))}"))
    if to_change:
        print(warning(f"{press('Apply', '--apply')} to write {methods_text(len(to_change))}"))
    if not not_in_settings and not to_change:
        print(method_name("all methods match"))
    return to_change, results


def method_line(result, width, food_per_unit):
    setting = result["setting"]
    inputs = result.get("amounts", result["inputs"])
    food = f"{number(result['food_out'])} food"
    if result["efficiency"] != 1:
        food += quiet(f" at {percent(result['efficiency'] * 100)}%")
    parts = [pad(method_name(result["name"]), width), pad(food, 18), pad(recipe_text(setting, inputs, food_per_unit), 30)]
    if result["margin"] is None:
        parts.append(quiet("no price"))
    else:
        text = f"{result['margin'] * 100:+.0f}%"
        parts.append(bad(text + " unprofitable") if result["margin"] < 0 else quiet(text))
        if below_min(result):
            parts.append(warning(f"below min {result['min_profit'] * 100:+.0f}%"))
        if above_max(result):
            parts.append(warning(f"above max {result['max_profit'] * 100:+.0f}%"))
    if setting is None:
        parts.append(missing("not in settings"))
    return " ".join(parts)


def change_lines(result):
    """One line for each value Apply writes: old in grey, new in yellow. Then why, in grey."""
    lines = []
    for good, old, new in result["changes"]:
        if good == "generator note":
            lines.append(warning("+ generator note"))
            continue
        old, new = (number(value) if isinstance(value, float) else value for value in (old, new))
        if old is None:
            lines.append(pad(good, 14) + warning(f"+ {new}"))
        elif new is None:
            lines.append(pad(good, 14) + quiet(f"{old} → ") + warning("removed"))
        else:
            lines.append(pad(good, 14) + quiet(f"{old} → ") + warning(str(new)))
    if result["mismatch"]:
        food_in, food_out = result["mismatch"]
        if abs(food_in * result["efficiency"] - food_out) <= SAME / 2 * max(food_out, 1e-9):
            text = f"why: round_food_inputs is {result['setting']['round_food']} decimals"
        else:
            text = f"why: today the inputs hold {number(round(food_in, 3))} food for {number(round(food_out, 3))} food out"
            if result["efficiency"] != 1:
                text += f", which needs {number(round(food_out / result['efficiency'], 3))} in at {percent(result['efficiency'] * 100)}%"
        lines.append(quiet(text))
    return lines


def details(result):
    lines = []
    if result["mismatch"]:
        food_in, food_out = result["mismatch"]
        text = f"input food {number(round(food_in, 3))}, output food {number(round(food_out, 3))}"
        if result["efficiency"] != 1:
            text += f", {percent(result['efficiency'] * 100)}% needs {number(round(food_out / result['efficiency'], 3))} in"
        lines.append(warning(text))
    if len(result["places"]) > 1:
        lines.append(bad(f"defined {len(result['places'])} times, cannot write it"))
    elif not result["places"]:
        lines.append(bad("only in vanilla, copy it into the mod first"))
    if result["changes"]:
        changes = []
        for good, old, new in result["changes"]:
            old, new = (number(value) if isinstance(value, float) else value for value in (old, new))
            if old is None:
                changes.append(f"+{good} {new}".strip())
            elif new is None:
                changes.append(f"-{good} {old}")
            else:
                changes.append(f"{good} {old} → {new}")
        lines.append(quiet(" · ".join(changes)))
    return lines


# ------------------------------------------------------------------ apply

def apply(results, goods, food_per_unit, into=None, spare=()):
    """Works out every file's new text first, so a problem stops the run before anything is written."""
    texts = {}
    for result in results:
        path = result["places"][0][0]
        if path not in texts:
            texts[path] = path.read_text(encoding="utf-8-sig")
        spans = block_span(texts[path], result["name"])
        if len(spans) != 1:
            raise Problem(f"{result['name']} is no longer defined once in {path.name}. Nothing was written.")
        start, end = spans[0]
        texts[path] = texts[path][:start] + rewrite(texts[path][start:end], result, goods, food_per_unit) + texts[path][end:]
    # After the provisions methods, so an added spare labor method goes after their new text
    for plan in spare:
        path = plan["path"]
        if path not in texts:
            texts[path] = path.read_text(encoding="utf-8-sig")
        text = texts[path]
        if plan["old_output"] is None:
            spans = block_span(text, plan["after"])
            if len(spans) != 1:
                raise Problem(f"{plan['after']} is no longer defined once in {path.name}. Nothing was written.")
            start = end = spans[0][1]
            indent = re.match(r"[ \t]*", text[spans[0][0]:]).group(0)
            block = "\n\n" + spare_block(plan, indent)
        else:
            spans = block_span(text, plan["name"])
            if len(spans) != 1:
                raise Problem(f"{plan['name']} is no longer defined once in {path.name}. Nothing was written.")
            start, end = spans[0]
            block = spare_block(plan, re.match(r"[ \t]*", text[start:]).group(0))
        texts[path] = text[:start] + block + text[end:]
    names = [result["name"] for result in results] + [plan["name"] for plan in spare]
    contents = {path: ("﻿" + text).encode("utf-8") for path, text in texts.items()}
    folder = write_with_backup(contents, "apply", names, into)
    print(method_name(f"wrote {methods_text(len(names))} in {files_text(len(texts))}") + quiet(f"   backup {folder.name}"))


def spare_block(plan, indent):
    return "\n".join([
        f"{indent}{plan['name']} = {{ {NOTE}",
        f"{indent}\t# Extra harvest with no inputs, so the AI margin check on the last slot always passes.",
        f"{indent}\tproduced = {plan['good']}",
        f"{indent}\toutput = {number(plan['output'])}",
        f"{indent}\tcategory = building_maintenance",
        f"{indent}}}"])


# ------------------------------------------------------------------ spare labor

def primary_good(block, goods):
    """The good of the building's first method slot."""
    for key, _, value in block:
        if key in ("unique_production_methods", "possible_production_methods") and isinstance(value, list):
            for _, _, method in value:
                good = get(method, "produced") if isinstance(method, list) else None
                if good in goods and good != PROVISIONS:
                    return good
            return None
    return None


def spare_labor(buildings, goods, prices, results):
    """Reports each spare_labor method and returns the ones Apply writes."""
    wanted = {}
    for name, section in read_settings_file(SETTINGS_FILE).items():
        method = section.get(SPARE_LABOR, "").strip()
        if method and method.lower() != "none":
            if not re.fullmatch(r"\w+", method):
                raise Problem(f'In [{name}], spare_labor must be a method name, but it is "{method}".')
            wanted[name] = method
    if not wanted:
        return []
    general = next(section for name, section in read_settings_file(SETTINGS_FILE).items() if name.lower() == "general")
    spare_output = read_number("general", "spare_labor_output", general.get("spare_labor_output", ""), above_zero=True)
    if spare_output is None:
        raise Problem("A building sets spare_labor, so [general] needs spare_labor_output.")
    places = locate(list(wanted.values()))
    plans = []
    print()
    print(title("spare labor"))
    for building, name in wanted.items():
        good = primary_good(buildings[building][0], goods)
        if not prices.get(good):
            raise Problem(f"[{building}] sets spare_labor, but its first method slot makes no good with a price.")
        output = spare_output
        plan = {"name": name, "good": good, "output": output, "old_output": None}
        found = places[name]
        if len(found) > 1:
            raise Problem(f"{name} is defined {len(found)} times. Remove the copies first.")
        if found:
            path, start, _ = found[0]
            text = path.read_text(encoding="utf-8-sig")
            end = next(span_end for span_start, span_end in block_span(text, name) if span_start == start)
            old = text[start:end]
            match = re.search(r"(?m)^[ \t]*output\s*=\s*([0-9.]+)", old)
            plan["old_output"] = float(match.group(1)) if match else 0.0
            plan["path"] = path
            changed = (differs(plan["old_output"], output) or re.search(r"(?m)^[ \t]*produced\s*=\s*" + good + r"\b", old) is None
                       or NOTE not in old)
        else:
            anchors = [result for result in results if building in result["owners"] and len(result["places"]) == 1]
            if not anchors:
                raise Problem(f"[{building}] sets spare_labor, but none of its provisions methods is in the mod files.")
            path = anchors[0]["places"][0][0]
            last = max((result["places"][0][1], result["name"]) for result in anchors if result["places"][0][0] == path)
            plan["path"], plan["after"] = path, last[1]
            changed = True
        line = f"{pad(building_name(building), 28)} {pad(method_name(name), 26)} {good} {number(output)}"
        if not changed:
            print(line)
            continue
        print(line + "  " + warning("+ new method" if plan["old_output"] is None else f"output {number(plan['old_output'])} → {number(output)}"))
        plans.append(plan)
    print()
    print(warning(f"{press('Apply', '--apply')} to write {methods_text(len(plans))}") if plans else method_name("all spare labor methods match"))
    return plans


def rewrite(block, result, goods, food_per_unit):
    """The block with its note, input amounts, output and debug_max_profit set. Other lines and their notes stay."""
    lines = block.split("\n")
    if len(lines) < 3:
        raise Problem(f"{result['name']} is written on one line. Write it over several lines first.")
    setting = result["setting"]
    amounts, output = result["amounts"], result["new_output"]
    food = sum(amount * food_per_unit[good] for good, amount in amounts.items() if good in food_goods(setting))
    food += setting["recipe"].get(MILK, 0) / 100 * food_left(setting, food_per_unit)
    food += sum(amount * food_per_unit[good] for good, amount in result.get("milk", {}).items())
    output_note = f"# input food {number(round(food, 2))}, output food {number(round(result['food_out'], 2))}"
    max_profit = setting["max_profit"]["file"] if setting["max_profit"] else None
    first = re.sub(r"\{.*$", "{ " + NOTE, lines[0])
    body, written = [], set()
    for line in lines[1:-1]:
        profit = re.match(r"^([ \t]*)" + MAX_PROFIT_LINE + r"(\s*=\s*)(\S+)(.*)$", line)
        if profit:
            if max_profit is not None:
                body.append(f"{profit.group(1)}{MAX_PROFIT_LINE}{profit.group(2)}{max_profit}{profit.group(4)}")
                written.add(MAX_PROFIT_LINE)
            continue
        match = re.match(r"^([ \t]*)(\w+)(\s*=\s*)([0-9.]+)(.*)$", line)
        if match and match.group(2) in goods:
            good = match.group(2)
            if good in amounts:
                body.append(f"{match.group(1)}{good}{match.group(3)}{number(amounts[good])}{match.group(5)}")
                written.add(good)
            continue
        if match and match.group(2) == "output":
            body.append(f"{match.group(1)}output{match.group(3)}{number(output)} {output_note}")
            written.add("output")
            continue
        body.append(line)
    new_goods = [good for good in amounts if good not in written]
    if new_goods or "output" not in written:
        produced = next((index for index, line in enumerate(body) if re.match(r"^[ \t]*produced\s*=", line)), None)
        if produced is None:
            raise Problem(f"{result['name']} has no produced line.")
        indent = re.match(r"^[ \t]*", body[produced]).group(0)
        if "output" not in written:
            # The building files keep output under produced
            body.insert(produced + 1, f"{indent}output = {number(output)} {output_note}")
        body[produced:produced] = [f"{indent}{good} = {number(amounts[good])}" for good in new_goods]
    if max_profit is not None and MAX_PROFIT_LINE not in written:
        # The line goes under category, where the building files keep it
        category = next((index for index, line in enumerate(body) if re.match(r"^[ \t]*category\s*=", line)), None)
        anchor = category if category is not None else next(
            index for index, line in enumerate(body) if re.match(r"^[ \t]*output\s*=", line))
        indent = re.match(r"^[ \t]*", body[anchor]).group(0)
        body.insert(anchor + 1, f"{indent}{MAX_PROFIT_LINE} = {max_profit}")
    return "\n".join([first] + body + [lines[-1]])


# ------------------------------------------------------------------ backups

def backups():
    """Backup folders, newest first."""
    folder = long_path(BACKUP_FOLDER)
    if not folder.is_dir():
        return []
    return sorted((path for path in folder.iterdir() if path.is_dir() and BACKUP_NAME.fullmatch(path.name)),
                  key=lambda path: path.name, reverse=True)


def write_with_backup(contents, label, method_names, into=None):
    """Writes {path: bytes}, and deletes each path whose bytes are None. Saves each file before and after the write,
    and the settings used, then keeps the newest 5.

    into is a backup that the window made a moment before for the same Apply. The files go into it, so that one
    Apply is one backup. A file it already holds keeps its "before" copy, which is the older one."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder, count = long_path(Path(into) if into else BACKUP_FOLDER / stamp), 1
    while not into and folder.exists():
        folder, count = long_path(BACKUP_FOLDER) / f"{stamp}_{count}", count + 1
    for path in contents:
        saved = folder / "before" / path.relative_to(MOD_FOLDER)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not saved.exists():
            shutil.copy2(path, saved)
    if SETTINGS_FILE.exists():
        shutil.copy2(SETTINGS_FILE, folder / "settings.txt")
    info = folder / "info.txt"
    lines = info.read_text(encoding="utf-8").splitlines() if into and info.exists() else [label]
    info.write_text("\n".join(lines + method_names) + "\n", encoding="utf-8")
    for path, content in contents.items():
        if content is None:
            path.unlink(missing_ok=True)
            continue
        path.write_bytes(content)
        saved = folder / "after" / path.relative_to(MOD_FOLDER)
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
    for old in backups()[BACKUPS_KEPT:]:
        shutil.rmtree(old)
    return folder


def backup_files(folder, part):
    root = folder / part
    return {path.relative_to(root): path for path in root.rglob("*") if path.is_file()} if root.is_dir() else {}


def list_backups():
    items = backups()
    if not items:
        print(quiet("no backups yet"))
        return
    print(title("backups") + quiet("   newest first, 5 kept"))
    for index, folder in enumerate(items, 1):
        info = (folder / "info.txt").read_text(encoding="utf-8").splitlines() if (folder / "info.txt").exists() else ["?"]
        files = sorted(backup_files(folder, "before"))
        what = info[0] + (f" · {methods_text(len(info) - 1)}" if len(info) > 1 else "")
        print(f"{warning(str(index))}  {folder.name[:10]} {folder.name[11:19].replace('-', ':')}  {what} · {files_text(len(files))}")
        for relative in files:
            print(quiet(f"     {relative.as_posix()}"))


def restore(choice, force):
    items = backups()
    if not items:
        raise Problem("There are no backups yet.")
    if not 1 <= choice <= len(items):
        raise Problem(f"There is no backup {choice}. Run with --backups to list them.")
    folder = items[choice - 1]
    before, after = backup_files(folder, "before"), backup_files(folder, "after")
    changed = [relative for relative, saved in after.items()
               if (MOD_FOLDER / relative).exists() and (MOD_FOLDER / relative).read_bytes() != saved.read_bytes()]
    if changed and not force:
        raise Problem("These files changed after that backup. Restoring them would also undo those changes:\n  "
                      + "\n  ".join(relative.as_posix() for relative in changed)
                      + "\nAdd --force to restore anyway.")
    contents = {MOD_FOLDER / relative: saved.read_bytes() for relative, saved in before.items()}
    # A file that the backed-up run created did not exist before it, so the restore deletes it
    contents.update({MOD_FOLDER / relative: None for relative in after if relative not in before})
    new_folder = write_with_backup(contents, f"restore of {folder.name}", [])
    print(method_name(f"restored {files_text(len(contents))} from {folder.name}") + quiet(f"   backup {new_folder.name}"))
    for path in sorted(contents):
        print(quiet(f"  {path.relative_to(MOD_FOLDER).as_posix()}" + ("  (deleted)" if contents[path] is None else "")))


# ------------------------------------------------------------------ import

def derive_food_values(methods, food_per_provisions, known):
    """Food per unit for goods the settings do not have yet, read from today's methods.

    A good is food when it is some method's only input or its largest input. Its value comes from the
    methods where it is the only food, and the largest such value wins, since no method gains food."""
    food = set(known)
    for method in methods.values():
        if method["inputs"]:
            food.add(max(method["inputs"], key=method["inputs"].get))
    values = {}
    for method in methods.values():
        food_inputs = [good for good in method["inputs"] if good in food]
        if len(food_inputs) == 1 and food_inputs[0] not in known and method["inputs"][food_inputs[0]] > 0:
            good = food_inputs[0]
            value = round(method["output"] * food_per_provisions / method["inputs"][good], 2)
            values[good] = max(values.get(good, 0), value)
    return values


def import_methods(methods, food_per_provisions, food_per_unit, settings):
    new = {name: method for name, method in methods.items() if name not in settings}
    if not new:
        print(method_name("nothing new to import"))
        return
    added_food = derive_food_values(methods, food_per_provisions, food_per_unit)
    all_food = {**added_food, **food_per_unit}
    places = locate(list(new))
    sections, last_owner = [], None
    order = sorted(new.items(), key=lambda item: (str(places[item[0]][0][0]) if places[item[0]] else "~",
                                                  places[item[0]][0][1] if places[item[0]] else 0))
    for name, method in order:
        food = {good: amount * all_food[good] for good, amount in method["inputs"].items() if good in all_food}
        other = {good: amount for good, amount in method["inputs"].items() if good not in all_food}
        total = sum(food.values())
        recipe = {good: round(100 * value / total, 2) for good, value in food.items()} if total else {MILK: 100}
        if total:
            largest = max(recipe, key=recipe.get)
            recipe[largest] = round(recipe[largest] + 100 - sum(recipe.values()), 2)
        owner = ", ".join(method["owners"]) or "shared method"
        where = shown_path(places[name][0][0]) if places[name] else "game files only"
        lines = [f"# {owner} ({where})"] if owner != last_owner else []
        last_owner = owner
        lines += [f"[{name}]",
                  f"food_out = {number(method['output'] * food_per_provisions)}",
                  "recipe = " + map_text(recipe)]
        if other:
            lines.append("other = " + map_text(other))
        if method["max_profit"] is not None:
            value = method["max_profit"]
            lines.append("max_profit = " + (number(float(value) * 100) if re.fullmatch(r"-?[0-9.]+", value) else value))
        sections.append(("\n\n\n" if lines[0].startswith("#") else "\n\n") + "\n".join(lines))

    if SETTINGS_FILE.exists():
        text = SETTINGS_FILE.read_text(encoding="utf-8-sig").rstrip("\n")
        if added_food:
            # Milk types belong to milk_food, where read_settings found them
            text = merge_food_values(text, {good: value for good, value in all_food.items() if not is_milk_type(good)})
    else:
        text = SETTINGS_HEADER + "[general]\nefficiency = 100\nfood_per_unit = " + food_table(all_food)
    SETTINGS_FILE.write_text(text + "".join(sections) + "\n", encoding="utf-8-sig", newline="\n")
    print(method_name(f"added {methods_text(len(sections))} to {SETTINGS_FILE.name}"))
    for good, value in sorted(added_food.items()):
        print(quiet(f"  food per unit: {good} {number(value)}"))


def map_text(values):
    return "{ " + ", ".join(f'"{good}": {number(value)}' for good, value in values.items()) + " }"


def food_table(values):
    rows = [f'    "{good}": {number(value)},' for good, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))]
    return "{\n" + "\n".join(rows) + "\n}"


def merge_food_values(text, values):
    match = re.search(r"(?ms)^food_per_unit\s*=\s*\{.*?\}", text)
    table = "food_per_unit = " + food_table(values)
    if match:
        return text[:match.start()] + table + text[match.end():]
    general = re.search(r"(?m)^\[general\][^\n]*\n", text)
    if not general:
        raise Problem("The settings file needs a [general] section.")
    return text[:general.end()] + table + "\n" + text[general.end():]


# ------------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser(description="Keeps every provisions production method in line with provisions_methods_settings.txt.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--import", dest="import_methods", action="store_true",
                        help="add methods that are not in the settings yet")
    action.add_argument("--apply", action="store_true", help="write the recipes into the building files")
    action.add_argument("--backups", action="store_true", help="list the backups")
    action.add_argument("--restore", nargs="?", type=int, const=1, metavar="N",
                        help="undo to backup N (1 is the newest)")
    parser.add_argument("--force", action="store_true", help="with --restore: restore files that changed after the backup")
    parser.add_argument("--into-backup", type=Path, metavar="FOLDER",
                        help="with --apply: add to this backup, which the window made for the same Apply")
    parser.add_argument("--settings", type=Path, metavar="FILE", help="report on this settings file instead, for a dry run")
    arguments = parser.parse_args()
    if arguments.settings:
        if arguments.apply or arguments.import_methods:
            raise Problem("--settings is only for a report. It cannot go with --apply or --import.")
        global SETTINGS_FILE
        SETTINGS_FILE = arguments.settings

    if arguments.backups:
        list_backups()
        return
    if arguments.restore is not None:
        restore(arguments.restore, arguments.force)
        return
    goods, building_names, prices, food_per_provisions, methods = read_game()
    script_values = read_script_values()
    if arguments.import_methods:
        food_per_unit, settings = (read_settings(goods, building_names, methods, script_values)
                                   if SETTINGS_FILE.exists() else ({}, {}))
        import_methods(methods, food_per_provisions, food_per_unit, settings)
        return
    if not SETTINGS_FILE.exists():
        raise Problem("There is no settings file yet. Run with --import to make it from today's methods.")
    food_per_unit, settings = read_settings(goods, building_names, methods, script_values)
    to_change, results = report(prices, food_per_provisions, methods, food_per_unit, settings, script_values)
    spare = spare_labor(building_names, goods, prices, results)
    if arguments.apply and (to_change or spare):
        print()
        apply(to_change, goods, food_per_unit, arguments.into_backup, spare)


if __name__ == "__main__":
    try:
        main()
    except Problem as problem:
        print(bad(str(problem)))
        sys.exit(1)
