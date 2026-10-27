import json

from hypothesis import given
from hypothesis import strategies as st

from merge_gate import failure

PROMPT = "Review this PR. PROMPT-TEXT"
DIFF = "+DIFF-LINE secret-looking"
LIMIT_TEXT = "Claude AI usage limit reached|1761523200"


def execution(result):
    """The shape claude-code-action@925afb53 writes: every SDK message, prompt and diff included."""
    return [
        {"type": "system", "subtype": "init", "model": "claude-opus-5-5", "tools": ["Read"]},
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": PROMPT + DIFF}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Looking at " + DIFF}]}},
        {"type": "result", "duration_ms": 1017, "num_turns": 1, "total_cost_usd": 0, "modelUsage": {}, **result},
    ]


# Run 40367941066, attempt 1: the action logged only these fields and the error text was lost.
RECORDED = execution({"subtype": "success", "is_error": True, "result": LIMIT_TEXT})


def run_main(tmp_path, monkeypatch, capsys, content):
    path = tmp_path / "claude-execution-output.json"
    path.write_text(content)
    out = tmp_path / "GITHUB_OUTPUT"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert failure.main(["x", str(path)]) == 0
    return capsys.readouterr().out, out.read_text()


def test_a_recorded_error_result_gives_its_text_and_nothing_else(tmp_path, monkeypatch, capsys):
    log, output = run_main(tmp_path, monkeypatch, capsys, json.dumps(RECORDED))
    reason = f"subtype success, is_error true: {LIMIT_TEXT}"
    assert log == f"merge-gate: review failed: {reason}\n"
    assert output == f"reason={reason}\n"
    for text in (log, output):
        assert "PROMPT-TEXT" not in text and "DIFF-LINE" not in text


def test_error_subtypes_give_their_errors():
    messages = execution({"subtype": "error_during_execution", "is_error": True, "errors": ["API Error: 529", "overloaded"]})
    assert failure.failure_reason(messages) == "subtype error_during_execution, is_error true: API Error: 529; overloaded"


def test_a_result_without_an_error_never_shows_model_text():
    messages = execution({"subtype": "success", "is_error": False, "result": "The diff adds " + DIFF})
    assert failure.failure_reason(messages) == "subtype success, is_error false: no structured output"


def test_a_missing_or_broken_file_says_so(tmp_path, monkeypatch, capsys):
    assert failure.reason_from_file("") == "no execution file"
    assert failure.reason_from_file(str(tmp_path / "absent.json")) == "execution file unreadable"
    assert run_main(tmp_path, monkeypatch, capsys, "{not json")[1] == "reason=execution file is not JSON\n"
    assert failure.failure_reason({"type": "result"}) == "no result message"
    assert failure.failure_reason(RECORDED[:-1]) == "no result message"


def test_a_long_error_is_cut_to_the_limit():
    reason = failure.failure_reason(execution({"subtype": "success", "is_error": True, "result": "x" * 5000}))
    assert len(reason) == failure.LIMIT and reason.startswith("subtype success, is_error true: xxx")


def test_control_characters_never_reach_the_line():
    text = "a\x1b[31mb\x00c ::error::d"
    assert failure.failure_reason(execution({"subtype": "success", "is_error": True, "result": text})) == (
        "subtype success, is_error true: a [31mb c ::error::d"
    )


def test_only_the_last_result_counts():
    first = {"type": "result", "subtype": "success", "is_error": True, "result": "old"}
    assert failure.failure_reason([first, *RECORDED]).endswith(LIMIT_TEXT)


hostile_json = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=12,
)


@given(st.text(), st.text(), hostile_json)
def test_the_reason_is_always_one_short_printable_line(subtype, text, errors):
    for result in (
        {"subtype": subtype, "is_error": True, "result": text},
        {"subtype": "error_max_turns", "is_error": True, "errors": errors},
        {"subtype": subtype, "result": errors},
    ):
        reason = failure.failure_reason(execution(result))
        assert len(reason) <= failure.LIMIT and reason.isprintable() and reason == reason.strip()


@given(hostile_json)
def test_any_execution_file_gives_a_reason(value):
    assert failure.failure_reason(value)
