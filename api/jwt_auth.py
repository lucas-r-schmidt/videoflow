from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from models.database import get_session
from models.user import User

ALGORITHM = "HS256"
ACCESS_TTL  = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)

bearer = HTTPBearer()


def _issue(sub: str, ttl: timedelta, kind: str) -> str:
    payload = {
        "sub":  sub,
        "kind": kind,
        "exp":  datetime.utcnow() + ttl,
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=ALGORITHM)


def issue_tokens(user_id: str) -> dict:
    return {
        "access_token":  _issue(user_id, ACCESS_TTL,  "access"),
        "refresh_token": _issue(user_id, REFRESH_TTL, "refresh"),
        "token_type":    "bearer",
    }


def decode_token(token: str, kind: str) -> str:
    """Decodifica e valida o JWT. Retorna user_id (sub)."""
    try:
        payload = jwt.decode(token, settings.APP_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("kind") != kind or "sub" not in payload:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tipo ou formato de token inválido")
        return payload["sub"]
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido ou expirado")


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id = decode_token(creds.credentials, "access")
    result  = await session.execute(select(User).where(User.id == user_id))
    user    = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário não encontrado")
    return user
