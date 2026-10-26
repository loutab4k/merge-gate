"""The project's `.github/merge-gate.json`, read from the default branch and validated once here."""

import json
from dataclasses import dataclass
from pathlib import Path

from .globs import Glob, compile_glob

# Paths that steer CI, the gate or the agents; a project can add to them, never remove them.
BUILTIN_CRITICAL = (
    ".github/**",
    "**/CLAUDE.md",
    "**/CLAUDE.local.md",
    "**/AGENTS.md",
    ".claude/**",
    "**/.claude/**",
    ".mcp.json",
)

DEFAULTS = {
    "agent_branch_prefixes": ["ai/"],
    "bots": ["dependabot[bot]", "renovate[bot]"],
    "critical_paths": [],
    "test_paths": [
        "**/*_test.go",
        "**/test_*.py",
        "**/*_test.py",
        "**/*.test.*",
        "**/*.spec.*",
        "**/tests/**",
        "**/__tests__/**",
        "**/testdata/**",
        "**/conftest.py",
    ],
    "docs_paths": ["**/*.md", "docs/**"],
    "dependency_files": [
        "**/go.mod",
        "**/go.sum",
        "**/package.json",
        "**/package-lock.json",
        "**/pnpm-lock.yaml",
        "**/yarn.lock",
        "**/requirements*.txt",
        "**/poetry.lock",
        "**/uv.lock",
        "**/pyproject.toml",
        "**/Cargo.toml",
        "**/Cargo.lock",
    ],
    "max_changed_lines": 800,
}

REQUIRED = ("version", "mode", "owner")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    owner: str
    agent_branch_prefixes: tuple[str, ...]
    bots: frozenset[str]
    critical: tuple[Glob, ...]
    tests: tuple[Glob, ...]
    docs: tuple[Glob, ...]
    dependency_files: tuple[Glob, ...]
    max_changed_lines: int


def _string_list(raw: dict, key: str) -> list[str]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    return value


def parse_config(text: str) -> Config:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError("top level must be an object")
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise ConfigError(f"missing keys: {', '.join(missing)}")
    unknown = sorted(set(raw) - set(REQUIRED) - set(DEFAULTS))
    if unknown:
        raise ConfigError(f"unknown keys: {', '.join(unknown)}")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ConfigError("version must be 1")
    if raw["mode"] != "shadow":
        raise ConfigError('mode must be "shadow" (this gate never merges yet)')
    if not isinstance(raw["owner"], str) or not raw["owner"]:
        raise ConfigError("owner must be a GitHub login")
    merged = {**DEFAULTS, **raw}
    prefixes = tuple(_string_list(merged, "agent_branch_prefixes"))
    if not prefixes:
        raise ConfigError("agent_branch_prefixes must name at least one prefix")
    limit = merged["max_changed_lines"]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ConfigError("max_changed_lines must be a positive integer")

    def globs(key: str, extra: tuple[str, ...] = (), ignore_case: bool = False) -> tuple[Glob, ...]:
        try:
            return tuple(compile_glob(p, ignore_case) for p in (*extra, *_string_list(merged, key)))
        except ValueError as e:
            raise ConfigError(f"{key}: {e}") from e

    return Config(
        owner=raw["owner"],
        agent_branch_prefixes=prefixes,
        bots=frozenset(_string_list(merged, "bots")),
        critical=globs("critical_paths", BUILTIN_CRITICAL, ignore_case=True),
        tests=globs("test_paths"),
        docs=globs("docs_paths"),
        dependency_files=globs("dependency_files"),
        max_changed_lines=limit,
    )


def load_config(path: Path) -> Config:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise ConfigError(f"{path} not found on the base branch") from e
    return parse_config(text)
