"""Install the Bun that claude-code-action runs on, and print its path as a `$GITHUB_OUTPUT` line.

The action's own setup-bun unpacks with the `unzip` program, which lean self-hosted runner images
lack; Python's zipfile needs nothing. Keep the version equal to the pinned action's setup-bun input.
"""

import hashlib
import platform
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.4.4"
# The baseline build runs on any x86-64 CPU. SHA-256 from the release's SHASUMS256.txt.
ASSET = "bun-linux-x64-baseline"
SHA256 = "e0446eb55995772eb9894bebae9a6be368d985a8b9271ee124486f9946eedd76"
URL = f"https://github.com/oven-sh/bun/releases/download/bun-v{VERSION}/{ASSET}.zip"


def install(dest: Path) -> Path:
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise SystemExit(f"merge-gate: Bun install supports Linux x86-64 only, not {sys.platform} {platform.machine()}")
    with urllib.request.urlopen(URL, timeout=120) as resp:
        data = resp.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"merge-gate: {URL} has SHA-256 {digest}, expected {SHA256}")
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / f"{ASSET}.zip"
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as z:
        z.extract(f"{ASSET}/bun", dest)
    bun = dest / ASSET / "bun"
    bun.chmod(0o755)
    return bun


if __name__ == "__main__":
    print(f"path={install(Path(sys.argv[1]))}")
