"""The reviewer's structured output, the final verdict, and the PR comment that shows it."""

import json
from dataclasses import dataclass

from .model import Assessment, ChangeClass, Reason, ReasonCode

MARKER = "<!-- merge-gate:v1 -->"
MIN_CONFIDENCE = 8
BLOCKING = frozenset({"blocker", "major"})
SEVERITIES = ("blocker", "major", "minor", "nit")

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "confidence", "summary", "criteria", "findings"],
    "properties": {
        "verdict": {"enum": ["merge", "manual"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 10},
        "summary": {"type": "string"},
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "met", "evidence"],
                "properties": {
                    "criterion": {"type": "string"},
                    "met": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "file", "summary"],
                "properties": {
                    "severity": {"enum": list(SEVERITIES)},
                    "file": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
    },
}


@dataclass(frozen=True)
class Criterion:
    text: str
    met: bool
    evidence: str


@dataclass(frozen=True)
class Finding:
    severity: str
    file: str
    summary: str


@dataclass(frozen=True)
class Review:
    merge: bool
    confidence: int
    summary: str
    criteria: tuple[Criterion, ...]
    findings: tuple[Finding, ...]


def _object(value, schema: dict) -> bool:
    """`value` is a JSON object with exactly the schema's keys, each of its declared type or enum."""
    if not isinstance(value, dict) or set(value) != set(schema["required"]):
        return False
    for key, spec in schema["properties"].items():
        v = value[key]
        if "enum" in spec:
            ok = isinstance(v, str) and v in spec["enum"]
        elif spec["type"] == "string":
            ok = isinstance(v, str)
        elif spec["type"] == "boolean":
            ok = isinstance(v, bool)
        elif spec["type"] == "integer":
            ok = type(v) is int and spec["minimum"] <= v <= spec["maximum"]
        else:
            ok = isinstance(v, list) and all(_object(item, spec["items"]) for item in v)
        if not ok:
            return False
    return True


def parse_review(text: str) -> Review | None:
    """Anything that does not fit the schema exactly counts as no review."""
    try:
        raw = json.loads(text)
    except (ValueError, RecursionError):  # JSONDecodeError, an over-long integer, deep nesting
        return None
    if not _object(raw, REVIEW_SCHEMA):
        return None
    return Review(
        merge=raw["verdict"] == "merge",
        confidence=raw["confidence"],
        summary=raw["summary"],
        criteria=tuple(Criterion(c["criterion"], c["met"], c["evidence"]) for c in raw["criteria"]),
        findings=tuple(Finding(f["severity"], f["file"], f["summary"]) for f in raw["findings"]),
    )


@dataclass(frozen=True)
class Verdict:
    assessment: Assessment
    review: Review | None
    reasons: tuple[Reason, ...]

    @property
    def would_merge(self) -> bool:
        return not self.reasons


def decide(assessment: Assessment, review: Review | None) -> Verdict:
    if assessment.reasons:
        return Verdict(assessment, review, assessment.reasons)
    if review is None:
        return Verdict(assessment, None, (Reason(ReasonCode.NO_REVIEW, "no valid review output"),))
    reasons = []
    if not review.merge:
        reasons.append(Reason(ReasonCode.REVIEW_MANUAL, "the reviewer asked for a human"))
    if review.confidence < MIN_CONFIDENCE:
        reasons.append(
            Reason(ReasonCode.LOW_CONFIDENCE, f"confidence {review.confidence} < {MIN_CONFIDENCE}")
        )
    reasons += [
        Reason(ReasonCode.BLOCKING_FINDING, f"{f.severity}: {f.file}")
        for f in review.findings
        if f.severity in BLOCKING
    ]
    reasons += [Reason(ReasonCode.UNMET_CRITERION, c.text) for c in review.criteria if not c.met]
    deps = assessment.change_class in (ChangeClass.DEPS_PATCH, ChangeClass.DEPS_OTHER)
    if not review.criteria and not deps:
        reasons.append(Reason(ReasonCode.NO_CRITERIA, "no acceptance criteria in the PR"))
    return Verdict(assessment, review, tuple(reasons))


def _neutral(text: str, limit: int = 600) -> str:
    """Model and PR text as one inline code span: GitHub renders no link, image, HTML, mention or
    reference inside it, so injected text can neither ping anyone nor load a URL that leaks data."""
    text = " ".join(text.split())[:limit].replace("`", "'")
    return f"`{text}`" if text else "(empty)"


def record(verdict: Verdict, run_url: str) -> dict:
    a = verdict.assessment
    return {
        "version": 1,
        "mode": "shadow",
        "pr": a.pr.number,
        "head": a.pr.head_sha,
        "author": a.pr.author,
        "class": a.change_class.value,
        "changed_lines": a.changed_lines,
        "verdict": "would-merge" if verdict.would_merge else "manual",
        "reasons": [r.code.value for r in verdict.reasons],
        "confidence": verdict.review.confidence if verdict.review else None,
        "run": run_url,
    }


def render_comment(verdict: Verdict, run_url: str) -> str:
    a = verdict.assessment
    title = "would merge" if verdict.would_merge else "needs a human"
    lines = [
        MARKER,
        f"### merge-gate (shadow): {title}",
        "",
        f"Head `{a.pr.head_sha[:12]}` · class `{a.change_class.value}` · "
        f"{a.changed_lines} changed lines · shadow mode, nothing is merged · [run]({run_url})",
    ]
    if verdict.reasons:
        lines += ["", "**Why a human:**"]
        lines += [f"- `{r.code.value}`: {_neutral(r.detail, 200)}" for r in verdict.reasons]
    if verdict.review is not None:
        r = verdict.review
        lines += ["", f"**Review** (confidence {r.confidence}/10): {_neutral(r.summary)}"]
        lines += [
            f"- {'met' if c.met else 'NOT met'}: {_neutral(c.text, 200)} ({_neutral(c.evidence, 200)})"
            for c in r.criteria
        ]
        lines += [f"- {f.severity} {_neutral(f.file, 120)}: {_neutral(f.summary, 300)}" for f in r.findings]
    lines += [
        "",
        "<details><summary>record</summary>",
        "",
        "```json",
        json.dumps(record(verdict, run_url), sort_keys=True),
        "```",
        "</details>",
    ]
    return "\n".join(lines)
