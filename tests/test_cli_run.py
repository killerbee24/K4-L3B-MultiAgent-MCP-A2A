from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from student_agent import cli
from student_agent.cases import CaseSet


def test_run_preserves_previous_artifacts_when_gateway_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_output = tmp_path / "outputs" / "L3B_TEST_001.json"
    old_output.parent.mkdir()
    old_output.write_text("old output", encoding="utf-8")
    old_trace = tmp_path / "traces" / "trace.jsonl"
    old_trace.parent.mkdir()
    old_trace.write_text("old trace", encoding="utf-8")
    case_set = CaseSet("test-v1", "l3b", ("L3B_TEST_001",), {"L3B_TEST_001": {}})
    monkeypatch.setattr(cli, "load_case_set", lambda root: case_set)

    async def prepare_run(settings: Any, loaded: CaseSet) -> str:
        return "https://example.test/mcp"

    monkeypatch.setattr(cli, "_prepare_run", prepare_run)
    monkeypatch.setattr(
        cli.Settings,
        "load",
        lambda root: SimpleNamespace(mcp_endpoint="https://example.test/mcp", team_api_key="test"),
    )

    @asynccontextmanager
    async def failing_gateway(*args: Any) -> Any:
        raise RuntimeError("gateway unavailable")
        yield

    monkeypatch.setattr(cli, "connect_gateway", failing_gateway)
    with pytest.raises(RuntimeError, match="gateway unavailable"):
        asyncio.run(cli._run(tmp_path))

    assert old_output.read_text(encoding="utf-8") == "old output"
    assert old_trace.read_text(encoding="utf-8") == "old trace"
    assert list(tmp_path.glob(".day09-run-*")) == []


def test_run_publishes_staged_artifacts_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = "L3B_TEST_001"
    old_output = tmp_path / "outputs" / f"{case_id}.json"
    old_output.parent.mkdir()
    old_output.write_text("old output", encoding="utf-8")
    old_trace = tmp_path / "traces" / "trace.jsonl"
    old_trace.parent.mkdir()
    old_trace.write_text("old trace", encoding="utf-8")
    case_set = CaseSet("test-v1", "l3b", (case_id,), {case_id: {"case_id": case_id}})
    monkeypatch.setattr(cli, "load_case_set", lambda root: case_set)

    async def prepare_run(settings: Any, loaded: CaseSet) -> str:
        return "https://example.test/mcp"

    monkeypatch.setattr(cli, "_prepare_run", prepare_run)
    monkeypatch.setattr(
        cli.Settings,
        "load",
        lambda root: SimpleNamespace(mcp_endpoint="https://example.test/mcp", team_api_key="test"),
    )

    class FakeContracts:
        def __init__(self, root: Path) -> None:
            pass

        def validate_trace(self, event: dict[str, Any], label: str) -> None:
            pass

        def validate_output(self, output: dict[str, Any], label: str) -> None:
            pass

    class FakeGateway:
        async def list_tools(self) -> list[str]:
            return ["get_order"]

    @asynccontextmanager
    async def working_gateway(*args: Any) -> Any:
        yield FakeGateway()

    async def fake_solve(case: dict[str, Any], gateway: Any, trace: Any) -> dict[str, Any]:
        return {"case_id": case["case_id"], "new": True}

    monkeypatch.setattr(cli, "Contracts", FakeContracts)
    monkeypatch.setattr(cli, "connect_gateway", working_gateway)
    monkeypatch.setattr(cli, "solve_case", fake_solve)
    monkeypatch.setattr(cli, "validate_artifacts", lambda *args: ({}, []))

    asyncio.run(cli._run(tmp_path))
    assert json.loads(old_output.read_text(encoding="utf-8"))["new"] is True
    assert "case_finalized" in old_trace.read_text(encoding="utf-8")


def test_prepare_run_uses_workspace_api_and_checks_case_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def post(self, url: str, **kwargs: Any) -> Any:
            requests.append({"url": url, **kwargs})
            return SimpleNamespace(
                status_code=201,
                json=lambda: {
                    "variant_id": "l3b",
                    "case_set_version": "test-v1",
                    "mcp_endpoint": "https://gateway.example.test/mcp",
                },
            )

    monkeypatch.setattr(cli.httpx2, "AsyncClient", lambda timeout: FakeClient())
    settings = SimpleNamespace(
        competition_api_url="https://competition.example.test", team_api_key="key"
    )
    case_set = CaseSet("test-v1", "l3b", (), {})
    endpoint = asyncio.run(cli._prepare_run(settings, case_set))
    assert endpoint == "https://gateway.example.test/mcp"
    assert requests == [
        {
            "url": "https://competition.example.test/api/v2/runs",
            "headers": {"Authorization": "Bearer key"},
            "json": {"variant_id": "l3b"},
        }
    ]
