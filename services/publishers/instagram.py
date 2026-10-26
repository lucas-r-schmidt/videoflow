import asyncio
import httpx
from services.publishers.compliance import format_compliance_caption

GRAPH = "https://graph.facebook.com/v20.0"


async def publish_reel(
    file_path: str,
    job,
    part_index: int | None = None,
    total_parts: int | None = None,
    part_title: str | None = None,
    part_caption: str | None = None,
) -> dict:
    """
    Publica Reel no Instagram via Graph API.
    Requer: job.ig_user_id e job.ig_access_token no banco.
    Por ora usa variáveis de ambiente como fallback para testes.
    """
    from config import settings

    # Em produção, buscar do banco criptografado com Fernet
    ig_user_id = getattr(job, "ig_user_id", None) or ""
    access_token = getattr(job, "ig_access_token", None) or ""

    if not ig_user_id or not access_token:
        raise ValueError("Instagram credentials não configuradas para este job")

    raw_caption = part_caption or getattr(job, "generated_caption", None) or getattr(job, "caption", None)
    caption_text = format_compliance_caption(
        base_caption=raw_caption,
        channel_name=getattr(job, "channel_name", None),
        channel_handle=getattr(job, "channel_handle", None),
        source_url=getattr(job, "source_url", None),
        part_index=part_index,
        total_parts=total_parts,
    )


    async with httpx.AsyncClient(timeout=60) as client:
        # ETAPA 1: criar container
        r = await client.post(f"{GRAPH}/{ig_user_id}/media", data={
            "media_type": "REELS",
            "video_url": file_path,   # deve ser URL pública (S3/CDN)
            "caption": caption_text,
            "access_token": access_token,
        })
        r.raise_for_status()
        container_id = r.json()["id"]

        # ETAPA 2: aguarda processamento
        await _wait_container(client, container_id, access_token)

        # ETAPA 3: publicar
        r = await client.post(f"{GRAPH}/{ig_user_id}/media_publish", data={
            "creation_id": container_id,
            "access_token": access_token,
        })
        r.raise_for_status()
        return r.json()


async def delete_reel(media_id: str, access_token: str) -> bool:
    """Remove Reel do Instagram via Graph API (Kill Switch)."""
    if not media_id or not access_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(f"{GRAPH}/{media_id}", params={"access_token": access_token})
            return r.status_code in (200, 204, 404)
    except Exception:
        return False


async def _wait_container(client, container_id: str, token: str, max_tries: int = 24):
    for attempt in range(max_tries):
        r = await client.get(f"{GRAPH}/{container_id}", params={
            "fields": "status_code",
            "access_token": token,
        })
        status = r.json().get("status_code", "")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram container error: {r.json()}")
        await asyncio.sleep(5 * (attempt + 1))  # backoff simples
    raise TimeoutError("Instagram container não ficou pronto a tempo")


def _build_caption(job, part_index: int | None = None, total_parts: int | None = None) -> str:
    base = getattr(job, "caption", "") or "#shorts #reels #viral"
    if part_index:
        part_tag = f"PARTE {part_index}" + (f" de {total_parts}" if total_parts else "") + " 🎬🔥\n\n"
        if f"PARTE {part_index}" not in base:
            return f"{part_tag}{base}"
    return base
