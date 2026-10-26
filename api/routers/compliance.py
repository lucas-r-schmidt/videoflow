import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from models.database import get_session, TakedownRequest, Job, JobStatus
from models.user import User
from api.jwt_auth import get_current_user
from workers.celery_app import celery_app

try:
    import structlog
    logger = structlog.get_logger("compliance_router")
except ImportError:
    import logging
    logger = logging.getLogger("compliance_router")

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance & Takedowns"])


class TakedownCreate(BaseModel):
    job_id: str | None = None
    video_url: str | None = None
    claimant_name: str
    claimant_email: str
    reason: str


class TakedownResponse(BaseModel):
    id: str
    job_id: str | None = None
    video_url: str | None = None
    claimant_name: str
    claimant_email: str
    reason: str
    status: str
    resolution_notes: str | None = None
    created_at: str | None = None
    resolved_at: str | None = None


def _serialize_takedown(t: TakedownRequest) -> TakedownResponse:
    return TakedownResponse(
        id=t.id,
        job_id=t.job_id,
        video_url=t.video_url,
        claimant_name=t.claimant_name,
        claimant_email=t.claimant_email,
        reason=t.reason,
        status=t.status,
        resolution_notes=t.resolution_notes,
        created_at=t.created_at.isoformat() if t.created_at else None,
        resolved_at=t.resolved_at.isoformat() if t.resolved_at else None,
    )


@router.post("/takedown", status_code=status.HTTP_201_CREATED, response_model=TakedownResponse)
async def submit_takedown_request(
    payload: TakedownCreate,
    session: AsyncSession = Depends(get_session),
):
    """
    Endpoint público para criadores e detentores de direitos solicitarem remoção imediata.
    """
    if not payload.claimant_name.strip() or not payload.claimant_email.strip() or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Nome, email e justificativa são obrigatórios.")

    # Se informado link de vídeo, tenta localizar o Job correspondente
    matched_job_id = payload.job_id
    if not matched_job_id and payload.video_url:
        query = select(Job).where(Job.source_url == payload.video_url.strip()).limit(1)
        res = await session.execute(query)
        j = res.scalar_one_or_none()
        if j:
            matched_job_id = j.id

    req = TakedownRequest(
        id=str(uuid.uuid4()),
        job_id=matched_job_id,
        video_url=payload.video_url.strip() if payload.video_url else None,
        claimant_name=payload.claimant_name.strip(),
        claimant_email=payload.claimant_email.strip(),
        reason=payload.reason.strip(),
        status="pending",
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    logger.info("compliance.takedown_submitted", id=req.id, claimant=req.claimant_email, job_id=matched_job_id)
    return _serialize_takedown(req)


@router.get("/takedowns", response_model=list[TakedownResponse])
async def list_takedowns(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lista todas as solicitações de remoção para auditoria e mediação."""
    query = select(TakedownRequest).order_by(desc(TakedownRequest.created_at)).limit(100)
    res = await session.execute(query)
    items = res.scalars().all()
    return [_serialize_takedown(item) for item in items]


@router.post("/takedowns/{takedown_id}/resolve", response_model=TakedownResponse)
async def resolve_takedown(
    takedown_id: str,
    notes: str = "Takedown aprovado e executado via Kill Switch",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Aprova a solicitação de takedown: aciona o Kill Switch no job e marca como resolvido.
    """
    req = await session.get(TakedownRequest, takedown_id)
    if not req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    req.status = "resolved"
    req.resolution_notes = notes
    req.resolved_at = datetime.utcnow()

    if req.job_id:
        job = await session.get(Job, req.job_id)
        if job:
            job.approval_status = "removed_by_takedown"
            job.status = JobStatus.cancelled
            job.error_message = f"Removido por solicitação de Takedown #{req.id[:8]} ({req.claimant_email})"
            # Aciona task de exclusão externa
            try:
                celery_app.send_task(
                    "workers.pipeline_task.kill_switch_task",
                    args=[job.id, f"Takedown #{req.id[:8]}: {req.reason}"]
                )
            except Exception as e:
                logger.warning("compliance.kill_switch_error", error=str(e))

    await session.commit()
    await session.refresh(req)
    return _serialize_takedown(req)


@router.post("/takedowns/{takedown_id}/reject", response_model=TakedownResponse)
async def reject_takedown(
    takedown_id: str,
    notes: str = "Solicitação rejeitada após análise de Fair Use",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    req = await session.get(TakedownRequest, takedown_id)
    if not req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    req.status = "rejected"
    req.resolution_notes = notes
    req.resolved_at = datetime.utcnow()
    await session.commit()
    await session.refresh(req)
    return _serialize_takedown(req)
