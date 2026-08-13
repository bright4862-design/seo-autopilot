from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Any

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "seo-autopilot-501517")
REGION = os.getenv("AGENT_PLATFORM_LOCATION", "europe-west1")
WORKER = "fixlist-standard150-worker"
GATEWAY = "fixlist-dispatch-gateway"
QUEUE = "fixlist-standard150"
QUEUE_LOCATION = "europe-west1"
SIGNING_SECRET = "SCAN_EVIDENCE_SIGNING_KEY"
MUTATION_CONFIRM = "FIXLIST_RELEASE_MUTATION"
ALLOWED_SERVICES = {WORKER, GATEWAY}


class FixListReleaseOperator:
    """Autonomous GCP operator restricted to the FixList release surface."""

    def set_up(self):
        self.project = PROJECT
        self.region = REGION
        self._run = None
        self._logging = None
        self._tasks = None
        self._builds = None
        self._secrets = None

    @property
    def run(self):
        if self._run is None:
            from google.cloud import run_v2
            self._run = run_v2.ServicesClient()
        return self._run

    @property
    def logging(self):
        if self._logging is None:
            from google.cloud import logging_v2
            self._logging = logging_v2.Client(project=self.project)
        return self._logging

    @property
    def tasks(self):
        if self._tasks is None:
            from google.cloud import tasks_v2
            self._tasks = tasks_v2.CloudTasksClient()
        return self._tasks

    @property
    def builds(self):
        if self._builds is None:
            from google.cloud.devtools import cloudbuild_v1
            self._builds = cloudbuild_v1.CloudBuildClient()
        return self._builds

    @property
    def secrets(self):
        if self._secrets is None:
            from google.cloud import secretmanager
            self._secrets = secretmanager.SecretManagerServiceClient()
        return self._secrets

    def _service_name(self, service: str) -> str:
        if service not in ALLOWED_SERVICES:
            raise PermissionError(f"service is outside the FixList release allowlist: {service}")
        return f"projects/{self.project}/locations/{self.region}/services/{service}"

    def _queue_name(self, queue: str, location: str) -> str:
        if queue != QUEUE or location != QUEUE_LOCATION:
            raise PermissionError("queue is outside the FixList Standard 150 allowlist")
        return self.tasks.queue_path(self.project, location, queue)

    @staticmethod
    def _require_confirm(confirm: str) -> None:
        if confirm != MUTATION_CONFIRM:
            raise PermissionError("exact FixList release mutation confirmation required")

    @staticmethod
    def _summary(service_obj) -> dict[str, Any]:
        return {
            "name": service_obj.name,
            "uri": service_obj.uri,
            "latest_ready_revision": service_obj.latest_ready_revision,
            "latest_created_revision": service_obj.latest_created_revision,
            "reconciling": service_obj.reconciling,
            "service_account": service_obj.template.service_account,
            "images": [c.image for c in list(service_obj.template.containers or [])],
            "traffic": [
                {
                    "revision": t.revision,
                    "percent": t.percent,
                    "tag": t.tag,
                    "uri": t.uri,
                }
                for t in list(service_obj.traffic_statuses or [])
            ],
        }

    def inspect_release_surface(self) -> dict[str, Any]:
        worker = self.run.get_service(name=self._service_name(WORKER))
        gateway = self.run.get_service(name=self._service_name(GATEWAY))
        queue = self.tasks.get_queue(name=self._queue_name(QUEUE, QUEUE_LOCATION))
        return {
            "risk": "READ_ONLY",
            "project": self.project,
            "worker": self._summary(worker),
            "gateway": self._summary(gateway),
            "queue": {
                "name": queue.name,
                "state": str(queue.state),
                "max_dispatches_per_second": queue.rate_limits.max_dispatches_per_second,
                "max_concurrent_dispatches": queue.rate_limits.max_concurrent_dispatches,
            },
        }

    def inspect_cloud_run(self, service: str) -> dict[str, Any]:
        current = self.run.get_service(name=self._service_name(service))
        return {"risk": "READ_ONLY", "service": self._summary(current)}

    def read_logs(
        self,
        service: str,
        minutes: int = 60,
        limit: int = 50,
        request_id: str = "",
        scan_id: str = "",
    ) -> dict[str, Any]:
        self._service_name(service)
        minutes = max(1, min(int(minutes), 1440))
        limit = max(1, min(int(limit), 200))
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        parts = [
            'resource.type="cloud_run_revision"',
            f'resource.labels.service_name="{service}"',
            f'timestamp>="{since.isoformat()}"',
        ]
        if request_id:
            parts.append(f'"{request_id}"')
        if scan_id:
            parts.append(f'"{scan_id}"')
        log_filter = " AND ".join(parts)
        rows: list[dict[str, Any]] = []
        for entry in self.logging.list_entries(
            filter_=log_filter,
            order_by="timestamp desc",
            max_results=limit,
        ):
            rows.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "payload": dict(entry.payload) if isinstance(entry.payload, dict) else str(entry.payload),
                "log_name": entry.log_name,
            })
        return {"risk": "READ_ONLY", "filter": log_filter, "entries": rows}

    def inspect_queue(self, queue: str = QUEUE, location: str = QUEUE_LOCATION) -> dict[str, Any]:
        q = self.tasks.get_queue(name=self._queue_name(queue, location))
        return {
            "risk": "READ_ONLY",
            "name": q.name,
            "state": str(q.state),
            "max_dispatches_per_second": q.rate_limits.max_dispatches_per_second,
            "max_concurrent_dispatches": q.rate_limits.max_concurrent_dispatches,
        }

    def list_tasks(
        self,
        queue: str = QUEUE,
        location: str = QUEUE_LOCATION,
        name_contains: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        from google.cloud import tasks_v2
        parent = self._queue_name(queue, location)
        limit = max(1, min(int(limit), 200))
        rows: list[dict[str, Any]] = []
        pager = self.tasks.list_tasks(
            request={
                "parent": parent,
                "response_view": tasks_v2.Task.View.FULL,
                "page_size": min(limit, 100),
            }
        )
        for task in pager:
            short = task.name.rsplit("/", 1)[-1]
            if name_contains and name_contains not in short:
                continue
            rows.append({
                "name": task.name,
                "schedule_time": task.schedule_time.isoformat() if task.schedule_time else None,
                "dispatch_count": task.dispatch_count,
                "response_count": task.response_count,
                "last_attempt_response_status": getattr(task.last_attempt.response_status, "code", None) if task.last_attempt else None,
            })
            if len(rows) >= limit:
                break
        return {"risk": "READ_ONLY", "tasks": rows}

    def inspect_build(self, build_id: str) -> dict[str, Any]:
        build = self.builds.get_build(project_id=self.project, id=build_id)
        return {
            "risk": "READ_ONLY",
            "id": build.id,
            "status": str(build.status),
            "log_url": build.log_url,
            "images": list(build.images),
        }

    def pause_queue(self, confirm: str, queue: str = QUEUE, location: str = QUEUE_LOCATION) -> dict[str, Any]:
        self._require_confirm(confirm)
        q = self.tasks.pause_queue(name=self._queue_name(queue, location))
        return {"risk": "PRODUCTION_MUTATION", "operation": "pause_queue", "name": q.name, "state": str(q.state)}

    def resume_queue(self, confirm: str, queue: str = QUEUE, location: str = QUEUE_LOCATION) -> dict[str, Any]:
        self._require_confirm(confirm)
        q = self.tasks.resume_queue(name=self._queue_name(queue, location))
        return {"risk": "PRODUCTION_MUTATION", "operation": "resume_queue", "name": q.name, "state": str(q.state)}

    def set_traffic_100(self, service: str, revision: str, confirm: str) -> dict[str, Any]:
        from google.cloud import run_v2
        from google.protobuf.field_mask_pb2 import FieldMask
        self._require_confirm(confirm)
        name = self._service_name(service)
        current = self.run.get_service(name=name)
        if current.reconciling:
            raise RuntimeError("Cloud Run service is reconciling; mutation blocked")
        short_revision = str(revision or "").rsplit("/", 1)[-1]
        if not short_revision.startswith(f"{service}-"):
            raise PermissionError("revision does not belong to the allowlisted service")
        current.traffic = [run_v2.TrafficTarget(
            type_=run_v2.TrafficTargetAllocationType.TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION,
            revision=short_revision,
            percent=100,
        )]
        self.run.update_service(
            service=current,
            update_mask=FieldMask(paths=["traffic"]),
        ).result(timeout=300)
        verified = self.run.get_service(name=name)
        return {"risk": "PRODUCTION_MUTATION", "operation": "set_traffic_100", "verification": self._summary(verified)}

    def export_signing_key_encrypted(self, public_key_pem: str) -> dict[str, str]:
        """Return the worker's exact pinned signing key only as hybrid-encrypted ciphertext."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os as _os

        worker = self.run.get_service(name=self._service_name(WORKER))
        secret_name = ""
        secret_version = ""
        for container in list(worker.template.containers or []):
            for env in list(container.env or []):
                if env.name != SIGNING_SECRET:
                    continue
                source = getattr(env, "value_source", None)
                ref = getattr(source, "secret_key_ref", None) if source else None
                secret_name = str(getattr(ref, "secret", "") or "")
                secret_version = str(getattr(ref, "version", "") or "")
                break
        if not secret_name or not secret_version or secret_version == "latest":
            raise RuntimeError("live worker signing secret is not pinned to an exact version")

        resource = f"projects/{self.project}/secrets/{secret_name}/versions/{secret_version}"
        response = self.secrets.access_secret_version(request={"name": resource})
        plaintext = bytes(response.payload.data)

        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        aes_key = _os.urandom(32)
        nonce = _os.urandom(12)
        aad = f"{self.project}:{secret_name}:{secret_version}".encode("utf-8")
        ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, aad)
        wrapped_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return {
            "risk": "SECRET_CIPHERTEXT_ONLY",
            "secret": secret_name,
            "version": secret_version,
            "wrapped_key_b64": base64.b64encode(wrapped_key).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "aad_b64": base64.b64encode(aad).decode("ascii"),
        }


release_operator = FixListReleaseOperator()
