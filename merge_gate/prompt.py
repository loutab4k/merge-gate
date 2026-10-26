"""Print the reviewer prompt and the verdict schema as `$GITHUB_OUTPUT` lines."""

import json
import secrets
from pathlib import Path

from .verdict import REVIEW_SCHEMA


def main() -> None:
    prompt = (Path(__file__).parent.parent / "prompts" / "review.md").read_text(encoding="utf-8")
    delimiter = f"EOF_{secrets.token_hex(16)}"
    print(f"prompt<<{delimiter}\n{prompt}\n{delimiter}")
    print(f"schema={json.dumps(REVIEW_SCHEMA, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
