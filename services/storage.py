"""
services/storage.py
Gerenciamento de armazenamento externo e CDN.
Suporta Cloudflare R2 (S3-compatible com 10 GB gratuitos e zero egress fee).
"""

from pathlib import Path
import structlog
from config import settings

logger = structlog.get_logger("storage")


def is_r2_configured() -> bool:
    """Verifica se as credenciais do Cloudflare R2 estão preenchidas."""
    return bool(
        getattr(settings, "R2_ACCOUNT_ID", None)
        and getattr(settings, "R2_ACCESS_KEY_ID", None)
        and getattr(settings, "R2_SECRET_ACCESS_KEY", None)
        and getattr(settings, "R2_BUCKET_NAME", None)
    )


def upload_to_r2(local_path: str | Path, key_name: str | None = None) -> str | None:
    """
    Envia o arquivo gerado para o bucket Cloudflare R2.
    Retorna a URL pública do vídeo ou None em caso de falha/não configurado.
    """
    if not is_r2_configured():
        return None

    path = Path(local_path)
    if not path.exists():
        logger.warning("storage.r2.file_not_found", path=str(path))
        return None

    key = key_name or path.name
    endpoint = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

    try:
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

        content_type = "video/mp4" if path.suffix.lower() == ".mp4" else "application/octet-stream"
        s3.upload_file(
            str(path),
            settings.R2_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": content_type},
        )

        # Determina a URL pública de acesso (R2 dev URL ou domínio customizado)
        if getattr(settings, "R2_PUBLIC_URL", None):
            public_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"
        else:
            public_url = f"https://{settings.R2_BUCKET_NAME}.r2.dev/{key}"

        logger.info("storage.r2.upload_success", key=key, url=public_url)
        return public_url

    except ImportError:
        logger.warning("storage.r2.boto3_missing", message="Instale boto3 para habilitar upload para o R2.")
        return None
    except Exception as e:
        logger.error("storage.r2.upload_error", error=str(e), key=key)
        return None
