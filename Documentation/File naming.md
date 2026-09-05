# File naming

**Prefix every file you add with `MnT_`.** That is the default and covers almost everything.

Four exceptions, first match wins.

**1. Overriding a vanilla file? Use the vanilla filename exactly, no prefix.**
The engine matches on path and filename. Prefix it and yours becomes a *new* file while the vanilla
one still loads, so nothing is overridden. Nearly all of our unprefixed files are this.

**2. Does the directory force a name?**
`modifier_type_definitions/` and `cultures/` require lowercase, so `mnt_`. `levies/` needs a numeric
prefix that sorts against the vanilla `00_`–`10_` files, which is why we have `051_tribal_levies.txt`.
When in doubt, match the casing of the vanilla files already in that directory.

**3. Adding to a named subsystem? Use its prefix instead of `MnT_`.**
`RGO_` (raw goods buildings), `epbm_` (Estates Pay Building Maintenance), `fum_` (Faster
Universalis), `aut_` (Autonomous integration), `SYS-` (logging and census). Don't double up —
`RGO_buildings.txt`, not `MnT_RGO_buildings.txt`.

**4. Need load-order precedence?**
Prefix for sort position and say why in a comment on line 1, the way
`in_game/gui/shared/aaa_epbm_expense_tooltip.gui` does.

## Case is load-bearing

Files load in ASCII order, and `MnT_` sorts before `Mnt_` sorts before `mnt_`. Which end of that
order wins depends on what the file holds:

- Entries under `common/` are **last-definition-wins** — later in the sort beats earlier.
- GUI templates are **first-definition-wins** — earlier beats later. That is why the tooltip file
  above is named `aaa_`.

A rename that changes only case still moves the file in load order and can flip which definition
wins. Before renaming, grep for every key the file defines and confirm nothing else contests them.

## Two standing rules

- **Prefix, never suffix.** `MnT_marry_noble.txt`, not `marry_noble_MnT.txt`.
- **Never use `&` in a filename.**

## One known exception

`in_game/common/estates/M&T_default.txt` - don't rename it.
