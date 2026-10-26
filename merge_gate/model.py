"""Facts about one pull request and what the gate concluded from them."""

from dataclasses import dataclass, field
from enum import Enum


class FileStatus(Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    RENAMED = "renamed"
    COPIED = "copied"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class PullRequest:
    number: int
    author: str
    head_ref: str
    head_sha: str
    draft: bool
    title: str


@dataclass(frozen=True)
class ChangedFile:
    path: str
    previous_path: str | None
    status: FileStatus
    additions: int
    deletions: int
    patch: str | None


class ChangeClass(Enum):
    DEPS_PATCH = "deps-patch"
    DEPS_OTHER = "deps-other"
    DOCS = "docs"
    TESTS = "tests"
    CODE = "code"


class ReasonCode(Enum):
    DRAFT = "draft"
    NOT_CANDIDATE = "not-candidate"
    CI_NOT_GREEN = "ci-not-green"
    CRITICAL_PATH = "critical-path"
    TEST_DELETED = "test-deleted"
    SKIP_MARKER = "skip-marker"
    UNINSPECTABLE_TEST = "uninspectable-test"
    VERSION_DOWNGRADE = "version-downgrade"
    TOO_LARGE = "too-large"
    NO_REVIEW = "no-review"
    REVIEW_MANUAL = "review-manual"
    LOW_CONFIDENCE = "low-confidence"
    BLOCKING_FINDING = "blocking-finding"
    UNMET_CRITERION = "unmet-criterion"
    NO_CRITERIA = "no-criteria"


# Reasons that still route the PR to a human but leave the review to run, so shadow mode measures
# the reviewer on the riskiest PRs too.
REVIEWED_ANYWAY = frozenset({ReasonCode.CRITICAL_PATH})


@dataclass(frozen=True)
class Reason:
    code: ReasonCode
    detail: str


@dataclass(frozen=True)
class Assessment:
    pr: PullRequest
    change_class: ChangeClass
    changed_lines: int
    reasons: tuple[Reason, ...] = field(default=())

    @property
    def needs_review(self) -> bool:
        return all(r.code in REVIEWED_ANYWAY for r in self.reasons)
