import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import String, Integer, Float, DateTime, JSON, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from sqlalchemy.pool import NullPool

from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class JobStatus(str, PyEnum):
    queued      = "queued"
    downloading = "downloading"
    analyzing   = "analyzing"
    processing  = "processing"
    publishing  = "publishing"
    done        = "done"
    failed      = "failed"
    cancelled   = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id:             Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:        Mapped[str | None]    = mapped_column(String, nullable=True, index=True)
    status:         Mapped[str]           = mapped_column(String, default=JobStatus.queued)
    source_type:    Mapped[str]           = mapped_column(String)          # youtube | google_drive
    source_url:     Mapped[str | None]    = mapped_column(String, nullable=True)
    drive_file_id:  Mapped[str | None]    = mapped_column(String, nullable=True)
    cut_mode:       Mapped[str]           = mapped_column(String)          # highlights | sequential
    part_duration:  Mapped[int]           = mapped_column(Integer, default=60)
    max_clip_duration: Mapped[int]        = mapped_column(Integer, default=60)
    max_clips:      Mapped[int]           = mapped_column(Integer, default=3)
    platforms:      Mapped[list]          = mapped_column(JSON, default=list)
    subtitle_style: Mapped[str]           = mapped_column(String, default="none")  # none | simple | karaoke
    aspect_mode:    Mapped[str]           = mapped_column(String, default="fill")  # fill | blur | split
    niche_preset:   Mapped[str]           = mapped_column(String, default="general", nullable=True) # general | emotional | debate
    enable_hook:    Mapped[bool]          = mapped_column(Boolean, default=True)
    jump_cut:       Mapped[bool]          = mapped_column(Boolean, default=True, nullable=True)
    hook_text:      Mapped[str | None]    = mapped_column(String, nullable=True)
    generated_title:Mapped[str | None]    = mapped_column(String, nullable=True)
    generated_caption: Mapped[str | None] = mapped_column(String, nullable=True)
    publish_mode:   Mapped[str]           = mapped_column(String, default="shareNow")  # shareNow | addToQueue | scheduled
    due_at:         Mapped[str | None]    = mapped_column(String, nullable=True)        # ISO 8601 UTC
    scheduled_at:   Mapped[int | None]    = mapped_column(Integer, nullable=True)
    output_files:   Mapped[list]          = mapped_column(JSON, default=list)
    error_message:  Mapped[str | None]    = mapped_column(String, nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
