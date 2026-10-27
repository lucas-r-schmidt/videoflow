from pathlib import Path
import structlog
from celery import Task
from sqlalchemy.orm import Session

from workers.celery_app import celery_app
from models.database import Job, JobStatus, AsyncSessionLocal
from services.downloader import download_youtube, download_google_drive
from services.ai_analyzer import transcribe_video, find_highlights_by_energy
from services.video_processor import (
    cut_and_convert_to_vertical,
    split_into_parts,
    plan_part_intervals,
    _probe_duration,
)
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
                auto_split_long = ("single" not in cut_mode_str)
                part_metadata = {}

                if is_highlights:
                    log.info("pipeline.analysis.transcribe.start")
                    segments = transcribe_video(str(video_path))

                    niche = getattr(job, "niche_preset", "general") or "general"
                    if segments:
                        # 1. Ranking multimodal com Gemini (ouve entonação/clímax); fallback LLM texto; fallback energia de áudio
                        best = None
                        if getattr(settings, "GEMINI_API_KEY", None):
                            try:
                                from services.ai_analyzer import rank_segments_gemini_multimodal
                                best = rank_segments_gemini_multimodal(str(video_path), job.max_clip_duration, getattr(job, "max_clips", 3), niche_preset=niche)
                                if best:
                                    log.info("pipeline.gemini_multimodal.success", clips=len(best))
                            except Exception as me:
                                log.warning("pipeline.gemini_multimodal.failed", error=str(me))

                        if not best:
                            try:
                                from services.ai_analyzer import rank_segments_ai
                                best = rank_segments_ai(segments, job.max_clip_duration, getattr(job, "max_clips", 3), niche_preset=niche)
                            except Exception as e:
                                log.warning("pipeline.ai_ranking.failed", error=str(e))
                                best = None

                        if not best:
                            log.info("pipeline.fallback_to_energy_highlights", reason="ai_ranking_empty_or_failed")
                            best = find_highlights_by_energy(str(video_path), job.max_clip_duration)

                        if not best:
                            clip_dur = float(getattr(job, "max_clip_duration", 60) or 60)
                            best = [{"start": 0.0, "end": clip_dur, "score": 10.0}]

                        # 2. Gera copy viral (gancho, legenda, CTA e título) a partir do trecho ESCOLHIDO
                        try:
                            from services.ai_analyzer import generate_viral_copy
                            if best:
                                top_clip = best[0]
                                c_segs = [s for s in segments if s["end"] >= top_clip["start"] and s["start"] <= top_clip["end"]]
                                clip_text = " ".join(s.get("text", "") for s in c_segs)
                            else:
                                clip_text = " ".join(s.get("text", "") for s in segments)

                            copy_res = generate_viral_copy(clip_text, niche_preset=niche)
                            job.generated_caption = copy_res.get("caption")
                            job.generated_title = copy_res.get("title")
                            if getattr(job, "enable_hook", True) and not getattr(job, "hook_text", None):
                                job.hook_text = copy_res.get("hook")
                            log.info("pipeline.viral_copy.done", title=job.generated_title, hook=job.hook_text)
                        except Exception as e:
                            log.warning("pipeline.viral_copy.failed", error=str(e))
                    else:
                        best = find_highlights_by_energy(str(video_path), job.max_clip_duration)

                    await _set_status(session, job, JobStatus.processing)
                    asp_mode = getattr(job, "aspect_mode", "fill") or "fill"
                    sub_style = getattr(job, "subtitle_style", "none")
                    hook = job.hook_text if getattr(job, "enable_hook", True) else None

                    from services.video_processor import _find_best_cut_point

                    output_files = []
                    clip_counter = 0

                    max_c = getattr(job, "max_clips", 3)
                    if max_c == 0:
                        selected_clips = [c for c in best if float(c.get("score", 0)) >= 7.0][:12]
                        if not selected_clips and best:
                            selected_clips = best[:3]
                    else:
                        selected_clips = best[:max_c]

                    jump_cut_enabled = getattr(job, "jump_cut", True)
                    if jump_cut_enabled is None:
                        jump_cut_enabled = True

                    enable_bgm = getattr(job, "enable_bgm", True)
                    speed_boost = float(getattr(job, "speed_boost", 1.03) or 1.03)
                    enable_headline = getattr(job, "enable_headline", True)
                    horizontal_flip = getattr(job, "horizontal_flip", False)
                    watermark_text = getattr(job, "watermark_text", None)

                    for i, seg in enumerate(selected_clips):
                        s_start = float(seg["start"])
                        s_end = float(seg["end"])
                        dur = s_end - s_start

                        # Se auto-split estiver ativo e o corte passar de 65s, fatia em partes de até ~58s
                        if auto_split_long and dur > 65.0:
                            subparts = []
                            c_start = s_start
                            while c_start < s_end:
                                rem = s_end - c_start
                                if rem <= 62.0:
                                    subparts.append((c_start, s_end))
                                    break
                                target = c_start + 58.0
                                cut = _find_best_cut_point(target, segments, s_end, video_path=video_path)
                                if cut <= c_start or (cut - c_start) < 25.0:
                                    cut = min(c_start + 58.0, s_end)
                                subparts.append((c_start, cut))
                                c_start = cut

                            tot_sub = len(subparts)
                            for p_num, (p_start, p_end) in enumerate(subparts, 1):
                                p_hook = hook
                                if getattr(job, "enable_hook", True):
                                    if hook and tot_sub > 1:
                                        p_hook = f"{hook} (PARTE {p_num}/{tot_sub})"
                                    elif tot_sub > 1:
                                        p_hook = f"PARTE {p_num}/{tot_sub} 👀"

                                part_title = f"{job.generated_title} (Parte {p_num}/{tot_sub})" if (job.generated_title and tot_sub > 1) else (job.generated_title or p_hook)

                                out_file = str(cut_and_convert_to_vertical(
                                    video_path,
                                    p_start, p_end,
                                    f"{OUTPUT_DIR}/{job_id}_clip{clip_counter}.mp4",
                                    segments=segments,
                                    subtitle_style=sub_style,
                                    aspect_mode=asp_mode,
                                    hook_text=p_hook,
                                    headline_text=part_title if enable_headline else None,
                                    jump_cut=jump_cut_enabled,
                                    enable_bgm=enable_bgm,
                                    speed_boost=speed_boost,
                                    horizontal_flip=horizontal_flip,
                                    watermark_text=watermark_text,
                                ))
                                output_files.append(out_file)
                                clip_counter += 1

                                if job.generated_title:
                                    part_metadata[clip_counter] = {
                                        "title": part_title,
                                        "caption": job.generated_caption,
                                    }
                        else:
                            headline_val = (job.generated_title or hook) if enable_headline else None
                            out_file = str(cut_and_convert_to_vertical(
                                video_path,
                                s_start, s_end,
                                f"{OUTPUT_DIR}/{job_id}_clip{clip_counter}.mp4",
                                segments=segments,
                                subtitle_style=sub_style,
                                aspect_mode=asp_mode,
                                hook_text=hook,
                                headline_text=headline_val,
                                jump_cut=jump_cut_enabled,
                                enable_bgm=enable_bgm,
                                speed_boost=speed_boost,
                                horizontal_flip=horizontal_flip,
                                watermark_text=watermark_text,
                            ))
                            output_files.append(out_file)
                            clip_counter += 1
                            if job.generated_title:
                                part_metadata[clip_counter] = {
                                    "title": job.generated_title,
                                    "caption": job.generated_caption,
                                }
                else:
                    await _set_status(session, job, JobStatus.processing)
                    sub_style = getattr(job, "subtitle_style", "none")
                    asp_mode = getattr(job, "aspect_mode", "fill") or "fill"
                    enable_bgm = getattr(job, "enable_bgm", True)
                    speed_boost = float(getattr(job, "speed_boost", 1.03) or 1.03)
                    enable_headline = getattr(job, "enable_headline", True)
                    horizontal_flip = getattr(job, "horizontal_flip", False)
                    watermark_text = getattr(job, "watermark_text", None)

                    # 1. Transcreve vídeo para snapping inteligente e legendas
                    segs = None
                    try:
                        log.info("pipeline.transcription.start")
                        segs = transcribe_video(str(video_path))
                    except Exception as e:
                        log.warning("pipeline.transcription.failed", error=str(e))

                    # 2. Planeja intervalos com corte inteligente nas falas e cenas
                    total_dur = _probe_duration(video_path)
                    max_p = getattr(job, "max_clips", None)
                    # Hard limit de segurança (máximo 30 partes) se não definido ou 0
                    effective_max = max_p if (max_p and max_p > 0) else 30
                    intervals = plan_part_intervals(total_dur, job.part_duration, segments=segs, max_parts=effective_max, video_path=video_path)
                    total_parts = len(intervals)

                    # 3. Copies individuais e ganchos contextuais por parte via IA
                    part_hooks = []
                    enable_hook = getattr(job, "enable_hook", True)
                    custom_hook = job.hook_text if enable_hook else False

                    for start, end, idx in intervals:
                        p_hook = custom_hook
                        p_meta = None
                        if segs and enable_hook and not getattr(job, "hook_text", None):
                            p_segs = [s for s in segs if s["end"] > start and s["start"] < end]
                            p_text = " ".join(s.get("text", "") for s in p_segs)
                            if p_text.strip():
                                try:
                                    from services.ai_analyzer import generate_part_copy
                                    niche = getattr(job, "niche_preset", "general") or "general"
                                    p_meta = generate_part_copy(p_text, idx, total_parts, niche_preset=niche)
                                    p_hook = p_meta.get("hook")
                                except Exception as e:
                                    log.warning("pipeline.part_copy.failed", part=idx, error=str(e))

                        part_hooks.append(p_hook if enable_hook else False)
                        if p_meta:
                            part_metadata[idx] = p_meta

                    part_headlines = None
                    if enable_headline:
                        part_headlines = [
                            part_metadata.get(idx, {}).get("title") or job.generated_title or f"PARTE {idx} 🔥"
                            for _, _, idx in intervals
                        ]

                    output_files = [str(p) for p in split_into_parts(
                        video_path, job_id, job.part_duration,
                        segments=segs,
                        subtitle_style=sub_style,
                        aspect_mode=asp_mode,
                        hook_texts=part_hooks if enable_hook else None,
                        hook_text=custom_hook,
                        headline_texts=part_headlines,
                        headline_text=job.generated_title if enable_headline else None,
                        enable_bgm=enable_bgm,
                        speed_boost=speed_boost,
                        horizontal_flip=horizontal_flip,
                        watermark_text=watermark_text,
                        max_parts=effective_max,
                    )]

                log.info("pipeline.processing.done", clips=len(output_files))

                # Purge imediato do vídeo fonte bruto (economia de 98% de espaço no disco)
                try:
                    if video_path and video_path.exists() and job.source_type in ("youtube", "url", "google_drive"):
                        freed_mb = round(video_path.stat().st_size / (1024 * 1024), 1)
                        video_path.unlink(missing_ok=True)
                        log.info("pipeline.raw_video_purged", freed_mb=freed_mb)
                except Exception as e:
                    log.warning("pipeline.raw_video_purge_failed", error=str(e))

                # ── 3. Armazenamento e Sincronização dos Cortes ────────
                try:
                    from services.storage import upload_to_r2, is_r2_configured
                    if is_r2_configured():
                        r2_urls = []
                        for f in output_files:
                            url_res = upload_to_r2(f)
                            r2_urls.append(url_res or f)
                        job.output_files = r2_urls
                        log.info("pipeline.storage.r2_synced", count=len(r2_urls))
                    else:
                        job.output_files = output_files
                except Exception as e:
                    log.warning("pipeline.storage.r2_failed", error=str(e))
                    job.output_files = output_files

                # ── 4. Publicação ou Fila de Aprovação (Human-in-the-Loop) ──
                requires_approval = getattr(job, "requires_approval", True)
                approval_status = getattr(job, "approval_status", "pending")
                should_auto_publish = (not requires_approval) or (approval_status == "approved")

                if should_auto_publish and job.platforms:
                    await _set_status(session, job, JobStatus.publishing)
                    total_parts = len(output_files)

                    for platform in job.platforms:
                        for idx, file_path in enumerate(output_files, 1):
                            part_meta = part_metadata.get(idx)
                            part_no = idx if (not is_highlights or total_parts > 1) else None
                            tot_no = total_parts if (not is_highlights or total_parts > 1) else None
                            p_title = part_meta.get("title") if part_meta else job.generated_title
                            p_caption = part_meta.get("caption") if part_meta else job.generated_caption
                            await _publish(
                                platform,
                                file_path,
                                job,
                                log,
                                part_index=part_no,
                                total_parts=tot_no,
                                part_title=p_title,
                                part_caption=p_caption,
                            )
                    job.approval_status = "published"
                    log.info("pipeline.auto_published", platforms=job.platforms)
                else:
                    job.approval_status = "pending"
                    log.info("pipeline.awaiting_user_approval", job_id=job.id, clips=len(output_files))

                # ── 5. Concluído ──────────────────────────────────
                session.add(job)
                await session.commit()
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
                try:
                    await session.refresh(job)
                    if job.status == JobStatus.cancelled:
                        log.info("pipeline.aborted", reason="cancelled_by_user")
                        return
                except Exception:
                    pass
                log.error("pipeline.failed", error=str(exc))
                job.error_message = str(exc)
                await _set_status(session, job, JobStatus.failed)
                task.retry(exc=exc)
    finally:
        await engine.dispose()


async def _set_status(session, job: Job, status: JobStatus):
    try:
        from sqlalchemy import select
        res = await session.execute(select(Job.status).where(Job.id == job.id))
        current_status = res.scalar_one_or_none()
        if current_status == JobStatus.cancelled:
            job.status = JobStatus.cancelled
            return
    except Exception:
        pass
    job.status = status
    session.add(job)
    await session.commit()


async def _publish(
    platform: str,
    file_path: str,
    job: Job,
    log,
    part_index: int | None = None,
    total_parts: int | None = None,
    part_title: str | None = None,
    part_caption: str | None = None,
):
    log.info("pipeline.publish.start", platform=platform, file=file_path, part=part_index)
    pub_result = None
    try:
        plat_lower = (platform or "").lower().strip()
        if plat_lower in ("buffer", "buffer_gateway", "clipe-que-vale", "clipe_que_vale"):
            pub_result = await publish_buffer_gateway(
                file_path, job,
                part_index=part_index, total_parts=total_parts,
                part_title=part_title, part_caption=part_caption,
            )
        elif plat_lower == "instagram":
            pub_result = await publish_reel(
                file_path, job,
                part_index=part_index, total_parts=total_parts,
                part_title=part_title, part_caption=part_caption,
            )
        elif plat_lower == "tiktok":
            pub_result = await publish_tiktok(
                file_path, job,
                part_index=part_index, total_parts=total_parts,
                part_title=part_title, part_caption=part_caption,
            )
        elif plat_lower == "kwai":
            pub_result = await prepare_kwai_upload(job.id, file_path)

        if pub_result:
            try:
                import json
                existing = []
                if getattr(job, "platform_post_ids", None):
                    try:
                        existing = json.loads(job.platform_post_ids)
                    except Exception:
                        existing = []
                post_id = (
                    pub_result.get("id")
                    or pub_result.get("post_id")
                    or pub_result.get("update_id")
                    or (pub_result.get("updates", [{}])[0].get("id") if isinstance(pub_result.get("updates"), list) and pub_result.get("updates") else None)
                )
                existing.append({
                    "platform": plat_lower,
                    "post_id": str(post_id) if post_id else None,
                    "file": file_path,
                    "part_index": part_index,
                })
                job.platform_post_ids = json.dumps(existing)
            except Exception as e:
                log.warning("pipeline.publish.record_post_id_error", error=str(e))
    except Exception as e:
        log.error("pipeline.publish.error", platform=platform, error=str(e))
    return pub_result


@celery_app.task(
    name="workers.pipeline_task.publish_job_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def publish_job_task(self, job_id: str):
    """Dispara a publicação de um job previamente aprovado pelo usuário."""
    import asyncio
    asyncio.run(_publish_job_async(self, job_id))


@celery_app.task(
    name="workers.pipeline_task.kill_switch_task",
    bind=True,
    max_retries=1,
)
def kill_switch_task(self, job_id: str, reason: str = "Takedown / Kill Switch acionado"):
    """Exclui postagens remotas no Buffer / Instagram e cancela o Job imediatamente."""
    import asyncio
    asyncio.run(_kill_switch_async(self, job_id, reason))


async def _kill_switch_async(task: Task, job_id: str, reason: str):
    import json
    from models.database import engine, AsyncSessionLocal
    from services.publishers.buffer_gateway import delete_buffer_gateway_post
    from services.publishers.instagram import delete_reel

    log = logger.bind(job_id=job_id)
    log.info("kill_switch.start", reason=reason)

    try:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                log.warning("kill_switch.job_not_found")
                return

            post_records = []
            if getattr(job, "platform_post_ids", None):
                try:
                    post_records = json.loads(job.platform_post_ids)
                except Exception:
                    post_records = []

            for rec in post_records:
                plat = rec.get("platform", "").lower()
                pid = rec.get("post_id")
                if not pid:
                    continue
                try:
                    if "buffer" in plat:
                        await delete_buffer_gateway_post(str(pid))
                    elif "instagram" in plat:
                        token = getattr(job, "ig_access_token", None) or ""
                        await delete_reel(str(pid), token)
                    log.info("kill_switch.deleted_remote", platform=plat, post_id=pid)
                except Exception as e:
                    log.error("kill_switch.delete_failed", platform=plat, post_id=pid, error=str(e))

            job.status = JobStatus.cancelled
            job.approval_status = "removed_by_takedown"
            job.error_message = f"Conteúdo removido pelo Kill Switch. Motivo: {reason}"
            await session.commit()
            log.info("kill_switch.completed")
    finally:
        await engine.dispose()


async def _publish_job_async(task: Task, job_id: str):
    from models.database import engine, AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if not job:
                logger.warning("publish_job.not_found", job_id=job_id)
                return

            log = logger.bind(job_id=job_id)
            if not job.output_files:
                log.warning("publish_job.no_output_files")
                return

            await _set_status(session, job, JobStatus.publishing)
            total_parts = len(job.output_files)

            success_count = 0
            for platform in job.platforms:
                for idx, file_path in enumerate(job.output_files, 1):
                    part_no = idx if total_parts > 1 else None
                    tot_no = total_parts if total_parts > 1 else None
                    res = await _publish(
                        platform,
                        file_path,
                        job,
                        log,
                        part_index=part_no,
                        total_parts=tot_no,
                        part_title=job.generated_title,
                        part_caption=job.generated_caption,
                    )
                    if res:
                        success_count += 1

            if success_count > 0:
                job.approval_status = "published"
                job.error_message = None
                await _set_status(session, job, JobStatus.done)
                log.info("publish_job.completed", success_count=success_count)
            else:
                job.approval_status = "approved"
                job.error_message = "Falha ao enviar para o Buffer Gateway (serviço retornou erro)."
                await _set_status(session, job, JobStatus.failed)
                log.error("publish_job.failed_all")
    finally:
        await engine.dispose()


@celery_app.task(
    name="workers.pipeline_task.watch_channels_task",
    bind=True,
    max_retries=1,
)
def watch_channels_task(self):
    """
    Verifica periodicamente se canais autorizados da Whitelist postaram episódios novos.
    Aplica carência mínima e trava de segurança de fila para não lotar o disco.
    """
    import asyncio
    from models.database import engine, AsyncSessionLocal
    from services.channel_watcher import run_channel_watcher

    async def _run():
        try:
            async with AsyncSessionLocal() as session:
                enqueued = await run_channel_watcher(session)
                logger.info("watch_channels_task.finished", count=len(enqueued))
        finally:
            await engine.dispose()

    asyncio.run(_run())


@celery_app.task(
    name="workers.pipeline_task.cleanup_old_files_task",
    bind=True,
    max_retries=1,
)
def cleanup_old_files_task(self):
    """
    Auto-Purge periódico: remove temporários órfãos e arquivos de cortes rejeitados ou antigos (> 7 dias).
    """
    import time
    from pathlib import Path
    from config import settings

    logger.info("cleanup_old_files_task.start")
    freed_bytes = 0

    # 1. Limpa /tmp órfãos com mais de 4 horas
    tmp_dir = Path(settings.VIDEO_TMP_DIR)
    if tmp_dir.exists():
        now = time.time()
        for f in tmp_dir.iterdir():
            try:
                if f.is_file() and (now - f.stat().st_mtime) > (4 * 3600):
                    freed_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
            except Exception:
                pass

    # 2. Limpa saídas antigas (> 7 dias)
    out_dir = Path(settings.VIDEO_OUTPUT_DIR)
    if out_dir.exists():
        now = time.time()
        for f in out_dir.iterdir():
            try:
                if f.is_file() and (now - f.stat().st_mtime) > (7 * 86400):
                    freed_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
            except Exception:
                pass

    logger.info("cleanup_old_files_task.finished", freed_mb=round(freed_bytes / (1024 * 1024), 2))


