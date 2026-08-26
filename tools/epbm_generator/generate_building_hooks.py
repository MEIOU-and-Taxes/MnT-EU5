#!/usr/bin/env python3
"""
generate_building_hooks.py — Estate-pays-building-maintenance codegen.

Scans vanilla EU5 + mod building_types and production_methods, determines
which buildings should contribute to the epbm estate-maintenance system,
and writes out the generated script the runtime needs.

────────────────────────────────────────────────────────────────────────────
PIPELINE OVERVIEW
────────────────────────────────────────────────────────────────────────────
The generator runs in four stages:

  1. PARSE PRODUCTION METHODS
     Scans vanilla + mod production_methods/ files. Filters to qualifying
     PMs: those with goods inputs, no `no_upkeep = yes`, and no output
     goods. Builds a goods-per-PM map used for pricing at runtime.

  2. PARSE ALL BUILDINGS
     Scans vanilla + mod building_types/ directories. When a mod file has
     the same name as a vanilla file, the mod version completely replaces
     it. INJECT/REPLACE blocks from mod files are applied on top of
     vanilla building definitions. Records each building's estate
     assignment, PM references, and source file.

  3. CLASSIFY
     Matches buildings to qualifying PMs. Identifies crown buildings.
     Warns about estate-assigned buildings that have no qualifying
     maintenance PM. Outputs the qualifying building list and a map
     of unique goods profiles.

  4. GENERATE INIT EFFECTS + CROWN INJECT
     Writes `epbm_stamp_globals`: called once at game start (and on
     save-game load). Allocates one pooled location per unique PM goods
     profile, populates the global `epbm_profiles` map (PM -> location),
     registers estate-assigned buildings in `epbm_estate_map`, crown
     buildings in `epbm_crown_map`, and all tracked building types in
     `epbm_tracked_types`. Tags crown buildings with a cosmetic modifier.

────────────────────────────────────────────────────────────────────────────
RUNTIME CONTEXT
────────────────────────────────────────────────────────────────────────────
The generated artifacts feed the EPBM runtime (epbm_*.txt scripts):

  - The calc engine iterates `every_owned_building` filtered against the
    `epbm_tracked_types` global map, prices each building's maintenance
    PM against its local market, and routes costs to the appropriate
    estate bucket.

  - Pooled locations (one per PM goods profile) store goods quantities in
    an epbm_goods variable map, letting the calculator price each
    building's maintenance against its local market.

  - The estate map routes estate-assigned buildings to their owning
    estate's cost bucket. Non-estate buildings go to a shared pool that
    is split by estate power.

────────────────────────────────────────────────────────────────────────────
CONFIGURATION
────────────────────────────────────────────────────────────────────────────
All tunables live in `epbm_generator_config.py` next to this script.
"""

import os
import re
import sys
from collections import OrderedDict
from pathlib import Path

# Import the user-editable configuration. Must sit next to this script.
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
import epbm_generator_config as cfg  # noqa: E402


# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

PM_META_KEYS = {"category", "no_upkeep", "potential", "produced", "output"}


def parse_employment_values(vanilla_dir, mod_dir=None, buildings=None):
    """Parse employment script values from default_values.txt.

    Collects all script value names referenced by building employment_size
    fields, then resolves them from default_values.txt files.
    Returns a dict mapping script value name to float (in thousands).
    """
    needed = set()
    if buildings:
        for bdata in buildings.values():
            emp = bdata.get('employment_size')
            if emp and not _is_numeric(emp):
                needed.add(emp)

    result = {}
    search_dirs = []
    main_menu = vanilla_dir.parent / "main_menu" if vanilla_dir.name == "in_game" else vanilla_dir / "main_menu"
    sv_dir = main_menu / "common" / "script_values"
    if sv_dir.exists():
        search_dirs.append(sv_dir)
    if mod_dir:
        mod_sv = mod_dir / "common" / "script_values"
        if mod_sv.exists():
            search_dirs.append(mod_sv)

    pat = re.compile(r'^(\w+)\s*=\s*([\d.]+)\s*$')
    for d in search_dirs:
        for f in sorted(d.iterdir()):
            if not f.name.endswith(".txt"):
                continue
            try:
                text = f.read_text(encoding="utf-8-sig")
            except Exception:
                continue
            for line in text.splitlines():
                m = pat.match(line.strip())
                if m:
                    name = m.group(1)
                    if needed and name not in needed:
                        continue
                    result[name] = float(m.group(2))
    return result


def _is_numeric(s):
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False

SKIP_FILES = {"readme.txt", "__readme.txt", "00_unique_buildings_to_make_obsolete.txt"}

PREFIX = cfg.PREFIX

GENERATED_HEADER_LINES = [
    "# AUTO-GENERATED by tools/epbm_generator/. Hand edits will be lost on the next run.",
]


# ═════════════════════════════════════════════════════════════════════════
# Check mode
# ═════════════════════════════════════════════════════════════════════════

CHECK_MODE = False
_check_diffs = []


def _is_check_mode():
    return CHECK_MODE


def _record_diff(path, kind):
    _check_diffs.append((Path(path), kind))


def _write_output(path, content, encoding="utf-8-sig"):
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
    path = Path(path)
    if _is_check_mode():
        if path.exists():
            _record_diff(path, 'stale')
        return
    if path.exists():
        path.unlink()


def _p(name):
    return f"{PREFIX}_{name}"


# ═════════════════════════════════════════════════════════════════════════
# Paradox script parser
# ═════════════════════════════════════════════════════════════════════════

def strip_bom(text):
    return text.lstrip("﻿")


def strip_comments(text):
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
        if text[i] in '{}':
            yield text[i]
            i += 1
            continue
        if text[i] in '=!<>':
            j = i + 1
            while j < n and text[j] in '=!<>':
                j += 1
            yield text[i:j]
            i = j
            continue
        j = i
        while j < n and text[j] not in " \t\r\n{}=\"":
            j += 1
        yield text[i:j]
        i = j


def parse_block(tokens, idx):
    assert tokens[idx] == '{', f"Expected '{{' at index {idx}, got '{tokens[idx]}'"
    idx += 1
    result = OrderedDict()
    while idx < len(tokens) and tokens[idx] != '}':
        key = tokens[idx]
        idx += 1
        if key == '{':
            _, idx = parse_block(tokens, idx - 1)
            continue
        if idx < len(tokens) and tokens[idx] == '=':
            idx += 1
            if idx < len(tokens) and tokens[idx] == '{':
                val, idx = parse_block(tokens, idx)
            else:
                val = tokens[idx]
                idx += 1
        elif idx < len(tokens) and tokens[idx] == '{':
            val, idx = parse_block(tokens, idx)
        else:
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
        idx += 1
    return result, idx


def parse_file(filepath):
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

def parse_production_methods(vanilla_dir, mod_dir=None):
    """Return a dict pm_name -> { goods, no_upkeep, has_output, has_potential }."""
    pms = {}
    for pm_dir in [vanilla_dir / "common" / "production_methods"]:
        if pm_dir.exists():
            for f in sorted(pm_dir.iterdir()):
                if f.name.endswith(".txt") and f.name.lower() not in SKIP_FILES:
                    pms.update(_parse_pm_file(f))
    if mod_dir:
        mod_pm_dir = mod_dir / "common" / "production_methods"
        if mod_pm_dir.exists():
            for f in sorted(mod_pm_dir.iterdir()):
                if f.name.endswith(".txt") and f.name.lower() not in SKIP_FILES:
                    pms.update(_parse_pm_file(f))
    return pms


def _parse_pm_file(filepath):
    data = parse_file(filepath)
    pms = {}
    for name, block in data.items():
        if name.startswith("REPLACE:"):
            name = name[8:]
        if not isinstance(block, dict):
            continue
        pm = {
            'goods': OrderedDict(),
            'no_upkeep': 'no_upkeep' in block and block['no_upkeep'] == 'yes',
            'has_output': 'produced' in block or 'output' in block,
            'has_potential': 'potential' in block,
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

def _parse_building_block(bname, block, source_file):
    b = {
        'file': source_file,
        'estate': block.get('estate'),
        'is_foreign': block.get('is_foreign') == 'yes',
        'employment_size': block.get('employment_size'),
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
                }
    return b


def _scan_building_dir(directory):
    buildings = OrderedDict()
    injects = []
    replaces = []
    files_present = set()

    generator_outputs = {
        f"{PREFIX}_generated_crown_inject.txt",
    }

    BUILDING_SHAPE_FIELDS = {
        'category', 'max_levels', 'pop_type', 'is_foreign', 'is_special',
        'employment_size', 'possible_production_methods',
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
                if not (BUILDING_SHAPE_FIELDS & block.keys()):
                    continue
                buildings[key] = _parse_building_block(key, block, f)

    return buildings, injects, replaces, files_present


def _apply_inject(building, inject_block):
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
                    }
        elif k == 'estate':
            building['estate'] = v
            raw['estate'] = v
        else:
            raw[k] = v


def parse_all_buildings(vanilla_dir, mod_dir=None):
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

CROWN_MODIFIER_KEYS = {
    'local_max_control',
    'global_max_control',
    'local_crown_estate_power',
    'global_crown_estate_power',
    'local_proximity_source',
}

CROWN_TRIGGER_KEYS = {'fort_level', 'minimum_fort_level'}

FORT_KEYS = {'fort_level', 'minimum_fort_level'}

TRIGGER_BLOCK_KEYS = {
    'country_potential',
    'location_potential',
    'international_organization_potential',
    'remove_if',
    'trigger',
    'potential',
}


def _scan_for_crown(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in TRIGGER_BLOCK_KEYS:
                continue
            if k in CROWN_TRIGGER_KEYS:
                return True
            if k in CROWN_MODIFIER_KEYS and isinstance(v, str):
                try:
                    if float(v) > 0:
                        return True
                except ValueError:
                    pass
            if _scan_for_crown(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _scan_for_crown(item):
                return True
    return False


def _is_fort_building(building):
    raw = building['raw']
    return _scan_for_fort(raw)


def _scan_for_fort(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in TRIGGER_BLOCK_KEYS:
                continue
            if k in FORT_KEYS:
                return True
            if _scan_for_fort(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _scan_for_fort(item):
                return True
    return False


def _is_crown_building(building):
    if building.get('estate') is not None:
        return False
    raw = building['raw']
    if raw.get('category') == 'government_category':
        return True
    return _scan_for_crown(raw)


def classify(buildings, pms):
    all_pm_goods = OrderedDict()

    for pm_name, pm in pms.items():
        if pm['no_upkeep'] or pm['has_output']:
            continue
        if not pm['goods']:
            continue
        all_pm_goods[pm_name] = pm['goods']

    qualifying = []
    crown_buildings = []
    crown_with_pm = 0
    fort_excluded = []
    for bname, b in buildings.items():
        if _is_fort_building(b):
            fort_excluded.append(bname)
            continue

        for pm_name, pm_data in b['unique_pms'].items():
            if not pm_data.get('is_maintenance', False):
                continue
            if pm_data.get('no_upkeep', False) or pm_data.get('has_output', False):
                continue
            if not pm_data['goods']:
                continue
            all_pm_goods[pm_name] = pm_data['goods']

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

        if _is_crown_building(b):
            crown_buildings.append(bname)
            if has_tracked:
                crown_with_pm += 1

        if has_tracked:
            qualifying.append((bname, b['is_foreign'], b['estate'], b.get('employment_size')))

    used_pms = set()
    for bname, _is_foreign, _estate, _emp in qualifying:
        b = buildings[bname]
        for pm_name in b['possible_pms']:
            if pm_name in all_pm_goods:
                used_pms.add(pm_name)
        for pm_name in b['unique_pms']:
            if pm_name in all_pm_goods:
                used_pms.add(pm_name)
    orphaned_pms = set(all_pm_goods.keys()) - used_pms
    if orphaned_pms:
        for pm_name in orphaned_pms:
            del all_pm_goods[pm_name]
        print(f"  pruned {len(orphaned_pms)} unreferenced PM profile(s)")

    if fort_excluded:
        print(f"  excluded {len(fort_excluded)} fort building(s): {', '.join(sorted(fort_excluded))}")

    if crown_buildings:
        print(f"  classified {len(crown_buildings)} crown building(s)")
        print(f"    of which {crown_with_pm} have a maintenance PM")

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

    return qualifying, all_pm_goods, crown_buildings


# ═════════════════════════════════════════════════════════════════════════
# Code generators
# ═════════════════════════════════════════════════════════════════════════

def generate_crown_inject(crown_buildings):
    lines = list(GENERATED_HEADER_LINES)
    lines.append("# INJECT cosmetic 'Crown Building' modifier onto government /")
    lines.append("# fort / crown-power-granting buildings.")
    lines.append("")

    for bname in sorted(crown_buildings):
        lines.append(f"INJECT:{bname} = {{")
        lines.append("\tmodifier = {")
        lines.append(f"\t\t{_p('crown_building')} = yes")
        lines.append("\t}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)



def _resolve_employment(emp_name, emp_vals):
    """Resolve an employment_size field to a numeric value."""
    if emp_name is None:
        return 0
    try:
        return float(emp_name)
    except (ValueError, TypeError):
        pass
    return emp_vals.get(emp_name, 0)


def generate_init_effects(qualifying, all_pm_goods, crown_buildings, employment_values=None):
    all_pm_dicts = _p('all_pm_dicts')
    profiles = _p('profiles')
    estate_map = _p('estate_map')
    crown_map = _p('crown_map')
    tracked_types = _p('tracked_types')

    lines = list(GENERATED_HEADER_LINES)
    lines.append("")

    lines.append("# Called once at game start: clear globals, then register one pooled")
    lines.append(f"# location per maintenance PM via {_p('register_pm')}.")
    lines.append(f"{_p('stamp_globals')} = {{")
    lines.append(f"\tclear_global_variable_list = {all_pm_dicts}")
    lines.append(f"\tclear_global_variable_map = {profiles}")
    lines.append(f"\tclear_global_variable_map = {estate_map}")
    lines.append(f"\tclear_global_variable_map = {crown_map}")
    lines.append(f"\tclear_global_variable_map = {tracked_types}")
    lines.append("")

    for pm_name in sorted(all_pm_goods.keys()):
        pm_goods = all_pm_goods[pm_name]
        lines.append(f"\t{_p('register_pm')} = {{")
        lines.append(f"\t\tpm = {pm_name}")
        lines.append(f"\t\tgoods_block = \"")
        for good, amount in pm_goods.items():
            lines.append(f"\t\t\t{_p('good')} = {{ good = {good} amount = {amount} }}")
        lines.append("\t\t\"")
        lines.append("\t}")

    # Tracked building types with employment-per-level
    emp_vals = employment_values or {}
    lines.append("")
    lines.append(f"\t# Tracked building types (value = employment per level, in thousands)")
    for bname, _is_foreign, _estate, emp_name in sorted(qualifying, key=lambda x: x[0]):
        bt_ref = f"building_type:{bname}"
        emp_val = _resolve_employment(emp_name, emp_vals)
        lines.append(f"\tadd_to_global_variable_map = {{ name = {tracked_types} key = {bt_ref} value = {emp_val} }}")

    # Estate-assignment map
    estate_buildings = [(b, e) for b, _, e, _ in qualifying if e is not None]
    if estate_buildings:
        lines.append("")
        lines.append(f"\t# Estate-assigned buildings: charge full cost to the named estate")
        for bname, estate in sorted(estate_buildings):
            bt_ref = f"building_type:{bname}"
            lines.append(f"\tadd_to_global_variable_map = {{ name = {estate_map} key = {bt_ref} value = estate_type:{estate} }}")

    # Crown-routing map
    qualifying_crown = sorted(b for b in crown_buildings
                              if b in {q[0] for q in qualifying})
    if qualifying_crown:
        lines.append("")
        lines.append(f"\t# Crown buildings: upkeep routed to the crown-total bucket")
        for bname in qualifying_crown:
            bt_ref = f"building_type:{bname}"
            lines.append(f"\tadd_to_global_variable_map = {{ name = {crown_map} key = {bt_ref} value = yes }}")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════

def main():
    global CHECK_MODE
    CHECK_MODE = bool(os.environ.get("EPBM_CHECK"))
    _check_diffs.clear()

    vanilla_dir = _resolve_vanilla_dir()
    mod_dir = Path(cfg.MOD_IN_GAME)
    output_dir = Path(cfg.OUTPUT_ROOT)

    if not mod_dir.exists():
        print(f"ERROR: MOD_IN_GAME does not exist: {mod_dir}")
        sys.exit(1)

    if CHECK_MODE:
        print("-- CHECK MODE (read-only) --")
    print(f"Vanilla: {vanilla_dir}")
    print(f"Mod:     {mod_dir}")
    print(f"Output:  {output_dir}")

    # ── Stage 1: Parse production methods ──
    print("")
    print("Parsing production methods...")
    pms = parse_production_methods(vanilla_dir, mod_dir)
    print(f"  found {len(pms)} production methods")
    qualifying_pms = {k: v for k, v in pms.items()
                      if not v['no_upkeep'] and not v['has_output'] and v['goods']}
    print(f"  qualifying PMs (has goods, no no_upkeep, no output): {len(qualifying_pms)}")

    # ── Stage 2: Parse all buildings ──
    print("")
    print("Parsing building types...")
    buildings = parse_all_buildings(vanilla_dir, mod_dir)
    print(f"  found {len(buildings)} buildings")

    # ── Stage 2b: Parse employment values ──
    print("")
    print("Parsing employment script values...")
    employment_values = parse_employment_values(vanilla_dir, mod_dir, buildings)
    print(f"  found {len(employment_values)} employment value(s)")

    # ── Stage 3: Classify buildings ──
    print("")
    print("Classifying qualifying buildings...")
    qualifying, all_pm_goods, crown_buildings = classify(buildings, pms)
    print(f"  qualifying buildings:      {len(qualifying)}")
    print(f"  crown buildings:           {len(crown_buildings)}")
    print(f"  unique PM goods profiles:  {len(all_pm_goods)}")

    non_foreign = [q for q in qualifying if not q[1]]
    foreign_count = sum(1 for q in qualifying if q[1])
    estate_count = sum(1 for q in qualifying if q[2] is not None)

    missing_emp = [q[0] for q in qualifying if _resolve_employment(q[3], employment_values) == 0]
    if missing_emp:
        print(f"  WARNING: {len(missing_emp)} building(s) missing employment value:")
        for b in sorted(missing_emp)[:10]:
            print(f"    {b}")
        if len(missing_emp) > 10:
            print(f"    ... and {len(missing_emp) - 10} more")
    print(f"  Non-foreign buildings:     {len(non_foreign)}")
    print(f"  Foreign buildings:         {foreign_count}")
    print(f"  Estate-assigned:           {estate_count}")

    # ── Output subdirectories ──
    out_effects = output_dir / "in_game" / "common" / "scripted_effects"
    out_buildings = output_dir / "in_game" / "common" / "building_types"

    # ── Stage 4: Init effects ──
    print("")
    print("Writing generated init effects...")
    init_effects = generate_init_effects(qualifying, all_pm_goods, crown_buildings, employment_values)
    out_path = out_effects / f"{PREFIX}_generated_init_effects.txt"
    _write_output(out_path, init_effects)
    print(f"  {'would write' if CHECK_MODE else 'wrote'} {out_path.relative_to(output_dir)}")

    # ── Stage 5a: Crown building cosmetic flag ──
    crown_inject_path = out_buildings / f"{PREFIX}_generated_crown_inject.txt"
    qualifying_names = {q[0] for q in qualifying}
    qualifying_crown = sorted(b for b in crown_buildings if b in qualifying_names)
    if qualifying_crown:
        print("")
        print(f"Generating crown-building flag for {len(qualifying_crown)} building(s)...")
        crown_code = generate_crown_inject(qualifying_crown)
        _write_output(crown_inject_path, crown_code)
        print(f"  {'would write' if CHECK_MODE else 'wrote'} {crown_inject_path.relative_to(output_dir)}")
    else:
        _delete_stale(crown_inject_path)

    # ── Clean up stale files from previous generator versions ──
    for stale_path in (
        out_buildings / f"{PREFIX}_generated_inject.txt",
        out_buildings / f"{PREFIX}_generated_replace.txt",
        output_dir / "in_game" / "common" / "international_organizations" / f"{PREFIX}_generated_ios.txt",
        output_dir / "in_game" / "common" / "biases" / f"{PREFIX}_generated_biases.txt",
        output_dir / "main_menu" / "localization" / "english" / f"{PREFIX}_ios_l_english.yml",
        output_dir / "main_menu" / "localization" / "english" / f"{PREFIX}_generated_replaced_pms_l_english.yml",
        output_dir / "in_game" / "common" / "script_values" / f"{PREFIX}_generated_script_values.txt",
    ):
        _delete_stale(stale_path)

    # ── Summary ──
    print("")
    print("=== Summary ===")
    print(f"Total qualifying buildings:   {len(qualifying)}")
    print(f"  Non-foreign:               {len(non_foreign)}")
    print(f"  Foreign:                   {foreign_count}")
    print(f"  Estate-assigned:           {estate_count}")
    print(f"Unique PM goods profiles:    {len(all_pm_goods)}")
    print(f"Tracked building types:      {len(qualifying)}")

    all_goods = set()
    for good_dict in all_pm_goods.values():
        all_goods.update(good_dict.keys())
    print(f"Distinct maintenance goods:  {len(all_goods)} ({', '.join(sorted(all_goods))})")

    if CHECK_MODE:
        print("")
        if _check_diffs:
            print(f"=== CHECK FAILED: {len(_check_diffs)} file(s) out of sync ===")
            for path, kind in sorted(_check_diffs, key=lambda p: str(p[0])):
                try:
                    rel = path.relative_to(output_dir)
                except ValueError:
                    rel = path
                label = {'changed': 'changed ', 'missing': 'missing ', 'stale': 'stale   '}.get(kind, kind)
                print(f"  [{label}] {rel}")
            print("")
            print("Run the generator locally and commit the result:")
            print("  python3 tools/epbm_generator/generate_building_hooks.py")
            return 2
        print("=== CHECK PASSED: tree is in sync ===")
        return 0

    return 0


def _resolve_vanilla_dir():
    for candidate in cfg.VANILLA_IN_GAME_CANDIDATES:
        if candidate.exists() and (candidate / "common" / "building_types").exists():
            return candidate
    print("ERROR: No vanilla in_game/ directory found. Tried:")
    for candidate in cfg.VANILLA_IN_GAME_CANDIDATES:
        print(f"  - {candidate}")
    print("Edit VANILLA_IN_GAME_CANDIDATES in epbm_generator_config.py")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
