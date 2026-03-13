from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-server"))

from server import create_app  # noqa: E402


class FakeService:
    def get_repo_status(self, repo: str | None = None) -> dict[str, object]:
        return {"repository": repo or "owner/repo", "default_branch": "main", "open_pull_requests": 2}

    def list_open_prs(self, repo: str | None = None, limit: int = 20) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "pull_requests": [{"number": 7, "title": "Docs refresh", "state": "open"}][:limit],
        }

    def get_pr(self, pr_number: int, repo: str | None = None) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "number": pr_number,
            "title": "Add manager docs",
            "body": "改了什么\n为什么改\n风险点\n如何验证",
            "author": "codex",
            "state": "open",
            "draft": False,
            "head": {"ref": "codex/demo", "sha": "abc123"},
            "base": {"ref": "main", "sha": "def456"},
        }

    def list_changed_files(self, pr_number: int, repo: str | None = None) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "pr_number": pr_number,
            "files": [
                {"filename": "docs/chatgpt-connect.md", "status": "modified", "additions": 10, "deletions": 1, "changes": 11},
                {"filename": "tests/test_mcp_server.py", "status": "added", "additions": 50, "deletions": 0, "changes": 50},
            ],
        }

    def get_pr_diff(self, pr_number: int, repo: str | None = None, start: int = 0, limit: int = 20) -> dict[str, object]:
        files = self.list_changed_files(pr_number, repo)["files"]
        return {"pr_number": pr_number, "start": start, "limit": limit, "has_more": False, "files": files[start : start + limit]}

    def read_file(self, path: str, repo: str | None = None, ref: str | None = None) -> dict[str, object]:
        return {"repository": repo or "owner/repo", "path": path, "ref": ref, "content": "# sample"}

    def get_checks(self, repo: str | None = None, pr_number: int | None = None, ref: str | None = None) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "pr_number": pr_number,
            "head_sha": ref or "abc123",
            "status": "success",
            "successful_count": 4,
            "failing_count": 0,
            "pending_count": 0,
            "check_runs": [{"name": "lint", "conclusion": "success"}],
            "failed_jobs": [],
        }

    def get_test_summary(self, repo: str | None = None, pr_number: int | None = None, ref: str | None = None) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "available": True,
            "status": "success",
            "tests": {"total": 12, "failures": 0, "errors": 0, "skipped": 0, "passed": 12},
            "coverage": {"available": False},
        }

    def review_pr(
        self,
        pr_number: int,
        repo: str | None = None,
        boss_goal: str | None = None,
        acceptance: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "pr_number": pr_number,
            "boss_goal": boss_goal,
            "acceptance": acceptance or [],
            "completed": ["Docs updated"],
            "missing": [],
            "findings": [],
            "risk_level": "low",
            "recommendation": "approve",
            "categories": {"merge_recommendation": "approve"},
        }

    def request_changes(
        self,
        pr_number: int,
        repo: str | None = None,
        boss_goal: str | None = None,
        acceptance: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "repository": repo or "owner/repo",
            "pr_number": pr_number,
            "status": "changes_requested",
            "merge_blocked": True,
            "required_actions": [{"title": "Add failure troubleshooting"}],
            "recommendation": "request_changes",
        }

    def list_recent_commits(self, repo: str | None = None, ref: str | None = None, limit: int = 10) -> dict[str, object]:
        return {"repository": repo or "owner/repo", "commits": [{"sha": "abc123", "message": "docs: add connect guide"}][:limit]}

    def get_issue(self, issue_number: int, repo: str | None = None) -> dict[str, object]:
        return {"repository": repo or "owner/repo", "number": issue_number, "title": "Boss request", "state": "open"}

    def post_pr_comment(self, pr_number: int, body: str, repo: str | None = None) -> dict[str, object]:
        return {"repository": repo or "owner/repo", "pr_number": pr_number, "comment_id": 99, "url": "https://example.invalid"}


def _client() -> TestClient:
    return TestClient(create_app(service_factory=lambda: FakeService()))


def test_initialize() -> None:
    client = _client()
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "pytest", "version": "1.0"}},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["serverInfo"]["name"] == "repo-governance-mcp"
    assert payload["result"]["capabilities"]["tools"]["listChanged"] is False


def test_tools_list_exposes_required_tools() -> None:
    client = _client()
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert response.status_code == 200
    tools = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "get_repo_status" in tools
    assert "review_pr" in tools
    assert "post_pr_comment" in tools


def test_tools_call_returns_structured_json() -> None:
    client = _client()
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_pr", "arguments": {"pr_number": 7}},
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["isError"] is False
    assert payload["structuredContent"]["number"] == 7
    assert "Add manager docs" in payload["content"][0]["text"]


def test_review_and_request_changes_tools() -> None:
    client = _client()
    review = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "review_pr",
                "arguments": {"pr_number": 7, "boss_goal": "Keep docs simple", "acceptance": ["One-page guide"]},
            },
        },
    )
    request_changes = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "request_changes", "arguments": {"pr_number": 7}},
        },
    )

    assert review.status_code == 200
    assert review.json()["result"]["structuredContent"]["recommendation"] == "approve"
    assert request_changes.status_code == 200
    assert request_changes.json()["result"]["structuredContent"]["merge_blocked"] is True
