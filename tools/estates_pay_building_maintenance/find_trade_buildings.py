#!/usr/bin/env python3
"""
Parse EU5 building definitions and identify all buildings that provide trade capacity.
Compares against the mod's tracked building list to show overlap.
"""

import re
from pathlib import Path

GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Europa Universalis V\game")
BUILDING_DIR = GAME_DIR / "in_game/common/building_types"
MOD_DIR = Path(__file__).resolve().parent.parent.parent

TRADE_MODIFIERS = {"local_merchant_capacity", "merchant_capacity_from_building"}


def parse_buildings(filepath: Path) -> dict:
    """
    Parse a building_types file and return a dict of building_name -> {properties}.
    Simple brace-depth parser that tracks top-level blocks and their modifier sub-blocks.
    """
    buildings = {}
    text = filepath.read_text(encoding="utf-8-sig")

    # Remove comments
    text = re.sub(r"#[^\n]*", "", text)

    depth = 0
    current_building = None
    current_block = None  # e.g. "modifier", "market_center_modifier"
    block_depth = 0

    i = 0
    while i < len(text):
        ch = text[i]

        if ch == "{":
            depth += 1
            if depth == 1:
                # Starting a top-level building block — find the name before this brace
                before = text[:i].rstrip()
                m = re.search(r"(\w+)\s*=\s*$", before)
                if m:
                    current_building = m.group(1)
                    buildings[current_building] = {"modifiers": {}, "file": filepath.name}
            elif depth == 2 and current_building:
                # Starting a sub-block inside a building — check if it's a modifier block
                before = text[:i].rstrip()
                m = re.search(r"(\w+)\s*=\s*$", before)
                if m and m.group(1) in ("modifier", "market_center_modifier"):
                    current_block = m.group(1)
                    block_depth = depth
            i += 1

        elif ch == "}":
            if depth == 1:
                current_building = None
                current_block = None
            elif current_block and depth == block_depth:
                current_block = None
            depth -= 1
            i += 1

        elif current_block and depth == block_depth + 0:
            # We're directly inside a modifier block — look for key = value
            m = re.match(r"\s*(\w+)\s*=\s*([^\s{}\n]+)", text[i:])
            if m:
                key = m.group(1)
                val = m.group(2)
                if key in TRADE_MODIFIERS:
                    buildings[current_building]["modifiers"][key] = float(val)
                i += m.end()
            else:
                i += 1
        else:
            i += 1

    return buildings


def get_tracked_buildings() -> set:
    """Read the mod's tracked building list from generated files."""
    tracked = set()
    for fname in ["mnt_generated_inject.txt", "mnt_generated_replace.txt"]:
        fpath = MOD_DIR / "in_game/common/building_types" / fname
        if fpath.exists():
            for line in fpath.read_text(encoding="utf-8-sig").splitlines():
                m = re.match(r"^(?:INJECT|REPLACE):(\w+)\s*=", line)
                if m:
                    tracked.add(m.group(1))
    return tracked


def main():
    tracked = get_tracked_buildings()
    trade_buildings = {}

    for filepath in sorted(BUILDING_DIR.glob("*.txt")):
        buildings = parse_buildings(filepath)
        for name, data in buildings.items():
            if data["modifiers"]:
                trade_buildings[name] = data

    print(f"Found {len(trade_buildings)} buildings with trade capacity modifiers\n")

    # Split by tracked vs not
    tracked_trade = {k: v for k, v in trade_buildings.items() if k in tracked}
    untracked_trade = {k: v for k, v in trade_buildings.items() if k not in tracked}

    print(f"TRACKED BY MOD ({len(tracked_trade)}):")
    for name in sorted(tracked_trade):
        mods = tracked_trade[name]["modifiers"]
        mod_str = ", ".join(f"{k} = {v}" for k, v in mods.items())
        print(f"  {name:40s} {mod_str:40s} ({tracked_trade[name]['file']})")

    print(f"\nNOT TRACKED ({len(untracked_trade)}):")
    for name in sorted(untracked_trade):
        mods = untracked_trade[name]["modifiers"]
        mod_str = ", ".join(f"{k} = {v}" for k, v in mods.items())
        print(f"  {name:40s} {mod_str:40s} ({untracked_trade[name]['file']})")


if __name__ == "__main__":
    main()
