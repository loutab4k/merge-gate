"""Deterministic checks that decide, before any LLM runs, whether a PR may be reviewed for merge."""

import re
from collections.abc import Iterator

from .config import Config
from .globs import first_match
from .model import (
    Assessment,
    ChangeClass,
    ChangedFile,
    FileStatus,
    PullRequest,
    Reason,
    ReasonCode,
)

# Added lines containing one of these in a test file disable, narrow or stop collecting tests.
# A false hit only sends the PR to a human, so plain substrings are enough.
SKIP_MARKERS = (
    # Go
    ".Skip(",
    ".Skipf(",
    ".SkipNow(",
    # Any build constraint drops a test file from a plain `go test ./...` on some platform or tag set.
    "//go:build",
    "// +build",
    # Python
    "mark.skip",
    "mark.xfail",
    "pytest.skip(",
    "pytest.xfail(",
    "pytest.importorskip(",
    "unittest.skip",
    "SkipTest",
    "skipTest(",
    "expectedFailure",
    "collect_ignore",
    # JavaScript and TypeScript
    ".skip(",
    ".skip.",
    ".skipIf(",
    ".only(",
    ".only.",
    ".todo(",
    ".fails(",
    # Rust
    "#[ignore",
)
# Focus and skip functions, matched only as a whole name: `xit(` must not hit `exit(`, nor `fit(` `model.fit(`.
SKIP_FUNCTIONS = ("xit(", "xdescribe(", "xtest(", "fit(", "fdescribe(", "skip(")
_SKIP = re.compile(
    "|".join(
        [re.escape(m) for m in SKIP_MARKERS]
        + [r"(?<![\w.$])" + re.escape(f) for f in SKIP_FUNCTIONS]
    )
)

# GitHub's diff media type refuses a PR with more files than this (HTTP 406).
MAX_DIFF_FILES = 300

_SEMVER = r"v?([0-9]{1,9})\.([0-9]{1,9})\.([0-9]{1,9})"
# Dependabot's single-dependency title, optionally behind a conventional-commit prefix.
_DEPENDABOT_TITLE = re.compile(
    r"(?:[a-z]+(?:\([A-Za-z0-9_./-]+\))?: )?[Bb]ump (\S+) from "
    + _SEMVER
    + " to "
    + _SEMVER
    + r"(?: in \S+)?"
)


def added_lines(patch: str) -> Iterator[str]:
    # GitHub's per-file patch starts at the first hunk, so it has no `+++` header to skip.
    # Split on "\n" only: str.splitlines() also splits on characters a PR can hide inside a line.
    for line in patch.split("\n"):
        if line.startswith("+"):
            yield line[1:]


def skip_marker_in(patch: str) -> str | None:
    for line in added_lines(patch):
        m = _SKIP.search(line)
        if m is not None:
            return m.group()
    return None


def parse_dependabot_bump(title: str) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    m = _DEPENDABOT_TITLE.fullmatch(title)
    if m is None:
        return None
    nums = tuple(int(g) for g in m.groups()[1:7])
    return nums[:3], nums[3:]


def _is_candidate(pr: PullRequest, config: Config) -> bool:
    if pr.author in config.bots:
        return True
    return pr.author == config.owner and pr.head_ref.startswith(config.agent_branch_prefixes)


def _classify(pr: PullRequest, files: list[ChangedFile], config: Config) -> tuple[ChangeClass, list[Reason]]:
    paths = [f.path for f in files]

    def all_in(globs) -> bool:
        return bool(paths) and all(first_match(globs, p) for p in paths)

    if pr.author in config.bots and all_in(config.dependency_files):
        bump = parse_dependabot_bump(pr.title)
        if bump is None:
            return ChangeClass.DEPS_OTHER, []
        old, new = bump
        if new < old:
            return ChangeClass.DEPS_OTHER, [Reason(ReasonCode.VERSION_DOWNGRADE, f"{pr.title}")]
        if new[:2] == old[:2]:
            return ChangeClass.DEPS_PATCH, []
        return ChangeClass.DEPS_OTHER, []
    if all_in(config.docs):
        return ChangeClass.DOCS, []
    if all_in(config.tests):
        return ChangeClass.TESTS, []
    return ChangeClass.CODE, []


def _file_reasons(f: ChangedFile, config: Config) -> list[Reason]:
    reasons = []
    for path in {f.path, f.previous_path} - {None}:
        for code, globs in ((ReasonCode.AGENT_CONFIG, config.agent_config), (ReasonCode.CRITICAL_PATH, config.critical)):
            glob = first_match(globs, path)
            if glob is not None:
                reasons.append(Reason(code, f"{path} matches {glob.pattern}"))
    was_test = f.previous_path is not None and first_match(config.tests, f.previous_path)
    if not (was_test or first_match(config.tests, f.path)):
        return reasons
    # A renamed test can stop being collected while still matching test_paths
    # (tests/test_a.py -> tests/a_cases.py, x_test.go -> testdata/x_test.go), so any rename counts.
    if f.status is FileStatus.REMOVED or (f.status is FileStatus.RENAMED and was_test):
        reasons.append(Reason(ReasonCode.TEST_DELETED, f"{f.previous_path or f.path} {f.status.value}"))
    elif f.patch is None and f.additions > 0:
        reasons.append(Reason(ReasonCode.UNINSPECTABLE_TEST, f"{f.path}: GitHub returned no patch"))
    elif f.patch is not None:
        marker = skip_marker_in(f.patch)
        if marker is not None:
            reasons.append(Reason(ReasonCode.SKIP_MARKER, f"{f.path} adds {marker}"))
    return reasons


def assess(
    pr: PullRequest,
    files: list[ChangedFile],
    ci_green: bool,
    config: Config,
) -> Assessment:
    changed_lines = sum(f.additions + f.deletions for f in files)
    change_class, reasons = _classify(pr, files, config)
    if pr.draft:
        reasons.append(Reason(ReasonCode.DRAFT, "draft PR"))
    if not _is_candidate(pr, config):
        reasons.append(
            Reason(ReasonCode.NOT_CANDIDATE, f"author {pr.author}, branch {pr.head_ref}")
        )
    if not ci_green:
        reasons.append(Reason(ReasonCode.CI_NOT_GREEN, "the CI run did not succeed"))
    if len(files) > MAX_DIFF_FILES:
        reasons.append(Reason(ReasonCode.TOO_LARGE, f"{len(files)} files > {MAX_DIFF_FILES}"))
    if changed_lines > config.max_changed_lines:
        reasons.append(
            Reason(ReasonCode.TOO_LARGE, f"{changed_lines} changed lines > {config.max_changed_lines}")
        )
    for f in files:
        reasons.extend(_file_reasons(f, config))
    return Assessment(pr, change_class, changed_lines, tuple(reasons))
