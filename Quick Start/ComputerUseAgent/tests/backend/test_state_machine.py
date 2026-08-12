import pytest

from cua_platform.tasks.state_machine import (
    ExecutionStatus,
    Verdict,
    derive_verdict,
    transition,
    validate_terminal_outcome,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ExecutionStatus.SCRIPT_PENDING, ExecutionStatus.QUEUED),
        (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING),
        (ExecutionStatus.QUEUED, ExecutionStatus.RESULT_READY),
        (ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED),
        (ExecutionStatus.RUNNING, ExecutionStatus.RESULT_READY),
        (ExecutionStatus.RUNNING, ExecutionStatus.CANCELLED),
    ],
)
def test_allowed_transitions(current, target):
    assert transition(current, target) == target


def test_invalid_transition_fails_fast():
    with pytest.raises(ValueError, match="invalid_transition"):
        transition(ExecutionStatus.SCRIPT_PENDING, ExecutionStatus.RESULT_READY)


@pytest.mark.parametrize(
    ("must_results", "evidence_complete", "expected"),
    [
        (["pass", "pass"], True, Verdict.PASS),
        (["pass", "fail"], True, Verdict.FAIL),
        (["pass", "unknown"], True, Verdict.FAIL),
        (["pass"], False, Verdict.FAIL),
        ([], True, Verdict.FAIL),
    ],
)
def test_verdict_never_defaults_to_pass(must_results, evidence_complete, expected):
    assert derive_verdict(must_results, evidence_complete) == expected


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        (ExecutionStatus.RESULT_READY, Verdict.PASS),
        (ExecutionStatus.RESULT_READY, Verdict.FAIL),
        (ExecutionStatus.CANCELLED, None),
    ],
)
def test_terminal_outcome_accepts_consistent_status_and_verdict(status, verdict):
    validate_terminal_outcome(status, verdict)


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        (ExecutionStatus.CANCELLED, Verdict.PASS),
        (ExecutionStatus.CANCELLED, Verdict.FAIL),
        (ExecutionStatus.RUNNING, Verdict.PASS),
        (ExecutionStatus.RUNNING, None),
    ],
)
def test_terminal_outcome_rejects_inconsistent_status_and_verdict(status, verdict):
    with pytest.raises(ValueError, match="invalid_terminal_outcome"):
        validate_terminal_outcome(status, verdict)
