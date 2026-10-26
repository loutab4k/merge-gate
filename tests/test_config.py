import json

import pytest

from merge_gate.config import ConfigError, parse_config

BASE = {"version": 1, "mode": "shadow", "owner": "owner"}


def test_minimal_config_gets_defaults_and_builtin_critical_paths():
    c = parse_config(json.dumps(BASE))
    assert c.agent_branch_prefixes == ("ai/",) and "dependabot[bot]" in c.bots
    assert any(g.pattern == ".github/**" for g in c.critical)


def test_project_paths_add_to_builtins():
    c = parse_config(json.dumps({**BASE, "critical_paths": ["db/migrations/**"]}))
    patterns = [g.pattern for g in c.critical]
    assert ".github/**" in patterns and "db/migrations/**" in patterns


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        json.dumps({"version": 1, "mode": "shadow"}),
        json.dumps({**BASE, "version": 2}),
        json.dumps({**BASE, "version": True}),
        json.dumps({**BASE, "version": 1.0}),
        json.dumps({**BASE, "critical_paths": ["/billing/**"]}),
        json.dumps({**BASE, "critical_paths": ["billing/"]}),
        json.dumps({**BASE, "critical_paths": ["**/*.{sql,go}"]}),
        json.dumps({**BASE, "test_paths": ["!vendor/**"]}),
        json.dumps({**BASE, "mode": "on"}),
        json.dumps({**BASE, "owner": ""}),
        json.dumps({**BASE, "typo_paths": []}),
        json.dumps({**BASE, "critical_paths": "billing/**"}),
        json.dumps({**BASE, "critical_paths": [""]}),
        json.dumps({**BASE, "max_changed_lines": 0}),
        json.dumps({**BASE, "max_changed_lines": True}),
        json.dumps({**BASE, "agent_branch_prefix": "ai/"}),
        json.dumps({**BASE, "agent_branch_prefixes": []}),
        json.dumps({**BASE, "agent_branch_prefixes": [""]}),
        json.dumps({**BASE, "agent_branch_prefixes": "ai/"}),
    ],
)
def test_invalid_configs_are_refused(raw):
    with pytest.raises(ConfigError):
        parse_config(raw)
