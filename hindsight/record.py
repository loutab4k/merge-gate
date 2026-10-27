"""A shadow verdict, read back from the PR comment the gate posted (`merge_gate.verdict.record`)."""

import json
import re
from dataclasses import dataclass

from merge_gate.github import COMMENT_AUTHOR
from merge_gate.verdict import MARKER

VERDICTS = ("would-merge", "manual")
REVIEWS = (None, "merge", "manual")
SHA = re.compile(r"[0-9a-f]{40}")
ISSUE_URL = re.compile(r"https://api\.github\.com/repos/[^/]+/[^/]+/issues/([1-9][0-9]*)")
RECORD_BLOCK = "<details><summary>record</summary>\n\n```json\n"


@dataclass(frozen=True)
class Shadow:
    repo: str
    pr: int
    head: str
    verdict: str
    review: str | None
    confidence: int | None
    reasons: tuple[str, ...]
    change_class: str
    comment_url: str
    run: str


@dataclass(frozen=True)
class Skipped:
    repo: str
    comment_url: str
    reason: str


def is_gate_comment(comment: dict) -> bool:
    return comment["body"].startswith(MARKER)


def parse_comment(repo: str, comment: dict) -> Shadow | Skipped:
    """A gate comment becomes a Shadow only when the gate itself wrote it and its record is whole:
    anyone who can comment can paste the marker, so author and PR number are checked too."""
    url = comment["html_url"]
    if comment["user"]["login"] != COMMENT_AUTHOR:
        return Skipped(repo, url, "not written by the gate")
    issue = ISSUE_URL.fullmatch(comment["issue_url"])
    body = comment["body"]
    if RECORD_BLOCK not in body:
        return Skipped(repo, url, "no record block")
    raw = body.rsplit(RECORD_BLOCK, 1)[1].split("\n```", 1)[0]
    try:
        rec = json.loads(raw)
    except (ValueError, RecursionError):
        return Skipped(repo, url, "record is not JSON")
    if not isinstance(rec, dict) or not _valid(rec):
        return Skipped(repo, url, "record does not fit version 1")
    if issue is None or int(issue[1]) != rec["pr"]:
        return Skipped(repo, url, "record names another PR")
    return Shadow(
        repo=repo,
        pr=rec["pr"],
        head=rec["head"],
        verdict=rec["verdict"],
        review=rec.get("review"),
        confidence=rec.get("confidence"),
        reasons=tuple(rec["reasons"]),
        change_class=rec["class"],
        comment_url=url,
        run=rec["run"],
    )


def _valid(rec: dict) -> bool:
    # `review` arrived with merge-gate#3; earlier records lack it.
    confidence = rec.get("confidence")
    return (
        rec.get("version") == 1
        and type(rec.get("pr")) is int
        and isinstance(rec.get("head"), str)
        and SHA.fullmatch(rec["head"]) is not None
        and rec.get("verdict") in VERDICTS
        and rec.get("review") in REVIEWS
        and (confidence is None or (type(confidence) is int and 0 <= confidence <= 10))
        and isinstance(rec.get("reasons"), list)
        and all(isinstance(r, str) for r in rec["reasons"])
        and isinstance(rec.get("class"), str)
        and isinstance(rec.get("run"), str)
    )
