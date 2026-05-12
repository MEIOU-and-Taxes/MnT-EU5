#!/usr/bin/env python3
"""
MnT_generate_building_hooks.py — Estate-pays-building-maintenance codegen.

Scans vanilla EU5 + MnT building_types and production_methods, determines
which buildings should contribute to the MnT_epbm estate-maintenance system,
and writes out every piece of generated script the runtime needs.

────────────────────────────────────────────────────────────────────────────
PIPELINE OVERVIEW
────────────────────────────────────────────────────────────────────────────
The generator runs in eight stages:

  1. PARSE PRODUCTION METHODS
     Scans vanilla + mod production_methods/ files. Filters to qualifying
     PMs: those with goods inputs, no `no_upkeep = yes`, and no output
     goods. Builds a goods-per-PM map used for pricing at runtime.

  2. PARSE ALL BUILDINGS
     Scans vanilla + mod building_types/ directories. When a mod file has
     the same name as a vanilla file, the mod version completely replaces
     it. INJECT/REPLACE blocks from mod files are applied on top of
     vanilla building definitions. Records each building's estate
     assignment, PM references, source file, and existing hook state.

  3. CLASSIFY
     Matches buildings to qualifying PMs. Skips fort-granting buildings
     (crown-paid via separate system). Warns about estate-assigned
     buildings that have no qualifying maintenance PM. Outputs the
     qualifying building list and a map of unique goods profiles.

  4. REWRITE MOD FILES IN-PLACE
     For each mod building file containing qualifying buildings, strips
     any previously-injected on_built/on_destroyed hooks, then re-injects
     fresh hooks. This is the only destructive step. Files are never
     modified if their hooks are already up to date.

  5. GENERATE INJECT/REPLACE FOR VANILLA-ONLY BUILDINGS
     Buildings that live in files the mod doesn't replace get INJECT
     blocks (hook-only additions) or REPLACE blocks (full building
     definition with hooks, used when the building already has hooks
     that need updating or when the PM was renamed to avoid collision).

  6. GENERATE INTERNATIONAL ORGANIZATIONS (IOs)
     One IO definition per unique PM goods profile. IOs are abused as
     variable-map containers — each IO holds a goods→quantity map that
     the runtime prices against the local market. Buildings that share
     identical goods profiles share a single IO.

  7. GENERATE INIT EFFECTS
     Writes `MnT_epbm_stamp_globals`: called once at game start (and on
     save-game load). Creates all IOs, populates the global
     `MnT_epbm_profiles` map (PM → IO scope), and registers estate-
     assigned buildings in `MnT_epbm_estate_map` (building_type → estate).

  8. GENERATE BIASES + LOCALIZATION
     Engine mandates one io_opinion bias entry per IO (even if neutral).
     Localization provides empty/placeholder strings for IO names and
     any PMs renamed during the REPLACE step to avoid name collisions.

────────────────────────────────────────────────────────────────────────────
RUNTIME CONTEXT
────────────────────────────────────────────────────────────────────────────
The generated artifacts feed the EPBM runtime (MnT_epbm_*.txt scripts):

  - on_built / on_destroyed hooks keep per-location building lists current
    as the player builds or demolishes. These lists drive the monthly
    maintenance calculation without needing to iterate every building in
    the country each tick.

  - The IO goods maps let the calculator price each building's maintenance
    against its local market. Goods prices vary by market, so the same
    building type costs different amounts in different trade nodes.

  - The estate map routes estate-assigned buildings to their owning
    estate's cost bucket. Non-estate buildings go to a shared pool that
    is split by estate power.

  - The monthly flow is: snapshot last month's values for display →
    recalculate all building costs → charge each estate via
    add_gold_to_estate. Player recalcs monthly; AI recalcs yearly
    with monthly charges using cached rates.

────────────────────────────────────────────────────────────────────────────
CONFIGURATION
────────────────────────────────────────────────────────────────────────────
All tunables live in `MnT_epbm_generator_config.py` next to this script —
edit that file, not this one. The generator imports it as a module.

────────────────────────────────────────────────────────────────────────────
SAFETY
────────────────────────────────────────────────────────────────────────────
This script is DESTRUCTIVE. It rewrites MnT's own building_types/*.txt in
place, which means any uncommitted edits in those files could be clobbered
if something goes wrong mid-run. Before running the generator:

  - Commit any in-flight changes to the MnT dev mod first.
  - The generator refuses to run if `git status` reports uncommitted changes
    inside MOD_IN_GAME/common/building_types (override: REQUIRE_CLEAN_GIT).
  - The generator prompts for interactive confirmation before rewriting any
    files (override: REQUIRE_CONFIRMATION, or set MNT_EPBM_CI=1 for CI).

If you ever need to hand-edit a building that the generator touches, MOVE
that building into a new .txt file first. The generator only rewrites files
that currently contain a qualifying building, so relocating one out of an
existing file takes that file off the generator's radar.
────────────────────────────────────────────────────────────────────────────
"""

import os
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

# Import the user-editable configuration. Must sit next to this script.
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
import MnT_epbm_generator_config as cfg  # noqa: E402


# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

# Keys that appear inside production_method blocks but are NOT goods inputs.
# Anything else in a PM block is treated as a good → quantity pair.
PM_META_KEYS = {"category", "no_upkeep", "potential", "produced", "output"}

# Filenames skipped when scanning building_types directories. These are
# vanilla's own admin/obsolescence lists that don't define real buildings.
SKIP_FILES = {"readme.txt", "__readme.txt", "00_unique_buildings_to_make_obsolete.txt"}

# Prefix resolved from config at import time. Every generated identifier and
# filename is derived from this via `_p(name)` → `f"{PREFIX}_{name}"`.
PREFIX = cfg.PREFIX

# Header banner for fully-generated files (IOs, biases, init effects,
# INJECT/REPLACE, loc). One line so diffs stay readable.
GENERATED_HEADER_LINES = [
    "# AUTO-GENERATED by tools/MnT_epbm_generator/. Hand edits will be lost on the next run.",
]

GENERATED_LOC_HEADER_LINES = [
    "# AUTO-GENERATED by tools/MnT_epbm_generator/ — do not edit.",
]

# Distinctive substring that marks a building_types file as touched by the
# generator. Used to detect the header on reruns so we don't double-prepend.
INPLACE_HEADER_MARKER = "MnT EPBM: on_built / on_destroyed hooks in this file are maintained by"
INPLACE_HEADER_LINES = [
    f"# {INPLACE_HEADER_MARKER}",
    "# tools/MnT_epbm_generator/. After adding a building or a maintenance",
    "# production method, commit your changes and re-run:",
    "#   python3 tools/MnT_epbm_generator/MnT_generate_building_hooks.py",
    "",
]


# ═════════════════════════════════════════════════════════════════════════
# Check mode
# ═════════════════════════════════════════════════════════════════════════
# When MNT_EPBM_CHECK is set in the environment, the generator runs its
# entire pipeline without touching the filesystem. Each would-be write is
# compared to the file currently on disk; any mismatch (content, missing
# file, or stale file that should no longer exist) is collected into the
# module-level _check_diffs list. main() reports those diffs and exits
# non-zero so CI can fail the job.
#
# Check mode is idempotency as a first-class contract: if `git diff` would
# be non-empty after a real run, check mode surfaces exactly the same set
# of paths.

CHECK_MODE = False
_check_diffs = []  # list of (path, kind) — kind ∈ {'changed', 'missing', 'stale'}


def _is_check_mode():
    return CHECK_MODE


def _record_diff(path, kind):
    _check_diffs.append((Path(path), kind))


def _write_output(path, content, encoding="utf-8-sig"):
    """Write `content` to `path`, or in check mode compare and record the
    diff. Creates parent directories as needed in write mode; in check mode
    we never touch the filesystem at all."""
    path = Path(path)
    if _is_check_mode():
        if not path.exists():
            _record_diff(path, 'missing')
            return
        try:
            current = path.read_text(encoding=encoding)
        except OSError:
            _record_diff(path, 'missing')
            return
        if current != content:
            _record_diff(path, 'changed')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


def _delete_stale(path):
    """Delete a stale generator-output file, or in check mode record it as
    a diff (the tree has a file the generator would no longer produce)."""
    path = Path(path)
    if _is_check_mode():
        if path.exists():
            _record_diff(path, 'stale')
        return
    if path.exists():
        path.unlink()


def _p(name):
    """Prefix a name with the configured PREFIX (e.g. _p('buildings') →
    'MnT_epbm_buildings'). Every generated identifier flows through this
    helper so the prefix is consistent and changeable from one place."""
    return f"{PREFIX}_{name}"


# ═════════════════════════════════════════════════════════════════════════
# Paradox script parser
# ═════════════════════════════════════════════════════════════════════════
# Hand-rolled tokenizer + recursive-descent parser for Paradox script files.
# We only need a subset of the grammar (key = value, nested blocks, bare
# list values, # comments, quoted strings), which lets us stay dependency-
# free and fast on the ~200 building_type files we feed it.
# ═════════════════════════════════════════════════════════════════════════

def strip_bom(text):
    """Drop the BOM if present; Paradox files are UTF-8 with BOM."""
    return text.lstrip("\ufeff")


def strip_comments(text):
    """Remove `#`-to-end-of-line comments while respecting quoted strings
    (a `#` inside a quoted string is a literal, not a comment start)."""
    lines = []
    for line in text.split("\n"):
        in_quote = False
        result = []
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif ch == '#' and not in_quote:
                break
            result.append(ch)
        lines.append("".join(result))
    return "\n".join(lines)


def tokenize(text):
    """Yield tokens from Paradox script source.

    Token types: identifiers, numbers, quoted strings (unwrapped), braces,
    and `=`. Whitespace is a separator only. Comments are stripped first.
    """
    text = strip_bom(text)
    text = strip_comments(text)
    i = 0
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
            continue
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == '\\':
                    j += 1
                j += 1
            yield text[i + 1:j]
            i = j + 1
            continue
        if text[i] in '{}=':
            yield text[i]
            i += 1
            continue
        j = i
        while j < n and text[j] not in " \t\r\n{}=\"":
            j += 1
        yield text[i:j]
        i = j


def parse_block(tokens, idx):
    """Parse a `{ ... }` block starting at `tokens[idx]` (which must be
    `{`). Returns `(OrderedDict, next_idx)`. Duplicate keys collapse into a
    list (common for `possible_production_methods` etc.)."""
    assert tokens[idx] == '{', f"Expected '{{' at index {idx}, got '{tokens[idx]}'"
    idx += 1
    result = OrderedDict()
    while idx < len(tokens) and tokens[idx] != '}':
        key = tokens[idx]
        idx += 1
        if idx < len(tokens) and tokens[idx] == '=':
            idx += 1
            if idx < len(tokens) and tokens[idx] == '{':
                val, idx = parse_block(tokens, idx)
            else:
                val = tokens[idx]
                idx += 1
        else:
            # Bare value with no `=`, e.g. list entries inside
            # possible_production_methods = { pm_name_a pm_name_b }.
            val = True
            if key in result:
                if isinstance(result[key], list):
                    result[key].append(val)
                else:
                    result[key] = [result[key], val]
                continue
            result[key] = val
            continue
        if key in result:
            if isinstance(result[key], list):
                result[key].append(val)
            else:
                result[key] = [result[key], val]
        else:
            result[key] = val
    if idx < len(tokens):
        idx += 1  # consume the closing '}'
    return result, idx


def parse_file(filepath):
    """Parse a Paradox script file into a dict of top-level definitions."""
    text = filepath.read_text(encoding="utf-8-sig")
    toks = list(tokenize(text))
    result = OrderedDict()
    idx = 0
    while idx < len(toks):
        key = toks[idx]
        idx += 1
        if idx < len(toks) and toks[idx] == '=':
            idx += 1
            if idx < len(toks) and toks[idx] == '{':
                val, idx = parse_block(toks, idx)
            else:
                val = toks[idx]
                idx += 1
        else:
            val = True
        if key in result:
            if isinstance(result[key], list):
                result[key].append(val)
            else:
                result[key] = [result[key], val]
        else:
            result[key] = val
    return result


# ═════════════════════════════════════════════════════════════════════════
# Production methods parser
# ═════════════════════════════════════════════════════════════════════════
# We read vanilla's `unsorted_building_inputs.txt` plus any MnT production
# method files. Inline `unique_production_methods` defined inside building_type
# blocks are handled separately (see `_parse_building_block`).
# ═════════════════════════════════════════════════════════════════════════

def parse_production_methods(vanilla_dir, mod_dir=None):
    """Return a dict pm_name → { goods, no_upkeep, has_output, has_potential }."""
    pms = {}
    vanilla_pm = vanilla_dir / "common" / "production_methods" / "unsorted_building_inputs.txt"
    if vanilla_pm.exists():
        pms.update(_parse_pm_file(vanilla_pm))
    if mod_dir:
        mod_pm_dir = mod_dir / "common" / "production_methods"
        if mod_pm_dir.exists():
            for mod_pm in sorted(mod_pm_dir.glob("*.txt")):
                pms.update(_parse_pm_file(mod_pm))
    return pms


def _parse_pm_file(filepath):
    """Parse a single production-methods file into the internal schema."""
    data = parse_file(filepath)
    pms = {}
    for name, block in data.items():
        if not isinstance(block, dict):
            continue
        pm = {
            'goods': OrderedDict(),
            'no_upkeep': 'no_upkeep' in block and block['no_upkeep'] == 'yes',
            'has_output': 'produced' in block or 'output' in block,
            'has_potential': 'potential' in block,
            'is_maintenance': block.get('category') == 'building_maintenance',
            'produced_good': block.get('produced'),
        }
        for k, v in block.items():
            if k not in PM_META_KEYS and isinstance(v, str):
                try:
                    pm['goods'][k] = float(v)
                except ValueError:
                    pass
        pms[name] = pm
    return pms


# ═════════════════════════════════════════════════════════════════════════
# Building types parser (with mod overlay)
# ═════════════════════════════════════════════════════════════════════════
# Vanilla ships building definitions split across multiple .txt files. Mods
# layer on top using three mechanisms:
#   - Full file replacement: a mod file with the same name as a vanilla
#     file shadows the vanilla file entirely.
#   - `INJECT:name = { ... }` blocks: deep-merge into an existing building.
#   - `REPLACE:name = { ... }` blocks: swap a single building definition.
# We honour all three so we can ingest whatever MnT (or a future overlay)
# decides to do — and so the resulting classification reflects what the
# game will actually see at load time.
# ═════════════════════════════════════════════════════════════════════════

def _parse_building_block(bname, block, source_file):
    """Convert a raw parsed building block into our internal schema."""
    b = {
        'file': source_file,
        'estate': block.get('estate'),
        'is_foreign': block.get('is_foreign') == 'yes',
        'has_on_built': 'on_built' in block,
        'has_on_destroyed': 'on_destroyed' in block,
        'possible_pms': [],
        'unique_pms': OrderedDict(),
        'raw': block,
    }
    ppm = block.get('possible_production_methods')
    if isinstance(ppm, dict):
        b['possible_pms'] = list(ppm.keys())
    elif isinstance(ppm, list):
        b['possible_pms'] = ppm

    upm = block.get('unique_production_methods')
    if isinstance(upm, dict):
        for pm_name, pm_block in upm.items():
            if isinstance(pm_block, dict):
                goods = OrderedDict()
                for k, v in pm_block.items():
                    if k not in PM_META_KEYS and isinstance(v, str):
                        try:
                            goods[k] = float(v)
                        except ValueError:
                            pass
                b['unique_pms'][pm_name] = {
                    'goods': goods,
                    'has_output': 'produced' in pm_block or 'output' in pm_block,
                    'no_upkeep': pm_block.get('no_upkeep') == 'yes',
                    'is_maintenance': pm_block.get('category') == 'building_maintenance',
                    'produced_good': pm_block.get('produced'),
                }
    return b


def _scan_building_dir(directory):
    """Scan a building_types directory. Returns:
      - buildings: dict of normal building definitions (no prefix)
      - injects: list of (bname, block, source_file) for INJECT: keys
      - replaces: list of (bname, block, source_file) for REPLACE: keys
      - files_present: set of filenames encountered (used to detect full
        file replacement when overlaying a mod on top of vanilla).

    Skips this generator's own output files (`{PREFIX}_generated_inject.txt`
    and `{PREFIX}_generated_replace.txt`). If we didn't, a second run would
    re-ingest the first run's INJECT/REPLACE blocks and flip every INJECT
    building into the REPLACE bucket, corrupting classification and making
    the script non-idempotent.
    """
    buildings = OrderedDict()
    injects = []
    replaces = []
    files_present = set()

    # Names of our own generated files — skipped so the parser never reads
    # its own output. Derived from PREFIX so changing the prefix config
    # keeps the skip list in sync automatically.
    generator_outputs = {
        f"{PREFIX}_generated_inject.txt",
        f"{PREFIX}_generated_replace.txt",
    }

    for f in sorted(directory.iterdir()):
        if f.name in generator_outputs:
            continue
        if f.name.lower() in SKIP_FILES or not f.name.endswith(".txt"):
            continue
        files_present.add(f.name)
        data = parse_file(f)
        for key, block in data.items():
            if not isinstance(block, dict):
                continue
            if key.startswith("INJECT:"):
                injects.append((key[7:], block, f))
            elif key.startswith("REPLACE:"):
                replaces.append((key[8:], block, f))
            else:
                buildings[key] = _parse_building_block(key, block, f)

    return buildings, injects, replaces, files_present


def _apply_inject(building, inject_block):
    """Deep-merge an INJECT: block onto an existing building."""
    block = inject_block
    raw = building['raw']

    for k, v in block.items():
        if k == 'possible_production_methods' and isinstance(v, dict):
            ppm = raw.get('possible_production_methods', OrderedDict())
            if not isinstance(ppm, dict):
                ppm = OrderedDict()
            ppm.update(v)
            raw['possible_production_methods'] = ppm
            building['possible_pms'] = list(ppm.keys())
        elif k == 'unique_production_methods' and isinstance(v, dict):
            upm = raw.get('unique_production_methods', OrderedDict())
            if not isinstance(upm, dict):
                upm = OrderedDict()
            upm.update(v)
            raw['unique_production_methods'] = upm
            for pm_name, pm_block in v.items():
                if isinstance(pm_block, dict):
                    goods = OrderedDict()
                    for gk, gv in pm_block.items():
                        if gk not in PM_META_KEYS and isinstance(gv, str):
                            try:
                                goods[gk] = float(gv)
                            except ValueError:
                                pass
                    building['unique_pms'][pm_name] = {
                        'goods': goods,
                        'has_output': 'produced' in pm_block or 'output' in pm_block,
                        'no_upkeep': pm_block.get('no_upkeep') == 'yes',
                        'is_maintenance': pm_block.get('category') == 'building_maintenance',
                        'produced_good': pm_block.get('produced'),
                    }
        elif k == 'on_built':
            building['has_on_built'] = True
            raw['on_built'] = v
        elif k == 'on_destroyed':
            building['has_on_destroyed'] = True
            raw['on_destroyed'] = v
        elif k == 'estate':
            building['estate'] = v
            raw['estate'] = v
        else:
            raw[k] = v


def parse_all_buildings(vanilla_dir, mod_dir=None):
    """Parse every building_types file from vanilla, optionally overlaying
    a mod. The overlay rules mirror how the engine loads mods at runtime:
      1. Parse vanilla.
      2. For any file in the mod that shares a name with a vanilla file,
         drop the vanilla buildings from that file (mod file replaces it
         entirely) and replace them with the mod's buildings.
      3. Apply mod INJECT: directives on the merged pool.
      4. Apply mod REPLACE: directives on the merged pool.
    """
    vanilla_bt_dir = vanilla_dir / "common" / "building_types"
    if not vanilla_bt_dir.exists():
        print(f"ERROR: vanilla building_types directory not found: {vanilla_bt_dir}")
        sys.exit(1)

    vanilla_buildings, vanilla_injects, vanilla_replaces, vanilla_files = _scan_building_dir(vanilla_bt_dir)
    buildings = vanilla_buildings

    if mod_dir:
        mod_bt_dir = mod_dir / "common" / "building_types"
        if mod_bt_dir.exists():
            mod_buildings, mod_injects, mod_replaces, mod_files = _scan_building_dir(mod_bt_dir)

            replaced_files = vanilla_files & mod_files
            if replaced_files:
                buildings = OrderedDict(
                    (k, v) for k, v in buildings.items()
                    if v['file'].name not in replaced_files
                )
                print(f"  mod replaces {len(replaced_files)} vanilla file(s): {', '.join(sorted(replaced_files))}")

            buildings.update(mod_buildings)

            for bname, block, source in mod_injects:
                if bname in buildings:
                    _apply_inject(buildings[bname], block)
                else:
                    print(f"  WARNING: INJECT target '{bname}' not found, skipping")

            for bname, block, source in mod_replaces:
                buildings[bname] = _parse_building_block(bname, block, source)
        else:
            print(f"  no building_types directory in mod, using vanilla only")

    return buildings


# ═════════════════════════════════════════════════════════════════════════
# Classification
# ═════════════════════════════════════════════════════════════════════════
# Two things come out of this pass:
#
#   1. all_pm_goods — catalog of every maintenance production method we find
#      across vanilla + mod, keyed by PM name. Each entry is the ordered
#      goods dict (good -> per-level amount). One IO gets generated per
#      entry, and the runtime `MnT_epbm_profiles` map lands the building's
#      active PM into the right IO.
#
#   2. qualifying — every building that has at least one PM in that catalog.
#      These are the buildings we hook with on_built/on_destroyed and add
#      to the init dispatch. We don't pre-assign a single PM per building —
#      runtime picks dynamically via ordered_production_method_of_building.
#
# A PM qualifies as maintenance when it has goods inputs and is not flagged
# no_upkeep. External PMs from production_methods/*.txt are assumed to be
# maintenance when they have no output. Inline unique_production_methods always
# need `category = building_maintenance`. The only output-bearing upkeep PMs
# cataloged here are maintenance PMs that produce credit, because those still
# have chargeable inputs that EPBM must price.
# ═════════════════════════════════════════════════════════════════════════

def _output_is_compatible_with_epbm_upkeep(pm):
    if not pm.get('has_output', False):
        return True
    return pm.get('is_maintenance', False) and pm.get('produced_good') == 'credit'

def _grants_fort_level(obj):
    """Recursively scan a parsed building block for any `fort_level = X`
    entry. Buildings that grant fort_level are fortifications — those are
    always crown-paid, never charged to estates, so classify() drops them
    from the qualifying set regardless of whether they have a maintenance
    PM in the catalog."""
    if isinstance(obj, dict):
        if 'fort_level' in obj:
            return True
        for v in obj.values():
            if _grants_fort_level(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _grants_fort_level(item):
                return True
    return False


def classify(buildings, pms):
    """Return `(qualifying, all_pm_goods)` where `qualifying` is a list of
    `(bname, is_foreign, estate)` tuples and `all_pm_goods` maps PM name →
    ordered goods dict."""
    all_pm_goods = OrderedDict()

    # Pass 1a: catalog every external/shared maintenance PM
    for pm_name, pm in pms.items():
        if pm['no_upkeep']:
            continue
        if not pm['goods']:
            continue
        if not _output_is_compatible_with_epbm_upkeep(pm):
            continue
        all_pm_goods[pm_name] = pm['goods']

    # Pass 1b: catalog every inline unique maintenance PM (MnT's preferred
    # style). Inline definitions clobber externals with the same name, which
    # matches how the engine merges overrides at load time.
    for bname, b in buildings.items():
        for pm_name, pm_data in b['unique_pms'].items():
            if not pm_data.get('is_maintenance', False):
                continue
            if pm_data.get('no_upkeep', False):
                continue
            if not _output_is_compatible_with_epbm_upkeep(pm_data):
                continue
            if not pm_data['goods']:
                continue
            all_pm_goods[pm_name] = pm_data['goods']

    # Pass 2: any building that references at least one catalog PM is
    # qualifying — that's the set we hook and put into the init dispatch.
    # Fortification buildings are skipped even if they have a maintenance
    # PM; the crown pays for those directly.
    qualifying = []
    fort_count = 0
    for bname, b in buildings.items():
        has_tracked = False
        for pm_name in b['possible_pms']:
            if pm_name in all_pm_goods:
                has_tracked = True
                break
        if not has_tracked:
            for pm_name in b['unique_pms']:
                if pm_name in all_pm_goods:
                    has_tracked = True
                    break
        if not has_tracked:
            continue
        if _grants_fort_level(b['raw']):
            fort_count += 1
            continue
        qualifying.append((bname, b['is_foreign'], b['estate']))

    if fort_count > 0:
        print(f"  skipped {fort_count} fort-granting building(s) (crown-paid)")

    qualifying_names = {q[0] for q in qualifying}
    estate_no_pm = []
    for bname, b in buildings.items():
        if b['estate'] is not None and bname not in qualifying_names:
            estate_no_pm.append((bname, b['estate']))
    if estate_no_pm:
        print(f"\n  WARNING: {len(estate_no_pm)} estate building(s) have no qualifying maintenance PM:")
        for bname, estate in sorted(estate_no_pm):
            print(f"    {bname} (estate={estate})")
        print()

    return qualifying, all_pm_goods


# ═════════════════════════════════════════════════════════════════════════
# In-place hook injection (MnT building_types files)
# ═════════════════════════════════════════════════════════════════════════
# For every qualifying building whose source file lives inside MOD_IN_GAME,
# we rewrite that file in place to add (or extend) the on_built and
# on_destroyed blocks so they call MnT_epbm_on_building_built /
# MnT_epbm_on_building_destroyed. The rewrite is idempotent: we strip any
# previously-injected hook lines first so reruns are stable.
#
# Vanilla-only buildings don't get in-place treatment — we can't write into
# the vanilla install — so they go through the INJECT/REPLACE path instead.
# ═════════════════════════════════════════════════════════════════════════

def _strip_generator_injected_lines(text):
    """Remove every previously-injected hook line from a file. Detection is
    keyed on the current PREFIX so renaming PREFIX leaves old hooks
    untouched (intentional — lets you migrate between prefix schemes)."""
    built_marker = _p('on_building_built')
    destroyed_marker = _p('on_building_destroyed')
    list_name = _p('buildings')

    if built_marker not in text and destroyed_marker not in text:
        return text

    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Drop pairs: `location = { add_to_variable_list ... }` + marker call.
        if list_name in stripped and 'add_to_variable_list' in stripped:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and built_marker in lines[j]:
                i = j + 1
                continue

        if list_name in stripped and 'remove_list_variable' in stripped:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and destroyed_marker in lines[j]:
                i = j + 1
                continue

        # Drop standalone marker calls (no paired list op).
        if stripped == f'{built_marker} = yes' or stripped == f'{destroyed_marker} = yes':
            i += 1
            continue

        result.append(line)
        i += 1

    text = '\n'.join(result)
    text = _remove_empty_hook_blocks(text)
    return text


def _remove_empty_hook_blocks(text):
    """Drop `on_built = { }` / `on_destroyed = { }` blocks that contain only
    whitespace after stripping. Without this, repeated runs would leave
    behind empty shells."""
    for hook in ('on_built', 'on_destroyed'):
        pattern = re.compile(
            r'\n[ \t]*' + hook + r'\s*=\s*\{[ \t]*\n([ \t]*\n)*[ \t]*\}',
        )
        text = pattern.sub('', text)
    return text


def _find_building_bounds(text, building_name):
    """Find the (start, end) offsets of `building_name = { ... }` at the
    top level of `text`. Also accepts top-level INJECT:/REPLACE: wrappers.
    Returns None if not found."""
    pattern = re.compile(
        r'^((?:INJECT:|REPLACE:)?' + re.escape(building_name) + r')\s*=\s*\{',
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return None
    start = match.start()
    brace_start = text.index('{', match.start())
    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return (start, i + 1)
        i += 1
    return None


def _inject_hook_into_building_text(building_text, has_on_built, has_on_destroyed):
    """Mutate a single building's text to add our on_built / on_destroyed
    hook lines. If a block already exists, inject before its closing brace;
    otherwise add a new block just above the building's outer `}`."""
    list_name = _p('buildings')
    add_code_lines = (
        f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}\n"
        f"\t\t{_p('on_building_built')} = yes\n"
    )
    remove_code_lines = (
        f"\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}\n"
        f"\t\t{_p('on_building_destroyed')} = yes\n"
    )

    text = building_text

    # ---- on_built ----
    if has_on_built:
        on_built_pattern = re.compile(r'on_built\s*=\s*\{')
        match = on_built_pattern.search(text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        text = text[:i] + add_code_lines + "\t" + text[i:]
                        break
                i += 1
    else:
        last_brace = text.rindex('}')
        on_built_block = f"\ton_built = {{\n{add_code_lines}\t}}\n"
        text = text[:last_brace] + on_built_block + text[last_brace:]

    # ---- on_destroyed ----
    if has_on_destroyed:
        on_destroyed_pattern = re.compile(r'on_destroyed\s*=\s*\{')
        match = on_destroyed_pattern.search(text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        text = text[:i] + remove_code_lines + "\t" + text[i:]
                        break
                i += 1
    else:
        last_brace = text.rindex('}')
        on_destroyed_block = f"\ton_destroyed = {{\n{remove_code_lines}\t}}\n"
        text = text[:last_brace] + on_destroyed_block + text[last_brace:]

    return text


def _ensure_inplace_header(text):
    """Add (or keep) the top-of-file warning header that tells humans the
    file is partially generated. Idempotent — detects the marker line."""
    if INPLACE_HEADER_MARKER in text:
        return text
    header = '\n'.join(INPLACE_HEADER_LINES)
    # If the file already starts with a BOM we inserted earlier, preserve it.
    if text.startswith('\ufeff'):
        return '\ufeff' + header + text[1:]
    return header + text


def _braces_balanced(text):
    """Belt-and-suspenders brace check. If the in-place rewrite desyncs the
    braces we want to catch it before overwriting the source file."""
    depth = 0
    in_quote = False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def apply_in_place(qualifying, buildings, mod_dir):
    """Rewrite MnT building files in place with hook injection. Returns
    `(modified_file_count, vanilla_only_qualifying)` where the second value
    lists qualifying buildings whose source files live in the vanilla
    install (those still need INJECT/REPLACE overrides)."""
    mod_bt_dir = mod_dir / "common" / "building_types"

    mod_buildings_by_file = {}
    vanilla_only = []

    for bname, is_foreign, estate in qualifying:
        if is_foreign:
            # Foreign buildings never live in a location scope, so they
            # don't need on_built / on_destroyed hooks at all — they are
            # iterated straight from country scope at calculation time.
            continue
        b = buildings[bname]
        filepath = b['file']
        try:
            filepath.relative_to(mod_bt_dir)
            mod_buildings_by_file.setdefault(filepath, []).append((bname, b))
        except ValueError:
            vanilla_only.append((bname, is_foreign, estate))

    if vanilla_only:
        print(f"  {len(vanilla_only)} building(s) from vanilla-only files (will generate INJECT/REPLACE)")

    modified_files = 0

    for filepath, bldg_list in sorted(mod_buildings_by_file.items(), key=lambda x: x[0].name):
        text = filepath.read_text(encoding="utf-8-sig")
        original = text

        # Step 1: strip any previously-injected hooks so the rewrite is
        # fully idempotent across reruns.
        text = _strip_generator_injected_lines(text)

        # Step 2: re-parse the stripped text to learn which buildings still
        # have hand-written on_built / on_destroyed blocks (so we inject
        # inside them instead of creating duplicates).
        stripped_toks = list(tokenize(text))
        stripped_blocks = {}
        idx = 0
        while idx < len(stripped_toks):
            key = stripped_toks[idx]
            idx += 1
            if idx < len(stripped_toks) and stripped_toks[idx] == '=':
                idx += 1
                if idx < len(stripped_toks) and stripped_toks[idx] == '{':
                    val, idx = parse_block(stripped_toks, idx)
                else:
                    val = stripped_toks[idx]
                    idx += 1
            else:
                val = True
            if isinstance(val, dict):
                stripped_blocks[key] = val

        # Step 3: inject hooks into each qualifying building in this file.
        for bname, b in bldg_list:
            bounds = _find_building_bounds(text, bname)
            if bounds is None:
                print(f"  WARNING: could not find '{bname}' in {filepath.name}, skipping")
                continue

            start, end = bounds
            building_text = text[start:end]

            block = (
                stripped_blocks.get(bname)
                or stripped_blocks.get(f"REPLACE:{bname}")
                or stripped_blocks.get(f"INJECT:{bname}")
                or {}
            )
            has_on_built = 'on_built' in block
            has_on_destroyed = 'on_destroyed' in block

            modified = _inject_hook_into_building_text(building_text, has_on_built, has_on_destroyed)
            text = text[:start] + modified + text[end:]

        # Step 4: add / refresh the "this file is partially generated" header.
        text = _ensure_inplace_header(text)

        # Step 5: validate brace balance before writing. This is a last-ditch
        # safety net in case a regex misfired on weird content.
        if not _braces_balanced(text):
            print(f"  ERROR: brace balance check failed for {filepath.name}, skipping write")
            continue

        if text != original:
            if _is_check_mode():
                _record_diff(filepath, 'changed')
                print(f"  {filepath.name}: would inject hooks into {len(bldg_list)} building(s)")
            else:
                filepath.write_text(text, encoding="utf-8-sig")
                modified_files += 1
                print(f"  {filepath.name}: injected hooks into {len(bldg_list)} building(s)")
        else:
            print(f"  {filepath.name}: no changes needed ({len(bldg_list)} already hooked)")

    return modified_files, vanilla_only


# ═════════════════════════════════════════════════════════════════════════
# Vanilla-only INJECT/REPLACE generation
# ═════════════════════════════════════════════════════════════════════════

def read_raw_building_text(filepath, building_name):
    """Return the raw source text for a named building (braces included),
    or None if not found."""
    text = filepath.read_text(encoding="utf-8-sig")
    text = strip_bom(text)
    pattern = re.compile(r'^(' + re.escape(building_name) + r')\s*=\s*\{', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    start = match.start()
    brace_start = text.index('{', match.start())
    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


def inject_on_built_hook(raw_text, building_name):
    """For REPLACE buildings: insert our hook into the raw source and rename
    any inline production-method names so they don't collide with vanilla.

    Returns (modified_text, renamed_pms) where renamed_pms is a list of the
    renamed inline PM names (without the prefix) — the caller uses this to
    emit loc aliases for each renamed PM.
    """
    list_name = _p('buildings')
    add_code = (
        f"\n\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}"
        f"\n\t\t{_p('on_building_built')} = yes"
    )
    remove_code = (
        f"\n\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}"
        f"\n\t\t{_p('on_building_destroyed')} = yes"
    )

    renamed_pms = []  # populated by rename_pm() below

    # Rename inline unique_production_methods to avoid duplicate PM errors
    # when the REPLACE: block is merged on top of the vanilla definition.
    # Each renamed PM gets collected so we can emit a loc alias for it.
    upm_pattern = re.compile(r'unique_production_methods\s*=\s*\{')
    upm_match = upm_pattern.search(raw_text)
    if upm_match:
        brace_start = upm_match.end() - 1
        depth = 0
        i = brace_start
        while i < len(raw_text):
            if raw_text[i] == '{':
                depth += 1
            elif raw_text[i] == '}':
                depth -= 1
                if depth == 0:
                    upm_end = i + 1
                    break
            i += 1
        else:
            upm_end = len(raw_text)
        upm_block = raw_text[upm_match.start():upm_end]
        pm_def_pattern = re.compile(r'(\t\t)(\w+)(\s*=\s*\{)')

        def rename_pm(m):
            name = m.group(2)
            if name in ('unique_production_methods', 'category', 'potential', 'no_upkeep'):
                return m.group(0)
            renamed_pms.append(name)
            return f"{m.group(1)}{_p(name)}{m.group(3)}"

        new_upm_block = pm_def_pattern.sub(rename_pm, upm_block)
        raw_text = raw_text[:upm_match.start()] + new_upm_block + raw_text[upm_end:]

    # Inject into existing on_built (or create it if absent).
    on_built_pattern = re.compile(r'(on_built\s*=\s*\{)')
    match = on_built_pattern.search(raw_text)
    if match:
        brace_start = match.end() - 1
        depth = 0
        i = brace_start
        while i < len(raw_text):
            if raw_text[i] == '{':
                depth += 1
            elif raw_text[i] == '}':
                depth -= 1
                if depth == 0:
                    raw_text = raw_text[:i] + add_code + "\n\t" + raw_text[i:]
                    break
            i += 1

    # Add on_destroyed (or inject into an existing one).
    if 'on_destroyed' not in raw_text:
        last_brace = raw_text.rindex('}')
        on_destroyed = f"\n\ton_destroyed = {{{remove_code}\n\t}}"
        raw_text = raw_text[:last_brace] + on_destroyed + "\n" + raw_text[last_brace:]
    else:
        on_destroyed_pattern = re.compile(r'(on_destroyed\s*=\s*\{)')
        match = on_destroyed_pattern.search(raw_text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(raw_text):
                if raw_text[i] == '{':
                    depth += 1
                elif raw_text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        raw_text = raw_text[:i] + remove_code + "\n\t" + raw_text[i:]
                        break
                i += 1

    return raw_text, renamed_pms


def generate_inject(qualifying, buildings):
    """Return the text of the INJECT: file for buildings that have no
    existing on_built/on_destroyed hooks in their vanilla definition."""
    lines = list(GENERATED_HEADER_LINES)
    lines.append("# INJECT overrides for vanilla-only buildings (no existing on_built).")
    lines.append("# To customize a building here: copy its full definition into a new .txt")
    lines.append("# in this directory. The next generator run will drop it from this file")
    lines.append("# and hook your copy in place instead.")
    lines.append("")

    for bname, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue
        if b['has_on_built'] or b['has_on_destroyed']:
            continue

        list_name = _p('buildings')
        lines.append(f"INJECT:{bname} = {{")
        lines.append(f"\ton_built = {{")
        lines.append(f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\t{_p('on_building_built')} = yes")
        lines.append(f"\t}}")
        lines.append(f"\ton_destroyed = {{")
        lines.append(f"\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\t{_p('on_building_destroyed')} = yes")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_replace(qualifying, buildings):
    """Return `(text, building_to_renamed_pms)` for the REPLACE: file.

    The second value maps building_name -> [renamed inline PM keys] for every
    REPLACE'd building whose inline `unique_production_methods` got prefixed.
    Callers feed that map into generate_replaced_pm_localization() to emit
    display-name aliases for the renamed PMs.
    """
    lines = list(GENERATED_HEADER_LINES)
    lines.append("# REPLACE overrides for vanilla-only buildings that already ship with")
    lines.append("# an on_built / on_destroyed block (a plain INJECT would leave theirs intact).")
    lines.append("#")
    lines.append("# NOTE: any `unique_production_methods` defined inline inside a REPLACE'd")
    lines.append("# building gets prefixed with `MnT_epbm_` in the block below — without the")
    lines.append("# rename the engine would see two PMs with the same name (vanilla + our")
    lines.append("# REPLACE) and error. Display names for the renamed PMs are generated")
    lines.append("# into MnT_epbm_generated_replaced_pms_l_english.yml, aliased back to")
    lines.append("# each building's loc key via `$<building>$` so the UI still shows the")
    lines.append("# original name.")
    lines.append("#")
    lines.append("# To customize a building here: copy its full definition into a new .txt")
    lines.append("# in this directory. The next generator run will drop it from this file")
    lines.append("# and hook your copy in place instead.")
    lines.append("")

    building_to_renamed_pms = OrderedDict()

    for bname, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue
        if not b['has_on_built'] and not b['has_on_destroyed']:
            continue

        raw = read_raw_building_text(b['file'], bname)
        if raw is None:
            lines.append(f"# WARNING: could not extract raw text for {bname}")
            lines.append("")
            continue

        modified, renamed_pms = inject_on_built_hook(raw, bname)
        if renamed_pms:
            building_to_renamed_pms[bname] = renamed_pms
        lines.append(f"# {bname} (REPLACE due to existing on_built hook)")
        lines.append(f"REPLACE:{modified}")
        lines.append("")

    return "\n".join(lines), building_to_renamed_pms


def generate_replaced_pm_localization(building_to_renamed_pms):
    """Emit loc aliases for inline PMs that generate_replace() renamed.

    Each entry reads `MnT_epbm_<pm_key>: "$<building>$"`, which tells the
    engine to render the renamed PM with the original building's display
    name. Returns the YAML text, or None if there are no renamed PMs
    (caller should then delete any stale version of the file)."""
    if not building_to_renamed_pms:
        return None

    lines = ["\ufeffl_english:"]
    for hdr in GENERATED_LOC_HEADER_LINES:
        lines.append(" " + hdr)
    lines.append(" # Aliases for inline PMs renamed by the REPLACE generator.")
    lines.append(" # See MnT_epbm_generated_replace.txt for why the rename happens.")

    for bname in sorted(building_to_renamed_pms.keys()):
        for pm_name in building_to_renamed_pms[bname]:
            lines.append(f' {_p(pm_name)}: "${bname}$"')

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# IO / bias / init-effect / localization generators
# ═════════════════════════════════════════════════════════════════════════

def generate_io_definitions(all_pm_goods):
    """One hidden international_organization per distinct PM goods profile.
    These IOs are used purely as variable-map containers at runtime."""
    lines = list(GENERATED_HEADER_LINES)
    lines.append("# Hidden international organizations used as variable map containers.")
    lines.append(f"# Each IO hosts a {_p('goods')} variable map for one PM profile.")
    lines.append("")

    for pm_name in sorted(all_pm_goods.keys()):
        io_name = f"{_p('pm')}_{pm_name}"
        lines.append(f"{io_name} = {{")
        lines.append("\tunique = yes")
        lines.append("\thas_target = no")
        lines.append("\tshow_on_diplomatic_map = no")
        lines.append("\tcreate_visible_trigger = { always = no }")
        lines.append("\tauto_disband_trigger = { always = no }")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_io_biases(all_pm_goods):
    """The engine requires an io_opinion bias per IO. These are all zero."""
    lines = list(GENERATED_HEADER_LINES)
    lines.append("# Opinion biases for hidden PM IOs (required by engine, value 0).")
    lines.append("")

    for pm_name in sorted(all_pm_goods.keys()):
        lines.append(f"io_opinion_{_p('pm')}_{pm_name} = {{")
        lines.append("\tvalue = 0")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_io_localization(all_pm_goods):
    """Empty loc entries for every IO so the engine doesn't spam warnings."""
    # YAML file with BOM + l_english header.
    lines = ["\ufeffl_english:"]
    for hdr in GENERATED_LOC_HEADER_LINES:
        lines.append(" " + hdr)

    for pm_name in sorted(all_pm_goods.keys()):
        io = f"{_p('pm')}_{pm_name}"
        lines.append(f' {io}: ""')
        lines.append(f' {io}_desc: ""')
        lines.append(f' diplomatic_status_{io}_name: ""')
        lines.append(f' diplomatic_status_{io}_tooltip: ""')
        lines.append(f' {io}_list_who_tt: ""')
        lines.append(f' io_opinion_{io}: ""')

    return "\n".join(lines)


def generate_init_effects(qualifying, all_pm_goods):
    """Emit `MnT_epbm_stamp_globals`. Called once at game start from the
    hand-written full_rebuild effect. Destroys any stale IO instances,
    recreates one per PM profile, populates each IO's goods variable-map,
    stamps the global production_method → IO lookup map plus the
    building_type → estate_type assignment map, and records a global
    list of all IOs for monthly cache clearing.

    The per-building init dispatch that used to live here has been
    replaced by a hand-written iterator inside MnT_epbm_initialize_location
    — it uses the same profile-map check as the calc path and no longer
    needs a generated building_type → add-to-list switch.
    """
    all_ios = _p('all_ios')
    profiles = _p('profiles')
    estate_map = _p('estate_map')

    lines = list(GENERATED_HEADER_LINES)
    lines.append("")

    # ── Part 1: stamp_globals ──
    lines.append("# Called once at game start: destroy stale IOs, clear globals, then")
    lines.append("# register one IO per maintenance PM via MnT_epbm_register_pm.")
    lines.append(f"{_p('stamp_globals')} = {{")
    lines.append("\t# destroy_international_organization requires country scope")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")
    lines.append("\t\tevery_in_global_list = {")
    lines.append(f"\t\t\tvariable = {all_ios}")
    lines.append("\t\t\tsave_temporary_scope_as = io_to_destroy")
    lines.append("\t\t\tprev = {")
    lines.append("\t\t\t\tdestroy_international_organization = { target = scope:io_to_destroy }")
    lines.append("\t\t\t}")
    lines.append("\t\t}")
    lines.append("\t}")
    lines.append(f"\tclear_global_variable_list = {all_ios}")
    lines.append(f"\tclear_global_variable_map = {profiles}")
    lines.append(f"\tclear_global_variable_map = {estate_map}")
    lines.append("")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")

    for pm_name in sorted(all_pm_goods.keys()):
        pm_goods = all_pm_goods[pm_name]
        lines.append(f"\t\t{_p('register_pm')} = {{")
        lines.append(f"\t\t\tpm = {pm_name}")
        lines.append(f"\t\t\tgoods_block = \"")
        for good, amount in pm_goods.items():
            lines.append(f"\t\t\t\t{_p('good')} = {{ good = {good} amount = {amount} }}")
        lines.append("\t\t\t\"")
        lines.append("\t\t}")

    lines.append("\t}")

    # Estate-assignment map: building_type → estate_type. Each entry means
    # "charge the full maintenance cost of this building to this estate".
    estate_buildings = [(b, e) for b, _, e in qualifying if e is not None]
    if estate_buildings:
        lines.append("")
        lines.append(f"\t# Estate-assigned buildings: charge full cost to the named estate")
        for bname, estate in sorted(estate_buildings):
            bt_ref = f"building_type:{bname}"
            lines.append(f"\tadd_to_global_variable_map = {{ name = {estate_map} key = {bt_ref} value = estate_type:{estate} }}")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Safety gates
# ═════════════════════════════════════════════════════════════════════════

def _resolve_vanilla_dir():
    """Return the first existing candidate from VANILLA_IN_GAME_CANDIDATES.
    Abort with a helpful message if none exist."""
    for candidate in cfg.VANILLA_IN_GAME_CANDIDATES:
        if candidate.exists() and (candidate / "common" / "building_types").exists():
            return candidate
    print("ERROR: No vanilla in_game/ directory found. Tried:")
    for candidate in cfg.VANILLA_IN_GAME_CANDIDATES:
        print(f"  - {candidate}")
    print("Edit VANILLA_IN_GAME_CANDIDATES in MnT_epbm_generator_config.py")
    print("to add your install path.")
    sys.exit(1)


def _check_git_clean(building_types_dir):
    """Refuse to run if there are uncommitted changes in the building_types
    directory. The in-place rewrite is destructive — unsaved hand edits
    must be committed (or stashed) first so recovery is one `git checkout`
    away."""
    if not cfg.REQUIRE_CLEAN_GIT:
        return
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain', '--', str(building_types_dir)],
            capture_output=True,
            text=True,
            cwd=str(building_types_dir),
            check=True,
        )
    except FileNotFoundError:
        print("WARNING: git not found on PATH — skipping clean-tree check.")
        return
    except subprocess.CalledProcessError as e:
        print(f"WARNING: git status failed ({e}) — skipping clean-tree check.")
        return

    # Filter out the generator's own output files — they aren't hand edits
    # and naturally appear as untracked/modified between runs. The safety
    # gate only cares about files the generator might clobber.
    generator_outputs = {
        f"{PREFIX}_generated_inject.txt",
        f"{PREFIX}_generated_replace.txt",
    }
    dirty_lines = []
    for raw_line in result.stdout.splitlines():
        # porcelain format: "XY path/to/file" (XY = two status chars + space)
        if len(raw_line) < 4:
            continue
        path = raw_line[3:]
        basename = Path(path).name
        if basename in generator_outputs:
            continue
        dirty_lines.append(raw_line)

    if dirty_lines:
        print("ERROR: uncommitted changes detected in:")
        print(f"       {building_types_dir}")
        print("")
        print("       The generator rewrites these files in place. Commit or stash")
        print("       your changes first (or set REQUIRE_CLEAN_GIT = False in")
        print("       MnT_epbm_generator_config.py if you know what you're doing).")
        print("")
        print("Dirty files:")
        for line in dirty_lines:
            print(f"  {line}")
        sys.exit(1)


def _confirm_destructive(building_types_dir):
    """Block on interactive y/N unless running in CI or the user has
    disabled REQUIRE_CONFIRMATION in the config."""
    if not cfg.REQUIRE_CONFIRMATION:
        return
    if os.environ.get("MNT_EPBM_CI"):
        print("MNT_EPBM_CI is set — skipping interactive confirmation.")
        return

    print("")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  WARNING: This run will REWRITE building files IN PLACE.        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"  Target directory: {building_types_dir}")
    print("")
    print("  Every .txt file in that directory that contains a qualifying")
    print("  building will be rewritten with on_built / on_destroyed hooks.")
    print("  Uncommitted hand edits inside those files may be lost if the")
    print("  generator misparses anything. Recovery is `git checkout --` on")
    print("  the affected files.")
    print("")
    try:
        answer = input("  Type 'yes' to continue, anything else to abort: ").strip().lower()
    except EOFError:
        answer = ""
    if answer != "yes":
        print("Aborted.")
        sys.exit(0)


# ═════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════

def main():
    # ── Check mode toggle ──
    # MNT_EPBM_CHECK=1 turns the generator into a read-only validator: it
    # runs the full pipeline, compares each proposed write against the
    # current file on disk, and exits non-zero if the tree is out of sync.
    # The git-clean and confirmation gates are skipped because nothing is
    # actually written.
    global CHECK_MODE
    CHECK_MODE = bool(os.environ.get("MNT_EPBM_CHECK"))
    _check_diffs.clear()

    # ── Resolve paths ──
    vanilla_dir = _resolve_vanilla_dir()
    mod_dir = Path(cfg.MOD_IN_GAME)
    output_dir = Path(cfg.OUTPUT_ROOT)

    if not mod_dir.exists():
        print(f"ERROR: MOD_IN_GAME does not exist: {mod_dir}")
        sys.exit(1)

    building_types_dir = mod_dir / "common" / "building_types"

    if CHECK_MODE:
        print("── CHECK MODE (read-only) ──")
    print(f"Vanilla: {vanilla_dir}")
    print(f"Mod:     {mod_dir}")
    print(f"Output:  {output_dir}")
    print("")

    # ── Safety gates (skipped in check mode, since nothing is written) ──
    if not CHECK_MODE:
        _check_git_clean(building_types_dir)
        _confirm_destructive(building_types_dir)

    # ── Stage 1: Parse production methods ──
    # Scan vanilla + mod PM files, filter to qualifying (has goods, no
    # no_upkeep, and no non-maintenance output). Result: pm_name → schema.
    print("")
    print("Parsing production methods...")
    pms = parse_production_methods(vanilla_dir, mod_dir)
    print(f"  found {len(pms)} production methods")
    qualifying_pms = {
        k: v for k, v in pms.items()
        if not v['no_upkeep'] and v['goods'] and _output_is_compatible_with_epbm_upkeep(v)
    }
    print(f"  qualifying PMs (has goods, no no_upkeep, no non-maintenance output): {len(qualifying_pms)}")

    # ── Stage 2: Parse all buildings ──
    # Merge vanilla + mod building_types. Mod files replace same-named
    # vanilla files; INJECT/REPLACE blocks override individual buildings.
    print("")
    print("Parsing building types...")
    buildings = parse_all_buildings(vanilla_dir, mod_dir)
    print(f"  found {len(buildings)} buildings")

    # ── Stage 3: Classify buildings ──
    # Match buildings to qualifying PMs, skip forts, warn about estate
    # buildings missing maintenance PMs. Produces the qualifying list.
    print("")
    print("Classifying qualifying buildings...")
    qualifying, all_pm_goods = classify(buildings, pms)
    print(f"  qualifying buildings:      {len(qualifying)}")
    print(f"  unique PM goods profiles:  {len(all_pm_goods)}")

    # Tuple layout: (bname, is_foreign, estate)
    non_foreign = [q for q in qualifying if not q[1]]
    foreign_count = sum(1 for q in qualifying if q[1])
    estate_count = sum(1 for q in qualifying if q[2] is not None)
    inject_count = sum(1 for b, _, _ in non_foreign
                       if not buildings[b]['has_on_built'] and not buildings[b]['has_on_destroyed'])
    replace_count = sum(1 for b, _, _ in non_foreign
                        if buildings[b]['has_on_built'] or buildings[b]['has_on_destroyed'])
    print(f"  INJECT buildings (vanilla-only, no existing hook): {inject_count}")
    print(f"  REPLACE buildings (vanilla-only, existing hook):   {replace_count}")
    print(f"  Foreign buildings (country-scope iteration):       {foreign_count}")

    # ── Output subdirectories ──
    out_effects = output_dir / "in_game" / "common" / "scripted_effects"
    out_ios = output_dir / "in_game" / "common" / "international_organizations"
    out_biases = output_dir / "in_game" / "common" / "biases"
    out_loc = output_dir / "main_menu" / "localization" / "english"
    out_buildings = output_dir / "in_game" / "common" / "building_types"

    # ── Stage 4: Rewrite mod files in-place ──
    # Strip old on_built/on_destroyed hooks and re-inject fresh ones.
    # Only touches files that contain qualifying buildings.
    print("")
    print("Rewriting MnT building files in place...")
    modified, vanilla_only = apply_in_place(qualifying, buildings, mod_dir)
    print(f"  modified {modified} file(s)")

    # ── Stage 5: INJECT/REPLACE for vanilla-only buildings ──
    if vanilla_only:
        print("")
        print(f"Generating INJECT/REPLACE for {len(vanilla_only)} vanilla-only building(s)...")

        inject_code = generate_inject(vanilla_only, buildings)
        out_path = out_buildings / f"{PREFIX}_generated_inject.txt"
        _write_output(out_path, inject_code)
        print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")

        replace_code, replace_renamed_pms = generate_replace(vanilla_only, buildings)
        out_path = out_buildings / f"{PREFIX}_generated_replace.txt"
        _write_output(out_path, replace_code)
        print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")
    else:
        # Clean up any stale generated INJECT/REPLACE files from previous runs
        # where vanilla-only buildings used to exist. Bounded delete — only
        # two exact filenames, and only inside the mod's own output dir.
        for stale in (
            out_buildings / f"{PREFIX}_generated_inject.txt",
            out_buildings / f"{PREFIX}_generated_replace.txt",
        ):
            if stale.exists():
                if CHECK_MODE:
                    print(f"  {stale.name}: stale (would delete)")
                else:
                    print(f"  cleaned stale {stale.name}")
                _delete_stale(stale)
        replace_renamed_pms = OrderedDict()

    # ── Stages 6-8: IOs, init effects, biases, localization ──
    # Generate all runtime artifacts: IO definitions (goods containers),
    # init effects (game-start setup), biases (engine-required), and
    # localization (prevent missing-loc warnings).
    print("")
    print("Writing generated IOs / biases / init effects / loc...")

    io_defs = generate_io_definitions(all_pm_goods)
    out_path = out_ios / f"{PREFIX}_generated_ios.txt"
    _write_output(out_path, io_defs)
    print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")

    init_effects = generate_init_effects(qualifying, all_pm_goods)
    out_path = out_effects / f"{PREFIX}_generated_init_effects.txt"
    _write_output(out_path, init_effects)
    print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")

    biases = generate_io_biases(all_pm_goods)
    out_path = out_biases / f"{PREFIX}_generated_biases.txt"
    _write_output(out_path, biases)
    print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")

    loc = generate_io_localization(all_pm_goods)
    out_path = out_loc / f"{PREFIX}_ios_l_english.yml"
    _write_output(out_path, loc, encoding="utf-8")
    print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")

    # Aliases for PMs renamed by the REPLACE generator (see generate_replace).
    # Written only when the REPLACE pass actually renamed something; otherwise
    # any stale version of the file gets cleaned up.
    replaced_pms_loc = generate_replaced_pm_localization(replace_renamed_pms)
    replaced_pms_path = out_loc / f"{PREFIX}_generated_replaced_pms_l_english.yml"
    if replaced_pms_loc is not None:
        _write_output(replaced_pms_path, replaced_pms_loc, encoding="utf-8")
        print(f"  {'would write' if CHECK_MODE else 'wrote'} {replaced_pms_path.relative_to(output_dir)}")
    else:
        if replaced_pms_path.exists():
            if CHECK_MODE:
                print(f"  {replaced_pms_path.name}: stale (would delete)")
            else:
                print(f"  cleaned stale {replaced_pms_path.name}")
            _delete_stale(replaced_pms_path)

    # ── Summary ──
    print("")
    print("=== Summary ===")
    print(f"Total qualifying buildings:       {len(qualifying)}")
    print(f"  Location-tracked (non-foreign): {len(non_foreign)}")
    print(f"  Foreign buildings:              {foreign_count}")
    print(f"  Estate-assigned buildings:      {estate_count}")
    print(f"Unique PM goods profiles:         {len(all_pm_goods)}")

    all_goods = set()
    for good_dict in all_pm_goods.values():
        all_goods.update(good_dict.keys())
    print(f"Distinct maintenance goods: {len(all_goods)} ({', '.join(sorted(all_goods))})")

    # ── Check-mode verdict ──
    # Exit codes:
    #   0 = tree is in sync (or normal write mode completed)
    #   1 = script/config error (raised earlier via sys.exit(1))
    #   2 = check mode detected drift — tree needs regeneration
    if CHECK_MODE:
        print("")
        if _check_diffs:
            print(f"=== CHECK FAILED: {len(_check_diffs)} file(s) out of sync ===")
            for path, kind in sorted(_check_diffs, key=lambda p: str(p[0])):
                try:
                    rel = path.relative_to(output_dir)
                except ValueError:
                    rel = path
                label = {
                    'changed': 'changed ',
                    'missing': 'missing ',
                    'stale':   'stale   ',
                }.get(kind, kind)
                print(f"  [{label}] {rel}")
            print("")
            print("Run the generator locally and commit the result:")
            print("  python3 tools/MnT_epbm_generator/MnT_generate_building_hooks.py")
            return 2
        print("=== CHECK PASSED: tree is in sync ===")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
