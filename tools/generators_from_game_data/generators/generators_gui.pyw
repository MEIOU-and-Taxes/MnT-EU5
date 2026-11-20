"""
MnT GENERATORS

A window for one generator's settings files, with buttons that run the generator.
Open it with "MnT Provisions.bat" or "MnT Building Setup.bat" in the tools folder.
The first argument names the generator: provisions or buildings.

Edits keep the files' own layout and notes: only the values you change are rewritten.
Names in lists and maps come from the game files, so they are picked, not typed.
"""

import difflib
import importlib.util
import itertools
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont, messagebox, ttk
except ImportError:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "This Python has no tkinter, which the window needs.\n\nRun the Python installer "
                                         "again, choose Modify, and tick \"tcl/tk and IDLE\".", "MnT Generators", 0x10)
    raise

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # Without Pillow the window shows names instead of game icons
    Image = ImageDraw = ImageTk = None

HERE = Path(__file__).resolve().parent
MOD_ROOT = HERE.parents[2]
BUILDING_SETUP = HERE / "building_setup" / "building_setup.py"
PROVISIONS = HERE / "provisions_methods" / "provisions_methods.py"
# Outside the repo, so a bug seen once in normal use stays on record after its dialog closes
ERROR_LOG = Path.home() / ".cache" / "mnt-generators" / "errors.log"


def script_environment():
    """Generator runs print UTF-8, such as the arrows in their change tables, whatever the Windows code page is."""
    return dict(os.environ, FORCE_COLOR="1", MNT_GENERATORS_WINDOW="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def log_error(text, context):
    try:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG.open("a", encoding="utf-8") as log:
            log.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {context}\n{text.rstrip()}\n\n")
    except OSError:
        pass

# ------------------------------------------------------------------ colors

SIDEBAR, BG, FIELD, HOVER, BORDER, CONSOLE = "#18191c", "#1f2023", "#2a2c30", "#33363b", "#34363b", "#141517"
TEXT, MUTED, FAINT = "#e3e5e8", "#9a9fa8", "#6d727b"
ACCENT, ACCENT_HOVER, SELECTED = "#5b8cff", "#7aa2ff", "#2c3a5e"
WARN, BAD, GOOD = "#f0b232", "#ff6b6b", "#57d38c"
# The generators' terminal colors, made readable on a dark background
ANSI_COLORS = {"1": {"foreground": "#ffffff", "bold": True}, "2": {"foreground": FAINT}, "32": {"foreground": GOOD},
               "33": {"foreground": WARN}, "35": {"foreground": "#c77dff"}, "91": {"foreground": BAD},
               "1;34": {"foreground": "#7aa7ff", "bold": True}}
ANSI = re.compile(r"\033\[([0-9;]*)m")

# ------------------------------------------------------------------ what each setting is

# The window shows these instead of the longer notes in the settings files
HELP = {
    "report_building_types": "Building types the data dump reports.",
    "pop_types_for_levels": "Pop types that count toward levels.",
    "respect_technology": "Skip building types the owner cannot build yet.",
    "place_secondary_rgos": "Also place secondary RGO buildings.",
    "max_secondary_rgos_per_location": "Most secondary RGO building types in one location.",
    "place": "No: this building type is not placed.",
    "place_as_secondary": "This building type can be a secondary RGO.",
    "secondary_priority": "Higher wins ties between secondary RGO building types.",
    "ideal_rgo_multiplier": "Multiplies the level of the location's main RGO building.",
    "destroy_vanilla_building_levels_before_counting": "Remove this building type's vanilla levels first.",
    "pops_per_level": "Thousand pops per level.",
    "development_per_level": "One level per this much development.",
    "base_level_by_location_rank": "Levels added by location rank.",
    "additive_multiplier_per_development": "Added per development. 0.02 at 20 development gives 1.4x.",
    "additive_multiplier_per_population": "Added per thousand pops. 0.01 at 20,000 pops gives 1.2x.",
    "lake_multiplier": "Multiplier next to a lake.",
    "coastal_multiplier": "Multiplier on the coast.",
    "river_multiplier": "Multiplier by river size. Unlisted sizes count as 1.",
    "location_rank_multiplier": "Multiplier by location rank. Unlisted ranks count as 1.",
    "topography_multiplier": "Multiplier by topography. Unlisted topography counts as 1.",
    "vegetation_multiplier": "Multiplier by vegetation. Unlisted vegetation counts as 1.",
    "climate_multiplier": "Multiplier by climate. Unlisted climates count as 1.",
    "final_level_multiplier": "Multiplies the final level.",
    "round_levels": "How levels round.",
    "percentage_of_building_max_level": "Level cap, as a percent of the building type's max level.",
    "fixed_level": "Replaces the calculated level.",
    "fixed_level_floor": "Lowest level.",
    "fixed_level_ceiling": "Highest level.",
    "distribution_group": "Building types that share this level.",
    "food_per_unit": "Food in one unit of each good.",
    "milk_food": "Food in one unit of each milk type. Recipes use milk as an input with no good and no cost.",
    "efficiency": "Output food as a percent of input food. 100 when not set anywhere.",
    "other_percent": "Extra inputs as a percent of the provisions made.",
    "min_profit": "Flag methods below this profit.",
    "round_food_inputs": "Round food inputs to this many decimal places.",
    "round_percent_inputs": "Round percentage inputs to this many decimal places.",
    "fixed": "Which side stays when food values change. Output when not set. Each method can switch it.",
    "max_profit": "Flag methods above this profit. Also sets debug_max_profit.",
    "food_out": "Food made per level. 10 food is 1 provisions.",
    "recipe": "Each good's percent of the input food. Must total 100.",
    "recipe_fixed": "Food goods at a fixed amount. The recipe shares divide the food left.",
    "other": "Extra inputs in fixed amounts.",
}

YES_NO = {"kind": "choice", "choices": ["yes", "no"]}
BUILDING_FIELDS = {
    "report_building_types": {"kind": "list", "names": "buildings"},
    "pop_types_for_levels": {"kind": "list", "names": "pop_types"},
    "respect_technology": YES_NO,
    "place_secondary_rgos": YES_NO,
    "place": YES_NO,
    "place_as_secondary": YES_NO,
    "destroy_vanilla_building_levels_before_counting": YES_NO,
    "round_levels": {"kind": "choice", "choices": ["up", "down", "nearest"]},
    "base_level_by_location_rank": {"kind": "map", "names": "location_rank"},
    "river_multiplier": {"kind": "map", "names": "river"},
    "location_rank_multiplier": {"kind": "map", "names": "location_rank"},
    "topography_multiplier": {"kind": "map", "names": "topography"},
    "vegetation_multiplier": {"kind": "map", "names": "vegetation"},
    "climate_multiplier": {"kind": "map", "names": "climate"},
    "fixed_level": {"kind": "number_or_map", "names": "location_rank"},
    "distribution_group": {"kind": "list", "names": "buildings"},
}
PROVISIONS_FIELDS = {
    "food_per_unit": {"kind": "map", "names": "goods", "new_value": "10"},
    "milk_food": {"kind": "map", "names": "goods", "new_value": "5"},
    "efficiency": {"kind": "number"},
    "min_profit": {"kind": "profit"},
    "max_profit": {"kind": "profit"},
    "round_food_inputs": {"kind": "choice", "choices": ["0", "1", "2", "3", "4", "5"]},
    "round_percent_inputs": {"kind": "choice", "choices": ["0", "1", "2", "3", "4", "5"]},
    "fixed": {"kind": "choice", "choices": ["output", "inputs"]},
    "food_out": {"kind": "number"},
    "recipe": {"kind": "map", "names": "recipe", "new_value": "rest", "total": True},
    "recipe_fixed": {"kind": "map", "names": "recipe", "new_value": "10"},
    "other": {"kind": "map", "names": "goods", "new_value": "0.001"},
    "other_percent": {"kind": "map", "names": "goods", "new_value": "1"},
}


def mod_script_files():
    """The mod's script files, to find what else names a production method."""
    for folder in ("in_game", "main_menu"):
        yield from (MOD_ROOT / folder).rglob("*.txt")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_names(tool=None):
    """Every name the dropdowns offer, read from the game and mod files. Returns (names, problems)."""
    names, problems = {}, []

    def step(label, work):
        try:
            work()
        except BaseException as error:  # One missing source must not stop the others
            problems.append(f"Could not read {label}: {error}")

    building_setup = load_module(BUILDING_SETUP, "building_setup_for_window")
    game = []
    step("the game folder", lambda: game.append(building_setup.find_game_folder()))
    if game:
        def facts():
            for fact, folder in building_setup.FACT_FOLDERS.items():
                names[fact] = building_setup.read_definition_keys(game[0], folder)
            names["pop_types"] = ["all"] + building_setup.read_definition_keys(game[0], "pop_types")

        def buildings():
            every = sorted(building_setup.read_building_max_levels(game[0]))
            names["buildings"] = every
            names["rgo_buildings"] = [name for name in every if name.startswith(building_setup.RGO_PREFIX)]
            names["other_buildings"] = [name for name in every if not name.startswith(building_setup.RGO_PREFIX)]
        step("the location facts", facts)
        step("the building types", buildings)
        if getattr(tool, "names_from_loc", False):
            step("the English names", lambda: tool.loc.load(game[0]))
    names["river"] = list(building_setup.RIVER_SIZES)

    def provisions():
        module = load_module(PROVISIONS, "provisions_methods_for_window")
        goods, _, _, _, methods = module.read_game()
        names["goods"] = sorted(goods)
        names["recipe"] = [module.MILK] + sorted(goods)
        names["methods"] = sorted(methods)
        names["owners_of"] = {name: method["owners"] for name, method in methods.items()}
        names["method_owners"] = sorted({owner for method in methods.values() for owner in method["owners"]})
        values = module.read_script_values()
        names["profit"] = sorted(name for name in values if re.search("profit|margin", name)) or sorted(values)
        names["profit_values"] = values
    step("the provisions methods", provisions)
    return names, problems


# ------------------------------------------------------------------ settings files

NOTE = re.compile(r"(^|\s)#")  # A note starts at a # at the start of a line or after a space, as in the generators


def split_note(line):
    match = NOTE.search(line)
    if not match:
        return line, ""
    return line[:match.end() - 1], line[match.end() - 1:]


class SettingsFile:
    """A settings file as lines. Sections and settings point at line numbers, so edits keep the layout."""

    def __init__(self, path, kind):
        self.path, self.kind = path, kind
        self.load()

    def load(self):
        raw = self.path.read_bytes()
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        self.lines = raw.decode("utf-8-sig").split("\n")
        self.dirty = False
        self.parse()

    def content(self):
        """The bytes save writes."""
        return (b"\xef\xbb\xbf" if self.bom else b"") + "\n".join(self.lines).encode("utf-8")

    def save(self):
        self.path.write_text("\n".join(self.lines), encoding="utf-8-sig" if self.bom else "utf-8", newline="\n")
        self.dirty = False

    def parse(self):
        self.sections, current, notes, index = [], None, [], 0
        while index < len(self.lines):
            code, note = split_note(self.lines[index])
            text = code.strip()
            if not text:
                notes = notes + [note.lstrip("#").strip()] if note.strip() else []
                index += 1
                continue
            if text.startswith("[") and text.endswith("]"):
                current = {"name": text[1:-1].strip(), "header": index, "notes": notes, "settings": []}
                self.sections.append(current)
                notes, index = [], index + 1
                continue
            key, equals, value = text.partition("=")
            if equals and current is not None:
                value, end = value.strip(), index
                closer = {"{": "}", "[": "]"}.get(value[:1])
                if closer and not value.endswith(closer):
                    end = index + 1
                    while end < len(self.lines) - 1 and not split_note(self.lines[end])[0].strip().endswith(closer):
                        end += 1
                current["settings"].append({"key": key.strip().lower(), "start": index, "end": end,
                                            "note": note.lstrip("#").strip()})
                index = end + 1
            else:
                index += 1
            notes = []
        self.help = {}
        for section in self.sections:
            for setting in section["settings"]:
                if setting["note"] and setting["key"] not in self.help:
                    self.help[setting["key"]] = setting["note"]

    def names(self):
        return [section["name"] for section in self.sections]

    def section(self, name):
        return next((section for section in self.sections if section["name"] == name), None)

    def value(self, setting):
        """The value without notes. A list over several lines keeps its line breaks."""
        codes = [split_note(line)[0].rstrip() for line in self.lines[setting["start"]:setting["end"] + 1]]
        codes[0] = codes[0].partition("=")[2]
        return "\n".join(codes).strip()

    def set_value(self, setting, value):
        """Rewrites one setting. The note on its first line stays, in its column when the value fits before it."""
        first = self.lines[setting["start"]]
        code, note = split_note(first)
        prefix = re.match(r"^\s*[^=]*=\s*", first).group(0)
        new = (prefix + value.strip()).split("\n")
        if note:
            new[0] = (new[0].ljust(len(code)) if len(new[0]) < len(code) else new[0] + " ") + note
        self.lines[setting["start"]:setting["end"] + 1] = new

    def add_setting(self, section, key, value):
        settings = section["settings"]
        at = settings[-1]["end"] + 1 if settings else section["header"] + 1
        self.lines[at:at] = f"{key} = {value}".split("\n")
        self.parse()

    def remove_setting(self, setting):
        del self.lines[setting["start"]:setting["end"] + 1]
        self.parse()

    def add_section(self, name, settings):
        while self.lines and self.lines[-1] == "":
            self.lines.pop()
        self.lines += ["", "", f"[{name}]"] + [f"{key} = {value}" for key, value in settings] + [""]
        self.parse()

    def remove_section(self, section):
        start = section["header"] - len(section["notes"])
        end = section["settings"][-1]["end"] + 1 if section["settings"] else section["header"] + 1
        while end < len(self.lines) and self.lines[end].strip() == "":
            end += 1
        del self.lines[start:end]
        self.parse()


def parse_map(text):
    """{ "a": 1, "b": 2 } as [(a, 1), (b, 2)]. [] for None, and None when the text is not a map."""
    text = text.strip()
    if text.lower() in ("", "none"):
        return []
    if not (text.startswith("{") and text.endswith("}")):
        return None
    rows = []
    for part in text[1:-1].replace("\n", ",").split(","):
        if part.strip():
            name, colon, value = part.partition(":")
            if not colon:
                return None
            rows.append((name.strip().strip("\"'"), value.strip()))
    return rows


def parse_list(text):
    text = text.strip()
    if text.lower() in ("", "none"):
        return []
    if not (text.startswith("[") and text.endswith("]")):
        return None
    return [name.strip().strip("\"'") for name in text[1:-1].replace("\n", ",").split(",") if name.strip().strip("\"'")]


def map_text(rows, multiline=False):
    """One line when it is short, unless the value was written over several lines before."""
    if not rows:
        return "None"
    one_line = "{ " + ", ".join(f'"{name}": {value}' for name, value in rows) + " }"
    if len(one_line) <= 100 and not multiline:
        return one_line
    return "{\n" + "".join(f'    "{name}": {value},\n' for name, value in rows) + "}"


def list_text(names, multiline=False):
    if not names:
        return "None"
    one_line = "[ " + ", ".join(f'"{name}"' for name in names) + " ]"
    if len(one_line) <= 100 and not multiline:
        return one_line
    return "[\n" + "".join(f'    "{name}",\n' for name in names) + "]"


def short_name(name):
    """The sidebar drops the prefix every RGO building shares."""
    return name[len("RGO_building_"):] if name.startswith("RGO_building_") else name


TITLES = {"efficiency": "Food conversion efficiency", "fixed": "Fixed Inputs/Outputs"}


def setting_title(key):
    if key in TITLES:
        return TITLES[key]
    title = key.replace("_", " ").capitalize()
    return re.sub(r"\brgo(s?)\b", lambda match: "RGO" + match.group(1), title)


def placeholder(entry, variable, text):
    """Grey text inside an empty field. It takes the field's color, font and text position, so it looks like the
    field's own text. A click on it goes to the field."""
    style = ttk.Style(entry)
    name = entry.cget("style") or entry.winfo_class()
    padding = re.findall(r"\d+", str(style.lookup(name, "padding") or style.lookup(entry.winfo_class(), "padding") or "6"))
    label = tk.Label(entry, text=text, foreground=FAINT, cursor="xterm", padx=0, pady=0, borderwidth=0,
                     font=entry.cget("font") or "TkDefaultFont")
    label.bind("<Button-1>", lambda _: entry.focus_set())
    label.bind("<Enter>", lambda _: entry.event_generate("<Enter>"))

    def paint(*_):
        state = [flag for flag in entry.state() if flag in ("focus", "hover", "readonly", "disabled")]
        label.configure(background=style.lookup(name, "fieldbackground", state) or FIELD)

    def update(*_):
        if variable.get():
            label.place_forget()
        else:
            paint()
            label.place(x=int(padding[0]) + 2, rely=0.5, anchor="w")
    variable.trace_add("write", update)
    for event in ("<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>"):
        entry.bind(event, lambda _: entry.after_idle(paint), add="+")
    update()


# ------------------------------------------------------------------ value editors

class Editor:
    """One setting's control. changed turns on with the first edit, so untouched values keep their layout."""

    def __init__(self, parent, app, value, spec, on_change):
        self.app, self.spec, self.on_change, self.changed = app, spec, on_change, False
        self.frame = ttk.Frame(parent)

    def touch(self, *_):
        self.changed = True
        self.on_change()

    def names(self, current=()):
        listed = self.app.names.get(self.spec.get("names"), [])
        return list(listed) + [name for name in current if name not in listed]

    def shown(self, name):
        return shown_name(self.spec.get("tool"), self.spec.get("names"), name)

    def icon(self, name):
        icons = getattr(self.spec.get("tool"), "icons", None)
        return icons.building(name, 16) if icons and self.spec.get("names") in BUILDING_NAMES else None

    def choices(self, names):
        """(text, name, icon) for a ChoicePopup, in the game's order."""
        return [(self.shown(name), name, self.icon(name)) for name in names]


class ChoiceEditor(Editor):
    def __init__(self, parent, app, value, spec, on_change):
        super().__init__(parent, app, value, spec, on_change)
        choices = list(spec["choices"]) + ["None"]
        if value not in choices:
            choices.append(value)
        unset = value in ("", "None") and spec.get("hint") == "default"
        self.variable = tk.StringVar(value="default" if unset else value or "None")
        box = ttk.Combobox(self.frame, state="readonly", values=choices, textvariable=self.variable, width=12)
        box.bind("<<ComboboxSelected>>", self.touch)
        box.pack(side="left")

    def get(self):
        return self.variable.get()


class NumberEditor(Editor):
    """An empty field writes None."""

    hint = "not set"

    def __init__(self, parent, app, value, spec, on_change):
        super().__init__(parent, app, value, spec, on_change)
        self.variable = tk.StringVar(value="" if value.lower() == "none" else value)
        entry = self.field()
        entry.pack(side="left")
        placeholder(entry, self.variable, spec.get("hint", self.hint))
        self.variable.trace_add("write", self.touch)

    def field(self):
        return ttk.Entry(self.frame, textvariable=self.variable, width=12)

    def get(self):
        return self.variable.get().strip() or "None"


def profit_number(text, values):
    """A profit setting as a percent: a number is a percent already, a script value name is looked up.
    Empty when it cannot be read."""
    text = (text or "").strip()
    if re.fullmatch(r"-?([0-9]+\.?[0-9]*|\.[0-9]+)%?", text):
        return f"{float(text.rstrip('%')):g}%"
    if text in values:
        return f"{values[text] * 100:g}%"
    return ""


class ProfitEditor(NumberEditor):
    hint = "not set"

    def field(self):
        box = ttk.Combobox(self.frame, textvariable=self.variable, width=34, values=self.app.names.get("profit", []))
        # The number behind a script value name, so the name is not a mystery
        shown = ttk.Label(self.frame, style="Muted.TLabel")
        update = lambda *_: shown.configure(text=profit_number(self.variable.get(), self.app.names.get("profit_values", {})))
        self.variable.trace_add("write", update)
        update()
        self.frame.after_idle(lambda: shown.pack(side="left", padx=(10, 0)))
        return box


class TextEditor(Editor):
    """For a value the other controls cannot show."""

    def __init__(self, parent, app, value, spec, on_change):
        super().__init__(parent, app, value, spec, on_change)
        if "\n" not in value:
            variable = tk.StringVar(value=value)
            ttk.Entry(self.frame, textvariable=variable, width=60).pack(fill="x")
            variable.trace_add("write", self.touch)
            self.read = variable.get
            return
        self.widget = tk.Text(self.frame, height=min(value.count("\n") + 1, 14), width=60, undo=True, font=app.mono)
        app.dark_text(self.widget, FIELD)
        self.widget.insert("1.0", value)
        self.widget.edit_modified(False)
        self.widget.bind("<<Modified>>", self.text_modified)
        self.read = lambda: self.widget.get("1.0", "end-1c")
        self.widget.pack(fill="x")

    def text_modified(self, _):
        if self.widget.edit_modified():
            self.widget.edit_modified(False)
            self.touch()

    def get(self):
        return self.read()


def milk_source(good):
    """The herd behind a milk type: "camels" for "milk_camels". None for anything else."""
    return good[len("milk_"):] if good.startswith("milk_") else None


# Name lists whose keys have English names in the game files
LOC_NAMES = {"climate", "topography", "vegetation", "location_rank", "pop_types", "buildings", "rgo_buildings", "other_buildings"}
BUILDING_NAMES = {"buildings", "rgo_buildings", "other_buildings"}


def shown_name(tool, names, key):
    """The English name of a key from a name list, or the key when the game has none."""
    loc = getattr(tool, "loc", None)
    return (loc.name(key) if loc and names in LOC_NAMES else None) or key


def goods_choices(goods, tool):
    """(name, good, icon) for each good, sorted by name, for a ChoicePopup. A milk type shows as milk (its herd)."""
    icons, loc = getattr(tool, "icons", None), getattr(tool, "loc", None)

    def choice(good):
        source = milk_source(good) or good
        name = (loc.name(source) if loc else None) or source
        return (f"milk ({name.lower()})" if milk_source(good) else name, good, icons.good(source, 16) if icons else None)
    return sorted((choice(good) for good in goods), key=lambda choice: choice[0].lower())


class ChoicePopup(tk.Toplevel):
    """A dark list of choices, each with an optional icon, in columns that fit on the screen. It closes on a choice,
    Escape, a click outside it, or when the widget that opened it goes away."""
    ROW, ROWS, PAD = 26, 16, 8

    def __init__(self, anchor, x, y, choices, on_choose):
        super().__init__(anchor)
        self.withdraw()  # Hidden until it has its place, so it does not flash in the corner
        self.overrideredirect(True)
        self.configure(background=BORDER)
        self.on_choose, self.hovered = on_choose, None
        self.images = [image for _, _, image in choices if image]  # Tk drops an image that Python no longer holds
        font = tkfont.nametofont("TkDefaultFont")
        icon = 20 if self.images else 0
        columns = [choices[start:start + self.ROWS] for start in range(0, len(choices), self.ROWS)] or [[]]
        widths = [max([font.measure(label) for label, _, _ in column] + [60]) + icon + 2 * self.PAD for column in columns]
        height = self.ROW * max(len(column) for column in columns) + 2 * self.PAD
        self.canvas = tk.Canvas(self, width=sum(widths), height=height, background=FIELD, highlightthickness=0, borderwidth=0)
        self.canvas.pack(padx=1, pady=1)
        self.rows, left = [], 0
        for column, width in zip(columns, widths):
            for index, (label, value, image) in enumerate(column):
                top = self.PAD + index * self.ROW
                box = (left + 2, top, left + width - 2, top + self.ROW)
                back = self.canvas.create_rectangle(*box, fill=FIELD, outline="")
                if image:
                    self.canvas.create_image(left + self.PAD, top + self.ROW // 2, image=image, anchor="w")
                self.canvas.create_text(left + self.PAD + icon, top + self.ROW // 2, text=label, anchor="w", fill=TEXT, font=font)
                self.rows.append((box, back, value))
            left += width
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<Leave>", lambda _: self.highlight(None))
        self.bind("<Button-1>", self.click)
        self.bind("<Escape>", lambda _: self.destroy())
        anchor.bind("<Destroy>", lambda _: self.winfo_exists() and self.destroy(), add="+")
        self.update_idletasks()
        # Stay on the screen: move up as far as it needs to fit
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        x = max(0, min(x, self.winfo_screenwidth() - width))
        y = max(0, min(y, self.winfo_screenheight() - height - 48))
        self.attributes("-topmost", True)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.grab_set()
        self.focus_force()

    def row_at(self, x, y):
        return next((row for row in self.rows if row[0][0] <= x < row[0][2] and row[0][1] <= y < row[0][3]), None)

    def highlight(self, row):
        if row is not self.hovered:
            if self.hovered:
                self.canvas.itemconfigure(self.hovered[1], fill=FIELD)
            if row:
                self.canvas.itemconfigure(row[1], fill=SELECTED)
            self.hovered = row
            self.canvas.configure(cursor="hand2" if row else "")

    def motion(self, event):
        self.highlight(self.row_at(event.x, event.y))

    def click(self, event):
        # The grab sends clicks outside the popup here too, so a click outside closes it
        inside = 0 <= event.x_root - self.canvas.winfo_rootx() < self.canvas.winfo_width() and \
            0 <= event.y_root - self.canvas.winfo_rooty() < self.canvas.winfo_height()
        row = self.row_at(event.x_root - self.canvas.winfo_rootx(), event.y_root - self.canvas.winfo_rooty()) if inside else None
        if inside and not row:
            return
        self.destroy()
        if row:
            self.on_choose(row[2])


class MapEditor(Editor):
    """Rows of a picked name and a typed number. Goods show as their icon and name."""

    def __init__(self, parent, app, value, spec, on_change):
        super().__init__(parent, app, value, spec, on_change)
        self.rows, self.multiline = [], "\n" in value
        self.tool = spec.get("tool") if spec.get("names") in ("goods", "recipe") else None
        # Every row's name is as wide as the longest name, so the numbers line up and no name is cut
        self.name_width = max([len(self.shown(name)) for name, _ in parse_map(value) or []] +
                              [len(self.shown(name)) for name in self.names()] + [12]) + 2
        self.rows_frame = ttk.Frame(self.frame)
        self.rows_frame.pack(anchor="w")
        for name, number in parse_map(value):
            self.add_row(name, number)
        bottom = ttk.Frame(self.frame)
        bottom.pack(anchor="w", pady=(4, 0))
        self.adder = ttk.Button(bottom, text="+ Add", style="Ghost.TButton", command=self.show_goods)
        self.adder.pack(side="left")
        self.total = ttk.Label(bottom, style="Muted.TLabel")
        self.total.pack(side="left", padx=12)
        self.refresh()

    def add_row(self, name, number):
        row = ttk.Frame(self.rows_frame)
        row.pack(anchor="w", pady=2)
        name_variable, number_variable = tk.StringVar(value=name), tk.StringVar(value=number)
        entry = (row, name_variable, number_variable)
        if self.tool:
            image = self.tool.icons.good(name, 16)
            ttk.Label(row, text=" " + (self.tool.loc.name(name) or name), image=image or "", compound="left" if image else "none",
                      width=24).pack(side="left")
        else:
            image = self.icon(name)
            ttk.Label(row, text=self.shown(name), image=image or "", compound="left" if image else "none",
                      width=self.name_width).pack(side="left")
        ttk.Entry(row, textvariable=number_variable, width=9, justify="right").pack(side="left", padx=6)
        ttk.Button(row, text="✕", style="Icon.TButton", command=lambda: self.remove_row(entry)).pack(side="left")
        number_variable.trace_add("write", lambda *_: (self.touch(), self.refresh()))
        self.rows.append(entry)

    def remove_row(self, entry):
        entry[0].destroy()
        self.rows.remove(entry)
        self.touch()
        self.refresh()

    def numbers(self):
        total = 0.0
        for _, _, number in self.rows:
            try:
                total += float(number.get().rstrip("%"))
            except ValueError:
                pass
        return total

    def show_goods(self):
        used = {name.get() for _, name, _ in self.rows}
        left = [name for name in self.names() if name not in used]
        ChoicePopup(self.adder, self.adder.winfo_rootx(), self.adder.winfo_rooty() + self.adder.winfo_height(),
                    goods_choices(left, self.tool) if self.tool else self.choices(left), self.add_picked)

    def add_picked(self, name):
        number = self.spec.get("new_value", "1")
        if number == "rest":
            number = f"{max(0.0, 100 - self.numbers()):g}"
        self.add_row(name, number)
        self.touch()
        self.refresh()

    def refresh(self):
        used = {name.get() for _, name, _ in self.rows}
        left = [name for name in self.names() if name not in used]
        self.adder.configure(text="+ Add" if left or not self.names() else "all added")
        self.adder.state(["!disabled"] if left or not self.names() else ["disabled"])
        if not self.rows and not self.spec.get("total"):
            self.total.configure(text=self.spec.get("hint", ""), foreground=FAINT)
        elif not self.spec.get("total"):
            self.total.configure(text="")
        if self.spec.get("total"):
            total = self.numbers()
            good = abs(total - 100) < 0.001
            self.total.configure(text=f"total {total:g}%" + ("" if good else ", needs 100%"), foreground=MUTED if good else WARN)

    def get(self):
        return map_text([(name.get(), number.get().strip() or "0") for _, name, number in self.rows], self.multiline)


class ListEditor(Editor):
    """Tick boxes for a short list of names, picked chips for a long one."""

    def __init__(self, parent, app, value, spec, on_change):
        super().__init__(parent, app, value, spec, on_change)
        self.chosen, self.multiline = parse_list(value), "\n" in value
        every = self.names(self.chosen)
        if 0 < len(every) <= 16:
            self.ticks = {}
            for index, name in enumerate(every):
                variable = tk.BooleanVar(value=name in self.chosen)
                ttk.Checkbutton(self.frame, text=self.shown(name), variable=variable, command=self.touch).grid(
                    row=index // 3, column=index % 3, sticky="w", padx=(0, 18), pady=2)
                self.ticks[name] = variable
            return
        self.ticks = None
        self.chips = ttk.Frame(self.frame)
        self.chips.pack(anchor="w")
        self.adder = ttk.Button(self.frame, text="+ Add", style="Ghost.TButton", command=self.show_choices)
        self.adder.pack(anchor="w", pady=(4, 0))
        self.show_chips()

    def show_chips(self):
        for child in self.chips.winfo_children():
            child.destroy()
        if not self.chosen:
            ttk.Label(self.chips, text=self.spec.get("hint", "none"), style="Faint.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 2))
        for index, name in enumerate(self.chosen):
            chip = ttk.Frame(self.chips, style="Chip.TFrame", padding=(8, 2, 2, 2))
            chip.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 6), pady=3)
            image = self.icon(name)
            ttk.Label(chip, text=self.shown(name), image=image or "", compound="left" if image else "none",
                      style="Chip.TLabel").pack(side="left")
            ttk.Button(chip, text="✕", style="ChipX.TButton", command=lambda n=name: self.remove(n)).pack(side="left", padx=(4, 0))
        left = [name for name in self.names() if name not in self.chosen]
        self.adder.configure(text="+ Add" if left else "all added")
        self.adder.state(["!disabled"] if left else ["disabled"])

    def show_choices(self):
        left = [name for name in self.names() if name not in self.chosen]
        ChoicePopup(self.adder, self.adder.winfo_rootx(), self.adder.winfo_rooty() + self.adder.winfo_height(),
                    self.choices(left), self.add_picked)

    def add_picked(self, name):
        self.chosen.append(name)
        self.touch()
        self.show_chips()

    def remove(self, name):
        self.chosen.remove(name)
        self.touch()
        self.show_chips()

    def get(self):
        if self.ticks is not None:
            return list_text([name for name, variable in self.ticks.items() if variable.get()], self.multiline)
        return list_text(self.chosen, self.multiline)


class NumberOrMapEditor(Editor):
    """fixed_level: not set, one level everywhere, or a level per location rank."""

    MODES = ["not set", "same everywhere", "by location rank"]

    def __init__(self, parent, app, value, spec, on_change):
        super().__init__(parent, app, value, spec, on_change)
        self.value = value
        mode = 0 if value.lower() in ("", "none") else 2 if value.startswith("{") else 1
        self.mode = ttk.Combobox(self.frame, state="readonly", values=self.MODES, width=18)
        self.mode.current(mode)
        self.mode.bind("<<ComboboxSelected>>", lambda _: (self.show(), self.touch()))
        self.mode.pack(anchor="w")
        self.inner = None
        self.show()

    def show(self):
        if self.inner:
            self.inner.frame.destroy()
            self.inner = None
        mode = self.mode.current()
        start = self.value if (mode == 2) == self.value.startswith("{") else "None"
        if mode == 1:
            self.inner = NumberEditor(self.frame, self.app, start, self.spec, self.touch)
        elif mode == 2:
            self.inner = MapEditor(self.frame, self.app, start, self.spec, self.touch)
        if self.inner:
            self.inner.frame.pack(anchor="w", pady=(6, 0))

    def get(self):
        return self.inner.get() if self.inner else "None"


def make_editor(parent, app, value, spec, on_change):
    kind = spec.get("kind", "number")
    if kind == "map" and parse_map(value) is not None:
        return MapEditor(parent, app, value, spec, on_change)
    if kind == "list" and parse_list(value) is not None:
        return ListEditor(parent, app, value, spec, on_change)
    if kind == "number_or_map" and (not value.startswith("{") or parse_map(value) is not None):
        return NumberOrMapEditor(parent, app, value, spec, on_change)
    if kind == "choice":
        return ChoiceEditor(parent, app, value, spec, on_change)
    if kind == "profit":
        return ProfitEditor(parent, app, value, spec, on_change)
    if kind == "number" and "\n" not in value and not value.startswith(("{", "[")):
        return NumberEditor(parent, app, value, spec, on_change)
    return TextEditor(parent, app, value, spec, on_change)


# ------------------------------------------------------------------ the two tools

DEFAULT_SECTIONS = ("general", "all buildings", "all rgo buildings")
POP_PAGE = "pop demands"  # The Pop Demands page, and its section in the settings
POP_ORDER = ("nobles", "clergy", "burghers", "soldiers", "laborers", "peasants", "slaves", "tribesmen")
DUMP_ON = re.compile(r"limit\s*=\s*\{\s*always\s*=\s*yes\s*\}")


class BuildingSetup:
    title = "Building setup"
    purpose = "Starting building levels."
    script = BUILDING_SETUP
    fields = BUILDING_FIELDS
    files = [("RGO building types", HERE / "building_setup" / "rgo_setup_settings.txt", "rgo"),
             ("Other building types", HERE / "building_setup" / "building_setup_settings.txt", "other")]
    none_turns_off = True  # A missing setting uses the default section; None turns the default off
    actions = [
        ("Restore Backup Data", "restore", None, "Restore a backup version, Apply always creates one before running", False),
        ("Run with data dump", ["--setup-data-dump"],
         "This deletes the generated setup files and turns on the data dump.\n\nThen deploy the mod, start a new game "
         "in debug mode, open the country screen, close the game, and press Apply.\n\nContinue?",
         "Get new game data, after a patch for example.", False),
    ]
    console_hint = ""

    names_from_loc = True  # load_names reads the English names into self.loc

    def __init__(self, app):
        self.app = app
        self.module = load_module(BUILDING_SETUP, "building_setup_settings_lists")
        self.loc = Localization()
        try:
            game_folder = self.module.find_game_folder()
        except Exception:  # Icons then come from the mod only
            game_folder = None
        self.icons = Icons(game_folder)

    def placed(self):
        """{building type: buildings in the setup files}, read again when a setup file changes."""
        paths = (self.module.RGO_OUTPUT_FILE, self.module.BUILDING_OUTPUT_FILE)
        stamp = tuple(path.stat().st_mtime if path.is_file() else 0 for path in paths)
        if getattr(self, "placed_stamp", None) != stamp:
            self.placed_stamp, self.placed_counts = stamp, {}
            for path in paths:
                if path.is_file():
                    for building, locations in self.module.placed_levels(path.read_bytes()).items():
                        self.placed_counts[building] = len(locations)
        return self.placed_counts

    def file_count(self, settings_file):
        """Buildings the setup files place for the building types of one settings file."""
        rgo = self.module.RGO_PREFIX
        total = sum(count for building, count in self.placed().items() if building.startswith(rgo) == (settings_file.kind == "rgo"))
        return f"{total:,}" if total else ""

    def count(self, settings_file, name):
        """Buildings the setup files place for a building type, or for every member of a distribution group."""
        placed = self.placed()
        members = self.group_members(settings_file).get(name)
        if members is not None:
            return f"{sum(placed.get(member, 0) for member in members):,}"
        return f"{placed[name]:,}" if name in placed else ""

    def label(self, name, size=16):
        """(text, icon) for a section: a building type's English name and icon, other sections as named."""
        lower = name.lower()
        if lower == "general":
            return "General", None
        if lower in DEFAULT_SECTIONS or name not in self.app.names.get("buildings", [name]):
            return name, None  # A distribution group has the name it was given
        return self.loc.name(name) or short_name(name), self.icons.building(name, size)

    def notice(self):
        """A warning above the form while the data dump is on."""
        path = self.module.DUMP_EFFECT_FILE
        if path.is_file() and DUMP_ON.search(path.read_text(encoding="utf-8-sig")):
            return "Data dump is on. Deploy the mod, start a new game in debug mode, close it at the country screen, then press Apply."
        return None

    def group_members(self, settings_file):
        """{group section: its member building types}."""
        groups = {}
        for section in settings_file.sections:
            for setting in section["settings"]:
                if setting["key"] == self.module.GROUP_SETTING:
                    groups[section["name"]] = parse_list(settings_file.value(setting)) or []
        return groups

    def allowed(self, settings_file, name):
        module = self.module
        if name.lower() == "general":
            return module.RGO_GENERAL_SETTINGS if settings_file.kind == "rgo" else module.BUILDING_GENERAL_SETTINGS
        if settings_file.kind == "rgo":
            return module.RGO_BUILDING_SETTINGS
        groups = self.group_members(settings_file)
        if name in groups:
            return module.GROUP_SETTINGS
        if any(name in members for members in groups.values()):
            return module.GROUP_MEMBER_SETTINGS
        return module.OTHER_BUILDING_SETTINGS

    def groups(self, settings_file):
        """[(group label or None, the section the label opens or None, member sections)] for the sidebar.
        None puts the members straight under the file."""
        names = settings_file.names()
        defaults = [name for name in names if name.lower() in DEFAULT_SECTIONS]
        result, placed = [(None, None, defaults)], set(defaults)
        for group, members in self.group_members(settings_file).items():
            inside = [name for name in members if name in names]
            result.append((group, group, inside))
            placed.update(inside + [group])
        result.append((None, None, [name for name in names if name not in placed]))
        return result

    def describe(self, settings_file, name):
        lower = name.lower()
        if lower == "general":
            return "Settings for the whole file."
        if lower in DEFAULT_SECTIONS:
            return "Default settings for every building type in this file."
        groups = self.group_members(settings_file)
        if name in groups:
            return "Building types in this group share one level."
        group = next((group for group, members in groups.items() if name in members), None)
        if group:
            return f"In group {group}."
        return "RGO building type." if settings_file.kind == "rgo" else "Building type."

    def default_chain(self, settings_file, name):
        """The sections a missing setting falls back to, nearest first."""
        if name.lower() == "general" or name.lower() in DEFAULT_SECTIONS:
            return []
        default = self.module.RGO_DEFAULT_SECTION if settings_file.kind == "rgo" else self.module.BUILDING_DEFAULT_SECTION
        group = next((group for group, members in self.group_members(settings_file).items() if name in members), None)
        return ([group] if group else []) + [default]

    def section_choices(self, settings_file):
        return self.app.names.get("rgo_buildings" if settings_file.kind == "rgo" else "other_buildings", [])

    def new_section_settings(self, name):
        return []


class ProvisionsMethods:
    title = "Provisions methods"
    purpose = "Recipe and food amount for each method."
    script = PROVISIONS
    fields = PROVISIONS_FIELDS
    files = [("Provisions methods", HERE / "provisions_methods" / "provisions_methods_settings.txt", "provisions")]
    none_turns_off = False  # None and a missing setting both use the default
    actions = [
        ("Sync From Files", ["--import"], None, "Sync existing production method code to tool config", False),
        ("Restore Backup Data", "restore", None, "Restore a backup version, Apply always creates one before running", False),
    ]
    console_hint = ""

    def __init__(self, app):
        self.app = app
        self.model, self.loc = ProvisionsModel(), Localization()
        try:
            game_folder = self.model.game_folder()
        except Exception:  # Icons and names then come from the mod only
            game_folder = None
        self.icons = Icons(game_folder)

    def notice(self):
        return self.model.problem

    def is_building(self, name):
        return name in self.app.names.get("method_owners", []) and name not in self.app.names.get("methods", [])

    def allowed(self, settings_file, name):
        if name.lower() == "general":
            return ["food_per_unit", "milk_food", "efficiency", "min_profit", "max_profit", "round_food_inputs", "round_percent_inputs", "fixed"]
        if self.is_building(name):
            return ["efficiency"]
        return ["food_out", "recipe", "recipe_fixed", "other", "other_percent", "efficiency", "min_profit", "max_profit", "fixed"]

    def groups(self, settings_file):
        """Methods under the building that uses them, as the report shows them."""
        names = settings_file.names()
        owners_of = self.app.names.get("owners_of", {})
        defaults = [name for name in names if name.lower() == "general"]
        result, placed, by_owner = [(None, None, defaults)], set(defaults), {}
        for name in names:
            if name in owners_of:
                by_owner.setdefault((owners_of[name] or ["Shared methods"])[0], []).append(name)
        for owner, members in by_owner.items():
            head = owner if owner in names else None
            result.append((owner, head, members))
            placed.update(members + [head])
        rest = [name for name in names if name not in placed]
        if rest:
            result.append(("Other sections", None, rest))
        return result

    def describe(self, settings_file, name):
        if name.lower() == "general":
            return "Settings for every method."
        if self.is_building(name):
            return "Food conversion efficiency for this building's methods."
        owners = self.app.names.get("owners_of", {}).get(name)
        if owners:
            return "Used by " + ", ".join(owners) + "."
        if owners is None and self.app.names.get("methods"):
            return "Not found in the game files."
        return "Method."

    def default_chain(self, settings_file, name):
        """The sections a missing setting falls back to, nearest first."""
        if name.lower() == "general":
            return []
        owners = self.app.names.get("owners_of", {}).get(name, [])
        return [owner for owner in owners if settings_file.section(owner)] + ["general"]

    def section_choices(self, settings_file):
        return self.app.names.get("methods", []) + self.app.names.get("method_owners", [])

    def new_section_settings(self, name):
        if name in self.app.names.get("methods", []):
            return [("food_out", "1"), ("recipe", "None")]
        return [("efficiency", "100")]


TOOLS = {"provisions": ProvisionsMethods, "buildings": BuildingSetup}


# ------------------------------------------------------------------ the tool's files in the window

def python_for_scripts():
    """The console Python next to the windowed one (pythonw.exe, or pythonw3.12.exe from the Store),
    so the scripts' output can be read."""
    executable = Path(sys.executable)
    console = executable.with_name(re.sub(r"^pythonw", "python", executable.name, flags=re.IGNORECASE))
    return str(console if console.exists() else executable)


class Document:
    """The tool's settings files: their sections in the sidebar, and the shown section's form and the console.
    self.file is the file of the shown section."""

    def __init__(self, app, tool):
        self.app, self.tool = app, tool
        self.files = [(label, SettingsFile(path, kind)) for label, path, kind in tool.files]
        self.file = self.files[0][1]
        self.editors, self.section_name, self.console_open, self.added_keys = [], None, False, {}
        self.build_sidebar(app.side_stack)
        self.build_main(app.main_stack)
        self.fill_sections()

    @property
    def dirty(self):
        return any(settings_file.dirty for _, settings_file in self.files)

    def wheel_canvases(self):
        return [self.canvas]

    def item_id(self, settings_file, name):
        """Tree ids start with the file's number, because both building files have a [general] section."""
        return f"{[other for _, other in self.files].index(settings_file)}:{name}"

    # -------------------------------------------------------------- layout

    def build_sidebar(self, parent):
        self.side = ttk.Frame(parent, style="Side.TFrame")
        self.side.grid(row=0, column=0, sticky="nsew")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(self.side, textvariable=self.search)
        self.search_entry.pack(fill="x", padx=14, pady=(0, 8))
        placeholder(self.search_entry, self.search, "Search   (Ctrl+F, then Enter)")
        self.search.trace_add("write", lambda *_: self.fill_sections())
        self.search_entry.bind("<Return>", lambda _: self.open_first_match())
        self.search_entry.bind("<Down>", lambda _: self.enter_tree())
        holder = ttk.Frame(self.side, style="Side.TFrame")
        holder.pack(fill="both", expand=True, padx=(8, 0))
        self.tree = ttk.Treeview(holder, show="tree", selectmode="browse", style="Side.Treeview", columns=("count",))
        self.tree.column("#0", stretch=True)
        self.tree.column("count", width=56, minwidth=56, stretch=False, anchor="e")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("file", font=self.app.caption, foreground=FAINT)
        self.tree.tag_configure("group", font=self.app.bold, foreground=TEXT)
        self.tree.tag_configure("plain", foreground=MUTED)
        self.tree.bind("<<TreeviewSelect>>", self.choose_section)
        ttk.Button(self.side, text="+   New section", style="Side.TButton", command=self.new_section).pack(fill="x", padx=14, pady=12)

    def build_main(self, parent):
        self.main = ttk.Frame(parent)
        self.main.grid(row=0, column=0, sticky="nsew")

        self.header = header = ttk.Frame(self.main, padding=(28, 14, 22, 12))
        header.pack(fill="x")
        self.path_label = ttk.Label(header, style="Faint.TLabel")
        self.path_label.pack(side="left")
        opener = ttk.Label(header, text="Open file", style="Link.TLabel", cursor="hand2")
        opener.pack(side="left", padx=(12, 0))
        opener.bind("<Button-1>", lambda _: self.open_file())
        self.save_button = ttk.Button(header, text="Save", style="Accent.TButton", command=self.save)
        self.save_button.pack(side="right")
        self.undo_button = ttk.Button(header, text="Undo changes", style="Ghost.TButton", command=self.revert)
        self.undo_button.pack(side="right", padx=(0, 6))
        self.status = ttk.Label(header, style="Faint.TLabel")
        self.status.pack(side="right", padx=(0, 14))
        self.notice = ttk.Label(self.main, style="Notice.TLabel", padding=(28, 8), wraplength=900, justify="left")
        ttk.Separator(self.main).pack(fill="x")

        self.panes = ttk.PanedWindow(self.main, orient="vertical")
        self.panes.pack(fill="both", expand=True)
        form_area, console = ttk.Frame(self.panes), ttk.Frame(self.panes, style="Console.TFrame")
        self.panes.add(form_area, weight=4)
        self.panes.add(console, weight=1)
        self.panes.bind("<Configure>", lambda _: self.place_sash())

        self.canvas = tk.Canvas(form_area, highlightthickness=0, background=BG, borderwidth=0)
        form_scroll = ttk.Scrollbar(form_area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=form_scroll.set)
        form_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.form = self.new_form()
        self.form_window = self.canvas.create_window((0, 0), window=self.form, anchor="nw")
        self.canvas.bind("<Configure>", lambda event: (self.canvas.itemconfigure(self.form_window, width=event.width),
                                                       self.update_scrollregion()))

        self.console_bar = bar = ttk.Frame(console, style="Console.TFrame", padding=(22, 10, 22, 8))
        bar.pack(fill="x")
        self.action_buttons = []
        for label, arguments, confirm, hint, main in self.tool.actions:
            button = ttk.Button(bar, text=label, style="Accent.TButton" if main else "TButton",
                                command=lambda a=arguments, c=confirm: self.action(a, c))
            button.pack(side="left", padx=(0, 6))
            Hint(button, hint)
            self.action_buttons.append(button)
        self.busy = ttk.Label(bar, style="ConsoleFaint.TLabel")
        self.busy.pack(side="left", padx=10)
        ttk.Button(bar, text="Clear", style="ConsoleGhost.TButton", command=self.close_console).pack(side="right")
        holder = ttk.Frame(console, style="Console.TFrame")
        holder.pack(fill="both", expand=True, padx=(14, 0))
        self.output = tk.Text(holder, wrap="none", height=8, state="disabled", font=self.app.mono)
        self.app.dark_text(self.output, CONSOLE)
        out_y = ttk.Scrollbar(holder, orient="vertical", command=self.output.yview)
        out_x = ttk.Scrollbar(holder, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=out_y.set, xscrollcommand=out_x.set)
        out_y.pack(side="right", fill="y")
        out_x.pack(side="bottom", fill="x")
        self.output.pack(fill="both", expand=True)
        for code, options in ANSI_COLORS.items():
            self.output.tag_configure(code, foreground=options["foreground"],
                                      font=self.app.mono_bold if options.get("bold") else self.app.mono)
        self.write(self.tool.console_hint, ("2",))
        self.console_blank = True
        self.update_notice()
        self.update_status()

    def new_form(self):
        form = ttk.Frame(self.canvas, padding=(28, 18, 22, 28))
        form.bind("<Configure>", lambda _: self.update_scrollregion())
        return form

    def extra_rows(self, section_name, row):
        """Rows a tool adds above a section's settings. Returns the next free row."""
        return row

    def update_scrollregion(self):
        # Never shorter than the view: a shorter region lets the canvas scroll into empty space
        height = max(self.form.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), height))

    def show(self):
        self.side.tkraise()
        self.main.tkraise()

    def place_sash(self):
        """The console shows only its buttons and one line until a run, then half the height."""
        height = self.panes.winfo_height()
        if height <= 100:
            return
        closed = self.console_bar.winfo_reqheight() + self.app.mono.metrics("linespace") + 34
        self.panes.sashpos(0, height // 2 if self.console_open else max(100, height - closed))

    def update_notice(self):
        text = self.tool.notice()
        if text:
            self.notice.configure(text=text)
            self.notice.pack(fill="x", after=self.header)
        else:
            self.notice.pack_forget()

    # -------------------------------------------------------------- sections

    def side_label(self, name, size=16):
        label = getattr(self.tool, "label", None)
        return label(name, size) if label else (short_name(name), None)

    def side_count(self, settings_file, name):
        """The number the sidebar shows right of a section, or nothing."""
        count = getattr(self.tool, "count", None)
        return (count(settings_file, name) if count else "",)

    def side_order(self, names):
        """Building types sort by the name the sidebar shows. The default sections keep their order."""
        if any(name.lower() in DEFAULT_SECTIONS for name in names):
            return names
        return sorted(names, key=lambda name: self.side_label(name)[0].lower())

    def fill_sections(self):
        words = self.search.get().lower().split()

        def matches(name):
            text = (name + " " + self.side_label(name)[0]).lower()
            return all(word in text for word in words)

        self.tree.delete(*self.tree.get_children())
        several = len(self.files) > 1
        for index, (file_label, settings_file) in enumerate(self.files):
            top, indent = "", "  "
            if several:
                top, indent = f"file:{index}", ""
                self.tree.insert("", "end", iid=top, text="  " + file_label.upper(), open=True, tags=("file",))
            for label, head, members in self.tool.groups(settings_file):
                if label is None:
                    for name in self.side_order(members):
                        if matches(name):
                            default = name.lower() in DEFAULT_SECTIONS
                            text, image = self.side_label(name)
                            self.tree.insert(top, "end", iid=f"{index}:{name}", text=indent + (" " + text if image else text), image=image or "",
                                             values=self.side_count(settings_file, name),
                                             tags=("group" if default else "plain",))
                    continue
                whole = matches(label)
                shown = members if whole else [name for name in members if matches(name)]
                if not shown and not whole:
                    continue
                group_id = f"{index}:{head}" if head else f"{index}:group:{label}"
                self.tree.insert(top, "end", iid=group_id, text="  " + label, open=True, tags=("group",),
                                 values=self.side_count(settings_file, head) if head else ("",))
                for name in self.side_order(shown):
                    text, image = self.side_label(name)
                    self.tree.insert(group_id, "end", iid=f"{index}:{name}", text=" " + text if image else text, image=image or "",
                                     values=self.side_count(settings_file, name), tags=("plain",))
            if several and words and not self.tree.get_children(top):
                self.tree.delete(top)
        if self.section_name not in self.file.names():
            self.section_name = None
        if self.section_name is None:
            first = next(((settings_file, settings_file.names()[0]) for _, settings_file in self.files if settings_file.names()), None)
            if first:
                self.show_section(*first)
        self.mark_selected()
        self.update_status()

    def section_items(self, parent=""):
        """Every tree item that opens a section, top to bottom."""
        for item in self.tree.get_children(parent):
            if not item.startswith("file:") and not item.partition(":")[2].startswith("group:"):
                yield item
            yield from self.section_items(item)

    def open_first_match(self):
        first = next(self.section_items(), None)
        if first:
            self.tree.selection_set(first)

    def enter_tree(self):
        first = next(self.section_items(), None)
        if first:
            self.tree.focus_set()
            self.tree.focus(first)
            self.tree.selection_set(first)

    def mark_selected(self):
        if self.section_name is None:
            return
        item = self.item_id(self.file, self.section_name)
        if self.tree.exists(item):
            if self.tree.selection() != (item,):
                self.tree.selection_set(item)
            self.tree.see(item)

    def choose_section(self, _=None):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        index, _, name = item.partition(":")
        if item.startswith("file:") or name.startswith("group:"):
            self.tree.item(item, open=not self.tree.item(item, "open"))
            self.tree.selection_remove(item)
            self.mark_selected()
            return
        settings_file = self.files[int(index)][1]
        if settings_file is not self.file or name != self.section_name:
            self.commit()
            self.show_section(settings_file, name)

    def show_section(self, settings_file, name):
        self.file, self.section_name = settings_file, name
        self.path_label.configure(text=settings_file.path.name)
        # The page is built in a frame that is not on screen yet, then swapped in whole. Tk lays it out once.
        shown, self.form = self.form, self.new_form()
        self.editors = []
        section = self.file.section(name)
        if section is None:
            self.swap_form(shown)
            return
        self.form.columnconfigure(0, minsize=270)
        self.form.columnconfigure(1, weight=1)
        top = ttk.Frame(self.form)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        text, image = self.side_label(name, 24) if getattr(self.tool, "label", None) else ("General" if name.lower() == "general" else name, None)
        ttk.Label(top, text=" " + text if image else text, image=image or "", compound="left",
                  style="Heading.TLabel").pack(side="left")
        if text.lower() != name.lower():
            ttk.Label(top, text=name, style="Faint.TLabel").pack(side="left", padx=(10, 0), pady=(4, 0))
        if len(self.files) > 1:
            label = next(label for label, other in self.files if other is settings_file)
            ttk.Label(top, text="·  " + label, style="Muted.TLabel").pack(side="left", padx=(10, 0), pady=(4, 0))
        if name.lower() not in DEFAULT_SECTIONS:
            ttk.Button(top, text="Delete section", style="Danger.TButton", command=self.remove_section).pack(side="right")
        ttk.Label(self.form, text=self.tool.describe(self.file, name), style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))
        row = 2
        if section["notes"]:
            ttk.Label(self.form, text="\n".join(section["notes"]), style="Faint.TLabel", wraplength=760,
                      justify="left").grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
            row += 1
        ttk.Frame(self.form, height=14).grid(row=row, column=0)
        row = self.extra_rows(name, row + 1)
        # Only the settings this section sets. "+ Add setting" shows one more, and it is written once it has a value.
        used = {setting["key"] for setting in section["settings"]}
        allowed = self.tool.allowed(self.file, name)
        chain = self.tool.default_chain(self.file, name)
        if chain:
            rows = [(setting["key"], setting) for setting in section["settings"]]
        else:
            # [general] and the default sections keep one fixed order
            by_key = {setting["key"]: setting for setting in section["settings"]}
            rows = [(key, by_key[key]) for key in allowed if key in by_key] + [(key, setting) for key, setting in by_key.items() if key not in allowed]
        added = [key for key in self.added_keys.get((id(self.file), name), []) if key not in used]
        rows += [(key, None) for key in added]
        left = [key for key in allowed if key not in used and key not in added]
        if not rows:
            ttk.Label(self.form, text="This section sets nothing. It uses the defaults.", style="Faint.TLabel").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(0, 14))
            row += 1
        for key, setting in rows:
            ttk.Separator(self.form).grid(row=row, column=0, columnspan=3, sticky="ew")
            row += 1
            default = self.default_of(chain, key)
            if setting is None:
                hint = "default" if default else "not set"
            else:
                hint = "off" if default and self.tool.none_turns_off else "default" if default else "not set"
            spec = dict(self.tool.fields.get(key, {"kind": "number"}), hint=hint, tool=self.tool)
            label = ttk.Frame(self.form)
            label.grid(row=row, column=0, sticky="nw", padx=(0, 28), pady=14)
            ttk.Label(label, text=setting_title(key), style="Setting.TLabel" if setting else "Unset.TLabel").pack(anchor="w")
            help_text = HELP.get(key) or self.file.help.get(key)
            if help_text:
                ttk.Label(label, text=help_text, style="Help.TLabel", wraplength=250, justify="left").pack(anchor="w", pady=(3, 0))
            if default:
                ttk.Label(label, text=f"Default ({default[0]}): {default[1]}", style="Help.TLabel", wraplength=250,
                          justify="left").pack(anchor="w", pady=(3, 0))
            if setting and default and self.tool.none_turns_off:
                # Here an empty value turns the default off, so going back to the default takes the line out
                back = ttk.Label(label, text="use default", style="Link.TLabel", cursor="hand2", font=self.app.small)
                back.pack(anchor="w", pady=(4, 0))
                back.bind("<Button-1>", lambda _, key=key: self.remove_setting(key))
            editor = make_editor(self.form, self.app, self.file.value(setting) if setting else "None", spec, self.edited)
            editor.frame.grid(row=row, column=1, sticky="w", pady=14)
            self.editors.append((setting, key, editor))
            row += 1
        if rows:
            ttk.Separator(self.form).grid(row=row, column=0, columnspan=3, sticky="ew")
            row += 1
        if left:
            adder = ttk.Button(self.form, text="+ Add setting", style="Ghost.TButton")
            adder.configure(command=lambda: ChoicePopup(adder, adder.winfo_rootx(), adder.winfo_rooty() + adder.winfo_height(),
                                                        [(setting_title(key), key, None) for key in left], self.show_setting))
            adder.grid(row=row, column=0, sticky="w", pady=12)
        self.swap_form(shown)
        self.canvas.yview_moveto(0)
        self.mark_selected()

    def show_setting(self, key):
        """Shows one more setting on this page. It goes into the file once it has a value."""
        self.commit()
        self.added_keys.setdefault((id(self.file), self.section_name), []).append(key)
        self.show_section(self.file, self.section_name)

    def swap_form(self, shown):
        self.canvas.itemconfigure(self.form_window, window=self.form)
        if shown is not self.form:
            shown.destroy()

    def default_of(self, chain, key):
        """(section, value on one line) of the nearest section in chain that has the setting, or None."""
        for section_name in chain:
            section = next((section for section in self.file.sections if section["name"].lower() == section_name.lower()), None)
            setting = next((setting for setting in section["settings"] if setting["key"] == key), None) if section else None
            if setting:
                value = re.sub(r"\s+", " ", self.file.value(setting)).replace(", }", " }").replace(", ]", " ]")
                value = self.readable(key, value)
                return section["name"], value if len(value) <= 90 else value[:87] + "..."
        return None

    def readable(self, key, value):
        """A map as "Name 1.1, Name 0.9" and a list as "Name, Name", with the English names."""
        names = self.tool.fields.get(key, {}).get("names")
        rows, listed = parse_map(value), parse_list(value)
        if rows:
            return ", ".join(f"{shown_name(self.tool, names, name)} {number}" for name, number in rows)
        if listed:
            return ", ".join(shown_name(self.tool, names, name) for name in listed)
        return value

    def edited(self):
        if not self.file.dirty:
            self.file.dirty = True
            self.update_status()

    def commit(self):
        """Puts the edited values into the file's lines. Last line first, so line numbers stay right."""
        in_file = sorted([(setting, editor) for setting, _, editor in self.editors if setting and editor.changed],
                         key=lambda pair: -pair[0]["start"])
        for setting, editor in in_file:
            self.file.set_value(setting, editor.get())
        if in_file:
            self.file.parse()
        for setting, key, editor in self.editors:
            # A setting not in the file is written only once it has a value
            if setting is None and editor.changed and editor.get().strip().lower() != "none":
                self.file.add_setting(self.file.section(self.section_name), key, editor.get())
        self.editors = []

    close_question = "Save your changes before closing?"

    def primary(self):
        self.save()

    def finish_before_close(self):
        self.save()
        return True

    def run_before_close(self, arguments):
        """Runs the generator and waits for it. False, with its output shown, when it did not finish."""
        process = subprocess.run([python_for_scripts(), str(self.tool.script), *arguments], cwd=str(self.tool.script.parent),
                                 capture_output=True, env=script_environment(), encoding="utf-8", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode == 0:
            return True
        output = ANSI.sub("", process.stdout + process.stderr)
        if "Traceback (most recent call last)" in output:
            log_error(output[output.index("Traceback (most recent call last)"):], f"{self.tool.script.name} {' '.join(arguments)}")
        messagebox.showerror(self.tool.title, "Your changes were not applied, so the window stays open.\n\n" + output.strip()[-1500:])
        return False

    def update_status(self):
        dirty = self.dirty
        self.status.configure(text="Not saved" if dirty else "Saved", foreground=WARN if dirty else FAINT)
        for button in (self.save_button, self.undo_button):
            button.state(["!disabled"] if dirty else ["disabled"])

    def refresh(self, settings_file=None, name=None):
        self.editors = []
        if name is not None:
            self.file, self.section_name = settings_file, name
        self.fill_sections()
        if self.section_name:
            self.show_section(self.file, self.section_name)

    def remove_setting(self, key):
        self.commit()
        section = self.file.section(self.section_name)
        self.file.remove_setting(next(setting for setting in section["settings"] if setting["key"] == key))
        self.file.dirty = True
        self.refresh()

    def new_section(self):
        choices = [(name, (settings_file, name)) for _, settings_file in self.files
                   for name in self.tool.section_choices(settings_file) if name not in settings_file.names()]
        group_file = next((settings_file for _, settings_file in self.files if settings_file.kind == "other"), None)
        result = ListDialog(self.app, "New section", "Choose a building type or method." +
                            (" Or type a name to make a group." if group_file else ""),
                            choices, allow_new=group_file is not None).result
        if not result:
            return
        settings_file, name = result if isinstance(result, tuple) else (group_file, result)
        self.commit()
        settings_file.add_section(name, self.tool.new_section_settings(name))
        settings_file.dirty = True
        self.search.set("")
        self.refresh(settings_file, name)

    def remove_section(self):
        if not messagebox.askyesno("Delete section", f"Delete [{self.section_name}] and all its settings?"):
            return
        self.commit()
        self.file.remove_section(self.file.section(self.section_name))
        self.file.dirty = True
        self.section_name = None
        self.refresh()

    def save(self):
        self.commit()
        for _, settings_file in self.files:
            if settings_file.dirty:
                settings_file.save()
        self.refresh()

    def revert(self):
        if self.dirty and not messagebox.askyesno("Undo changes", "Undo the changes you have not saved?"):
            return
        for _, settings_file in self.files:
            settings_file.load()
        self.refresh()

    def open_file(self):
        if os.name == "nt":
            os.startfile(self.file.path)
        else:
            subprocess.Popen(["xdg-open", str(self.file.path)])

    # -------------------------------------------------------------- running

    def action(self, arguments, confirm):
        if confirm and not messagebox.askyesno(self.tool.title, confirm):
            return
        if self.dirty and self.save() is False:
            return
        if arguments == "restore":
            self.choose_backup()
        else:
            self.run(arguments + self.backup_arguments(arguments))

    def backup_arguments(self, arguments):
        return []

    def choose_backup(self):
        module = load_module(self.tool.script, self.tool.script.stem + "_backups")
        items = []
        for index, folder in enumerate(module.backups(), 1):
            info = (folder / "info.txt").read_text(encoding="utf-8").splitlines() if (folder / "info.txt").exists() else ["?"]
            files = len(module.backup_files(folder, "before"))
            when = f"{folder.name[:10]}  {folder.name[11:19].replace('-', ':')}"
            methods = f", {len(info) - 1} methods" if len(info) > 1 else ""
            items.append((f"{when}    {info[0]}{methods}, {files} files", index))
        if not items:
            messagebox.showinfo("Restore Backup Data", "There are no backups yet. Apply makes one.")
            return
        choice = ListDialog(self.app, "Restore Backup Data", "Choose a backup. Newest first.", items, search=False).result
        if choice:
            self.run(["--restore", str(choice)], lambda output, code: self.offer_force(output, code, choice))

    def offer_force(self, output, code, choice):
        if code != 0 and "--force" in output and messagebox.askyesno(
                "Restore Backup Data", "Files changed since that backup. Restoring undoes those changes too.\n\nRestore anyway?"):
            self.run(["--restore", str(choice), "--force"])

    def run(self, arguments, then=None):
        for button in self.action_buttons:
            button.state(["disabled"])
        self.busy.configure(text="running...")
        self.console_open = True
        self.place_sash()
        if self.console_blank:
            self.clear_output()
        gap = "" if self.output.index("end-1c") == "1.0" else "\n"
        self.write(f"{gap}> {self.tool.script.name} {' '.join(arguments)}\n", ("2",))
        messages, collected = queue.Queue(), []
        self.last_run_lines = []
        environment = script_environment()

        def work():
            try:
                process = subprocess.Popen([python_for_scripts(), str(self.tool.script), *arguments],
                                           cwd=str(self.tool.script.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           env=environment, encoding="utf-8", errors="replace",
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for line in process.stdout:
                    messages.put(line)
                messages.put(("done", process.wait()))
            except Exception as error:  # The window has to say why a run could not start
                messages.put(f"Could not run the script: {error}\n")
                messages.put(("done", 1))

        def poll():
            while True:
                try:
                    item = messages.get_nowait()
                except queue.Empty:
                    self.app.root.after(50, poll)
                    return
                if isinstance(item, tuple):
                    output = "".join(collected)
                    if "Traceback (most recent call last)" in output:
                        log_error(output[output.index("Traceback (most recent call last)"):],
                                  f"{self.tool.script.name} {' '.join(arguments)}")
                    for button in self.action_buttons:
                        button.state(["!disabled"])
                    self.busy.configure(text="")
                    self.reload_after_run()
                    self.update_notice()
                    if then:
                        then(output, item[1])
                    return
                collected.append(ANSI.sub("", item))
                self.last_run_lines.append(item)
                self.write_colored(item)

        threading.Thread(target=work, daemon=True).start()
        poll()

    def reload_after_run(self):
        """The run may have changed the settings, as Import does."""
        if not self.dirty:
            for _, settings_file in self.files:
                settings_file.load()
            self.refresh()

    def close_console(self):
        self.clear_output()
        self.console_open = False
        self.place_sash()

    def clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.console_blank = False

    def write(self, text, tags=()):
        self.output.configure(state="normal")
        self.output.insert("end", text, tags)
        self.output.see("end")
        self.output.configure(state="disabled")

    def write_many(self, pieces):
        """Writes [(text, tags)] in one insert. A large diff written piece by piece takes many seconds."""
        if not pieces:
            return
        self.output.configure(state="normal")
        self.output.insert("end", *[part for text, tags in pieces for part in (text, tags)])
        self.output.configure(state="disabled")

    def write_colored(self, line):
        parts, tags = ANSI.split(line), ()
        for index, part in enumerate(parts):
            if index % 2:
                tags = () if part in ("", "0") else (part,)
            elif part:
                self.write(part, tags)


class ListDialog:
    """A list to click in, with a search field. allow_new also accepts a typed name that is not in the list."""

    def __init__(self, app, title, prompt, items, search=True, allow_new=False):
        self.items, self.result, self.allow_new = items, None, allow_new
        self.window = window = tk.Toplevel(app.root, background=BG)
        window.title(title)
        window.transient(app.root)
        window.geometry(f"560x560+{app.root.winfo_rootx() + 200}+{app.root.winfo_rooty() + 80}")
        app.dark_title_bar(window)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w")
        ttk.Label(frame, text=prompt, style="Muted.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(4, 12))
        self.filter = tk.StringVar()
        if search:
            entry = ttk.Entry(frame, textvariable=self.filter)
            entry.pack(fill="x", pady=(0, 8))
            placeholder(entry, self.filter, "Search")
            entry.focus_set()
            self.filter.trace_add("write", lambda *_: self.fill())
        holder = ttk.Frame(frame)
        holder.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(holder, activestyle="none", font=app.mono)
        app.dark_list(self.listbox)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda _: self.done())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self.done).pack(side="right")
        ttk.Button(buttons, text="Cancel", style="Ghost.TButton", command=window.destroy).pack(side="right", padx=6)
        window.bind("<Return>", lambda _: self.done())
        window.bind("<Escape>", lambda _: window.destroy())
        self.fill()
        window.grab_set()
        window.wait_window()

    def fill(self):
        words = self.filter.get().lower().split()
        self.shown = [(text, value) for text, value in self.items if all(word in text.lower() for word in words)]
        self.listbox.delete(0, "end")
        for text, _ in self.shown:
            self.listbox.insert("end", "  " + text)
        if self.shown:
            self.listbox.selection_set(0)

    def done(self):
        selected = self.listbox.curselection()
        typed = self.filter.get().strip()
        if selected:
            self.result = self.shown[selected[0]][1]
        elif self.allow_new and re.fullmatch(r"\w+", typed):
            self.result = typed
        else:
            return
        self.window.destroy()


class Hint:
    """A small note under the mouse pointer after a short wait."""

    def __init__(self, widget, text):
        self.widget, self.text, self.window, self.waiting = widget, text, None, None
        widget.bind("<Enter>", lambda _: self.wait(), add="+")
        widget.bind("<Leave>", lambda _: self.hide(), add="+")
        widget.bind("<Button-1>", lambda _: self.hide(), add="+")

    def wait(self):
        self.waiting = self.widget.after(600, self.show)

    def show(self):
        if not self.text:
            return
        x, y = self.widget.winfo_rootx(), self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        if isinstance(self.text, list):
            # (value, icon) pairs: each value with its icon after it. A text icon stands in when there is no image.
            row = tk.Frame(self.window, background=HOVER, padx=8, pady=5)
            row.pack()
            for value, icon in self.text:
                image = icon if not isinstance(icon, str) else ""
                tk.Label(row, text=value + (icon if isinstance(icon, str) else ""), image=image,
                         compound="right" if image else "none", background=HOVER, foreground=TEXT, padx=4).pack(side="left")
            return
        tk.Label(self.window, text=self.text, background=HOVER, foreground=TEXT, padx=10, pady=5,
                 wraplength=340, justify="left").pack()

    def hide(self):
        if self.waiting:
            self.widget.after_cancel(self.waiting)
            self.waiting = None
        if self.window:
            self.window.destroy()
            self.window = None


# ------------------------------------------------------------------ provisions: live check, icons and names

MILK = "milk"  # A recipe share of food from the herd. It is not a good and needs no input.
MILK_CHOICE = "milk (no input)"
HEALTH_ORDER = {"bad": 3, "warn": 2, "good": 1, "none": 0}
HEALTH_COLOR = {"bad": BAD, "warn": WARN, "good": GOOD, "none": FAINT}
LOC_LINE = re.compile(r'^(\s+)([\w.\-]+)(:\d*)\s*"(.*)"(.*)$')


def hex_rgb(color):
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def mix(first, second, share):
    """The color share of the way from first to second."""
    return "#" + "".join(f"{round(a + (b - a) * share):02x}" for a, b in zip(hex_rgb(first), hex_rgb(second)))


def lighten(color):
    return "#" + "".join(f"{min(255, part + (255 - part) // 3):02x}" for part in hex_rgb(color))


def diff_lines(old, new, context=2):
    """Unified diff lines. Blank lines and braces repeat often, so autojunk stays off or whole blocks show as changed."""
    lines = []
    for group in difflib.SequenceMatcher(None, old, new, autojunk=False).get_grouped_opcodes(context):
        first, last = group[0], group[-1]
        lines.append(f"@@ -{first[1] + 1},{last[2] - first[1]} +{first[3] + 1},{last[4] - first[3]} @@")
        for tag, old_start, old_end, new_start, new_end in group:
            if tag == "equal":
                lines += [" " + line for line in old[old_start:old_end]]
                continue
            lines += ["-" + line for line in old[old_start:old_end]]
            lines += ["+" + line for line in new[new_start:new_end]]
    return lines


def number_text(value):
    return f"{value:.5f}".rstrip("0").rstrip(".") if value is not None else ""


# Values outside the settings that the provisions system depends on, and the mod files that hold them
VALUE_FILES = {"goods": "in_game/common/goods/MnT_provisions.txt", "defines": "loading_screen/common/defines/MnT_Defines.txt",
               "pops": "in_game/common/pop_types/MnT_pop_types.txt", "demand": "in_game/common/scripted_effects/MnT_provisions.txt",
               "food_goods": "in_game/common/goods/03_food.txt"}
GOODS_FOLDER = "in_game/common/goods"
DEMAND_DIVIDE = r"(name = mnt_food divide = )([0-9.]+)"


def block_of(text, header):
    """(start, end) of the block that opens with this header, by brace count. None when it is missing."""
    match = re.search(r"(?m)^[ \t]*" + re.escape(header) + r"\s*=\s*\{", text)
    if not match:
        return None
    depth, comment = 0, False
    for index in range(match.end() - 1, len(text)):
        # Braces in comments do not count: some goods keep their old demand blocks commented out
        char = text[index]
        if comment:
            comment = char != "\n"
        elif char == "#":
            comment = True
        else:
            depth += {"{": 1, "}": -1}.get(char, 0)
            if depth == 0:
                return match.start(), index + 1
    return None


def inner_block(text, header, span):
    """(start, end) of a block inside span, in the whole text's positions. None when it is missing."""
    found = block_of(text[span[0]:span[1]], header) if span else None
    return (span[0] + found[0], span[0] + found[1]) if found else None


def good_span(text, good):
    """(start, end) of a good's block, with or without a REPLACE: or INJECT: prefix. None when it is missing."""
    return next((span for span in (block_of(text, prefix + good) for prefix in ("REPLACE:", "INJECT:", "")) if span), None)


def luxury_spans(text, good):
    """(demand_add span, demand_multiply span) of a good. Either is None when it is missing."""
    span = good_span(text, good)
    return inner_block(text, "demand_add", span), inner_block(text, "demand_multiply", span)


def add_lines(text, span, lines):
    """The text with lines put just before the closing brace of span, one tab deeper than that brace."""
    close = span[1] - 1
    start = text.rfind("\n", 0, close) + 1
    indent = re.match(r"[ \t]*", text[start:close]).group(0) + "\t"
    newline = "\r\n" if "\r\n" in text else "\n"
    if text[start:close].strip():
        # The brace shares its line with other text: start a new line
        return text[:close] + newline + "".join(indent + line + newline for line in lines) + text[close:]
    return text[:start] + "".join(indent + line.replace("\n", newline + indent) + newline for line in lines) + text[start:]


def remove_line(text, key, span):
    """The text without the line that sets key inside span."""
    found = re.search(r"(?m)^[ \t]*" + re.escape(key) + r"\s*=\s*-?[0-9.]+[^\n]*\n?", text[span[0]:span[1]])
    return text[:span[0] + found.start()] + text[span[0] + found.end():] if found else text


def remove_if_empty(text, span):
    """The text without the block at span when only comments and blank space are left in it."""
    if span is None or re.sub(r"#[^\n]*", "", text[text.index("{", span[0]) + 1:span[1] - 1]).strip():
        return text
    start, end = text.rfind("\n", 0, span[0]) + 1, span[1]
    end = text.index("\n", end) + 1 if "\n" in text[end:] else end
    return text[:start] + text[end:]


def value_in(text, key, span=None):
    """The number after "key =" inside span (or anywhere), as text. None when it is missing."""
    start, end = span or (0, len(text))
    match = re.search(r"(?m)^[ \t]*" + re.escape(key) + r"\s*=\s*(-?[0-9.]+)", text[start:end])
    return match.group(1) if match else None


def set_value_in(text, key, value, span=None):
    """The text with the number after "key =" inside span replaced. The line's comment stays."""
    start, end = span or (0, len(text))
    current = value_in(text, key, span)
    if current is not None and float(current) == float(value):
        return text
    part, count = re.subn(r"(?m)^([ \t]*" + re.escape(key) + r"\s*=\s*)(-?[0-9.]+)", lambda match: match.group(1) + value,
                          text[start:end], count=1)
    if not count:
        raise ValueError(f"{key} is missing.")
    return text[:start] + part + text[end:]


def read_game_values(mod_folder):
    """{"price", "food", "subsistence", "pops": {pop type: food}} as text, from the mod's files."""
    texts = {key: (mod_folder / path).read_bytes().decode("utf-8-sig") for key, path in VALUE_FILES.items()}
    goods = block_of(texts["goods"], "provisions")
    pops = {}
    for match in re.finditer(r"(?m)^((?:REPLACE:|INJECT:)?(\w+))\s*=\s*\{", texts["pops"]):
        food = value_in(texts["pops"], "pop_food_consumption", block_of(texts["pops"], match.group(1)))
        if food is not None:
            pops[match.group(2)] = food
    # Luxury food: goods with demand_add "all" (units per food) and demand_multiply (each class's food)
    luxury, goods_at = {}, {}
    for path in sorted((mod_folder / GOODS_FOLDER).glob("*.txt")):
        text = path.read_bytes().decode("utf-8-sig")
        for match in re.finditer(r"(?m)^(?:REPLACE:|INJECT:)?(\w+)\s*=\s*\{", text):
            good = match.group(1)
            goods_at.setdefault(good, f"{GOODS_FOLDER}/{path.name}")
            add_span, multiply_span = luxury_spans(text, good)
            add = value_in(text, "all", add_span) if add_span else None
            if add is not None and multiply_span and good not in luxury:
                start, end = multiply_span
                luxury[good] = {"add": add, "multiply": dict(re.findall(r"(?m)^[ \t]*(\w+)\s*=\s*(-?[0-9.]+)", text[start:end]))}
    return {"price": value_in(texts["goods"], "default_market_price", goods), "food": value_in(texts["goods"], "food", goods),
            "subsistence": value_in(texts["defines"], "SUBSISTENCE_AGRICULTURE"), "pops": pops, "luxury": luxury,
            "goods_at": goods_at}


def linked_values(values):
    """The values that follow the provisions price, food and subsistence food. None when one is not a number."""
    try:
        price, food, subsistence = float(values["price"]), float(values["food"]), float(values["subsistence"])
    except (TypeError, ValueError):
        return None
    if food <= 0:
        return None
    return {"food_price": number_text(round(price / food, 5)), "base_production": number_text(round(subsistence / food, 5)),
            "divide": number_text(food)}


def write_game_values(mod_folder, values, text_of):
    """{path: text} for the files these values change. text_of(path) gives a file's current text."""
    linked = linked_values(values)
    if linked is None:
        raise ValueError("the provisions price, food or subsistence food is not a number.")
    paths = {key: mod_folder / path for key, path in VALUE_FILES.items()}
    out = {}
    text = text_of(paths["goods"])
    for key, value in (("default_market_price", values["price"]), ("food", values["food"]),
                       ("base_production", linked["base_production"])):
        text = set_value_in(text, key, value, block_of(text, "provisions"))
    out[paths["goods"]] = text
    text = set_value_in(text_of(paths["defines"]), "SUBSISTENCE_AGRICULTURE", values["subsistence"])
    out[paths["defines"]] = set_value_in(text, "FOOD_PRICE", linked["food_price"])
    text = text_of(paths["pops"])
    for pop, food in values["pops"].items():
        header = next(prefix + pop for prefix in ("REPLACE:", "INJECT:", "") if block_of(text, prefix + pop))
        text = set_value_in(text, "pop_food_consumption", food, block_of(text, header))
    out[paths["pops"]] = text
    text, count = re.subn(DEMAND_DIVIDE, lambda match: match.group(1) + linked["divide"], text_of(paths["demand"]), count=1)
    if not count:
        raise ValueError("the monthly provisions demand script has no divide by food.")
    out[paths["demand"]] = text
    # Luxury goods: demand_add is the units that hold one food, so it follows the good's food value.
    # A new luxury good gets the lines it is missing; a removed one loses its "all" line and its class lines.
    for good in values.get("removed_luxury", []):
        path = mod_folder / values["goods_at"][good]
        text = out.get(path) or text_of(path)
        add_span, _ = luxury_spans(text, good)
        if add_span:
            text = remove_line(text, "all", add_span)
            text = remove_if_empty(text, luxury_spans(text, good)[0])
        for pop in values["pops"]:
            _, multiply_span = luxury_spans(text, good)
            if multiply_span:
                text = remove_line(text, pop, multiply_span)
        _, multiply_span = luxury_spans(text, good)
        if multiply_span:
            text = remove_if_empty(text, multiply_span)
        out[path] = text
    for good, demand in values.get("luxury", {}).items():
        food = values.get("food_per_unit", {}).get(good, 0)
        if food <= 0:
            continue
        path = mod_folder / values["goods_at"][good]
        text = out.get(path) or text_of(path)
        units = number_text(round(1 / food, 5))
        add_span, _ = luxury_spans(text, good)
        if add_span is None:
            text = add_lines(text, good_span(text, good), ["demand_add = {\n\tall = " + units + "\n}"])
        elif value_in(text, "all", add_span) is None:
            text = add_lines(text, add_span, ["all = " + units])
        else:
            text = set_value_in(text, "all", units, add_span)
        if luxury_spans(text, good)[1] is None:
            text = add_lines(text, good_span(text, good), ["demand_multiply = {\n}"])
        for pop, amount in demand["multiply"].items():
            _, multiply_span = luxury_spans(text, good)
            if value_in(text, pop, multiply_span) is None:
                text = add_lines(text, multiply_span, [f"{pop} = {amount}"])
            else:
                text = set_value_in(text, pop, amount, multiply_span)
        out[path] = text
    return out


class ProvisionsModel:
    """The provisions script's own check, run on the unsaved settings, so each method's health shows while you type."""

    def __init__(self):
        self.module = load_module(PROVISIONS, "provisions_methods_live")
        self.game, self.results, self.problem = None, {}, None
        self.food_per_unit = {}
        self.added = set()  # Production methods that Apply adds to the building files
        self.converted = set()  # Other production methods that Apply turns into provisions methods
        self.temp = Path(tempfile.gettempdir()) / "mnt_provisions_live_settings.txt"

    def game_folder(self):
        return self.module.get_from_config("Paths", "game_directory")

    def load_game(self):
        """Reads the goods and every building file. Run again after a run changes the building files."""
        module = self.module
        goods, building_names, prices, food_per_provisions, methods = module.read_game()
        slots, others, slot_of = self.read_slots(set(goods), methods)
        self.game = {"goods": goods, "building_names": building_names, "prices": prices, "methods": methods,
                     "food_per_provisions": food_per_provisions, "script_values": module.read_script_values(),
                     "places": module.locate(list(methods) + list(others)), "slots": slots, "others": others,
                     "slot_of": slot_of, "fields": self.fields}
        self.values = read_game_values(module.MOD_FOLDER)

    def read_slots(self, goods, methods):
        """Each production methods block in a building is one slot: one of its production methods runs at a time.
        Returns the slots of each building with provisions methods, the other production methods in them,
        and each provisions method's (building, slot number)."""
        module = self.module
        game_folder, mod = module.get_from_config("Paths", "game_directory"), str(module.MOD_FOLDER)
        buildings = module.load_folder("in_game/common/building_types", game_folder, mod)
        shared = module.load_folder("in_game/common/production_methods", game_folder, mod)
        slots, others, slot_of, users, fields = {}, {}, {}, {}, {}
        for building, (block, _, _) in buildings.items():
            building_slots = []
            for key, _, value in block:
                if key not in ("unique_production_methods", "possible_production_methods") or not isinstance(value, list):
                    continue
                is_shared = key == "possible_production_methods"
                names = []
                for name, _, method in value:
                    if is_shared:
                        method = shared[name][0] if name in shared else None
                        users[name] = users.get(name, 0) + 1
                    names.append((name, method))
                    if isinstance(method, list):
                        fields[name] = {key: module.get(method, key) for key in ("icon_type", "icon", "category")
                                        if module.get(method, key)}
                building_slots.append({"shared": is_shared, "methods": names})
            if not any(name in methods for slot in building_slots for name, _ in slot["methods"]):
                continue
            for slot in building_slots:
                for name, method in slot["methods"]:
                    if name not in methods and isinstance(method, list):
                        others.setdefault(name, {
                            "inputs": {good: float(amount) for good, _, amount in method if good in goods and isinstance(amount, str)
                                       and re.fullmatch(r"[0-9.]+", amount)},
                            "produced": module.get(method, "produced"), "output": float(module.get(method, "output") or 0),
                            "shared": slot["shared"]})
                slot["methods"] = [name for name, _ in slot["methods"]]
            slots[building] = building_slots
            for number, slot in enumerate(building_slots, 1):
                for name in slot["methods"]:
                    if name in methods:
                        slot_of.setdefault(name, (building, number))
        for name, info in others.items():
            info["users"] = users.get(name, 1)
        self.fields = fields
        return slots, others, slot_of

    def analyse(self, lines, values=None):
        """values: the game values as edited. The check uses their provisions price and food."""
        module, game = self.module, self.game
        if game is None:
            return
        prices, food_per_provisions = game["prices"], game["food_per_provisions"]
        if values and linked_values(values):
            prices = dict(prices, **{module.PROVISIONS: float(values["price"])})
            food_per_provisions = float(values["food"])
        self.prices = prices
        self.temp.write_text("\n".join(lines), encoding="utf-8-sig")
        module.SETTINGS_FILE = self.temp
        try:
            self.food_per_unit, settings = module.read_settings(game["goods"], game["building_names"], game["methods"], game["script_values"])
        except module.Problem as problem:
            self.problem = str(problem)
            return
        self.problem = None
        self.results, self.raw = {}, {}
        for name, method in game["methods"].items():
            result = module.check(name, method, settings.get(name), game["places"].get(name, []), self.food_per_unit,
                                  food_per_provisions, prices, game["script_values"])
            self.results[name] = self.summary(result)
            self.raw[name] = result

    def summary(self, result):
        """Health is about profit only. Work for Apply and problems this window cannot fix are flags."""
        module, prices = self.module, getattr(self, "prices", self.game["prices"])
        inputs = dict(result.get("amounts", result["inputs"]), **result.get("milk", {}))
        output = result.get("new_output", result["output"])
        profit = output * prices.get(module.PROVISIONS, 0) - sum(prices.get(good, 0) * amount for good, amount in inputs.items())
        margin, health, reasons = result["margin"], "good", []
        if margin is None:
            health = "none"
            if output > 0:
                reasons.append("The output has no price.")
        elif margin < 0:
            health = "bad"
            reasons.append(f"Loses money: profit {margin * 100:+.0f}%.")
        elif module.below_min(result):
            health = "warn"
            reasons.append(f"Profit {margin * 100:+.0f}% is below the min of {result['min_profit'] * 100:+.0f}%.")
        elif module.above_max(result):
            health = "warn"
            reasons.append(f"Profit {margin * 100:+.0f}% is above the max of {result['max_profit'] * 100:+.0f}%.")
        flags, pending = [], ""
        places = result["places"]
        if result["setting"] is None:
            flags.append("Not in settings. Sync From Files adds it.")
        elif len(places) > 1:
            flags.append(f"Defined {len(places)} times in the mod. Apply cannot write it.")
        elif result["name"] in self.added:
            pending = "Apply adds it."
        elif result["name"] in self.converted:
            pending = "Apply makes it a provisions method."
        elif not places:
            flags.append("Only in vanilla. Copy it into the mod before Apply can write it.")
        elif result["changes"]:
            parts = []
            for good, old, new in result["changes"]:
                old, new = (number_text(value) if isinstance(value, float) else value for value in (old, new))
                parts.append(good if good == "generator note" else f"+{good} {new}".strip() if old is None else f"-{good} {old}" if new is None else f"{good} {old} → {new}")
            pending = "Apply writes: " + ", ".join(parts)
        return {"health": health, "reasons": reasons, "flags": flags, "pending": pending, "name": result["name"],
                "margin": margin, "profit": profit, "inputs": inputs, "output": output, "food_out": result["food_out"],
                "in_settings": result["setting"] is not None, "owners": result["owners"]}


class Icons:
    """Game icons as Tk images, from the mod first, then the game. Without Pillow there are none."""

    def __init__(self, game_folder):
        self.roots = [HERE.parents[2] / "main_menu" / "gfx" / "interface"]
        if game_folder:
            self.roots.append(Path(game_folder) / "main_menu" / "gfx" / "interface")
        self.cache, self.glows = {}, {}

    def get(self, relative, size):
        key = (relative, size)
        if key not in self.cache:
            self.cache[key] = None
            path = next((root / relative for root in self.roots if (root / relative).is_file()), None)
            if Image is not None and path is not None:
                try:
                    image = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
                    self.cache[key] = ImageTk.PhotoImage(image)
                except Exception:  # A broken icon shows as text
                    pass
        return self.cache[key]

    def good(self, good, size=16):
        return self.get(f"icons/trade_goods/icon_goods_{good}.dds", size)

    def building(self, key, size=20):
        if key.startswith("RGO_building_"):
            return self.good(key[len("RGO_building_"):], size)
        return self.get(f"icons/buildings/{key}.dds", size)

    def food(self, size=16):
        return self.get("icons/location_icons/food.dds", size)

    def gold(self, size=16):
        return self.get("icons/resources/gold.dds", size)

    def warning(self, size=16):
        return self.get("icons/icon_warning.dds", size)

    def glow(self, width, height, color, strength):
        """A rounded box whose border has the color and fades out toward the center. Cached per size and color."""
        key = (width, height, color, strength)
        if Image is None or width < 20:
            return None
        if key not in self.glows:
            base = Image.new("RGBA", (width, height), hex_rgb(HOVER if strength > 150 else SIDEBAR) + (255,))
            layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            depth = min(14, height // 2)
            for step in range(depth):
                alpha = int(strength * (1 - step / depth) ** 2)
                draw.rounded_rectangle((step, step, width - 1 - step, height - 1 - step), radius=max(7 - step, 2),
                                       outline=hex_rgb(color) + (alpha,))
            self.glows[key] = ImageTk.PhotoImage(Image.alpha_composite(base, layer))
        return self.glows[key]


class Localization:
    """English names from the game and the mod. A name the mod defines can be edited in its own file."""

    # A name that nothing defines yet is added at the end of this file
    NEW_NAMES = HERE.parents[2] / "main_menu" / "localization" / "english" / "MnT_provisions_buildings_l_english.yml"

    def __init__(self):
        # renames: {old key: new key}. Apply writes the new key on the old key's line and its _desc line.
        self.names, self.where, self.pending, self.renames = {}, {}, {}, {}

    def load(self, game_folder):
        names, where = {}, {}
        roots = [(Path(game_folder) / "main_menu" / "localization" / "english", False)] if game_folder else []
        roots.append((HERE.parents[2] / "main_menu" / "localization" / "english", True))
        for root, in_mod in roots:
            if not root.is_dir():
                continue
            # Files in replace/ win over the others
            for path in sorted(root.rglob("*.yml"), key=lambda path: ("replace" in path.relative_to(root).parts, str(path))):
                try:
                    lines = path.read_text(encoding="utf-8-sig", errors="replace").split("\n")
                except OSError:
                    continue
                for index, line in enumerate(lines):
                    match = LOC_LINE.match(line)
                    if match:
                        names[match[2]] = match[4]
                        if in_mod:
                            where[match[2]] = (path, index)
                        else:
                            where.pop(match[2], None)
        self.names, self.where = names, where

    def name(self, key):
        return self.pending.get(key, self.names.get(key))

    def editable(self, key):
        return key in self.where

    def addable(self, key):
        """True when no file defines the name, so Apply can add it to NEW_NAMES."""
        return key not in self.names

    def set(self, key, text):
        text = text.replace("\n", " ").replace('"', "'")
        if text == self.names.get(key):
            self.pending.pop(key, None)
        else:
            self.pending[key] = text

    def new_lines(self):
        """({path: (bom, lines)}, {new key: (path, index)}) with the pending names put in. Writes nothing."""
        by_file, files, placed = {}, {}, {}
        for key, text in self.pending.items():
            path, index = self.where.get(key, (self.NEW_NAMES, None))
            by_file.setdefault(path, []).append((index, key, text))
        for old in self.renames:
            for key in (old, old + "_desc"):
                if key in self.where and key not in self.pending:
                    path, index = self.where[key]
                    by_file.setdefault(path, []).append((index, key, None))
        for path, edits in by_file.items():
            raw = path.read_bytes()
            lines = raw.decode("utf-8-sig").split("\n")
            cr = "\r" if lines[0].endswith("\r") else ""
            for index, key, text in edits:
                written = self.renamed_key(key)
                if index is None:
                    if lines[-1].strip():
                        lines.append("")
                    lines[-1:-1] = [f' {written}: "{text}"{cr}']
                    placed[written] = (path, len(lines) - 2)
                    continue
                match = LOC_LINE.match(lines[index]) if index < len(lines) else None
                if match and match[2] == key:
                    text = match[4] if text is None else text
                    lines[index] = f'{match[1]}{written}{match[3]} "{text}"{match[5]}'
            files[path] = (raw.startswith(b"\xef\xbb\xbf"), lines)
        return files, placed

    def renamed_key(self, key):
        """The key Apply writes: the new key for a renamed production method or its _desc."""
        for old, new in self.renames.items():
            if key in (old, old + "_desc"):
                return new + key[len(old):]
        return key

    def save(self):
        files, placed = self.new_lines()
        for path, (bom, lines) in files.items():
            path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + "\n".join(lines).encode("utf-8"))
        self.where.update(placed)
        self.names.update(self.pending)
        for key in list(self.where) + list(self.names):
            written = self.renamed_key(key)
            if written != key:
                if key in self.where:
                    self.where[written] = self.where.pop(key)
                if key in self.names:
                    self.names[written] = self.names.pop(key)
        self.pending, self.renames = {}, {}


# ------------------------------------------------------------------ provisions: the window parts

class CanvasTip:
    """A note under the pointer for one canvas item after a short wait."""

    def __init__(self, widget):
        self.widget, self.window, self.waiting, self.text = widget, None, None, None

    def show_later(self, text, x, y):
        if text == self.text:
            return
        self.hide()
        self.text = text
        if text:
            self.waiting = self.widget.after(450, lambda: self.show(x, y))

    def show(self, x, y):
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x + 14}+{y + 16}")
        tk.Label(self.window, text=self.text, background=HOVER, foreground=TEXT, padx=10, pady=6,
                 wraplength=360, justify="left").pack()

    def hide(self):
        if self.waiting:
            self.widget.after_cancel(self.waiting)
            self.waiting = None
        if self.window:
            self.window.destroy()
            self.window = None
        self.text = None


class EquationTip(CanvasTip):
    """CanvasTip with the wait and look of Hint: it shows under the item, and a list of (value, icon) pairs shows as a row."""

    def show_later(self, text, x, y):
        if text == self.text:
            return
        self.hide()
        self.text = text
        if text:
            self.waiting = self.widget.after(600, lambda: self.show(x, y))

    def show(self, x, y):
        self.waiting = None
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        if not isinstance(self.text, list):
            tk.Label(self.window, text=self.text, background=HOVER, foreground=TEXT, padx=10, pady=5,
                     wraplength=340, justify="left").pack()
            return
        row = tk.Frame(self.window, background=HOVER, padx=8, pady=5)
        row.pack()
        for value, icon in self.text:
            image = icon if not isinstance(icon, str) else ""
            tk.Label(row, text=value + (icon if isinstance(icon, str) else ""), image=image,
                     compound="right" if image else "none", background=HOVER, foreground=TEXT, padx=4).pack(side="left")


class EquationCanvas(tk.Canvas):
    """An equation row drawn as canvas items and wrapped into lines like Flow. One shared entry moves to the amount
    under the pointer, so a card needs three widgets (canvas, entry, placeholder label) instead of dozens.

    Terms (dicts): chip, operator, menu, text, break. Each term can have "gap": the space after it (default 6).
    break: starts a new line; its "gap" is the space above that line (default 6).
    chip: background, outline (None or color), padding (left, top, right, bottom; default 6, 3, 4, 3), segments.
    operator: text, joins_next. menu: text, choices [(label, value, image or None)], on_choose, width (chars, default 7), hint.
    text: text, color, font (default "note"), hint.
    Segments in a chip. Text segments carry the 2 px padding of a ttk label. Font names are keys of EquationCanvas.fonts.
    ("icon", image, hint)  ("text", text, color, hint, font)  ("live", key, color, hint, font)
    ("amount", variable, width_chars, options)  ("toggle", text, on_click, active, hint)  ("button", text, on_click)
    ("gap", px): the space before the next segment. The default is 0 after an icon, 4 before a button, else 6.
    amount options: placeholder, choices (strings, or tuples like a menu's), base (default the chip background), color, justify ("right"), pad (x, y)."""
    GAP, LINE_GAP, STEPS, DELAY = 6, 6, 6, 16
    CURSORS = {"amount": "xterm", "toggle": "hand2"}
    fonts, lines, arrow = {}, {}, None

    def __init__(self, parent, width_hint=None, background=BG):
        super().__init__(parent, background=background, highlightthickness=0, borderwidth=0, width=1, height=1)
        if not self.fonts:
            family = tkfont.nametofont("TkDefaultFont").cget("family")
            self.fonts.update(normal=tkfont.nametofont("TkDefaultFont"), bold=tkfont.Font(family=family, size=10, weight="bold"),
                              small=tkfont.Font(family=family, size=8), note=tkfont.Font(family=family, size=9),
                              italic=tkfont.Font(family=family, size=10, slant="italic"),
                              operator=tkfont.Font(family=family, size=14, weight="bold"))
            self.lines.update({name: font.metrics("linespace") for name, font in self.fonts.items()})
            self.lines["zero"] = self.fonts["normal"].measure("0")
        self.width_hint, self.terms, self.live = width_hint, [], {}
        self.zones, self.amounts, self.live_items, self.traces = [], [], {}, []
        self.levels, self.targets = {}, {}  # Fade level and goal of each amount, by variable name, so a redraw keeps them
        self.entry = self.placeholder = self.window = self.active = self.hovered = None
        self.pending = self.job = None
        self.fits = (0, 0)  # The widths that give the same lines as the last draw
        self.tip = EquationTip(self)
        self.bind("<Configure>", lambda _: self.relayout())
        self.bind("<Motion>", self.motion)
        self.bind("<Leave>", self.leave)
        self.bind("<Button-1>", self.click)
        self.bind("<Destroy>", self.destroyed)

    # -------------------------------------------------------------- public

    def set_terms(self, terms):
        self.terms = terms
        if self.pending is None:
            self.pending = self.after_idle(self.draw)

    def set_text(self, key, text):
        old = self.live.get(key, "")
        self.live[key] = text
        if old == text or self.pending is not None or key not in self.live_items:
            return
        item, font = self.live_items[key]
        if self.fonts[font].measure(old) == self.fonts[font].measure(text):
            self.itemconfigure(item, text=text)
        else:
            self.pending = self.after_idle(self.draw)

    def relayout(self):
        """Re-wraps when the width changed enough to move an item to another line."""
        if self.pending is not None or not self.fits[0] <= self.wrap_width() < self.fits[1]:
            self.draw()

    def wrap_width(self):
        # Not shown yet: the hint gives the width it will get, so the first layout is already right
        width = self.winfo_width()
        return width if width > 1 else self.width_hint() if self.width_hint else 100000

    # -------------------------------------------------------------- measure and draw

    def draw(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        width, low, high = self.wrap_width(), 0, 100000
        self.untrace()
        self.delete("all")
        self.window, self.hovered, self.zones, self.amounts, self.live_items = None, None, [], [], {}
        self.tip.hide()
        sizes = [self.measure(term) for term in self.terms]
        lines, line, x, spaces, space = [], [], 0, [], self.LINE_GAP
        for index, term in enumerate(self.terms):
            if term["kind"] == "break":
                if line:
                    lines.append(line)
                    spaces.append(space)
                line, x, space = [], 0, term.get("gap", self.LINE_GAP)
                continue
            need = x + sizes[index][0]
            if line and need <= width:
                low = max(low, need)
            elif line:
                high = min(high, need)
                # An operator moves down with the item after it
                carry = [line.pop()] if len(line) > 1 and self.terms[line[-1]].get("joins_next") else []
                lines.append(line)
                spaces.append(space)
                line, space, x = carry, self.LINE_GAP, sum(sizes[other][0] + self.terms[other].get("gap", self.GAP) for other in carry)
            line.append(index)
            x += sizes[index][0] + term.get("gap", self.GAP)
        if line:
            lines.append(line)
            spaces.append(space)
        self.fits = (low, high)
        y = 0
        for number, line in enumerate(lines):
            y += spaces[number] if number else 0
            height, x = max(sizes[index][1] for index in line), 0
            for index in line:
                self.paint_term(self.terms[index], x, y + (height - sizes[index][1]) // 2, sizes[index])
                x += sizes[index][0] + self.terms[index].get("gap", self.GAP)
            y += height
        height = max(y, 1)
        if int(self.cget("height")) != height:
            self.configure(height=height)
        # The entry stays on its amount through a redraw. If that amount is gone, the entry lets go of the focus.
        if self.active is not None:
            again = next((amount for amount in self.amounts if amount["key"] == self.active["key"]), None)
            self.active = None
            if again is not None:
                self.put_entry(again)
            elif self.focus_get() is self.entry:
                self.focus_set()

    def measure(self, term):
        """(width, height, segment places) of a term."""
        kind, fonts, lines = term["kind"], self.fonts, self.lines
        if kind == "operator":
            return fonts["operator"].measure(term["text"]) + 12, lines["operator"] + 4, None
        if kind == "menu":
            return term.get("width", 7) * lines["zero"] + 29, lines["normal"] + 12, None
        if kind == "text":
            font = term.get("font", "note")
            return fonts[font].measure(term["text"]) + 4, lines[font] + 4, None
        if kind != "chip":
            return 0, 0, None
        left, top, right, bottom = term.get("padding", (6, 3, 4, 3))
        places, x, gap, previous = [], left, None, None
        for segment in term["segments"]:
            kind = segment[0]
            if kind == "gap":
                gap = segment[1]
                continue
            size = self.segment_size(segment)
            if size is None:
                continue
            if places:
                joined = gap is None and previous == "icon"
                x += 0 if joined else gap if gap is not None else 4 if kind == "button" else 6
                if joined and kind in ("text", "live"):
                    # Text right after an icon centers on the icon, as in one ttk label with both
                    size = size[0], max(size[1], places[-1][3])
            places.append((segment, x) + size)
            x += size[0]
            gap, previous = None, kind
        inner = max((place[3] for place in places), default=0)
        return x + right, top + inner + bottom, places

    def segment_size(self, segment):
        kind, lines = segment[0], self.lines
        if kind == "icon":
            image = segment[1]
            return (image.width() + 4, image.height() + 4) if image else None
        if kind in ("text", "live"):
            font = segment[4] if len(segment) > 4 else "normal"
            text = segment[1] if kind == "text" else self.live.get(segment[1], "")
            return self.fonts[font].measure(text) + 4, lines[font] + 4
        if kind == "toggle":
            return self.fonts["normal"].measure(segment[1]) + 8, lines["normal"] + 6
        if kind == "button":
            return max(2 * lines["zero"], self.fonts["normal"].measure(segment[1])) + 8, lines["normal"]
        options = segment[3] if len(segment) > 3 else {}
        pad_x, pad_y = options.get("pad", (0, 0))
        # A Tk entry's text sits inside its highlight, border and one more pixel
        width = self.fit_width(segment) if self.fits_value(segment) else segment[2] * lines["zero"]
        width += 2 * (2 + pad_x)
        return width + (13 if options.get("choices") else 0), lines["normal"] + 2 * (2 + pad_y)

    @staticmethod
    def fits_value(segment):
        """A plain amount box is as wide as its value. Boxes with a placeholder or a dropdown keep their width."""
        options = segment[3] if len(segment) > 3 else {}
        return not options.get("placeholder") and not options.get("choices")

    def fit_width(self, segment):
        """The value's width, at least two digits, plus room for the cursor."""
        zero = self.lines["zero"]
        return max(self.fonts["normal"].measure(segment[1].get()), 2 * zero) + zero // 2 + 2

    def paint_term(self, term, x, y, size):
        width, height, places = size
        kind, fonts, lines = term["kind"], self.fonts, self.lines
        if kind == "operator":
            self.create_text(x + 6, y + 2, text=term["text"], anchor="nw", fill=FAINT, font=fonts["operator"])
        elif kind == "text":
            self.create_text(x + 2, y + 2, text=term["text"], anchor="nw", fill=term.get("color", FAINT),
                             font=fonts[term.get("font", "note")])
            if term.get("hint"):
                self.zones.append([x, y, x + width, y + height, "hint", None, term["hint"]])
        elif kind == "menu":
            self.create_rectangle(x, y, x + width - 1, y + height - 1, fill=BG, outline=BORDER)
            arrow = self.create_rectangle(x + width - 14, y, x + width - 1, y + height - 1, fill=BG, outline=BORDER)
            self.create_text(x + 8, y + 6, text=term["text"], anchor="nw", fill=ACCENT, font=fonts["normal"])
            self.triangle(x + width - 7, y + height // 2)
            self.zones.append([x, y, x + width, y + height, "menu", (arrow, BG, term["choices"], term["on_choose"], FIELD),
                               term.get("hint")])
        elif kind == "chip":
            background = term["background"]
            self.create_rectangle(x, y, x + width - 1, y + height - 1, fill=background, outline=term.get("outline") or background)
            top, bottom = term.get("padding", (6, 3, 4, 3))[1::2]
            inner = height - top - bottom
            for segment, left, segment_width, segment_height in places:
                self.paint_segment(segment, x + left, y + top + (inner - segment_height) // 2, segment_width,
                                   segment_height, background, y, y + height)

    def paint_segment(self, segment, x, y, width, height, background, chip_top, chip_bottom):
        kind, fonts = segment[0], self.fonts
        hint = None
        if kind == "icon":
            self.create_image(x + 2, y + 2, image=segment[1], anchor="nw")
            hint = segment[2] if len(segment) > 2 else None
        elif kind in ("text", "live"):
            color, hint = segment[2], segment[3] if len(segment) > 3 else None
            font = segment[4] if len(segment) > 4 else "normal"
            text = segment[1] if kind == "text" else self.live.get(segment[1], "")
            item = self.create_text(x + 2, y + (height - self.lines[font]) // 2, text=text, anchor="nw", fill=color,
                                    font=fonts[font])
            if kind == "live":
                self.live_items[segment[1]] = (item, font)
        elif kind == "toggle":
            color = TEXT if segment[3] else FAINT
            item = self.create_text(x + 4, y + 3, text=segment[1], anchor="nw", fill=color, font=fonts["normal"])
            self.zones.append([x, y, x + width, y + height, "toggle", (item, color, segment[2]),
                               segment[4] if len(segment) > 4 else None])
        elif kind == "button":
            box = self.create_rectangle(x, y, x + width - 1, y + height - 1, fill=background, outline="")
            item = self.create_text(x + (width - fonts["normal"].measure(segment[1])) // 2, y, text=segment[1], anchor="nw",
                                    fill=MUTED, font=fonts["normal"])
            self.zones.append([x, y, x + width, y + height, "button", (box, item, background, segment[2]), None])
        elif kind == "amount":
            self.paint_amount(segment, x, y, width, height, background)
        if hint:
            self.zones.append([x, chip_top, x + width, chip_bottom, "hint", None, hint])

    def paint_amount(self, segment, x, y, width, height, background):
        variable, chars = segment[1], segment[2]
        options = segment[3] if len(segment) > 3 else {}
        base = options.get("base", background)
        pad_x = options.get("pad", (0, 0))[0]
        box_width = width - (13 if options.get("choices") else 0)
        amount = {"key": str(variable), "var": variable, "box": (x, y, x + box_width, y + height), "base": base,
                  "inset": 2 + pad_x, "justify": options.get("justify", "right"), "color": options.get("color", TEXT),
                  "placeholder": options.get("placeholder", ""), "segment": segment, "width": box_width,
                  "line": base if options.get("choices") else FAINT}  # A dropdown field shows no hover outline
        share = self.levels.get(amount["key"], 0) / self.STEPS
        amount["rect"] = self.create_rectangle(x, y, x + box_width - 1, y + height - 1, fill=mix(base, FIELD, share),
                                               outline=mix(base, amount["line"], share))
        right = amount["justify"] == "right"
        amount["spot"] = (x + box_width - amount["inset"] if right else x + amount["inset"], y + (height - self.lines["normal"]) // 2)
        amount["text"] = self.create_text(*amount["spot"], anchor="ne" if right else "nw", font=self.fonts["normal"])
        self.show_value(amount)
        self.traces.append((variable, variable.trace_add("write", lambda *_: self.show_value(amount))))
        self.amounts.append(amount)
        self.zones.append([x, y, x + box_width, y + height, "amount", amount, None])
        if options.get("choices"):
            arrow = self.create_rectangle(x + box_width, y, x + width - 1, y + height - 1, fill=base, outline="")
            self.triangle(x + box_width + 6, y + height // 2)
            choices = [(choice, choice, None) if isinstance(choice, str) else choice for choice in options["choices"]]
            self.zones.append([x + box_width, y, x + width, y + height, "menu", (arrow, base, choices, variable.set, HOVER), None])

    def triangle(self, x, y):
        # The ttk dropdown arrow: rows of 7, 5, 3 and 1 pixels
        if EquationCanvas.arrow is None:
            EquationCanvas.arrow = tk.PhotoImage(width=7, height=4)
            for row in range(4):
                EquationCanvas.arrow.put(MUTED, to=(row, row, 7 - row, row + 1))
        self.create_image(x - 3, y - 1, image=EquationCanvas.arrow, anchor="nw")

    def show_value(self, amount):
        value = amount["var"].get()
        self.itemconfigure(amount["text"], text=value or amount["placeholder"], fill=amount["color"] if value else FAINT)
        # Placeholder text sits one pixel below the value, as placeholder() puts it
        x, y = amount["spot"]
        self.coords(amount["text"], x, y if value else y + 1)
        if amount is self.active:
            self.show_placeholder()
        segment = amount["segment"]
        if self.fits_value(segment) and self.pending is None and self.segment_size(segment)[0] != amount["width"]:
            self.pending = self.after_idle(self.draw)  # The box grows or shrinks with the value

    def untrace(self):
        for variable, trace in self.traces:
            try:
                variable.trace_remove("write", trace)
            except tk.TclError:  # The variable is gone already
                pass
        self.traces = []

    def destroyed(self, event):
        if event.widget is not self:
            return
        self.untrace()
        self.tip.hide()
        for job in (self.pending, self.job):
            if job is not None:
                self.after_cancel(job)
        self.pending = self.job = None

    # -------------------------------------------------------------- pointer

    def zone_at(self, x, y):
        return next((zone for zone in self.zones if zone[0] <= x < zone[2] and zone[1] <= y < zone[3]), None)

    def motion(self, event):
        zone = self.zone_at(event.x, event.y)
        if zone is self.hovered:
            return
        if self.hovered is not None:
            self.hover(self.hovered, False)
        self.hovered = zone
        cursor = self.CURSORS.get(zone[4], "") if zone else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)
        if zone is None or zone[6] is None:
            self.tip.hide()
            if zone:
                self.hover(zone, True)
            return
        self.tip.show_later(zone[6], self.winfo_rootx() + zone[0], self.winfo_rooty() + zone[3] + 6)
        self.hover(zone, True)

    def leave(self, _):
        if self.on_entry():  # The pointer moved onto the entry, which is part of this canvas
            return
        self.tip.hide()
        if self.hovered is not None:
            self.hover(self.hovered, False)
            self.hovered = None

    def hover(self, zone, on):
        kind, data = zone[4], zone[5]
        if kind == "amount":
            if on and (self.focus_get() is not self.entry or self.active is data):
                self.put_entry(data)
            self.fade(data, on or (data is self.active and self.focus_get() is self.entry))
        elif kind == "toggle":
            self.itemconfigure(data[0], fill=ACCENT_HOVER if on else data[1])
        elif kind == "button":
            self.itemconfigure(data[0], fill=BORDER if on else data[2])
            self.itemconfigure(data[1], fill=BAD if on else MUTED)
        elif kind == "menu":
            self.itemconfigure(data[0], fill=data[4] if on else data[1])

    def click(self, event):
        self.tip.hide()
        zone = self.zone_at(event.x, event.y)
        kind = zone[4] if zone else None
        if kind == "amount":
            self.put_entry(zone[5])
            self.entry.focus_set()
            self.entry.icursor(f"@{event.x - zone[0]}")
        elif kind in ("toggle", "button"):
            zone[5][-1]()
        elif kind == "menu":
            ChoicePopup(self, self.winfo_rootx() + zone[0], self.winfo_rooty() + zone[3], zone[5][2], zone[5][3])
        elif self.focus_get() is self.entry:
            self.focus_set()  # A click beside the amounts lets go of the entry

    # -------------------------------------------------------------- the shared entry

    def make_entry(self):
        self.entry = tk.Entry(self, relief="flat", highlightthickness=1, highlightcolor=ACCENT, foreground=TEXT,
                              insertbackground=TEXT, selectbackground=ACCENT, font="TkDefaultFont")
        # Grey text in an empty field, like placeholder()
        self.placeholder = tk.Label(self.entry, foreground=FAINT, cursor="xterm", padx=0, pady=0, borderwidth=0,
                                    font="TkDefaultFont")
        self.placeholder.bind("<Button-1>", lambda _: self.entry.focus_set())
        for widget in (self.entry, self.placeholder):
            widget.bind("<Leave>", self.leave_entry)
        self.entry.bind("<FocusIn>", lambda _: self.active and self.fade(self.active, True))
        self.entry.bind("<FocusOut>", lambda _: self.active and self.fade(self.active, self.on_entry()))
        self.entry.bind("<Tab>", lambda _: self.tab(1))
        self.entry.bind("<Shift-Tab>", lambda _: self.tab(-1))

    def on_entry(self):
        if self.entry is None:
            return False
        return self.winfo_containing(*self.winfo_pointerxy()) in (self.entry, self.placeholder)

    def leave_entry(self, _):
        if self.on_entry() or self.active is None:
            return
        self.hovered = None  # The next motion on the canvas finds the zone again
        self.fade(self.active, self.focus_get() is self.entry)

    def put_entry(self, amount):
        if self.entry is None:
            self.make_entry()
        if self.active is not None and self.active is not amount:
            self.fade(self.active, False)
        if self.active is amount and self.window is not None and self.itemcget(self.window, "state") != "hidden":
            return
        self.active = amount
        x0, y0, x1, y1 = amount["box"]
        self.entry.configure(textvariable=amount["var"], justify=amount["justify"], borderwidth=amount["inset"] - 2)
        if self.window is None:
            self.window = self.create_window(x0, y0, window=self.entry, anchor="nw", width=x1 - x0, height=y1 - y0)
        else:
            self.coords(self.window, x0, y0)
            self.itemconfigure(self.window, width=x1 - x0, height=y1 - y0, state="normal")
        self.paint(amount)
        self.show_placeholder()

    def show_placeholder(self):
        amount = self.active
        if not amount["placeholder"] or amount["var"].get():
            self.placeholder.place_forget()
        else:
            # place() counts from inside the highlight and border, so the text sits where the canvas draws it
            x0, y0, x1, y1 = amount["box"]
            y = (y1 - y0 - self.lines["normal"]) // 2 - amount["inset"] + 2
            right = amount["justify"] == "right"
            self.placeholder.configure(text=amount["placeholder"])
            self.placeholder.place(relx=1 if right else 0, x=-1 if right else 1, y=y, anchor="ne" if right else "nw")

    def tab(self, step):
        if self.active not in self.amounts:
            return None
        index = self.amounts.index(self.active) + step
        if not 0 <= index < len(self.amounts):
            return None  # Past the last amount, Tab goes on to the next widget
        self.put_entry(self.amounts[index])
        self.fade(self.active, True)
        self.entry.select_range(0, "end")
        self.entry.icursor("end")
        return "break"

    def fade(self, amount, on):
        self.targets[amount["key"]] = 1 if on else 0
        if self.job is None:
            self.step()

    def step(self):
        self.job = None
        moving = False
        for amount in self.amounts:
            key = amount["key"]
            level, goal = self.levels.get(key, 0), self.targets.get(key, 0) * self.STEPS
            if level != goal:
                self.levels[key] = level + (1 if goal > level else -1)
                self.paint(amount)
                moving = True
        if moving:
            self.job = self.after(self.DELAY, self.step)
        elif self.active is not None and not self.levels.get(self.active["key"]) and self.focus_get() is not self.entry:
            # Faded out: hide the entry, and the text under it shows the value
            self.itemconfigure(self.window, state="hidden")
            self.active = None

    def paint(self, amount):
        share = self.levels.get(amount["key"], 0) / self.STEPS
        background, line = mix(amount["base"], FIELD, share), mix(amount["base"], amount["line"], share)
        self.itemconfigure(amount["rect"], fill=background, outline=line)
        if amount is self.active:
            self.entry.configure(background=background, highlightbackground=line)
            self.placeholder.configure(background=background)


def icon_label(parent, image, text="", style="TLabel", **options):
    """An icon with text beside it. Without the icon, only the text shows."""
    label = ttk.Label(parent, text=text, image=image or "", compound="left" if image else "none", style=style, **options)
    return label


class LiveText:
    """Stands in for a label whose text the card sets later; the text lives on the equation canvas."""

    def __init__(self, canvas, key):
        self.canvas, self.key = canvas, key

    def configure(self, text="", **_):
        self.canvas.set_text(self.key, text)


class MethodCard:
    """One method as an equation: inputs + inputs = food out. Edits are kept here until the document writes them."""

    def __init__(self, document, parent, name):
        self.doc, self.name = document, name
        self.app, self.tool = document.app, document.tool
        self.icons, self.loc, self.model = self.tool.icons, self.tool.loc, self.tool.model
        self.section = document.file.section(name)
        self.changed, self.focused, self.hovered = set(), False, False
        self.frame = tk.Frame(parent, background=BG, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        self.bar = tk.Frame(self.frame, background=FAINT, width=4)
        self.bar.pack(side="left", fill="y")
        self.body = ttk.Frame(self.frame, padding=(14, 10, 14, 10))
        self.body.pack(side="left", fill="both", expand=True)
        self.frame.bind("<Enter>", lambda _: self.hover(True))
        self.frame.bind("<Leave>", self.leave)
        self.build_top()
        self.equation = EquationCanvas(self.body, lambda inset=self.doc.card_inset: self.doc.canvas.winfo_width() - 84 - inset)
        self.equation.pack(fill="x", pady=(8, 0))
        if self.section is None:
            self.build_outside()
        else:
            values = {setting["key"]: document.file.value(setting) for setting in self.section["settings"]}
            self.food_out = tk.StringVar(value="" if values.get("food_out", "None").lower() == "none" else values["food_out"])
            # Each food input: good, number, and whether the number is a fixed amount or a share
            self.recipe = [[good, tk.StringVar(value=share), False] for good, share in parse_map(values.get("recipe", "None")) or []]
            self.recipe += [[good, tk.StringVar(value=amount), True]
                            for good, amount in parse_map(values.get("recipe_fixed", "None")) or []]
            # Each other input: good, amount, and whether the amount is a percent of the provisions made
            self.other = [[good, tk.StringVar(value=amount), False] for good, amount in parse_map(values.get("other", "None")) or []]
            self.other += [[good, tk.StringVar(value=share), True]
                           for good, share in parse_map(values.get("other_percent", "None")) or []]
            self.small = {key: tk.StringVar(value="" if values.get(key, "None").lower() == "none" else values[key])
                          for key in ("efficiency", "min_profit", "max_profit")}
            self.fixed = "" if values.get("fixed", "None").lower() == "none" else values["fixed"].lower()
            self.food_out.trace_add("write", lambda *_: self.touch("food_out"))
            for key, variable in self.small.items():
                variable.trace_add("write", lambda *_, key=key: self.touch(key))
            self.build_equation()
        self.flag_line = ttk.Label(self.body, style="Flag.TLabel", wraplength=900, justify="left")
        self.update()

    # -------------------------------------------------------------- layout

    def build_top(self):
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        self.doc.name_field(top, self.name, 34)
        places = self.model.game["places"].get(self.name) if self.model.game else None
        if self.doc.removable(self.name):
            self.doc.remove_button(top, self.name)
        elif self.section is not None and not places:
            remove = ttk.Button(top, text="Remove from settings", style="Danger.TButton",
                                command=lambda: self.doc.delete_method(self.name))
            remove.pack(side="right", padx=(14, 0))
        self.flag = ttk.Label(top, cursor="question_arrow")
        self.flag.pack(side="right", padx=(10, 0))
        self.flag_hint = Hint(self.flag, "")
        self.profit = icon_label(top, self.icons.gold(16), style="Muted.TLabel")
        self.profit.pack(side="right", padx=(10, 0))
        self.margin = ttk.Label(top, style="Margin.TLabel")
        self.margin.pack(side="right")

    def hover(self, on):
        self.hovered = on
        self.paint_border()

    def leave(self, event):
        # Leave also fires when the pointer moves onto a widget inside the card
        under = self.frame.winfo_containing(event.x_root, event.y_root)
        if under is None or not str(under).startswith(str(self.frame)):
            self.hover(False)

    def paint_border(self):
        result = self.model.results.get(self.name)
        health = result["health"] if result else "none"
        color = ACCENT if self.focused else HEALTH_COLOR[health] if health in ("bad", "warn") else BORDER
        if self.hovered:
            color = ACCENT_HOVER if self.focused else lighten(color) if color != BORDER else MUTED
        self.frame.configure(highlightbackground=color, highlightcolor=color, highlightthickness=2 if self.focused else 1)

    def good_segments(self, good, size=18):
        """A good's icon and name, with its price and food in the hint."""
        source = milk_source(good)
        name = f"milk ({(self.loc.name(source) or source).lower()})" if source else self.loc.name(good) or good
        image = self.icons.good(source or good, size)
        prices = (getattr(self.model, "prices", None) or self.model.game["prices"]) if self.model.game else {}
        food = self.model.food_per_unit.get(good)
        parts = [(name, "")] if image and not self.doc.show_names.get() else []
        if not source:
            parts.append((number_text(prices.get(good, 0)), self.icons.gold(16) or " gold"))
        if food:
            parts.append((number_text(food), self.icons.food(16) or " food"))
        text = self.label_text(name, image)
        return [("icon", image, parts)] + ([("text", text, TEXT, parts)] if text else [])

    def label_text(self, name, image):
        """The good's name beside its icon, unless the goods names are off. Without an icon the name always shows."""
        return name if self.doc.show_names.get() or not image else ""

    def goods_choices(self, goods):
        return goods_choices(goods, self.tool)

    def gold_segments(self, key):
        """A small coin and the gold value, set later by key: an input's cost or the output's value."""
        coin = self.icons.gold(12)
        return [("gap", 6)] + ([("icon", coin, None), ("gap", 1)] if coin else []) + [("live", "gold " + key, MUTED, None, "small")]

    def show_gold(self, amounts, produced, output):
        prices = getattr(self.model, "prices", None) or self.model.game["prices"]
        for good, amount in amounts.items():
            self.equation.set_text("gold " + good, number_text(round(amount * prices.get(good, 0), 3)))
        if produced:
            self.equation.set_text("gold out", number_text(round(output * prices.get(produced, 0), 3)))

    def build_equation(self):
        canvas, terms = self.equation, []
        inherited = self.inherited()
        for key, label, width in (("efficiency", "food conversion efficiency %", 5), ("min_profit", "min profit", 16),
                                  ("max_profit", "max profit", 16)):
            terms.append({"kind": "text", "text": label, "color": FAINT, "gap": 4})
            options = {"placeholder": inherited.get(key, ("not set", None))[0], "justify": "left", "pad": (4, 2)}
            segments = [("amount", self.small[key], width, options)]
            if key != "efficiency":
                values = self.app.names.get("profit_values", {})
                options["choices"] = [(f"{name}   {profit_number(name, values)}", name, None) for name in self.app.names.get("profit", [])]
                segments += [("live", "value " + key, MUTED, None, "small"), ("gap", 4)]
            terms.append({"kind": "chip", "background": FIELD, "padding": (0, 0, 0, 0), "gap": 18, "segments": segments})
        # Which side stays when food values change. The one in use is plain text; a click on the other switches.
        fixed = self.fixed_side()
        terms.append({"kind": "text", "text": "fixed", "color": FAINT, "gap": 4})
        for side, hint in (("output", "Keep food out. The inputs follow the food values."),
                           ("inputs", "Keep the input amounts. Food out follows the food values.")):
            if side == fixed:
                terms.append({"kind": "chip", "background": ACCENT, "padding": (6, 4, 6, 4), "gap": 0,
                              "segments": [("text", side, "#ffffff", None)]})
            else:
                terms.append({"kind": "chip", "background": FIELD, "padding": (4, 3, 4, 3), "gap": 0,
                              "segments": [("toggle", side, lambda side=side: self.set_fixed(side), False, hint)]})
        terms.append({"kind": "break", "gap": 8})
        self.amount_labels = {}
        inputs_fixed = fixed == "inputs"
        shared = [row for row in self.recipe if not row[2]]
        show_share = inputs_fixed or len(self.recipe) > 1 or (shared and self.share_total() != 100)
        rows = [(row, True) for row in self.recipe] + [(row, False) for row in self.other]
        for index, (row, in_recipe) in enumerate(rows):
            if index:
                terms.append({"kind": "operator", "text": "+", "joins_next": True})
            good = row[0]
            milk = good == MILK
            segments = [("icon", self.icons.food(16), None), ("text", "milk", MUTED, None, "italic")] if milk \
                else self.good_segments(good)
            remove = lambda rows=self.recipe if in_recipe else self.other, row=row: self.remove_good(rows, row)
            if in_recipe and row[2] and not inputs_fixed:
                # A fixed food good: the number is the amount. A click on "share" turns it back into a share.
                segments += [("amount", row[1], 6, {}), ("gap", 4),
                             ("toggle", "share", lambda row=row: self.swap_recipe_unit(row), False,
                              "Use a share of the food left after the fixed goods."), ("gap", 0),
                             ("text", "fixed", TEXT, None)]
                segments += ([] if milk_source(good) else self.gold_segments(good)) + [("button", "✕", remove)]
                row[1].trace_add("write", lambda *_: self.touch("recipe"))
                terms.append({"kind": "chip", "background": HOVER, "segments": segments})
                continue
            if in_recipe and inputs_fixed:
                # Fixed inputs: the number is the amount
                segments += [("amount", row[1], 6, {})] + ([] if milk_source(good) else self.gold_segments(good)) \
                    + [("button", "✕", remove)]
                row[1].trace_add("write", lambda *_: self.touch("recipe"))
                terms.append({"kind": "chip", "background": HOVER, "segments": segments})
                continue
            if in_recipe:
                if show_share:
                    segments += [("amount", row[1], 6, {}), ("gap", 0), ("text", "%", FAINT if milk else MUTED, None, "small")]
                    row[1].trace_add("write", lambda *_: self.touch("recipe"))
                if milk:
                    segments += [("text", "no input", FAINT, None, "small"), ("button", "✕", remove)]
                    terms.append({"kind": "chip", "background": BG, "outline": FAINT, "padding": (7, 4, 7, 4), "segments": segments})
                    continue
                hint = 'This amount is set by "food out"' + (" and its share." if show_share else ".")
                segments += [("gap", 4), ("text", "share", TEXT, None), ("gap", 0),
                             ("toggle", "fixed", lambda row=row: self.swap_recipe_unit(row), False,
                              "Use a fixed amount. The other shares divide the food left.")]
                # Milk is not bought, so it has no gold
                segments += [("live", "in " + good, MUTED, hint, "small")] + ([] if milk_source(good) else self.gold_segments(good)) \
                    + [("button", "✕", remove)]
                self.amount_labels[good] = LiveText(canvas, "in " + good)
            else:
                # Both units show. The one in use is plain text; a click on the other switches to it.
                swap = lambda row=row: self.swap_unit(row)
                units = [("flat", "Use a fixed amount.", not row[2]), ("%", "Use a percent of the provisions made.", row[2])]
                segments += [("amount", row[1], 6, {})]
                for unit, hint, in_use in units:
                    segments += [("gap", 0), ("text", unit, TEXT, None) if in_use else ("toggle", unit, swap, False, hint)]
                if row[2]:
                    segments += [("gap", 4), ("live", "in " + good, MUTED, 'This amount is set by "food out" and its percent.', "small")]
                    self.amount_labels[good] = LiveText(canvas, "in " + good)
                row[1].trace_add("write", lambda *_: self.touch("other"))
                segments += self.gold_segments(good) + [("button", "✕", remove)]
            terms.append({"kind": "chip", "background": HOVER, "segments": segments})
        used = {row[0] for row in self.recipe + self.other}
        food_goods = [good for good in self.model.food_per_unit if good not in used]
        terms.append({"kind": "menu", "text": "+ food", "hint": "Add a food input",
                      "choices": ([] if MILK in used or inputs_fixed or any(map(milk_source, food_goods))
                                  else [(MILK_CHOICE, MILK, self.icons.food(16))])
                      + self.goods_choices(food_goods),
                      "on_choose": lambda good: self.add_good(self.recipe, good)})
        every_good = self.model.game["goods"] if self.model.game else []
        terms.append({"kind": "menu", "text": "+ other", "choices": self.goods_choices([good for good in every_good if good not in used]),
                      "on_choose": lambda good: self.add_good(self.other, good)})
        terms.append({"kind": "operator", "text": "=", "joins_next": True})
        # Each part reads like an input: icon, name, amount, then gold
        food = self.icons.food(18)
        out = [("icon", food, None)]
        if self.label_text("food", food):
            out.append(("text", self.label_text("food", food), GOOD, None, "bold"))
        out += [("live", "food", MUTED, "The inputs set this amount.", "small") if inputs_fixed else ("amount", self.food_out, 5, {}),
                ("gap", 8), ("text", "→", FAINT, None), ("gap", 8)]
        name = self.loc.name("provisions") or "provisions"
        image = self.icons.good("provisions", 18)
        out.append(("icon", image, None))
        if self.label_text(name, image):
            out.append(("text", self.label_text(name, image), GOOD, None, "bold"))
        out += [("live", "out", MUTED, 'This amount is set by "food out".', "small")] + self.gold_segments("out")
        terms.append({"kind": "chip", "background": OUT_BG, "padding": (6, 3, 8, 3), "segments": out})
        terms.append({"kind": "chip", "background": BG, "padding": (0, 0, 0, 0), "segments": [("live", "warn", WARN, None, "note")]})
        self.provisions, self.total_warning = LiveText(canvas, "out"), LiveText(canvas, "warn")
        self.food_label = LiveText(canvas, "food")
        canvas.set_terms(terms)

    def build_outside(self):
        """A method the settings do not have yet: today's numbers, read only."""
        result = self.model.results.get(self.name)
        terms = []
        if result:
            for index, (good, amount) in enumerate(result["inputs"].items()):
                if index:
                    terms.append({"kind": "operator", "text": "+", "joins_next": True})
                terms.append({"kind": "chip", "background": HOVER,
                              "segments": self.good_segments(good) + [("text", number_text(amount), MUTED, None, "small")]})
            terms.append({"kind": "operator", "text": "=", "joins_next": True})
            terms.append({"kind": "chip", "background": OUT_BG, "padding": (6, 3, 8, 3),
                          "segments": [("icon", self.icons.food(18), None), ("text", "food", GOOD, None, "bold"),
                                       ("text", number_text(result['food_out']), MUTED, None, "small")]})
        self.equation.set_terms(terms)
        line = ttk.Frame(self.body)
        line.pack(fill="x", pady=(8, 0))
        ttk.Label(line, text="Not in settings, so nothing here can be edited yet.", style="Muted.TLabel").pack(side="left")
        ttk.Button(line, text="Sync From Files", command=lambda: self.doc.action(["--import"], None)).pack(side="left", padx=(10, 0))

    # -------------------------------------------------------------- values

    def inherited(self):
        """The building's or the general value each small setting falls back to, as placeholder text."""
        found = {}
        for section_name in self.tool.default_chain(self.doc.file, self.name):
            section = self.doc.file.section(section_name)
            for setting in section["settings"] if section else []:
                if setting["key"] not in found:
                    found[setting["key"]] = (self.doc.file.value(setting), section_name)
        return found

    def share_total(self):
        total = 0.0
        for _, share, fixed in self.recipe:
            if fixed:
                continue
            try:
                total += float(share.get().rstrip("%"))
            except ValueError:
                pass
        return round(total, 3)

    def touch(self, key):
        self.changed.add(key)
        self.doc.edited()

    def add_good(self, rows, good):
        if not good or good.startswith("+"):
            return
        # A milk type takes over the plain milk's share, so the recipe still totals 100
        plain = next((row for row in self.recipe if row[0] == MILK), None) if rows is self.recipe and milk_source(good) else None
        if plain:
            plain[0] = good
            self.touch("recipe")
            self.build_equation()
            self.update()
            return
        if rows is not self.recipe:
            start = "0.001"
        elif self.fixed_side() == "inputs":
            start = "0.1"
        else:
            start = f"{max(0.0, 100 - self.share_total()):g}"
        rows.append([good, tk.StringVar(value=start), False])
        self.touch("recipe" if rows is self.recipe else "other")
        self.build_equation()
        self.update()

    def remove_good(self, rows, row):
        rows.remove(row)
        self.touch("recipe" if rows is self.recipe else "other")
        self.build_equation()
        self.update()

    def fixed_side(self):
        """This method's fixed side, else the general one, else output."""
        return self.fixed or (self.inherited().get("fixed", ("output", None))[0] or "output").lower()

    def set_fixed(self, side):
        """Switches the fixed side and keeps today's numbers: the inputs become fixed amounts, or the food
        out and the food shares come back from the amounts."""
        result = self.model.results.get(self.name)
        amounts = dict(result["inputs"]) if result else {}
        if side == "inputs":
            amounts.update(self.plain_milk_to_type())
            for row in self.recipe:
                if row[0] in amounts:
                    row[1].set(number_text(round(amounts[row[0]], 5)))
        else:
            self.reshare()
            if result:
                self.food_out.set(number_text(round(result["food_out"], 5)))
        self.fixed = side
        self.touch("fixed")
        self.touch("recipe")
        self.build_equation()
        self.update()

    def plain_milk_to_type(self):
        """Plain milk has no amount to fix. It becomes the milk type of the building's herd, with the same food.
        Returns {milk type: amount}, or nothing when there is no plain milk or no milk type for the herd."""
        plain = next((row for row in self.recipe if row[0] == MILK), None)
        raw = self.model.raw.get(self.name, {})
        owners = " ".join(raw.get("owners", []))
        milk_type = next((good for good in self.model.food_per_unit if milk_source(good) and milk_source(good) in owners), None)
        if plain is None or milk_type is None or not raw.get("setting"):
            return {}
        try:
            share = float(plain[1].get())
        except ValueError:
            share = 0.0
        setting = raw["setting"]
        milk_food = share / 100 * raw["food_out"] / setting["efficiency"]
        plain[0] = milk_type
        return {milk_type: milk_food / self.model.food_per_unit[milk_type]}

    def reshare(self):
        """Sets the shares from today's amounts: each share good's part of the food the fixed goods leave."""
        amounts = self.model.results[self.name]["inputs"] if self.name in self.model.results else {}
        food = {row[0]: amounts.get(row[0], 0) * self.model.food_per_unit.get(row[0], 0) for row in self.recipe if not row[2]}
        total = sum(food.values())
        for row in self.recipe:
            if not row[2]:
                row[1].set(number_text(round(100 * food[row[0]] / total, 2)) if total else "0")

    def swap_recipe_unit(self, row):
        """A share becomes a fixed amount, or back. Today's amounts stay; the other shares change to fit."""
        amounts = self.model.results[self.name]["inputs"] if self.name in self.model.results else {}
        row[2] = not row[2]
        if row[2]:
            row[1].set(number_text(round(amounts.get(row[0], 0), 5)))
        self.reshare()
        self.touch("recipe")
        self.build_equation()
        self.update()

    def swap_unit(self, row):
        """A fixed amount becomes a percent of the provisions made, or back, with the same amount."""
        result = self.model.results.get(self.name)
        output = result["output"] if result else 0
        try:
            value = float(row[1].get())
        except ValueError:
            value = 0.0
        if row[2]:
            row[1].set(number_text(round(value / 100 * output, 5)))
        else:
            row[1].set(number_text(round(value / output * 100, 3)) if output else "0")
        row[2] = not row[2]
        self.touch("other")
        self.build_equation()
        self.update()

    def edits(self):
        """(section, setting, value) for each setting changed on this card."""
        if self.section is None:
            return []
        out = []
        for key in self.changed:
            if key == "food_out":
                value = self.food_out.get().strip() or "None"
            elif key == "recipe":
                out.append((self.name, "recipe_fixed",
                            map_text([(good, amount.get().strip() or "0") for good, amount, fixed in self.recipe if fixed])))
                value = map_text([(good, share.get().strip() or "0") for good, share, fixed in self.recipe if not fixed])
            elif key == "fixed":
                value = self.fixed or "None"
            elif key == "other":
                out.append((self.name, "other_percent",
                            map_text([(good, amount.get().strip() or "0") for good, amount, is_percent in self.other if is_percent])))
                value = map_text([(good, amount.get().strip() or "0") for good, amount, is_percent in self.other if not is_percent])
            else:
                value = self.small[key].get().strip() or "None"
            out.append((self.name, key, value))
        return out

    def update(self):
        """Shows the live check: health bar, profit, input amounts, output and anything to do."""
        result = self.model.results.get(self.name)
        if result is None:
            self.bar.configure(background=FAINT)
            self.margin.configure(text="")
            self.profit.configure(text="")
            self.flag.configure(image="", text="")
            self.flag_hint.text = ""
            self.paint_border()
            self.show_flag_line("Not found in the game files." if self.model.game else "")
            return
        color = HEALTH_COLOR[result["health"]]
        self.bar.configure(background=color)
        self.paint_border()
        margin = result["margin"]
        self.margin.configure(text=("no price" if result["output"] > 0 else "") if margin is None else f"{margin * 100:+.0f}%",
                              foreground=color)
        self.profit.configure(text=f"{result['profit']:+.3f}".rstrip("0").rstrip("."),
                              foreground=GOOD if result["profit"] > 0 else BAD if result["profit"] < 0 else MUTED)
        flags, warning = result["flags"], self.icons.warning(16)
        if flags:
            self.flag.configure(image=warning or "", text="" if warning else "!")
        elif result["pending"]:
            self.flag.configure(image="", text="⟳", foreground=WARN)
        else:
            self.flag.configure(image="", text="")
        self.flag_hint.text = "\n".join(flags + [result["pending"]] if result["pending"] else flags)
        self.show_flag_line("\n".join(result["reasons"] + flags))
        if self.section is not None:
            inherited, values = self.inherited(), self.app.names.get("profit_values", {})
            for key in ("min_profit", "max_profit"):
                text = self.small[key].get() or inherited.get(key, ("", None))[0]
                self.equation.set_text("value " + key, profit_number(text, values))
            for good, label in getattr(self, "amount_labels", {}).items():
                amount = result["inputs"].get(good)
                label.configure(text=f"({number_text(amount)})" if amount is not None else "")
            self.provisions.configure(text=f"({number_text(result['output'])})")
            self.food_label.configure(text=f"({number_text(round(result['food_out'], 5))})")
            self.show_gold(result["inputs"], "provisions", result["output"])
            total = self.share_total()
            needs_total = self.fixed_side() == "output" and self.recipe and abs(total - 100) >= 0.05
            self.total_warning.configure(text=f"shares total {total:g}%, need 100%" if needs_total else "")

    def show_flag_line(self, text):
        if text:
            self.flag_line.configure(text=text)
            self.flag_line.pack(anchor="w", pady=(8, 0))
        else:
            self.flag_line.pack_forget()


SLOT_BG = "#1b1c1f"
OUT_BG = "#1f3a2c"


class OtherMethodCard(MethodCard):
    """A production method that does not make provisions, such as an RGO's main output. Its amounts are edited
    straight in the building file on Apply. Only a production method the mod defines once can be edited."""

    def __init__(self, document, parent, name):
        self.doc, self.name = document, name
        self.app, self.tool = document.app, document.tool
        self.icons, self.loc, self.model = self.tool.icons, self.tool.loc, self.tool.model
        self.info = self.model.game["others"][name]
        self.editable = len(self.model.game["places"].get(name, [])) == 1 or name in document.added
        self.changed, self.focused, self.hovered, self.health = False, False, False, "none"
        pending = document.block_edits.get(name) or self.info
        inputs, output, self.produced = pending["inputs"], pending["output"], pending["produced"]
        self.inputs = [[good, tk.StringVar(value=number_text(amount))] for good, amount in inputs.items()]
        self.output = tk.StringVar(value=number_text(output))
        self.output.trace_add("write", lambda *_: self.touch())
        self.frame = tk.Frame(parent, background=BG, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        self.bar = tk.Frame(self.frame, background=FAINT, width=4)
        self.bar.pack(side="left", fill="y")
        self.body = ttk.Frame(self.frame, padding=(14, 8, 14, 8))
        self.body.pack(side="left", fill="both", expand=True)
        self.frame.bind("<Enter>", lambda _: self.hover(True))
        self.frame.bind("<Leave>", self.leave)
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        self.doc.name_field(top, name, 34)
        note = ("" if self.editable else "read only, not defined once in the mod") if not self.info["shared"] else \
            f"shared by {self.info['users']} buildings" + ("" if self.editable else ", read only")
        if note:
            ttk.Label(top, text=note, style="Small.TLabel").pack(side="left", padx=(10, 0))
        if self.doc.removable(name):
            self.doc.remove_button(top, name)
        self.profit = icon_label(top, self.icons.gold(16), style="Muted.TLabel")
        self.profit.pack(side="right", padx=(10, 0))
        self.margin = ttk.Label(top, style="Margin.TLabel")
        self.margin.pack(side="right")
        self.equation = EquationCanvas(self.body, lambda inset=self.doc.card_inset: self.doc.canvas.winfo_width() - 84 - inset)
        self.equation.pack(fill="x", pady=(6, 0))
        self.build_equation()
        self.update()

    def build_equation(self):
        terms, goods = [], self.model.game["goods"]
        for index, row in enumerate(self.inputs):
            if index:
                terms.append({"kind": "operator", "text": "+", "joins_next": True})
            good, amount = row
            segments = self.good_segments(good)
            if self.editable:
                amount.trace_add("write", lambda *_: self.touch())
                segments += [("amount", amount, 6, {})] + self.gold_segments(good) + \
                    [("button", "✕", lambda row=row: self.remove_good(self.inputs, row))]
            else:
                segments += [("text", amount.get(), MUTED, None, "small")] + self.gold_segments(good)
            terms.append({"kind": "chip", "background": HOVER, "segments": segments})
        used = {good for good, _ in self.inputs}
        if self.editable:
            terms.append({"kind": "menu", "text": "+ input", "choices": self.goods_choices([good for good in goods if good not in used]),
                          "on_choose": lambda good: self.add_good(self.inputs, good)})
        produced = self.produced
        if produced or self.editable:
            terms.append({"kind": "operator", "text": "=", "joins_next": True})
        if produced:
            image = self.icons.good(produced, 18)
            name = self.loc.name(produced) or produced
            parts = [(name, ""), (number_text((getattr(self.model, "prices", None) or self.model.game["prices"]).get(produced, 0)), self.icons.gold(16) or " gold")]
            out = [("icon", image, parts)]
            if self.label_text(name, image):
                out.append(("text", self.label_text(name, image), GOOD, parts, "bold"))
            out.append(("amount", self.output, 6, {}) if self.editable else ("text", self.output.get(), MUTED, None, "small"))
            out += self.gold_segments("out")
            if self.editable:
                out.append(("button", "✕", lambda: self.set_produced(None)))
            terms.append({"kind": "chip", "background": OUT_BG, "padding": (6, 3, 8, 3), "segments": out})
        elif self.editable:
            terms.append({"kind": "menu", "text": "+ output", "width": 8, "choices": self.goods_choices(goods),
                          "on_choose": self.set_produced})
        self.equation.set_terms(terms)

    def set_produced(self, good):
        """Sets or clears the good this production method makes. A new output starts at 1."""
        if good == "provisions":
            self.doc.convert_to_provisions(self.name)
            return
        self.produced = good
        self.output.set("1" if good else "0")
        self.touch()
        self.build_equation()

    def add_good(self, rows, good):
        if good and not good.startswith("+"):
            rows.append([good, tk.StringVar(value="0.1")])
            self.touch()
            self.build_equation()

    def remove_good(self, rows, row):
        rows.remove(row)
        self.touch()
        self.build_equation()

    def touch(self):
        self.changed = True
        self.doc.block_edited()
        self.update()

    def values(self):
        """The amounts as typed. None when one is not a number."""
        try:
            inputs = {good: float(amount.get()) for good, amount in self.inputs}
            output = float(self.output.get())
        except ValueError:
            return None
        return {"inputs": inputs, "output": output, "produced": self.produced}

    def edits(self):
        return []

    def paint_border(self):
        color = HEALTH_COLOR[self.health] if self.health == "bad" else BORDER
        if self.hovered:
            color = lighten(color) if color != BORDER else MUTED
        self.frame.configure(highlightbackground=color, highlightcolor=color)

    def update(self):
        values, prices = self.values(), getattr(self.model, "prices", None) or self.model.game["prices"]
        if values is None:
            self.health = "none"
            self.margin.configure(text="not a number", foreground=WARN)
            self.profit.configure(text="")
        else:
            value_out = values["output"] * prices.get(self.produced, 0)
            cost = sum(prices.get(good, 0) * amount for good, amount in values["inputs"].items())
            margin = 1 - cost / value_out if value_out > 0 else None
            self.health = "none" if margin is None else "bad" if margin < 0 else "good"
            color = HEALTH_COLOR[self.health]
            self.margin.configure(text="" if not self.produced else "no price" if margin is None else f"{margin * 100:+.0f}%",
                                  foreground=color)
            profit = value_out - cost
            self.show_gold(values["inputs"], self.produced, values["output"])
            self.profit.configure(text=f"{profit:+.3f}".rstrip("0").rstrip("."),
                                  foreground=GOOD if profit > 0 else BAD if profit < 0 else MUTED)
        self.bar.configure(background=HEALTH_COLOR[self.health])
        self.paint_border()


def block_pairs(inside):
    """The key = value pairs inside a block on one line. A nested block stays whole as its pair's value."""
    pairs, index = [], 0
    while match := re.compile(r"\s*([\w.:]+\s*=\s*)").match(inside, index):
        index = match.end()
        if inside.startswith("{", index):
            depth, end = 0, index
            while end < len(inside):
                depth += {"{": 1, "}": -1}.get(inside[end], 0)
                end += 1
                if depth == 0:
                    break
        else:
            end = re.compile(r"[^\s{}]*").match(inside, index).end()
        pairs.append(match.group(1) + inside[index:end])
        index = end
    return pairs


def rewrite_amounts(block, inputs, output, goods, produced, newline):
    """The block with these input amounts, output good and output amount. Other lines and their notes stay."""
    lines = block.split("\n")
    if len(lines) < 3:
        # A block on one or two lines, such as "name = { }", is opened up over several lines first
        match = re.match(r"^([ \t]*)([^\n]*?\{)(.*)\}([^\n]*)$", block, re.DOTALL)
        if not match:
            raise ValueError("its block could not be read.")
        indent = match.group(1)
        pairs = block_pairs(match.group(3))
        cr = "\r" if newline == "\r\n" else ""
        lines = [f"{indent}{match.group(2)}{cr}"] + [f"{indent}\t{pair}{cr}" for pair in pairs] + [f"{indent}}}{match.group(4)}"]
    cr = "\r" if lines[0].endswith("\r") else ""
    body, written = [], set()
    for line in lines[1:-1]:
        match = re.match(r"^([ \t]*)(\w+)(\s*=\s*)([0-9.]+)(.*)$", line)
        if match and match.group(2) in goods:
            if match.group(2) in inputs:
                body.append(f"{match.group(1)}{match.group(2)}{match.group(3)}{number_text(inputs[match.group(2)])}{match.group(5)}")
                written.add(match.group(2))
            continue
        if match and match.group(2) == "output":
            if produced:
                body.append(f"{match.group(1)}output{match.group(3)}{number_text(output)}{match.group(5)}")
                written.add("output")
            continue
        made = re.match(r"^([ \t]*)produced(\s*=\s*)(\w+)(.*)$", line)
        if made:
            if produced:
                body.append(f"{made.group(1)}produced{made.group(2)}{produced}{made.group(4)}")
                written.add("produced")
            continue
        body.append(line)
    indent = re.match(r"^[ \t]*", lines[0]).group(0) + "\t"
    if produced and "produced" not in written:
        body.append(f"{indent}produced = {produced}{cr}")
    if produced and "output" not in written:
        anchor = next(index for index, line in enumerate(body) if re.match(r"^[ \t]*produced\s*=", line))
        body.insert(anchor + 1, f"{indent}output = {number_text(output)}{cr}")
    new = [good for good in inputs if good not in written]
    if new:
        anchor = next((index for index, line in enumerate(body) if re.match(r"^[ \t]*produced\s*=", line)), len(body))
        body[anchor:anchor] = [f"{indent}{good} = {number_text(inputs[good])}{cr}" for good in new]
    return "\n".join([lines[0]] + body + [lines[-1]])


class ApplyDocument(Document):
    """A window whose edits wait for Apply: Apply Dry Run and Apply at the top, the other actions in a bar above
    the page, and after a dry run a button that swaps the output between the summary and the code changes."""

    def build_apply_header(self):
        self.move_actions_up()
        self.save_button.configure(text="Apply", command=self.primary)
        self.dry_run_button = ttk.Button(self.header, text="Apply Dry Run", command=self.dry_run)
        self.dry_run_button.pack(side="right", padx=(0, 6), after=self.save_button)
        Hint(self.dry_run_button, "Preview code changes")
        self.action_buttons.append(self.dry_run_button)
        # The console bar holds only the swap button, so the bar shows only while the dry run's views are current
        self.code_changes = tk.BooleanVar(value=False)
        self.views = None
        self.view_strip = self.console_bar
        self.view_button = ttk.Button(self.console_bar, text="Show code changes", command=self.swap_view)
        self.view_button.pack(side="left")
        self.console_bar.pack_forget()

    def move_actions_up(self):
        """Sync From Files, Restore Backup Data and Clear go in a bar at the top of the page area."""
        form_area = self.canvas.master
        bar = ttk.Frame(form_area, padding=(28, 10, 22, 0))
        bar.pack(side="top", fill="x", before=form_area.pack_slaves()[0])
        for child in self.console_bar.winfo_children():
            child.destroy()
        self.action_buttons = []
        for label, arguments, confirm, hint, main in self.tool.actions:
            button = ttk.Button(bar, text=label, style="Accent.TButton" if main else "TButton",
                                command=lambda a=arguments, c=confirm: self.action(a, c))
            button.pack(side="left", padx=(0, 6))
            Hint(button, hint)
            self.action_buttons.append(button)
        self.busy = ttk.Label(bar, style="Faint.TLabel")
        self.busy.pack(side="left", padx=10)
        ttk.Button(bar, text="Clear", style="Ghost.TButton", command=self.close_console).pack(side="right")

    def swap_view(self):
        self.code_changes.set(not self.code_changes.get())
        self.show_view()

    def show_view(self):
        """Puts the last dry run's summary or code diff in the output."""
        if not self.views:
            return
        self.clear_output()
        self.view_button.configure(text="Show summary" if self.code_changes.get() else "Show code changes")
        if self.code_changes.get():
            self.write_many(self.views["code"])
        else:
            self.write("> dry run summary\n", ("2",))
            for line in self.views["summary"]:
                self.write_colored(line)
        self.output.see("1.0")

    def run(self, arguments, then=None):
        if not arguments or arguments[0] not in ("--settings", "--dry-run"):
            self.views = None  # Another run makes the dry run's views old
            self.view_strip.pack_forget()
        super().run(arguments, then)

    def close_console(self):
        self.views = None
        self.view_strip.pack_forget()
        super().close_console()


class BuildingDocument(ApplyDocument):
    """Building setup: the settings form. Apply runs the generator on the settings as they are in the window,
    and the generator writes them with the setup files, after a backup."""

    close_question = "Apply your changes before closing?"
    OPTIONS = {"rgo": "--rgo-settings", "other": "--building-settings"}

    def __init__(self, app, tool):
        super().__init__(app, tool)
        self.build_apply_header()
        self.update_status()

    # -------------------------------------------------------------- sidebar
    # A drawn list, as in the provisions window. Hover changes only the colors of two rows, so it stays fast.

    PANEL, ROW, INDENT = 36, 30, 18

    def build_sidebar(self, parent):
        self.expanded, self.side_rows, self.hover_row = {}, [], None
        self.side = ttk.Frame(parent, style="Side.TFrame")
        self.side.grid(row=0, column=0, sticky="nsew")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(self.side, textvariable=self.search)
        self.search_entry.pack(fill="x", padx=14, pady=(0, 8))
        placeholder(self.search_entry, self.search, "Search   (Ctrl+F, then Enter)")
        self.search.trace_add("write", lambda *_: self.draw_list())
        self.search_entry.bind("<Return>", lambda _: self.open_first_match())
        self.search_entry.bind("<Down>", lambda _: self.enter_tree())
        holder = ttk.Frame(self.side, style="Side.TFrame")
        holder.pack(fill="both", expand=True, padx=(6, 0))
        self.list = tk.Canvas(holder, background=SIDEBAR, highlightthickness=0, borderwidth=0, takefocus=1)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.list.pack(side="left", fill="both", expand=True)
        self.tip = CanvasTip(self.list)
        self.list.bind("<Configure>", lambda _: self.draw_list())
        self.list.bind("<Motion>", self.list_motion)
        self.list.bind("<Leave>", lambda _: (self.set_hover(None), self.tip.hide()))
        self.list.bind("<Button-1>", self.list_click)
        self.list.bind("<Up>", lambda _: self.step_section(-1))
        self.list.bind("<Down>", lambda _: self.step_section(1))
        ttk.Button(self.side, text="+   New section", style="Side.TButton", command=self.new_section).pack(fill="x", padx=14, pady=12)

    def wheel_canvases(self):
        return [self.canvas, self.list]

    def is_open(self, key, searching):
        return searching or self.expanded.get(key, True)

    def draw_list(self):
        canvas = self.list
        canvas.delete("all")
        self.side_rows, self.hover_row = [], None
        width = max(canvas.winfo_width(), 200)
        words = self.search.get().lower().split()

        def matches(name):
            text = (name + " " + self.side_label(name)[0]).lower()
            return all(word in text for word in words)

        y = 4
        for index, (file_label, settings_file) in enumerate(self.files):
            rows = []  # (kind, name, indent)
            for label, head, members in self.tool.groups(settings_file):
                if label is None:
                    rows += [("section", name, 0) for name in self.side_order(members) if matches(name)]
                    continue
                shown = members if matches(label) else [name for name in members if matches(name)]
                if not shown and not matches(label):
                    continue
                rows.append(("group" if shown else "section", head or label, 0))
                if self.is_open((index, head or label), bool(words)):
                    rows += [("member", name, 1) for name in self.side_order(shown)]
            if words and not rows:
                continue
            open_ = self.is_open(("file", index), bool(words))
            y = self.draw_panel(index, file_label, settings_file, open_, y, width)
            if not open_:
                continue
            guide_top = None
            for kind, name, indent in rows:
                if kind == "member" and guide_top is None:
                    guide_top = y - 2
                if kind != "member" and guide_top is not None:
                    canvas.create_line(14, guide_top, 14, y - self.ROW / 2 - 4, fill=BORDER, width=2)
                    guide_top = None
                y = self.draw_section(index, settings_file, kind, name, indent, y, width, bool(words))
            if guide_top is not None:
                canvas.create_line(14, guide_top, 14, y - self.ROW / 2 - 2, fill=BORDER, width=2)
            y += 8
        canvas.configure(scrollregion=(0, 0, width, max(y + 8, canvas.winfo_height())))

    def draw_panel(self, index, file_label, settings_file, open_, y, width):
        """A file's header: a solid panel that opens and closes its building types."""
        canvas, x0, x1 = self.list, 4, width - 6
        background = canvas.create_rectangle(x0, y, x1, y + self.PANEL, fill=FIELD, outline="")
        chevron = canvas.create_text(x0 + 12, y + self.PANEL / 2, text="▾" if open_ else "▸", anchor="w", fill=MUTED)
        canvas.create_text(x0 + 28, y + self.PANEL / 2, text=file_label, anchor="w", fill="#ffffff", font=self.app.header_font)
        total = self.tool.file_count(settings_file)
        if total:
            canvas.create_text(x1 - 10, y + self.PANEL / 2, text=total, anchor="e", fill=FAINT, font=self.app.small)
        self.side_rows.append({"top": y, "bottom": y + self.PANEL, "kind": "file", "index": index, "open": open_,
                               "background": background, "base": FIELD, "texts": [(chevron, MUTED)]})
        return y + self.PANEL + 6

    def draw_section(self, index, settings_file, kind, name, indent, y, width, searching):
        """One row that opens a section. A group row also opens and closes its members."""
        canvas = self.list
        x0, x1 = 4 + indent * self.INDENT, width - 6
        selected = settings_file is self.file and name == self.section_name
        base = SELECTED if selected else SIDEBAR
        background = canvas.create_rectangle(x0, y, x1, y + self.ROW, fill=base, outline="")
        if selected:
            canvas.create_rectangle(x0, y, x0 + 3, y + self.ROW, fill=ACCENT, outline="")
        middle, x, texts = y + self.ROW / 2, x0 + 12, []
        if indent:
            canvas.create_line(14, middle, x0, middle, fill=BORDER, width=2)
        if kind == "group":
            open_ = self.is_open((index, name), searching)
            chevron = canvas.create_text(x, middle, text="▾" if open_ else "▸", anchor="w", fill=MUTED)
            texts.append((chevron, MUTED))
            x += 16
        text, image = self.side_label(name)
        if image:
            canvas.create_image(x, middle, image=image, anchor="w")
            x += 22
        default = name.lower() in DEFAULT_SECTIONS or name in self.tool.group_members(settings_file)
        color = "#ffffff" if selected else TEXT if default else MUTED
        label = canvas.create_text(x, middle, text=text, anchor="w", fill=color, font=self.app.bold if default else None)
        texts.append((label, color))
        count = self.side_count(settings_file, name)[0]
        room = x1 - 10 - x - (self.app.small.measure(count) + 10 if count else 0)
        self.clip_text(label, room)
        if count:
            counted = canvas.create_text(x1 - 10, middle, text=count, anchor="e", fill=FAINT, font=self.app.small)
            texts.append((counted, FAINT))
        self.side_rows.append({"top": y, "bottom": y + self.ROW, "kind": kind, "index": index, "name": name,
                               "file": settings_file, "background": background, "base": base, "texts": texts,
                               "open": kind == "group" and self.is_open((index, name), searching)})
        return y + self.ROW + 2

    def clip_text(self, item, room):
        """Cuts a canvas text to the room it has, with ... at the end."""
        canvas = self.list
        text = canvas.itemcget(item, "text")
        while text and canvas.bbox(item) and canvas.bbox(item)[2] - canvas.bbox(item)[0] > room:
            text = text[:-1]
            canvas.itemconfigure(item, text=text + "…")

    def row_at(self, event):
        y = self.list.canvasy(event.y)
        return next((row for row in self.side_rows if row["top"] <= y < row["bottom"]), None)

    def set_hover(self, row):
        if row is self.hover_row:
            return
        for old, hovered in ((self.hover_row, False), (row, True)):
            if old is None:
                continue
            fill = HOVER if hovered and old["base"] != SELECTED else old["base"]
            self.list.itemconfigure(old["background"], fill=fill)
            for item, color in old["texts"]:
                self.list.itemconfigure(item, fill="#ffffff" if hovered and color in (TEXT, MUTED) else color)
        self.hover_row = row
        self.list.configure(cursor="hand2" if row else "")

    def list_motion(self, event):
        row = self.row_at(event)
        self.set_hover(row)
        tip = ""
        if row and row["kind"] != "file" and row["name"].lower() not in DEFAULT_SECTIONS:
            count = self.side_count(row["file"], row["name"])[0]
            tip = row["name"] + (f"\n{count} in the setup files" if count else "")
        self.tip.show_later(tip, event.x_root, event.y_root)

    def list_click(self, event):
        row = self.row_at(event)
        self.tip.hide()
        self.list.focus_set()
        if not row:
            return
        if row["kind"] == "file":
            self.expanded[("file", row["index"])] = not row["open"]
            self.draw_list()
            return
        if row["kind"] == "group" and event.x < 30:
            self.expanded[(row["index"], row["name"])] = not row["open"]
            self.draw_list()
            return
        if row["kind"] == "group":
            self.expanded[(row["index"], row["name"])] = True
        self.open_section(row["file"], row["name"])

    def open_section(self, settings_file, name):
        if settings_file is not self.file or name != self.section_name:
            self.commit()
            self.show_section(settings_file, name)
        self.draw_list()
        self.see_selected()

    def section_rows(self):
        return [row for row in self.side_rows if row["kind"] != "file"]

    def step_section(self, step):
        rows = self.section_rows()
        at = next((place for place, row in enumerate(rows) if row["file"] is self.file and row["name"] == self.section_name), -1)
        if rows and 0 <= at + step < len(rows):
            self.open_section(rows[at + step]["file"], rows[at + step]["name"])
        return "break"

    def see_selected(self):
        row = next((row for row in self.section_rows() if row["file"] is self.file and row["name"] == self.section_name), None)
        region = self.list.cget("scrollregion").split()
        if not row or len(region) < 4 or float(region[3]) <= 0 or self.list.winfo_height() <= 1:
            return
        total, top = float(region[3]), self.list.canvasy(0)
        bottom = top + self.list.winfo_height()
        if row["top"] < top or row["bottom"] > bottom:
            self.list.yview_moveto(max(0, row["top"] - self.list.winfo_height() / 3) / total)

    def fill_sections(self):
        if self.section_name not in self.file.names():
            self.section_name = None
        if self.section_name is None:
            first = next(((settings_file, settings_file.names()[0]) for _, settings_file in self.files if settings_file.names()), None)
            if first:
                self.show_section(*first)
        self.draw_list()
        self.update_status()

    def mark_selected(self):
        if hasattr(self, "list"):
            self.draw_list()
            self.see_selected()

    def open_first_match(self):
        rows = self.section_rows()
        if rows:
            self.open_section(rows[0]["file"], rows[0]["name"])

    def enter_tree(self):
        self.list.focus_set()
        if not any(row["file"] is self.file and row["name"] == self.section_name for row in self.section_rows()):
            self.open_first_match()

    # -------------------------------------------------------------- running

    def settings_arguments(self):
        """Copies of the settings files as they are in the window, for the generator to read."""
        self.commit()
        arguments = []
        for _, settings_file in self.files:
            path = Path(tempfile.gettempdir()) / f"mnt_building_setup_{settings_file.kind}_settings.txt"
            path.write_bytes(settings_file.content())
            arguments += [self.OPTIONS[settings_file.kind], str(path)]
        self.refresh()  # commit let go of the editors, so the page gets new ones
        return arguments

    def primary(self):
        self.run(self.settings_arguments(), self.after_apply)

    def after_apply(self, output, code):
        if code == 0:
            for _, settings_file in self.files:
                settings_file.load()
            self.refresh()

    def finish_before_close(self):
        return self.run_before_close(self.settings_arguments())

    def dry_run(self):
        """The generator's summary of what would change, and the code diff of each file it would write."""
        arguments = self.settings_arguments()
        folder = Path(tempfile.mkdtemp(prefix="mnt_building_setup_dry_run_"))
        self.views = None
        self.view_strip.pack_forget()

        def done(output, code):
            try:
                if code == 0:
                    self.views = {"summary": list(self.last_run_lines), "code": self.code_changes_view(folder)}
                    self.view_strip.pack(fill="x", before=self.output.master)
                    self.show_view()
            finally:
                shutil.rmtree(folder, ignore_errors=True)
        self.run(["--dry-run", str(folder)] + arguments, done)

    def code_changes_view(self, folder):
        """[(text, tags)]: a diff of each file in folder against the same file in the mod. Lines in a row with the
        same color join into one piece, so a large diff writes fast."""
        view = [("> code changes Apply would write\n", ("2",))]
        files = sorted(path for path in folder.rglob("*") if path.is_file())
        for path in files:
            relative = path.relative_to(folder)
            real = MOD_ROOT / relative
            before = real.read_bytes().decode("utf-8-sig").replace("\r\n", "\n") if real.is_file() else ""
            after = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
            view.append((f"\n{relative.as_posix()}\n", ("1;34",)))
            for line in diff_lines(before.split("\n"), after.split("\n")):
                tag = "32" if line.startswith("+") else "91" if line.startswith("-") else "2" if line.startswith("@@") else ""
                tags = (tag,) if tag else ()
                if view[-1][1] == tags and not view[-1][0].startswith("\n"):
                    view[-1] = (view[-1][0] + line + "\n", tags)
                else:
                    view.append((line + "\n", tags))
        view.append(("\nNo file changes.\n" if not files else
                     f"\n{len(files)} file{'s' if len(files) != 1 else ''} change. Nothing was written.\n", ("2",)))
        return view

    def update_status(self):
        dirty = self.dirty
        self.status.configure(text="Not applied" if dirty else "", foreground=WARN)
        self.undo_button.state(["!disabled"] if dirty else ["disabled"])
        self.save_button.state(["!disabled"])

    def revert(self):
        if self.dirty and not messagebox.askyesno("Undo changes", "Undo the changes you have not applied?"):
            return
        for _, settings_file in self.files:
            settings_file.load()
        self.refresh()


class ProvisionsDocument(ApplyDocument):
    """Provisions: a sidebar that shows each method's health, and one page per building with a card per method."""

    BUILDING_ROW, METHOD_ROW = 38, 46
    METHOD_INDENT = 22  # Methods sit under their building, joined to it by a guide line

    def __init__(self, app, tool):
        self.page, self.focus, self.cards, self.header_edits = "general", None, [], {}
        self.expanded, self.hovered, self.check_after, self.list_items = {}, None, None, []
        self.block_edits, self.other_cards, self.card_inset = {}, [], 0
        # Production methods and slots that Apply adds or removes. Nothing is written before Apply.
        self.added, self.removed, self.reload_names = {}, set(), False
        self.backup_folder = None
        # Production methods whose key Apply renames: {old key: new key}
        self.renamed = {}
        # Game values changed here: "price", "food", "subsistence", ("add_good", good) or ("remove_good", good).
        # The Pop Demands numbers live in the settings.
        self.value_edits = {}
        self.show_others = tk.BooleanVar(value=False)
        self.show_names = tk.BooleanVar(value=True)
        super().__init__(app, tool)
        self.build_apply_header()
        self.reload_after_run()  # The first read of the game files, in the background

    # -------------------------------------------------------------- sidebar

    def build_sidebar(self, parent):
        self.side = ttk.Frame(parent, style="Side.TFrame")
        self.side.grid(row=0, column=0, sticky="nsew")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(self.side, textvariable=self.search)
        self.search_entry.pack(fill="x", padx=14, pady=(0, 6))
        placeholder(self.search_entry, self.search, "Search   (Ctrl+F, then Enter)")
        self.search.trace_add("write", lambda *_: self.draw_list())
        self.search_entry.bind("<Return>", lambda _: self.open_first_match())
        counts = ttk.Frame(self.side, style="Side.TFrame")
        counts.pack(fill="x", padx=18, pady=(0, 6))
        self.count_labels = {}
        for health, tip in (("bad", "Methods that lose money."), ("warn", "Methods outside their min or max profit."),
                            ("good", "Methods with a healthy profit.")):
            label = tk.Label(counts, background=SIDEBAR, foreground=HEALTH_COLOR[health], font=self.app.bold)
            label.pack(side="left", padx=(0, 10))
            Hint(label, tip)
            self.count_labels[health] = label
        self.apply_link = tk.Label(counts, background=SIDEBAR, foreground=WARN, cursor="hand2", font=self.app.bold)
        self.apply_link.bind("<Button-1>", lambda _: self.primary())
        self.apply_link.bind("<Enter>", lambda _: self.apply_link.configure(foreground="#ffd27a"))
        self.apply_link.bind("<Leave>", lambda _: self.apply_link.configure(foreground=WARN))
        self.import_link = tk.Label(counts, background=SIDEBAR, foreground=MUTED, cursor="hand2")
        self.import_link.bind("<Button-1>", lambda _: self.action(["--import"], None))
        holder = ttk.Frame(self.side, style="Side.TFrame")
        holder.pack(fill="both", expand=True, padx=(6, 0))
        self.list = tk.Canvas(holder, background=SIDEBAR, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.list.pack(side="left", fill="both", expand=True)
        self.tip = CanvasTip(self.list)
        self.list.bind("<Configure>", lambda _: self.draw_list())
        self.list.bind("<Motion>", self.list_motion)
        self.list.bind("<Leave>", lambda _: (self.set_hover(None), self.tip.hide()))
        self.list.bind("<Button-1>", self.list_click)
        ttk.Button(self.side, text="+   Add production method", style="Side.TButton",
                   command=self.choose_building_for_method).pack(fill="x", padx=14, pady=12)

    def owner_of(self, name):
        owners = self.app.names.get("owners_of", {}).get(name)
        if owners is None:
            result = self.tool.model.results.get(name)
            owners = result["owners"] if result else None
        if owners is None:
            return "Other sections"
        return owners[0] if owners else "Shared methods"

    def buildings(self):
        """[(building, [methods])] in the settings file's order, then methods the settings do not have yet."""
        order, members = [], {}
        names = self.file.names()
        is_building = set(self.app.names.get("method_owners", [])) - set(self.app.names.get("methods", []))
        for name in names + sorted(self.tool.model.results):
            if name.lower() in ("general", POP_PAGE):
                continue
            building = name if name in is_building else self.owner_of(name)
            if building not in members:
                order.append(building)
                members[building] = []
            if name not in is_building and name not in members[building]:
                members[building].append(name)
        return [(building, members[building]) for building in order]

    def health_of(self, name):
        result = self.tool.model.results.get(name)
        return result["health"] if result else "none"

    def needs_work(self, methods):
        results = [self.tool.model.results.get(name) for name in methods]
        return any(result is None or result["health"] in ("bad", "warn") or result["flags"] for result in results)

    def draw_list(self):
        canvas, icons, loc = self.list, self.tool.icons, self.tool.loc
        canvas.delete("all")
        width = max(canvas.winfo_width(), 200)
        words = self.search.get().lower().split()

        def matches(name):
            text = f"{name} {loc.name(name) or ''}".lower()
            return all(word in text for word in words)

        y, self.list_items = 4, []
        if not words or matches("general"):
            self.draw_row(("general", "general"), y, self.BUILDING_ROW, width)
            y += self.BUILDING_ROW + 4
        if not words or matches(POP_PAGE):
            self.draw_row(("demand", POP_PAGE), y, self.BUILDING_ROW, width)
            y += self.BUILDING_ROW + 10
        for building, methods in self.buildings():
            shown = methods if not words or matches(building) else [name for name in methods if matches(name)]
            shown = [name for name in shown if name not in self.removed]
            if words and not shown and not matches(building):
                continue
            open_ = bool(words) or self.expanded.get(building, self.needs_work(methods) or building == self.page)
            self.draw_row(("building", building, methods, open_), y, self.BUILDING_ROW, width)
            y += self.BUILDING_ROW + 4
            if open_ and shown:
                line_top, guide = y - 4, 14
                # With two provisions slots or more, each slot's methods get a caption
                slot_of = self.tool.model.game.get("slot_of", {}) if self.tool.model.game else {}
                numbers = {slot_of.get(name, (None, 0))[1] for name in shown}
                # The building file's order: by slot, then by place in the slot
                slots = self.tool.model.game.get("slots", {}).get(building, []) if self.tool.model.game else []
                place = {name: (number, index) for number, slot in enumerate(slots, 1) for index, name in enumerate(slot["methods"])}
                shown = sorted(shown, key=lambda name: place.get(name, (len(slots) + 1, 0)))
                last = None
                for name in shown:
                    number = slot_of.get(name, (None, 0))[1]
                    if len(numbers) > 1 and number != last:
                        slot_name = self.tool.loc.name(f"{building}_slot_{number - 1}")
                        canvas.create_text(self.METHOD_INDENT + 4, y + 7, text=(slot_name or f"slot {number}").upper(),
                                           anchor="w", fill=MUTED, font=self.app.caption)
                        y += 18
                        last = number
                    self.draw_row(("method", name, building), y, self.METHOD_ROW, width)
                    middle = y + self.METHOD_ROW / 2
                    canvas.create_line(guide, middle, self.METHOD_INDENT, middle, fill=BORDER, width=2)
                    y += self.METHOD_ROW + 4
                canvas.create_line(guide, line_top, guide, middle + 1, fill=BORDER, width=2)
            y += 8
        canvas.configure(scrollregion=(0, 0, width, max(y + 8, canvas.winfo_height())))
        self.update_counts()

    def draw_row(self, item, y, height, width):
        canvas, icons, loc = self.list, self.tool.icons, self.tool.loc
        kind, key = item[0], item[1]
        self.list_items.append((y, y + height, item))
        hovered = self.hovered == (kind, key)
        selected = (kind in ("general", "demand") and self.page == key) or (kind == "building" and self.page == key and not self.focus) \
            or (kind == "method" and self.focus == key)
        x0, x1 = (self.METHOD_INDENT if kind == "method" else 4), width - 6
        if kind == "method":
            health = self.health_of(key)
            image = icons.glow(x1 - x0, height, HEALTH_COLOR[health], 190 if hovered else 120)
            if image:
                canvas.create_image(x0, y, image=image, anchor="nw")
            else:
                canvas.create_rectangle(x0, y, x1, y + height, outline=HEALTH_COLOR[health], fill=SIDEBAR)
            if selected:
                canvas.create_rectangle(x0, y, x1 - 1, y + height - 1, outline=ACCENT, width=2)
            result = self.tool.model.results.get(key)
            name = loc.name(key) or key
            right = x1 - 10
            if result:
                margin = result["margin"]
                canvas.create_text(right, y + 13, text="-" if margin is None else f"{margin * 100:+.0f}%", anchor="e",
                                   fill=HEALTH_COLOR[result["health"]], font=self.app.bold)
            name_id = canvas.create_text(x0 + 12, y + 13, text=name, anchor="w", fill="#ffffff" if hovered or selected else TEXT)
            self.clip_text(name_id, right - 46 - (x0 + 12))
            if result:
                x = x0 + 12
                for good in result["inputs"]:
                    image = icons.good(good, 16)
                    if image:
                        canvas.create_image(x, y + 32, image=image, anchor="w")
                        x += 18
                    else:
                        x = canvas.bbox(canvas.create_text(x, y + 32, text=good, anchor="w", fill=MUTED, font=self.app.small))[2] + 4
                x = canvas.bbox(canvas.create_text(x + 4, y + 32, text=f"→ {number_text(result['food_out'])}", anchor="w",
                                                   fill=TEXT, font=self.app.small))[2] + 2
                food = icons.food(14)
                if food:
                    canvas.create_image(x, y + 32, image=food, anchor="w")
                    x += 16
                profit = result["profit"]
                x = canvas.bbox(canvas.create_text(x + 8, y + 32, text=f"{profit:+.2f}", anchor="w", font=self.app.small,
                                                   fill=GOOD if profit > 0 else BAD if profit < 0 else MUTED))[2] + 2
                gold = icons.gold(14)
                if gold:
                    canvas.create_image(x, y + 32, image=gold, anchor="w")
                if result["flags"]:
                    warning = icons.warning(16)
                    if warning:
                        canvas.create_image(right, y + 32, image=warning, anchor="e")
                    else:
                        canvas.create_text(right, y + 32, text="!", anchor="e", fill=WARN, font=self.app.bold)
                elif result["pending"]:
                    canvas.create_text(right, y + 32, text="⟳", anchor="e", fill=WARN)
            return
        # Buildings and General settings are solid panels, so they read as headers over their methods
        canvas.create_rectangle(x0, y, x1, y + height, fill=SELECTED if selected else HOVER if hovered else FIELD,
                                outline=ACCENT if selected else "")
        if kind in ("general", "demand"):
            canvas.create_text(x0 + 14, y + height / 2, text="General settings" if kind == "general" else "Pop Demands",
                               anchor="w", fill="#ffffff", font=self.app.header_font)
            return
        methods, open_ = item[2], item[3]
        worst = max((self.health_of(name) for name in methods), key=HEALTH_ORDER.get, default="none")
        canvas.create_rectangle(x0, y, x0 + 4, y + height, fill=HEALTH_COLOR[worst], outline="")
        canvas.create_text(x0 + 12, y + height / 2, text="▾" if open_ else "▸", anchor="w", fill=TEXT if hovered else MUTED)
        x = x0 + 26
        image = icons.building(key, 26)
        if image:
            canvas.create_image(x, y + height / 2, image=image, anchor="w")
            x += 32
        name_id = canvas.create_text(x, y + height / 2, text=loc.name(key) or key, anchor="w", fill="#ffffff", font=self.app.header_font)
        self.clip_text(name_id, x1 - 52 - x)
        canvas.create_text(x1 - 26, y + height / 2, text=str(len(methods)), anchor="e", fill=FAINT, font=self.app.small)
        flagged = any(self.tool.model.results.get(name, {}).get("flags") for name in methods)
        if flagged and icons.warning(14):
            canvas.create_image(x1 - 40, y + height / 2, image=icons.warning(14), anchor="e")
        if worst == "good" and not flagged:
            canvas.create_text(x1 - 8, y + height / 2, text="✓", anchor="e", fill=GOOD, font=self.app.bold)
        elif worst in ("bad", "warn"):
            canvas.create_text(x1 - 8, y + height / 2, text="●", anchor="e", fill=HEALTH_COLOR[worst])

    def clip_text(self, item, room):
        """Cuts a canvas text to the room it has, with ... at the end."""
        canvas = self.list
        text = canvas.itemcget(item, "text")
        while text and canvas.bbox(item) and canvas.bbox(item)[2] - canvas.bbox(item)[0] > room:
            text = text[:-1]
            canvas.itemconfigure(item, text=text + "…")

    def update_counts(self):
        results = self.tool.model.results.values()
        for health, label in self.count_labels.items():
            count = sum(1 for result in results if result["health"] == health)
            label.configure(text=f"● {count}" if count else "")
        pending = sum(1 for result in results if result["pending"])
        outside = sum(1 for result in results if not result["in_settings"])
        if pending:
            self.apply_link.configure(text=f"{pending} to apply ›")
            self.apply_link.pack(side="left", padx=(4, 10))
        else:
            self.apply_link.pack_forget()
        if outside:
            self.import_link.configure(text=f"{outside} to sync ›")
            self.import_link.pack(side="left")
        else:
            self.import_link.pack_forget()
        self.update_status()

    def item_at(self, event):
        y = self.list.canvasy(event.y)
        return next((item for top, bottom, item in self.list_items if top <= y < bottom), None)

    def set_hover(self, key):
        if key != self.hovered:
            self.hovered = key
            self.draw_list()

    def list_motion(self, event):
        item = self.item_at(event)
        self.set_hover((item[0], item[1]) if item else None)
        text = ""
        if item and item[0] == "method":
            result = self.tool.model.results.get(item[1])
            lines = result["flags"] + [result["pending"]] if result else ["Not found in the game files."]
            lines = [line for line in lines if line]
            text = "\n".join(lines)
        self.tip.show_later(text, event.x_root, event.y_root)

    def list_click(self, event):
        item = self.item_at(event)
        self.tip.hide()
        if not item:
            return
        if item[0] == "building" and event.x < 30:
            self.expanded[item[1]] = not item[3]
            self.draw_list()
            return
        if item[0] in ("general", "demand"):
            self.open_page(item[1])
        elif item[0] == "building":
            self.expanded[item[1]] = True
            self.open_page(item[1])
        else:
            self.open_page(item[2], focus=item[1])

    def open_first_match(self):
        method = next((item for _, _, item in self.list_items if item[0] == "method"), None)
        building = next((item for _, _, item in self.list_items if item[0] == "building"), None)
        if method:
            self.open_page(method[2], focus=method[1])
        elif building:
            self.open_page(building[1])

    def wheel_canvases(self):
        return [self.canvas, self.list]

    # -------------------------------------------------------------- pages

    def fill_sections(self):
        self.render_page()
        self.draw_list()
        self.update_status()

    def mark_selected(self):
        pass

    def open_page(self, page, focus=None):
        if not self.keep_block_edits():
            return
        self.commit()
        self.page, self.focus = page, focus
        self.render_page()
        self.draw_list()

    def page_of(self, name):
        if name == POP_PAGE:
            return name
        if name.lower() == "general":
            return "general"
        if name in self.app.names.get("methods", []) or name in self.tool.model.results:
            return self.owner_of(name)
        return name

    def refresh(self, settings_file=None, name=None):
        if name is not None:
            self.page, self.focus = self.page_of(name), (name if self.page_of(name) != name else None)
        self.fill_sections()
        self.schedule_check()

    def render_page(self):
        self.editors, self.cards, self.header_edits = [], [], {}
        if self.page == POP_PAGE:
            self.show_demand_page()
            return
        if self.page == "general" or self.file.section(self.page) and self.page not in dict(self.buildings()):
            self.form.columnconfigure(0, weight=0, minsize=270)
            self.form.columnconfigure(1, weight=1)
            self.show_section(self.file, "general" if self.page == "general" else self.page)
            return
        self.section_name = None
        # The page is built in a frame that is not on screen yet, then swapped in whole, so it does not draw in stages
        shown = self.form
        self.form = self.new_form()
        self.form.columnconfigure(0, weight=1, minsize=0)
        self.form.columnconfigure(1, weight=0)
        self.path_label.configure(text=self.file.path.name)
        methods = dict(self.buildings()).get(self.page, [])
        self.build_header(self.page)
        self.other_cards = []
        slots = self.tool.model.game.get("slots", {}).get(self.page) if self.tool.model.game else None
        row, placed = 1, set()
        options = ttk.Frame(self.form)
        options.grid(row=row, column=0, sticky="w", pady=(0, 12))
        row += 1
        if slots:
            box = ttk.Checkbutton(options, text="Show the other production methods", variable=self.show_others,
                                  command=lambda: self.open_page(self.page, self.focus))
            box.pack(side="left", padx=(0, 24))
        names = ttk.Checkbutton(options, text="Show goods names", variable=self.show_names,
                                command=lambda: self.open_page(self.page, self.focus))
        names.pack(side="left")
        for number, slot in enumerate(slots or [], 1):
            provisions = [name for name in slot["methods"] if name in self.tool.model.game["methods"]]
            placed.update(slot["methods"])
            if provisions or slot.get("new") or self.show_others.get():
                self.build_slot(number, slot, provisions).grid(row=row, column=0, sticky="ew", pady=(0, 14))
                row += 1
        if slots:
            add_slot = self.link(self.form, "+   Add production method slot", lambda: self.add_slot(self.page), BG)
            add_slot.grid(row=row, column=0, sticky="w", pady=(0, 10))
            Hint(add_slot, "Adds another production line")
            row += 1
        self.card_inset = 0
        rest = [name for name in methods if name not in placed]
        for name in rest:
            self.method_card(self.form, name).frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            row += 1
        focus_card = next((card for card in self.cards if card.name == self.focus), None)
        if focus_card:
            focus_card.focused = True
            focus_card.paint_border()
        # Lay the whole page out before it shows, so cards do not grow and then shrink
        self.form.update_idletasks()
        for card in self.cards + self.other_cards:
            card.equation.relayout()
        self.form.update_idletasks()
        self.canvas.itemconfigure(self.form_window, window=self.form)
        shown.destroy()
        self.canvas.yview_moveto(0)
        self.form.update_idletasks()
        self.update_scrollregion()
        if focus_card:
            self.scroll_to(focus_card)

    SLOT_INSET = 26  # The slot box's padding and border, which the cards inside it lose

    def method_card(self, parent, name):
        card = MethodCard(self, parent, name)
        self.cards.append(card)
        return card

    def build_slot(self, number, slot, provisions):
        """One slot: a box with the production methods that take turns in it."""
        game, loc, icons = self.tool.model.game, self.tool.loc, self.tool.icons
        box = tk.Frame(self.form, background=SLOT_BG, highlightthickness=1, highlightbackground=BORDER, padx=12, pady=10)
        produced = [game["others"][name]["produced"] for name in slot["methods"] if name in game["others"]
                    and game["others"][name]["produced"]]
        good = "provisions" if provisions else (produced[0] if produced else None)
        caption = tk.Frame(box, background=SLOT_BG)
        caption.pack(fill="x", pady=(0, 8))
        image = icons.good(good, 18) if good else None
        if image:
            tk.Label(caption, image=image, background=SLOT_BG).pack(side="left", padx=(0, 6))
        key = f"{self.page}_slot_{number - 1}"
        title = tk.StringVar(value=loc.name(key) or "")
        if loc.editable(key) or loc.addable(key):
            entry = ttk.Entry(caption, textvariable=title, width=22, style="SlotName.TEntry", font=self.app.bold)
            entry.pack(side="left")
            placeholder(entry, title, "Name this slot")
            title.trace_add("write", lambda *_: (loc.set(key, title.get().strip()) if title.get().strip() or loc.editable(key)
                                                 else loc.pending.pop(key, None), self.loc_edited()))
        else:
            tk.Label(caption, text=title.get(), background=SLOT_BG, foreground=TEXT, font=self.app.bold).pack(side="left")
        tk.Label(caption, text=f"slot {number}" + ("  ·  shared production methods" if slot["shared"] else ""),
                 background=SLOT_BG, foreground=FAINT, font=self.app.small).pack(side="left", padx=(12, 0))
        self.card_inset = self.SLOT_INSET
        for name in slot["methods"]:
            info = game["others"].get(name)
            if name in self.removed:
                self.removed_line(box, name).pack(fill="x", pady=(0, 8))
                continue
            if name in game["methods"]:
                card = self.method_card(box, name)
            elif info:
                # An empty production method lets the building make nothing in this slot. It always shows.
                if not self.show_others.get() and (info["produced"] or info["inputs"]):
                    continue
                card = OtherMethodCard(self, box, name)
                self.other_cards.append(card)
            else:
                continue
            card.frame.pack(fill="x", pady=(0, 8))
        if not slot["shared"]:
            add = self.link(box, "+   Add production method", lambda: self.add_method(self.page, number), SLOT_BG)
            add.pack(anchor="w", pady=(2, 0))
            Hint(add, "Create a blank production method in this slot")
        return box

    def link(self, parent, text, command, background):
        link = tk.Label(parent, text=text, background=background, foreground=ACCENT, cursor="hand2")
        link.bind("<Button-1>", lambda _: command())
        link.bind("<Enter>", lambda _: link.configure(foreground=ACCENT_HOVER))
        link.bind("<Leave>", lambda _: link.configure(foreground=ACCENT))
        return link

    def name_field(self, parent, key, width):
        """The production method's name in the game. A name no file defines yet is added on Apply."""
        loc = self.tool.loc
        title = tk.StringVar(value=loc.name(key) or "")
        if loc.editable(key) or loc.addable(key):
            entry = ttk.Entry(parent, textvariable=title, width=width, style="Name.TEntry", font=self.app.bold)
            entry.pack(side="left")
            placeholder(entry, title, "Name this production method")
            title.trace_add("write", lambda *_: (loc.set(key, title.get().strip()) if title.get().strip() or loc.editable(key)
                                                 else loc.pending.pop(key, None), self.loc_edited()))
        else:
            ttk.Label(parent, text=title.get() or key, style="Setting.TLabel").pack(side="left")
        if not self.removable(key):
            ttk.Label(parent, text=key, style="Faint.TLabel").pack(side="left", padx=(10, 0))
            return
        # The key renames the same way: type in it. Apply writes it.
        typed = tk.StringVar(value=self.renamed.get(key, key))
        entry = ttk.Entry(parent, textvariable=typed, width=max(len(typed.get()), len(key)) + 4, style="Key.TEntry")
        entry.pack(side="left", padx=(10, 0))
        problem = ttk.Label(parent, style="Warn.TLabel")
        problem.pack(side="left", padx=(6, 0))
        typed.trace_add("write", lambda *_: problem.configure(text=self.rename_method(key, typed.get().strip())))

    def removable(self, name):
        places = self.tool.model.game["places"].get(name) if self.tool.model.game else None
        return name in self.added or (places is not None and len(places) == 1)

    def remove_button(self, parent, name):
        remove = ttk.Button(parent, text="Remove", style="Danger.TButton", command=lambda: self.remove_method(name))
        remove.pack(side="right", padx=(14, 0))
        Hint(remove, "Remove this production method and its localizations")

    def removed_line(self, parent, name):
        line = tk.Frame(parent, background=SLOT_BG, highlightthickness=1, highlightbackground=BORDER, padx=14, pady=8)
        tk.Label(line, text=f"{self.tool.loc.name(name) or name}", background=SLOT_BG, foreground=FAINT,
                 font=self.app.bold).pack(side="left")
        tk.Label(line, text=f"{name}   ·   removed on Apply", background=SLOT_BG, foreground=FAINT).pack(side="left", padx=(10, 0))
        keep = self.link(line, "Keep", lambda: self.keep_method(name), SLOT_BG)
        keep.pack(side="right")
        return line

    def scroll_to(self, card):
        height = max(self.form.winfo_reqheight(), self.canvas.winfo_height(), 1)
        y = card.frame.winfo_rooty() - self.form.winfo_rooty()
        self.canvas.yview_moveto(max(0, y - 12) / height)

    def build_header(self, building):
        loc, icons = self.tool.loc, self.tool.icons
        top = ttk.Frame(self.form)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        image = icons.building(building, 32)
        if image:
            ttk.Label(top, image=image).pack(side="left", padx=(0, 10))
        title = tk.StringVar(value=loc.name(building) or building)
        if loc.editable(building):
            entry = ttk.Entry(top, textvariable=title, width=28, style="Name.TEntry", font=self.app.heading)
            entry.pack(side="left")
            title.trace_add("write", lambda *_: (loc.set(building, title.get()), self.loc_edited()))
        else:
            ttk.Label(top, text=title.get(), style="Heading.TLabel").pack(side="left")
        ttk.Label(top, text=building, style="Faint.TLabel").pack(side="left", padx=(10, 0), pady=(6, 0))
        if building in self.app.names.get("method_owners", []):
            section = self.file.section(building)
            value = next((self.file.value(setting) for setting in section["settings"] if setting["key"] == "efficiency"), "") if section else ""
            efficiency = tk.StringVar(value="" if value.lower() in ("", "none") else value)
            entry = ttk.Entry(top, textvariable=efficiency, width=5, style="Small.TEntry")
            entry.pack(side="right")
            general = self.file.section("general")
            fallback = next((self.file.value(setting) for setting in general["settings"] if setting["key"] == "efficiency"), "100") if general else "100"
            placeholder(entry, efficiency, fallback)
            ttk.Label(top, text="food conversion efficiency % for all its methods", style="Small.TLabel").pack(side="right", padx=(0, 6))

            def changed(*_):
                self.header_edits[(building, "efficiency")] = efficiency.get().strip() or "None"
                self.edited()
            efficiency.trace_add("write", changed)

    def delete_method(self, name):
        if not messagebox.askyesno("Remove from settings", f"Remove [{name}] from the settings? No production method has this name."):
            return
        self.commit()
        self.file.remove_section(self.file.section(name))
        self.file.dirty = True
        self.refresh()

    # -------------------------------------------------------------- adding and removing production methods

    def choose_building_for_method(self):
        slots = self.tool.model.game["slots"] if self.tool.model.game else {}
        items = [(f"{self.tool.loc.name(building) or building}   {building}", building)
                 for building, _ in self.buildings() if building in slots]
        building = ListDialog(self.app, "Add production method", "Choose the building.", items).result
        if building:
            self.add_method(building)

    def add_method(self, building, number=None):
        """A blank production method in one slot. It is written to the building file on Apply."""
        game, model = self.tool.model.game, self.tool.model
        slots = game["slots"].get(building, [])
        if number is None:
            number = next((index for index, slot in enumerate(slots, 1)
                           if any(name in game["methods"] for name in slot["methods"])), None)
            if number is None:
                return
        slot = slots[number - 1]
        provisions = slot.get("new") or any(name in game["methods"] for name in slot["methods"])
        siblings = [name for name in slot["methods"] if name in game["methods"]] if provisions else \
            [name for name in slot["methods"] if game["others"].get(name, {}).get("produced")]
        names = siblings or [name for each in slots for name in each["methods"]]
        prefix = os.path.commonprefix(names) if len(names) > 1 else names[0] if names else building + "_"
        prefix = prefix[:prefix.rfind("_") + 1]
        # A blank production method with a free key. Its name and key are typed on its card.
        taken = set(game["methods"]) | set(game["others"]) | set(self.renamed.values())
        key = next(key for key in (prefix + "new" + (f"_{count}" if count > 1 else "") for count in itertools.count(1))
                   if key not in taken)
        name = ""
        self.commit()
        copied = game["fields"].get(siblings[-1], {}) if siblings else {}
        if provisions:
            fields = {"produced": "provisions", "output": "0", "category": copied.get("category", "building_maintenance")}
            game["methods"][key] = {"block": [], "owners": [building], "inputs": {}, "output": 0.0, "max_profit": None}
            game["slot_of"][key] = (building, number)
            model.added.add(key)
            if not self.file.section(key):
                self.file.add_section(key, [("food_out", "0")])
            self.file.dirty = True
        else:
            produced = game["others"][siblings[-1]]["produced"] if siblings else None
            fields = {key_: value for key_, value in (("icon_type", copied.get("icon_type")), ("icon", copied.get("icon")),
                                                      ("produced", produced), ("output", "0" if produced else None),
                                                      ("category", copied.get("category"))) if value}
            game["others"][key] = {"inputs": {}, "produced": produced, "output": 0.0, "shared": False, "users": 1}
        game["places"][key] = []
        slot["methods"].append(key)
        self.added[key] = {"building": building, "slot": slot, "fields": fields}
        if name:
            self.tool.loc.set(key, name)
        self.run_check()
        self.open_page(building, key)
        self.update_status()

    def game_values(self):
        """The game values with the edits made here."""
        values = getattr(self.tool.model, "values", None)
        if not values:
            return None
        order = {pop: index for index, pop in enumerate(POP_ORDER)}
        pops = dict(sorted(values["pops"].items(), key=lambda item: order.get(item[0], len(order))))
        added = [key[1] for key in self.value_edits if isinstance(key, tuple) and key[0] == "add_good"]
        removed = [key[1] for key in self.value_edits if isinstance(key, tuple) and key[0] == "remove_good"]
        demands = dict(values.get("luxury", {}), **{good: {"add": None, "multiply": {}} for good in added})
        luxury = {good: {"add": demand["add"], "multiply": {pop: demand["multiply"].get(pop, "0") for pop in pops}}
                  for good, demand in demands.items() if good not in removed}
        food_per_unit = dict(self.tool.model.food_per_unit)
        # The Pop Demands settings hold each class's numbers as typed, and they win over the game files
        for pop, row in self.demand_settings().items():
            if pop not in pops:
                continue
            luxury_food = row.get("total", 0) * row.get("luxury", 0) / 100
            pops[pop] = number_text(round(row.get("total", 0) - luxury_food, 5))
            for good, demand in luxury.items():
                if food_per_unit.get(good, 0) > 0:
                    demand["multiply"][pop] = number_text(round(luxury_food * row.get(good, 0) / 100, 5))
        return dict(values, **{key: self.value_edits.get(key, values[key]) for key in ("price", "food", "subsistence")}, pops=pops,
                    luxury=luxury, removed_luxury=removed, food_per_unit=food_per_unit)

    def extra_rows(self, section_name, row):
        """The game values on the general page: the provisions good, subsistence food and each pop type's food."""
        values = self.game_values()
        if section_name != "general" or not values:
            return row
        icons = self.tool.icons

        def setting_row(title, help_text):
            nonlocal row
            ttk.Separator(self.form).grid(row=row, column=0, columnspan=3, sticky="ew")
            label = ttk.Frame(self.form)
            label.grid(row=row + 1, column=0, sticky="nw", padx=(0, 28), pady=14)
            ttk.Label(label, text=title, style="Setting.TLabel").pack(anchor="w")
            ttk.Label(label, text=help_text, style="Help.TLabel", wraplength=250, justify="left").pack(anchor="w", pady=(3, 0))
            controls = ttk.Frame(self.form)
            controls.grid(row=row + 1, column=1, columnspan=2, sticky="w", pady=14)
            row += 2
            return controls

        def entry(parent, key, value, width=7):
            variable = tk.StringVar(value=value)

            def changed(*_):
                original = self.tool.model.values[key]
                if variable.get().strip() == original:
                    self.value_edits.pop(key, None)
                else:
                    self.value_edits[key] = variable.get().strip()
                show_linked()
                self.update_status()
                self.schedule_check()
            variable.trace_add("write", changed)
            ttk.Entry(parent, textvariable=variable, width=width, justify="right").pack(side="left")

        controls = setting_row("Provisions", "The provisions good: its price, and the food in one unit. "
                                             "Apply also changes FOOD_PRICE and the food demand script to match.")
        icon_label(controls, icons.good("provisions", 18), "").pack(side="left", padx=(0, 6))
        entry(controls, "price", values["price"])
        icon_label(controls, icons.gold(16), "").pack(side="left", padx=(4, 18))
        entry(controls, "food", values["food"])
        icon_label(controls, icons.food(16), " food").pack(side="left", padx=(4, 0))
        controls = setting_row("Subsistence food", "Food per 1k idle peasants and slaves (SUBSISTENCE_AGRICULTURE). "
                                                   "The provisions base production follows it.")
        entry(controls, "subsistence", values["subsistence"])
        icon_label(controls, icons.food(16), " food").pack(side="left", padx=(4, 0))
        linked = ttk.Label(self.form, style="Faint.TLabel", wraplength=640, justify="left")
        linked.grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 12))
        row += 1

        def show_linked():
            follow = linked_values(self.game_values())
            linked.configure(text="Not a number." if follow is None else
                             f"Apply also sets: base production {follow['base_production']}  ·  "
                             f"FOOD_PRICE {follow['food_price']}  ·  food demand divided by {follow['divide']}")
        show_linked()
        return row

    def show_demand_page(self):
        """Each class's food: the total, the share luxury goods carry and how the luxury food splits between the goods.
        Provisions carry the rest."""
        self.section_name = None
        for child in self.form.winfo_children():
            child.destroy()
        self.form.columnconfigure(0, weight=0, minsize=0)
        self.form.columnconfigure(1, weight=1)
        self.path_label.configure(text=Path(VALUE_FILES["pops"]).name + ", " + Path(VALUE_FILES["food_goods"]).name)
        ttk.Label(self.form, text="Pop Demands", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(self.form, text="Food per 1k pops per month. Luxury goods carry the luxury share, provisions carry the rest.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 16))
        values, original = self.game_values(), getattr(self.tool.model, "values", None)
        if not values:
            return
        icons, food_per_unit = self.tool.icons, self.tool.model.food_per_unit
        goods = [good for good in values["luxury"] if food_per_unit.get(good, 0) > 0]
        food_icon, provisions_icon = icons.food(14), icons.good("provisions", 14)
        try:
            food_per_provision = float(values["food"])
        except (TypeError, ValueError):
            food_per_provision = 0
        # The whole table scrolls sideways when it does not fit. left holds the class columns, table the goods.
        holder = tk.Canvas(self.form, background=BG, highlightthickness=0, height=1)
        holder.grid(row=2, column=0, columnspan=2, sticky="new")
        inner = ttk.Frame(holder)
        holder.create_window(0, 0, window=inner, anchor="nw")
        left, table = ttk.Frame(inner), ttk.Frame(inner)
        left.grid(row=0, column=0, sticky="nw")
        table.grid(row=0, column=1, sticky="nw")
        bar = ttk.Scrollbar(self.form, orient="horizontal", command=holder.xview)
        holder.configure(xscrollcommand=bar.set)
        self.sideways = holder
        for frame in (left, table):
            # Both sides get the same row heights, so the rows line up
            frame.rowconfigure(0, minsize=32)
            for row in range(1, len(values["pops"]) + 1):
                frame.rowconfigure(row, minsize=34)
        for column, title in enumerate(("", "Total Food", "Luxury Food", "Provisions Food")):
            ttk.Label(left, text=title, style="Setting.TLabel").grid(row=0, column=column, sticky="sw", padx=(0, 12), pady=(0, 6))
        for column, good in enumerate(goods):
            header = ttk.Frame(table)
            header.grid(row=0, column=column, sticky="sw", padx=(0, 12), pady=(0, 6))
            name = icon_label(header, icons.good(good, 18), " " + (self.tool.loc.name(good) or good), style="Setting.TLabel")
            name.pack(side="left")
            Hint(name, f"{number_text(food_per_unit[good])} food per unit")
            remove = self.link(header, "✕", lambda good=good: self.change_luxury(good, False), BG)
            remove.configure(foreground=FAINT)
            remove.pack(side="left", padx=(6, 0))
            Hint(remove, "Pops stop buying this good as luxury food")
        # Goods with a food value and a block in the mod's goods files can become luxury goods
        choices = [good for good in food_per_unit if good not in goods and good in values["goods_at"]]
        if choices:
            add = self.link(table, "+ luxury good", lambda: menu.tk_popup(add.winfo_rootx(), add.winfo_rooty() + add.winfo_height()), BG)
            add.grid(row=0, column=len(goods), sticky="sw", pady=(0, 6))
            menu = tk.Menu(add, tearoff=0)
            for good in choices:
                menu.add_command(label=self.tool.loc.name(good) or good, image=icons.good(good, 16) or "", compound="left",
                                 command=lambda good=good: self.change_luxury(good, True))

        def add_row(row, pop):
            # The numbers behind the rounded text, used until a cell is edited
            exact = self.demand_row(pop, values, goods)
            shown = {key: number_text(round(exact.get(key, 0), 2)) if exact.get(key) else "" for key in ["total", "luxury"] + goods}
            variables = {key: tk.StringVar(value=text) for key, text in shown.items()}

            def number(key):
                text = variables[key].get().strip().rstrip("%")
                if text == shown[key]:
                    return exact.get(key, 0.0)
                try:
                    return float(text) if text else 0.0
                except ValueError:
                    return None

            def cell(column, key, unit, parent=left):
                frame = ttk.Frame(parent)
                frame.grid(row=row, column=column, sticky="w", padx=(0, 12))
                ttk.Entry(frame, textvariable=variables[key], width=6, justify="right").pack(side="left")
                if unit:
                    ttk.Label(frame, text=unit, style="Faint.TLabel").pack(side="left", padx=(2, 0))
                return frame

            def amount(parent, image, style="Small.TLabel"):
                """A computed amount with the icon of its unit after it: food or provisions."""
                label = ttk.Label(parent, image=image or "", compound="right", style=style)
                label.pack(side="left", padx=(4, 0))
                return label

            ttk.Label(left, text=pop.capitalize()).grid(row=row, column=0, sticky="w", padx=(0, 12))
            ttk.Label(cell(1, "total", ""), image=food_icon or "", text="" if food_icon else " food",
                      style="Faint.TLabel").pack(side="left", padx=(4, 0))
            cell(2, "luxury", "%")
            provisions_cell = ttk.Frame(left)
            provisions_cell.grid(row=row, column=3, sticky="w", padx=(0, 12))
            provisions_label = amount(provisions_cell, food_icon, "Muted.TLabel")
            units_label = amount(provisions_cell, provisions_icon)
            food_labels = {}
            for column, good in enumerate(goods, 4):
                food_labels[good] = amount(cell(column - 4, good, "%", table), food_icon)
            warning = ttk.Label(table, style="Warn.TLabel")
            warning.grid(row=row, column=len(goods) + 1, sticky="w")

            def changed(*_, first=False):
                numbers = {key: number(key) for key in variables}
                if None in numbers.values():
                    warning.configure(text="not a number")
                    return
                luxury_food = numbers["total"] * numbers["luxury"] / 100
                provisions_food = numbers["total"] - luxury_food
                provisions_label.configure(text=f"{number_text(round(provisions_food, 5))} " if food_icon else
                                           f"{number_text(round(provisions_food, 5))} food")
                units = number_text(round(provisions_food / food_per_provision, 5)) if food_per_provision else "?"
                units_label.configure(text=f"=  {units} " if provisions_icon else f"=  {units} provisions")
                for good in goods:
                    food = luxury_food * numbers[good] / 100
                    text = number_text(round(food, 5)) if food else ""
                    food_labels[good].configure(text=(text + " " if food_icon else text + " food") if text else " ",
                                                image=(food_icon or "") if text else "")
                shares = sum(numbers[good] for good in goods)
                warning.configure(text=f"shares total {shares:g}%, need 100%" if luxury_food and abs(shares - 100) >= 0.05 else "")
                if not first:
                    self.set_demand_row(pop, numbers)
            for variable in variables.values():
                variable.trace_add("write", changed)
            changed(first=True)

        for row, pop in enumerate(values["pops"], 1):
            add_row(row, pop)

        def fit(_=None):
            width, height = inner.winfo_reqwidth(), inner.winfo_reqheight()
            holder.configure(height=height, scrollregion=(0, 0, width, height))
            if holder.winfo_width() > 1 and holder.winfo_width() < width:
                bar.grid(row=3, column=0, columnspan=2, sticky="ew")
            else:
                bar.grid_remove()
        inner.bind("<Configure>", fit)
        holder.bind("<Configure>", fit)
        fit()

    def demand_settings(self):
        """{pop type: {"total", "luxury", good: share}} from the Pop Demands section of the settings."""
        section = self.file.section(POP_PAGE)
        rows = {}
        for setting in section["settings"] if section else []:
            try:
                rows[setting["key"]] = {key: float(value) for key, value in parse_map(self.file.value(setting)) or []}
            except ValueError:
                pass
        return rows

    def demand_row(self, pop, values, goods):
        """A class's total, luxury share and goods shares: from the settings, else worked out from the game files."""
        row = self.demand_settings().get(pop)
        if row is not None:
            return dict(row)
        foods = {good: float(values["luxury"][good]["multiply"].get(pop, 0)) for good in goods}
        luxury = sum(foods.values())
        total = float(values["pops"][pop]) + luxury
        row = {"total": total, "luxury": luxury / total * 100 if total else 0}
        row.update({good: food / luxury * 100 if luxury else 0 for good, food in foods.items()})
        return row

    def set_demand_row(self, pop, row):
        """Writes a class's numbers to the settings as typed. Apply works out the game values from them."""
        text = map_text([(key, number_text(round(value, 5))) for key, value in row.items() if value or key in ("total", "luxury")])
        section = self.file.section(POP_PAGE)
        setting = next((setting for setting in section["settings"] if setting["key"] == pop), None) if section else None
        if setting and self.file.value(setting) == text:
            return
        self.write_edits(self.file, [(POP_PAGE, pop, text)])
        self.file.dirty = True
        self.update_status()

    def change_luxury(self, good, add):
        """Adds a luxury good column, or removes one. Apply writes the demand lines."""
        if add:
            if ("remove_good", good) in self.value_edits:
                self.value_edits.pop(("remove_good", good))
            else:
                self.value_edits[("add_good", good)] = True
        else:
            # Each class keeps its total and luxury share: the good's share goes to the other luxury goods by their
            # shares, or to provisions when the class buys no other luxury good
            values = self.game_values()
            goods = [other for other in values["luxury"] if values["food_per_unit"].get(other, 0) > 0]
            for pop in values["pops"]:
                row = self.demand_row(pop, values, goods)
                share = row.pop(good, 0)
                if not share and pop not in self.demand_settings():
                    continue
                kept = sum(row.get(other, 0) for other in goods if other != good)
                for other in goods:
                    if other != good and kept:
                        row[other] = row.get(other, 0) * (kept + share) / kept
                if share and not kept:
                    row["luxury"] = 0
                self.set_demand_row(pop, row)
            if ("add_good", good) in self.value_edits:
                self.value_edits.pop(("add_good", good))
            else:
                self.value_edits[("remove_good", good)] = True
        self.render_page()
        self.update_status()

    def convert_to_provisions(self, name):
        """An other production method that now makes provisions gets settings, so the generator sets its food."""
        game, model = self.tool.model.game, self.tool.model
        building, number = next((building, number) for building, slots in game["slots"].items()
                                for number, slot in enumerate(slots, 1) if name in slot["methods"])
        self.commit()
        for card in self.other_cards:
            if card.name == name:
                card.changed = False  # Its old output must not be kept over the change below
        game["others"].pop(name)
        game["methods"][name] = {"block": [], "owners": [building], "inputs": {}, "output": 0.0, "max_profit": None}
        game["slot_of"][name] = (building, number)
        # Apply first writes produced = provisions into the block, then the generator writes the inputs and output
        self.block_edits[name] = {"inputs": {}, "output": 0.0, "produced": "provisions"}
        if name in self.added:
            self.added[name]["fields"] = {key: value for key, value in self.added[name]["fields"].items()
                                          if key in ("icon_type", "icon", "category")}
            model.added.add(name)
        else:
            model.converted.add(name)
        # A section kept from before is used as it is, so the settings do not hold the method twice
        if not self.file.section(name):
            self.file.add_section(name, [("food_out", "0")])
        self.file.dirty = True
        self.run_check()
        self.open_page(building, name)
        self.update_status()

    def add_slot(self, building):
        self.tool.model.game["slots"][building].append({"shared": False, "methods": [], "new": True})
        self.open_page(building, self.focus)
        self.update_status()

    def remove_method(self, name):
        """Marks the production method for removal on Apply. A production method added since the last Apply goes now."""
        game, model = self.tool.model.game, self.tool.model
        self.commit()
        # A removed production method is not renamed
        self.renamed.pop(name, None)
        self.tool.loc.renames.pop(name, None)
        if name in self.added:
            spec = self.added.pop(name)
            spec["slot"]["methods"].remove(name)
            for table in ("methods", "others", "places", "slot_of"):
                game[table].pop(name, None)
            model.added.discard(name)
            section = self.file.section(name)
            if section:
                self.file.remove_section(section)
            self.tool.loc.pending.pop(name, None)
        else:
            path = game["places"][name][0][0]
            used = sorted({str(other.relative_to(MOD_ROOT)) for other in mod_script_files() if other != path and re.search(
                r"\b" + re.escape(name) + r"\b", other.read_text(encoding="utf-8-sig", errors="replace"))})
            if used and not messagebox.askyesno(
                    "Still used elsewhere",
                    f"{self.tool.loc.name(name) or name} is also used in:\n\n" + "\n".join(used) +
                    "\n\nIf you remove it, those files will point to a production method that no longer exists."
                    "\n\nRemove it anyway?"):
                return
            self.removed.add(name)
        if self.focus == name:
            self.focus = None
        self.run_check()
        self.open_page(self.page, self.focus)
        self.update_status()

    def rename_method(self, name, new):
        """Apply renames the key everywhere the mod uses it. Returns the problem with the new key, or ""."""
        game, loc = self.tool.model.game, self.tool.loc
        taken = (set(game["methods"]) | set(game["others"]) | set(self.renamed.values())) - {self.renamed.get(name), name}
        self.renamed.pop(name, None)
        loc.renames.pop(name, None)
        if new and new != name and re.fullmatch(r"[A-Za-z_]\w*", new) and new not in taken:
            self.renamed[name] = loc.renames[name] = new
        self.update_status()
        if not new or new == name:
            return ""
        return "letters, digits and _ only" if not re.fullmatch(r"[A-Za-z_]\w*", new) else "already used" if new in taken else ""

    @staticmethod
    def rename_section(settings_file, old, new):
        section = settings_file.section(old)
        # A left-over section with the new key holds no method, so the renamed one replaces it
        stale = settings_file.section(new)
        if section and stale:
            settings_file.remove_section(stale)
            settings_file.parse()
            section = settings_file.section(old)
        if section:
            settings_file.lines[section["header"]] = f"[{new}]"
            settings_file.parse()

    def keep_method(self, name):
        self.removed.discard(name)
        self.open_page(self.page, self.focus)
        self.update_status()

    def new_slots(self):
        game = self.tool.model.game
        return [(building, slot) for building, slots in (game["slots"].items() if game else []) for slot in slots if slot.get("new")]

    def write_building_files(self):
        """Writes the added and removed production methods, new slots, the other production methods' amounts
        and the game values. Works out every file first, so a problem stops it before anything is written."""
        writer = load_module(PROVISIONS, "provisions_methods_write")
        self.backup_folder = None
        worked = self.building_texts(writer)
        if worked is None:
            return False
        texts = worked[0]
        if not texts:
            return True
        names = list(self.added) + sorted(self.removed) + [name for name in self.block_edits if name not in self.removed] \
            + list(self.renamed.values())
        self.backup_folder = writer.write_with_backup({path: ("\ufeff" + text).encode("utf-8") for path, text in texts.items()},
                                                      "apply", names)
        return True

    def building_texts(self, writer, title="Not applied"):
        """({path: new text}, {added method: path}) for the window's own changes. None after a problem."""
        game = self.tool.model.game
        texts, where = {}, {}

        def text_of(path):
            if path not in texts:
                texts[path] = path.read_bytes().decode("utf-8-sig")
            return texts[path]

        def path_of(name):
            places = game["places"].get(name)
            return where.get(name) or (places[0][0] if places and len(places) == 1 else None)

        def blank(key, fields, indent, newline):
            return newline.join([f"{indent}{key} = {{"] + [f"{indent}\t{field} = {value}" for field, value in fields.items()]
                                + [f"{indent}}}"])

        def fail(text):
            messagebox.showerror(title, text + " Nothing was written.")
            return None

        for key, spec in self.added.items():
            slot = spec["slot"]
            if slot.get("new"):
                continue
            anchor = next((name for name in reversed(slot["methods"][:slot["methods"].index(key)]) if path_of(name)), None)
            if anchor is None:
                return fail(f"{key}: the mod does not define the other production methods in its slot.")
            path = path_of(anchor)
            text = text_of(path)
            spans = writer.block_span(text, anchor)
            if len(spans) != 1:
                return fail(f"{anchor} is not defined once in {path.name}.")
            start, end = spans[0]
            newline = "\r\n" if "\r\n" in text else "\n"
            indent = re.match(r"[ \t]*", text[start:]).group(0)
            texts[path] = text[:end] + newline * 2 + blank(key, spec["fields"], indent, newline) + text[end:]
            where[key] = path
        for building, slot in self.new_slots():
            if not slot["methods"]:
                continue
            path = next((path_of(name) for each in game["slots"][building] for name in each["methods"] if path_of(name)), None)
            text = text_of(path) if path else ""
            spans = next((spans for spans in (writer.block_span(text, prefix + building) for prefix in ("", "REPLACE:", "INJECT:"))
                          if len(spans) == 1), None)
            if not spans:
                return fail(f"{building} is not defined once in the mod.")
            start, end = spans[0]
            newline = "\r\n" if "\r\n" in text else "\n"
            indent = re.match(r"[ \t]*", text[start:]).group(0)
            closing = text.rfind("\n", 0, end - 1) + 1
            body = (newline * 2).join(blank(key, self.added[key]["fields"], indent + "\t\t", newline) for key in slot["methods"])
            texts[path] = (text[:closing] + newline + f"{indent}\tunique_production_methods = {{{newline}{body}{newline}"
                           f"{indent}\t}}{newline}" + text[closing:])
            for key in slot["methods"]:
                where[key] = path
        for name in self.removed:
            path = path_of(name)
            text = text_of(path)
            spans = writer.block_span(text, name)
            if len(spans) != 1:
                return fail(f"{name} is not defined once in {path.name}.")
            start, end = spans[0]
            before, after = text[:start], text[end:]
            # The rest of the block's last line goes, and one blank line, so the blocks around it keep their spacing
            after = re.sub(r"^[ \t]*\r?\n", "", after, count=1)
            if re.match(r"[ \t]*\r?\n", after) and (re.search(r"\n[ \t]*\r?\n$", before) or before.rstrip().endswith("{")):
                after = re.sub(r"^[ \t]*\r?\n", "", after, count=1)
            texts[path] = before + after
        for name, values in self.block_edits.items():
            if name in self.removed:
                continue
            path = path_of(name)
            text = text_of(path)
            spans = writer.block_span(text, name)
            if len(spans) != 1:
                return fail(f"{name} is not defined once in {path.name}.")
            start, end = spans[0]
            try:
                block = rewrite_amounts(text[start:end], values["inputs"], values["output"], game["goods"], values["produced"],
                                        "\r\n" if "\r\n" in text else "\n")
            except ValueError as problem:
                return fail(f"{name}: {problem}")
            texts[path] = text[:start] + block + text[end:]
        for old, new in self.renamed.items():
            if old in self.removed:
                continue
            for path in mod_script_files():
                text = texts.get(path) or path.read_bytes().decode("utf-8-sig", errors="replace")
                if re.search(r"\b" + re.escape(old) + r"\b", text):
                    texts[path] = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
        try:
            current = lambda path: texts.get(path) or path.read_bytes().decode("utf-8-sig")
            for path, text in write_game_values(writer.MOD_FOLDER, self.game_values(), current).items():
                if text != current(path):
                    texts[path] = text
        except ValueError as problem:
            return fail(f"Game values: {problem}")
        return texts, where

    def remove_names(self, names):
        """Takes each name and its _desc line out of the mod's localization."""
        loc, lines_of = self.tool.loc, {}
        for name in names:
            for key in (name, name + "_desc"):
                if key in loc.where:
                    path, index = loc.where[key]
                    lines_of.setdefault(path, []).append(index)
        for path, indexes in lines_of.items():
            lines = path.read_bytes().decode("utf-8-sig").split("\n")
            for index in sorted(set(indexes), reverse=True):
                del lines[index]
            path.write_bytes("\n".join(lines).encode("utf-8-sig"))

    # -------------------------------------------------------------- edits and the live check

    def pending_edits(self):
        edits = [edit for card in self.cards for edit in card.edits()]
        edits += [(section, key, value) for (section, key), value in self.header_edits.items()]
        edits += [(self.section_name, key, editor.get()) for _, key, editor in self.editors if editor.changed]
        return edits

    def write_edits(self, target, edits):
        """Changes first, last line first so line numbers hold, then new settings and new sections."""
        existing, new = [], []
        for section_name, key, value in edits:
            section = target.section(section_name)
            setting = next((setting for setting in section["settings"] if setting["key"] == key), None) if section else None
            (existing if setting else new).append((setting or section_name, key, value))
        for setting, _, value in sorted(existing, key=lambda edit: -edit[0]["start"]):
            target.set_value(setting, value)
        target.parse()
        for section_name, key, value in new:
            if value.strip().lower() == "none":
                continue
            section = target.section(section_name)
            if section:
                target.add_setting(section, key, value)
            else:
                target.add_section(section_name, [(key, value)])

    def commit(self):
        self.write_edits(self.file, self.pending_edits())
        self.editors, self.header_edits = [], {}
        for card in self.cards:
            card.changed = set()

    def edited(self):
        self.file.dirty = True
        self.update_status()
        self.schedule_check()

    def loc_edited(self):
        self.update_status()
        self.draw_list()

    @property
    def dirty(self):
        return super().dirty or bool(self.tool.loc.pending) or bool(getattr(self, "block_edits", None)) or \
            any(card.changed for card in getattr(self, "other_cards", [])) or bool(getattr(self, "added", None)) or \
            bool(getattr(self, "removed", None)) or bool(getattr(self, "renamed", None)) or bool(self.new_slots()) or bool(getattr(self, "value_edits", None))

    def block_edited(self):
        self.update_status()

    def keep_block_edits(self):
        """Keeps the other production methods' edits when their cards go away. False when an amount is not a number."""
        for card in self.other_cards:
            if card.changed:
                values = card.values()
                if values is None:
                    messagebox.showerror("Not a number", f"{card.name} has an amount that is not a number.")
                    return False
                self.block_edits[card.name] = values
                card.changed = False
        return True

    def save(self):
        """Writes the building files, the settings and the names. Apply runs this before the generator."""
        if not self.keep_block_edits():
            return False
        self.commit()
        if not self.write_building_files():
            return False
        loc = self.tool.loc
        for name in self.removed:
            section = self.file.section(name)
            if section:
                self.file.remove_section(section)
                self.file.dirty = True
            loc.pending.pop(name, None)
            loc.renames.pop(name, None)
        for old, new in self.renamed.items():
            if old not in self.removed:
                self.rename_section(self.file, old, new)
        self.reload_names = bool(loc.pending or self.removed or self.renamed)
        loc.save()
        self.remove_names(self.removed)
        for _, slot in self.new_slots():
            slot.pop("new")
        self.added, self.removed, self.block_edits, self.renamed = {}, set(), {}, {}
        self.tool.model.added, self.tool.model.converted = set(), set()
        self.tool.model.values = read_game_values(self.tool.model.module.MOD_FOLDER)
        self.value_edits = {}
        super().save()
        return True

    def dry_run(self):
        """The generator's report on the settings as they are in the window, without writing them,
        and the code diff of everything Apply would write. The Code changes box picks which one shows."""
        self.commit()
        code = self.code_changes_view()
        if code is None:
            return
        self.views = None
        self.view_strip.pack_forget()

        def done(output, exit_code):
            self.views = {"summary": list(self.last_run_lines), "code": code}
            self.view_strip.pack(fill="x", before=self.output.master)
            self.show_view()
        preview = SettingsFile.__new__(SettingsFile)
        preview.path, preview.kind, preview.bom, preview.dirty = self.file.path, self.file.kind, self.file.bom, False
        preview.lines = list(self.file.lines)
        preview.parse()
        path = Path(tempfile.gettempdir()) / "mnt_provisions_dry_run_settings.txt"
        path.write_text("\n".join(preview.lines), encoding="utf-8-sig")
        self.run(["--settings", str(path)], done)

    def code_changes_view(self):
        """[(text, tags)] for each file Apply would write, as a diff: the window's own edits, then the generator's
        recipes on top. None after a problem."""
        self.run_check()
        model, writer = self.tool.model, load_module(PROVISIONS, "provisions_methods_write")
        worked = self.building_texts(writer, "Apply Dry Run")
        if worked is None:
            return None
        texts, where = worked
        before, after, notes = {}, {}, []

        def current(path):
            if path not in before:
                before[path] = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
            return before[path]
        for path, text in texts.items():
            current(path)
            after[path] = text.replace("\r\n", "\n")
        # The generator's new amounts, as Apply's run writes them after the window's edits
        module = model.module
        for name, result in sorted(model.raw.items()):
            if result["setting"] is None or not result["changes"] or name in self.removed:
                continue
            path = where.get(name) or (Path(result["places"][0][0]) if len(result["places"]) == 1 else None)
            if path is None:
                continue
            text = after.get(path, current(path))
            spans = module.block_span(text, self.renamed.get(name, name))
            if len(spans) != 1:
                notes.append(f"{name}: not defined once in {path.name}, so the generator skips it.")
                continue
            start, end = spans[0]
            try:
                after[path] = text[:start] + module.rewrite(text[start:end], result, model.game["goods"], model.food_per_unit) + text[end:]
            except module.Problem as problem:
                notes.append(str(problem))
        settings_before = self.file.path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n") if self.file.path.exists() else ""
        preview = SettingsFile.__new__(SettingsFile)
        preview.path, preview.kind, preview.bom, preview.dirty = self.file.path, self.file.kind, self.file.bom, False
        preview.lines = list(self.file.lines)
        preview.parse()
        for name in self.removed:
            section = preview.section(name)
            if section:
                preview.remove_section(section)
        for old, new in self.renamed.items():
            self.rename_section(preview, old, new)
        before[self.file.path], after[self.file.path] = settings_before, "\n".join(preview.lines).replace("\r\n", "\n")
        loc_files, _ = self.tool.loc.new_lines()
        removed_lines = {}
        for name in self.removed:
            for key in (name, name + "_desc"):
                if key in self.tool.loc.where:
                    path, index = self.tool.loc.where[key]
                    removed_lines.setdefault(path, set()).add(index)
        for path in set(loc_files) | set(removed_lines):
            lines = list(loc_files[path][1]) if path in loc_files else path.read_bytes().decode("utf-8-sig").split("\n")
            for index in sorted(removed_lines.get(path, ()), reverse=True):
                del lines[index]
            current(path)
            after[path] = "\n".join(lines).replace("\r\n", "\n")
        view = [("> code changes Apply would write\n", ("2",))]
        changed = 0
        for path in sorted(after, key=lambda path: str(path)):
            if after[path] == before.get(path, ""):
                continue
            changed += 1
            try:
                shown = path.relative_to(MOD_ROOT).as_posix()
            except ValueError:
                shown = path.name
            view.append((f"\n{shown}\n", ("1;34",)))
            for line in diff_lines(before.get(path, "").split("\n"), after[path].split("\n")):
                tag = "32" if line.startswith("+") else "91" if line.startswith("-") else "2" if line.startswith("@@") else ()
                view.append((line + "\n", (tag,) if tag else ()))
        view += [(note + "\n", ("33",)) for note in notes]
        view.append(("\nNo file changes.\n" if not changed else f"\n{changed} file{'s' if changed != 1 else ''} change. Nothing was written.\n",
                     ("2",)))
        return view

    # Save and the generator's apply are one step for the user: Apply
    close_question = "Apply your changes before closing?"

    def primary(self):
        self.action(["--apply"], None)

    def finish_before_close(self):
        if not self.save():
            return False
        return self.run_before_close(["--apply"] + self.backup_arguments(["--apply"]))

    def backup_arguments(self, arguments):
        """The generator adds its files to the backup that save made, so one Apply is one backup to restore."""
        folder, self.backup_folder = self.backup_folder, None
        return ["--into-backup", str(folder)] if folder and "--apply" in arguments else []

    def update_status(self):
        dirty = self.dirty
        results = self.tool.model.results.values() if self.tool.model.results else []
        waiting = dirty or any(result["pending"] for result in results)
        self.status.configure(text="Not applied" if waiting else "Applied", foreground=WARN if waiting else FAINT)
        self.save_button.state(["!disabled"] if waiting else ["disabled"])
        self.undo_button.state(["!disabled"] if dirty else ["disabled"])

    def revert(self):
        if self.dirty and not messagebox.askyesno("Undo changes", "Undo the changes you have not applied?"):
            return
        self.tool.loc.pending, self.tool.loc.renames, self.renamed = {}, {}, {}
        self.block_edits = {}
        self.value_edits = {}
        structure = bool(self.added or self.removed or self.new_slots() or self.tool.model.converted)
        for building, slot in self.new_slots():
            self.tool.model.game["slots"][building].remove(slot)
        self.added, self.removed = {}, set()
        self.tool.model.added, self.tool.model.converted = set(), set()
        if structure:
            self.reload_after_run()
        for card in self.other_cards:
            card.changed = False
        for _, settings_file in self.files:
            settings_file.load()
        self.refresh()

    def schedule_check(self):
        if self.check_after:
            self.app.root.after_cancel(self.check_after)
        self.check_after = self.app.root.after(250, self.run_check)

    def run_check(self):
        self.check_after = None
        model = self.tool.model
        if model.game is None:
            return
        preview = SettingsFile.__new__(SettingsFile)
        preview.path, preview.kind, preview.bom, preview.dirty = self.file.path, self.file.kind, self.file.bom, False
        preview.lines = list(self.file.lines)
        preview.parse()
        self.write_edits(preview, self.pending_edits())
        model.analyse(preview.lines, self.game_values())
        self.update_notice()
        for card in self.cards:
            card.update()
        self.draw_list()

    def reload_after_run(self, names=False):
        """A run may change the building files and the settings, so the game data is read again."""
        if not self.dirty:
            for _, settings_file in self.files:
                settings_file.load()

        names = names or self.reload_names
        self.reload_names = False
        # Pending additions live only in the game data, so a dry run must not read the files over them
        keep = bool(self.added or self.new_slots())

        def work():
            try:
                if not self.tool.loc.names or names:
                    self.tool.loc.load(self.tool.model.game_folder())
                if not keep:
                    self.tool.model.load_game()
            except Exception as error:  # The window has to say why the check stopped
                self.tool.model.problem = f"Could not read the game files: {error}"
            self.app.root.after(0, lambda: (self.refresh(), self.run_check()))
        threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ the window

class App:
    def __init__(self, tool_class):
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        self.root = tk.Tk()
        self.root.title(tool_class.title)
        self.root.configure(background=BG)
        width = min(1360, int(self.root.winfo_screenwidth() * 0.9))
        height = min(940, int(self.root.winfo_screenheight() * 0.86))
        self.root.geometry(f"{width}x{height}+{(self.root.winfo_screenwidth() - width) // 2}+"
                           f"{max(0, (self.root.winfo_screenheight() - height) // 2 - 20)}")
        self.root.minsize(980, 600)
        self.dark_title_bar(self.root)
        self.names, self.inbox = {}, queue.Queue()
        self.style_window()

        sidebar = ttk.Frame(self.root, style="Side.TFrame", width=300)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text=tool_class.title, style="Brand.TLabel").pack(anchor="w", padx=18, pady=(18, 0))
        ttk.Label(sidebar, text=tool_class.purpose, style="SideNote.TLabel", wraplength=260,
                  justify="left").pack(anchor="w", padx=18, pady=(2, 14))
        self.side_stack = ttk.Frame(sidebar, style="Side.TFrame")
        self.side_stack.pack(fill="both", expand=True)
        self.side_stack.rowconfigure(0, weight=1)
        self.side_stack.columnconfigure(0, weight=1)
        ttk.Frame(self.root, style="Line.TFrame", width=1).pack(side="left", fill="y")
        self.main_stack = ttk.Frame(self.root)
        self.main_stack.pack(side="left", fill="both", expand=True)
        self.main_stack.rowconfigure(0, weight=1)
        self.main_stack.columnconfigure(0, weight=1)

        tool = tool_class(self)
        self.current = (ProvisionsDocument if isinstance(tool, ProvisionsMethods) else BuildingDocument)(self, tool)
        self.current.show()

        self.root.bind_all("<MouseWheel>", self.wheel)
        # Scrolling the form must not change the dropdown under the pointer
        self.root.unbind_class("TCombobox", "<MouseWheel>")
        self.root.bind("<Control-s>", lambda _: self.current.primary())
        self.root.bind("<Control-f>", lambda _: self.current.search_entry.focus_set())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self.problem
        self.root.after(200, self.current.place_sash)
        threading.Thread(target=lambda: self.inbox.put(load_names(self.current.tool)), daemon=True).start()
        self.wait_for_names()

    def wheel(self, event):
        # The path as Tk gives it. tkinter cannot name a dropdown's list, and that list scrolls itself.
        under = str(self.root.tk.call("winfo", "containing", event.x_root, event.y_root))
        sideways = getattr(self.current, "sideways", None)
        if event.state & 0x1 and sideways is not None and sideways.winfo_exists() and under.startswith(str(sideways)):
            sideways.xview_scroll(int(-event.delta / 120), "units")
            return
        for canvas in self.current.wheel_canvases():
            if under.startswith(str(canvas)) and ".popdown" not in under:
                canvas.yview_scroll(int(-event.delta / 120), "units")

    def wait_for_names(self):
        try:
            self.names, problems = self.inbox.get_nowait()
        except queue.Empty:
            self.root.after(100, self.wait_for_names)
            return
        document = self.current
        document.commit()
        document.refresh()
        if problems:
            document.clear_output()
            for problem in problems:
                document.write(problem + "\n", ("33",))

    def style_window(self):
        family = "Segoe UI" if os.name == "nt" else tkfont.nametofont("TkDefaultFont").cget("family")
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(family=family, size=10)
        tkfont.nametofont("TkTextFont").configure(family=family, size=10)
        self.bold = tkfont.Font(family=family, size=10, weight="bold")
        self.mono = tkfont.Font(family="Consolas" if os.name == "nt" else "DejaVu Sans Mono", size=10)
        self.mono_bold = tkfont.Font(family=self.mono.cget("family"), size=10, weight="bold")
        self.caption = tkfont.Font(family=family, size=8, weight="bold")
        self.small = tkfont.Font(family=family, size=8)
        self.heading = tkfont.Font(family=family, size=14, weight="bold")
        self.header_font = tkfont.Font(family=family, size=11, weight="bold")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER,
                        lightcolor=BG, darkcolor=BG, troughcolor=BG, focuscolor=BG, insertcolor=TEXT,
                        selectbackground=SELECTED, selectforeground=TEXT, arrowcolor=MUTED, font=base)
        style.map(".", foreground=[("disabled", FAINT)])

        def flat(name, background, foreground, hover, hover_text=None, padding=(14, 6), font=None):
            style.configure(name, background=background, foreground=foreground, bordercolor=background,
                            lightcolor=background, darkcolor=background, borderwidth=0, focusthickness=0,
                            padding=padding, relief="flat", **({"font": font} if font else {}))
            style.map(name, background=[("disabled", background), ("pressed", hover), ("active", hover)],
                      bordercolor=[("active", hover)], lightcolor=[("active", hover)], darkcolor=[("active", hover)],
                      foreground=[("disabled", FAINT), ("active", hover_text or foreground)])

        flat("TButton", FIELD, TEXT, HOVER)
        flat("Accent.TButton", ACCENT, "#ffffff", ACCENT_HOVER, font=self.bold)
        style.map("Accent.TButton", background=[("disabled", FIELD), ("active", ACCENT_HOVER)],
                  foreground=[("disabled", FAINT), ("active", "#ffffff")])
        flat("Ghost.TButton", BG, MUTED, FIELD, TEXT)
        flat("Danger.TButton", BG, FAINT, FIELD, BAD, padding=(10, 4))
        flat("Icon.TButton", BG, FAINT, FIELD, BAD, padding=(6, 2))
        flat("Side.TButton", SIDEBAR, MUTED, FIELD, TEXT, padding=(12, 7))
        flat("ConsoleGhost.TButton", CONSOLE, FAINT, FIELD, TEXT, padding=(10, 4))
        flat("ChipX.TButton", HOVER, MUTED, BORDER, BAD, padding=(4, 0))
        style.configure("Side.TButton", anchor="w")

        style.configure("TFrame", background=BG)
        style.configure("Side.TFrame", background=SIDEBAR)
        style.configure("Console.TFrame", background=CONSOLE)
        style.configure("Line.TFrame", background=BORDER)
        style.configure("Chip.TFrame", background=HOVER)
        style.configure("Chip.TLabel", background=HOVER)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Brand.TLabel", background=SIDEBAR, foreground=TEXT, font=(family, 13, "bold"))
        style.configure("SideNote.TLabel", background=SIDEBAR, foreground=FAINT, font=(family, 9))
        style.configure("Heading.TLabel", font=(family, 14, "bold"))
        style.configure("Setting.TLabel", font=self.bold)
        style.configure("Unset.TLabel", font=self.bold, foreground=MUTED)
        style.configure("Caption.TLabel", foreground=FAINT, font=(family, 8, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Faint.TLabel", foreground=FAINT)
        style.configure("Link.TLabel", foreground=ACCENT)
        style.configure("Notice.TLabel", background="#3a2f12", foreground=WARN)
        style.configure("Help.TLabel", foreground=FAINT, font=(family, 9))
        style.configure("ConsoleFaint.TLabel", background=CONSOLE, foreground=FAINT)
        # Method cards
        style.configure("ChipFaint.TLabel", background=HOVER, foreground=MUTED, font=self.small)
        style.configure("Milk.TLabel", foreground=MUTED, font=(family, 10, "italic"))
        style.configure("MilkFaint.TLabel", foreground=FAINT, font=self.small)
        style.configure("Out.TFrame", background="#1f3a2c")
        style.configure("Out.TLabel", background="#1f3a2c", foreground=GOOD, font=self.bold)
        style.configure("OutFaint.TLabel", background="#1f3a2c", foreground=MUTED)
        style.configure("Operator.TLabel", foreground=FAINT, font=(family, 14, "bold"))
        style.configure("Margin.TLabel", font=(family, 11, "bold"))
        style.configure("Flag.TLabel", foreground=WARN, font=(family, 9))
        style.configure("Warn.TLabel", foreground=WARN, font=(family, 9))
        style.configure("Small.TLabel", foreground=FAINT, font=(family, 9))

        for name in ("TEntry", "TCombobox"):
            style.configure(name, fieldbackground=FIELD, bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD,
                            padding=(6, 4), arrowsize=12)
            style.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", FIELD)])
        style.map("TEntry", bordercolor=[("focus", ACCENT), ("hover", FAINT)])
        for name in ("Chip.TEntry", "Small.TEntry", "Name.TEntry"):
            style.configure(name, padding=(4, 2))
            style.map(name, bordercolor=[("focus", ACCENT), ("hover", FAINT)], lightcolor=[("focus", FIELD)])
        style.configure("Name.TEntry", fieldbackground=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.map("Name.TEntry", fieldbackground=[("focus", FIELD), ("hover", FIELD)],
                  bordercolor=[("focus", ACCENT), ("hover", FAINT)], lightcolor=[("focus", FIELD), ("hover", FIELD)])
        # A production method's key: the name field's look in the key's faint color
        style.configure("Key.TEntry", fieldbackground=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG, foreground=FAINT)
        style.map("Key.TEntry", fieldbackground=[("focus", FIELD), ("hover", FIELD)], foreground=[("focus", TEXT)],
                  bordercolor=[("focus", ACCENT), ("hover", FAINT)], lightcolor=[("focus", FIELD), ("hover", FIELD)])
        style.configure("SlotName.TEntry", padding=(4, 2), fieldbackground=SLOT_BG, bordercolor=SLOT_BG,
                        lightcolor=SLOT_BG, darkcolor=SLOT_BG)
        style.map("SlotName.TEntry", fieldbackground=[("focus", FIELD), ("hover", FIELD)],
                  bordercolor=[("focus", ACCENT), ("hover", FAINT)], lightcolor=[("focus", FIELD), ("hover", FIELD)])
        style.configure("Small.TCombobox", padding=(4, 2))
        style.configure("TCombobox", background=FIELD, arrowcolor=MUTED)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)],
                  background=[("active", HOVER), ("readonly", FIELD)], bordercolor=[("focus", ACCENT)])
        style.configure("Add.TCombobox", fieldbackground=BG, background=BG, bordercolor=BORDER, lightcolor=BG, darkcolor=BG)
        style.map("Add.TCombobox", fieldbackground=[("readonly", BG)], foreground=[("readonly", ACCENT)],
                  selectbackground=[("readonly", BG)], selectforeground=[("readonly", ACCENT)],
                  background=[("active", FIELD), ("readonly", BG)])
        style.configure("TCheckbutton", indicatorbackground=FIELD, indicatorforeground="#ffffff", indicatorrelief="flat",
                        indicatormargin=(0, 0, 8, 0), upperbordercolor=BORDER, lowerbordercolor=BORDER)
        style.map("TCheckbutton", indicatorbackground=[("selected", ACCENT)], background=[("active", BG)])
        style.configure("Console.TCheckbutton", background=CONSOLE, foreground=MUTED)
        style.map("Console.TCheckbutton", indicatorbackground=[("selected", ACCENT)], background=[("active", CONSOLE)])

        style.configure("Side.Treeview", background=SIDEBAR, fieldbackground=SIDEBAR, foreground=MUTED,
                        borderwidth=0, rowheight=28, indent=14)
        style.map("Side.Treeview", background=[("selected", SELECTED)], foreground=[("selected", "#ffffff")])
        style.layout("Side.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Treeview.Item", padding=(2, 0))

        for orient in ("Vertical", "Horizontal"):
            style.layout(f"{orient}.TScrollbar", [(f"{orient}.Scrollbar.trough", {"sticky": "nswe", "children": [
                (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("TScrollbar", troughcolor=BG, background=BORDER, bordercolor=BG, lightcolor=BORDER,
                        darkcolor=BORDER, arrowsize=9, gripcount=0)
        style.map("TScrollbar", background=[("active", FAINT)], lightcolor=[("active", FAINT)], darkcolor=[("active", FAINT)])
        style.configure("TSeparator", background=BORDER)
        style.configure("TPanedwindow", background=BORDER)
        style.configure("Sash", sashthickness=3, gripcount=0, background=BORDER, lightcolor=BORDER, bordercolor=BORDER)

        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", SELECTED)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.root.option_add("*TCombobox*Listbox.font", base)

    def dark_list(self, widget):
        widget.configure(background=FIELD, foreground=TEXT, selectbackground=SELECTED, selectforeground="#ffffff",
                         highlightthickness=0, borderwidth=0)

    def dark_text(self, widget, background):
        widget.configure(background=background, foreground=TEXT, insertbackground=TEXT, selectbackground=SELECTED,
                         highlightthickness=0, borderwidth=0, padx=10, pady=8)

    def dark_title_bar(self, window):
        if os.name != "nt":
            return
        try:
            import ctypes
            window.update_idletasks()
            handle = ctypes.windll.user32.GetParent(window.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(ctypes.c_int(1)), 4)
        except Exception:
            pass

    def problem(self, kind, value, trace):
        text = "".join(traceback.format_exception(kind, value, trace))
        log_error(text, f"{self.current.tool.title}, section {self.current.section_name}")
        messagebox.showerror("MnT Generators", f"{text[-1800:]}\nSaved in {ERROR_LOG}")

    def close(self):
        self.current.commit()
        if self.current.dirty:
            answer = messagebox.askyesnocancel(self.current.tool.title, self.current.close_question)
            if answer is None:
                return
            if answer and not self.current.finish_before_close():
                return
        self.root.destroy()


def main():
    tool = TOOLS.get(sys.argv[1] if len(sys.argv) > 1 else "")
    if tool is None:
        tk.Tk().withdraw()
        messagebox.showerror("MnT Generators", "Open MnT Provisions.bat or MnT Building Setup.bat in the tools folder.")
        return
    threading.excepthook = lambda error: log_error(
        "".join(traceback.format_exception(error.exc_type, error.exc_value, error.exc_traceback)), "background thread")
    try:
        App(tool).root.mainloop()
    except Exception:
        text = traceback.format_exc()
        log_error(text, tool.title)
        try:
            messagebox.showerror("MnT Generators", text[-2000:])
        except Exception:
            print(text)


if __name__ == "__main__":
    main()
