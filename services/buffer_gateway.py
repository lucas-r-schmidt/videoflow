from pathlib import Path
import httpx
import structlog
from config import settings

logger = structlog.get_logger("buffer_gateway")


async def publish_buffer_gateway(file_path: str, job) -> dict:
    """
    Envia o corte final gerado para o Buffer Gateway (FastAPI).
    O Gateway cuida do upload para o Cloudinary CDN e disparo para a API GraphQL do Buffer.
    """
    log = logger.bind(job_id=getattr(job, "id", None), file=file_path)
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {file_path}")

    caption = getattr(job, "generated_caption", None) or _build_caption(job)
    video_title = getattr(job, "generated_title", None) or "Clipe que Vale #Shorts"
    url = f"{settings.BUFFER_GATEWAY_URL.rstrip('/')}/api/v1/publish-file"

    headers = {
        "X-API-Key": settings.BUFFER_GATEWAY_API_KEY,
    }

    profile_name = getattr(settings, "BUFFER_GATEWAY_PROFILE", "clipe-que-vale")
    data = {
        "text": caption,
        "title": video_title,
        "project_id": profile_name,
        "profile": profile_name,
        "services": getattr(settings, "BUFFER_GATEWAY_DEFAULT_SERVICES", "tiktok,instagram,youtube"),
        "mode": getattr(settings, "BUFFER_GATEWAY_MODE", "shareNow"),
    }

    log.info(
        "buffer_gateway.upload.start",
        url=url,
        profile=profile_name,
        title=video_title,
    )

    async with httpx.AsyncClient(timeout=180.0) as client:
        with open(path, "rb") as f:
            files = {
                "file": (path.name, f, "video/mp4"),
            }
            resp = await client.post(url, headers=headers, data=data, files=files)

        if resp.status_code >= 400:
            log.error(
                "buffer_gateway.upload.failed",
                status=resp.status_code,
                response=resp.text,
            )
            resp.raise_for_status()

        result = resp.json()
        log.info("buffer_gateway.upload.success", result=result)
        return result


def _build_caption(job) -> str:
    """Gera legenda e hashtags adequadas para o corte viral."""
    custom_caption = getattr(job, "caption", None)
    if custom_caption:
        return custom_caption

    tags = ["#cortes", "#viral", "#reels", "#shorts", "#tiktok"]
    return f"Assista até o final! 🎬🔥\n\n{' '.join(tags)}"
