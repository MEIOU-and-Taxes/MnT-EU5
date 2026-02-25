#!/usr/bin/env python3
"""
Generate Paradox script files for Estates Pay Building Maintenance mod.

Parses base game building_types/ and production_methods/ to produce:
  - mnt_generated_inject.txt         (INJECT blocks: list management on build/destroy)
  - mnt_generated_replace.txt        (REPLACE blocks: same for buildings with existing on_built)
  - mnt_generated_init_effects.txt   (IO creation + parent profile map + init dispatch)
  - mnt_generated_ios.txt            (hidden international organizations as variable map hosts)
"""

import os
import re
import sys
from collections import OrderedDict
from pathlib import Path

# Paths
GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Europa Universalis V\game\in_game")
BUILDING_DIR = GAME_DIR / "common" / "building_types"
PM_FILE = GAME_DIR / "common" / "production_methods" / "unsorted_building_inputs.txt"
MOD_DIR = Path(__file__).resolve().parent.parent.parent
OUT_EFFECTS = MOD_DIR / "in_game" / "common" / "scripted_effects"
OUT_BUILDINGS = MOD_DIR / "in_game" / "common" / "building_types"
OUT_IOS = MOD_DIR / "in_game" / "common" / "international_organizations"
OUT_BIASES = MOD_DIR / "in_game" / "common" / "biases"
OUT_LOC = MOD_DIR / "main_menu" / "localization" / "english"

# Keys in PM definitions that are NOT goods
PM_META_KEYS = {"category", "no_upkeep", "potential", "produced", "output"}

# Government/military buildings: excluded from mnt maintenance tracking.
# Crown pays their maintenance directly. Marked with mnt_crown_building modifier.
# 97 automated (capital-specific, forts, soldier-employing) + 42 reclassified
GOVERNMENT_BUILDINGS = {
    # Automated scan (97)
    "ablaq_palace", "admiralty", "alhambra", "amsterdam_admiralty", "armory",
    "art_school", "arts_academy", "bailiff", "bajang_ratu",
    "barcelona_royal_shipyard", "barracks", "bastion",
    "bavarian_academy_of_sciences", "bey_fortress", "brethren_marsh",
    "calmecac", "camara_comptos", "cantonments", "castel_sant_angelo",
    "castle", "cawa_barracks", "chancery", "city_guard", "coastal_fort",
    "conscription_center", "copenhagen_dockyard", "dock", "dry_dock",
    "enderun_academy", "fortress", "fortezza_di_sant_andrea",
    "friesland_admiralty", "gallowglass_sept", "ghilman_barracks",
    "grand_shipyard", "great_enclosure", "great_hill_complex",
    "great_valley_complex", "hexamilion_wall", "house_of_parliament",
    "hsa_burgtor", "imperial_halic_shipyards", "janissary_barracks",
    "jurchen_barracks", "kastellet", "kilwan_shipwrights",
    "korean_gunnery_coastal_defense", "korean_gunnery_land_defense",
    "kremlin", "kronborg", "kurmina_headquarter", "kurultai",
    "mamluk_barracks", "naval_base", "naval_battery", "north_sea_shipyards",
    "oma_nizwa_fort", "order_headquarters", "ostrog", "peel_towers",
    "pirate_stronghold", "pirate_tavern", "pukara_building",
    "qalat_al_mashwar", "rahdar", "red_fort", "regimental_camp",
    "repaired_great_wall_of_china", "republican_assembly",
    "rotterdam_admiralty", "royal_academy_of_arts",
    "royal_atarazanas_seville", "royal_court", "royal_garden",
    "royal_society", "ruined_great_wall_of_china",
    "segovia_artillery_academy", "sergeantry", "shipyard", "sofa_barracks",
    "star_fort", "stockade", "supreme_court", "tambo", "telpochcalli",
    "the_bock_fortifications", "theodosian_walls", "thema_headquarters",
    "tower_of_belem", "training_fields", "uffizi", "venetian_arsenal",
    "venetian_palaces", "walls_of_benin", "walls_of_ston", "war_college",
    "warrior_temple", "west_friesland_admiralty", "zazzau_walls",
    "zeeland_admiralty", "zwinger",
    # Reclassified from regular (42)
    "ambras_castle", "belvedere_palace", "berlin_palace",
    "coastal_settlements", "construction_center", "counting_house",
    "doges_palace", "eghabho_nore_mansion", "el_escorial_palace",
    "forbidden_city", "fortress_church", "fortress_granary",
    "galley_barracks", "general_archive_of_simancas", "grand_apartment",
    "guich_garrison", "imperial_city_of_hue", "kalari", "kings_manor",
    "lieutenancy", "local_governor", "minting_office",
    "moscow_artillery_yard", "munich_residenz_founding", "naval_governor",
    "novodevichy_convent", "oma_falaj", "papal_archives",
    "protected_harbor", "quirinal_palace", "ribat", "ribeira_das_naus",
    "rock_of_monaco", "safaviyya_order_hall", "sanssouci",
    "schonbrunn_palace", "sco_palace_of_holyroodhouse", "seljuk_mint",
    "the_cipher_secretary", "versailles", "viceroyalty", "zhixian",
}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Parsing helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def strip_bom(text):
    return text.lstrip("\ufeff")


def strip_comments(text):
    """Remove # comments (but not inside quotes)."""
    lines = []
    for line in text.split("\n"):
        in_quote = False
        result = []
        for i, ch in enumerate(line):
            if ch == '"':
                in_quote = not in_quote
            elif ch == '#' and not in_quote:
                break
            result.append(ch)
        lines.append("".join(result))
    return "\n".join(lines)


def tokenize(text):
    """Simple tokenizer for Paradox script: yields tokens (strings, braces, =, values)."""
    text = strip_bom(text)
    text = strip_comments(text)
    i = 0
    n = len(text)
    while i < n:
        # Skip whitespace
        if text[i] in " \t\r\n":
            i += 1
            continue
        # Quoted string
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == '\\':
                    j += 1
                j += 1
            yield text[i+1:j]
            i = j + 1
            continue
        # Braces and equals
        if text[i] in '{}=':
            yield text[i]
            i += 1
            continue
        # Unquoted token
        j = i
        while j < n and text[j] not in " \t\r\n{}=\"":
            j += 1
        yield text[i:j]
        i = j


def parse_block(tokens, idx):
    """
    Parse a { ... } block starting at tokens[idx] which should be '{'.
    Returns (dict_or_list, next_idx).
    For simplicity, returns an OrderedDict of key=value pairs.
    Nested blocks become nested dicts. Duplicate keys get list values.
    """
    assert tokens[idx] == '{', f"Expected '{{' at index {idx}, got '{tokens[idx]}'"
    idx += 1
    result = OrderedDict()
    while idx < len(tokens) and tokens[idx] != '}':
        key = tokens[idx]
        idx += 1
        if idx < len(tokens) and tokens[idx] == '=':
            idx += 1  # skip =
            if idx < len(tokens) and tokens[idx] == '{':
                val, idx = parse_block(tokens, idx)
            else:
                val = tokens[idx]
                idx += 1
        else:
            # Bare value (no =), common in lists like possible_production_methods
            val = True
            # Don't advance idx - key is already consumed
            if key in result:
                if isinstance(result[key], list):
                    result[key].append(val)
                else:
                    result[key] = [result[key], val]
                continue
            result[key] = val
            continue
        # Store with duplicate handling
        if key in result:
            if isinstance(result[key], list):
                result[key].append(val)
            else:
                result[key] = [result[key], val]
        else:
            result[key] = val
    if idx < len(tokens):
        idx += 1  # skip '}'
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Parse production methods
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def parse_production_methods():
    """
    Parse unsorted_building_inputs.txt.
    Returns dict: pm_name -> { 'goods': OrderedDict(good->amount), 'no_upkeep': bool, 'has_output': bool, 'has_potential': bool }
    """
    data = parse_file(PM_FILE)
    pms = {}
    for name, block in data.items():
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Parse building types
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def parse_all_buildings():
    """
    Parse all building files.
    Returns dict: building_name -> {
        'file': Path,
        'estate': str or None,
        'is_foreign': bool,
        'has_on_built': bool,
        'has_on_destroyed': bool,
        'possible_pms': [str],     (from possible_production_methods)
        'unique_pms': {pm_name: {goods}},  (from unique_production_methods)
        'raw': dict,  (full parsed block for REPLACE)
    }
    """
    buildings = OrderedDict()
    skip_files = {"readme.txt", "00_unique_buildings_to_make_obsolete.txt"}

    for f in sorted(BUILDING_DIR.iterdir()):
        if f.name in skip_files or not f.name.endswith(".txt"):
            continue
        data = parse_file(f)
        for bname, block in data.items():
            if not isinstance(block, dict):
                continue
            # Detect trade capacity modifiers in modifier block
            modifier_block = block.get('modifier', {})
            has_trade_capacity = False
            if isinstance(modifier_block, dict):
                if ('local_merchant_capacity' in modifier_block or
                        'merchant_capacity_from_building' in modifier_block):
                    has_trade_capacity = True

            b = {
                'file': f,
                'estate': block.get('estate'),
                'is_foreign': block.get('is_foreign') == 'yes',
                'has_trade_capacity': has_trade_capacity,
                'has_on_built': 'on_built' in block,
                'has_on_destroyed': 'on_destroyed' in block,
                'possible_pms': [],
                'unique_pms': OrderedDict(),
                'raw': block,
            }
            # Parse possible_production_methods (references to external PMs)
            ppm = block.get('possible_production_methods')
            if isinstance(ppm, dict):
                b['possible_pms'] = [k for k in ppm.keys()]
            elif isinstance(ppm, list):
                b['possible_pms'] = ppm

            # Parse unique_production_methods (inline PMs)
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
                        has_output = 'produced' in pm_block or 'output' in pm_block
                        no_upkeep = pm_block.get('no_upkeep') == 'yes'
                        is_maintenance = pm_block.get('category') == 'building_maintenance'
                        b['unique_pms'][pm_name] = {
                            'goods': goods,
                            'has_output': has_output,
                            'no_upkeep': no_upkeep,
                            'is_maintenance': is_maintenance,
                        }

            buildings[bname] = b
    return buildings


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Classify qualifying buildings and PMs
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def classify(buildings, pms):
    """
    Determine which buildings qualify for maintenance tracking.
    A building qualifies if:
      - Not in GOVERNMENT_BUILDINGS set
      - No estate = X assignment
      - Has at least one qualifying PM (category=building_maintenance, has goods, no no_upkeep, no output)

    Returns:
      qualifying: list of (building_name, pm_name, pm_source, is_trade, is_foreign) tuples
        pm_source = 'external' | 'inline'
        is_trade = True if building has trade capacity modifiers (and not foreign)
        is_foreign = True if building has is_foreign = yes
      all_pm_goods: dict pm_name -> OrderedDict(good->amount)
    """
    qualifying = []
    all_pm_goods = OrderedDict()

    for bname, b in buildings.items():
        if bname in GOVERNMENT_BUILDINGS:
            continue
        if b['estate'] is not None:
            continue

        # Check external PMs
        best_pm = None
        for pm_name in b['possible_pms']:
            if pm_name not in pms:
                continue
            pm = pms[pm_name]
            if pm['no_upkeep'] or pm['has_output']:
                continue
            if not pm['goods']:
                continue
            if best_pm is None:
                best_pm = (pm_name, 'external')
                all_pm_goods[pm_name] = pm['goods']

        # Check inline PMs
        for pm_name, pm_data in b['unique_pms'].items():
            if not pm_data.get('is_maintenance', False):
                continue
            if pm_data.get('no_upkeep', False) or pm_data.get('has_output', False):
                continue
            if not pm_data['goods']:
                continue
            if best_pm is None:
                best_pm = (pm_name, 'inline')
                all_pm_goods[pm_name] = pm_data['goods']

        if best_pm:
            is_trade = b['has_trade_capacity'] and not b['is_foreign']
            qualifying.append((bname, best_pm[0], best_pm[1], is_trade, b['is_foreign']))

    return qualifying, all_pm_goods


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Read raw building text for REPLACE blocks
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def read_raw_building_text(filepath, building_name):
    """
    Extract the raw text of a building definition from a file.
    Returns the text between building_name = { ... } including braces.
    """
    text = filepath.read_text(encoding="utf-8-sig")
    text = strip_bom(text)

    # Find the building definition start
    pattern = re.compile(r'^(' + re.escape(building_name) + r')\s*=\s*\{', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None

    start = match.start()
    # Find matching closing brace
    brace_start = text.index('{', match.start())
    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
        i += 1
    return None


def inject_on_built_hook(raw_text, building_name, list_name="mnt_building_types"):
    """
    For REPLACE buildings: insert our list-management hook into existing on_built,
    and add on_destroyed if it doesn't exist.
    Also renames inline unique_production_methods PM names to avoid duplicates.
    Returns modified building text.
    """
    add_code = (
        f"\n\t\t# mnt: Track building for maintenance"
        f"\n\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}"
        f"\n\t\tmnt_on_building_built = yes"
    )
    remove_code = (
        f"\n\t\t# mnt: Untrack building"
        f"\n\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}"
        f"\n\t\tmnt_on_building_destroyed = yes"
    )

    # Rename inline PM names to avoid duplicate PM name errors
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
            return f"{m.group(1)}mnt_{name}{m.group(3)}"
        new_upm_block = pm_def_pattern.sub(rename_pm, upm_block)
        raw_text = raw_text[:upm_match.start()] + new_upm_block + raw_text[upm_end:]

    # Find on_built block and inject before its closing brace
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

    # Add on_destroyed if not present
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

    return raw_text


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Code generation
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_inject(qualifying, buildings):
    """Generate mnt_generated_inject.txt (INJECT blocks for buildings without on_built)."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# INJECT blocks: manage location tracking list on build/destroy",
        "",
    ]

    for bname, pm_name, _, is_trade, is_foreign in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue  # Foreign buildings don't get list hooks
        if b['has_on_built'] or b['has_on_destroyed']:
            continue  # These go in REPLACE file

        list_name = "mnt_trade_types" if is_trade else "mnt_building_types"

        tag = ' (trade)' if is_trade else ''
        lines.append(f"# {bname} uses {pm_name}{tag}")
        lines.append(f"INJECT:{bname} = {{")
        lines.append(f"\ton_built = {{")
        lines.append(f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\tmnt_on_building_built = yes")
        lines.append(f"\t}}")
        lines.append(f"\ton_destroyed = {{")
        lines.append(f"\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\tmnt_on_building_destroyed = yes")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_replace(qualifying, buildings):
    """Generate mnt_generated_replace.txt (REPLACE blocks for buildings with existing on_built)."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# REPLACE blocks for buildings with existing on_built/on_destroyed hooks",
        "",
    ]

    for bname, pm_name, _, is_trade, is_foreign in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue  # Foreign buildings don't get list hooks
        if not b['has_on_built'] and not b['has_on_destroyed']:
            continue  # These go in INJECT file

        raw = read_raw_building_text(b['file'], bname)
        if raw is None:
            lines.append(f"# WARNING: Could not extract raw text for {bname}")
            lines.append("")
            continue

        list_name = "mnt_trade_types" if is_trade else "mnt_building_types"

        tag = ' (trade)' if is_trade else ''
        modified = inject_on_built_hook(raw, bname, list_name)
        lines.append(f"# {bname} uses {pm_name} (REPLACE due to existing on_built){tag}")
        lines.append(f"REPLACE:{modified}")
        lines.append("")

    return "\n".join(lines)


def generate_io_definitions(all_pm_goods):
    """
    Generate mnt_generated_ios.txt:
    Hidden international organizations, one per unique PM profile.
    Each IO hosts an mnt_goods variable map (goods_ref -> per_level_amount),
    populated at creation time via the create_international_organization block.
    """
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# Hidden international organizations used as variable map containers.",
        "# Each IO hosts an mnt_goods variable map for one PM profile.",
        "",
    ]

    for pm_name in sorted(all_pm_goods.keys()):
        io_name = f"mnt_pm_{pm_name}"
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
    """
    Generate mnt_generated_biases.txt:
    Opinion biases for each IO (value = 0 since these are hidden data containers).
    Eliminates 'needs an opinion of other members' warnings.
    """
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# Opinion biases for hidden PM IOs (required by engine, value 0).",
        "",
    ]

    for pm_name in sorted(all_pm_goods.keys()):
        lines.append(f"io_opinion_mnt_pm_{pm_name} = {{")
        lines.append("\tvalue = 0")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_io_localization(all_pm_goods):
    """
    Generate mnt_ios_l_english.yml:
    Localization entries for each IO to suppress auto-generated placeholder warnings.
    """
    lines = ["\ufeffl_english:"]

    for pm_name in sorted(all_pm_goods.keys()):
        io = f"mnt_pm_{pm_name}"
        lines.append(f' {io}: ""')
        lines.append(f' {io}_desc: ""')
        lines.append(f' diplomatic_status_{io}_name: ""')
        lines.append(f' diplomatic_status_{io}_tooltip: ""')
        lines.append(f' {io}_list_who_tt: ""')
        lines.append(f' io_opinion_{io}: ""')

    return "\n".join(lines)


def generate_init_effects(qualifying, all_pm_goods, buildings):
    """
    Generate mnt_generated_init_effects.txt:
    1. mnt_stamp_globals: creates PM IOs + stamps parent building_type->IO map
    2. mnt_init_building: dispatch that adds building_type to location list (game start)
    """
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# IO creation + parent profile lookup + init dispatch",
        "",
    ]

    # â”€â”€ Part 1: Create IOs and stamp parent profile map â”€â”€
    lines.append("# Create PM international organizations and populate their goods maps,")
    lines.append("# then stamp global parent map mnt_profiles (building_type -> IO scope).")
    lines.append("# Called once at game start.")
    lines.append("mnt_stamp_globals = {")
    lines.append("\t# destroy_international_organization requires country scope")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")
    lines.append("\t\tevery_in_global_list = {")
    lines.append("\t\t\tvariable = mnt_all_ios")
    lines.append("\t\t\tsave_temporary_scope_as = io_to_destroy")
    lines.append("\t\t\tprev = {")
    lines.append("\t\t\t\tdestroy_international_organization = { target = scope:io_to_destroy }")
    lines.append("\t\t\t}")
    lines.append("\t\t}")
    lines.append("\t}")
    lines.append("\tclear_global_variable_list = mnt_all_ios")
    lines.append("\tclear_global_variable_map = mnt_profiles")
    lines.append("")
    lines.append("\t# Create all PM IOs and populate goods maps inside creation scope")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")

    for pm_name in sorted(all_pm_goods.keys()):
        goods = all_pm_goods[pm_name]
        io_type = f"international_organization_type:mnt_pm_{pm_name}"
        goods_str = ", ".join(f"{g} {a}" for g, a in goods.items())
        lines.append(f"\t\t# PM: {pm_name} ({goods_str})")
        lines.append(f"\t\tcreate_international_organization = {{")
        lines.append(f"\t\t\ttype = {io_type}")
        for good, amount in goods.items():
            lines.append(f"\t\t\tadd_to_variable_map = {{ name = mnt_goods key = goods:{good} value = {amount} }}")
        lines.append("\t\t}")

    lines.append("\t}")
    lines.append("")
    lines.append("\t# Parent map: building_type -> IO scope")

    for bname, pm_name, _, is_trade, is_foreign in sorted(qualifying, key=lambda x: x[0]):
        bt_ref = f"building_type:{bname}"
        io_ref = f"international_organization:mnt_pm_{pm_name}"
        tag = ' (foreign)' if is_foreign else (' (trade)' if is_trade else '')
        lines.append(f"\tadd_to_global_variable_map = {{ name = mnt_profiles key = {bt_ref} value = {io_ref} }}{f'  # {tag.strip()}' if tag else ''}")

    lines.append("")
    lines.append("\t# Global list of all PM IOs (for monthly cache clearing)")
    for pm_name in sorted(all_pm_goods.keys()):
        io_ref = f"international_organization:mnt_pm_{pm_name}"
        lines.append(f"\tadd_to_global_variable_list = {{ name = mnt_all_ios target = {io_ref} }}")

    lines.append("}")
    lines.append("")

    # â”€â”€ Part 2: Init dispatch for pre-existing buildings â”€â”€
    lines.append("# Init dispatch: add building instance to location list for pre-existing buildings")
    lines.append("# Scope: building (called via every_buildings_in_location)")
    lines.append("# Trade buildings go to mnt_trade_types, regular to mnt_building_types.")
    lines.append("# Foreign and government buildings are skipped (no location list).")
    lines.append("mnt_init_building = {")
    lines.append("\tsave_temporary_scope_as = mnt_bldg")

    first = True
    for bname, pm_name, _, is_trade, is_foreign in sorted(qualifying, key=lambda x: x[0]):
        if is_foreign:
            continue  # Foreign buildings aren't tracked in location lists
        keyword = "if" if first else "else_if"
        first = False
        bt_ref = f"building_type:{bname}"
        list_name = "mnt_trade_types" if is_trade else "mnt_building_types"
        lines.append(f"\t{keyword} = {{")
        lines.append(f"\t\tlimit = {{ building_type = {bt_ref} }}")
        lines.append(f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = scope:mnt_bldg }} }}")
        lines.append("\t}")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def generate_crown_inject(buildings):
    """Generate mnt_generated_crown_inject.txt â€” INJECT blocks for government buildings with crown modifier."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# Crown building modifier for government/military buildings excluded from mnt",
        "",
    ]

    for bname in sorted(GOVERNMENT_BUILDINGS):
        if bname not in buildings:
            continue
        lines.append(f"INJECT:{bname} = {{")
        lines.append(f"\tmodifier = {{")
        lines.append(f"\t\tmnt_crown_building = yes")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)




# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Main
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    print("Parsing production methods...")
    pms = parse_production_methods()
    print(f"  Found {len(pms)} production methods")
    qualifying_pms = {k: v for k, v in pms.items()
                      if not v['no_upkeep'] and not v['has_output'] and v['goods']}
    print(f"  Qualifying PMs (has goods, no no_upkeep, no output): {len(qualifying_pms)}")

    print("\nParsing building types...")
    buildings = parse_all_buildings()
    print(f"  Found {len(buildings)} buildings")

    print("\nClassifying qualifying buildings...")
    qualifying, all_pm_goods = classify(buildings, pms)
    print(f"  Qualifying buildings: {len(qualifying)}")
    print(f"  Unique PM goods profiles: {len(all_pm_goods)}")

    # Count government buildings found in game data
    govt_found = sum(1 for b in GOVERNMENT_BUILDINGS if b in buildings)
    govt_missing = GOVERNMENT_BUILDINGS - set(buildings.keys())
    print(f"  Government buildings excluded: {govt_found}")
    if govt_missing:
        print(f"  WARNING: {len(govt_missing)} government buildings not found in game data: {', '.join(sorted(govt_missing))}")

    # Build reverse map: pm_name -> list of building names
    pm_to_buildings = {}
    for bname, pm_name, _, _, _ in qualifying:
        pm_to_buildings.setdefault(pm_name, []).append(bname)

    # Count categories
    non_foreign = [(b, _, _, t, fg) for b, _, _, t, fg in qualifying if not fg]
    inject_count = sum(1 for b, _, _, _, _ in non_foreign
                       if not buildings[b]['has_on_built'] and not buildings[b]['has_on_destroyed'])
    replace_count = sum(1 for b, _, _, _, _ in non_foreign
                        if buildings[b]['has_on_built'] or buildings[b]['has_on_destroyed'])
    trade_count = sum(1 for _, _, _, is_trade, _ in qualifying if is_trade)
    foreign_count = sum(1 for _, _, _, _, is_foreign in qualifying if is_foreign)
    print(f"  INJECT buildings: {inject_count}")
    print(f"  REPLACE buildings: {replace_count}")
    print(f"  Trade capacity buildings: {trade_count}")
    print(f"  Foreign buildings: {foreign_count}")

    if replace_count > 0:
        replace_buildings = [b for b, _, _, _, fg in qualifying
                            if not fg and (buildings[b]['has_on_built'] or buildings[b]['has_on_destroyed'])]
        print(f"  REPLACE candidates: {', '.join(replace_buildings)}")

    # Generate files
    print("\nGenerating files...")

    inject_code = generate_inject(qualifying, buildings)
    out_path = OUT_BUILDINGS / "mnt_generated_inject.txt"
    out_path.write_text(inject_code, encoding="utf-8-sig")
    print(f"  Wrote {out_path.name}")

    replace_code = generate_replace(qualifying, buildings)
    out_path = OUT_BUILDINGS / "mnt_generated_replace.txt"
    out_path.write_text(replace_code, encoding="utf-8-sig")
    print(f"  Wrote {out_path.name}")

    io_defs = generate_io_definitions(all_pm_goods)
    OUT_IOS.mkdir(parents=True, exist_ok=True)
    out_path = OUT_IOS / "mnt_generated_ios.txt"
    out_path.write_text(io_defs, encoding="utf-8-sig")
    print(f"  Wrote {out_path.name}")

    init_effects = generate_init_effects(qualifying, all_pm_goods, buildings)
    out_path = OUT_EFFECTS / "mnt_generated_init_effects.txt"
    out_path.write_text(init_effects, encoding="utf-8-sig")
    print(f"  Wrote {out_path.name}")

    crown_inject = generate_crown_inject(buildings)
    out_path = OUT_BUILDINGS / "mnt_generated_crown_inject.txt"
    out_path.write_text(crown_inject, encoding="utf-8-sig")
    print(f"  Wrote {out_path.name}")

    biases = generate_io_biases(all_pm_goods)
    OUT_BIASES.mkdir(parents=True, exist_ok=True)
    out_path = OUT_BIASES / "mnt_generated_biases.txt"
    out_path.write_text(biases, encoding="utf-8-sig")
    print(f"  Wrote {out_path.name}")

    loc = generate_io_localization(all_pm_goods)
    OUT_LOC.mkdir(parents=True, exist_ok=True)
    out_path = OUT_LOC / "mnt_ios_l_english.yml"
    out_path.write_text(loc, encoding="utf-8")
    print(f"  Wrote {out_path.name}")

    # Summary
    print("\n=== Summary ===")
    print(f"Total qualifying buildings: {len(qualifying)}")
    print(f"  Regular buildings: {len(qualifying) - trade_count - foreign_count}")
    print(f"  Trade capacity buildings: {trade_count}")
    print(f"  Foreign buildings: {foreign_count}")
    print(f"  Government buildings excluded: {govt_found}")
    print(f"Unique PM goods profiles: {len(all_pm_goods)}")
    print(f"INJECT blocks: {inject_count}")
    print(f"REPLACE blocks: {replace_count}")

    # Count unique goods across all PMs
    all_goods = set()
    for goods in all_pm_goods.values():
        all_goods.update(goods.keys())
    print(f"Distinct maintenance goods: {len(all_goods)} ({', '.join(sorted(all_goods))})")

    print("\n=== PM to Buildings Mapping ===")
    for pm_name in sorted(all_pm_goods.keys()):
        blist = pm_to_buildings.get(pm_name, [])
        goods = all_pm_goods[pm_name]
        goods_str = ", ".join(f"{g}={a}" for g, a in goods.items())
        print(f"  {pm_name} ({len(blist)} buildings): [{goods_str}]")
        for b in sorted(blist):
            src = "inline" if any(bn == b and s == 'inline' for bn, _, s, _, _ in qualifying) else "external"
            tags = []
            if buildings[b].get('has_trade_capacity') and not buildings[b]['is_foreign']:
                tags.append("trade")
            if buildings[b]['is_foreign']:
                tags.append("foreign")
            tag_str = f" ({', '.join(tags)})" if tags else ""
            print(f"    - {b} ({src}){tag_str}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
