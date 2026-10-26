from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "production"
    APP_SECRET_KEY: str
    FRONTEND_URL: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str

    # Redis / Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Segurança
    FERNET_KEY: str
    ADMIN_PIN: str = "240810"

    # Instagram
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""
    INSTAGRAM_REDIRECT_URI: str = ""

    # TikTok
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    TIKTOK_REDIRECT_URI: str = ""

    # Google Drive
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    # Whisper
    WHISPER_MODEL: str = "large-v3-turbo"

    # LLM (Gemini / Groq / Cerebras / OpenRouter / OpenAI / Ollama)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_FALLBACK_MODEL: str = "openai/gpt-oss-20b"
    CEREBRAS_API_KEY: str = ""
    CEREBRAS_MODEL: str = "llama3.1-8b"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = ""
    OLLAMA_MODEL: str = "phi3:mini"

    # yt-dlp PO Token (Proof of Origin)
    YTDLP_PO_TOKEN: str = ""

    # Cloudflare Workers AI (Whisper gratuito)
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_API_TOKEN: str = ""

    # Ingestão / Download Alternativo (Cobalt)
    COBALT_API_URL: str = ""

    # Cloudflare R2 (Storage S3-compatible gratuito)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_PUBLIC_URL: str = ""

    # Storage
    VIDEO_TMP_DIR: str = "/tmp/videos"
    VIDEO_OUTPUT_DIR: str = "/app/outputs"
    VIDEO_CLEANUP_AFTER_SECONDS: int = 3600
    MAX_UPLOAD_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB limite padrão

    # Buffer Gateway
    BUFFER_GATEWAY_URL: str = "https://gentleman-productions-white-annually.trycloudflare.com"
    BUFFER_GATEWAY_API_KEY: str = "gateway_secret_token_123"
    BUFFER_GATEWAY_PROFILE: str = "clipe-que-vale"
    BUFFER_GATEWAY_DEFAULT_SERVICES: str = "tiktok,instagram,youtube"
    BUFFER_GATEWAY_MODE: str = "shareNow"


settings = Settings()
