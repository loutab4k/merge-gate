"""A synthetic repository in the shapes of the recorded GitHub responses, one PR per outcome."""

import json
from datetime import datetime, timedelta, timezone

from hindsight.__main__ import SHADOW_START
from merge_gate.model import Assessment, ChangeClass, PullRequest, Reason, ReasonCode
from merge_gate.verdict import decide, parse_review, render_comment

REPO = "owner/proj"
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
AS_OF = T0 + timedelta(days=200)
GOOD_REVIEW = {"verdict": "merge", "confidence": 9, "summary": "ok", "findings": [],
               "criteria": [{"criterion": "works", "met": True, "evidence": "test"}]}


def merge_sha(n: int) -> str:
    return f"{n:040d}"


def head_sha(n: int) -> str:
    return f"{n:039d}f"


def patch(old_line: int) -> str:
    return f"@@ -{old_line},1 +{old_line},1 @@\n-old\n+new"


def comment_body(n: int, critical: bool = False, review: dict | None = GOOD_REVIEW) -> str:
    """The gate's own comment for PR n, from merge_gate's renderer."""
    reasons = (Reason(ReasonCode.CRITICAL_PATH, ".github/x"),) if critical else ()
    a = Assessment(PullRequest(n, "owner", "ai/x", head_sha(n), False, "t"), ChangeClass.CODE, 10, reasons)
    return render_comment(decide(a, parse_review(json.dumps(review)) if review else None), f"https://run/{n}")


class FakeRepo:
    def __init__(self):
        self.responses = {}
        self.comments = []
        self.pulls = []

    def comment(self, issue: int, body: str, author: str = "github-actions[bot]") -> None:
        self.comments.append({
            "html_url": f"https://github.com/{REPO}/pull/{issue}#issuecomment-{len(self.comments)}",
            "issue_url": f"https://api.github.com/repos/{REPO}/issues/{issue}",
            "user": {"login": author},
            "body": body,
        })

    def unmerged(self, n: int, state: str) -> None:
        self.pulls.append(self._pull(n, None, state, "t", ""))

    def merged(self, n: int, at: datetime, files: list[dict], title: str = "Add x", body: str = "",
               message: str | None = None, runs: tuple[str, ...] = (), two_parents: bool = False,
               branch_message: str = "work") -> None:
        self.pulls.append(self._pull(n, at, "closed", title, body))
        base = f"repos/{REPO}"
        self.responses[f"PAGES {base}/pulls/{n}/files?per_page=100"] = [files]
        self.responses[f"PAGES {base}/pulls/{n}/commits?per_page=100"] = [
            [{"sha": head_sha(n), "commit": {"message": branch_message}}]
        ]
        self.responses[f"GET {base}/actions/runs?head_sha={merge_sha(n)}&event=push&per_page=100"] = {
            "workflow_runs": [
                {"id": i, "name": "check", "conclusion": c, "html_url": f"https://runs/{n}/{i}"}
                for i, c in enumerate(runs)
            ]
        }
        parents = [{"sha": self.parent(n)}] + ([{"sha": head_sha(n)}] if two_parents else [])
        self.responses[f"GET {base}/commits/{merge_sha(n)}"] = {
            "parents": parents,
            "files": [] if two_parents else files,
            "commit": {"message": message or title},
        }
        if two_parents:
            self.responses[f"GET {base}/compare/{self.parent(n)}...{merge_sha(n)}"] = {"files": files}

    @staticmethod
    def parent(n: int) -> str:
        return f"{n:039d}e"

    def blame(self, later: int, path: str, ranges: list[tuple[int, int, str]]) -> None:
        key = {"name": "proj", "oid": self.parent(later), "owner": "owner", "path": path}
        self.responses[f"BLAME {json.dumps(key, sort_keys=True)}"] = {"data": {"repository": {"object": {
            "blame": {"ranges": [{"startingLine": a, "endingLine": b, "commit": {"oid": c}} for a, b, c in ranges]}
        }}}}

    def _pull(self, n, at, state, title, body):
        return {
            "number": n,
            "html_url": f"https://github.com/{REPO}/pull/{n}",
            "state": state,
            "base": {"ref": "main"},
            "head": {"sha": head_sha(n)},
            "merged_at": at.isoformat().replace("+00:00", "Z") if at else None,
            "merge_commit_sha": merge_sha(n) if at else None,
            "title": title,
            "body": body,
        }

    def build(self) -> dict:
        base = f"repos/{REPO}"
        return {
            **self.responses,
            f"PAGES {base}/issues/comments?since={SHADOW_START}&per_page=100": [self.comments],
            f"PAGES {base}/pulls?state=all&per_page=100": [self.pulls],
        }


def scenario() -> FakeRepo:
    """PR n is graded; PR n+1 is the later PR that decides its outcome."""
    r = FakeRepo()
    own = [{"filename": "b.py", "status": "modified", "patch": patch(5)}]
    later = [{"filename": "b.py", "status": "modified", "patch": patch(5)}]
    day = timedelta(days=10)
    hour = timedelta(hours=1)

    r.merged(10, T0, own)
    readd = [{"filename": "b.py", "status": "modified", "patch": "@@ -4,0 +5,1 @@\n+old"}]
    r.merged(11, T0 + hour, readd, title="Undo", message=f"Undo\n\nThis reverts commit {merge_sha(10)}.")
    r.merged(20, T0 + day, own, runs=("success", "failure", "cancelled"))
    r.merged(30, T0 + 2 * day, own)
    r.merged(31, T0 + 2 * day + hour, later, title="Fix b parsing")
    r.blame(31, "b.py", [(1, 4, "c" * 40), (5, 5, merge_sha(30))])
    r.merged(40, T0 + 3 * day, own)
    r.merged(41, T0 + 3 * day + hour, later, title="Extend b")
    r.blame(41, "b.py", [(1, 9, merge_sha(40))])
    r.merged(50, AS_OF - timedelta(days=1), own)
    r.unmerged(60, "closed")
    r.unmerged(70, "open")
    r.merged(80, T0 + 4 * day, own, runs=("success",))
    r.merged(81, T0 + 4 * day + hour, [{"filename": "z.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+z"}])
    r.merged(90, T0 + 5 * day, own)
    r.merged(91, T0 + 5 * day + hour, later, title="Fix b", two_parents=True)
    r.blame(91, "b.py", [(5, 5, head_sha(90))])
    r.merged(100, T0 + 6 * day, own)
    r.merged(101, T0 + 6 * day + hour, readd, title="Revert \"Add x\"", body=f"Reverts {REPO}#100")

    r.merged(110, T0 + 7 * day, own)
    r.merged(120, T0 + 8 * day, own)
    # A PR that only deleted a line, reverted with `git revert -m 1` in a merge-commit repo: the
    # revert only adds lines, and only its branch commit says what it reverts.
    r.merged(130, T0 + 9 * day, [{"filename": "b.py", "status": "modified", "patch": "@@ -5,1 +4,0 @@\n-old"}])
    r.merged(131, T0 + 9 * day + hour, readd, title='Revert "Merge pull request #130 from owner/x"', two_parents=True,
             branch_message=f'Revert "Merge pull request #130 from owner/x"\n\nThis reverts commit {merge_sha(130)}, reversing\nchanges.')
    r.merged(140, T0 + 10 * day, own)
    r.merged(141, T0 + 10 * day + hour, later, title="Add x, part 2", body="Follow-up to #140")
    r.blame(141, "b.py", [(5, 5, merge_sha(140))])

    # PR 151 is stacked on 150 and merged without a rebase: GitHub lists 150's branch commits among
    # its own, and its squash message repeats 150's in-branch revert of its own first commit.
    first, second = f"{150:039d}a", head_sha(150)
    in_branch = [{"sha": first, "commit": {"message": "try"}},
                 {"sha": second, "commit": {"message": f'Revert "try"\n\nThis reverts commit {first}.'}}]
    r.merged(150, T0 + 11 * day, own)
    r.responses[f"PAGES repos/{REPO}/pulls/150/commits?per_page=100"] = [in_branch]
    r.merged(151, T0 + 11 * day + hour, readd, title="Add y", message=f"Add y\n\n* This reverts commit {first}.")
    r.responses[f"PAGES repos/{REPO}/pulls/151/commits?per_page=100"] = [
        in_branch + [{"sha": head_sha(151), "commit": {"message": "Add y"}}]
    ]

    for n in (10, 30, 40, 50, 60, 70, 80, 90, 100, 130, 140, 150):
        r.comment(n, comment_body(n))
    r.comment(20, comment_body(20, critical=True, review=None))
    r.comment(110, comment_body(110, review={**GOOD_REVIEW, "verdict": "manual", "confidence": 6}))
    r.comment(120, comment_body(120, review=None))
    r.comment(11, comment_body(10))  # the record names PR 10 on PR 11
    r.comment(31, comment_body(31), author="mallory")
    r.comment(41, comment_body(41).split("<details>")[0])
    r.comment(99, comment_body(99))  # an issue, not a PR
    return r
