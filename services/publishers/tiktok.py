import asyncio
import httpx

TIKTOK_API = "https://open.tiktokapis.com/v2"


async def publish_tiktok(
    file_path: str,
    job,
    part_index: int | None = None,
    total_parts: int | None = None,
    part_title: str | None = None,
    part_caption: str | None = None,
) -> dict:
    """
    Publica vídeo no TikTok via Content Posting API v2.
    file_path deve ser URL pública acessível pelo TikTok.
    """
    access_token = getattr(job, "tiktok_access_token", None) or ""

    if not access_token:
        raise ValueError("TikTok access_token não configurado para este job")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    title_text = part_title or _build_title(job, part_index, total_parts)

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{TIKTOK_API}/post/publish/video/init/",
            headers=headers,
            json={
                "post_info": {
                    "title": title_text,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },

                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": file_path,
                },
            },
        )
        r.raise_for_status()
        publish_id = r.json()["data"]["publish_id"]

        # Aguarda processamento
        await _wait_publish(client, publish_id, headers)
        return {"publish_id": publish_id, "status": "published"}


async def _wait_publish(client, publish_id: str, headers: dict, max_tries: int = 20):
    for _ in range(max_tries):
        r = await client.post(
            f"{TIKTOK_API}/post/publish/status/fetch/",
            headers=headers,
            json={"publish_id": publish_id},
        )
        status = r.json().get("data", {}).get("status", "")
        if status == "PUBLISH_COMPLETE":
            return
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"TikTok publish falhou: {r.json()}")
        await asyncio.sleep(10)
    raise TimeoutError("TikTok publish não completou a tempo")


def _build_title(job, part_index: int | None = None, total_parts: int | None = None) -> str:
    title = getattr(job, "caption", "") or getattr(job, "generated_title", "") or "#shorts #viral"
    if part_index:
        part_tag = f"PARTE {part_index}" + (f"/{total_parts}" if total_parts else "") + " 🔥 "
        if f"PARTE {part_index}" not in title:
            title = f"{part_tag}{title}"

    # Adiciona menção de crédito ao criador no TikTok
    handle = getattr(job, "channel_handle", None) or getattr(job, "channel_name", None)
    if handle:
        handle_tag = handle if handle.startswith("@") else f"@{handle}"
        title = f"{title} | Cr: {handle_tag}"

    return title[:300]
