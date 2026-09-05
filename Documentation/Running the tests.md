# Running the tests

EU5 ships a scripted test framework, and `common/tests/` is an ordinary script directory — so we can
add our own tests the same way we add anything else and run them against the mod unattended. The base
game ships **37 tests** spanning 1346 to 1636. As shipped the game throws every result away, so do
"Turn the log on" first, or you get nothing and conclude the feature is broken.

## What a test is

A declarative assertion about game state inside a date window. `00_generic.txt` in full:

```
black_death_happened_test = {
    year = 1346
    success = { any_country = { country_has_disease = disease:bubonic_plague } }
    end_year = 1360
    fail_on_end_year = yes
}
```

`year` is optional — omit it and the test runs from campaign start. `end_year` closes the window.

**Always set `fail_on_end_year = yes`.** A test only logs when it resolves, so without this a test
that never fires is silent — indistinguishable from one that never loaded. All 37 shipped tests
set it.

`common/tests/readme.txt` in the game files has the full grammar. It also documents `failure`,
`success_effect`, `failure_effect` and `success_child`, which no shipped test uses — treat those as
untried.

Ours go in `in_game/common/tests/MnT_<subject>_tests.txt`: a new file with the `MnT_` prefix, so it
adds to the base suite rather than replacing it.

## Turn the log on

Results go to `logs/game_tests.log`. The game ships
`platform_specific_game_data/log_settings_live.json` with `"sinks": []` on the `tests` category, so
every result line is discarded. Give that entry the sinks the file beside it
(`default_log_settings_live.json`) already has:

```json
{
  "category": "tests",
  "always_flush_level": "error",
  "sinks": [
    { "type": "file", "log_level": "info",  "file_name": "game_tests", "format_pattern": "[%T][%s:%#]: %v" },
    { "type": "file", "log_level": "error", "file_name": "error",      "format_pattern": "[%T][%s:%#]: %v" }
  ]
}
```

That file is inside the Steam install: back it up, and re-check it after a patch or a file validation.

## Running it

```
steam -applaunch 3450310 --automated_test --event_test_suite --nographics --seed 12345 --play="FRA" --timed_handsoff=60
```

Launching through Steam mounts the active playset, so the tests run against the mod. Running the
binary directly mounts no mods and tests vanilla.

| Switch | What it does |
|---|---|
| `--automated_test` | Enables automated test mode. Required. |
| `--event_test_suite` | Runs the scripted tests. Refuses without `--automated_test`. |
| `--nographics` | No renderer, no window. See below. |
| `--play="TAG"` | Starts a campaign as that country. |
| `--seed N` | Seeds world generation. |
| `--timed_handsoff=N` | AI plays N months, then the game exits cleanly. |

### `--nographics` is the one that matters

No window, no renderer — and the mod still mounts and the tests still log normally. Nothing steals
focus, so a suite can run while you work, and a run needs no display at all, which is what makes
CI possible.

### Three traps

- **The switch is `--automated_test`, not `--test`.** `--test` is rejected with
  `Trying to run scripted test without automated test mode!`
- **`--handsoff` alone does not advance the clock.** `--play=FRA --handsoff` loaded, sat for about a
  minute and exited with the date never having moved. `--timed_handsoff=N` makes time pass.
- **Never use `--end_after_test`.** It reads as "stop once the tests finish"; it behaves as "stop
  immediately", killing the run in under 90 seconds with no output and no error, which looks exactly
  like the feature not existing. Bound the run with `--timed_handsoff` instead.

## Reading the output

`Documents/Paradox Interactive/Europa Universalis V/logs/game_tests.log`:

```
[23:07:38][tests.cpp:92]: [TEST_NAME][byzantium_succession_crisis][RESULT][PASS][DATE][1337.11.1]
[23:17:26][tests.cpp:92]: [TEST_NAME][black_death_happened_test][RESULT][PASS][DATE][1346.2.1]
```

**The date is not a measurement.** Two runs with identical switches and the same seed resolved
`byzantium_succession_crisis` a year apart. `--seed` constrains world generation, not the whole
simulation — pass it, but a shifted date alone is not evidence that your change caused it.

## Keep test windows early

Later years cost disproportionately more to reach. **Set the window as early as the mechanic
allows** — a test that can only resolve after 1450 will not be reached in a development run. The
shipped suite's last window closes in 1636.
