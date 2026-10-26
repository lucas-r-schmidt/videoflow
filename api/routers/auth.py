import secrets
import hashlib
import base64
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from models.database import get_session
from models.user import User
from api.jwt_auth import issue_tokens, decode_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

FRONTEND_URL = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _get_frontend_base(request: Request) -> str:
    return FRONTEND_URL



# ── PKCE helpers ──────────────────────────────────────────────

def _pkce_pair():
    verifier  = secrets.token_urlsafe(64)
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ═══════════════════════════════════════════════════════════════
#  GOOGLE LOGIN — ponto de entrada do sistema
# ═══════════════════════════════════════════════════════════════

@router.get("/google/login")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_CLIENT_ID não configurado no arquivo .env. Configure credenciais Google Cloud Console ou use 'Entrar como Teste / Dev'."
        )
    state = secrets.token_urlsafe(16)
    request.session["g_state"] = state
    params = urlencode({
        "client_id":     settings.GOOGLE_CLIENT_ID,
        "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join([
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/drive.readonly",
        ]),
        "access_type": "offline",
        "prompt":      "consent",
        "state":       state,
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    session: AsyncSession = Depends(get_session),
):
    if state != request.session.pop("g_state", None):
        raise HTTPException(400, "State mismatch")

    async with httpx.AsyncClient() as client:
        # Troca code → tokens
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "code":          code,
            "client_id":     settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        r.raise_for_status()
        tok = r.json()

        # Busca perfil do usuário
        r = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
        )
        r.raise_for_status()
        profile = r.json()

    # Upsert: cria ou atualiza usuário
    result = await session.execute(select(User).where(User.google_sub == profile["sub"]))
    user   = result.scalar_one_or_none()

    if not user:
        user = User(
            google_sub = profile["sub"],
            email      = profile["email"],
            name       = profile.get("name", ""),
            avatar_url = profile.get("picture"),
        )
        session.add(user)

    user.name       = profile.get("name", user.name)
    user.avatar_url = profile.get("picture", user.avatar_url)

    if tok.get("access_token"):
        user.set_token("gd_token_enc", tok["access_token"])
    if tok.get("refresh_token"):
        user.set_token("gd_refresh_enc", tok["refresh_token"])

    await session.commit()
    await session.refresh(user)

    # Emite JWT interno e redireciona para o frontend
    base_fe = _get_frontend_base(request)
    tokens = issue_tokens(user.id)
    redirect = (
        f"{base_fe}/auth/callback"
        f"?access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
    )
    return RedirectResponse(redirect)


@router.api_route("/dev-login", methods=["GET", "POST"])
async def dev_login(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Login rápido para dev ou protegido por ADMIN_PIN em produção."""
    submitted_pin = request.query_params.get("pin") or request.headers.get("X-Admin-PIN")
    if not submitted_pin and request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                submitted_pin = body.get("pin")
        except Exception:
            pass

    configured_pin = getattr(settings, "ADMIN_PIN", "")
    if settings.APP_ENV != "development":
        if not configured_pin or submitted_pin != configured_pin:
            raise HTTPException(
                status_code=403,
                detail="PIN de administrador inválido ou ausente."
            )

    result = await session.execute(select(User).where(User.google_sub == "dev-user-001"))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            google_sub="dev-user-001",
            email="dev@videoflow.local",
            name="Dev Teste",
            avatar_url="https://api.dicebear.com/7.x/bottts/svg?seed=VideoFlowDev",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    tokens = issue_tokens(user.id)

    # Se chamado via AJAX / frontend fetch / JSON
    if "application/json" in request.headers.get("accept", "") or request.method == "POST":
        return tokens

    base_fe = _get_frontend_base(request)
    redirect = (
        f"{base_fe}/auth/callback"
        f"?access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
    )
    return RedirectResponse(redirect)



# ── Rota /me ──────────────────────────────────────────────────

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id":         user.id,
        "email":      user.email,
        "name":       user.name,
        "avatar_url": user.avatar_url,
        "connected":  {
            "instagram":    bool(user.ig_token_enc),
            "tiktok":       bool(user.tt_token_enc),
            "google_drive": bool(user.gd_token_enc),
        },
    }


# ── Refresh JWT ───────────────────────────────────────────────

@router.post("/refresh")
async def refresh(refresh_token: str, session: AsyncSession = Depends(get_session)):
    user_id = decode_token(refresh_token, "refresh")
    result  = await session.execute(select(User).where(User.id == user_id))
    user    = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    return issue_tokens(user.id)


# ═══════════════════════════════════════════════════════════════
#  CONECTAR INSTAGRAM (após login)
# ═══════════════════════════════════════════════════════════════

@router.get("/instagram/login")
async def instagram_login(request: Request, user: User = Depends(get_current_user)):
    state = secrets.token_urlsafe(16)
    request.session["ig_state"]   = state
    request.session["ig_user_id"] = user.id
    params = urlencode({
        "client_id":     settings.INSTAGRAM_APP_ID,
        "redirect_uri":  settings.INSTAGRAM_REDIRECT_URI,
        "scope":         "instagram_basic,instagram_content_publish,pages_show_list",
        "response_type": "code",
        "state":         state,
    })
    return RedirectResponse(f"https://www.facebook.com/dialog/oauth?{params}")


@router.get("/instagram/callback")
async def instagram_callback(
    request: Request,
    code: str,
    state: str,
    session: AsyncSession = Depends(get_session),
):
    if state != request.session.pop("ig_state", None):
        raise HTTPException(400, "State mismatch")

    user_id = request.session.pop("ig_user_id", None)
    result  = await session.execute(select(User).where(User.id == user_id))
    user    = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Sessão expirada — faça login novamente")

    async with httpx.AsyncClient() as client:
        r = await client.get("https://graph.facebook.com/v20.0/oauth/access_token", params={
            "client_id":     settings.INSTAGRAM_APP_ID,
            "client_secret": settings.INSTAGRAM_APP_SECRET,
            "redirect_uri":  settings.INSTAGRAM_REDIRECT_URI,
            "code":          code,
        })
        r.raise_for_status()
        short_tok = r.json()["access_token"]

        r = await client.get("https://graph.facebook.com/v20.0/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id":  settings.INSTAGRAM_APP_ID,
            "client_secret": settings.INSTAGRAM_APP_SECRET,
            "fb_exchange_token": short_tok,
        })
        r.raise_for_status()
        long_tok = r.json()["access_token"]

        r = await client.get("https://graph.facebook.com/v20.0/me/accounts",
                             params={"access_token": long_tok})
        pages = r.json().get("data", [])
        if not pages:
            raise HTTPException(400, "Nenhuma Page encontrada")

        page_token = pages[0]["access_token"]
        page_id    = pages[0]["id"]
        r = await client.get(f"https://graph.facebook.com/v20.0/{page_id}", params={
            "fields": "instagram_business_account",
            "access_token": page_token,
        })
        ig_uid = r.json().get("instagram_business_account", {}).get("id", "")

    user.ig_user_id = ig_uid
    user.set_token("ig_token_enc", long_tok)
    await session.commit()

    return RedirectResponse(f"{FRONTEND_URL}/settings?connected=instagram")


# ═══════════════════════════════════════════════════════════════
#  CONECTAR TIKTOK (após login)
# ═══════════════════════════════════════════════════════════════

@router.get("/tiktok/login")
async def tiktok_login(request: Request, user: User = Depends(get_current_user)):
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    request.session["tt_verifier"] = verifier
    request.session["tt_state"]    = state
    request.session["tt_user_id"]  = user.id
    params = urlencode({
        "client_key":            settings.TIKTOK_CLIENT_KEY,
        "scope":                 "video.publish,video.upload",
        "response_type":         "code",
        "redirect_uri":          settings.TIKTOK_REDIRECT_URI,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })
    return RedirectResponse(f"https://www.tiktok.com/v2/auth/authorize/?{params}")


@router.get("/tiktok/callback")
async def tiktok_callback(
    request: Request,
    code: str,
    state: str,
    session: AsyncSession = Depends(get_session),
):
    if state != request.session.pop("tt_state", None):
        raise HTTPException(400, "State mismatch")

    user_id  = request.session.pop("tt_user_id", None)
    verifier = request.session.pop("tt_verifier", None)
    result   = await session.execute(select(User).where(User.id == user_id))
    user     = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Sessão expirada")

    async with httpx.AsyncClient() as client:
        r = await client.post("https://open.tiktokapis.com/v2/oauth/token/", data={
            "client_key":    settings.TIKTOK_CLIENT_KEY,
            "client_secret": settings.TIKTOK_CLIENT_SECRET,
            "code":          code,
            "grant_type":    "authorization_code",
            "redirect_uri":  settings.TIKTOK_REDIRECT_URI,
            "code_verifier": verifier,
        })
        r.raise_for_status()
        tok = r.json()

    user.set_token("tt_token_enc",   tok["access_token"])
    user.set_token("tt_refresh_enc", tok["refresh_token"])
    await session.commit()

    return RedirectResponse(f"{FRONTEND_URL}/settings?connected=tiktok")
