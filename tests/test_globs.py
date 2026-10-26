import pytest
from hypothesis import given
from hypothesis import strategies as st

from merge_gate.globs import compile_glob

segment = st.text(st.characters(blacklist_characters="/*?\x00{}[]!"), min_size=1, max_size=8)
path = st.lists(segment, min_size=1, max_size=5).map("/".join)
any_text = st.text(max_size=30)


@given(path, path)
def test_literal_pattern_matches_only_itself(pattern, candidate):
    assert compile_glob(pattern).matches(candidate) == (pattern == candidate)


@given(segment, any_text)
def test_star_stays_inside_one_segment(prefix, rest):
    assert compile_glob(prefix + "/*").matches(f"{prefix}/{rest}") == ("/" not in rest)


@given(st.lists(segment, max_size=4), segment)
def test_double_star_slash_matches_any_depth(dirs, name):
    assert compile_glob(f"**/{name}").matches("/".join([*dirs, name]))


@given(segment, st.lists(segment, min_size=1, max_size=4))
def test_trailing_double_star_matches_everything_below(top, rest):
    glob = compile_glob(f"{top}/**")
    assert glob.matches("/".join([top, *rest]))
    assert not glob.matches(top + "x/" + rest[0])


@given(any_text, any_text)
def test_any_pattern_compiles_or_is_refused_and_matches_without_error(pattern, candidate):
    try:
        glob = compile_glob(pattern)
    except ValueError:
        return
    glob.matches(candidate)


def test_examples():
    assert compile_glob(".github/**").matches(".github/workflows/ci.yml")
    assert not compile_glob(".github/**").matches("src/.github/x")
    assert compile_glob("**/CLAUDE.md").matches("CLAUDE.md")
    assert compile_glob("**/CLAUDE.md").matches("a/b/CLAUDE.md")
    assert not compile_glob("**/CLAUDE.md").matches("a/NOTCLAUDE.md")
    assert compile_glob("**/*_test.go").matches("pkg/x/y_test.go")
    assert not compile_glob("**/*_test.go").matches("pkg/x/y_test.go.bak")
    assert not compile_glob("a.b").matches("axb")
    assert compile_glob("**/claude.md", ignore_case=True).matches("pkg/CLAUDE.md")
    assert compile_glob(".claude/**", ignore_case=True).matches(".Claude/settings.json")
    assert not compile_glob("**/claude.md").matches("pkg/CLAUDE.md")
    for dialect in ["/billing/**", "billing/", "!x", "**/*.{a,b}", "[ab]"]:
        with pytest.raises(ValueError):
            compile_glob(dialect)
