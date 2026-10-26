"""Path globs from trusted config: `**` spans directories, `*` and `?` stay inside one segment.

Every other character is literal, so a path can match only what the config spelled out.
Critical paths match ignoring case: a case-insensitive checkout (macOS) loads `claude.md` as `CLAUDE.md`.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Glob:
    pattern: str
    regex: re.Pattern[str]

    def matches(self, path: str) -> bool:
        return self.regex.fullmatch(path) is not None


def compile_glob(pattern: str, ignore_case: bool = False) -> Glob:
    """Refuses patterns written for other glob dialects, which would silently never match."""
    if pattern.startswith(("/", "!")) or pattern.endswith("/") or any(c in pattern for c in "{}[]"):
        raise ValueError(
            f"{pattern!r}: write a path relative to the repository root, without a leading or "
            "trailing /, !, {} or []; a directory is dir/**"
        )
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:[^/]*/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    flags = re.DOTALL | (re.IGNORECASE if ignore_case else 0)
    return Glob(pattern, re.compile("".join(out), flags))


def first_match(globs: tuple[Glob, ...], path: str) -> Glob | None:
    return next((g for g in globs if g.matches(path)), None)
