"""Read-only GitHub access through the `gh` CLI: the one place the eval touches the network.

Each response is keyed by its request, so a run can be recorded to a JSON file and replayed offline.
"""

import json
import subprocess

# Commit.blame is GraphQL-only; REST has no blame endpoint.
BLAME_QUERY = """
query($owner: String!, $name: String!, $oid: GitObjectID!, $path: String!) {
  repository(owner: $owner, name: $name) {
    object(oid: $oid) {
      ... on Commit { blame(path: $path) { ranges { startingLine endingLine commit { oid } } } }
    }
  }
}
"""


class GhError(RuntimeError):
    pass


class Gh:
    def __init__(self, recording: dict | None = None):
        self.recording = recording

    def get(self, path: str):
        return self._fetch(f"GET {path}", ["api", path])

    def pages(self, path: str) -> list:
        """Every item of a paginated JSON array."""
        pages = self._fetch(f"PAGES {path}", ["api", "--paginate", "--slurp", path])
        return [item for page in pages for item in page]

    def blame(self, repo: str, oid: str, path: str) -> list[tuple[int, int, str]]:
        """(first line, last line, commit) ranges of `path` at commit `oid`."""
        owner, name = repo.split("/")
        variables = {"owner": owner, "name": name, "oid": oid, "path": path}
        args = ["api", "graphql", "-f", f"query={BLAME_QUERY}"]
        for k, v in variables.items():
            args += ["-f", f"{k}={v}"]
        data = self._fetch(f"BLAME {json.dumps(variables, sort_keys=True)}", args)
        obj = data["data"]["repository"]["object"]
        if obj is None:
            raise GhError(f"no commit {oid} in {repo}")
        return [(r["startingLine"], r["endingLine"], r["commit"]["oid"]) for r in obj["blame"]["ranges"]]

    def _fetch(self, key: str, args: list[str]):
        # GET is gh's default for `gh api` without fields; the GraphQL call is a query, never a mutation.
        try:
            proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            raise GhError(f"gh {key} timed out") from None
        if proc.returncode != 0:
            raise GhError(f"gh {key} failed: {proc.stderr.strip()}")
        value = json.loads(proc.stdout)
        if self.recording is not None:
            self.recording[key] = value
        return value


class Replay(Gh):
    """Answers from a recording; any request it does not hold fails, so tests never reach the network."""

    def __init__(self, responses: dict):
        super().__init__()
        self.responses = responses

    def _fetch(self, key: str, args: list[str]):
        if key not in self.responses:
            raise GhError(f"not recorded: {key}")
        return self.responses[key]
