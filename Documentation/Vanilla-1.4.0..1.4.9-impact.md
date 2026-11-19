# Vanilla 1.4.0 → 1.4.9 impact on M&T

Report generated 2026-11-19 by the vanilla mirror at `C:\Dev\Projects\paradox\eu5\mod\vanilla`.

| | |
|---|---|
| Range | `v1.4.0-open-beta` (2026-10-01) → `v1.4.9` (2026-11-18) |
| Updates | 9 |
| Updates with at least one hit | 8 |
| Mod checked | `MnT-EU5`, branch `fix/1.4.9` |
| Whole-file overrides affected | 21 distinct files |
| Key-level overrides affected | 175 distinct keys |
| Method | `tools/vanilla.py impact --since 1.4.0-open-beta` followed by inspection of every file and key group |

The key count is deliberately inflated by two patterns: M&T's `INJECT:`-only building caps
(one hit per changed building type) and M&T's intentional wholesale rebalances of child
traits/dhimmi privileges. Those are separated from real actions below.

## Priority summary

| # | Area | Update | Priority | Action |
|---|---|---|---|---|
| 1 | `on_action` overrides drop vanilla additions | 1.4.2 / 1.4.5 / 1.4.7 | **High** | merge HRE setup, cardinal transfer, D009 pulses, Irish pulse |
| 2 | `location_window.gui` / `production_lateralview.gui` | 1.4.1–1.4.8 | **High** | rebase the GUI copies; several UI features break |
| 3 | `promote_culture` rewrite | 1.4.2 | **High** | port visible/finish/AI changes |
| 4 | malaria climate triggers | 1.4.4 | **High** | add semi-arid/subpolar cases |
| 5 | camel mercenary composition | 1.4.8 | **High** | port nobles/tribesmen split |
| 6 | `increase_control_*` Noblesse Oblige gate | 1.4.8 | **High** | add `NOT = { has_reform = ... }` |
| 7 | subject-type changes | 1.4.1 | Medium | add tariff exemptions, cancel flag, diplomatic reputation |
| 8 | `ayuntamientos` sign flip | 1.4.2 | Medium | port `-0.05` + decentralization |
| 9 | dhimmi privilege power nerfs | 1.4.3 | Medium | decide whether to follow vanilla 0.1/0.2/0.33 |
| 10 | `location_templates.txt` raw-material shuffles | 1.4.1 / 1.4.2 / 1.4.3 / 1.4.8 | Medium | M&T full copy masks all of it; decide whether to merge |
| 11 | societal subject loyalty 30 → 15 | 1.4.2 | Medium | decide whether M&T keeps 30 |
| 12 | building `graphical_tags` / category / audio | 1.4.1 / 1.4.2 | Low | add graphical tags to full copies |
| 13 | 1.4.9 six keys | 1.4.9 | Mostly fixed | verify remaining `SimpleContextualFast...` sites |

## 1.4.0 → 1.4.1

16 whole-file overrides, 122 keys.

### Buildings

Vanilla added `graphical_tags` to every production building and changed four rural/common
buildings:

```diff
 mercury_patio = {
 	audio_tier = 3
+	audio_category = industry
-	category = rgo_building_category
+	category = infrastructure_category
```

```diff
 windmill / local_smelters / sawmill = {
+	audio_category = industry
-	category = rgo_building_category
+	category = infrastructure_category
```

M&T already uses `rgo_enhancement_category` and `audio_category = industry` for these
blocks, so the category/audio change is already covered (and 1.4.2 reverts vanilla back to
`rgo_enhancement_category`, matching M&T). M&T's full production copies do **not** have the
new `graphical_tags = { factory_small/medium/large }`; this is cosmetic only.

**Action:** optionally add `graphical_tags` to `production_leather/tools/weapons.txt`.
No gameplay action for category/audio.

### Subject types

Vanilla added:

- `subject_exempt_from_overlord_import_tariffs = yes` and
  `overlord_exempt_from_subject_import_tariffs = yes` to `colonial_nation` and `dominion`.
- `diplomatic_reputation = 0.8` to dominion, fiefdom, hanseatic member, march, tributary,
  uc_bey and vassal acceptance reasons.
- `overlord_can_cancel = yes` for colonial nations.
- A `wont_join_vs_other_appanages...` custom tooltip to vassal.

M&T ships full copies of all of these; none of the new lines are present.

**Action:** add the tariff exemptions, `overlord_can_cancel`, diplomatic reputation lines,
and the vassal tooltip to the M&T copies.

### GUI

`location_window.gui`:

- foreign estate-building flag now also shows when `CanExpandBuilding`.
- upgrade icon visibility includes `IsPlayerBuilding`.
- town-right revoke gets `GetRevokeFirstTownRightConditions` and
  `CanRevokeFirstTownRight`.

`production_lateralview.gui`:

- mass-upgrade condition switches to `CanBuildAnyBuilding` /
  `AreBuildingsUnderConstruction`.
- three text widths 40 → 55.

**Action:** rebase both GUI copies; these are functional UI changes, not cosmetic.

### Map data

`location_templates.txt` reassigns raw materials across Castile/Aragon (549 lines):
`leon wheat→beeswax`, `riano beeswax→wild_game`, `soria beeswax→horses`, etc.
M&T ships a full `location_templates.txt`, so **none of these vanilla rebalances apply**.
Decide whether M&T wants to merge them; otherwise document the intentional divergence.

### Keys

122 keys are almost entirely `INJECT:<building> = { max_levels = ... }` entries in
`mnt_building_caps.txt`. Vanilla changed the building block, so the tool flags the key, but
the injection only adds `max_levels` and applies cleanly.

Actual key-level actions are the subject types above and the GUI/subject file overrides.
`maha_samanta` remains an `INJECT:` and needs no action.

## 1.4.1 → 1.4.2

4 whole-file overrides, 29 keys.

### No action

- `country_base_values`: vanilla doubles `country_child_education` 0.375 → 0.75.
  M&T already has `0.75`.
- `wool` and `horses`: added as vanilla goods. M&T already defines both in
  `MnT_raw_materials.txt`.
- `fishing_village`: vanilla adds `has_river = yes` as an alternative to coastal.
  M&T already has the `OR` and disables the building (`always = no`).
- child traits: vanilla lowers child-education bonuses; M&T deliberately uses its own
  values (`child_prodigy 0.6/0.3`). Confirm this remains intentional.
- `legacy_of_osman`: vanilla changes `global_max_control` to `global_monthly_control`;
  M&T already comments that modifier out deliberately.
- unique buildings / building categories: M&T mostly uses `INJECT:`.

### Action

**`on_game_start` + `on_location_changed_owner` (High).** M&T defines these keys directly
in `MnT_pulse.txt`, replacing vanilla's entire list. Vanilla added:

- HRE setup: `hre_set_ai_diplo_action_cooldown` fan-out for every HRE member.
- Cardinal transfer rewrite: move only a cardinal actually seated in the conquered
  location, and only to a Catholic winner; otherwise clear cardinal variables.

Because M&T replaces the key, neither addition runs. Merge the vanilla effects into
M&T's `on_actions`/effect blocks, or convert the M&T definitions to an additive pattern.

**`ayuntamientos` (Medium).** M&T still has the old:

```diff
-	pop_join_rebel_threshold = 0.05
+	pop_join_rebel_threshold = -0.05
+	monthly_towards_decentralization = societal_value_monthly_move
```

Port both lines; the sign flip changes the privilege from increasing to reducing rebel
participation.

**`promote_culture` (High).** Vanilla rewrote visibility, assimilation target handling,
finish conditions and AI scoring. M&T's `REPLACE:promote_culture` still uses the old
`culture_percentage_in_country >= 0.01` visibility and the old 0.95 finish test. Port the
new block; otherwise AI/visibility behavior diverges.

**`dhimmi_estate` (No action).** Vanilla adds
`ignores_culture_religion_penalties = yes`; M&T already has it.

**`societal_values` (Medium).** Vanilla lowers `subject_loyalty` 30 → 15. M&T still has 30.
Decide whether this is an intentional M&T balance choice.

## 1.4.2 → 1.4.3

4 whole-file overrides, 14 keys.

### Dhimmi privileges

Vanilla cuts every `global_dhimmi_estate_power` value roughly in half to a third
(0.25→0.1, 0.5→0.2, 1.0→0.33, etc.). M&T uses its own values (0.25, 0.2, 0.5), already
lower than the old vanilla but still above the new vanilla. Decide whether to follow the
new baseline.

### Other keys

- `camels`: vanilla adds `demand_only_in_region = mongolia_region` and
  `xinjiang_region`. M&T's `MnT_raw_materials.txt` lacks these two lines.
- `integrate_area` / `integrate_province`: vanilla changes map color max to
  `MAP_COLOR_MAX` and adds `map_mode = select_target_integrate_*`. M&T full copies still
  use `MAP_COLOR_HIGH` and have no map mode.
- `marry_lowborn`: vanilla wraps the close-relative check in a custom tooltip. M&T copy
  lacks it; cosmetic.
- `manufactories_advance`: vanilla adds `unlock_policy = cameralism_policy`. M&T uses
  `INJECT:manufactories_advance`, so it applies cleanly.
- `familial_governor`: vanilla adds `released_when_overlord_conquered = yes`; M&T copy
  lacks it.
- `fiefdom`: vanilla adds a `NOT = { has_reform = tun_strong_familial_governors }` gate;
  M&T copy lacks it.
- `tun_ungovernable_agriculturalists`: vanilla adds an `on_deactivate` modifier; M&T copy
  lacks it.
- `exploration_monthly.10`: M&T's event copy differs; inspect whether the vanilla change
  should be ported.

### GUI

`location_window.gui` changes 96/195 lines (town-rights layout and tooltip flow). M&T's
copy is now several upstream revisions behind; rebase this file as a unit.

`map_data/location_templates.txt` changes two lines; M&T's full copy masks them.

## 1.4.3 → 1.4.4

One key: `malaria`.

Vanilla adds:

```diff
 climate = hot_semi_arid
 climate = cold_semi_arid
 ...
 climate = subpolar
```

M&T's `MnT_malaria.txt` uses `arid_climate_trigger`,
`cold_arid_climate_trigger` and `mediterranean_climate_trigger`, and treats continental/
arctic as zero. It does not include the new semi-arid/subpolar climates.

**Action (High):** add hot/cold semi-arid to the malaria multiplier group and subpolar to
the zero-multiplier group.

## 1.4.4 → 1.4.5

Two keys: `monthly_country_pulse`, `yearly_country_pulse`.

D009 adds new files that define both keys:

```text
monthly_country_pulse = { random_events = { d009_sephardi_catastrophe.8/9 } }
yearly_country_pulse = { random_events = { goods_camels.*, d009_* ... } }
```

M&T also defines both keys in `MnT_pulse.txt`. If M&T's definition wins, all D009 pulses
are suppressed; if the game merges, they may be duplicated.

**Action (High):** merge the D009 events into M&T's pulse lists, or restructure M&T to use
additive on_action entries so DLC pulses survive.

## 1.4.5 → 1.4.6

No file or key impact.

## 1.4.6 → 1.4.7

One file, one key.

- `yearly_country_pulse`: vanilla adds `yearly_flavor_ire_pulse` and moves the five
  `ireland.10–50` events into it. M&T's yearly pulse list does not include the new pulse,
  so those Irish events stop firing.
- `location_window.gui`: 51/6-line UI change; rebase with the other GUI updates.

**Action:** add `yearly_flavor_ire_pulse` to M&T's yearly list; rebase GUI.

## 1.4.7 → 1.4.8

5 files, 18 keys.

- **Camel units (High):** all camel unit types change mercenary composition from
  `tribesmen × 0.3` to `nobles × 0.3` plus `tribesmen × 0.01`. M&T's full
  `3_camel_units.txt` still uses the old composition; port it to all 13 units.
- **`increase_control_province` / `_area` (High):** vanilla adds
  `NOT = { has_reform = government_reform:noblesse_oblige_reform }` to `potential`.
  M&T's `REPLACE:` copies lack the gate, so the action remains available under the
  reform that is supposed to disable it.
- **`appanage` (Low):** vanilla wraps `nav_appanage_rights_granted` in a custom tooltip
  in three places. M&T copy lacks the wrappers.
- **`on_location_changed_owner` (High):** 1.4.8 adds cardinal `employer` handling and
  `cardinal_awaiting_new_owner`; M&T's plain key override does not run it. Merge with the
  1.4.2 cardinal changes.
- **`location_window.gui` / `map_markers.gui` / `location_templates.txt`:** rebase/mask as
  above.
- **`dhimmi_abrahamic_communities`:** vanilla changes it again; M&T copy should be checked
  against the new block.

## 1.4.8 → 1.4.9

4 files, 6 keys. These are the items already covered by the previous 1.4.9 report; the
current branch has ported most of them:

| Item | Status on `fix/1.4.9` |
|---|---|
| `country_base_values` + dhimmi noble marriage | **fixed** — line present |
| `tributary` `trigger_if { exists = scope:target }` | **fixed** — present |
| `D008_pronoia` DLC gate | **fixed** — `has_dlc` present |
| `kilwan_merchant_settlement` pottery guild | **fixed** — pottery removed |
| `dismantle_fortifications` AI reason label | **fixed** — `desc` present |
| `production_lateralview.gui` fast tooltip | **partially** — 2 fast sites adopted, 7 old-type sites remain; optional |
| `maha_samanta` | no action — M&T only injects |

No further action needed for the six key hits beyond the optional fast-tooltip cleanup.

## Checklist

- [ ] Merge HRE setup + cardinal transfer into M&T's `on_game_start` / `on_location_changed_owner`
- [ ] Merge D009 monthly/yearly pulses into M&T's pulse lists
- [ ] Add `yearly_flavor_ire_pulse` to M&T's yearly list
- [ ] Rebase `location_window.gui` and `production_lateralview.gui`
- [ ] Port the 1.4.2 `promote_culture` rewrite
- [ ] Add semi-arid/subpolar climates to malaria
- [ ] Port camel mercenary composition
- [ ] Add Noblesse Oblige gate to `increase_control_*`
- [ ] Add subject tariff/cancel/diplomatic-reputation changes
- [ ] Port `ayuntamientos` sign flip/decentralization
- [ ] Decide on dhimmi power nerfs and societal subject loyalty 30 vs 15
- [ ] Decide whether to merge vanilla raw-material changes into M&T's `location_templates.txt`
- [ ] Add `graphical_tags` to production building copies (cosmetic)
- [ ] Port camels demand regions, integrate map modes, appanage tooltips, familial/fiefdom/tun changes
- [ ] Optional: remaining `SimpleContextualFastStringPairTooltipType` sites

## Reproduce

```powershell
cd C:\Dev\Projects\paradox\eu5\mod\vanilla
python tools/vanilla.py impact "C:\Dev\Projects\paradox\m&t\eu5\MnT-EU5" --since 1.4.0-open-beta
```

Full tool output is in `mnt-impact-1.4.0..1.4.9.txt` in the workspace.
