import json

import pytest
from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from app.stage_tasks import StageTaskDispatcher, configured_dispatcher, stage_task_id


class Client:
    def __init__(self, *, duplicate=False):
        self.requests = []
        self.duplicate = duplicate

    def create_task(self, *, request, timeout, retry):
        assert timeout == 20 and retry is None
        # Validate the real SDK wire schema, not merely a hand-written mock.
        tasks_v2.types.CreateTaskRequest(**request)
        self.requests.append(request)
        if self.duplicate:
            raise AlreadyExists("already queued")


@pytest.mark.asyncio
async def test_dispatch_pins_origin_queue_and_oidc_and_preserves_future_pacer_slot():
    client = Client()
    dispatcher = StageTaskDispatcher("projects/test-project/locations/europe-west1/queues/scan-stages", "https://worker.example.run.app", "invoker@test-project.iam.gserviceaccount.com", client=client)
    job = {"scan_id": "scan_test", "attempt_count": 2, "website_url": "https://site.example/", "worker_url": "https://attacker.example"}
    await dispatcher.enqueue(job, "batch", 3, not_before=1800000000.5)
    task = client.requests[0]["task"]
    http = task["http_request"]
    assert http["url"] == "https://worker.example.run.app/scan-batch"
    assert http["oidc_token"]["audience"] == "https://worker.example.run.app"
    assert http["oidc_token"]["service_account_email"] == "invoker@test-project.iam.gserviceaccount.com"
    assert task["dispatch_deadline"]["seconds"] == 480
    assert task["schedule_time"] == {"seconds": 1800000000, "nanos": 500000000}
    assert json.loads(http["body"])["batch"] == 3
    assert task["name"].endswith(stage_task_id(job, "batch", 3))


@pytest.mark.asyncio
async def test_duplicate_task_creation_is_success_and_does_not_change_identity():
    client = Client(duplicate=True)
    dispatcher = StageTaskDispatcher("projects/project/locations/europe-west1/queues/stages", "https://worker.example", "invoker@project.iam.gserviceaccount.com", client=client)
    job = {"scan_id": "scan_test", "attempt_count": 1}
    await dispatcher.enqueue(job, "finalize", 2, limited=True)
    assert stage_task_id(job, "finalize", 2) == stage_task_id(dict(job), "finalize", 2)
    assert stage_task_id(job, "finalize", 2) != stage_task_id({**job, "attempt_count": 2}, "finalize", 2)


@pytest.mark.parametrize("origin", ["http://worker.example", "https://worker.example/scan-batch", "https://worker.example?target=evil", "https://user:pass@worker.example"])
def test_unpinned_worker_origins_are_rejected(origin):
    with pytest.raises(RuntimeError):
        StageTaskDispatcher("projects/project/locations/europe-west1/queues/stages", origin, "invoker@project.iam.gserviceaccount.com")


def test_infrastructure_environment_contract(monkeypatch):
    monkeypatch.setenv("SCAN_STAGE_TASKS_QUEUE_PATH", "projects/project/locations/europe-west1/queues/stages")
    monkeypatch.setenv("SCAN_STAGE_TARGET_URL", "https://worker.example")
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "invoker@project.iam.gserviceaccount.com")
    configured = configured_dispatcher()
    assert configured.queue_path == "projects/project/locations/europe-west1/queues/stages"
    assert configured.worker_url == "https://worker.example"
