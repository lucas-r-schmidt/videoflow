import uuid
import json
import aiofiles
import structlog
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from models.database import Job, JobStatus, get_session
from models.user import User
from api.jwt_auth import get_current_user
from workers.celery_app import celery_app

logger = structlog.get_logger()
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
    split_long_clips: bool = True
    jump_cut: bool = True
    platforms: list[str] = ["instagram", "tiktok"]
    subtitle_style: str = "none"   # none | simple | karaoke
    aspect_mode: str = "fill"      # fill | blur | split
    niche_preset: str = "general"  # general | emotional | debate
    enable_hook: bool = True
    hook_text: str | None = None
    publish_mode: str = "shareNow" # shareNow | addToQueue | scheduled | draft
    due_at: str | None = None      # ISO 8601 UTC string (ex: "2026-10-15T18:00:00Z")
    scheduled_at: int | None = None
    requires_approval: bool = True # Modo Human-in-the-Loop por padrão para segurança


class JobResponse(BaseModel):
    job_id: str
    status: str
    output_files: list[str] = []
    error_message: str | None = None
    hook_text: str | None = None
    generated_title: str | None = None
    generated_caption: str | None = None
    publish_mode: str = "shareNow"
    due_at: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    cut_mode: str | None = None
    subtitle_style: str | None = None
    aspect_mode: str | None = None
    niche_preset: str | None = "general"
    max_clip_duration: int | None = None
    platforms: list[str] = []
    created_at: str | None = None

    # Governança e aprovação
    channel_name: str | None = None
    channel_handle: str | None = None
    requires_approval: bool = True
    approval_status: str | None = "pending"


def _serialize_job(job: Job) -> JobResponse:
    web_outputs = []
    if job.output_files:
        for f in job.output_files:
            web_outputs.append(f"/outputs/{Path(f).name}")
    created_iso = None
    if getattr(job, "created_at", None):
        created_iso = job.created_at.isoformat() + ("Z" if not job.created_at.tzinfo else "")
    return JobResponse(
        job_id=job.id,
        status=job.status,
        output_files=web_outputs,
        error_message=job.error_message,
        hook_text=getattr(job, "hook_text", None),
        generated_title=getattr(job, "generated_title", None),
        generated_caption=getattr(job, "generated_caption", None),
        publish_mode=getattr(job, "publish_mode", "shareNow") or "shareNow",
        due_at=getattr(job, "due_at", None),
        source_type=getattr(job, "source_type", None),
        source_url=getattr(job, "source_url", None) or getattr(job, "drive_file_id", None),
        cut_mode=getattr(job, "cut_mode", None),
        subtitle_style=getattr(job, "subtitle_style", None),
        aspect_mode=getattr(job, "aspect_mode", None),
        niche_preset=getattr(job, "niche_preset", "general") or "general",
        max_clip_duration=getattr(job, "max_clip_duration", None),
        platforms=getattr(job, "platforms", None) or [],
        created_at=created_iso,
        channel_name=getattr(job, "channel_name", None),
        channel_handle=getattr(job, "channel_handle", None),
        requires_approval=getattr(job, "requires_approval", True) if getattr(job, "requires_approval", None) is not None else True,
        approval_status=getattr(job, "approval_status", "pending") or "pending",
    )


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
    return [_serialize_job(job) for job in jobs]


@router.post("", status_code=202, response_model=JobResponse)
@router.post("/", status_code=202, response_model=JobResponse)
async def create_job(
    payload: JobCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    job_data = payload.model_dump()

    # Pre-flight Check: Whitelist de canais autorizados e carência mínima
    if payload.source_type == "youtube" and payload.source_url:
        from services.downloader import probe_youtube_metadata, check_channel_authorization
        try:
            metadata = probe_youtube_metadata(payload.source_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        is_auth, reason, matched_ch = await check_channel_authorization(metadata, session)
        if not is_auth:
            raise HTTPException(status_code=400, detail=reason)

        job_data["channel_name"] = metadata.get("channel_name")
        job_data["channel_id"] = metadata.get("channel_id")
        job_data["channel_handle"] = metadata.get("channel_handle")
        job_data["upload_date"] = str(metadata.get("upload_date") or "")

    split_long = job_data.pop("split_long_clips", True)
    if job_data.get("cut_mode") == "highlights":
        job_data["cut_mode"] = "highlights_split" if split_long else "highlights_single"
    job_data["user_id"] = user.id
    job = Job(**job_data)
    session.add(job)
    await session.commit()
    await session.refresh(job)

    # Enfileira task principal no Celery
    celery_app.send_task("workers.pipeline_task.run_pipeline", args=[job.id])

    return _serialize_job(job)


@router.post("/upload", status_code=202, response_model=JobResponse)
async def upload_job(
    file: UploadFile = File(...),
    cut_mode: str = Form("highlights"),
    part_duration: int = Form(60),
    max_clip_duration: int = Form(60),
    max_clips: int = Form(3),
    split_long_clips: bool = Form(True),
    jump_cut: bool = Form(True),
    platforms: str = Form("[]"),
    subtitle_style: str = Form("none"),
    aspect_mode: str = Form("fill"),
    niche_preset: str = Form("general"),
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

    effective_cut_mode = cut_mode
    if cut_mode == "highlights":
        effective_cut_mode = "highlights_split" if split_long_clips else "highlights_single"

    job = Job(
        id=job_id,
        user_id=user.id,
        source_type="upload",
        source_url=str(saved_path),
        cut_mode=effective_cut_mode,
        part_duration=part_duration,
        max_clip_duration=max_clip_duration,
        max_clips=max_clips,
        platforms=platform_list,
        subtitle_style=subtitle_style,
        aspect_mode=aspect_mode,
        niche_preset=niche_preset,
        enable_hook=enable_hook,
        jump_cut=jump_cut,
        hook_text=hook_text,
        publish_mode=publish_mode,
        due_at=due_at,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    celery_app.send_task("workers.pipeline_task.run_pipeline", args=[job.id])

    return _serialize_job(job)


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

    return _serialize_job(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job não encontrado")

    if job.user_id and job.user_id != user.id:
        raise HTTPException(403, "Sem permissão para cancelar este job")

    if job.status in (JobStatus.done, JobStatus.failed, JobStatus.cancelled):
        return {"message": f"Job já finalizado (status: {job.status})", "status": job.status}

    # Atualiza status no banco de dados
    job.status = JobStatus.cancelled
    job.error_message = "Processamento cancelado pelo usuário"
    await session.commit()

    # Revoga task ativa no Celery
    try:
        from workers.celery_app import celery_app
        i = celery_app.control.inspect()
        active = i.active() or {}
        reserved = i.reserved() or {}
        for worker_name, tasks in {**active, **reserved}.items():
            for t in tasks:
                t_args = t.get("args") or []
                if t_args and t_args[0] == job_id:
                    celery_app.control.revoke(t["id"], terminate=True, signal="SIGKILL")
    except Exception as e:
        logger.warning("jobs.cancel.celery_revoke_failed", error=str(e), job_id=job_id)

    # Limpeza de arquivos temporários
    try:
        tmp_dir = Path(settings.VIDEO_TMP_DIR)
        for f in tmp_dir.glob(f"{job_id}*"):
            f.unlink(missing_ok=True)
    except Exception:
        pass

    return {"message": "Job cancelado com sucesso", "status": job.status, "job_id": job.id}


@router.post("/{job_id}/publish", response_model=JobResponse)
async def publish_approved_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Aprova e dispara a publicação dos cortes gerados para as plataformas configuradas.
    """
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    if not job.output_files:
        raise HTTPException(status_code=400, detail="O vídeo ainda não foi processado ou não gerou cortes.")

    job.approval_status = "approved"
    job.status = JobStatus.publishing
    await session.commit()
    await session.refresh(job)

    # Dispara task de publicação no Celery
    celery_app.send_task("workers.pipeline_task.publish_job_task", args=[job.id])

    return _serialize_job(job)


@router.post("/{job_id}/reject", response_model=JobResponse)
async def reject_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    job.approval_status = "rejected"
    await session.commit()
    await session.refresh(job)
    return _serialize_job(job)



