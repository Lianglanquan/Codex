from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response

LOGGER = logging.getLogger("repo_mcp")
logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"))


class GitHubAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _json_rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload,
        "isError": False,
    }


def _coerce_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{field}` must be an integer") from exc


@dataclass
class GitHubRepoService:
    token: str
    repository: str
    api_url: str
    allowed_repos: set[str]
    enable_write: bool

    @classmethod
    def from_env(cls) -> "GitHubRepoService":
        token = os.getenv("GITHUB_TOKEN", "").strip()
        repository = os.getenv("GITHUB_REPOSITORY", "").strip()
        if not token:
            raise RuntimeError("GITHUB_TOKEN is required")
        if not repository:
            raise RuntimeError("GITHUB_REPOSITORY is required")

        allowed = {
            item.strip()
            for item in os.getenv("MCP_ALLOWED_REPOS", repository).split(",")
            if item.strip()
        }
        return cls(
            token=token,
            repository=repository,
            api_url=os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
            allowed_repos=allowed,
            enable_write=_bool_env("MCP_ENABLE_WRITE", default=False),
        )

    def _resolve_repo(self, repo: str | None) -> str:
        target = (repo or self.repository).strip()
        if target not in self.allowed_repos:
            raise PermissionError(f"Repository `{target}` is not in MCP_ALLOWED_REPOS")
        return target

    def _request(
        self,
        method: str,
        path: str | None = None,
        *,
        repo: str | None = None,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        accept: str = "application/vnd.github+json",
        write: bool = False,
        absolute_url: str | None = None,
        raw: bool = False,
    ) -> Any:
        if write and not self.enable_write:
            raise PermissionError("Write operations are disabled. Set MCP_ENABLE_WRITE=true to allow comments.")

        target_repo = self._resolve_repo(repo)
        if absolute_url:
            url = absolute_url
        else:
            assert path is not None
            clean_path = path.lstrip("/")
            url = f"{self.api_url}/repos/{target_repo}/{clean_path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-governance-mcp/0.1.0",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, headers=headers, method=method.upper(), data=data)
        LOGGER.debug("GitHub request %s %s", method.upper(), url)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                if raw:
                    return payload
                if not payload:
                    return {}
                return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            LOGGER.warning("GitHub API error %s %s: %s", method.upper(), url, exc.code)
            raise GitHubAPIError(exc.code, f"GitHub API request failed: {exc.reason}", body_text) from exc

    def get_repo_status(self, repo: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        repo_data = self._request("GET", "", repo=target_repo)
        pulls = self._request("GET", "pulls", repo=target_repo, query={"state": "open", "per_page": 100})
        commits = self._request("GET", "commits", repo=target_repo, query={"per_page": 1})
        recent_commit = commits[0] if commits else None
        checks = self.get_checks(repo=target_repo, ref=recent_commit["sha"] if recent_commit else None)
        return {
            "repository": target_repo,
            "default_branch": repo_data.get("default_branch"),
            "open_pull_requests": len(pulls),
            "recent_commit": {
                "sha": recent_commit.get("sha"),
                "message": recent_commit.get("commit", {}).get("message"),
                "author": recent_commit.get("commit", {}).get("author", {}).get("name"),
                "date": recent_commit.get("commit", {}).get("author", {}).get("date"),
            }
            if recent_commit
            else None,
            "checks_overview": {
                "status": checks.get("status"),
                "successful": checks.get("successful_count"),
                "failing": checks.get("failing_count"),
                "pending": checks.get("pending_count"),
            },
        }

    def list_open_prs(self, repo: str | None = None, limit: int = 20) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        payload = self._request(
            "GET",
            "pulls",
            repo=target_repo,
            query={"state": "open", "sort": "updated", "direction": "desc", "per_page": limit},
        )
        return {
            "repository": target_repo,
            "pull_requests": [
                {
                    "number": item["number"],
                    "title": item["title"],
                    "state": item["state"],
                    "draft": item["draft"],
                    "author": item["user"]["login"],
                    "head": item["head"]["ref"],
                    "base": item["base"]["ref"],
                    "updated_at": item["updated_at"],
                    "url": item["html_url"],
                }
                for item in payload
            ],
        }

    def get_pr(self, pr_number: int, repo: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        pr = self._request("GET", f"pulls/{pr_number}", repo=target_repo)
        reviews = self._request("GET", f"pulls/{pr_number}/reviews", repo=target_repo, query={"per_page": 100})
        review_summary: dict[str, int] = {}
        for review in reviews:
            state = review.get("state", "UNKNOWN")
            review_summary[state] = review_summary.get(state, 0) + 1
        return {
            "repository": target_repo,
            "number": pr["number"],
            "title": pr["title"],
            "body": pr.get("body") or "",
            "author": pr["user"]["login"],
            "state": pr["state"],
            "draft": pr["draft"],
            "head": {"ref": pr["head"]["ref"], "sha": pr["head"]["sha"]},
            "base": {"ref": pr["base"]["ref"], "sha": pr["base"]["sha"]},
            "mergeable_state": pr.get("mergeable_state"),
            "changed_files": pr.get("changed_files", 0),
            "review_summary": review_summary,
            "url": pr["html_url"],
        }

    def list_changed_files(self, pr_number: int, repo: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        files = self._request("GET", f"pulls/{pr_number}/files", repo=target_repo, query={"per_page": 100})
        return {
            "repository": target_repo,
            "pr_number": pr_number,
            "files": [
                {
                    "filename": item["filename"],
                    "status": item["status"],
                    "additions": item["additions"],
                    "deletions": item["deletions"],
                    "changes": item["changes"],
                    "patch": item.get("patch"),
                }
                for item in files
            ],
        }

    def get_pr_diff(self, pr_number: int, repo: str | None = None, start: int = 0, limit: int = 20) -> dict[str, Any]:
        files = self.list_changed_files(pr_number, repo)["files"]
        slice_end = start + limit
        return {
            "pr_number": pr_number,
            "start": start,
            "limit": limit,
            "has_more": slice_end < len(files),
            "files": files[start:slice_end],
        }

    def read_file(self, path: str, repo: str | None = None, ref: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        query = {"ref": ref} if ref else None
        payload = self._request("GET", f"contents/{path}", repo=target_repo, query=query)
        if payload.get("type") != "file":
            raise ValueError(f"`{path}` is not a file")
        content = payload.get("content", "")
        decoded = base64.b64decode(content).decode("utf-8", errors="replace")
        return {
            "repository": target_repo,
            "path": path,
            "ref": ref,
            "sha": payload.get("sha"),
            "size": payload.get("size"),
            "content": decoded,
        }

    def list_recent_commits(self, repo: str | None = None, ref: str | None = None, limit: int = 10) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        query: dict[str, Any] = {"per_page": limit}
        if ref:
            query["sha"] = ref
        payload = self._request("GET", "commits", repo=target_repo, query=query)
        return {
            "repository": target_repo,
            "commits": [
                {
                    "sha": item["sha"],
                    "message": item["commit"]["message"],
                    "author": item["commit"]["author"]["name"],
                    "date": item["commit"]["author"]["date"],
                    "url": item["html_url"],
                }
                for item in payload
            ],
        }

    def get_issue(self, issue_number: int, repo: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        payload = self._request("GET", f"issues/{issue_number}", repo=target_repo)
        return {
            "repository": target_repo,
            "number": payload["number"],
            "title": payload["title"],
            "body": payload.get("body") or "",
            "state": payload["state"],
            "author": payload["user"]["login"],
            "labels": [label["name"] for label in payload.get("labels", [])],
            "is_pull_request": "pull_request" in payload,
            "url": payload["html_url"],
        }

    def _resolve_head_sha(self, repo: str | None = None, pr_number: int | None = None, ref: str | None = None) -> tuple[str, dict[str, Any] | None]:
        if pr_number is not None:
            pr = self.get_pr(pr_number, repo)
            return pr["head"]["sha"], pr
        if ref:
            return ref, None
        commits = self._request("GET", "commits", repo=repo, query={"per_page": 1})
        if not commits:
            raise ValueError("Repository has no commits to inspect")
        return commits[0]["sha"], None

    def _latest_workflow_run(self, repo: str, head_sha: str) -> dict[str, Any] | None:
        payload = self._request("GET", "actions/runs", repo=repo, query={"head_sha": head_sha, "per_page": 10})
        runs = payload.get("workflow_runs", [])
        return runs[0] if runs else None

    def get_checks(self, repo: str | None = None, pr_number: int | None = None, ref: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        head_sha, pr = self._resolve_head_sha(target_repo, pr_number=pr_number, ref=ref)
        payload = self._request("GET", f"commits/{head_sha}/check-runs", repo=target_repo, query={"per_page": 100})
        check_runs = payload.get("check_runs", [])
        latest_run = self._latest_workflow_run(target_repo, head_sha)
        failed_jobs: list[dict[str, Any]] = []

        if latest_run:
            jobs_payload = self._request(
                "GET",
                f"actions/runs/{latest_run['id']}/jobs",
                repo=target_repo,
                query={"per_page": 100},
            )
            for job in jobs_payload.get("jobs", []):
                if job.get("conclusion") not in {None, "success", "skipped", "neutral"}:
                    failed_steps = [
                        step["name"]
                        for step in job.get("steps", [])
                        if step.get("conclusion") not in {None, "success", "skipped"}
                    ]
                    failed_jobs.append(
                        {
                            "name": job["name"],
                            "status": job["status"],
                            "conclusion": job.get("conclusion"),
                            "failed_steps": failed_steps,
                            "details_url": job.get("html_url"),
                        }
                    )

        pending_count = 0
        failing_count = 0
        successful_count = 0
        for check in check_runs:
            conclusion = check.get("conclusion")
            status = check.get("status")
            if status != "completed" or conclusion is None:
                pending_count += 1
            elif conclusion in {"success", "neutral", "skipped"}:
                successful_count += 1
            else:
                failing_count += 1

        overall_status = "success"
        if failing_count or failed_jobs:
            overall_status = "failure"
        elif pending_count:
            overall_status = "pending"

        return {
            "repository": target_repo,
            "pr_number": pr_number,
            "head_sha": head_sha,
            "status": overall_status,
            "successful_count": successful_count,
            "failing_count": failing_count + len(failed_jobs),
            "pending_count": pending_count,
            "latest_workflow_run": {
                "id": latest_run["id"],
                "name": latest_run["name"],
                "status": latest_run["status"],
                "conclusion": latest_run.get("conclusion"),
                "url": latest_run["html_url"],
            }
            if latest_run
            else None,
            "check_runs": [
                {
                    "name": check["name"],
                    "status": check["status"],
                    "conclusion": check.get("conclusion"),
                    "started_at": check.get("started_at"),
                    "completed_at": check.get("completed_at"),
                    "details_url": check.get("details_url"),
                }
                for check in check_runs
            ],
            "failed_jobs": failed_jobs,
            "pr": pr,
        }

    def get_test_summary(self, repo: str | None = None, pr_number: int | None = None, ref: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        head_sha, _ = self._resolve_head_sha(target_repo, pr_number=pr_number, ref=ref)
        workflow_run = self._latest_workflow_run(target_repo, head_sha)
        if not workflow_run:
            return {
                "repository": target_repo,
                "available": False,
                "message": "No workflow run was found for the requested ref.",
            }

        artifacts = self._request("GET", f"actions/runs/{workflow_run['id']}/artifacts", repo=target_repo, query={"per_page": 100})
        match = next((item for item in artifacts.get("artifacts", []) if item.get("name") == "ci-test-summary"), None)
        if not match:
            return {
                "repository": target_repo,
                "available": False,
                "message": "Artifact `ci-test-summary` was not found. Confirm the test job uploaded it.",
                "workflow_run_id": workflow_run["id"],
            }

        archive = self._request(
            "GET",
            repo=target_repo,
            absolute_url=match["archive_download_url"],
            raw=True,
            accept="application/vnd.github+json",
        )
        with zipfile.ZipFile(BytesIO(archive)) as zip_file:
            file_name = next((name for name in zip_file.namelist() if name.endswith("test-summary.json")), None)
            if file_name is None:
                raise ValueError("Artifact `ci-test-summary` does not contain `test-summary.json`")
            with zip_file.open(file_name) as handle:
                summary = json.loads(handle.read().decode("utf-8"))
        summary["repository"] = target_repo
        summary["workflow_run_id"] = workflow_run["id"]
        summary["workflow_url"] = workflow_run["html_url"]
        summary["available"] = True
        return summary

    def review_pr(
        self,
        pr_number: int,
        repo: str | None = None,
        boss_goal: str | None = None,
        acceptance: list[str] | None = None,
    ) -> dict[str, Any]:
        pr = self.get_pr(pr_number, repo)
        files = self.list_changed_files(pr_number, repo)["files"]
        checks = self.get_checks(repo=repo, pr_number=pr_number)
        findings: list[dict[str, Any]] = []
        completed = [
            f"PR metadata is available for #{pr_number}",
            f"{len(files)} changed files are visible to review",
        ]
        missing: list[str] = []

        if checks["status"] != "success":
            findings.append(
                {
                    "severity": "high",
                    "category": "tests-and-release",
                    "title": "Checks are not green",
                    "evidence": {"status": checks["status"], "failed_jobs": checks["failed_jobs"]},
                    "fix_guidance": "Resolve failing or pending CI jobs before merge and rerun review on the latest head SHA.",
                }
            )

        forbidden = [item["filename"] for item in files if item["filename"].startswith(".agents/") or item["filename"].startswith(".codex/")]
        if forbidden:
            findings.append(
                {
                    "severity": "high",
                    "category": "scope",
                    "title": "Forbidden control files were modified",
                    "evidence": {"files": forbidden},
                    "fix_guidance": "Revert `.agents/` / `.codex/` changes unless the task explicitly authorizes them.",
                }
            )

        code_changed = any(
            item["filename"].startswith(("apps/", "orchestrator/", "mcp-server/")) and not item["filename"].endswith(".md")
            for item in files
        )
        tests_changed = any(item["filename"].startswith("tests/") for item in files)
        body = (pr.get("body") or "").lower()
        has_test_gap_note = "无法补测试" in body or "test gap" in body or "no test" in body
        if code_changed and not tests_changed and not has_test_gap_note:
            findings.append(
                {
                    "severity": "medium",
                    "category": "code-quality",
                    "title": "Code changed without test evidence or explanation",
                    "evidence": {"changed_files": [item["filename"] for item in files]},
                    "fix_guidance": "Add or update tests, or explain why tests cannot be added and how the gap was validated.",
                }
            )
            missing.append("Test additions or a written test gap explanation")

        ui_changed = any(item["filename"].startswith("apps/web/") for item in files)
        if ui_changed and not (("移动端" in pr["body"] or "mobile" in body) and ("桌面端" in pr["body"] or "desktop" in body)):
            findings.append(
                {
                    "severity": "medium",
                    "category": "ui-ux",
                    "title": "UI verification does not mention desktop and mobile coverage",
                    "evidence": {"pr_body": pr["body"]},
                    "fix_guidance": "Update the PR description with desktop and mobile verification notes for the UI change.",
                }
            )
            missing.append("Desktop/mobile verification note")

        if not all(keyword in pr["body"] for keyword in ["改了什么", "为什么改", "风险点", "如何验证"]):
            findings.append(
                {
                    "severity": "medium",
                    "category": "delivery",
                    "title": "PR description is incomplete",
                    "evidence": {"body": pr["body"]},
                    "fix_guidance": "Fill in the PR template sections for what changed, why, risks, and validation.",
                }
            )
            missing.append("Complete PR template fields")

        recommendation = "approve" if not findings else "request_changes"
        risk_level = "low" if not findings else "medium"
        if any(item["severity"] == "high" for item in findings):
            risk_level = "high"

        return {
            "repository": pr["repository"],
            "pr_number": pr_number,
            "boss_goal": boss_goal,
            "acceptance": acceptance or [],
            "completed": completed,
            "missing": missing,
            "findings": findings,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "categories": {
                "requirement_completion": "pass" if not missing else "partial",
                "code_quality": "pass" if not any(f["category"] == "code-quality" for f in findings) else "needs-work",
                "ui_ux_quality": "pass" if not any(f["category"] == "ui-ux" for f in findings) else "needs-work",
                "risk_and_regression": "pass" if checks["status"] == "success" else "blocked",
                "tests_and_release": "pass" if checks["status"] == "success" else "blocked",
                "merge_recommendation": recommendation,
            },
        }

    def request_changes(
        self,
        pr_number: int,
        repo: str | None = None,
        boss_goal: str | None = None,
        acceptance: list[str] | None = None,
    ) -> dict[str, Any]:
        review = self.review_pr(pr_number, repo=repo, boss_goal=boss_goal, acceptance=acceptance)
        actions = [
            {
                "title": finding["title"],
                "severity": finding["severity"],
                "evidence": finding["evidence"],
                "required_fix": finding["fix_guidance"],
            }
            for finding in review["findings"]
        ]
        return {
            "repository": review["repository"],
            "pr_number": pr_number,
            "status": "changes_requested" if actions else "no_changes_requested",
            "merge_blocked": bool(actions),
            "required_actions": actions,
            "recommendation": review["recommendation"],
        }

    def post_pr_comment(self, pr_number: int, body: str, repo: str | None = None) -> dict[str, Any]:
        target_repo = self._resolve_repo(repo)
        if not body.strip():
            raise ValueError("`body` must not be empty")
        payload = self._request(
            "POST",
            f"issues/{pr_number}/comments",
            repo=target_repo,
            body={"body": body},
            write=True,
        )
        return {
            "repository": target_repo,
            "pr_number": pr_number,
            "comment_id": payload["id"],
            "url": payload["html_url"],
        }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_repo_status",
        "description": "Return the default branch, current open PR count, latest commit, and overall check status.",
        "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "list_open_prs",
        "description": "List open pull requests ordered by most recently updated.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_pr",
        "description": "Return PR metadata, branch info, state, and review summary.",
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string"}, "pr_number": {"type": "integer"}},
            "required": ["pr_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_pr_diff",
        "description": "Return paginated changed-file diff summaries for a PR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "start": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["pr_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_changed_files",
        "description": "Return changed files and their statuses for a PR.",
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string"}, "pr_number": {"type": "integer"}},
            "required": ["pr_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the repository at a given ref.",
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string"}, "path": {"type": "string"}, "ref": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_checks",
        "description": "Return CI/check-run status and failing-job summaries for a PR or ref.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "ref": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_test_summary",
        "description": "Return test totals, failures, coverage availability, and key error excerpts from the CI artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "ref": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "review_pr",
        "description": "Generate a structured review summary for a PR using repository rules and current checks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "boss_goal": {"type": "string"},
                "acceptance": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["pr_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "request_changes",
        "description": "Produce a structured rework order for a PR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "boss_goal": {"type": "string"},
                "acceptance": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["pr_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_recent_commits",
        "description": "Return recent commits for the repository or a branch/ref.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "ref": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_issue",
        "description": "Return issue metadata and body for a repository issue.",
        "inputSchema": {
            "type": "object",
            "properties": {"repo": {"type": "string"}, "issue_number": {"type": "integer"}},
            "required": ["issue_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "post_pr_comment",
        "description": "Post a PR comment when write mode is explicitly enabled.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
                "body": {"type": "string"},
            },
            "required": ["pr_number", "body"],
            "additionalProperties": False,
        },
    },
]


def _call_tool(service: GitHubRepoService, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    repo = arguments.get("repo")
    if name == "get_repo_status":
        return service.get_repo_status(repo=repo)
    if name == "list_open_prs":
        return service.list_open_prs(repo=repo, limit=_coerce_int(arguments.get("limit", 20), field="limit"))
    if name == "get_pr":
        return service.get_pr(_coerce_int(arguments.get("pr_number"), field="pr_number"), repo=repo)
    if name == "get_pr_diff":
        return service.get_pr_diff(
            _coerce_int(arguments.get("pr_number"), field="pr_number"),
            repo=repo,
            start=_coerce_int(arguments.get("start", 0), field="start"),
            limit=_coerce_int(arguments.get("limit", 20), field="limit"),
        )
    if name == "list_changed_files":
        return service.list_changed_files(_coerce_int(arguments.get("pr_number"), field="pr_number"), repo=repo)
    if name == "read_file":
        path = str(arguments.get("path", "")).strip()
        if not path:
            raise ValueError("`path` is required")
        return service.read_file(path=path, repo=repo, ref=arguments.get("ref"))
    if name == "get_checks":
        return service.get_checks(
            repo=repo,
            pr_number=_coerce_int(arguments["pr_number"], field="pr_number") if "pr_number" in arguments else None,
            ref=arguments.get("ref"),
        )
    if name == "get_test_summary":
        return service.get_test_summary(
            repo=repo,
            pr_number=_coerce_int(arguments["pr_number"], field="pr_number") if "pr_number" in arguments else None,
            ref=arguments.get("ref"),
        )
    if name == "review_pr":
        acceptance = arguments.get("acceptance") or []
        return service.review_pr(
            _coerce_int(arguments.get("pr_number"), field="pr_number"),
            repo=repo,
            boss_goal=arguments.get("boss_goal"),
            acceptance=[str(item) for item in acceptance],
        )
    if name == "request_changes":
        acceptance = arguments.get("acceptance") or []
        return service.request_changes(
            _coerce_int(arguments.get("pr_number"), field="pr_number"),
            repo=repo,
            boss_goal=arguments.get("boss_goal"),
            acceptance=[str(item) for item in acceptance],
        )
    if name == "list_recent_commits":
        return service.list_recent_commits(
            repo=repo,
            ref=arguments.get("ref"),
            limit=_coerce_int(arguments.get("limit", 10), field="limit"),
        )
    if name == "get_issue":
        return service.get_issue(_coerce_int(arguments.get("issue_number"), field="issue_number"), repo=repo)
    if name == "post_pr_comment":
        body = str(arguments.get("body", "")).strip()
        if not body:
            raise ValueError("`body` is required")
        return service.post_pr_comment(
            _coerce_int(arguments.get("pr_number"), field="pr_number"),
            body=body,
            repo=repo,
        )
    raise ValueError(f"Unknown tool `{name}`")


def create_app(service_factory: Callable[[], GitHubRepoService] | None = None) -> FastAPI:
    app = FastAPI(title="Repo Governance MCP", version="0.1.0")
    app.state.service_factory = service_factory or GitHubRepoService.from_env

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"name": "repo-governance-mcp", "status": "ok"}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc.msg}") from exc

        def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params") or {}
            LOGGER.info("MCP method=%s", method)

            if not method:
                return _json_rpc_error(request_id, -32600, "Missing method")
            if method.startswith("notifications/"):
                return None
            if method == "initialize":
                return _json_rpc_result(
                    request_id,
                    {
                        "protocolVersion": os.getenv("MCP_PROTOCOL_VERSION", "2025-11-25"),
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "repo-governance-mcp", "version": "0.1.0"},
                    },
                )
            if method == "ping":
                return _json_rpc_result(request_id, {})
            if method == "tools/list":
                return _json_rpc_result(request_id, {"tools": TOOL_DEFINITIONS})
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not name:
                    return _json_rpc_error(request_id, -32602, "Missing tool name")
                try:
                    service = app.state.service_factory()
                    result = _call_tool(service, name, arguments)
                    return _json_rpc_result(request_id, _tool_result(result))
                except PermissionError as exc:
                    return _json_rpc_error(request_id, -32001, str(exc))
                except (ValueError, RuntimeError) as exc:
                    return _json_rpc_error(request_id, -32602, str(exc))
                except GitHubAPIError as exc:
                    return _json_rpc_error(
                        request_id,
                        -32010,
                        str(exc),
                        data={"status_code": exc.status_code, "body": exc.body},
                    )
            return _json_rpc_error(request_id, -32601, f"Method `{method}` is not supported")

        if isinstance(payload, list):
            responses = [handle_message(message) for message in payload]
            cleaned = [item for item in responses if item is not None]
            if not cleaned:
                return Response(status_code=202)
            return Response(content=json.dumps(cleaned, ensure_ascii=False), media_type="application/json")

        response = handle_message(payload)
        if response is None:
            return Response(status_code=202)
        return Response(content=json.dumps(response, ensure_ascii=False), media_type="application/json")

    return app


app = create_app()
