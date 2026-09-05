"""Black-box unittest fixtures for eu5lint and the repository Git hooks."""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import os
import sys
import tempfile
import unittest


TESTS_DIR = Path(__file__).resolve().parent
LINTER_DIR = TESTS_DIR.parent
REPO_ROOT = LINTER_DIR.parent.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
FAKE_GAME = FIXTURES_DIR / "fake_game"
FIXTURE_MANIFEST = FIXTURES_DIR / "vanilla_manifest.txt"
COMMIT_MSG_HOOK = REPO_ROOT / ".githooks" / "commit-msg"

if str(LINTER_DIR) not in sys.path:
    sys.path.insert(0, str(LINTER_DIR))

import manifest  # noqa: E402  (needs the path insert above)
from checks import braces, eventids, naming  # noqa: E402
import sources  # noqa: E402
from config import load_config  # noqa: E402
from sources import Context  # noqa: E402
import unittest.mock  # noqa: E402


@dataclass(frozen=True)
class FixtureCase:
    name: str
    command: str
    expected: tuple[tuple[str, str], ...]
    exit_code: int
    game_root: str | None = None
    manifest: str | None = None
    # Payload files to rewrite with CRLF before the run. The repository enforces
    # LF on every committed .txt, so a fixture that needs CRLF cannot carry it in
    # Git; it is produced in a temporary copy of the fixture tree instead.
    crlf_payload: tuple[str, ...] = ()
    # Distinguishes two cases that share one fixture directory. The generated test
    # method is named from this, and registration is name-keyed, so without it the
    # second case silently REPLACES the first and its coverage disappears with no
    # failure and no change in the test count.
    label: str | None = None
    # (code, substring) pairs that must appear in some finding's message. The
    # multiset above proves a rule fired on the right file; this proves it said
    # the right thing -- which matters for the rules that name a target filename,
    # where a wrong suggestion is worse than no suggestion.
    expected_messages: tuple[tuple[str, str], ...] = ()


def finding(code: str, path: str) -> tuple[str, str]:
    return code, path


def lint_json(
    root: Path,
    command: str,
    arguments: Sequence[str] = (),
    game_root: Path = FAKE_GAME,
    manifest_path: Path = FIXTURE_MANIFEST,
) -> subprocess.CompletedProcess[str]:
    """Run one linter subcommand over ``root`` and return the finished process."""

    return subprocess.run(
        [
            sys.executable,
            str(LINTER_DIR),
            command,
            "--root",
            str(root),
            "--config",
            str(root / "eu5lint.toml"),
            "--game-root",
            str(game_root),
            "--manifest",
            str(manifest_path),
            "--format",
            "json",
            *arguments,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def codes_in(stdout: str) -> Counter[str]:
    """Count the finding codes one JSON-mode linter run reported."""

    codes: Counter[str] = Counter()
    for line in stdout.splitlines():
        raw: object = json.loads(line)
        if isinstance(raw, dict):
            code = raw.get("code")
            if isinstance(code, str):
                codes[code] += 1
    return codes


COMMON_TXT = "in_game/common/MnT_"


CASES: tuple[FixtureCase, ...] = (
    FixtureCase(
        "bom_missing",
        "check",
        (finding("EU5001", f"{COMMON_TXT}bom.txt"),),
        1,
    ),
    FixtureCase(
        "bom_forbidden",
        "check",
        (finding("EU5002", "main_menu/setup/start/MnT_start.txt"),),
        1,
    ),
    FixtureCase(
        "bom_warn_required",
        "check",
        (finding("EU5003", "main_menu/setup/templates/MnT_template.txt"),),
        0,
    ),
    FixtureCase(
        "eol_crlf",
        "check",
        (finding("EU5010", f"{COMMON_TXT}crlf.txt"),),
        1,
        crlf_payload=("in_game/common/MnT_crlf.txt",),
    ),
    FixtureCase(
        "unbalanced_brace",
        "check",
        (finding("EU5020", f"{COMMON_TXT}brace.txt"),),
        1,
    ),
    FixtureCase(
        "unterminated_quote",
        "check",
        (finding("EU5021", f"{COMMON_TXT}quote.txt"),),
        1,
    ),
    FixtureCase(
        "multiline_quote",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "braces_in_strings_comments",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "bindings_no_braces",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "overwrite_shadow",
        "check",
        (
            finding(
                "EU5030",
                "in_game/common/goods/00_goods.txt",
            ),
        ),
        1,
    ),
    FixtureCase(
        "overwrite_stale",
        "check",
        (
            finding(
                "EU5031",
                "in_game/common/goods/00_goods.txt",
            ),
        ),
        1,
    ),
    FixtureCase(
        "overwrite_empty_reason",
        "check",
        (
            finding(
                "EU5032",
                "in_game/common/goods/00_goods.txt",
            ),
        ),
        1,
    ),
    FixtureCase(
        "declared_overwrite_clean",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "inject_scripted",
        "check",
        (finding("EU5040", "in_game/common/scripted_effects/MnT_effect.txt"),),
        1,
    ),
    FixtureCase(
        "nested_replace",
        "check",
        (finding("EU5041", "in_game/common/overrides/MnT_nested.txt"),),
        1,
    ),
    FixtureCase(
        "prefix_missing",
        "check",
        (
            finding("EU5050", "in_game/common/thing.txt"),
            finding("EU5081", "in_game/common/thing.txt"),
        ),
        1,
    ),
    FixtureCase(
        "prefix_lowercase",
        "check",
        (
            finding("EU5050", "in_game/common/mnt_thing.txt"),
            finding("EU5083", "in_game/common/mnt_thing.txt"),
        ),
        1,
    ),
    FixtureCase(
        "prefix_mixedcase",
        "check",
        (
            finding("EU5050", "in_game/common/Mnt_thing.txt"),
            finding("EU5083", "in_game/common/Mnt_thing.txt"),
        ),
        1,
    ),
    FixtureCase(
        "prefix_positive",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "prefix_unset",
        "check",
        (finding("EU5051", ""),),
        1,
    ),
    FixtureCase(
        "prefix_exception_invalid",
        "check",
        (
            finding("EU5052", "in_game/common/aaa_special.txt"),
            finding("EU5081", "in_game/common/aaa_special.txt"),
        ),
        1,
    ),
    FixtureCase(
        "prefix_exception_stale",
        "check",
        (finding("EU5052", "in_game/common/aaa_gone.txt"),),
        1,
    ),
    FixtureCase(
        "naming_prefixed_shadow",
        "check",
        (finding("EU5080", "in_game/common/upstream/MnT_layer.txt"),),
        1,
    ),
    FixtureCase(
        "naming_bare_override",
        "check",
        (),
        0,
    ),
    FixtureCase(
        # Placement is the one failure the engine never reports, so the rule is
        # a proxy: it reports what the base game does and never says what to do
        # about it. Two prescriptive wordings were tried and both were wrong on
        # a real path -- one told a DLC override to move phase, the other told a
        # wrong-phase file to descend a directory. The correctly-placed file
        # must stay silent, and a recorded exception must suppress the finding.
        "placement_phase",
        "check",
        (
            finding("EU5087", ""),
            finding(
                "EU5090",
                "loading_screen/common/MnT_in_a_container.txt",
            ),
            finding(
                "EU5090",
                "main_menu/common/advances/MnT_wrong_phase.txt",
            ),
        ),
        0,
        manifest=str(FIXTURES_DIR / "vanilla_manifest_placement.txt"),
        expected_messages=(
            # States what was observed and asks the reader to check, and must
            # never instruct: observed vanilla placement is not proof of engine
            # visibility, and every prescriptive wording tried was wrong in some
            # real case.
            ("EU5090", "every base-game file in 'common/advances' -- 5 of them"),
            ("EU5090", "This is evidence, not proof"),
        ),
    ),
    FixtureCase(
        "naming_bare_new",
        "check",
        (
            finding("EU5050", "in_game/common/loose/thing.txt"),
            finding("EU5081", "in_game/common/loose/thing.txt"),
        ),
        1,
    ),
    FixtureCase(
        "naming_lowercase_dir",
        "check",
        (
            finding(
                "EU5082",
                "in_game/common/cultures/MnT_egypt.txt",
            ),
            finding(
                "EU5082",
                "in_game/common/modifier_type_definitions/MnT_types.txt",
            ),
        ),
        1,
    ),
    FixtureCase(
        "naming_lowercase_near_miss",
        "check",
        (
            finding("EU5083", "in_game/common/loose/mnt_thing.txt"),
            # Capitals in a lowercase-forced directory: EU5082 only. If EU5083
            # also fired here the two would demand opposite renames of one file.
            finding(
                "EU5082",
                "in_game/common/modifier_type_definitions/Mnt_types.txt",
            ),
        ),
        1,
        # The suggestions point opposite ways on purpose: outside a
        # lowercase-forced directory the prefix's capitalization wins, inside
        # one the directory does. A rename acted on blindly must be right.
        expected_messages=(
            ("EU5083", "'MnT_thing.txt'"),
            ("EU5082", "'mnt_types.txt'"),
        ),
    ),
    FixtureCase(
        "naming_near_miss",
        "check",
        (finding("EU5083", "in_game/common/loose/Mnt_tribes.txt"),),
        1,
    ),
    FixtureCase(
        "naming_double_prefix",
        "check",
        (finding("EU5084", "in_game/common/loose/MnT_RGO_buildings.txt"),),
        0,
    ),
    FixtureCase(
        "naming_exception_allows",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "naming_exception_invalid",
        "check",
        (
            finding("EU5085", "in_game/common/loose/gone.txt"),
            finding("EU5085", "in_game/common/loose/MnT_here.txt"),
        ),
        1,
    ),
    FixtureCase(
        # The manifest is a snapshot and its version header is unverified, so a
        # game patch would otherwise leave the naming rules answering from a
        # stale file list in silence. Here the manifest is one path short of the
        # fake install, which is what a patch looks like.
        "clean",
        "check",
        (finding("EU5087", ""),),
        0,
        manifest=str(FIXTURES_DIR / "vanilla_manifest_stale.txt"),
        label="manifest_drifted_from_the_install",
        expected_messages=(("EU5087", "make vanilla-manifest"),),
    ),
    FixtureCase(
        "naming_manifest_missing",
        "check",
        (
            finding("EU5086", ""),
            finding("EU5083", "in_game/common/loose/Mnt_tribes.txt"),
        ),
        1,
        manifest="/nonexistent/vanilla_paths.txt",
    ),
    FixtureCase(
        "loc_bad_filename",
        "check",
        (finding("EU5060", "main_menu/localization/english/MnT_strings.yml"),),
        1,
    ),
    FixtureCase(
        "loc_bad_header",
        "check",
        (
            finding(
                "EU5061",
                "main_menu/localization/english/MnT_strings_l_english.yml",
            ),
        ),
        1,
    ),
    FixtureCase(
        "loc_bad_entry",
        "check",
        (
            finding(
                "EU5062",
                "main_menu/localization/english/MnT_strings_l_english.yml",
            ),
        ),
        1,
    ),
    FixtureCase(
        "loc_variants",
        "check",
        (),
        0,
    ),
    FixtureCase(
        "metadata_bad_fields",
        "check",
        (
            finding("EU5070", ".metadata/metadata.json"),
            finding("EU5070", ".metadata/metadata.json"),
            finding("EU5070", ".metadata/metadata.json"),
        ),
        1,
    ),
    FixtureCase(
        "metadata_bad_picture",
        "check",
        (finding("EU5071", ".metadata/metadata.json"),),
        1,
    ),
    FixtureCase(
        "metadata_picture_escape",
        "check",
        (finding("EU5071", ".metadata/metadata.json"),),
        1,
    ),
    FixtureCase(
        "metadata_no_bom",
        "check",
        (finding("EU5072", ".metadata/metadata.json"),),
        1,
    ),
    FixtureCase(
        "metadata_invalid_json",
        "check",
        (finding("EU5073", ".metadata/metadata.json"),),
        1,
    ),
    FixtureCase(
        "wrong_phase_localization",
        "check",
        (),
        0,
    ),
    FixtureCase(
        # An event is addressed by its ID, not by its file, so a prefixed copy of
        # a base-game event file does not replace it: both load and the ID is
        # registered twice. Three cases here -- a prefixed duplicate (fires), a
        # file named exactly as the base game's so it replaces that file outright
        # (silent, and that is the fix this rule recommends), and an ID the base
        # game does not have (silent).
        "eventids",
        "audit",
        (
            finding("EU5091", "in_game/events/MnT_probe_events.txt"),
            # Two mod files defining one ID collide with each other exactly as a
            # mod file collides with the base game. M&T bundle other mods inside
            # this same tree, so this is not hypothetical.
            finding("EU5091", "in_game/events/MnT_second_own.txt"),
        ),
        0,
        game_root=str(FIXTURES_DIR / "fake_game_events"),
        manifest=str(FIXTURES_DIR / "vanilla_manifest_eventids.txt"),
        expected_messages=(
            ("EU5091", "'probe_ns.1' is also defined by the base game"),
            # It must NOT prescribe a fix. Renaming the mod file to the base
            # game's name replaces that whole file, which on the real tree would
            # have deleted 36 vanilla events to patch one.
            ("EU5091", "No fix is suggested"),
            ("EU5091", "'mnt_own.1' is also defined by this mod"),
        ),
    ),
    FixtureCase(
        # A replace/ key the base game lacks is only a finding when nothing in the
        # mod reads it: the loader creates a missing key rather than discarding it,
        # so a mod defining its own string here is misplaced, not broken. The _desc
        # entry additionally checks the engine's <key>_desc convention, where the
        # key is never named anywhere.
        "dead_replace_referenced",
        "audit",
        (
            # MnT_orphan, in each language that defines it. Everything else in
            # these files is read one way or another and must stay silent:
            # MnT_own_thing from a script file, MnT_own_thing_desc via the
            # <key>_desc convention, MnT_interp via $...$ from a sibling entry
            # in its own file. The consumer's comment names MnT_orphan, which
            # must NOT rescue it, and the French file DEFINES it rather than
            # reading it, so both languages report.
            finding(
                "EU5100",
                "main_menu/localization/english/replace/MnT_own_l_english.yml",
            ),
            finding(
                "EU5100",
                "main_menu/localization/french/replace/MnT_own_l_french.yml",
            ),
        ),
        0,
    ),
    FixtureCase(
        "dead_replace",
        "audit",
        (
            finding(
                "EU5100",
                "main_menu/localization/english/replace/MnT_dead_l_english.yml",
            ),
        ),
        0,
    ),
    FixtureCase(
        "missing_asset",
        "audit",
        (finding("EU5110", "in_game/common/MnT_asset.txt"),),
        0,
    ),
    FixtureCase(
        # Two files share the NUnit and NCombat groups, which the engine merges:
        # vanilla splits NWeather across 00_defines.txt and 00_graphics.txt with
        # disjoint keys and both apply. Only the leaf key set in both files is a
        # competing definition, and only it may be reported.
        "defines_group_merge",
        "audit",
        (
            finding(
                "EU5120",
                "loading_screen/common/defines/MnT_b.txt",
            ),
        ),
        0,
        expected_messages=(("EU5120", "'NUnit.SHARED_KEY'"),),
    ),
    FixtureCase(
        "duplicate_key",
        "audit",
        (finding("EU5120", "in_game/common/MnT_dupes.txt"),),
        0,
    ),
    FixtureCase(
        "gui_unbalanced",
        "audit",
        (finding("EU5130", "in_game/gui/MnT_bad.gui"),),
        0,
    ),
    FixtureCase(
        "gui_bom_warning",
        "check",
        (finding("EU5003", "in_game/gui/MnT_widget.gui"),),
        0,
    ),
    FixtureCase(
        "missing_game_root",
        "audit",
        (finding("EU5900", ""),),
        0,
        game_root="/nonexistent",
    ),
    FixtureCase(
        # The same fixture against a root that EXISTS but is not an install. This is
        # the shape a blank [game].root produces, because it resolves against the
        # config file's own directory. Before the mount-root guard the builders
        # returned an empty index instead of None, so every base-game question
        # answered "no" and EU5900 never fired: this fixture's replace/ key was
        # reported as dead, and M&T's tree produced 814 warnings instead of 28.
        # Only EU5900 is expected here, never EU5100.
        "missing_game_root",
        "audit",
        (finding("EU5900", ""),),
        0,
        game_root=str(FIXTURES_DIR),
        label="game_root_exists_but_is_not_an_install",
    ),
    FixtureCase(
        "clean",
        "check",
        (),
        0,
    ),
)


class FixtureTests(unittest.TestCase):
    def run_fixture(self, case: FixtureCase) -> None:
        if case.crlf_payload:
            with tempfile.TemporaryDirectory() as tmp:
                staged = Path(tmp) / case.name
                shutil.copytree(FIXTURES_DIR / case.name, staged)
                for rel in case.crlf_payload:
                    target = staged / rel
                    target.write_bytes(
                        target.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    )
                self._run_fixture_at(case, staged)
            return
        self._run_fixture_at(case, FIXTURES_DIR / case.name)

    def _run_fixture_at(self, case: FixtureCase, fixture_root: Path) -> None:
        game_root = Path(case.game_root) if case.game_root else FAKE_GAME
        manifest = Path(case.manifest) if case.manifest else FIXTURE_MANIFEST
        result = lint_json(
            fixture_root,
            case.command,
            game_root=game_root,
            manifest_path=manifest,
        )
        self.assertEqual(
            result.returncode,
            case.exit_code,
            msg=(
                f"{case.name}: exit {result.returncode}, expected "
                f"{case.exit_code}\nstdout:\n{result.stdout}\nstderr:\n"
                f"{result.stderr}"
            ),
        )

        actual: Counter[tuple[str, str]] = Counter()
        messages: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            raw: object = json.loads(line)
            self.assertIsInstance(raw, dict, msg=f"{case.name}: non-object JSON")
            if not isinstance(raw, dict):
                continue
            code = raw.get("code")
            path = raw.get("path")
            self.assertIsInstance(code, str, msg=f"{case.name}: missing code")
            self.assertIsInstance(path, str, msg=f"{case.name}: missing path")
            if isinstance(code, str) and isinstance(path, str):
                actual[(code, path)] += 1
                message = raw.get("message")
                if isinstance(message, str):
                    messages.append((code, message))

        for code, fragment in case.expected_messages:
            texts = [m for c, m in messages if c == code]
            self.assertTrue(
                any(fragment in text for text in texts),
                msg=(
                    f"{case.name}: no {code} message contains {fragment!r}\n"
                    + "\n".join(texts)
                ),
            )

        expected = Counter(case.expected)
        self.assertEqual(
            actual,
            expected,
            msg=(
                f"{case.name}: finding multiset mismatch; "
                f"actual={actual}, expected={expected}\n"
                f"stderr:\n{result.stderr}"
            ),
        )


def make_fixture_test(case: FixtureCase) -> Callable[[FixtureTests], None]:
    def test(self: FixtureTests) -> None:
        self.run_fixture(case)
        print(f"PASS {case.name}")

    test.__name__ = f"test_{case.name}"
    return test


_registered: set[str] = set()
for fixture_case in CASES:
    _test_name = f"test_{fixture_case.label or fixture_case.name}"
    if _test_name in _registered:
        raise SystemExit(
            f"duplicate fixture test name {_test_name!r}: give one of the cases a "
            "distinct `label`, or its coverage is silently dropped"
        )
    _registered.add(_test_name)
    setattr(FixtureTests, _test_name, make_fixture_test(fixture_case))


@dataclass(frozen=True)
class MessageCase:
    name: str
    message: str
    exit_code: int
    expect_stderr: tuple[str, ...] = ()


GOOD_BODY = (
    "Why: the rule was unenforced.\n"
    "What: add a hook.\n"
    "Impact: messages are checked.\n"
)

# Git's --verbose block: comments, the scissors line, then a raw diff whose
# lines are not comment-prefixed.
SCISSORS = (
    "# Please enter the commit message for your changes.\n"
    "#\n"
    "# ------------------------ >8 ------------------------\n"
    "# Do not modify or remove the line above.\n"
    "diff --git a/docs/CONVENTIONS.md b/docs/CONVENTIONS.md\n"
    "--- a/docs/CONVENTIONS.md\n"
    "+++ b/docs/CONVENTIONS.md\n"
    "@@ -1,2 +1,2 @@\n"
    "-Why: the old wording.\n"
    "+Why: the new wording.\n"
    " Impact: an unchanged context line, indented by diff's leading space.\n"
)


MESSAGE_CASES: tuple[MessageCase, ...] = (
    MessageCase(
        "msg_conforming_inline",
        f"feat: add a commit-msg hook\n\n{GOOD_BODY}",
        0,
    ),
    MessageCase(
        "msg_conforming_heading",
        "chore: re-track dev tooling\n\nWhy:\nthe rule was unenforced.\n\n"
        "What:\nadd a hook.\n\nImpact:\nmessages are checked.\n",
        0,
    ),
    MessageCase(
        "msg_conforming_scope_and_breaking",
        f"feat(loc)!: rename the localization prefix\n\n{GOOD_BODY}",
        0,
    ),
    MessageCase(
        "msg_subject_at_limit",
        f"chore: {'x' * 65}\n\n{GOOD_BODY}",
        0,
    ),
    MessageCase(
        "msg_subject_too_long",
        f"chore: {'x' * 66}\n\n{GOOD_BODY}",
        1,
        ("Subject is 73 characters", "limit is 72"),
    ),
    MessageCase(
        "msg_missing_impact",
        "feat: add a commit-msg hook\n\n"
        "Why: the rule was unenforced.\nWhat: add a hook.\n",
        1,
        ("missing the required section(s): Impact",),
    ),
    MessageCase(
        "msg_missing_all_sections",
        "feat: add a commit-msg hook\n\nIt checks the message shape.\n",
        1,
        ("Why, What, Impact",),
    ),
    MessageCase(
        "msg_bad_type",
        f"feature: add a commit-msg hook\n\n{GOOD_BODY}",
        1,
        ('"feature" is not an accepted type',),
    ),
    MessageCase(
        "msg_uppercase_type",
        f"Feat: add a commit-msg hook\n\n{GOOD_BODY}",
        1,
        ("Types are lowercase",),
    ),
    MessageCase(
        "msg_not_conventional",
        f"add a commit-msg hook\n\n{GOOD_BODY}",
        1,
        ("not Conventional-Commits form",),
    ),
    MessageCase(
        "msg_no_blank_line",
        f"feat: add a commit-msg hook\n{GOOD_BODY}",
        1,
        ("No blank line between the subject and the body",),
    ),
    MessageCase(
        "msg_no_body",
        "feat: add a commit-msg hook\n",
        1,
        ("has no body",),
    ),
    MessageCase(
        "msg_merge_branch",
        "Merge branch 'topic' into main\n",
        0,
    ),
    MessageCase(
        "msg_merge_pull_request",
        "Merge pull request #7 from contributor/topic\n\nsome branch summary\n",
        0,
    ),
    MessageCase(
        "msg_revert",
        'Revert "feat: add eu5lint, a stdlib linter for EU5 mod invariants"\n\n'
        "This reverts commit 6bd7105.\n",
        0,
    ),
    MessageCase(
        "msg_reapply",
        'Reapply "feat: add eu5lint, a stdlib linter for EU5 mod invariants"\n\n'
        "This reverts commit abc1234.\n",
        0,
    ),
    MessageCase(
        "msg_fixup",
        "fixup! feat: add a commit-msg hook\n",
        0,
    ),
    MessageCase(
        "msg_squash",
        "squash! feat: add a commit-msg hook\n",
        0,
    ),
    MessageCase(
        "msg_comment_between_subject_and_body",
        "feat: add a commit-msg hook\n# a comment git will drop\n\n" + GOOD_BODY,
        0,
    ),
    MessageCase(
        "msg_only_comments",
        "\n# Please enter the commit message for your changes.\n#\n# On branch main\n",
        0,
    ),
    MessageCase(
        "msg_comments_are_not_body",
        "feat: add a commit-msg hook\n\nWhy: the rule was unenforced.\n"
        "# What: add a hook.\n# Impact: messages are checked.\n",
        1,
        ("missing the required section(s): What, Impact",),
    ),
    MessageCase(
        "msg_scissors_diff_ignored",
        f"feat: add a commit-msg hook\n\n{GOOD_BODY}\n{SCISSORS}",
        0,
    ),
    MessageCase(
        "msg_scissors_cannot_supply_a_section",
        "feat: add a commit-msg hook\n\nWhy: the rule was unenforced.\n"
        f"What: add a hook.\n\n{SCISSORS}",
        1,
        ("missing the required section(s): Impact",),
    ),
)


# These two classes exercise a commit-message convention carried by the repository's
# own hook, not any behavior of the linter. A tree that vendors the linter without
# that hook -- which is the normal case -- has nothing for them to test, so they skip
# rather than fail there.
@unittest.skipUnless(
    COMMIT_MSG_HOOK.exists(), "no .githooks/commit-msg in this repository"
)
class CommitMsgHookTests(unittest.TestCase):
    """Exercise .githooks/commit-msg as Git runs it: argv[1] is a message file."""

    def run_message(self, case: MessageCase) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            message_path = Path(tmp) / "COMMIT_EDITMSG"
            message_path.write_text(case.message, encoding="utf-8")
            result = subprocess.run(
                [str(COMMIT_MSG_HOOK), str(message_path)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(
            result.returncode,
            case.exit_code,
            msg=(
                f"{case.name}: exit {result.returncode}, expected "
                f"{case.exit_code}\nstderr:\n{result.stderr}"
            ),
        )
        if case.exit_code == 0:
            self.assertEqual(
                result.stderr,
                "",
                msg=f"{case.name}: accepted message still wrote to stderr",
            )
        for fragment in case.expect_stderr:
            self.assertIn(
                fragment,
                result.stderr,
                msg=f"{case.name}: stderr lacks {fragment!r}\n{result.stderr}",
            )


def make_message_test(case: MessageCase) -> Callable[[CommitMsgHookTests], None]:
    def test(self: CommitMsgHookTests) -> None:
        self.run_message(case)
        print(f"PASS {case.name}")

    test.__name__ = f"test_{case.name}"
    return test


for message_case in MESSAGE_CASES:
    setattr(
        CommitMsgHookTests, f"test_{message_case.name}", make_message_test(message_case)
    )


@unittest.skipUnless(
    COMMIT_MSG_HOOK.exists(), "no .githooks/commit-msg in this repository"
)
class HistoricalMessageTests(unittest.TestCase):
    """Every commit already in this history must satisfy the hook."""

    def test_existing_commit_messages_conform(self) -> None:
        log = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if log.returncode != 0:
            self.skipTest("not a Git checkout")
        with tempfile.TemporaryDirectory() as tmp:
            message_path = Path(tmp) / "COMMIT_EDITMSG"
            for sha in log.stdout.split():
                body = subprocess.run(
                    ["git", "log", "-1", "--format=%B", sha],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                message_path.write_text(body.stdout, encoding="utf-8")
                result = subprocess.run(
                    [str(COMMIT_MSG_HOOK), str(message_path)],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    msg=f"{sha} fails the commit-msg hook:\n{result.stderr}",
                )
        print("PASS historical_commit_messages")


class EventIdLayerFailureTests(unittest.TestCase):
    """An unlistable DLC directory must degrade to EU5092, not crash or lie.

    The first attempt at this guard used a bare ``return`` from a helper whose
    signature promises a dict, so it swapped a PermissionError for an
    AttributeError in the caller. An empty dict would have been worse still: it
    reads as "the base game defines no events" and would silence every real
    collision.
    """

    def test_an_unlistable_dlc_directory_yields_the_incomplete_notice(self) -> None:
        real_iterdir = Path.iterdir

        def refuse(self):
            if self.name == "dlc":
                raise PermissionError(13, "Permission denied")
            return real_iterdir(self)

        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "mod"
            shutil.copytree(FIXTURES_DIR / "eventids", root)
            (FAKE_GAME / "game" / "dlc").mkdir(parents=True, exist_ok=True)
            config = load_config(root / "eu5lint.toml", game_root_override=FAKE_GAME)
            context = Context(config, root, 0)
            files = sources.discover_worktree(root)
            with unittest.mock.patch.object(Path, "iterdir", refuse):
                findings = list(eventids.run(files, context))

        codes = {finding.code for finding in findings}
        self.assertIn("EU5092", codes, msg=f"expected the notice, got {codes}")
        self.assertNotIn("EU5091", codes, msg="reported collisions from a partial list")
        print("PASS eventids_unlistable_dlc_yields_incomplete_notice")


class ScopedReferenceCorpusTests(unittest.TestCase):
    """A path-limited EU5100 run must reach the same verdict as a whole-tree one.

    EU5100's question is "does anything in this mod read the key". A run handed
    one file cannot answer it from its own corpus, and the check used to say so
    in the message and then advise removal anyway. It now reads the whole
    worktree however it was scoped. Without this test, replacing that corpus
    with the selected files again passes every other test in the suite.
    """

    FIXTURE = FIXTURES_DIR / "dead_replace_referenced"
    ENGLISH = "main_menu/localization/english/replace/MnT_own_l_english.yml"

    def _dead_keys(self, arguments: Sequence[str]) -> set[str]:
        result = lint_json(self.FIXTURE, "audit", arguments)
        self.assertIn(
            result.returncode, (0, 1), msg=f"linter did not run: {result.stderr}"
        )
        return {
            line.split("key '", 1)[1].split("'", 1)[0]
            for line in result.stdout.splitlines()
            if "EU5100" in line and "key '" in line
        }

    def test_a_scoped_run_agrees_with_the_whole_tree_run(self) -> None:
        whole = self._dead_keys(())
        scoped = self._dead_keys((self.ENGLISH,))
        self.assertEqual(
            scoped,
            {key for key in whole if key},
            msg="scoped run disagrees with the whole-tree run",
        )
        print("PASS deadreplace_scoped_run_agrees_with_whole_tree")

    def test_a_referenced_key_is_never_called_dead(self) -> None:
        """The keys the fixture's consumer file reads must survive both scopes."""

        for arguments in ((), (self.ENGLISH,)):
            dead = self._dead_keys(arguments)
            for live in ("MnT_own_thing", "MnT_own_thing_desc", "MnT_composer"):
                self.assertNotIn(live, dead, msg=f"scope {arguments!r} called it dead")
        print("PASS deadreplace_referenced_keys_never_called_dead")


class SameFileEventEmissionTests(unittest.TestCase):
    """The same-file duplicate must reach a finding, not just the extractor.

    Keeping duplicates in ``_ids_in`` is necessary but not sufficient: deleting
    the emission branch that consumes them passed the whole suite.
    """

    def test_a_repeated_id_in_one_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "mod"
            shutil.copytree(FIXTURES_DIR / "eventids", root)
            repeated = root / "in_game" / "events" / "MnT_own_events.txt"
            repeated.write_bytes(
                b"\xef\xbb\xbfnamespace = own_ns\n"
                b"own_ns.1 = {}\nown_ns.2 = {}\nown_ns.1 = {}\n"
            )
            result = lint_json(root, "audit")
        self.assertIn(
            result.returncode, (0, 1), msg=f"linter did not run: {result.stderr}"
        )
        same_file = [
            line
            for line in result.stdout.splitlines()
            if "EU5091" in line and "is defined 2 times in this file" in line
        ]
        self.assertTrue(same_file, msg=f"no same-file EU5091:\n{result.stdout}")
        print("PASS eventids_same_file_duplicate_is_reported")


class IncompleteWalkTests(unittest.TestCase):
    """An unreadable subtree must not shorten a file list silently.

    os.walk discards errors unless handed a hook, so a permission failure used
    to remove files from the corpus without a word. That is how EU5100 could
    reach "nothing reads this key" about a key whose only consumer sat in the
    unreadable directory.
    """

    def test_a_failing_walk_raises_instead_of_truncating(self) -> None:
        root = Path(tempfile.mkdtemp())
        try:
            payload = root / "in_game" / "common"
            payload.mkdir(parents=True)
            (payload / "MnT_a.txt").write_bytes(b"\xef\xbb\xbfa = {}\n")
            real_walk = os.walk

            def refuse(top, **kwargs):
                onerror = kwargs.get("onerror")
                if onerror is not None:
                    onerror(PermissionError(13, "Permission denied"))
                return real_walk(top, **kwargs)

            with unittest.mock.patch.object(sources, "os") as fake_os:
                fake_os.walk = refuse
                fake_os.path = os.path
                with self.assertRaises(sources.SourceError):
                    sources.discover_worktree(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        print("PASS sources_incomplete_walk_raises")


class QuoteAwareExtractionTests(unittest.TestCase):
    """Definitions must not be invented from text inside a multiline string.

    The scanner always tracked quote state to keep braces inside strings out of
    the depth count, but returned only the depth, so a caller could not tell a
    real column-zero definition from prose inside a string. EU5091 and EU5120
    both read through this helper, so a fabricated key became a fabricated
    duplicate-ID or duplicate-key finding against content that does not exist.
    """

    def _keys(self, extractor, data: bytes) -> list[str]:
        return [key for _, _, key, operation in extractor(data) if not operation]

    def test_a_string_body_is_not_a_top_level_definition(self) -> None:
        data = b'text = "hello\nprobe_ns.1 = {}\nbye"\n'
        self.assertEqual(self._keys(braces.top_level_entries, data), ["text"])
        print("PASS braces_string_body_is_not_a_definition")

    def test_a_string_body_is_not_a_grouped_definition(self) -> None:
        data = b'NUnit = {\n  note = "hello\n  FAKE = 1\n  bye"\n}\n'
        self.assertEqual(self._keys(braces.grouped_entries, data), ["NUnit.note"])
        print("PASS braces_string_body_is_not_a_grouped_definition")

    def test_real_definitions_still_extract(self) -> None:
        """The guard must not silence ordinary content, including braces in
        strings, which is the case the quote tracking existed for."""

        self.assertEqual(
            self._keys(braces.top_level_entries, b'a = "text { not a brace"\nb = {}\n'),
            ["a", "b"],
        )
        self.assertEqual(
            self._keys(braces.grouped_entries, b"NUnit = {\n  SPEED = 1\n  MASS = 2\n}\n"),
            ["NUnit.SPEED", "NUnit.MASS"],
        )
        print("PASS braces_real_definitions_still_extract")


class SameFileEventDuplicateTests(unittest.TestCase):
    """One file defining an ID twice is a collision the engine also reports."""

    def test_duplicates_survive_extraction(self) -> None:
        ids = eventids._ids_in(b"new_ns.1 = {}\nnew_ns.2 = {}\nnew_ns.1 = {}\n")
        self.assertEqual(ids.count("new_ns.1"), 2, msg=f"collapsed to {ids}")
        print("PASS eventids_same_file_duplicates_survive_extraction")


class ManifestEnumerationFailureTests(unittest.TestCase):
    """An unreadable DLC directory degrades; it does not crash the run."""

    def test_iterdir_failure_becomes_a_manifest_error(self) -> None:
        real_iterdir = Path.iterdir

        def refuse(self):
            if self.name == "dlc":
                raise PermissionError(13, "Permission denied")
            return real_iterdir(self)

        root = Path(tempfile.mkdtemp())
        try:
            (root / "game" / "in_game" / "common").mkdir(parents=True)
            (root / "game" / "in_game" / "common" / "a.txt").write_bytes(b"a = {}\n")
            (root / "game" / "dlc").mkdir()
            with unittest.mock.patch.object(Path, "iterdir", refuse):
                with self.assertRaises(manifest.ManifestError):
                    manifest.collect(root, ("game",))
        finally:
            shutil.rmtree(root, ignore_errors=True)
        print("PASS manifest_unreadable_dlc_directory_degrades")


class VanillaManifestTests(unittest.TestCase):
    """The committed manifest is the naming check's only portable input."""

    def setUp(self) -> None:
        self.path = LINTER_DIR / "data" / "vanilla_paths.txt"
        self.text = self.path.read_text(encoding="utf-8")
        self.paths = sorted(manifest.load(self.path) or ())

    def test_header_records_provenance(self) -> None:
        for key in ("# game-version:", "# generated:", "# paths:"):
            self.assertIn(key, self.text, msg=f"manifest header lacks {key}")
        declared = int(
            next(
                line for line in self.text.splitlines() if line.startswith("# paths:")
            ).split(":", 1)[1]
        )
        self.assertEqual(declared, len(self.paths))
        print("PASS manifest_header_records_provenance")

    def test_entries_are_portable_repo_relative_posix_paths(self) -> None:
        self.assertGreater(len(self.paths), 0, msg="manifest is empty")
        for entry in self.paths:
            self.assertNotIn("\\", entry, msg=f"{entry} uses a Windows separator")
            self.assertFalse(entry.startswith("/"), msg=f"{entry} is absolute")
            self.assertNotIn("..", PurePosixPath(entry).parts, msg=f"{entry} escapes")
            self.assertIn(
                PurePosixPath(entry).parts[0],
                manifest.PHASE_ROOTS,
                msg=f"{entry} is outside the mounted phase roots",
            )
            self.assertIn(
                PurePosixPath(entry).suffix.lower(),
                manifest.EXTENSIONS,
                msg=f"{entry} has an extension outside the manifest's scope",
            )
        print("PASS manifest_entries_are_portable")

    def test_file_is_sorted_and_free_of_duplicates(self) -> None:
        body = [
            line
            for line in self.text.splitlines()
            if line and not line.startswith("#")
        ]
        self.assertEqual(body, sorted(body), msg="manifest body is not sorted")
        self.assertEqual(len(body), len(set(body)), msg="manifest has duplicates")
        print("PASS manifest_is_sorted")


class PrefixExceptionScopeTests(unittest.TestCase):
    """EU5052's staleness half is a claim only a whole-tree run can make.

Reporting a live exception as stale once turned every configured exception
    into a blocking error under ``.githooks/pre-commit``, which lints the staged
    subset, and the first fix was to answer only on whole-tree runs. That was
    too blunt: it also silenced genuinely rotted entries wherever the linter is
    given an explicit path list, which is exactly how CI invokes it.

    Existence is now asked of Git, which answers for the whole repository
    whatever subset a run was handed, so both halves hold at once: a file that
    is really gone is reported at any scope, and a file that merely sits outside
    this run's paths is not. EU5031 and EU5085 do the same. The empty-reason
    half was never a whole-tree claim and stays unguarded.
    """

    STALE = FIXTURES_DIR / "prefix_exception_stale"
    EMPTY_REASON = FIXTURES_DIR / "prefix_exception_invalid"
    OTHER_FILE = "in_game/common/MnT_thing.txt"

    def stage_one_file(self, parent: Path) -> Path:
        """Copy the stale fixture into a throwaway repo with one file staged.

        The staged set needs a repository of its own: run inside this one,
        ``git diff --cached`` would answer with whatever the developer happens
        to have staged.
        """

        root = parent / "mod"
        shutil.copytree(self.STALE, root)
        git = (
            "git",
            "-c",
            "user.name=eu5lint",
            "-c",
            "user.email=eu5lint@invalid",
            "-c",
            "commit.gpgsign=false",
        )
        staged = root / self.OTHER_FILE
        try:
            for arguments in (
                ("init", "-q", "."),
                ("add", "-A"),
                ("commit", "-q", "-m", "fixture"),
            ):
                subprocess.run(
                    (*git, *arguments), cwd=root, check=True, capture_output=True
                )
            staged.write_bytes(staged.read_bytes() + b"# restaged\n")
            subprocess.run(
                (*git, "add", self.OTHER_FILE),
                cwd=root,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            self.skipTest(f"git could not build the staged fixture: {exc}")
        return root

    def test_stale_exception_is_reported_on_a_whole_tree_run(self) -> None:
        result = lint_json(self.STALE, "check")
        self.assertEqual(codes_in(result.stdout)["EU5052"], 1, msg=result.stdout)
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        print("PASS prefix_exception_stale_reported_on_whole_tree")

    def test_stale_exception_is_reported_on_a_single_path_run(self) -> None:
        # Whether the file exists is answered by Git, for the whole tree, so the
        # scope of this particular run no longer decides it. The file really is
        # gone; saying so on a narrow run is correct, not a false positive.
        result = lint_json(self.STALE, "check", (self.OTHER_FILE,))
        self.assertEqual(codes_in(result.stdout)["EU5052"], 1, msg=result.stdout)
        print("PASS prefix_exception_stale_reported_on_single_path")

    def test_stale_exception_is_reported_on_a_staged_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.stage_one_file(Path(tmp))
            result = lint_json(root, "check", ("--staged",))
        self.assertEqual(codes_in(result.stdout)["EU5052"], 1, msg=result.stdout)
        print("PASS prefix_exception_stale_reported_on_staged")

    def test_a_live_exception_out_of_view_stays_silent(self) -> None:
        """The regression the old scope guard existed to prevent.

        An exception naming a file that DOES exist must not be called stale
        merely because this run was handed a different path. That is what turned
        every configured exception into a blocking error under the staged
        pre-commit hook, and it is the half that must keep working.
        """

        # This needs a tree with TWO payload files: the exception has to name one
        # that exists while the run is handed the other. Neither shipped fixture
        # has both, which is why this ran against EMPTY_REASON and a filename
        # from a different fixture -- the linter exited 2 on the missing path,
        # printed nothing, and "no stale line in stdout" passed on an empty
        # string. Adding the exit-code assertion is what surfaced that.
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "mod"
            shutil.copytree(self.STALE, root)
            other = root / "in_game" / "common" / "MnT_other.txt"
            other.write_bytes(b"\xef\xbb\xbfother = {}\n")
            config = root / "eu5lint.toml"
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    'path = "in_game/common/aaa_gone.txt"',
                    'path = "in_game/common/MnT_thing.txt"',
                ),
                encoding="utf-8",
            )
            result = lint_json(root, "check", ("in_game/common/MnT_other.txt",))

        # Assert the run happened before asserting what it did not say. A clean
        # run prints nothing, so absence of output is not the signal -- an exit
        # code outside {0, 1}, or anything on stderr, means the linter failed
        # rather than found nothing, and the assertion below would then pass on
        # an empty string.
        self.assertIn(
            result.returncode, (0, 1), msg=f"linter did not run: {result.stderr}"
        )
        self.assertEqual(result.stderr.strip(), "", msg="linter reported an error")
        stale = [
            line
            for line in result.stdout.splitlines()
            if "no such engine payload file" in line
        ]
        self.assertEqual(stale, [], msg=result.stdout)
        print("PASS prefix_exception_live_but_out_of_view_stays_silent")

    def test_empty_reason_is_reported_whatever_the_scope(self) -> None:
        result = lint_json(
            self.EMPTY_REASON, "check", ("in_game/common/aaa_special.txt",)
        )
        self.assertEqual(codes_in(result.stdout)["EU5052"], 1, msg=result.stdout)
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        print("PASS prefix_exception_empty_reason_ignores_scope")


class NamingCaseSensitivityTests(unittest.TestCase):
    """Case is the whole point, so it is asserted rather than assumed.

    A case-insensitive filesystem cannot answer these questions, which is why
    the check reads filenames from Git instead of from disk.
    """

    PREFIXES = ("MnT_", "mnt_", "RGO_")

    def test_exact_match_beats_case_variants(self) -> None:
        self.assertEqual(
            naming.prefix_state("MnT_thing.txt", self.PREFIXES),
            (naming.EXACT, "MnT_"),
        )
        self.assertEqual(
            naming.prefix_state("mnt_thing.txt", self.PREFIXES),
            (naming.EXACT, "mnt_"),
        )
        print("PASS naming_exact_match_beats_case_variants")

    def test_case_variant_is_a_near_miss_not_a_match(self) -> None:
        state, matched = naming.prefix_state("Mnt_thing.txt", self.PREFIXES)
        self.assertEqual(state, naming.NEAR_MISS)
        self.assertIn(matched, self.PREFIXES)
        # A second prefix, so the rule is shown to be about case rather than
        # about one prefix: `RGO_` is configured, `rgo_` is not a match for it.
        self.assertEqual(
            naming.prefix_state("rgo_buildings.txt", self.PREFIXES)[0],
            naming.NEAR_MISS,
        )
        print("PASS naming_case_variant_is_a_near_miss")

    def test_double_prefix_needs_both_halves_exact(self) -> None:
        self.assertEqual(
            naming.double_prefix("MnT_RGO_buildings.txt", self.PREFIXES),
            ("MnT_", "RGO_"),
        )
        self.assertIsNone(
            naming.double_prefix("MnT_rgo_buildings.txt", self.PREFIXES)
        )
        self.assertIsNone(naming.double_prefix("RGO_buildings.txt", self.PREFIXES))
        print("PASS naming_double_prefix_needs_both_halves_exact")

    def test_suggestion_is_offered_only_where_it_is_certain(self) -> None:
        forced = ("**/modifier_type_definitions/**", "**/cultures/**")
        # A wrong-cased prefix outside a forced directory: one right answer.
        self.assertEqual(
            naming.suggest_name(
                "in_game/common/script_values/mnt_centers.txt",
                "mnt_centers.txt",
                naming.NEAR_MISS,
                "MnT_",
                forced,
            ),
            "MnT_centers.txt",
        )
        # Inside a forced directory the directory rule wins, so the answer is
        # lowercase -- not the prefix's configured capitalization.
        self.assertEqual(
            naming.suggest_name(
                "in_game/common/modifier_type_definitions/Mnt_types.txt",
                "Mnt_types.txt",
                naming.NEAR_MISS,
                "MnT_",
                forced,
            ),
            "mnt_types.txt",
        )
        # Already correct in a forced directory: nothing to suggest.
        self.assertIsNone(
            naming.suggest_name(
                "in_game/common/modifier_type_definitions/mnt_types.txt",
                "mnt_types.txt",
                naming.NEAR_MISS,
                "MnT_",
                forced,
            )
        )
        # An unprefixed new file: which subsystem owns it is a human decision,
        # so the checker stays silent rather than guessing.
        self.assertIsNone(
            naming.suggest_name(
                "in_game/common/loose/thing.txt",
                "thing.txt",
                naming.NONE,
                "",
                forced,
            )
        )
        print("PASS naming_suggestion_only_where_certain")

    def test_only_manifest_scoped_engine_payload_is_checked(self) -> None:
        self.assertTrue(naming.is_checkable("in_game/common/x/MnT_a.txt"))
        self.assertFalse(naming.is_checkable("tools/eu5lint/config.py"))
        self.assertFalse(naming.is_checkable(".metadata/metadata.json"))
        self.assertFalse(naming.is_checkable("in_game/gfx/icons/MnT_a.dds"))
        self.assertFalse(naming.is_checkable("in_game/common/x/.gitkeep"))
        print("PASS naming_scope_is_manifest_backed_engine_payload")


class FixBomTests(unittest.TestCase):
    """Exercise the one command that WRITES to the tree.

    Every other command reports; this one rewrites files in place, so a mistake
    here damages the mod rather than merely misinforming. It is always run
    against a throwaway copy, never the fixture itself.
    """

    BOM = b"\xef\xbb\xbf"
    FIXTURE = "fix_bom"
    ADDS = "in_game/common/MnT_needs_bom.txt"
    KEEPS = "in_game/common/MnT_has_bom.txt"
    REMOVES = "main_menu/setup/start/MnT_start.txt"
    LEAVES = "main_menu/setup/templates/MnT_tmpl.txt"

    def _copy(self, tmp: str) -> Path:
        staged = Path(tmp) / self.FIXTURE
        shutil.copytree(FIXTURES_DIR / self.FIXTURE, staged)
        return staged

    def _fix(self, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(LINTER_DIR),
                "fix-bom",
                "--root",
                str(root),
                "--config",
                str(root / "eu5lint.toml"),
                *extra,
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

    def _state(self, root: Path) -> dict[str, bool]:
        return {
            rel: (root / rel).read_bytes().startswith(self.BOM)
            for rel in (self.ADDS, self.KEEPS, self.REMOVES, self.LEAVES)
        }

    def test_dry_run_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(tmp)
            before = {
                rel: (root / rel).read_bytes()
                for rel in (self.ADDS, self.KEEPS, self.REMOVES, self.LEAVES)
            }
            result = self._fix(root, "--dry-run")
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn(self.ADDS, result.stdout)
            self.assertIn(self.REMOVES, result.stdout)
            for rel, data in before.items():
                self.assertEqual(
                    (root / rel).read_bytes(), data, msg=f"--dry-run wrote {rel}"
                )
        print("PASS fix_bom_dry_run_changes_nothing")

    def test_only_required_and_forbidden_are_touched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(tmp)
            self.assertEqual(
                self._state(root),
                {
                    self.ADDS: False,
                    self.KEEPS: True,
                    self.REMOVES: True,
                    self.LEAVES: False,
                },
            )
            result = self._fix(root)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            # required gains one, forbidden loses one, already-correct is left,
            # and warn_required is advisory so fix-bom must not act on it.
            self.assertEqual(
                self._state(root),
                {
                    self.ADDS: True,
                    self.KEEPS: True,
                    self.REMOVES: False,
                    self.LEAVES: False,
                },
            )
        print("PASS fix_bom_touches_only_required_and_forbidden")

    def test_content_survives_and_a_second_run_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(tmp)
            payload = {
                rel: (root / rel).read_bytes().removeprefix(self.BOM)
                for rel in (self.ADDS, self.KEEPS, self.REMOVES, self.LEAVES)
            }
            self._fix(root)
            after_once = {
                rel: (root / rel).read_bytes()
                for rel in (self.ADDS, self.KEEPS, self.REMOVES, self.LEAVES)
            }
            for rel, body in payload.items():
                self.assertEqual(
                    after_once[rel].removeprefix(self.BOM),
                    body,
                    msg=f"fix-bom altered the body of {rel}",
                )
            self._fix(root)
            for rel, data in after_once.items():
                self.assertEqual(
                    (root / rel).read_bytes(), data, msg=f"second run rewrote {rel}"
                )
        print("PASS fix_bom_preserves_content_and_is_idempotent")


if __name__ == "__main__":
    unittest.main()
