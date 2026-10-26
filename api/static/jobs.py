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
from models.user import User
from api.jwt_auth import get_current_user
from workers.celery_app import celery_app

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


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
    aspect_mode: str = "fill"      # fill | blur
    enable_hook: bool = True
    hook_text: str | None = None
    publish_mode: str = "shareNow" # shareNow | addToQueue | scheduled
    due_at: str | None = None      # ISO 8601 UTC string (ex: "2026-10-15T18:00:00Z")
    scheduled_at: int | None = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    output_files: list[str] = []
    error_message: str | None = None
    hook_text: str | None = None
    generated_title: str | None = None
    publish_mode: str = "shareNow"
    due_at: str | None = None


# ── Endpoints ─────────────────────────────────────────────────

@router.get("", response_model=list[JobResponse])
@router.get("/", response_model=list[JobResponse])
async def list_jobs(
    limit: int = 20,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista os jobs recentes do usuário autenticado."""
    query = (
        select(Job)
        .where((Job.user_id == user.id) | (Job.user_id.is_(None)))
        .order_by(Job.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    jobs = result.scalars().all()
    resp = []
    for job in jobs:
        web_outputs = []
        if job.output_files:
            for f in job.output_files:
                web_outputs.append(f"/outputs/{Path(f).name}")
        resp.append(
            JobResponse(
                job_id=job.id,
                status=job.status,
                output_files=web_outputs,
                error_message=job.error_message,
                hook_text=getattr(job, "hook_text", None),
                generated_title=getattr(job, "generated_title", None),
                publish_mode=getattr(job, "publish_mode", "shareNow"),
                due_at=getattr(job, "due_at", None),
            )
        )
    return resp


@router.post("", status_code=202, response_model=JobResponse)
@router.post("/", status_code=202, response_model=JobResponse)
async def create_job(
    payload: JobCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    job_data = payload.model_dump()
    job_data["user_id"] = user.id
    job = Job(**job_data)
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
    aspect_mode: str = Form("fill"),
    enable_hook: bool = Form(True),
    hook_text: str | None = Form(None),
    publish_mode: str = Form("shareNow"),
    due_at: str | None = Form(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Permite upload direto de vídeo com limite de tamanho e validação de extensão."""
    file_ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de vídeo não suportado ({file_ext}). Permitidos: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}"
        )

    job_id = str(uuid.uuid4())
    tmp_dir = Path(settings.VIDEO_TMP_DIR)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    saved_path = tmp_dir / f"{job_id}{file_ext}"

    max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 500 * 1024 * 1024)
    total_bytes = 0

    try:
        async with aiofiles.open(saved_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):  # 1MB por vez
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    await out_file.close()
                    saved_path.unlink(missing_ok=True)
                    max_mb = max_bytes // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Arquivo excede o tamanho máximo permitido de {max_mb} MB."
                    )
                await out_file.write(chunk)
    except Exception:
        if saved_path.exists():
            saved_path.unlink(missing_ok=True)
        raise

    try:
        platform_list = json.loads(platforms) if isinstance(platforms, str) else []
    except Exception:
        platform_list = []

    job = Job(
        id=job_id,
        user_id=user.id,
        source_type="upload",
        source_url=str(saved_path),
        cut_mode=cut_mode,
        part_duration=part_duration,
        max_clip_duration=max_clip_duration,
        max_clips=max_clips,
        platforms=platform_list,
        subtitle_style=subtitle_style,
        aspect_mode=aspect_mode,
        enable_hook=enable_hook,
        hook_text=hook_text,
        publish_mode=publish_mode,
        due_at=due_at,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    celery_app.send_task("workers.pipeline_task.run_pipeline", args=[job.id])

    return JobResponse(
        job_id=job.id,
        status=job.status,
        publish_mode=job.publish_mode,
        due_at=job.due_at,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    # Verifica isolamento de tenant se job possuir dono
    if job.user_id and job.user_id != user.id:
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
        hook_text=getattr(job, "hook_text", None),
        generated_title=getattr(job, "generated_title", None),
        publish_mode=getattr(job, "publish_mode", "shareNow"),
        due_at=getattr(job, "due_at", None),
    )

