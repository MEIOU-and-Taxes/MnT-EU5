# MnT EPBM — Estates Pay Building Maintenance

A port of the EPBM (Estates Pay Building Maintenance) subsystem into MnT.
Estates pay their share of every building's maintenance cost, charged each
tick via scaled gold transfers — the gameplay goal is that estates carry
some of the upkeep burden that would otherwise fall entirely on the
treasury. The crown side of the ledger (i.e. why the crown's own bill
shrinks) is handled separately in MnT by a base building-maintenance
discount driven by crown power, not by this subsystem.

This document covers:

1. What the subsystem does at runtime.
2. The moving parts (IOs, variable maps, on_actions, etc.).
3. The generator script that wires it all up.
4. Time complexity for each phase of the generator.
5. File system risks and safety gates.
6. How to operate the script locally and in CI.

---

## 1. Runtime behaviour

Buildings are split into three categories, each with its own maintenance
distribution rule:

| Category | Split rule | Notes |
| --- | --- | --- |
| **Regular** buildings | Split across estates by that estate's local pop-tax burden, weighted by inverted control. | The default bucket. |
| **Trade-capacity** buildings (no output PM) | Split across estates by global estate power, independent of control. | Mirrors how trade profit is distributed. |
| **Foreign** buildings | Split across estates by global estate power. | Iterated from country scope — no location list tracking. |

Some buildings are **excluded** from estate maintenance and paid by the crown
directly — forts, barracks, palaces, government buildings, admiralties, etc.
The exclusion list lives in `tools/MnT_epbm_exclusions.txt`.

Estate-assigned buildings (set via the building's `estate = ...` field) are
charged entirely to their owning estate instead of being split.

---

## 2. Moving parts

The design has to work around several engine limitations:

- **No script-side "get building maintenance cost"** — we recompute the cost
  every tick from production-method goods and current market prices.
- **No script-side "iterate a PM's inputs"** — we extract them at build time
  (hence the Python generator) and stash them in IO-backed variable maps.
- **Variable maps don't nest** — we use lightweight hidden
  `international_organization` instances as variable-map containers. Each IO
  represents one maintenance production method and stores:
  - a **goods map** (good → quantity needed per building level), set once;
  - a **cost cache** (market → per-level cost), refreshed monthly so the
    script-side cost lookups remain O(1) amortised across markets.
- **Dynamic PM selection per building** — the global `MnT_epbm_profiles` map
  is keyed by `production_method`, not by `building_type`. At runtime each
  building uses `ordered_production_method_of_building` with
  `order_by = production_method_profit` and `position = 0` to pick its
  highest-profit active PM that we know about (`limit =
  is_key_in_global_variable_map`). That chosen PM feeds into the profile
  map to fetch the IO, the IO yields the cached cost, and the cost is
  scaled by `building_level`. This means buildings with multiple possible
  maintenance PMs get charged against whichever one is active, not a
  statically-picked "first match" from build time.
- **Per-country iteration is expensive** so we keep a cached index:
  - each location maintains a `MnT_epbm_buildings` variable list of its
    tracked buildings;
  - each country maintains a `MnT_epbm_locations` variable list of its
    locations that have at least one tracked building.
- **Estate assignment** remains keyed by `building_type` (via
  `MnT_epbm_estate_map`) since it is a property of the building, not the
  PM. The runtime checks that map per building and, if the building is
  estate-assigned, charges the full cost to the owning estate instead of
  splitting by estate power.

### Cadence

- **Game start** — `MnT_epbm_initialize_all` runs `MnT_epbm_full_rebuild`:
  stamps the global maps, scans every location, seeds each country's list,
  calculates the first month's cost, and charges it.
- **Monthly (player)** — full recalculate + charge.
- **Monthly (AI)** — charge only, using the cached rates from the last
  yearly recalc. Keeps the monthly cost flat even for large empires.
- **Yearly (AI)** — full recalculate.
- **Yearly (every country)** — decade counter: every 10 years, re-scan all
  owned locations and rebuild the `MnT_epbm_locations` list from scratch as
  a drift-correction safety net.
- **Weather pulse (monthly, global)** — clear every IO's cost cache so next
  month's prices start fresh.
- **On location owner change** — move the location between the old and new
  owner's `MnT_epbm_locations` list so the index stays accurate.
- **On first-level built / last-level destroyed** — injected hooks keep the
  location's `MnT_epbm_buildings` list and the owner's `MnT_epbm_locations`
  list up to date without a full rescan.

### Mod-state anchor

The upstream EPBM mod used Bouvet Island as a mod-state anchor location — a
location_modifier + version variable pair that detected mod remove/re-add
and version upgrades. **The MnT port removes this.** Full rebuilds now only
run once at game start plus the 10-year decade rebuild. If you need to
re-enable version tracking, reintroduce an anchor location + modifier and
add a `MnT_epbm_version_check` on_action.

---

## 3. The generator script

All of the above depends on two generated things:

1. A global `MnT_epbm_profiles` map from every maintenance `production_method`
   to its IO.
2. `on_built` / `on_destroyed` hooks on each qualifying building_type so the
   per-location tracking lists stay current as buildings come and go.

Both are produced by `tools/MnT_epbm_generator/MnT_generate_building_hooks.py`,
which reads vanilla EU5 + MnT building_types and production_methods,
catalogs every maintenance PM it finds, and writes the corresponding script.

### Settings (config file)

All tunables live in `tools/MnT_epbm_generator/MnT_epbm_generator_config.py`.
Edit that file instead of passing CLI arguments — the script takes no flags.

| Setting | Purpose |
| --- | --- |
| `PREFIX` | Identifier prefix for every generated name. Default `MnT_epbm`. |
| `VANILLA_IN_GAME_CANDIDATES` | Ordered list of paths tried when resolving vanilla. First existing hit wins. |
| `MOD_IN_GAME` | Path to the MnT dev mod's `in_game/` directory. |
| `OUTPUT_ROOT` | Where generated non-building files are written (creates subdirs under it). |
| `REQUIRE_CONFIRMATION` | Interactive y/N gate before rewriting files. |
| `REQUIRE_CLEAN_GIT` | Abort if building_types has uncommitted changes. |

### What it writes

| Path (under `OUTPUT_ROOT`) | Contents |
| --- | --- |
| `in_game/common/scripted_effects/MnT_epbm_generated_init_effects.txt` | `MnT_epbm_stamp_globals` (IO creation + global maps) and `MnT_epbm_init_building` (per-building dispatch). |
| `in_game/common/international_organizations/MnT_epbm_generated_ios.txt` | One hidden IO per maintenance PM profile. |
| `in_game/common/biases/MnT_epbm_generated_biases.txt` | Zero-value `io_opinion_*` biases required by the engine. |
| `main_menu/localization/english/MnT_epbm_ios_l_english.yml` | Empty loc entries for every generated IO so the engine doesn't warn. |
| `in_game/common/building_types/MnT_epbm_generated_inject.txt` | INJECT: hook overrides for vanilla-only buildings that have no existing `on_built`. Only written if needed. |
| `in_game/common/building_types/MnT_epbm_generated_replace.txt` | REPLACE: hook overrides for vanilla-only buildings that already ship with an `on_built` / `on_destroyed`. Only written if needed. |

Additionally, MnT's **own** `building_types/*.txt` files are **rewritten in
place** to add or extend `on_built` / `on_destroyed` blocks on every
qualifying building. Every file that gets touched receives a top-of-file
warning banner noting it is partially generated.

All generated files carry a "DO NOT EDIT — regenerated by the script" banner
at the top.

### Classification rule

The generator runs two independent passes:

**PM catalog.** Every production method that has goods inputs, is not
flagged `no_upkeep`, and produces no output becomes a catalog entry and
gets a dedicated IO. Inline `unique_production_methods` must additionally
carry `category = building_maintenance`; shared externals from
`unsorted_building_inputs.txt` are assumed to be maintenance by convention.
Inline definitions override externals of the same name (mirrors engine
load-order semantics).

**Qualifying buildings.** Any building that references at least one PM in
the catalog (via `possible_production_methods` or
`unique_production_methods`) is qualifying. That's the set we hook with
`on_built` / `on_destroyed` and add to the game-start init dispatch.
Runtime picks the active PM per building dynamically — there is no
build-time "best PM per building" selection. MnT does not use an
exclusion list.

---

## 4. Time complexity

Let:

- **B** = total building types across vanilla + mod (currently ~250)
- **F** = number of building_types *files* in mod dir (currently ~10)
- **P** = total production methods (currently ~130)
- **Q** = qualifying buildings (currently ~180)
- **G** = distinct PM goods profiles (currently ~90)
- **S** = total bytes across all building_types files

| Phase | Complexity | Notes |
| --- | --- | --- |
| Parse PMs | O(P) | Single-pass tokenize + parse of `unsorted_building_inputs.txt`. |
| Parse building_types | O(S) | One tokenize + parse pass per file. File IO dominates. |
| Classify | O(B · P_avg) | P_avg ≈ number of PM refs per building (~3). Effectively linear in B. |
| Generate init effects / IOs / biases / loc | O(Q + G) | Linear in qualifying-buildings + unique profiles. |
| In-place hook rewrite per file | O(s · q) | s = file bytes, q = qualifying buildings in that file. The re-tokenize after strip is the dominant cost; q is small. |
| In-place rewrite total | O(S + Q) | Summed across files, amortises to linear in total input size + qualifying count. |
| Vanilla-only INJECT/REPLACE generation | O(Q_van · s_van) | Q_van = qualifying vanilla-only buildings; s_van = affected vanilla file bytes. Small in practice (most buildings live in MnT overlays). |
| Brace-balance check | O(s) per file | Byte-by-byte scan with quote awareness. |
| git status check | O(1) shell call | Scoped to the building_types directory. |

End-to-end the script is dominated by file IO; empirically a full run on the
current MnT state is well under a second on any modern machine.

---

## 5. File system risks

This script is **destructive**. It rewrites files inside
`MOD_IN_GAME/common/building_types/` in place, and deletes its own stale
generator outputs (`MnT_epbm_generated_inject.txt`,
`MnT_epbm_generated_replace.txt`) when they are no longer needed.

The destructive surface is deliberately bounded:

- **Only** files inside `MOD_IN_GAME/common/building_types/` are rewritten.
  The script never touches vanilla, never touches the deployed mod, never
  touches files outside the configured `MOD_IN_GAME`.
- **Only** stale files whose basename exactly matches
  `{PREFIX}_generated_inject.txt` or `{PREFIX}_generated_replace.txt` inside
  `OUTPUT_ROOT/in_game/common/building_types/` are deleted. These file names
  are owned by the generator; you should never create a file with this name
  by hand.
- Every in-place rewrite goes through a **brace-balance check** before
  hitting disk. If the rewrite would leave a file with unbalanced braces,
  the write is skipped and the script logs an error.
- Every rewritten file keeps (or gains) a top-of-file warning banner
  naming the generator. Missing the banner does not crash the script, but
  its presence is how the generator (and humans) know the file is managed.

### Safety gates before any writes happen

1. **Vanilla path resolution** — if no candidate from
   `VANILLA_IN_GAME_CANDIDATES` exists and contains a `common/building_types`
   directory, the script aborts with a pointer at the config file.
2. **Git clean check** — if `REQUIRE_CLEAN_GIT` is on, the script runs
   `git status --porcelain` scoped to the building_types dir and aborts if
   anything is dirty. Override with `REQUIRE_CLEAN_GIT = False` at your own
   risk.
3. **Interactive confirmation** — if `REQUIRE_CONFIRMATION` is on, the
   script prints a warning banner and waits for the user to type `yes`.
   Bypass with the `MNT_EPBM_CI=1` environment variable or by flipping
   the config flag.

### What to do if something goes wrong

1. `git status` inside the mod to see which files were rewritten.
2. `git diff -- <path>` to review the damage.
3. `git checkout -- <path>` to roll back.
4. If a classification error is the root cause, fix the offending building's
   production method definition (its `category` should not be set to
   `building_maintenance` if you don't want it tracked) and rerun.

### If you need to edit a hooked building

If you want to hand-modify one of the buildings whose file is partially
generated, **move it into a new .txt file first** (inside the same
`building_types/` directory). The generator only rewrites files that
currently contain a qualifying building, so relocating the building out of
its current file takes that file off the generator's radar entirely.

---

## 6. Operating the script

### Local development

```bash
cd "~/.../Europa Universalis V/mod/.dev-mods/MnT-EU5 Development"
git add -A && git commit -m "WIP: pre-generator snapshot"
python3 tools/MnT_epbm_generator/MnT_generate_building_hooks.py
# -> review the console output, answer 'yes' to the confirmation prompt
# -> verify with `git diff` that only the expected files changed
```

If you want the generator to use a different vanilla install or a different
MnT path, edit `tools/MnT_epbm_generator/MnT_epbm_generator_config.py` —
not the script.

### CI guardrail: check mode

Setting `MNT_EPBM_CHECK=1` turns the generator into a read-only validator:
it runs the full pipeline, compares every proposed write against the file
on disk, and exits with a status code based on the result:

| Exit code | Meaning |
| --- | --- |
| 0 | Tree is in sync — no diffs, nothing to do. |
| 1 | Script or config error (bad path, parse failure, etc.). |
| 2 | Drift detected — the tree needs the generator to be rerun. |

Check mode skips both the git-clean and the interactive confirmation
gates because it never touches the filesystem. Typical GitHub Actions
step:

```yaml
- name: Verify MnT EPBM generator is in sync
  env:
    MNT_EPBM_CHECK: "1"
  run: python3 tools/MnT_epbm_generator/MnT_generate_building_hooks.py
```

If a PR adds a new building to a hooked file without rerunning the
generator, this step fails with output like:

```
=== CHECK FAILED: 5 file(s) out of sync ===
  [changed ] in_game/common/biases/MnT_epbm_generated_biases.txt
  [changed ] in_game/common/building_types/town_buildings.txt
  [changed ] in_game/common/international_organizations/MnT_epbm_generated_ios.txt
  [changed ] in_game/common/scripted_effects/MnT_epbm_generated_init_effects.txt
  [changed ] main_menu/localization/english/MnT_epbm_ios_l_english.yml

Run the generator locally and commit the result:
  python3 tools/MnT_epbm_generator/MnT_generate_building_hooks.py
```

### Unattended / CI write mode

If you want CI to actually regenerate and commit back (instead of
blocking the PR), set `MNT_EPBM_CI=1` so the interactive confirmation is
skipped, then run the script normally and commit any resulting diff:

```yaml
- name: Regenerate and commit MnT EPBM hooks
  env:
    MNT_EPBM_CI: "1"
  run: |
    python3 tools/MnT_epbm_generator/MnT_generate_building_hooks.py
    git config user.name  "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add -A
    git diff --cached --quiet || git commit -m "chore: regenerate MnT EPBM hooks"
```

The git-clean check remains in force in write mode — the generator will
fail the job if any uncommitted change is sitting in `building_types/`
before it runs, which is the expected behaviour inside a clean CI
checkout.

### Strip mode

The strip-mode implementation was removed from this port. If you need to
remove every `MnT_epbm_*` hook from the building files, use the upstream
EPBM repo's `generate_building_hooks.py --strip ...` (with `--prefix
MnT_epbm`) or `git checkout -- building_types/` after reverting the
relevant commits.
