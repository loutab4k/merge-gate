"""Say why the review step failed, from claude-code-action's execution file.

The action logs only a sanitized result (subtype, is_error, cost), so a failed review would show no
cause. The file holds every message, the prompt and the diff included; this reads only the final
result message. Its text comes from the model or the API and may echo PR content, so the reason is
one printable line, which cannot add a `$GITHUB_OUTPUT` key, logged with workflow commands stopped.
"""

import json
import os
import secrets
import sys
from pathlib import Path

from .verdict import REASON_LIMIT


def _line(text: str) -> str:
    return " ".join("".join(c if c.isprintable() else " " for c in text).split())


def failure_reason(messages) -> str:
    """The final result's subtype, is_error and error text; no model text when it reported no error."""
    if not isinstance(messages, list):
        return "no result message"
    results = [m for m in messages if isinstance(m, dict) and m.get("type") == "result"]
    if not results:
        return "no result message"
    result = results[-1]
    subtype = result.get("subtype") if isinstance(result.get("subtype"), str) else "unknown"
    is_error = result.get("is_error") is True
    reason = f"subtype {subtype}, is_error {'true' if is_error else 'false'}"
    if is_error or subtype != "success":
        errors = result.get("errors")
        if isinstance(result.get("result"), str):
            reason += f": {result['result']}"
        elif isinstance(errors, list):
            reason += ": " + "; ".join(e for e in errors if isinstance(e, str))
    else:
        reason += ": no structured output"
    return _line(reason)[:REASON_LIMIT].rstrip()


def reason_from_file(path: str) -> str:
    if not path:
        return "no execution file"
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "execution file unreadable"
    try:
        messages = json.loads(text)
    except (ValueError, RecursionError):
        return "execution file is not JSON"
    return failure_reason(messages)


def main(argv: list[str]) -> int:
    reason = reason_from_file(argv[1] if len(argv) > 1 else "")
    # The runner also runs legacy `##[command]` text found anywhere in a line, so the reason is
    # printed with workflow commands stopped; the random token cannot appear in it.
    token = secrets.token_hex(16)
    print(f"::stop-commands::{token}\nmerge-gate: review failed: {reason}\n::{token}::")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"reason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
