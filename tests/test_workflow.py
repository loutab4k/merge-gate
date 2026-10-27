from pathlib import Path

GATE = (Path(__file__).parent.parent / ".github" / "workflows" / "gate.yml").read_text()


def test_no_run_line_interpolates_an_expression():
    """Untrusted text reaches a shell only through env, so every run: is one line without ${{."""
    runs = [line.strip() for line in GATE.split("\n") if line.strip().startswith(("run:", "- run:"))]
    assert runs
    for run in runs:
        assert "${{" not in run and run.split("run:", 1)[1].strip() not in ("|", ">", "|-", ">-"), run


def test_the_failure_reason_flows_from_the_review_step_to_report():
    assert "failure_reason: ${{ steps.failure.outputs.reason }}" in GATE
    assert "if: failure() && steps.claude.outcome == 'failure'" in GATE
    assert "EXECUTION_FILE: ${{ steps.claude.outputs.execution_file }}" in GATE
    assert 'run: python3 -s -E -m merge_gate.failure "$EXECUTION_FILE"' in GATE
    assert "REVIEW_FAILURE: ${{ needs.review.outputs.failure_reason }}" in GATE
