"""The offline scaling probe sizes evidence explicitly and never fetches it."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("benchmark_review", Path(__file__).parents[1] / "benchmark_review.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_synthetic_evidence_has_distinct_pages_and_multiple_sections():
    payload = benchmark.synthetic_payload(500)
    assert payload["pages_crawled"] == payload["pages_found"] == 500
    assert len({page["url"] for page in payload["pages"]}) == 500
    assert {page["path"].split("/")[1] for page in payload["pages"]} == {"solutions", "products", "insights", "stores"}
    assert all(page["url"].startswith("https://benchmark.example/") for page in payload["pages"])


def test_timeout_is_reported_as_failed_measurement(monkeypatch):
    def timeout(*args, **kwargs):
        raise benchmark.subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(benchmark.subprocess, "run", timeout)
    assert benchmark.benchmark([500], 0.01) == [{"pages": 500, "success": False,
            "within_wall_timeout": False, "error": "review_process_wall_timeout"}]


@pytest.mark.parametrize("size", [0, -1, 5001])
def test_benchmark_does_not_allocate_unbounded_synthetic_input(size):
    with pytest.raises(ValueError):
        benchmark.synthetic_payload(size)
