import json

from hypothesis import given
from hypothesis import strategies as st

from merge_gate.model import Assessment, ChangeClass, Reason, ReasonCode
from merge_gate.verdict import MARKER, decide, parse_review, record, render_comment

from .helpers import pr

GOOD = {
    "verdict": "merge",
    "confidence": 9,
    "summary": "Adds X.",
    "criteria": [{"criterion": "x -> y", "met": True, "evidence": "a.go:3"}],
    "findings": [{"severity": "nit", "file": "a.go", "summary": "naming"}],
}


def clean(change_class=ChangeClass.CODE):
    return Assessment(pr(), change_class, 10)


def codes(v):
    return {r.code for r in v.reasons}


def with_(**kw):
    return parse_review(json.dumps({**GOOD, **kw}))


def test_good_review_would_merge():
    assert decide(clean(), parse_review(json.dumps(GOOD))).would_merge


def test_fail_closed():
    assert codes(decide(clean(), None)) == {ReasonCode.NO_REVIEW}
    assert codes(decide(clean(), with_(verdict="manual"))) == {ReasonCode.REVIEW_MANUAL}
    assert codes(decide(clean(), with_(confidence=7))) == {ReasonCode.LOW_CONFIDENCE}
    blocker = [{"severity": "major", "file": "a.go", "summary": "bug"}]
    assert codes(decide(clean(), with_(findings=blocker))) == {ReasonCode.BLOCKING_FINDING}
    unmet = [{"criterion": "x", "met": False, "evidence": "missing"}]
    assert codes(decide(clean(), with_(criteria=unmet))) == {ReasonCode.UNMET_CRITERION}
    assert codes(decide(clean(), with_(criteria=[]))) == {ReasonCode.NO_CRITERIA}
    assert decide(clean(ChangeClass.DEPS_PATCH), with_(criteria=[])).would_merge


def test_assessment_reasons_win_over_any_review():
    a = Assessment(pr(), ChangeClass.CODE, 10, (Reason(ReasonCode.CRITICAL_PATH, ".github/x"),))
    assert codes(decide(a, parse_review(json.dumps(GOOD)))) == {ReasonCode.CRITICAL_PATH}


def test_parse_review_rejects_anything_off_schema():
    for bad in [
        "",
        "null",
        "[]",
        json.dumps({**GOOD, "extra": 1}),
        json.dumps({k: v for k, v in GOOD.items() if k != "findings"}),
        json.dumps({**GOOD, "confidence": True}),
        json.dumps({**GOOD, "confidence": 11}),
        json.dumps({**GOOD, "confidence": 9.5}),
        json.dumps({**GOOD, "verdict": "approve"}),
        json.dumps({**GOOD, "criteria": "all met"}),
        json.dumps({**GOOD, "criteria": [{"criterion": "x", "met": "yes", "evidence": ""}]}),
        json.dumps({**GOOD, "findings": [{"severity": "critical", "file": "", "summary": ""}]}),
        json.dumps({**GOOD, "findings": [{"severity": "nit", "summary": ""}]}),
    ]:
        assert parse_review(bad) is None, bad


json_value = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=10),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=10), children, max_size=6),
    max_leaves=20,
)


@given(json_value)
def test_parse_review_never_raises(value):
    parse_review(json.dumps(value))


@given(st.dictionaries(st.sampled_from(sorted(GOOD)), json_value, min_size=5, max_size=5))
def test_would_merge_only_with_a_fully_positive_review(raw):
    review = parse_review(json.dumps(raw))
    verdict = decide(clean(), review)
    if verdict.would_merge:
        assert review.merge and review.confidence >= 8 and review.criteria
        assert all(c.met for c in review.criteria)
        assert not any(f.severity in ("blocker", "major") for f in review.findings)


def test_comment_neutralises_model_text_and_carries_a_record():
    hostile = with_(summary="@owner <img src=x> ```merge```", findings=[{"severity": "nit", "file": "<a>", "summary": "@x"}])
    verdict = decide(clean(), hostile)
    body = render_comment(verdict, "https://example.test/run/1")
    assert body.startswith(MARKER)
    assert "@owner" not in body and "<img" not in body and "<a>" not in body
    rec = json.loads(body.split("```json\n")[1].split("\n```")[0])
    assert rec == record(verdict, "https://example.test/run/1")
    assert rec["verdict"] == "would-merge" and rec["class"] == "code"
