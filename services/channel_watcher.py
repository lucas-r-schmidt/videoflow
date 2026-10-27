import sys
import uuid
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models.database import AuthorizedChannel, Job, JobStatus
from services.downloader import probe_youtube_metadata, check_channel_authorization
from workers.celery_app import celery_app

try:
    import structlog
    logger = structlog.get_logger("channel_watcher")
except ImportError:
    import logging
    logger = logging.getLogger("channel_watcher")


def probe_channel_latest_videos(channel_url: str, limit: int = 3) -> list[dict]:
    """
    Obtém metadados leves dos vídeos mais recentes do canal via yt-dlp flat playlist (zero consumo de vídeo).
    """
    ytdlp_bin = shutil.which("yt-dlp")
    base_cmd = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]
    
    # Monta a URL de listagem de vídeos
    target_url = channel_url.rstrip("/")
    if not target_url.endswith("/videos") and not target_url.endswith("/streams"):
        target_url = f"{target_url}/videos"

    cmd = base_cmd + [
        "--flat-playlist",
        "--playlist-end", str(max(1, limit)),
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--socket-timeout", "15",
        target_url
    ]

    for c_path in [Path("/app/cookies.txt"), Path("cookies.txt")]:
        try:
            if c_path.exists() and c_path.stat().st_size > 0:
                cmd.extend(["--cookies", str(c_path)])
                break
        except Exception:
            pass

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=35)
        data = json.loads(proc.stdout)
        entries = data.get("entries") or []
        results = []
        for e in entries:
            v_id = e.get("id")
            if not v_id:
                continue
            results.append({
                "id": v_id,
                "title": e.get("title") or "",
                "url": f"https://www.youtube.com/watch?v={v_id}",
                "uploader": data.get("channel") or data.get("uploader") or "",
            })
        return results
    except Exception as e:
        logger.warning("channel_watcher.flat_playlist_failed", url=channel_url, error=str(e)[:180])
        return []


async def run_channel_watcher(
    session: AsyncSession,
    max_new_per_channel: int = 1,
    max_total_pending: int = 3,
) -> list[str]:
    """
    Verifica todos os canais autorizados ativos com auto_watch=True.
    - Aplica Throttling: não enfileira novos vídeos se houver >= max_total_pending vídeos aguardando aprovação.
    - Valida carência mínima (min_delay_hours).
    - Cria Job automático com modo aprovação obrigatória (requires_approval=True).
    """
    logger.info("channel_watcher.start")

    # 1. Trava de Segurança de Fila (Anti-Sobrecarga de Disco)
    pending_count_res = await session.execute(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.done,
            Job.approval_status == "pending"
        )
    )
    pending_count = pending_count_res.scalar() or 0
    if pending_count >= max_total_pending:
        logger.info(
            "channel_watcher.throttled",
            pending_count=pending_count,
            limit=max_total_pending,
            msg="Fila de aprovação cheia. Aguardando revisão do usuário antes de baixar novos vídeos."
        )
        return []

    # 2. Busca canais ativos com monitoramento ligado
    query = select(AuthorizedChannel).where(
        AuthorizedChannel.is_active == True,
        AuthorizedChannel.auto_watch == True
    )
    channels_res = await session.execute(query)
    channels = channels_res.scalars().all()

    enqueued_jobs = []

    for ch in channels:
        target_url = ch.channel_url
        if not target_url and ch.handle:
            target_url = f"https://www.youtube.com/{ch.handle}/videos"
        elif not target_url and ch.channel_id:
            target_url = f"https://www.youtube.com/channel/{ch.channel_id}/videos"

        if not target_url:
            continue

        entries = probe_channel_latest_videos(target_url, limit=3)
        ch.last_checked_at = datetime.utcnow()

        new_for_ch = 0
        for entry in entries:
            if new_for_ch >= max_new_per_channel:
                break

            video_url = entry["url"]

            # Verifica se já existe Job criado com este link
            existing_res = await session.execute(select(Job.id).where(Job.source_url == video_url).limit(1))
            if existing_res.scalar_one_or_none():
                continue

            # Obtém metadados do vídeo e valida carência mínima
            try:
                meta = probe_youtube_metadata(video_url)
            except Exception as e:
                logger.warning("channel_watcher.video_probe_error", url=video_url, error=str(e))
                continue

            is_auth, reason, matched = await check_channel_authorization(meta, session)
            if not is_auth:
                # Se ainda estiver em carência (grace period), não cria job e tenta mais tarde
                logger.info("channel_watcher.skipped_not_ready", url=video_url, reason=reason)
                continue

            # Cria Job automático com todas as proteções Fair Use ativas
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                user_id=None,
                source_type="youtube",
                source_url=video_url,
                cut_mode="highlights_single",
                part_duration=60,
                max_clip_duration=60,
                max_clips=3,
                platforms=["buffer"],
                subtitle_style="karaoke",
                aspect_mode="fill",
                niche_preset="general",
                enable_hook=True,
                enable_bgm=True,
                speed_boost=1.03,
                enable_headline=True,
                horizontal_flip=False,
                watermark_text=ch.handle or None,
                publish_mode="shareNow",
                requires_approval=True, # Modo Aprovação Prévia sempre ativo para watcher
                approval_status="pending",
                channel_name=meta.get("channel_name") or ch.name,
                channel_id=meta.get("channel_id") or ch.channel_id,
                channel_handle=meta.get("channel_handle") or ch.handle,
                upload_date=str(meta.get("upload_date") or ""),
            )
            session.add(job)
            ch.last_video_id = entry["id"]
            await session.commit()

            # Enfileira pipeline de IA
            celery_app.send_task("workers.pipeline_task.run_pipeline", args=[job.id])
            logger.info("channel_watcher.job_enqueued", job_id=job.id, video=video_url, channel=ch.name)
            enqueued_jobs.append(job.id)
            new_for_ch += 1

            # Recalcula pendentes para não ultrapassar limite global
            pending_count += 1
            if pending_count >= max_total_pending:
                logger.info("channel_watcher.reached_queue_limit", total=pending_count)
                return enqueued_jobs

        await session.commit()

    return enqueued_jobs
