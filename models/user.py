import uuid
from datetime import datetime
from cryptography.fernet import Fernet
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base
from config import settings

_fernet = Fernet(settings.FERNET_KEY.encode())


class User(Base):
    __tablename__ = "users"

    id:         Mapped[str]      = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_sub: Mapped[str]      = mapped_column(String, unique=True, index=True)
    email:      Mapped[str]      = mapped_column(String, unique=True, index=True)
    name:       Mapped[str]      = mapped_column(String)
    avatar_url: Mapped[str|None] = mapped_column(String, nullable=True)

    # Tokens OAuth por plataforma — armazenados criptografados
    ig_user_id:       Mapped[str|None] = mapped_column(String, nullable=True)
    ig_token_enc:     Mapped[str|None] = mapped_column(String, nullable=True)
    tt_token_enc:     Mapped[str|None] = mapped_column(String, nullable=True)
    tt_refresh_enc:   Mapped[str|None] = mapped_column(String, nullable=True)
    gd_token_enc:     Mapped[str|None] = mapped_column(String, nullable=True)
    gd_refresh_enc:   Mapped[str|None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── helpers ───────────────────────────────────────────────

    def set_token(self, field: str, value: str):
        setattr(self, field, _fernet.encrypt(value.encode()).decode())

    def get_token(self, field: str) -> str | None:
        raw = getattr(self, field, None)
        return _fernet.decrypt(raw.encode()).decode() if raw else None
