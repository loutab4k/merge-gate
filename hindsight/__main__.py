"""Grade every shadow verdict merge-gate posted by what happened to its PR afterwards.

Read-only: it only reads GitHub through `gh api`. Run from the repository root:
    python3 -m hindsight [--repo OWNER/NAME ...] [--no-model] [--out DIR]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .gh import Gh, GhError
from .grade import Grader, run_claude
from .history import History, Pull
from .label import Label, graded, label, unmerged
from .record import Shadow, Skipped, is_gate_comment, parse_comment
from .report import Row, dataset, summary

# The repositories with a caller workflow for the gate: this one (.github/workflows/merge-gate.yml)
# and the two pilots (README, "Set up a project"). A new caller is added here.
REPOS = ("loutab4k/merge-gate", "loutab4k/dotfiles", "Proxi-Labs/vinipuch")
# merge-gate's first shadow comment (merge-gate#1): no gate comment is older, so earlier ones are not read.
SHADOW_START = "2026-10-26T00:00:00Z"
# Measured 2026-10-28: of 28 later PRs in dotfiles and vinipuch that name an earlier PR and say
# fix, revert or regression, 27 merged within one day of it and all 28 within three.
WINDOW_DAYS = 3


def collect(gh: Gh, repo: str) -> tuple[list[Shadow], list[Skipped], dict[int, Pull]]:
    comments = gh.pages(f"repos/{repo}/issues/comments?since={SHADOW_START}&per_page=100")
    parsed = [parse_comment(repo, c) for c in comments if is_gate_comment(c)]
    pulls = {p["number"]: Pull.parse(p) for p in gh.pages(f"repos/{repo}/pulls?state=all&per_page=100")}
    shadows, skipped = [], [p for p in parsed if isinstance(p, Skipped)]
    for p in parsed:
        if isinstance(p, Shadow):
            if p.pr in pulls:
                shadows.append(p)
            else:
                skipped.append(Skipped(repo, p.comment_url, "not a pull request"))
    return shadows, skipped, pulls


def evaluate(gh: Gh, repos: list[str], as_of: datetime, window_days: int, grader: Grader | None):
    rows, skipped = [], []
    for repo in repos:
        shadows, skips, pulls = collect(gh, repo)
        skipped += skips
        history = History(gh, repo, pulls, timedelta(days=window_days), as_of)
        for s in sorted(shadows, key=lambda s: s.pr):
            pull = pulls[s.pr]
            if pull.merged_at is None:
                rows.append(Row(s, pull, unmerged(pull)))
                continue
            facts = history.facts(pull)
            outcome = label(facts, as_of)
            grade, path = None, None
            if outcome.label is Label.AMBIGUOUS and grader is not None:
                grade, path = grader.grade(repo, facts)
                if grade is not None:
                    outcome = graded(outcome, grade, facts)
            rows.append(Row(s, pull, outcome, f"grades/{path.name}" if path else None, grade and grade.confidence))
    return rows, skipped


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def main(argv: list[str] | None = None, gh: Gh | None = None, run_model=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hindsight", description=__doc__.split("\n")[0])
    ap.add_argument("--repo", action="append", help=f"repeatable; default: {', '.join(REPOS)}")
    ap.add_argument("--out", type=Path, default=Path("hindsight-out"))
    ap.add_argument("--as-of", type=datetime.fromisoformat, help="ISO time with offset; default now")
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--no-model", action="store_true", help="leave ambiguous cases ungraded")
    ap.add_argument("--model", default="opus", help="claude -p model for ambiguous cases")
    ap.add_argument("--record", type=Path, help="also save every GitHub response here, for test fixtures")
    args = ap.parse_args(argv)
    if args.as_of is not None and args.as_of.tzinfo is None:
        ap.error("--as-of needs a UTC offset, such as 2026-10-28T00:00:00+00:00")
    as_of = args.as_of or datetime.now(timezone.utc).replace(microsecond=0)
    repos = args.repo or list(REPOS)
    recording = {} if args.record else None
    gh = gh or Gh(recording)
    args.out.mkdir(parents=True, exist_ok=True)
    grader = None if args.no_model else Grader(args.out / "grades", run_model or run_claude(args.model))
    try:
        rows, skipped = evaluate(gh, repos, as_of, args.window_days, grader)
    except GhError as e:
        print(f"hindsight: {e}", file=sys.stderr)
        return 1
    _write(args.out / "dataset.jsonl", dataset(rows))
    _write(args.out / "summary.md", summary(rows, skipped, repos, as_of, args.window_days))
    if recording is not None:
        _write(args.record, json.dumps(recording, indent=1, sort_keys=True) + "\n")
    print(f"{len(rows)} verdicts, {len(skipped)} skipped -> {args.out}/dataset.jsonl, {args.out}/summary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
