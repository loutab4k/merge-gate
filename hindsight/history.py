"""What happened to a PR after its verdict, read from GitHub: later PRs, reverts, CI on main, blame."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .gh import Gh

# A failed push run on the merge commit; `cancelled` is left out (a newer push cancels it).
RED = frozenset({"failure", "timed_out", "startup_failure"})
HUNK = re.compile(r"@@ -([0-9]+)(?:,[0-9]+)? \+[0-9]+(?:,[0-9]+)? @@")
# A later PR's title that says it repairs something. Line overlap alone, or with a mention of the
# PR, also catches planned evolution: merge-gate#3 rewrote mutants that #1 wrote, for its own change.
FIX_TITLE = re.compile(r"\b(?:fix(?:es|ed|ing)?|hotfix|bug(?:s|fix)?|regressions?|broken?|typo)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Pull:
    number: int
    url: str
    state: str
    base: str
    head_sha: str
    merged_at: datetime | None
    merge_sha: str | None
    title: str
    body: str

    @classmethod
    def parse(cls, raw: dict) -> "Pull":
        merged = raw["merged_at"]
        return cls(
            number=raw["number"],
            url=raw["html_url"],
            state=raw["state"],
            base=raw["base"]["ref"],
            head_sha=raw["head"]["sha"],
            merged_at=datetime.fromisoformat(merged) if merged else None,
            merge_sha=raw["merge_commit_sha"] if merged else None,
            title=raw["title"],
            body=raw["body"] or "",
        )


@dataclass(frozen=True)
class Later:
    """A PR merged into the same base inside the window, and how it relates to the graded PR."""

    pull: Pull
    reverts: bool
    names_pr: bool
    fix_title: bool
    shared_files: tuple[str, ...]
    overlap_files: tuple[str, ...]
    patches: tuple[tuple[str, str], ...]

    @property
    def related(self) -> bool:
        return self.reverts or self.names_pr or bool(self.shared_files)


@dataclass(frozen=True)
class CiRun:
    name: str
    conclusion: str | None
    url: str


@dataclass(frozen=True)
class Facts:
    pull: Pull
    window_end: datetime
    later: tuple[Later, ...]
    push_runs: tuple[CiRun, ...]
    own_patches: tuple[tuple[str, str], ...]


def removed_lines(patch: str) -> list[int]:
    """Old-side line numbers a unified-diff patch removes or changes. Lines are split on "\\n" only:
    file content may hold other characters that `splitlines` would treat as line breaks."""
    out, old = [], None
    for line in patch.split("\n"):
        m = HUNK.match(line)
        if m:
            old = int(m[1])
        elif old is None or line.startswith("\\"):
            continue
        elif line.startswith("-"):
            out.append(old)
            old += 1
        elif not line.startswith("+"):
            old += 1
    return out


def names(text: str, repo: str, number: int) -> bool:
    short = re.search(rf"(?<![\w/#-])#{number}\b", text)
    return bool(short or re.search(rf"\b{re.escape(repo)}(?:#|/pull/){number}\b", text))


class History:
    def __init__(self, gh: Gh, repo: str, pulls: dict[int, Pull], window: timedelta, as_of: datetime):
        self.gh = gh
        self.repo = repo
        self.pulls = pulls
        self.window = window
        self.as_of = as_of

    def facts(self, pull: Pull) -> Facts:
        assert pull.merged_at is not None and pull.merge_sha is not None
        files = self.gh.pages(f"repos/{self.repo}/pulls/{pull.number}/files?per_page=100")
        own_paths = {f["filename"] for f in files} | {f["previous_filename"] for f in files if "previous_filename" in f}
        own_commits = {pull.merge_sha} | {
            c["sha"] for c in self.gh.pages(f"repos/{self.repo}/pulls/{pull.number}/commits?per_page=100")
        }
        end = pull.merged_at + self.window
        candidates = [
            p
            for p in self.pulls.values()
            if p.merged_at and pull.merged_at < p.merged_at <= min(end, self.as_of) and p.base == pull.base
        ]
        later = [self._later(pull, p, own_paths, own_commits) for p in sorted(candidates, key=lambda p: p.number)]
        runs = self.gh.get(f"repos/{self.repo}/actions/runs?head_sha={pull.merge_sha}&event=push&per_page=100")
        return Facts(
            pull=pull,
            window_end=end,
            later=tuple(l for l in later if l.related),
            push_runs=tuple(
                CiRun(r["name"], r["conclusion"], r["html_url"])
                for r in sorted(runs["workflow_runs"], key=lambda r: r["id"])
            ),
            own_patches=tuple(sorted((f["filename"], f.get("patch", "")) for f in files)),
        )

    def _later(self, pull: Pull, later: Pull, own_paths: set[str], own_commits: set[str]) -> Later:
        commit = self.gh.get(f"repos/{self.repo}/commits/{later.merge_sha}")
        parent = commit["parents"][0]["sha"]
        # A merge commit's net change is the diff from its first parent; a squash commit has one parent.
        if len(commit["parents"]) == 1:
            changed = commit["files"]
        else:
            changed = self.gh.get(f"repos/{self.repo}/compare/{parent}...{later.merge_sha}")["files"]
        shared, overlap, patches = [], [], []
        for f in changed:
            old_path = f.get("previous_filename", f["filename"])
            if old_path not in own_paths and f["filename"] not in own_paths:
                continue
            shared.append(f["filename"])
            patches.append((f["filename"], f.get("patch", "")))
            lines = removed_lines(f.get("patch", ""))
            if lines and old_path in own_paths and self._blamed(parent, old_path, lines, own_commits):
                overlap.append(f["filename"])
        return Later(
            pull=later,
            reverts=bool(shared) and self._reverts(pull, later, commit["commit"]["message"], own_commits),
            names_pr=names(f"{later.title}\n{later.body}", self.repo, pull.number),
            fix_title=FIX_TITLE.search(later.title) is not None,
            shared_files=tuple(sorted(shared)),
            overlap_files=tuple(sorted(overlap)),
            patches=tuple(sorted(patches)),
        )

    def _reverts(self, pull: Pull, later: Pull, merge_message: str, own_commits: set[str]) -> bool:
        """GitHub's revert button (title and body); `git revert` of the PR's merge commit named in the
        later merge message or body; or a later branch commit reverting any of the PR's commits. The
        PR's own commits are skipped: a PR stacked on it lists them, in-branch reverts included, and
        a squash message repeats them. A revert always touches the PR's files, so only a later PR
        that shares one is asked."""
        if later.title == f'Revert "{pull.title}"':
            return True
        if re.search(rf"\bReverts {re.escape(self.repo)}#{pull.number}\b", later.body):
            return True
        if any(f"This reverts commit {pull.merge_sha}" in m for m in (merge_message, later.body)):
            return True
        branch = self.gh.pages(f"repos/{self.repo}/pulls/{later.number}/commits?per_page=100")
        messages = [c["commit"]["message"] for c in branch if c["sha"] not in own_commits]
        return any(f"This reverts commit {sha}" in m for sha in own_commits for m in messages)

    def _blamed(self, oid: str, path: str, lines: list[int], commits: set[str]) -> bool:
        ranges = self.gh.blame(self.repo, oid, path)
        return any(first <= n <= last and c in commits for first, last, c in ranges for n in lines)
