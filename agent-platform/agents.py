from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hmac
import os
from typing import Any, Optional


def _project(explicit: Optional[str] = None) -> str:
    value = explicit or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if not value:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required")
    return value


def _secret(project: str, secret_id: str, version: str = "latest") -> str:
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


RESEARCH_SYSTEM = """
You are the FixList Product Research Agent.
Research how FixList can become more useful, accurate, differentiated, reliable,
easier to use, and commercially stronger. Use current web evidence. Do not invent
competitor functionality. Distinguish VERIFIED FACT, REASONABLE INFERENCE,
PRODUCT IDEA and EXPERIMENTAL IDEA. Prefer incremental improvements over
fashionable rewrites, and treat production reliability as more important than
feature volume. Never modify code, production, IAM, pricing or customer state.
For significant recommendations include: Finding, Evidence, FixList Opportunity,
Recommended Change, Expected Impact, Engineering Effort, Risk, Confidence,
and Suggested Experiment.
""".strip()


class FixListResearchAgent:
    def __init__(self, model: str = "gemini-3.5-flash", project: Optional[str] = None):
        self.model_name = model
        self.project = project

    def set_up(self):
        from google import genai
        from google.genai.types import HttpOptions
        self.project = _project(self.project)
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location="global",
            http_options=HttpOptions(api_version="v1"),
        )

    @staticmethod
    def _sources(response: Any) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return out
        metadata = getattr(candidates[0], "grounding_metadata", None)
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if not web:
                continue
            uri = getattr(web, "uri", None)
            if not uri or uri in seen:
                continue
            seen.add(uri)
            out.append({
                "title": getattr(web, "title", None) or "",
                "uri": uri,
                "domain": getattr(web, "domain", None) or "",
            })
        return out

    def query(
        self,
        question: str,
        fixlist_context: str = "",
        competitors: Optional[list[str]] = None,
    ) -> dict:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
        competitors = competitors or []
        prompt = f"""
RESEARCH QUESTION
{question}

CURRENT FIXLIST CONTEXT
{fixlist_context or 'No additional context supplied.'}

COMPARATORS
{', '.join(competitors) if competitors else 'Choose the most relevant current products.'}

Research current evidence first. Return prioritized FixList improvements rather
than a generic market summary.
""".strip()
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=GenerateContentConfig(
                system_instruction=RESEARCH_SYSTEM,
                temperature=0.0,
                tools=[Tool(google_search=GoogleSearch())],
            ),
        )
        return {
            "agent": "fixlist-research",
            "model": self.model_name,
            "answer": getattr(response, "text", "") or "",
            "sources": self._sources(response),
        }


CLAUDE_SYSTEM = """
You are Claude acting as the senior engineering collaborator for FixList.
Work only inside the assignment sent by the FixList Claude Liaison. Separate
verified evidence from inference. Never claim a command, test, commit, merge,
deployment or configuration change occurred unless evidence proves it. If scope
must expand, return SCOPE EXPANSION REQUIRED and explain why. Preserve immutable
identifiers exactly.
""".strip()


class FixListClaudeLiaisonAgent:
    def __init__(
        self,
        model: str = "claude-opus-5",
        project: Optional[str] = None,
        secret_id: str = "anthropic-api-key",
        max_tokens: int = 8000,
    ):
        self.model_name = model
        self.project = project
        self.secret_id = secret_id
        self.max_tokens = max_tokens

    def set_up(self):
        self.project = _project(self.project)
        self.client = None

    def _client(self):
        if self.client is None:
            from anthropic import Anthropic
            self.client = Anthropic(
                api_key=_secret(self.project, self.secret_id),
                timeout=180.0,
                max_retries=2,
            )
        return self.client

    def query(
        self,
        objective: str,
        verified_state: str = "",
        scope: str = "",
        authorized_actions: Optional[list[str]] = None,
        prohibited_actions: Optional[list[str]] = None,
        acceptance_criteria: Optional[list[str]] = None,
        conversation: Optional[list[dict[str, str]]] = None,
    ) -> dict:
        authorized_actions = authorized_actions or []
        prohibited_actions = prohibited_actions or []
        acceptance_criteria = acceptance_criteria or []
        bullets = lambda items: "\n".join(f"- {item}" for item in items) if items else "- None supplied"
        assignment = f"""
FIXLIST TASK

OBJECTIVE
{objective}

CURRENT VERIFIED STATE
{verified_state or 'No additional verified state supplied.'}

EXACT SCOPE
{scope or 'Limit work strictly to the objective.'}

AUTHORIZED ACTIONS
{bullets(authorized_actions)}

PROHIBITED ACTIONS
{bullets(prohibited_actions)}

ACCEPTANCE CRITERIA
{bullets(acceptance_criteria)}

REQUIRED RESPONSE
CLAUDE STATUS: COMPLETE / BLOCKED / NEEDS REVIEW
TASK
WHAT YOU DID
EVIDENCE
UNRESOLVED ITEMS
RECOMMENDED NEXT ACTION
""".strip()
        messages: list[dict[str, str]] = []
        for item in conversation or []:
            if item.get("role") in {"user", "assistant"} and item.get("content"):
                messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": assignment})
        response = self._client().messages.create(
            model=self.model_name,
            system=CLAUDE_SYSTEM,
            max_tokens=self.max_tokens,
            messages=messages,
        )
        text = "\n".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return {
            "agent": "fixlist-claude-liaison",
            "model": self.model_name,
            "claude_message_id": response.id,
            "stop_reason": response.stop_reason,
            "answer": text,
        }


class FixListCloudOperatorAgent:
    def __init__(
        self,
        project: Optional[str] = None,
        default_region: str = "europe-west1",
        approval_secret_id: str = "fixlist-cloud-mutation-approval-token",
    ):
        self.project = project
        self.default_region = default_region
        self.approval_secret_id = approval_secret_id

    def set_up(self):
        from google.cloud import logging_v2, run_v2, tasks_v2
        from google.cloud.devtools import cloudbuild_v1
        self.project = _project(self.project)
        self.run_services = run_v2.ServicesClient()
        self.logging = logging_v2.Client(project=self.project)
        self.tasks = tasks_v2.CloudTasksClient()
        self.builds = cloudbuild_v1.CloudBuildClient()
        self._approval_token = None

    def _require_approval(self, supplied: str) -> None:
        if self._approval_token is None:
            self._approval_token = _secret(self.project, self.approval_secret_id)
        if not supplied or not hmac.compare_digest(self._approval_token, supplied):
            raise PermissionError("Valid production mutation approval token required")

    def _service_name(self, service: str, region: str = "") -> str:
        return f"projects/{self.project}/locations/{region or self.default_region}/services/{service}"

    @staticmethod
    def _short_revision(name: str) -> str:
        return name.rsplit("/", 1)[-1]

    @staticmethod
    def _summary(service_obj) -> dict:
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

    def inspect_cloud_run(self, service: str, region: str = "") -> dict:
        current = self.run_services.get_service(name=self._service_name(service, region))
        return {"risk": "READ_ONLY", "service": self._summary(current)}

    def read_logs(
        self,
        service: str,
        minutes: int = 60,
        limit: int = 50,
        request_id: str = "",
        scan_id: str = "",
    ) -> dict:
        minutes = max(1, min(minutes, 1440))
        limit = max(1, min(limit, 200))
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
        rows = []
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

    def inspect_build(self, build_id: str) -> dict:
        build = self.builds.get_build(project_id=self.project, id=build_id)
        return {
            "risk": "READ_ONLY",
            "id": build.id,
            "status": str(build.status),
            "log_url": build.log_url,
            "images": list(build.images),
        }

    def inspect_queue(self, queue: str, location: str) -> dict:
        q = self.tasks.get_queue(name=self.tasks.queue_path(self.project, location, queue))
        return {
            "risk": "READ_ONLY",
            "name": q.name,
            "state": str(q.state),
            "max_dispatches_per_second": q.rate_limits.max_dispatches_per_second,
            "max_concurrent_dispatches": q.rate_limits.max_concurrent_dispatches,
        }

    def pause_queue(self, queue: str, location: str, approval_token: str) -> dict:
        self._require_approval(approval_token)
        q = self.tasks.pause_queue(name=self.tasks.queue_path(self.project, location, queue))
        return {"risk": "PRODUCTION_MUTATION", "operation": "pause_queue", "name": q.name, "state": str(q.state)}

    def resume_queue(self, queue: str, location: str, approval_token: str) -> dict:
        self._require_approval(approval_token)
        q = self.tasks.resume_queue(name=self.tasks.queue_path(self.project, location, queue))
        return {"risk": "PRODUCTION_MUTATION", "operation": "resume_queue", "name": q.name, "state": str(q.state)}

    def set_traffic_100(self, service: str, revision: str, approval_token: str, region: str = "") -> dict:
        from google.cloud import run_v2
        from google.protobuf.field_mask_pb2 import FieldMask
        self._require_approval(approval_token)
        name = self._service_name(service, region)
        current = self.run_services.get_service(name=name)
        if current.reconciling:
            raise RuntimeError("Cloud Run service is currently reconciling; mutation blocked")
        current.traffic = [run_v2.TrafficTarget(
            type_=run_v2.TrafficTargetAllocationType.TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION,
            revision=self._short_revision(revision),
            percent=100,
        )]
        self.run_services.update_service(
            service=current,
            update_mask=FieldMask(paths=["traffic"]),
        ).result(timeout=300)
        verified = self.run_services.get_service(name=name)
        return {"risk": "PRODUCTION_MUTATION", "operation": "set_traffic_100", "verification": self._summary(verified)}


research_agent = FixListResearchAgent()
claude_liaison_agent = FixListClaudeLiaisonAgent()
cloud_operator_agent = FixListCloudOperatorAgent()
