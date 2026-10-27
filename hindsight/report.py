"""The dataset rows and the summary of a hindsight run."""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from merge_gate.model import ReasonCode

from .history import Pull
from .label import BAD, SETTLED, Label, Outcome
from .record import Shadow, Skipped

# The reasons `merge_gate.verdict._review_reasons` adds from a review it got: the review, not a
# rule, asked for a human. Its other reason, no-review, means the review step failed.
REVIEW_REASONS = frozenset(
    c.value
    for c in (
        ReasonCode.REVIEW_MANUAL,
        ReasonCode.LOW_CONFIDENCE,
        ReasonCode.BLOCKING_FINDING,
        ReasonCode.UNMET_CRITERION,
        ReasonCode.NO_CRITERIA,
    )
)


@dataclass(frozen=True)
class Row:
    shadow: Shadow
    pull: Pull
    outcome: Outcome
    grade_file: str | None = None

    @property
    def manual_kind(self) -> str | None:
        """`rule` when a deterministic check routed the PR to a human, `review` when only the review
        did, `no-review` when only a failed review step did."""
        if self.shadow.verdict != "manual":
            return None
        reasons = set(self.shadow.reasons)
        if reasons == {ReasonCode.NO_REVIEW.value}:
            return "no-review"
        return "review" if reasons <= REVIEW_REASONS else "rule"

    def json(self) -> dict:
        s, p, o = self.shadow, self.pull, self.outcome
        return {
            "repo": s.repo,
            "pr": s.pr,
            "pr_url": p.url,
            "comment_url": s.comment_url,
            "run": s.run,
            "head": s.head,
            "head_is_final": s.head == p.head_sha,
            "verdict": s.verdict,
            "manual_kind": self.manual_kind,
            "review": s.review,
            "confidence": s.confidence,
            "class": s.change_class,
            "reasons": list(s.reasons),
            "state": "merged" if p.merged_at else p.state,
            "merged_at": p.merged_at.isoformat() if p.merged_at else None,
            "merge_sha": p.merge_sha,
            "label": o.label.value,
            "bad": o.label in BAD,
            "settled": o.label in SETTLED,
            "evidence": [{"kind": e.kind, "url": e.url, "detail": e.detail} for e in o.evidence],
            "grade_file": self.grade_file,
        }


def dataset(rows: list[Row]) -> str:
    return "".join(json.dumps(r.json(), sort_keys=True) + "\n" for r in rows)


def _rate(bad: int, settled: int) -> str:
    return f"{bad} of {settled}" + (f" ({100 * bad // settled}%)" if settled else "")


def _table(rows: list[Row], key, title: str) -> list[str]:
    head = [
        f"| {title} | verdicts | would-merge | would-merge then bad | manual | manual then bad | manual then clean | unsettled or unmerged |",
        "|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    body = []
    for name in sorted(groups):
        g = groups[name]
        wm = [r for r in g if r.shadow.verdict == "would-merge"]
        man = [r for r in g if r.shadow.verdict == "manual"]
        body.append(
            f"| {name} | {len(g)} | {len(wm)} | {sum(r.outcome.label in BAD for r in wm)} | {len(man)} | "
            f"{sum(r.outcome.label in BAD for r in man)} | "
            f"{sum(r.outcome.label in SETTLED - BAD for r in man)} | "
            f"{sum(r.outcome.label not in SETTLED for r in g)} |"
        )
    return head + body


def summary(rows: list[Row], skipped: list[Skipped], repos: list[str], as_of: datetime, window_days: int) -> str:
    labels = Counter((r.outcome.label, r.shadow.verdict) for r in rows)
    lines = [
        "# merge-gate hindsight eval",
        "",
        f"As of {as_of.isoformat()}, window {window_days} days, repos: {', '.join(repos)}. "
        f"{len(rows)} verdicts, {len(skipped)} gate-marked comments skipped.",
        "",
        "Bad outcome: reverted, main-red, fixed-soon or model-bad. Settled: bad, clean or model-clean. "
        "`pending`: merged less than the window ago with nothing bad yet. `ambiguous`: a related later PR "
        "that no deterministic rule settles and no model grade decided.",
        "",
        "## Outcomes",
        "",
        "| label | would-merge | manual |",
        "|---|---|---|",
    ]
    lines += [
        f"| {label.value} | {labels[(label, 'would-merge')]} | {labels[(label, 'manual')]} |"
        for label in Label
        if labels[(label, "would-merge")] or labels[(label, "manual")]
    ]
    wm = [r for r in rows if r.shadow.verdict == "would-merge"]
    lines += [
        "",
        "## Would-merge followed by a bad outcome",
        "",
        f"{_rate(sum(r.outcome.label in BAD for r in wm), sum(r.outcome.label in SETTLED for r in wm))} "
        f"settled would-merge verdicts.",
        "",
        "## Manual verdicts",
        "",
        "A manual verdict was needed when the PR still had a bad outcome. A `review` manual verdict (only the "
        "review asked for a human) on a PR that stayed clean is review noise; a `rule` one is the gate's policy; "
        "a `no-review` one means the review step failed.",
        "",
    ]
    for kind in ("review", "rule", "no-review"):
        group = [r for r in rows if r.manual_kind == kind]
        settled = [r for r in group if r.outcome.label in SETTLED]
        lines.append(
            f"- `{kind}`: {len(group)} verdicts; bad outcome in {_rate(sum(r.outcome.label in BAD for r in settled), len(settled))} "
            f"settled; {len(group) - len(settled)} unsettled or unmerged."
        )
    lines += ["", "## Reviewer verdict against outcome", "", *_table(rows, lambda r: str(r.shadow.review), "review")]
    lines += ["", "## By class", "", *_table(rows, lambda r: r.shadow.change_class, "class")]
    lines += ["", "## By confidence", "", *_table(rows, lambda r: f"{r.shadow.confidence:02d}" if r.shadow.confidence is not None else "none", "confidence")]
    stale = sum(r.shadow.head != r.pull.head_sha for r in rows)
    lines += ["", f"{stale} verdicts judged a head that is not the PR's final head."]
    if skipped:
        lines += ["", "## Skipped comments", ""]
        lines += [f"- {reason}: {n}" for reason, n in sorted(Counter(s.reason for s in skipped).items())]
    return "\n".join(lines) + "\n"
