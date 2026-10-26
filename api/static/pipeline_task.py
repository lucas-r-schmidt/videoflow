from pathlib import Path
import structlog
from celery import Task
from sqlalchemy.orm import Session

from workers.celery_app import celery_app
from models.database import Job, JobStatus, AsyncSessionLocal
from services.downloader import download_youtube, download_google_drive
from services.ai_analyzer import transcribe_video, find_highlights_by_energy
from services.video_processor import cut_and_convert_to_vertical, split_into_parts
from services.publishers.instagram import publish_reel
from services.publishers.tiktok import publish_tiktok
from services.publishers.kwai import prepare_kwai_upload
from services.publishers.buffer_gateway import publish_buffer_gateway
from config import settings

logger = structlog.get_logger()
OUTPUT_DIR = settings.VIDEO_OUTPUT_DIR


@celery_app.task(
    name="workers.pipeline_task.run_pipeline",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def run_pipeline(self, job_id: str):
    """Pipeline síncrono — Celery worker roda em thread, não async."""
    import asyncio
    asyncio.run(_run(self, job_id))


async def _run(task: Task, job_id: str):
    from models.database import engine, AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                logger.warning("pipeline.job.not_found", job_id=job_id)
                return
            log = logger.bind(job_id=job_id)

            try:
                # ── 1. Download ───────────────────────────────────
                await _set_status(session, job, JobStatus.downloading)
                log.info("pipeline.download.start")

                if job.source_type == "upload":
                    video_path = Path(job.source_url)
                    if not video_path.exists():
                        raise FileNotFoundError(f"Arquivo de upload não encontrado: {video_path}")
                elif job.source_type == "youtube":
                    video_path = download_youtube(job.source_url, job_id)
                else:
                    video_path = download_google_drive(job.drive_file_id or job.source_url, job_id)

                log.info("pipeline.download.done", path=str(video_path))

                # ── 2. Análise / Corte ────────────────────────────
                await _set_status(session, job, JobStatus.analyzing)

                cut_mode_str = (job.cut_mode or "highlights").lower()
                is_highlights = "highlight" in cut_mode_str or "melhor" in cut_mode_str or cut_mode_str in ("", "highlights")

                if is_highlights:
                    log.info("pipeline.analysis.transcribe.start")
                    segments = transcribe_video(str(video_path))

                    if segments:
                        # Gera copy viral (gancho, legenda formatada, CTA e título para Shorts)
                        try:
                            from services.ai_analyzer import generate_viral_copy
                            clip_text = " ".join(s.get("text", "") for s in segments)
                            copy_res = generate_viral_copy(clip_text)
                            job.generated_caption = copy_res.get("caption")
                            job.generated_title = copy_res.get("title")
                            if getattr(job, "enable_hook", True) and not getattr(job, "hook_text", None):
                                job.hook_text = copy_res.get("hook")
                            log.info("pipeline.viral_copy.done", title=job.generated_title, hook=job.hook_text)
                        except Exception as e:
                            log.warning("pipeline.viral_copy.failed", error=str(e))

                        # tenta ranking com LLM (Groq/OpenAI/Ollama); fallback para energia de áudio
                        try:
                            from services.ai_analyzer import rank_segments_ai
                            best = rank_segments_ai(segments, job.max_clip_duration)
                        except Exception as e:
                            log.warning("pipeline.ai_ranking.failed", error=str(e))
                            best = find_highlights_by_energy(str(video_path), job.max_clip_duration)
                    else:
                        best = find_highlights_by_energy(str(video_path), job.max_clip_duration)

                    await _set_status(session, job, JobStatus.processing)
                    asp_mode = getattr(job, "aspect_mode", "fill") or "fill"
                    sub_style = getattr(job, "subtitle_style", "none")
                    hook = job.hook_text if getattr(job, "enable_hook", True) else None
                    output_files = [
                        str(cut_and_convert_to_vertical(
                            video_path,
                            seg["start"], seg["end"],
                            f"{OUTPUT_DIR}/{job_id}_clip{i}.mp4",
                            segments=segments,
                            subtitle_style=sub_style,
                            aspect_mode=asp_mode,
                            hook_text=hook,
                        ))
                        for i, seg in enumerate(best[:job.max_clips])
                    ]
                else:
                    await _set_status(session, job, JobStatus.processing)
                    sub_style = getattr(job, "subtitle_style", "none")
                    asp_mode = getattr(job, "aspect_mode", "fill") or "fill"
                    segs_for_subs = None
                    if sub_style != "none":
                        try:
                            log.info("pipeline.transcription.subtitles.start")
                            segs_for_subs = transcribe_video(str(video_path))
                        except Exception as e:
                            log.warning("pipeline.transcription.subtitles.failed", error=str(e))

                    hook = job.hook_text if getattr(job, "enable_hook", True) else False
                    max_p = getattr(job, "max_clips", None)
                    output_files = [str(p) for p in split_into_parts(
                        video_path, job_id, job.part_duration,
                        segments=segs_for_subs,
                        subtitle_style=sub_style,
                        aspect_mode=asp_mode,
                        hook_text=hook,
                        max_parts=max_p if (max_p and max_p > 0) else None,
                    )]

                log.info("pipeline.processing.done", clips=len(output_files))

                # ── 3. Publicação ─────────────────────────────────
                await _set_status(session, job, JobStatus.publishing)
                total_parts = len(output_files)

                for platform in job.platforms:
                    for idx, file_path in enumerate(output_files, 1):
                        part_no = idx if not is_highlights else None
                        tot_no = total_parts if not is_highlights else None
                        await _publish(
                            platform,
                            file_path,
                            job,
                            log,
                            part_index=part_no,
                            total_parts=tot_no,
                        )

                # ── 4. Concluído ──────────────────────────────────
                job.output_files = output_files
                await _set_status(session, job, JobStatus.done)
                log.info("pipeline.done")

                # Limpeza imediata do arquivo bruto temporário para não saturar disco
                try:
                    if video_path and video_path.exists():
                        video_path.unlink(missing_ok=True)
                        log.info("pipeline.cleanup.raw_video_deleted", path=str(video_path))
                except Exception:
                    pass

            except Exception as exc:
                log.error("pipeline.failed", error=str(exc))
                job.error_message = str(exc)
                await _set_status(session, job, JobStatus.failed)
                task.retry(exc=exc)
    finally:
        await engine.dispose()


async def _set_status(session, job: Job, status: JobStatus):
    job.status = status
    await session.commit()


async def _publish(
    platform: str,
    file_path: str,
    job: Job,
    log,
    part_index: int | None = None,
    total_parts: int | None = None,
):
    log.info("pipeline.publish.start", platform=platform, file=file_path, part=part_index)
    try:
        plat_lower = (platform or "").lower().strip()
        if plat_lower in ("buffer", "buffer_gateway", "clipe-que-vale", "clipe_que_vale"):
            await publish_buffer_gateway(file_path, job, part_index=part_index, total_parts=total_parts)
        elif plat_lower == "instagram":
            await publish_reel(file_path, job, part_index=part_index, total_parts=total_parts)
        elif plat_lower == "tiktok":
            await publish_tiktok(file_path, job, part_index=part_index, total_parts=total_parts)
        elif plat_lower == "kwai":
            await prepare_kwai_upload(job.id, file_path)
    except Exception as e:
        log.error("pipeline.publish.error", platform=platform, error=str(e))
