"""Break each safety check in turn, in a copy of the repository, and require the test suite to fail.

Run with the Python that has requirements-dev.txt: `.venv/bin/python scripts/mutation-check.py`.
A mutant whose text no longer appears exactly once fails too: update it with the code it guards.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
MUTANTS = [
    ("merge_gate/assess.py", "(ReasonCode.CRITICAL_PATH, config.critical)", "(ReasonCode.CRITICAL_PATH, ())"),
    ("merge_gate/assess.py", "return pr.author == config.owner and", "return True or"),
    ("merge_gate/assess.py", "if changed_lines > config.max_changed_lines", "if changed_lines >= config.max_changed_lines"),
    ("merge_gate/assess.py", 'patch.split("\\n")', "patch.splitlines()"),
    ("merge_gate/assess.py", "if not ci_green:", "if False:"),
    ("merge_gate/assess.py", "if f.status is FileStatus.REMOVED or", "if False and"),
    ("merge_gate/verdict.py", "MIN_CONFIDENCE = 8", "MIN_CONFIDENCE = 0"),
    ("merge_gate/verdict.py", 'or set(value) != set(schema["required"])', ""),
    ("merge_gate/verdict.py", "assessment.reasons + _review_reasons(", "(*_review_reasons("),
    ("merge_gate/verdict.py", "if not assessment.needs_review:", "if False:"),
    ("merge_gate/model.py", "return all(r.code in REVIEWED_ANYWAY", "return any(r.code in REVIEWED_ANYWAY"),
    ("merge_gate/model.py", "frozenset({ReasonCode.CRITICAL_PATH})", "frozenset(ReasonCode)"),
    ("merge_gate/config.py", "if not prefixes:", "if False:"),
    ("merge_gate/assess.py", "((ReasonCode.AGENT_CONFIG, config.agent_config), ", "("),
    ("merge_gate/config.py", "compile_glob(p, ignore_case=True) for p in AGENT_CONFIG", "compile_glob(p) for p in AGENT_CONFIG"),
    ("merge_gate/config.py", '    "**/.claude/**",\n', ""),
    ("merge_gate/config.py", '    "**/.claude",\n', ""),
    ("merge_gate/verdict.py", '"merge" if verdict.review.merge else "manual"', '"merge"'),
    ("merge_gate/assess.py", "startswith(config.agent_branch_prefixes)", "startswith(config.agent_branch_prefixes[0])"),
    ("merge_gate/verdict.py", 'if not review.criteria and not deps:', "if False:"),
    ("merge_gate/verdict.py", 'return f"`{text}`" if text else "(empty)"', "return text"),
    ("merge_gate/verdict.py", "ok = isinstance(v, list) and all(", "ok = all("),
    ("merge_gate/verdict.py", 'ok = type(v) is int and spec["minimum"] <= v', 'ok = isinstance(v, int) and spec["minimum"] <= v'),
    ("merge_gate/github.py", 'c["user"]["login"] == COMMENT_AUTHOR and ', ""),
    ("merge_gate/github.py", 'and head["repo"]["full_name"] == self.repo', ""),
    ("merge_gate/config.py", 'if raw["mode"] != "shadow":', "if False:"),
    ("merge_gate/config.py", 'globs("critical_paths", BUILTIN_CRITICAL, ignore_case=True)', 'globs("critical_paths", (), ignore_case=True)'),
    ("merge_gate/config.py", 'BUILTIN_CRITICAL, ignore_case=True)', 'BUILTIN_CRITICAL, ignore_case=False)'),
    ("merge_gate/config.py", 'type(raw["version"]) is not int or ', ""),
    ("merge_gate/globs.py", 'if pattern.startswith(("/", "!", "./"))', 'if False and pattern.startswith(("/", "!", "./"))'),
    ("merge_gate/assess.py", "MAX_DIFF_FILES = 300", "MAX_DIFF_FILES = 3000"),
    ("merge_gate/assess.py", "(f.status is FileStatus.RENAMED and was_test)", "(f.status is FileStatus.RENAMED and not first_match(config.tests, f.path))"),
    ("merge_gate/assess.py", 'r"v?([0-9]{1,9})\\.([0-9]{1,9})\\.([0-9]{1,9})"', 'r"v?(\\d{1,9})\\.(\\d{1,9})\\.(\\d{1,9})"'),
    ("merge_gate/assess.py", 'r"(?<![\\w.$])" + ', ""),
    ("merge_gate/assess.py", '"pytest.importorskip(",', ""),
    ("merge_gate/__main__.py", '("pull_request", "push")', '("pull_request",)'),
    ("merge_gate/bun.py", "if digest != SHA256:", "if False:"),
    ("merge_gate/globs.py", '("/", "!", "./")', '("/", "!")'),
    ("merge_gate/assess.py", '    "//go:build",\n', ""),
    ("merge_gate/assess.py", '"fdescribe(", "skip(")', '"fdescribe(")'),
    ("merge_gate/verdict.py", "except (ValueError, RecursionError):", "except json.JSONDecodeError:"),
    ("merge_gate/failure.py", 'c if c.isprintable() else " "', "c"),
    ("merge_gate/failure.py", "[:LIMIT]", ""),
    ("merge_gate/failure.py", 'if is_error or subtype != "success":', "if True:"),
    ("merge_gate/failure.py", "results[-1]", "results[0]"),
    ("merge_gate/failure.py", 'm.get("type") == "result"', "True"),
    ("merge_gate/verdict.py", 'review_error or "no valid review output"', '"no valid review output"'),
    ("merge_gate/__main__.py", 'os.environ.get("REVIEW_FAILURE", "")', '""'),
    ("merge_gate/verdict.py", "{_neutral(r.detail, 300)}", "{r.detail}"),
]

failed = 0
for rel, old, new in MUTANTS:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(SRC, work, ignore=shutil.ignore_patterns(".git", ".venv", ".hypothesis", "__pycache__", ".pytest_cache"))
        target = work / rel
        text = target.read_text()
        if text.count(old) != 1:
            print(f"BAD MUTANT (pattern count {text.count(old)}): {rel}: {old}")
            failed += 1
            continue
        target.write_text(text.replace(old, new))
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True,
        )
        caught = r.returncode != 0
        print(f"{'caught ' if caught else 'SURVIVED'} {rel}: {old[:60]}")
        failed += not caught
sys.exit(1 if failed else 0)
