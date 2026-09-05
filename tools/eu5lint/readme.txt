eu5lint - filename and encoding checks for this mod

WHY
  A filename decides load order, and in two directories it decides whether the
  file loads at all. None of that fails loudly: a wrong-cased file in
  modifier_type_definitions/ is simply not there, and a file that sorts into
  the wrong slot silently loses a contest it used to win. This checks those
  before the game does.

RUNNING IT
  python3 tools/eu5lint check           blocking checks over the whole tree
  python3 tools/eu5lint audit           the above, plus advisory checks
  python3 tools/eu5lint check <paths>   only these files
  python3 tools/eu5lint/tests/run_tests.py

  The test fixtures under tools/eu5lint/tests/fixtures/ are throwaway mod trees,
  each with its own eu5lint.toml declaring whatever prefix that case needs. They
  are test data, not mod content: several deliberately carry a broken filename or
  a wrong-cased prefix, which is the thing under test.

  Standard library only, no install step, but it needs **Python 3.13 or newer**
  (it uses pathlib's full_match). Run it from the repository root - unlike the
  other scripts here, which want to run from inside tools/.

  A few checks read an unpacked game install. They are skipped with a notice
  unless EU5_GAME is set or --game-root is passed. The naming checks never need
  it: they use the committed path manifest in tools/eu5lint/data/.

  CI runs this on the files a pull request touches, in
  .github/workflows/require-naming.yml.

THE CODES
  EU5001 / EU5003   BOM required / advisory, decided per directory
  EU5081            no prefix, and no base-game file at that path
  EU5082            capitals in a directory that requires lowercase
  EU5083            prefix spelled in the wrong case
  EU5084            two prefixes stacked in one filename
  EU5085            an exception below is stale or has no reason

  EU5082 is an error because such a file does not load at all. EU5083 is only a
  warning: the file still loads, it just sorts into an odd slot.

  Inside a directory that requires lowercase, EU5083 is suppressed and EU5082
  owns the filename's casing - otherwise the two rules would demand opposite
  renames of the same file.

  EU5082 and EU5083 tell you the exact name to rename to. Nothing suggests a
  name for a brand new file - which subsystem prefix it deserves is your call,
  not the tool's, and a confidently wrong rename is worse than no advice.

ADDING AN EXCEPTION
  A deliberate convention break goes in eu5lint.toml, with a reason:

      [[naming_exception]]
      path = "in_game/common/levies/051_tribal_levies.txt"
      reason = "numeric prefix on purpose: it sorts against the base game's own 00_-10_ levy files"

  The reason is not optional. An exception with an empty reason, or one naming
  a file that no longer exists, is itself reported as EU5085 - so the list
  cannot quietly fill up with entries nobody can explain any more.

  To change a rule everywhere instead, set its severity in the same file:

      [severity]
      EU5083 = "warn"      # "error" | "warn" | "off"

  Both are already used in eu5lint.toml, with the reasoning written next to
  each one.
