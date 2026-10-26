"""The GitHub REST calls the gate makes, parsed into the model at this boundary."""

import json
import os
import urllib.request

from .model import ChangedFile, FileStatus, PullRequest

# GitHub lists at most this many files of a PR; assess refuses far fewer.
MAX_LISTED_FILES = 3000
COMMENT_AUTHOR = "github-actions[bot]"


class GitHub:
    def __init__(self, repo: str, token: str, api: str = "https://api.github.com"):
        self.repo = repo
        self.token = token
        self.api = api.rstrip("/")

    @classmethod
    def from_env(cls) -> "GitHub":
        return cls(
            os.environ["GITHUB_REPOSITORY"],
            os.environ["GITHUB_TOKEN"],
            os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )

    def _request(self, method: str, path: str, body: dict | None = None, accept: str = "application/vnd.github+json") -> bytes:
        req = urllib.request.Request(
            f"{self.api}/repos/{self.repo}{path}",
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def _get(self, path: str):
        return json.loads(self._request("GET", path))

    def _pages(self, path: str, limit: int):
        sep = "&" if "?" in path else "?"
        items = []
        page = 1
        while len(items) < limit:
            batch = self._get(f"{path}{sep}per_page=100&page={page}")
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items

    def open_same_repo_pr(self, head_sha: str) -> PullRequest | None:
        """The open PR whose head is this commit in this repository; forks are never found."""
        for raw in self._get(f"/commits/{head_sha}/pulls"):
            head = raw["head"]
            if (
                raw["state"] == "open"
                and head["sha"] == head_sha
                and head["repo"] is not None
                and head["repo"]["full_name"] == self.repo
            ):
                return PullRequest(
                    number=raw["number"],
                    author=raw["user"]["login"],
                    head_ref=head["ref"],
                    head_sha=head["sha"],
                    draft=bool(raw["draft"]),
                    title=raw["title"],
                )
        return None

    def pr_body(self, number: int) -> str:
        return self._get(f"/pulls/{number}")["body"] or ""

    def changed_files(self, number: int) -> list[ChangedFile]:
        return [
            ChangedFile(
                path=f["filename"],
                previous_path=f.get("previous_filename"),
                status=FileStatus(f["status"]),
                additions=f["additions"],
                deletions=f["deletions"],
                patch=f.get("patch"),
            )
            for f in self._pages(f"/pulls/{number}/files", MAX_LISTED_FILES)
        ]

    def diff(self, number: int) -> str:
        return self._request("GET", f"/pulls/{number}", accept="application/vnd.github.diff").decode(
            "utf-8", "replace"
        )

    def upsert_comment(self, number: int, marker: str, body: str) -> None:
        for c in self._pages(f"/issues/{number}/comments", 10_000):
            if c["user"]["login"] == COMMENT_AUTHOR and c["body"].startswith(marker):
                self._request("PATCH", f"/issues/comments/{c['id']}", {"body": body})
                return
        self._request("POST", f"/issues/{number}/comments", {"body": body})
