from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from api.routers import jobs, auth, channels, compliance
from models.database import Base, engine, init_db
from models.user import User   # noqa: F401 — registra tabela no metadata
from config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria e migra tabelas (jobs, users, authorized_channels) + seed inicial
    await init_db()
    logger.info("database.initialized")
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="Video Automation API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── SessionMiddleware DEVE vir ANTES do CORSMiddleware ────────
# Assina o cookie com APP_SECRET_KEY (itsdangerous por baixo)
is_prod = settings.APP_ENV == "production"

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SECRET_KEY,
    session_cookie="va_session",
    max_age=600,          # 10 min — suficiente para o OAuth round-trip
    https_only=is_prod,   # True em produção (HTTPS)
    same_site="lax",
)

allowed_origins = list({
    settings.FRONTEND_URL.rstrip("/"),
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8085",
    "http://127.0.0.1:8085",
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,  # necessário para cookies de sessão
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

Path("/app/outputs").mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory="/app/outputs"), name="outputs")

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
assets_dir = static_dir / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

app.include_router(jobs.router)
app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(compliance.router)


@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
async def index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "VideoFlow API ativa. Interface web não encontrada."}


@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok"}

