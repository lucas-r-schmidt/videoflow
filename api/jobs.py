import uuid
import json
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from models.database import Job, JobStatus, get_session
from workers.celery_app import celery_app

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


# ── Schemas ───────────────────────────────────────────────────

class JobCreate(BaseModel):
    source_type: str                  # youtube | google_drive | upload
    source_url: str | None = None
    drive_file_id: str | None = None
    cut_mode: str = "sequential"      # highlights | sequential
    part_duration: int = 60
    max_clip_duration: int = 60
    max_clips: int = 3
    platforms: list[str] = ["instagram", "tiktok"]
    subtitle_style: str = "none"   # none | simple | karaoke
    scheduled_at: int | None = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    output_files: list[str] = []
    error_message: str | None = None


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/", status_code=202, response_model=JobResponse)
async def create_job(
    payload: JobCreate,
    session: AsyncSession = Depends(get_session),
):
    job = Job(**payload.model_dump())
    session.add(job)
    await session.commit()
    await session.refresh(job)

    # Enfileira task principal no Celery
    celery_app.send_task("workers.pipeline_task.run_pipeline", args=[job.id])

    return JobResponse(job_id=job.id, status=job.status)


@router.post("/upload", status_code=202, response_model=JobResponse)
async def upload_job(
    file: UploadFile = File(...),
    cut_mode: str = Form("highlights"),
    part_duration: int = Form(60),
    max_clip_duration: int = Form(60),
    max_clips: int = Form(3),
    platforms: str = Form("[]"),
    subtitle_style: str = Form("none"),
    session: AsyncSession = Depends(get_session),
):
    """Permite upload direto de vídeo MP4 sem depender de plataformas externas."""
    job_id = str(uuid.uuid4())
    tmp_dir = Path(settings.VIDEO_TMP_DIR)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    saved_path = tmp_dir / f"{job_id}{file_ext}"

    async with aiofiles.open(saved_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):  # 1MB por vez
            await out_file.write(chunk)

    try:
        platform_list = json.loads(platforms) if isinstance(platforms, str) else []
    except Exception:
        platform_list = []

    job = Job(
        id=job_id,
        source_type="upload",
        source_url=str(saved_path),
        cut_mode=cut_mode,
        part_duration=part_duration,
        max_clip_duration=max_clip_duration,
        max_clips=max_clips,
        platforms=platform_list,
        subtitle_style=subtitle_style,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    celery_app.send_task("workers.pipeline_task.run_pipeline", args=[job.id])

    return JobResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    web_outputs = []
    if job.output_files:
        for f in job.output_files:
            fname = Path(f).name
            web_outputs.append(f"/outputs/{fname}")

    return JobResponse(
        job_id=job.id,
        status=job.status,
        output_files=web_outputs,
        error_message=job.error_message,
    )

