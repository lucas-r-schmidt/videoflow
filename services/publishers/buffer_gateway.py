from pathlib import Path
import httpx
import structlog
from config import settings

from services.publishers.compliance import format_compliance_caption

logger = structlog.get_logger("buffer_gateway")


async def publish_buffer_gateway(
    file_path: str,
    job,
    part_index: int | None = None,
    total_parts: int | None = None,
    part_title: str | None = None,
    part_caption: str | None = None,
) -> dict:
    """
    Envia o corte final gerado para o Buffer Gateway (FastAPI).
    O Gateway cuida do upload para o Cloudinary CDN e disparo para a API GraphQL do Buffer.
    """
    log = logger.bind(job_id=getattr(job, "id", None), file=file_path)
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {file_path}")

    raw_caption = part_caption or getattr(job, "generated_caption", None) or getattr(job, "caption", None)
    caption = format_compliance_caption(
        base_caption=raw_caption,
        channel_name=getattr(job, "channel_name", None),
        channel_handle=getattr(job, "channel_handle", None),
        source_url=getattr(job, "source_url", None),
        part_index=part_index,
        total_parts=total_parts,
    )

    video_title = part_title or getattr(job, "generated_title", None) or "Clipe que Vale #Shorts"
    if part_index and not part_title:
        part_tag = f" - Parte {part_index}" + (f"/{total_parts}" if total_parts else "")
        if f"Parte {part_index}" not in video_title:
            video_title = f"{video_title}{part_tag}"


    url = f"{settings.BUFFER_GATEWAY_URL.rstrip('/')}/api/v1/publish-file"

    headers = {
        "X-API-Key": settings.BUFFER_GATEWAY_API_KEY,
    }

    profile_name = getattr(settings, "BUFFER_GATEWAY_PROFILE", "clipe-que-vale")
    publish_mode = getattr(job, "publish_mode", None) or getattr(settings, "BUFFER_GATEWAY_MODE", "shareNow")
    due_at = getattr(job, "due_at", None)
    mode_val = "addToQueue" if publish_mode == "addToQueue" else "shareNow"

    data = {
        "text": caption,
        "title": video_title,
        "project_id": profile_name,
        "profile": profile_name,
        "services": getattr(settings, "BUFFER_GATEWAY_DEFAULT_SERVICES", "tiktok,instagram,youtube"),
        "mode": mode_val,
        "ai_disclosure": "true",
    }
    if publish_mode == "scheduled" and due_at:
        data["due_at"] = str(due_at)

    log.info(
        "buffer_gateway.upload.start",
        url=url,
        profile=profile_name,
        title=video_title,
        publish_mode=publish_mode,
        due_at=due_at,
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


def _build_caption(job, part_index: int | None = None, total_parts: int | None = None) -> str:
    """Gera legenda e hashtags adequadas para o corte viral."""
    custom_caption = getattr(job, "caption", None)
    if custom_caption:
        base = custom_caption
    else:
        tags = ["#cortes", "#viral", "#reels", "#shorts", "#tiktok"]
        if part_index:
            tags.append(f"#parte{part_index}")
        base = f"Assista até o final! 🎬🔥\n\n{' '.join(tags)}"

    if part_index:
        part_tag = f"PARTE {part_index}" + (f" de {total_parts}" if total_parts else "") + " 🎬🔥\n\n"
        if f"PARTE {part_index}" not in base:
            return f"{part_tag}{base}"
    return base
