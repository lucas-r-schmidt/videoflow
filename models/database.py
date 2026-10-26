import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import String, Integer, Float, DateTime, JSON, Boolean, Text, ForeignKey, text, select
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


class AuthorizedChannel(Base):
    __tablename__ = "authorized_channels"

    id:             Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id:     Mapped[str]           = mapped_column(String, unique=True, index=True) # ID no YouTube (ex: UC...)
    name:           Mapped[str]           = mapped_column(String)                         # Ex: "Flow Podcast"
    handle:         Mapped[str | None]    = mapped_column(String, nullable=True, index=True) # Ex: "@flowpdc"
    channel_url:    Mapped[str | None]    = mapped_column(String, nullable=True)          # Ex: "https://youtube.com/@flowpdc"
    policy_notes:   Mapped[str | None]    = mapped_column(String, nullable=True)          # Ex: "Carência de 24h, link na descrição"
    min_delay_hours:Mapped[int]           = mapped_column(Integer, default=24)            # Carência mínima em horas
    credit_template:Mapped[str | None]    = mapped_column(String, nullable=True)          # Template opcional customizado
    is_active:      Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id:             Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:        Mapped[str | None]    = mapped_column(String, nullable=True, index=True)
    status:         Mapped[str]           = mapped_column(String, default=JobStatus.queued)
    source_type:    Mapped[str]           = mapped_column(String)          # youtube | google_drive | upload
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
    publish_mode:   Mapped[str]           = mapped_column(String, default="shareNow")  # shareNow | addToQueue | scheduled | draft
    due_at:         Mapped[str | None]    = mapped_column(String, nullable=True)        # ISO 8601 UTC
    scheduled_at:   Mapped[int | None]    = mapped_column(Integer, nullable=True)
    output_files:   Mapped[list]          = mapped_column(JSON, default=list)
    error_message:  Mapped[str | None]    = mapped_column(String, nullable=True)

    # Compliance & Governança de Canais e Aprovação Humana
    channel_name:      Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id:        Mapped[str | None] = mapped_column(String, nullable=True)
    channel_handle:    Mapped[str | None] = mapped_column(String, nullable=True)
    upload_date:       Mapped[str | None] = mapped_column(String, nullable=True)
    requires_approval: Mapped[bool]       = mapped_column(Boolean, default=True, nullable=True)
    approval_status:   Mapped[str]        = mapped_column(String, default="pending", nullable=True) # pending | approved | rejected | published

    # Transformação Audiovisual Anti-Content ID (Sprint 2 & 4)
    enable_bgm:        Mapped[bool]       = mapped_column(Boolean, default=True, nullable=True)
    speed_boost:       Mapped[float]      = mapped_column(Float, default=1.03, nullable=True)
    enable_headline:   Mapped[bool]       = mapped_column(Boolean, default=True, nullable=True)
    horizontal_flip:   Mapped[bool]       = mapped_column(Boolean, default=False, nullable=True)
    watermark_text:    Mapped[str | None] = mapped_column(String, nullable=True)

    # Rastreamento de Publicação Externa & Kill Switch (Sprint 3)
    platform_post_ids: Mapped[str]        = mapped_column(Text, default="[]", nullable=True) # JSON list de post IDs externos

    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TakedownRequest(Base):
    """Solicitações formais de remoção de conteúdo (DMCA / Notificação Extrajudicial)."""
    __tablename__ = "takedown_requests"

    id:             Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id:         Mapped[str | None]    = mapped_column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    video_url:      Mapped[str | None]    = mapped_column(String, nullable=True)
    claimant_name:  Mapped[str]           = mapped_column(String, nullable=False)
    claimant_email: Mapped[str]           = mapped_column(String, nullable=False)
    reason:         Mapped[str]           = mapped_column(Text, nullable=False)
    status:         Mapped[str]           = mapped_column(String, default="pending", nullable=False) # pending | resolved | rejected
    resolution_notes: Mapped[str | None]  = mapped_column(Text, nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


DEFAULT_AUTHORIZED_CHANNELS = [
    {
        "name": "Flow Podcast",
        "handle": "@flowpdc",
        "channel_id": "UC4ncvgh5hFr5O83MH7-jRJg",
        "channel_url": "https://www.youtube.com/@flowpdc",
        "min_delay_hours": 24,
        "policy_notes": "Pioneiro dos cortes no Brasil. Carência de 24h e link do episódio completo obrigatório.",
    },
    {
        "name": "Podpah",
        "handle": "@podpah",
        "channel_id": "UCvW6n8Teq8P1lX5mX6qT3qw",
        "channel_url": "https://www.youtube.com/@podpah",
        "min_delay_hours": 24,
        "policy_notes": "Permite cortes de fãs com créditos e links oficiais na descrição.",
    },
    {
        "name": "Inteligência Ltda.",
        "handle": "@inteligencialtda",
        "channel_id": "UCx8t7U_07uFv4o_B8v5L6tw",
        "channel_url": "https://www.youtube.com/@inteligencialtda",
        "min_delay_hours": 24,
        "policy_notes": "Incentiva clipadores independentes mediante créditos ao canal oficial.",
    },
    {
        "name": "PrimoCast / Thiago Nigro",
        "handle": "@primocast",
        "channel_id": "UCb_ZqU23K-U6lWq9C3eD_7w",
        "channel_url": "https://www.youtube.com/@primocast",
        "min_delay_hours": 24,
        "policy_notes": "Foco em educação financeira e negócios. Permite cortes com links oficiais.",
    },
    {
        "name": "Os Sócios Podcast",
        "handle": "@ossociospodcast",
        "channel_id": "UCk2vU7y8N89aX5W-r8s67ww",
        "channel_url": "https://www.youtube.com/@ossociospodcast",
        "min_delay_hours": 24,
        "policy_notes": "Bruno e Malu Perini. Foco em educação e negócios com menção obrigatória.",
    },
    {
        "name": "TEDx Talks",
        "handle": "@tedx",
        "channel_id": "UCsT0YIqwnpJCM-mx7-gSA4Q",
        "channel_url": "https://www.youtube.com/@tedx",
        "min_delay_hours": 0,
        "policy_notes": "Licença Creative Commons aberta com atribuição obrigatória.",
    },
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migração defensiva: adiciona colunas à tabela jobs se não existirem
        alter_statements = [
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS channel_name VARCHAR;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS channel_id VARCHAR;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS channel_handle VARCHAR;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS upload_date VARCHAR;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS approval_status VARCHAR DEFAULT 'pending';",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS enable_bgm BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS speed_boost FLOAT DEFAULT 1.03;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS enable_headline BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS horizontal_flip BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS watermark_text VARCHAR;",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS platform_post_ids TEXT DEFAULT '[]';",
        ]
        for stmt in alter_statements:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass

    # Seed inicial de canais autorizados se tabela estiver vazia
    async with AsyncSessionLocal() as session:
        try:
            res = await session.execute(select(AuthorizedChannel).limit(1))
            first = res.scalar_one_or_none()
            if not first:
                for ch in DEFAULT_AUTHORIZED_CHANNELS:
                    session.add(AuthorizedChannel(**ch))
                await session.commit()
        except Exception:
            await session.rollback()


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
