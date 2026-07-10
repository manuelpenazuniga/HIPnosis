"""tests/test_api.py — L6 tests for the FastAPI HTTP layer.

These tests drive the app through ``fastapi.testclient.TestClient`` (no
real socket, no uvicorn). Each test builds a fresh app via
``create_app()`` so it gets its own ``InMemoryRunStore``; the resolver
``app.api.trace_path_for_run`` is monkey-patched to point at a temp
trace directory, so nothing in the test ever touches the real
``workspaces/`` tree on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app.main import create_app
from core.trace import TraceWriter


@pytest.fixture
def client() -> TestClient:
    """A TestClient wrapping a fresh app with its own in-memory store."""
    return TestClient(create_app())


def test_healthz_returns_ok_and_mode(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # mode = oracle_mode efectivo; en tests depende del entorno, solo debe existir.
    assert isinstance(body["mode"], str)


def test_post_runs_creates_queued_run_with_run_prefix_id(client: TestClient) -> None:
    resp = client.post("/runs", json={"repo_url": "https://example.com/repo.git"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"].startswith("run_")
    assert len(body["id"]) == len("run_") + 8
    assert body["repo_url"] == "https://example.com/repo.git"
    assert body["state"] == "QUEUED"
    # INV-8: field names from schemas are preserved end-to-end.
    assert "budgets" in body and "counters" in body
    assert body["budgets"]["max_iterations"] >= 1
    assert body["counters"]["errors_initial"] == 0


def test_post_runs_rejects_empty_repo_url(client: TestClient) -> None:
    resp = client.post("/runs", json={"repo_url": ""})
    assert resp.status_code == 422


def test_post_runs_allowlist_rejects_unlisted_repo() -> None:
    """P0.12: con una allowlist no vacía, un repo fuera de ella da 403 y NO se crea."""
    from dataclasses import replace
    app = create_app()
    app.state.config = replace(app.state.config, repo_allowlist=("github.com/me/bsw-cuda",))
    c = TestClient(app)

    bad = c.post("/runs", json={"repo_url": "https://github.com/evil/malware"})
    assert bad.status_code == 403
    assert c.get("/runs").json() == [], "un repo rechazado no debe crear run"

    ok = c.post("/runs", json={"repo_url": "https://github.com/me/bsw-cuda"})
    assert ok.status_code == 200


def test_post_runs_empty_allowlist_allows_any_repo(client: TestClient) -> None:
    """Allowlist vacía (default dev/mock) = sin restricción."""
    resp = client.post("/runs", json={"repo_url": "https://github.com/anyone/anything"})
    assert resp.status_code == 200


def test_get_run_returns_created_run(client: TestClient) -> None:
    created = client.post("/runs", json={"repo_url": "https://x/y"}).json()
    run_id = created["id"]

    fetched = client.get(f"/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_get_run_unknown_id_returns_404(client: TestClient) -> None:
    resp = client.get("/runs/run_doesnotex")
    assert resp.status_code == 404


def test_list_runs_returns_all_created(client: TestClient) -> None:
    a = client.post("/runs", json={"repo_url": "https://a/a"}).json()
    b = client.post("/runs", json={"repo_url": "https://b/b"}).json()

    listed = client.get("/runs").json()
    ids = {r["id"] for r in listed}
    assert {a["id"], b["id"]}.issubset(ids)
    # All entries must still be QUEUED right after creation (no phase ran).
    assert {r["state"] for r in listed} == {"QUEUED"}


def test_events_returns_written_trace_with_index_keys(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = client.post("/runs", json={"repo_url": "https://x/y"}).json()
    run_id = run["id"]

    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(str(trace_path), run_id)
    writer.emit("phase", phase="QUEUED")
    writer.emit("phase", phase="CLONING")
    writer.emit("build", iteration=1, errors=4, delta=-2)

    monkeypatch.setattr(
        api_module, "trace_path_for_run", lambda rid: str(trace_path)
    )

    resp = client.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert [e["_i"] for e in events] == [0, 1, 2]
    assert [e["ev"] for e in events] == ["phase", "phase", "build"]
    assert events[2]["iteration"] == 1


def test_events_after_filters_past_line_index(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = client.post("/runs", json={"repo_url": "https://x/y"}).json()
    run_id = run["id"]

    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(str(trace_path), run_id)
    writer.emit("phase", phase="QUEUED")
    writer.emit("phase", phase="CLONING")
    writer.emit("build", iteration=1, errors=4, delta=-2)

    monkeypatch.setattr(
        api_module, "trace_path_for_run", lambda rid: str(trace_path)
    )

    tail = client.get(f"/runs/{run_id}/events?after=0").json()
    assert [e["_i"] for e in tail] == [1, 2]
    assert tail[0]["ev"] == "phase" and tail[0]["phase"] == "CLONING"
    assert tail[1]["ev"] == "build"

    nothing_left = client.get(f"/runs/{run_id}/events?after=2").json()
    assert nothing_left == []


def test_events_missing_trace_returns_empty_list_with_200(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run whose trace has not been written yet must yield ``[]`` and
    ``200`` so the dashboard can poll a freshly-created run without
    404-loops before the first ``emit``."""
    run = client.post("/runs", json={"repo_url": "https://x/y"}).json()
    run_id = run["id"]

    # Resolver points to a path that does NOT exist on disk.
    monkeypatch.setattr(
        api_module,
        "trace_path_for_run",
        lambda rid: str(tmp_path / "nope" / "trace.jsonl"),
    )

    resp = client.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    assert resp.json() == []


def test_events_unknown_run_returns_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api_module,
        "trace_path_for_run",
        lambda rid: str(tmp_path / "trace.jsonl"),
    )
    resp = client.get("/runs/run_nope/events")
    assert resp.status_code == 404


def test_post_runs_does_not_execute_pipeline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-3: ``POST /runs`` only enqueues. No phase, no LLM, no build is
    triggered. We assert that by checking the run's state stays at
    ``QUEUED`` and that nothing from the forbidden layers is imported.
    """
    created = client.post("/runs", json={"repo_url": "https://x/y"}).json()
    assert created["state"] == "QUEUED"

    # Forbidden-imports guard (AD-3): keep the HTTP layer off phases/oracle.
    import app.api as api_mod  # noqa: PLC0415
    import app.main as main_mod  # noqa: PLC0415
    for mod in (api_mod, main_mod):
        for name in dir(mod):
            if name.startswith("__"):
                continue
            obj = getattr(mod, name)
            module = getattr(obj, "__module__", "") or ""
            assert "phases" not in module, f"{mod.__name__}.{name} pulls in phases"
            assert ".oracle" not in module and not module.endswith("oracle"), (
                f"{mod.__name__}.{name} pulls in oracle"
            )


def test_diff_and_certificate_endpoints_serve_demo_fallback():
    """Sin workspace (modo replay), /diff y /certificate sirven el demo bundleado."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    c = TestClient(create_app(autorun=False))
    d = c.get("/runs/anyrun/diff")
    assert d.status_code == 200 and "diff" in d.json()
    assert "hipMalloc" in d.json()["diff"] or "hip_runtime" in d.json()["diff"]
    cert = c.get("/runs/anyrun/certificate")
    assert cert.status_code == 200 and "markdown" in cert.json()
    assert "PASS" in cert.json()["markdown"]
