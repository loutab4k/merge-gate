"""The outcome label of one verdict, decided from the facts alone; only `ambiguous` may go to a model."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .history import RED, Facts, Later, Pull


class Label(Enum):
    REVERTED = "reverted"
    MAIN_RED = "main-red"
    FIXED_SOON = "fixed-soon"
    MODEL_BAD = "model-bad"
    PENDING = "pending"
    AMBIGUOUS = "ambiguous"
    MODEL_CLEAN = "model-clean"
    CLEAN = "clean"
    CLOSED_UNMERGED = "closed-unmerged"
    OPEN = "open"


BAD = frozenset({Label.REVERTED, Label.MAIN_RED, Label.FIXED_SOON, Label.MODEL_BAD})
SETTLED = BAD | {Label.CLEAN, Label.MODEL_CLEAN}


@dataclass(frozen=True)
class Evidence:
    kind: str
    url: str
    detail: str = ""


@dataclass(frozen=True)
class Outcome:
    label: Label
    evidence: tuple[Evidence, ...] = ()


def unmerged(pull: Pull) -> Outcome:
    return Outcome(Label.OPEN if pull.state == "open" else Label.CLOSED_UNMERGED)


def label(facts: Facts, as_of: datetime) -> Outcome:
    """Bad outcomes stand as soon as they appear; anything else waits for the window to close."""
    reverted = [Evidence("reverted-by", l.pull.url) for l in facts.later if l.reverts]
    if reverted:
        return Outcome(Label.REVERTED, tuple(reverted))
    red = [Evidence("red-run", r.url, f"{r.name}: {r.conclusion}") for r in facts.push_runs if r.conclusion in RED]
    if red:
        return Outcome(Label.MAIN_RED, tuple(red))
    fixed = [
        Evidence("fixed-its-lines", l.pull.url, ", ".join(l.overlap_files))
        for l in facts.later
        if l.overlap_files and (l.names_pr or l.fix_title)
    ]
    if fixed:
        return Outcome(Label.FIXED_SOON, tuple(fixed))
    related = tuple(Evidence("related-later-pr", l.pull.url, _relation(l)) for l in facts.later)
    if as_of < facts.window_end:
        return Outcome(Label.PENDING, related)
    return Outcome(Label.AMBIGUOUS, related) if related else Outcome(Label.CLEAN)


def _relation(later: Later) -> str:
    parts = ["names the PR"] if later.names_pr else []
    if later.overlap_files:
        parts.append(f"changed its lines: {', '.join(later.overlap_files)}")
    parts.append(f"same files: {', '.join(later.shared_files) or 'none'}")
    return "; ".join(parts)
