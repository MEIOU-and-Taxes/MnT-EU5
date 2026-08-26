# Location Wealth (GDP and Wages): Systems Reference

Technical reference for the location wealth system, ported into MnT from the GDP and Wages mod with the `mnt_wealth_` prefix. For how the economy works as a game system, see the GDP and Wages mod's README.md.

The Estate_tooltip rows this system adds (estate investment into locations, asset seizure) live in the merged override in `in_game/gui/shared/epbm_government_tooltips.gui`, alongside EPBM's maintenance rows.

---

## Code Layout

| File | Domain |
|------|--------|
| `mnt_wealth_load_balancer.txt` | Load balancer and global location index |
| `mnt_wealth_dispatchers.txt` | Dispatchers: economy bootstrap, estate iterators, monthly and yearly location passes |
| `mnt_wealth_wages.txt` | Wage rates and per-estate wage income |
| `mnt_wealth_shares.txt` | Wealth pool seeding, arriving wealth, ownership drift, absent estate release |
| `mnt_wealth_gdp_survey.txt` | GDP survey, building classification, estate power, national raw power |
| `mnt_wealth_investment_level.txt` | Yearly investment level from pool, fractional level, modifier application, desired wealth |
| `mnt_wealth_investment_spending.txt` | Monthly and yearly investment progress, estate upkeep computation |
| `mnt_wealth_national_flow.txt` | Savings valves, seizure demand, per-location flow share, seizure from liquid and invested wealth |
| `mnt_wealth_national_totals.txt` | National GDP and raw power maintenance, owner-change transfer |
| `mnt_wealth_debug.txt` | Console-only verification: GDP drift, raw power drift, location consistency |
| `mnt_wealth_looting.txt` | Occupation looting: liquid wealth, invested wealth, resistance, payout |
| `mnt_wealth_map_modes.txt` | Map mode color band updates |
| `mnt_wealth_sized_modifiers.txt` | Modifier rounding and redraw |
| `mnt_wealth_api.txt` | Public effects for other mods |

---

## Wiring

`mnt_wealth_hardcoded.txt` registers with engine on_actions:

| Hook | Handler |
|------|---------|
| `on_game_start_after_lobby` | `mnt_wealth_initialize_economy` |
| `monthly_country_pulse` | `mnt_wealth_monthly_country_pulse` |
| `weather_monthly_pulse` | `mnt_wealth_weather_monthly_pulse` |
| `on_location_occupied` | `mnt_wealth_on_location_occupied` |
| `on_siege_won` | `mnt_wealth_on_siege_won` |
| `on_location_changed_owner` | `mnt_wealth_on_location_changed_owner` |
| `on_new_country_formed` | `mnt_wealth_on_new_country_formed` |
| `on_annexed` | `mnt_wealth_on_country_annexed` |
| `on_civil_war_annexed` | `mnt_wealth_on_country_civil_war_annexed` |
| `on_civil_war_won` | `mnt_wealth_on_civil_war_won` |
| `on_civil_war_lost` | `mnt_wealth_on_civil_war_lost` |

`on_location_occupied` and `on_siege_won` split capture by fort: a location without one changes hands on the first, a location with one on the second once its siege ends. Both hand off to `mnt_wealth_loot_captured_location`. Neither fires for every location the engine hands over, so some captures go unlooted.

Resolving a civil war resets the winner's variable maps while its plain variables survive. Each civil war handler rebuilds the winner's national raw power map from its locations. In the rebel-won resolution (`on_civil_war_lost`, root = the losing parent, `scope:winner` = the rebels; `on_civil_war_won` never fires there) the reset lands after every hook and wipes even that rebuild, so the handler also schedules `mnt_wealth_economy.31` one day later.

Events in `mnt_wealth_economy_events.txt`:

| Event | Fires | Purpose |
|-------|-------|---------|
| `mnt_wealth_economy.10` | Monthly per country | Set national savings valves for all estates |
| `mnt_wealth_economy.21` | Monthly per country | Load-balanced monthly location tick (human locations, cycle 1) |
| `mnt_wealth_economy.22` | Monthly per country | Load-balanced GDP survey (cycle 60) and yearly location tick (cycle 12), all locations |
| `mnt_wealth_economy.30` | 1 day after owner change | Settle investment and resurvey estate power under new owner |
| `mnt_wealth_economy.31` | 1 day after civil war annexation | Rebuild the winner's national raw power once the engine's map reset is over |

`.21` and `.22` carry no triggers: workers are threads sweeping the location indices, so a worker's own holdings are irrelevant, and any entry condition the balancer's reindex does not share silently drops that worker's slice of the chunk.

---

## Timing

Three load-balanced passes via the load balancer:

| Pass | Event | Index | Cycle | Scope |
|------|-------|-------|-------|-------|
| Monthly | `.21` | `mnt_wealth_human_location_index` | 1 month | Player-held locations |
| Yearly | `.22` | `mnt_wealth_location_index` | 12 months | All owned locations |
| GDP survey | `.22` | `mnt_wealth_location_index` | `mnt_wealth_gdp_cycle_months` (60) | All owned locations |

The world tick on `weather_monthly_pulse` expires the building-type cache. The two audit effects (`mnt_wealth_verify_national_gdp`, `mnt_wealth_verify_locations`) run on demand from the console.

Player locations compute wages and investment spending monthly. AI locations skip the monthly loop and use a closed-form yearly shortcut; the interface reconstructs current values for display.

### Load balancer

The first balancer call each month reindexes every country (`every_country`, not the landed subset: the monthly pulse reaches countries the landed iterator never yields, and every worker that can pulse must hold an index). Each month claims one chunk of the index (`chunk = index_size / CYCLE`). The first `WORKERS` countries by `mnt_wealth_country_index` split that chunk evenly. Which country processes which location carries no gameplay meaning.

The dispatcher is index-agnostic: a call site passes `INDEX_ACCESSOR` (a wrapper effect that scopes to the entry at the cursor), `INDEX_SIZE` (the index's count variable), and a `PASS_KEY` unique to that call site, which keys the frozen chunk size so passes never share a chunk-size slot. Any dense global index with a count variable can ride it. Up to 512 countries work each pass.

A dispatched `EFFECT` may bundle several sub effects that want the same index and cycle. The yearly pass dispatches `mnt_yearly_location_pass`, which runs the wealth yearly tick, the centers of importance scoring (`calc_location_center_scores`), and the AI building maintenance pricing (`epbm_price_location_buildings`) in one sweep. The centers ranking reads those cached scores once per cycle: `mnt_centers.2` fires one day after the monthly pulse and runs `mnt_rank_centers` (in `MnT_centers_ranking.txt`) in the twelfth cycle month, cleaning last year's winners through the `mnt_center_holders` global list instead of sweeping the world.

EPBM's AI path rides the same sweep: each AI location caches its domestic building maintenance (`epbm_loc_shared_cost`, `epbm_loc_crown_cost`, up to 12 months stale), estate-owned and foreign buildings are repriced yearly per country (`epbm_calculate_estate_and_foreign`; estate buildings are priced from the estate side, where `every_building_owned_by_estate` carries the ownership the engine already tracks), and the monthly charge first sums the caches with a light `every_owned_location` pass (`epbm_aggregate_maintenance`). The player path still recalculates exactly, monthly.

`EFFECT` must never rewrite the index it sweeps. For the location indices that means no colonizing or decolonizing: either moves entries between slots while the cursor is reading them.

### Indices

`mnt_wealth_location_index` (global map): all owned locations. Appended on colonization, swap-removed on decolonization.

`mnt_wealth_human_location_index` (global map): player-held locations. Rebuilt whole each month because no on_action fires when a country gains or loses a player.

---

## Passes, Step by Step

What each pass does, in the order it does it. Names are the dispatchers and
workers in the code.

### Monthly, per country

1. **Set the savings valves** (`mnt_wealth_economy.10` → `mnt_wealth_set_national_savings_valves`):
   for each estate, compare its treasury gold to its savings goal, update its
   seizure demand, and set one signed monthly flow. The treasury moves opposite
   to the flow in the same step.
2. **Run the monthly location tick** (`mnt_wealth_economy.21`, human locations, load balanced).
3. **Run the GDP survey and yearly tick** (`mnt_wealth_economy.22`, all locations, load balanced).

### Monthly location tick (human locations) — `mnt_wealth_location_month`

1. **Calculate wages** (`mnt_wealth_set_location_wages`): wage rate from modifiers,
   total wages from the cached GDP, and the wage burden modifier on the location.
2. **Collect estate income** (`mnt_wealth_estate_month` per estate): each estate's kept
   share of the wages, plus its share of the national flow (positive payout or
   negative seizure).
3. **Change wealth** (`mnt_wealth_apply_arriving_wealth`): arriving gold lands in the
   wealth pool and the ownership shares are recomputed from holdings.
4. **Spend on investment** (`mnt_wealth_invest_estate_wealth` per estate): each estate
   pays its share of the pool times the investment rate, upkeep is charged, and
   the net banks as since-review progress. The pool loses what was spent.
5. **Raise the map mode ceiling** if the pool outgrew it.

### Yearly location tick (all locations) — `mnt_wealth_location_year`

1. **AI locations only**: set wages, then run the whole year of investment in one
   closed-form pass (`mnt_wealth_set_ai_yearly_investment`).
2. **Settle the accumulators** (`mnt_wealth_settle_investment_accumulators`): the
   year's paid totals become per-estate progress, and the accumulated national
   flow is applied to the pool.
3. **Change investment levels** (`mnt_wealth_update_investment_levels`): release
   departed estates and redistribute what they held, credit progress to each
   estate's lifetime pool, then recompute its level, its desired wealth, and its
   sized investment or neglect modifier.
4. **Drift the wealth shares** toward each estate's cached power and rescale the
   share sum.
5. **AI locations only**: recompute the kept-wage display totals.
6. **Resurvey estate power** (`mnt_wealth_resurvey_estate_data`): take the location's
   raw power off the national map, survey it fresh, put it back on.

### GDP survey (every `mnt_wealth_gdp_cycle_months`, all locations) — `mnt_wealth_survey_location`

1. **Recompute local GDP** (`mnt_wealth_update_local_gdp`): rediscover the goods the
   location produces, price them in its market, and sum the value. The owner's
   national total loses the old GDP first and gains the new one after.
2. **Resurvey estate power** (`mnt_wealth_survey_estate_data`): divide the power
   modifiers back out of the engine's estate power, add slave heads back in,
   store raw and relative power, and recompute desired wealth.

### Event-driven

- **Owner change**: move the location's GDP and raw power to the new owner the
  same tick; one day later settle investment and resurvey under the new owner
  (`mnt_wealth_economy.30`).
- **Occupation or siege won**: loot the liquid and invested wealth, reduced by
  looting resistance, and pay the occupier's estates and treasury
  (`mnt_wealth_loot_captured_location`).
- **Civil wars and annexation**: clear the annexed country's totals and rebuild
  the winner's national raw power map once the engine's map reset is over.
- **Colonization and decolonization**: add or remove the location in the global
  location index.

---

## Formulas

### Wages

```
wage_rate = max(local_wage_modifier + global_wage_modifier, minimum_wage)
local_wages = wage_rate * cached_gdp
```

The wage rate is applied as a `mnt_wealth_wage_burden` production efficiency modifier, rounded to multiples of `mnt_wealth_wage_rounding_factor`.

### Ownership shares

```
holdings = old_share * old_pool + arriving_gold      per estate
new_share = holdings / holdings_total
```

Dividing by the holdings total (never the pool) keeps the shares summing to
one whole pool by construction. A settle that drains the whole pool leaves
the old shares standing. The yearly drift moves each on-roll estate's share
toward its cached relative power; because the roll is up to a year stale,
that pass can leave the sum a few percent above one (bounded by the drift
rate), and `mnt_wealth_set_local_wealth_share_sum` rescales every share by 1/sum in
the same frame whenever the sum passes 1.01. Sums below one are left alone:
at game start the missing remainder belongs to estates the owner has not
established yet, and the survey repairs it within one cycle.

### Investment spending and upkeep

```
investment_spending = estate_wealth_share * local_wealth * investment_rate
upkeep = desired_wealth * investment_rate
investment_progress = (spending * investment_efficiency) - (upkeep * upkeep_efficiency)
```

Equilibrium at `local_wealth = desired_wealth`.

### Desired wealth

```
base_desired = (raw_power / power_per_pop) * desired_multiplier * desired_modifier
base_desired = max(base_desired, local_gdp * relative_estate_power)

desired = base * (1 + level)^2                       when level > 0
desired = base / (1 + 0.5 * |level|)                 when level < 0
desired = base                                        when level = 0
```

### Upkeep floor

```
curve_upkeep = desired_wealth * investment_rate
floor_line = base_desired_wealth * investment_rate + level * upkeep_change_per_level
upkeep = max(curve, floor)    when invested
upkeep = min(curve, floor)    when neglected, never below 0
```

### Investment level

```
whole_level = floor(sqrt(|pool| / cost_base))
cost_to_reach_N = cost_base * N^2
cost_from_N_to_N+1 = cost_base * (2N + 1)
fractional_level = whole_level + (pool - cost_to_reach_whole) / cost_of_next_level
```

Signed: negative pool produces negative levels.

### National savings valve

```
savings_goal = country_economic_base * estate_national_power
gold_gap = savings_goal - estate_treasury

monthly_flow = clamp(gold_gap / 12, -seizure_cap, payout_cap)
payout_cap = country_economic_base * national_investment_limit_factor
seizure_cap = (seizure_limit_factor + seizure_demand) * savings_goal
```

Flow is split across locations by `location_raw_power / national_raw_power`.

EPBM's building maintenance (`epbm_charge_estates`, monthly) debits the same
engine estate treasury the valve reads. Maintenance costs therefore widen the
gold gap and feed seizure demand without any direct coupling between the two
systems; neither reads the other's variables.

### Seizure demand

```
if short: demand += (gap / goal)
if at goal: demand *= seizure_demand_decay (0.9/month)
```

### Looting

```
liquid_looted = wealth_pool * wealth_looted_modifier * (1 - resistance)
invested_looted = local_gdp * investment_looted_modifier * (1 - resistance)

liquid_gold = liquid_looted * gold_from_looted_wealth_kept
invested_gold = invested_looted * gold_from_looted_investment_kept

resistance = clamp(local_resistance + national_resistance, 0, resistance_cap)
```

### AI yearly shortcut

```
survival = 1 - investment_rate
pool_after_12 = pool * survival^12 + monthly_inflow * (1 - survival^12) / investment_rate
```

---

## State

### Location variables

| Variable | Purpose |
|----------|---------|
| `mnt_wealth_pool` | Liquid wealth pool |
| `mnt_wealth_local_gdp` | Cached GDP from last survey |
| `mnt_wealth_current_wage_rate` | Current wage rate |
| `mnt_wealth_local_wages` | Current wages in gold |
| `mnt_wealth_desired_total` | Sum of all estates' desired wealth |
| `mnt_wealth_kept_income_total` | Cached sum of estate income staying in the pool |
| `mnt_wealth_local_wealth_share_sum` | Sum of all ownership shares |
| `mnt_wealth_investment_paid_total` | AI accumulator: gold paid since last yearly pass |
| `mnt_wealth_investment_rate_total` | AI accumulator: investment rate since last yearly pass |
| `mnt_wealth_investment_months` | AI accumulator: months since last yearly pass |
| `mnt_wealth_review_month` | Month of last yearly pass (for display projection) |
| `mnt_wealth_location_id` | Index into the global location index |
| `mnt_wealth_removed_total` | Amount removed by last `mnt_wealth_remove_*` call |
| `mnt_wealth_loot_amount` | Gold looted in last occupation |

### Location variable maps (keyed by estate type)

| Map | Purpose |
|-----|---------|
| `mnt_wealth_local_wealth_share` | Ownership share per estate (0-1) |
| `mnt_wealth_investment_level` | Signed investment level per estate |
| `mnt_wealth_invested_wealth` | Permanent investment pool per estate |
| `mnt_wealth_invested_since_review` | Progress accumulated since last yearly pass |
| `mnt_wealth_base_desired_wealth` | Base desired wealth before level scaling |
| `mnt_wealth_expected_wealth` | Desired wealth after level scaling |
| `mnt_wealth_raw_power` | Raw local political power per estate (modifiers divided out) |
| `mnt_wealth_cached_local_relative_estate_power` | Relative power per estate (cached from survey) |
| `mnt_wealth_kept_wages` | Wage income kept per estate |
| `mnt_wealth_arriving` | Gold arriving for each estate this tick |
| `mnt_wealth_estate_slave_counts` | Slave pop count per estate |

### Location variable lists

| List | Purpose |
|------|---------|
| `mnt_wealth_goods_list` | Goods this location produces (rebuilt at survey) |

### Country variables

| Variable | Purpose |
|----------|---------|
| `mnt_wealth_country_index` | Position in the global country list |
| `mnt_wealth_country_id` | Permanent id for the drift logs, never reassigned |
| `mnt_wealth_national_gdp_total` | Sum of all owned locations' GDP |

### Country variable maps (keyed by estate type)

| Map | Purpose |
|-----|---------|
| `mnt_wealth_estate_flow` | Signed monthly flow per estate: positive = payout, negative = seizure |
| `mnt_wealth_estate_seizure_demand` | Accumulated seizure demand per estate |
| `mnt_wealth_national_estate_raw_power` | Sum of raw power across all owned locations per estate |

### Global variables

| Variable | Purpose |
|----------|---------|
| `mnt_wealth_country_count` | Number of countries indexed for the balancer |
| `mnt_wealth_country_id_counter` | Highest permanent country id handed out |
| `mnt_wealth_location_count` | Number of owned locations in the index |
| `mnt_wealth_human_location_count` | Number of player-held locations in the human index |
| `mnt_wealth_map_mode_max_wealth_pool` | Ceiling for the local wealth map mode |
| `mnt_wealth_building_table_age` | Months since the building-type cache was rebuilt |

### Global variable maps

| Map | Purpose |
|-----|---------|
| `mnt_wealth_location_index` | Owned location scope by integer index |
| `mnt_wealth_human_location_index` | Player-held location scope by integer index (rebuilt monthly) |
| `mnt_wealth_building_makes_goods` | Whether a building type produces goods (cache) |
| `mnt_wealth_power_per_pop` | Political weight per person for each estate (seeded at game start) |
| `mnt_wealth_estate_short_key` | Short flag key per estate type (seeded at game start) |
| `mnt_wealth_bands` | Map mode color thresholds (5 bands) |
| `mnt_wealth_frozen_chunk_size` | Load balancer chunk size per pass key, frozen for the whole cycle |

---

## Extension Modifiers

Each has a `local_` and `global_` version that add together.

| Modifier | Effect |
|----------|--------|
| `mnt_wealth_wage_modifier` | Adds to the wage rate |
| `mnt_wealth_minimum_wage` | Floor for the wage rate |
| `mnt_wealth_investment_rate` | Base share of wealth spent on investment |
| `mnt_wealth_investment_rate_efficiency` | Scales the investment rate (1 + efficiency) |
| `mnt_wealth_investment_efficiency` | Scales investment progress (1 + efficiency, floored at 0) |
| `mnt_wealth_upkeep_efficiency` | Scales upkeep cost (divide by 1 + efficiency, divisor floored at 0.5) |
| `mnt_wealth_X_desired_wealth` | Adds to desired wealth for estate X |
| `mnt_wealth_X_desired_wealth_modifier` | Multiplies desired wealth for estate X |
| `mnt_wealth_looting_resistance` | Reduces looting in that location / the owner's locations |

Country-scope only (no local version):

| Modifier | Effect |
|----------|--------|
| `mnt_wealth_looted_modifier` | Share of the wealth pool looted on occupation |
| `mnt_wealth_investment_looted_modifier` | Multiple of GDP looted as invested wealth on occupation |
| `mnt_wealth_gold_from_looted_wealth_kept` | Share of looted wealth kept as gold (rest destroyed) |
| `mnt_wealth_gold_from_looted_investment_kept` | Share of looted invested wealth kept as gold (rest destroyed) |

Per-estate power modifiers (accessed via `$ESTATE$` substitution):

| Modifier | Effect |
|----------|--------|
| `local_$ESTATE$_estate_power` | Local estate power modifier |
| `global_$ESTATE$_estate_power` | National estate power modifier |

---

## API

Public effects for other mods (location scope):

```
mnt_wealth_add_location_wealth        = { AMOUNT = x }
mnt_wealth_remove_location_wealth     = { AMOUNT = x }
mnt_wealth_add_local_estate_wealth    = { ESTATE = nobles AMOUNT = x }
mnt_wealth_remove_local_estate_wealth = { ESTATE = nobles AMOUNT = x }
```

`ESTATE` is one of: nobles, clergy, burghers, peasants, dhimmi, tribes, cossacks. Removal sets `var:mnt_wealth_removed_total` to the amount actually taken. The pool never goes negative.

---

## Tuning

Central tuning file: `in_game/common/script_values/mnt_wealth_tuning.txt`

Modifier strengths: `main_menu/common/static_modifiers/mnt_wealth_modifiers.txt`

---

## Dependencies

**Community Mod Framework** (Steam 3692202776), for the `on_game_start_after_lobby` hook. Everything else is vanilla.

Identifiers use the `mnt_wealth_` prefix.
