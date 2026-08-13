from __future__ import annotations

import os
import vertexai

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.getenv("AGENT_PLATFORM_LOCATION", "europe-west1")
client = vertexai.Client(project=PROJECT, location=LOCATION)

AGENTS = {
    "research": {
        "display_name": "FixList Research Agent",
        "description": "Grounded research on how to improve FixList.",
        "entrypoint_object": "research_agent",
        "methods": [{
            "name": "query", "api_mode": "", "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "fixlist_context": {"type": "string"},
                    "competitors": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question"],
            },
        }],
    },
    "claude": {
        "display_name": "FixList Claude Liaison",
        "description": "Controlled liaison between FixList and Claude Opus 5.",
        "entrypoint_object": "claude_liaison_agent",
        "methods": [{
            "name": "query", "api_mode": "", "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"},
                    "verified_state": {"type": "string"},
                    "scope": {"type": "string"},
                    "authorized_actions": {"type": "array", "items": {"type": "string"}},
                    "prohibited_actions": {"type": "array", "items": {"type": "string"}},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "conversation": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["objective"],
            },
        }],
    },
    "cloud": {
        "display_name": "FixList Cloud Operator",
        "description": "Controlled Cloud Run, Cloud Logging, Cloud Build and Cloud Tasks operator.",
        "entrypoint_object": "cloud_operator_agent",
        "methods": [
            {"name": "inspect_cloud_run", "api_mode": "", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "region": {"type": "string"}}, "required": ["service"]}},
            {"name": "read_logs", "api_mode": "", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "minutes": {"type": "integer"}, "limit": {"type": "integer"}, "request_id": {"type": "string"}, "scan_id": {"type": "string"}}, "required": ["service"]}},
            {"name": "inspect_build", "api_mode": "", "parameters": {"type": "object", "properties": {"build_id": {"type": "string"}}, "required": ["build_id"]}},
            {"name": "inspect_queue", "api_mode": "", "parameters": {"type": "object", "properties": {"queue": {"type": "string"}, "location": {"type": "string"}}, "required": ["queue", "location"]}},
            {"name": "pause_queue", "api_mode": "", "parameters": {"type": "object", "properties": {"queue": {"type": "string"}, "location": {"type": "string"}, "approval_token": {"type": "string"}}, "required": ["queue", "location", "approval_token"]}},
            {"name": "resume_queue", "api_mode": "", "parameters": {"type": "object", "properties": {"queue": {"type": "string"}, "location": {"type": "string"}, "approval_token": {"type": "string"}}, "required": ["queue", "location", "approval_token"]}},
            {"name": "set_traffic_100", "api_mode": "", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "revision": {"type": "string"}, "approval_token": {"type": "string"}, "region": {"type": "string"}}, "required": ["service", "revision", "approval_token"]}},
        ],
    },
}


def deploy(name: str):
    spec = AGENTS[name]
    remote = client.agent_engines.create(config={
        "display_name": spec["display_name"],
        "description": spec["description"],
        "source_packages": ["agents.py", "requirements.txt"],
        "entrypoint_module": "agents",
        "entrypoint_object": spec["entrypoint_object"],
        "requirements_file": "requirements.txt",
        "class_methods": spec["methods"],
    })
    print(f"DEPLOYED {name}: {remote.api_resource.name}", flush=True)


def selected_agents() -> list[str]:
    raw = os.getenv("FIXLIST_AGENTS_TO_DEPLOY", "research,claude,cloud")
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise ValueError("FIXLIST_AGENTS_TO_DEPLOY selected no agents")
    unknown = [name for name in names if name not in AGENTS]
    if unknown:
        raise ValueError(f"Unknown agent deployment target(s): {', '.join(unknown)}")
    return names


for name in selected_agents():
    deploy(name)
