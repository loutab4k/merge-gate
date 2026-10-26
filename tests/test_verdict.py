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


def test_a_critical_path_needs_a_human_whatever_the_review_says():
    a = Assessment(pr(), ChangeClass.CODE, 10, (Reason(ReasonCode.CRITICAL_PATH, ".github/x"),))
    v = decide(a, parse_review(json.dumps(GOOD)))
    assert codes(v) == {ReasonCode.CRITICAL_PATH} and not v.would_merge and v.review is not None
    assert codes(decide(a, with_(verdict="manual"))) == {ReasonCode.CRITICAL_PATH, ReasonCode.REVIEW_MANUAL}
    assert codes(decide(a, None)) == {ReasonCode.CRITICAL_PATH, ReasonCode.NO_REVIEW}


def test_other_assessment_reasons_drop_any_review():
    a = Assessment(pr(), ChangeClass.CODE, 10, (Reason(ReasonCode.SKIP_MARKER, "a_test.go adds t.Skip("),))
    v = decide(a, parse_review(json.dumps(GOOD)))
    assert codes(v) == {ReasonCode.SKIP_MARKER} and v.review is None


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
        json.dumps({**GOOD, "findings": {}}),
        json.dumps({**GOOD, "findings": ""}),
        json.dumps({**GOOD, "criteria": {}}),
        json.dumps({**GOOD, "findings": [{"severity": "nit", "file": "", "summary": "", "real": "blocker"}]}),
        json.dumps({**GOOD, "criteria": [{"criterion": "x", "met": True, "evidence": "", "note": ""}]}),
        json.dumps({**GOOD, "findings": [{"severity": ["nit"], "file": "", "summary": ""}]}),
        json.dumps(GOOD).replace('"confidence": 9', '"confidence": 9' + "0" * 5000),
        "[" * 100_000 + "]" * 100_000,
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


criterion = st.fixed_dictionaries({"criterion": st.text(max_size=5), "met": st.booleans(), "evidence": st.text(max_size=5)})
finding = st.fixed_dictionaries(
    {"severity": st.sampled_from(["blocker", "major", "minor", "nit"]), "file": st.text(max_size=5), "summary": st.text(max_size=5)}
)
valid_review = st.fixed_dictionaries(
    {
        "verdict": st.sampled_from(["merge", "manual"]),
        "confidence": st.integers(0, 10),
        "summary": st.text(max_size=10),
        "criteria": st.lists(criterion, max_size=3),
        "findings": st.lists(finding, max_size=3),
    }
)


@given(valid_review, st.sampled_from(list(ChangeClass)))
def test_would_merge_exactly_when_the_review_is_fully_positive(raw, change_class):
    review = parse_review(json.dumps(raw))
    assert review is not None
    positive = (
        raw["verdict"] == "merge"
        and raw["confidence"] >= 8
        and all(c["met"] for c in raw["criteria"])
        and not any(f["severity"] in ("blocker", "major") for f in raw["findings"])
        and (raw["criteria"] or change_class in (ChangeClass.DEPS_PATCH, ChangeClass.DEPS_OTHER))
    )
    assert decide(clean(change_class), review).would_merge == bool(positive)


@given(valid_review, st.sampled_from(["verdict", "confidence", "summary", "criteria", "findings"]), json_value)
def test_any_off_schema_field_means_no_review(raw, key, value):
    fits = {
        "verdict": value in ("merge", "manual"),
        "confidence": type(value) is int and 0 <= value <= 10,
        "summary": isinstance(value, str),
        # Random JSON almost never builds an item with the exact keys, so only [] fits.
        "criteria": value == [],
        "findings": value == [],
    }[key]
    assert (parse_review(json.dumps({**raw, key: value})) is not None) == fits


def test_comment_neutralises_model_text_and_carries_a_record():
    hostile = with_(
        summary="@owner <img src=x> ```merge``` ![ok](https://evil.test/p.png?d=1) [x](https://evil.test)\n\n# Title",
        findings=[{"severity": "nit", "file": "<a>", "summary": "@x other/repo#1"}],
    )
    verdict = decide(clean(), hostile)
    body = render_comment(verdict, "https://example.test/run/1")
    assert body.startswith(MARKER)
    # Every model-written text sits inside one inline code span that nothing can close.
    for line in body.split("\n"):
        if "evil.test" in line or "@owner" in line or "@x" in line or "<a>" in line:
            span = line.split(": ", 1)[1]
            assert span.startswith("`") and span.endswith("`") and span.count("`") == 2, line
    assert "\n# Title" not in body
    rec = json.loads(body.split("```json\n")[1].split("\n```")[0])
    assert rec == record(verdict, "https://example.test/run/1")
    assert rec["verdict"] == "would-merge" and rec["class"] == "code" and rec["review"] == "merge"
    critical = Assessment(pr(), ChangeClass.CODE, 10, (Reason(ReasonCode.CRITICAL_PATH, ".github/x"),))
    rec = record(decide(critical, parse_review(json.dumps(GOOD))), "")
    assert rec["verdict"] == "manual" and rec["review"] == "merge"
    assert record(decide(critical, with_(verdict="manual")), "")["review"] == "manual"
    assert record(decide(critical, None), "")["review"] is None
