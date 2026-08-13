from __future__ import annotations

import os
import vertexai

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.getenv("AGENT_PLATFORM_LOCATION", "europe-west1")
RELEASE_OPERATOR_SA = os.getenv(
    "FIXLIST_RELEASE_OPERATOR_SERVICE_ACCOUNT",
    f"fixlist-release-operator@{PROJECT}.iam.gserviceaccount.com",
)
client = vertexai.Client(project=PROJECT, location=LOCATION)

AGENTS = {
    "crawler-research": {
        "display_name": "FixList Crawler Research Agent",
        "description": "Read-only public GitHub mining for reusable SEO crawler engineering patterns.",
        "entrypoint_module": "crawler_research_agent",
        "entrypoint_object": "crawler_research_agent",
        "source_packages": ["crawler_research_agent.py", "requirements.txt"],
        "methods": [{
            "name": "query", "api_mode": "", "parameters": {
                "type": "object",
                "properties": {
                    "queries": {"type": "array", "items": {"type": "string"}},
                    "local_root": {"type": "string"},
                    "seed_repositories": {"type": "array", "items": {"type": "string"}},
                    "max_repos": {"type": "integer"},
                },
            },
        }],
    },
    "research": {
        "display_name": "FixList Research Agent",
        "description": "Grounded research on how to improve FixList.",
        "entrypoint_module": "agents",
        "entrypoint_object": "research_agent",
        "source_packages": ["agents.py", "requirements.txt"],
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
        "entrypoint_module": "agents",
        "entrypoint_object": "claude_liaison_agent",
        "source_packages": ["agents.py", "requirements.txt"],
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
        "display_name": "FixList Release Operator",
        "description": "Autonomous operator for the allowlisted FixList Standard 150 release surface.",
        "entrypoint_module": "release_operator",
        "entrypoint_object": "release_operator",
        "source_packages": ["release_operator.py", "requirements.txt"],
        "service_account": RELEASE_OPERATOR_SA,
        "methods": [
            {"name": "inspect_release_surface", "api_mode": "", "parameters": {"type": "object", "properties": {}}},
            {"name": "inspect_cloud_run", "api_mode": "", "parameters": {"type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"]}},
            {"name": "read_logs", "api_mode": "", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "minutes": {"type": "integer"}, "limit": {"type": "integer"}, "request_id": {"type": "string"}, "scan_id": {"type": "string"}}, "required": ["service"]}},
            {"name": "inspect_build", "api_mode": "", "parameters": {"type": "object", "properties": {"build_id": {"type": "string"}}, "required": ["build_id"]}},
            {"name": "inspect_queue", "api_mode": "", "parameters": {"type": "object", "properties": {"queue": {"type": "string"}, "location": {"type": "string"}}}},
            {"name": "list_tasks", "api_mode": "", "parameters": {"type": "object", "properties": {"queue": {"type": "string"}, "location": {"type": "string"}, "name_contains": {"type": "string"}, "limit": {"type": "integer"}}}},
            {"name": "pause_queue", "api_mode": "", "parameters": {"type": "object", "properties": {"confirm": {"type": "string"}, "queue": {"type": "string"}, "location": {"type": "string"}}, "required": ["confirm"]}},
            {"name": "resume_queue", "api_mode": "", "parameters": {"type": "object", "properties": {"confirm": {"type": "string"}, "queue": {"type": "string"}, "location": {"type": "string"}}, "required": ["confirm"]}},
            {"name": "set_traffic_100", "api_mode": "", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "revision": {"type": "string"}, "confirm": {"type": "string"}}, "required": ["service", "revision", "confirm"]}},
            {"name": "export_signing_key_encrypted", "api_mode": "", "parameters": {"type": "object", "properties": {"public_key_pem": {"type": "string"}}, "required": ["public_key_pem"]}},
        ],
    },
}


def deploy(name: str):
    spec = AGENTS[name]
    config = {
        "display_name": spec["display_name"],
        "description": spec["description"],
        "source_packages": spec["source_packages"],
        "entrypoint_module": spec["entrypoint_module"],
        "entrypoint_object": spec["entrypoint_object"],
        "requirements_file": "requirements.txt",
        "class_methods": spec["methods"],
    }
    if spec.get("service_account"):
        config["service_account"] = spec["service_account"]
    remote = client.agent_engines.create(config=config)
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
