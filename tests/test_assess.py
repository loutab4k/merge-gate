from hypothesis import given
from hypothesis import strategies as st

from merge_gate.assess import SKIP_FUNCTIONS, SKIP_MARKERS, assess, parse_dependabot_bump, skip_marker_in
from merge_gate.config import BUILTIN_CRITICAL
from merge_gate.globs import compile_glob
from merge_gate.model import ChangeClass, FileStatus, ReasonCode

from .helpers import CONFIG, changed, pr

clean_line = st.text(st.characters(blacklist_characters="\n\r"), max_size=40).filter(
    lambda s: skip_marker_in(f"+{s} ") is None
)


def codes(a):
    return {r.code for r in a.reasons}


def run(p=None, files=None, ci_green=True):
    return assess(p or pr(), files if files is not None else [changed("src/app.go")], ci_green, CONFIG)


def test_owner_agent_pr_with_plain_code_needs_review():
    a = run()
    assert a.needs_review and a.change_class is ChangeClass.CODE


def test_critical_paths_route_to_a_human():
    for path in [
        ".github/workflows/ci.yml",
        "CLAUDE.md",
        "pkg/AGENTS.md",
        ".claude/settings.json",
        "billing/charge.go",
        "pkg/claude.md",
        ".Claude/settings.json",
        "Billing/charge.go",
    ]:
        a = run(files=[changed(path)])
        assert ReasonCode.CRITICAL_PATH in codes(a), path


def test_rename_out_of_a_critical_path_counts_as_critical():
    a = run(files=[changed("src/x.yml", FileStatus.RENAMED, previous_path=".github/workflows/x.yml")])
    assert ReasonCode.CRITICAL_PATH in codes(a)


def test_non_candidates():
    assert ReasonCode.NOT_CANDIDATE in codes(run(pr(author="someone")))
    assert ReasonCode.NOT_CANDIDATE in codes(run(pr(head_ref="feature")))
    assert ReasonCode.DRAFT in codes(run(pr(draft=True)))
    assert run(pr(author="dependabot[bot]", head_ref="dependabot/go/x")).needs_review


def test_ci_not_green_and_size_limits():
    assert ReasonCode.CI_NOT_GREEN in codes(run(ci_green=False))
    renames = [changed(f"r/{i}.go", FileStatus.RENAMED, previous_path=f"o/{i}.go", additions=0, deletions=0) for i in range(301)]
    assert ReasonCode.TOO_LARGE in codes(run(files=renames))
    assert ReasonCode.TOO_LARGE not in codes(run(files=renames[:300]))
    assert ReasonCode.TOO_LARGE in codes(run(files=[changed("a.go", additions=801, deletions=0)]))
    assert ReasonCode.TOO_LARGE not in codes(run(files=[changed("a.go", additions=800, deletions=0)]))


def test_test_weakening():
    assert ReasonCode.TEST_DELETED in codes(run(files=[changed("x_test.go", FileStatus.REMOVED)]))
    assert ReasonCode.TEST_DELETED in codes(
        run(files=[changed("x.go", FileStatus.RENAMED, previous_path="x_test.go")])
    )
    for renamed_away in ["tests/a_cases.py", "pkg/testdata/x_test.go"]:
        moved = changed(renamed_away, FileStatus.RENAMED, previous_path="tests/test_a.py")
        assert ReasonCode.TEST_DELETED in codes(run(files=[moved])), renamed_away
    skip = changed("x_test.go", patch="@@ -1 +1,2 @@\n func TestX(t *testing.T) {\n+\tt.Skip(\"flaky\")")
    assert ReasonCode.SKIP_MARKER in codes(run(files=[skip]))
    assert ReasonCode.SKIP_MARKER in codes(run(files=[changed("conftest.py", patch="+collect_ignore = ['tests']")]))
    for hidden in [
        "+\x1et.Skip(",
        "+\u2028it.only(",
        "+++i; it.only(",
        "+\tself.skipTest('x')",
        "+\tpytest.xfail('x')",
        "+pytest.importorskip('x')",
        "+\traise unittest.SkipTest('x')",
        "+//go:build ignore",
        "+\ts.T().Skip(\"x\")",
        "+fit('x', () => {",
        "+fdescribe('x', () => {",
        "+test.skipIf(true)('x', () => {",
        "+it.skip.each([1])('x', () => {",
        "+describe.only.each([1])('x', () => {",
    ]:
        assert skip_marker_in(f"@@ -1 +1 @@\n{hidden}") is not None, repr(hidden)
    for innocent in ["+\tos.exit(1)", "+model.fit(x, y)", "+benefit(x)", "+\tprofit = 1"]:
        assert skip_marker_in(f"@@ -1 +1 @@\n{innocent}") is None, repr(innocent)
    assert ReasonCode.UNINSPECTABLE_TEST in codes(run(files=[changed("x_test.go", patch=None)]))
    assert run(files=[changed("x_test.go", patch=None, additions=0, deletions=3)]).needs_review


def test_classes():
    assert run(files=[changed("README.md"), changed("docs/a.txt")]).change_class is ChangeClass.DOCS
    assert run(files=[changed("a_test.go")]).change_class is ChangeClass.TESTS
    bot = pr(author="dependabot[bot]", head_ref="dependabot/go/x", title="Bump golang.org/x/net from 0.30.0 to 0.30.1")
    assert run(bot, files=[changed("go.mod"), changed("go.sum")]).change_class is ChangeClass.DEPS_PATCH
    minor = pr(author="dependabot[bot]", title="chore(deps): bump vitest from 3.1.0 to 3.2.0 in /web")
    assert run(minor, files=[changed("web/package.json")]).change_class is ChangeClass.DEPS_OTHER
    down = pr(author="dependabot[bot]", title="Bump x from 2.0.0 to 1.9.9")
    a = run(down, files=[changed("go.mod")])
    assert a.change_class is ChangeClass.DEPS_OTHER and ReasonCode.VERSION_DOWNGRADE in codes(a)
    assert run(files=[]).change_class is ChangeClass.CODE


@given(st.lists(clean_line, max_size=6), st.sampled_from(SKIP_MARKERS + SKIP_FUNCTIONS), clean_line, clean_line)
def test_skip_marker_found_only_on_added_lines(lines, marker, before, after):
    base = "".join(f" {line}\n" for line in lines)
    assert skip_marker_in(base) is None
    assert skip_marker_in(base + f"+{before} {marker}{after}\n") is not None
    assert skip_marker_in(base + f"-{before} {marker}{after}\n") is None
    assert skip_marker_in(base + f" {before} {marker}{after}\n") is None


versions = st.tuples(*[st.integers(0, 10**6)] * 3)
dep_name = st.text(st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-./@"), min_size=1, max_size=20)


@given(dep_name, versions, versions)
def test_dependabot_title_round_trip(name, old, new):
    title = f"Bump {name} from {'.'.join(map(str, old))} to {'.'.join(map(str, new))}"
    assert parse_dependabot_bump(title) == (old, new)


@given(st.text(max_size=80))
def test_dependabot_parser_parses_only_ascii_bump_titles(title):
    result = parse_dependabot_bump(title)
    if result is not None:
        assert " from " in title and " to " in title and title.isascii()


def test_dependabot_parser_refuses_near_misses():
    for title in [
        "Bump the npm group with 3 updates",
        "Bump x from 1.2 to 1.3",
        "Bump x from 1.2.3 to 1.2.4; also rewrite auth",
        "Bump x from 1.2.3-rc1 to 1.2.4",
        "Bump x from 1.2.3 to 1.2.٤",
        "Bump x from 1.2.3 to 1.2.４",
    ]:
        assert parse_dependabot_bump(title) is None, title


critical_path = st.sampled_from(BUILTIN_CRITICAL + ("billing/**",)).map(
    lambda g: g.replace("**/", "x/").replace("**", "y").replace("*", "z")
)


@given(critical_path, st.lists(st.sampled_from(["src/a.go", "README.md", "a_test.go"]), max_size=3))
def test_any_critical_file_blocks_review(critical, others):
    assert any(compile_glob(g).matches(critical) for g in BUILTIN_CRITICAL + ("billing/**",))
    a = run(files=[changed(p) for p in [*others, critical]])
    assert not a.needs_review and ReasonCode.CRITICAL_PATH in codes(a)
