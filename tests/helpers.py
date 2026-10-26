import json

from merge_gate.config import parse_config
from merge_gate.model import ChangedFile, FileStatus, PullRequest

CONFIG = parse_config(json.dumps({"version": 1, "mode": "shadow", "owner": "owner", "critical_paths": ["billing/**"]}))


def pr(author="owner", head_ref="ai/feature", draft=False, title="Add a feature", sha="a" * 40):
    return PullRequest(number=7, author=author, head_ref=head_ref, head_sha=sha, draft=draft, title=title)


def changed(path, status=FileStatus.MODIFIED, patch="@@ -1 +1 @@\n-old\n+new", additions=1, deletions=1, previous_path=None):
    return ChangedFile(path, previous_path, status, additions, deletions, patch)
