from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from apps.job_prompt import compose_boss_prompt
from orchestrator.hive.controller import HiveController
from orchestrator.hive.protocol import JobMode, JobRecord, JobRequest


class CreateJobPayload(BaseModel):
    job: str
    acceptance: list[str] = Field(default_factory=list)
    mode: JobMode = JobMode.AUTO
    repo_path: str | None = None
    background: str | None = None
    offload: str | None = None
    deliverable: str | None = None


app = FastAPI(title="Hive Codex API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3010",
        "http://localhost:3010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _controller(repo_path: str | None = None) -> HiveController:
    root = Path(repo_path or Path.cwd()).resolve()
    return HiveController(root)


def _compose_prompt(payload: CreateJobPayload) -> str:
    return compose_boss_prompt(
        goal=payload.job,
        background=payload.background,
        offload=payload.offload,
        deliverable=payload.deliverable,
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobRecord)
async def create_job(payload: CreateJobPayload) -> JobRecord:
    controller = _controller(payload.repo_path)
    return await controller.run_job(
        JobRequest(
            boss_prompt=_compose_prompt(payload),
            acceptance=payload.acceptance,
            repo_path=str(Path(payload.repo_path or Path.cwd()).resolve()),
            mode=payload.mode,
        )
    )


@app.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job(job_id: str, repo_path: str | None = None) -> JobRecord:
    controller = _controller(repo_path)
    try:
        return controller.get_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str, repo_path: str | None = None) -> FileResponse:
    controller = _controller(repo_path)
    try:
        return FileResponse(controller.get_job_events_path(job_id), media_type="application/x-ndjson")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
