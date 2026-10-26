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

# Added lines containing one of these in a test file disable or narrow tests. A false hit only
# sends the PR to a human, so plain substrings are enough.
SKIP_MARKERS = (
    "t.Skip(",
    "t.Skipf(",
    "t.SkipNow(",
    "@pytest.mark.skip",
    "@pytest.mark.xfail",
    "pytest.skip(",
    "@unittest.skip",
    "@unittest.expectedFailure",
    ".skip(",
    ".only(",
    ".todo(",
    ".fails(",
    "xit(",
    "xdescribe(",
    "xtest(",
    "#[ignore",
)

_SEMVER = r"v?(\d{1,9})\.(\d{1,9})\.(\d{1,9})"
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
        for marker in SKIP_MARKERS:
            if marker in line:
                return marker
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
    return pr.author == config.owner and pr.head_ref.startswith(config.agent_branch_prefix)


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
        glob = first_match(config.critical, path)
        if glob is not None:
            reasons.append(Reason(ReasonCode.CRITICAL_PATH, f"{path} matches {glob.pattern}"))
    if not first_match(config.tests, f.path) and not (
        f.previous_path and first_match(config.tests, f.previous_path)
    ):
        return reasons
    if f.status is FileStatus.REMOVED or (
        f.status is FileStatus.RENAMED and not first_match(config.tests, f.path)
    ):
        reasons.append(Reason(ReasonCode.TEST_DELETED, f.previous_path or f.path))
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
    files_complete: bool,
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
    if not files_complete:
        reasons.append(Reason(ReasonCode.TOO_LARGE, "GitHub lists at most 3000 files"))
    if changed_lines > config.max_changed_lines:
        reasons.append(
            Reason(ReasonCode.TOO_LARGE, f"{changed_lines} changed lines > {config.max_changed_lines}")
        )
    for f in files:
        reasons.extend(_file_reasons(f, config))
    return Assessment(pr, change_class, changed_lines, tuple(reasons))
