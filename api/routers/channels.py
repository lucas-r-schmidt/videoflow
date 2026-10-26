import uuid
from datetime import datetime
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import AuthorizedChannel, get_session
from models.user import User
from api.jwt_auth import get_current_user

logger = structlog.get_logger("channels")
router = APIRouter(prefix="/api/v1/channels", tags=["authorized-channels"])


class ChannelCreate(BaseModel):
    name: str
    channel_id: str | None = None
    handle: str | None = None
    channel_url: str | None = None
    policy_notes: str | None = None
    min_delay_hours: int = 24
    credit_template: str | None = None
    is_active: bool = True


class ChannelUpdate(BaseModel):
    name: str | None = None
    handle: str | None = None
    channel_url: str | None = None
    policy_notes: str | None = None
    min_delay_hours: int | None = None
    credit_template: str | None = None
    is_active: bool | None = None


class ChannelResponse(BaseModel):
    id: str
    name: str
    channel_id: str
    handle: str | None = None
    channel_url: str | None = None
    policy_notes: str | None = None
    min_delay_hours: int = 24
    credit_template: str | None = None
    is_active: bool = True
    created_at: str | None = None


def _serialize(ch: AuthorizedChannel) -> ChannelResponse:
    created_str = ch.created_at.isoformat() if ch.created_at else None
    return ChannelResponse(
        id=ch.id,
        name=ch.name,
        channel_id=ch.channel_id,
        handle=ch.handle,
        channel_url=ch.channel_url,
        policy_notes=ch.policy_notes,
        min_delay_hours=ch.min_delay_hours,
        credit_template=ch.credit_template,
        is_active=ch.is_active,
        created_at=created_str,
    )


@router.get("", response_model=list[ChannelResponse])
@router.get("/", response_model=list[ChannelResponse])
async def list_authorized_channels(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    query = select(AuthorizedChannel).order_by(AuthorizedChannel.name.asc())
    if active_only:
        query = query.where(AuthorizedChannel.is_active == True)
    res = await session.execute(query)
    channels = res.scalars().all()
    return [_serialize(c) for c in channels]


@router.post("", response_model=ChannelResponse, status_code=201)
@router.post("/", response_model=ChannelResponse, status_code=201)
async def create_authorized_channel(
    payload: ChannelCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    channel_id = (payload.channel_id or "").strip()
    handle = (payload.handle or "").strip()
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"

    # Se channel_id não foi informado, mas há channel_url, tenta resolver via yt-dlp
    if not channel_id and payload.channel_url:
        try:
            from services.downloader import probe_youtube_metadata
            meta = probe_youtube_metadata(payload.channel_url)
            channel_id = meta.get("channel_id") or channel_id
            if not handle:
                handle = meta.get("channel_handle") or handle
        except Exception as e:
            logger.warning("channels.auto_resolve_failed", error=str(e))

    if not channel_id:
        channel_id = handle or f"UC_{uuid.uuid4().hex[:16]}"

    # Verifica se já existe
    existing = await session.scalar(
        select(AuthorizedChannel).where(AuthorizedChannel.channel_id == channel_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Canal com ID '{channel_id}' já está cadastrado.")

    ch = AuthorizedChannel(
        name=payload.name.strip(),
        channel_id=channel_id,
        handle=handle or None,
        channel_url=payload.channel_url,
        policy_notes=payload.policy_notes,
        min_delay_hours=payload.min_delay_hours,
        credit_template=payload.credit_template,
        is_active=payload.is_active,
    )
    session.add(ch)
    await session.commit()
    await session.refresh(ch)
    return _serialize(ch)


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_authorized_channel(
    channel_id: str,
    payload: ChannelUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    ch = await session.get(AuthorizedChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Canal não encontrado.")

    data = payload.model_dump(exclude_unset=True)
    if "handle" in data and data["handle"]:
        h = data["handle"].strip()
        data["handle"] = h if h.startswith("@") else f"@{h}"

    for k, v in data.items():
        setattr(ch, k, v)

    await session.commit()
    await session.refresh(ch)
    return _serialize(ch)


@router.delete("/{channel_id}", status_code=204)
async def delete_authorized_channel(
    channel_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    ch = await session.get(AuthorizedChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Canal não encontrado.")

    await session.delete(ch)
    await session.commit()
    return None
