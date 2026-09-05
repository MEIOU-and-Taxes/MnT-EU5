# Adding a file

The repo root is the mod root. There is no build step — what you commit is what the game loads.

Most mistakes here fail **silently**: the game does not warn you about a file it never mounted or
an encoding it could not read. It just behaves as if your work is not there.

For what to call the file, see `Documentation/File naming.md`.

## Which top-level directory

`in_game/`, `main_menu/` and `loading_screen/` are three separate mounts, not folders we chose. A
file in the wrong one is invisible, not misfiled — the phase that wants it never mounted the tree
it is in, and nothing is logged.

**The rule: put your file at the same path the base game puts the equivalent file, phase directory
included.** Almost everything follows from that.

Localization is looser. All three phases mount a `localization/` tree and the loader finds files by
filename, not by directory, so put a loc file in the same phase as the GUI or script that uses its
keys. The `english/` subdirectory is convention, not a requirement.

The one real constraint is timing: `in_game/` mounts only after you leave the main menu, so text
that must appear on the frontend, bookmark screen or loading screens belongs in
`main_menu/localization/`.

**Overriding a base game string does not need the `replace/` subfolder.** An ordinary loc file
that redefines a base key wins — this repo relies on that for about a thousand keys.

`replace/` is a stronger option, not a required one: the loader holds those files back and applies
them last, so they win outright instead of competing on load order. It works in any phase. Use it
only when you want that last word. We ship one such file, and everything in it really does replace
something — keep it that way and put new strings in an ordinary file.

Localization files need two things: a filename ending `_l_english.yml` and a first line reading
`l_english:`.

## Encoding

- **`.txt` and `.yml` need a UTF-8 BOM.** Everything we ship under `common/`, `events/` and
  `localization/` has one. `named_colors/` and `map_data/` do not — match the directory you are
  writing into.
- **`.gui` files: either way.** The base game ships 50 with a BOM and 611 without, and our CI
  skips `.gui` for BOM checks entirely. Match the files around you.
- **LF line endings.** CI rejects any CRLF in a changed text file.

Adding a BOM from a shell:

```
printf '\xEF\xBB\xBF' | cat - file.yml > tmp && mv tmp file.yml
```

## Prefer a keyword over a copy

Where you can, add your own prefixed file in the right directory and use `INJECT:` or `REPLACE:`
rather than overwriting the base file wholesale. An overwrite means you own a complete copy of that
file forever and have to re-sync it every time the base game changes — see the maintenance note at
the top of `in_game/gui/shared/aaa_epbm_expense_tooltip.gui`.

Defines are the exception where care is needed: we ship two files in
`loading_screen/common/defines/`, and if both set the same define the engine picks one by filename
order and reports the conflict nowhere. Check both before adding one.

## Before you open a PR

- Target `develop`.
- Update `Documentation/Change log.md`, or prefix every commit with one of
  `build` `chore` `fix` `ci` `docs` `style` `refactor` `perf` `test` — CI enforces one or the other.
