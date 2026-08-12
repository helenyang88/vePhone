import os
from dataclasses import replace
from datetime import UTC, datetime

from mua_platform.main import create_app
from mua_platform.pods.models import DiscoveredPod
from mua_platform.runners.base import PollResult, RunRequest, RunnerEvent
from mua_platform.runners.mock import MockRunner

if os.environ.get("APP_ENV") != "e2e":
    raise RuntimeError("test_plan_server_requires_e2e_environment")


class TestPlanRunner(MockRunner):
    runner_type = "mobile_use"

    async def start(self, request: RunRequest, idempotency_key: str):
        normalized = replace(
            request,
            steps=request.steps
            or [{"index": 1, "instruction": request.content_markdown}],
            assertions=request.assertions or [],
        )
        return await super().start(normalized, idempotency_key)

    async def poll(self, handle, after_sequence):
        page = await super().poll(handle, after_sequence)
        request = self._request_from_handle(handle)
        events = tuple(
            _terminal_event(event, request.scenario)
            for event in page.events
        )
        return PollResult(events=events, terminal=page.terminal)


def _terminal_event(event: RunnerEvent, scenario: str) -> RunnerEvent:
    if event.type != "task_finished":
        return event
    if scenario == "success":
        outcome = {
            "verdict": "pass",
            "evidence_complete": True,
        }
    elif scenario == "assertion_failure":
        outcome = {
            "verdict": "fail",
            "failure_type": "assertion_failed",
            "evidence_complete": True,
        }
    else:
        outcome = {
            "verdict": "fail",
            "failure_type": "evidence_missing",
            "evidence_complete": False,
        }
    return RunnerEvent(
        sequence=event.sequence,
        type=event.type,
        payload=outcome,
    )


app = create_app(
    runner_factory=lambda _task, _config, _request_loader: TestPlanRunner(
        os.environ["APP_SECRET_KEY"],
    )
)

with app.state.session_factory() as db:
    db.add(
        DiscoveredPod(
            id="pod_row_test_plan",
            product_id=os.environ["COMPUTER_USE_ACCOUNT_ID"],
            pod_id="pod-test-plan",
            pod_name="test-plan-device",
            pod_status_code=1,
            discovery_state="active",
            last_seen_at=datetime.now(UTC),
        )
    )
    db.commit()
